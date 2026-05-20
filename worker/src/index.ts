interface Env {
  VIDEOS_BUCKET: R2Bucket;
  APP_ORIGIN: string;
  DEVICE_API_KEY: string;
  WORKER_SIGNING_SECRET: string;
  SUPABASE_URL: string;
  SUPABASE_SERVICE_ROLE_KEY: string;
  SUPABASE_ANON_KEY: string;
}

type UploadUrlRequest = {
  trap_id?: string;
  captured_at?: string;
  filename?: string;
};

type CreateVideoRequest = {
  trap_id?: string;
  captured_at?: string;
  r2_key?: string;
  hunter_note?: string | null;
};

type TrapRow = {
  trap_id: string;
  name: string | null;
  is_armed: boolean;
  last_seen_at: string | null;
  updated_at: string;
  created_at: string;
};

const TOKEN_TTL_SECONDS = 15 * 60;
const PLAY_TTL_SECONDS = 10 * 60;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return corsResponse(null, 204, env, "application/json", request.headers.get("origin"));
    }

    try {
      if (request.method === "POST" && url.pathname === "/upload-url") {
        return await handleUploadUrl(request, env);
      }

      if (request.method === "PUT" && url.pathname.startsWith("/upload/")) {
        return await handleUpload(request, env, url.pathname.slice("/upload/".length));
      }

      if (request.method === "POST" && url.pathname === "/videos") {
        return await handleCreateVideo(request, env);
      }

      const trapMatch = url.pathname.match(/^\/traps\/([^/]+)$/);
      if (request.method === "GET" && url.pathname === "/traps") {
        return await handleTrapList(request, env);
      }

      if (request.method === "GET" && trapMatch) {
        return await handleTrapState(request, env, decodeURIComponent(trapMatch[1]));
      }

      if (request.method === "PATCH" && trapMatch) {
        return await handleTrapUpdate(request, env, decodeURIComponent(trapMatch[1]));
      }

      const playUrlMatch = url.pathname.match(/^\/play-url\/([0-9a-fA-F-]{36})$/);
      if (request.method === "GET" && playUrlMatch) {
        return await handlePlayUrl(request, env, playUrlMatch[1]);
      }

      if ((request.method === "GET" || request.method === "HEAD") && url.pathname.startsWith("/play/")) {
        return await handlePlay(request, env, url.pathname.slice("/play/".length));
      }

      return json({ error: "not_found" }, 404, env, request.headers.get("origin"));
    } catch (error) {
      console.error(error);
      const message = error instanceof HttpError ? error.message : "internal_error";
      const status = error instanceof HttpError ? error.status : 500;
      return json({ error: message }, status, env, request.headers.get("origin"));
    }
  },
};

async function handleUploadUrl(request: Request, env: Env): Promise<Response> {
  requireDeviceToken(request, env);

  const body = await readJson<UploadUrlRequest>(request);
  const trapId = requireText(body.trap_id, "trap_id");
  const capturedAt = requireIsoDate(body.captured_at, "captured_at");
  const filename = requireText(body.filename, "filename");
  await requireTrapArmed(env, trapId);
  const r2Key = buildR2Key(trapId, capturedAt, filename);
  const exp = nowSeconds() + TOKEN_TTL_SECONDS;
  const token = await signToken({ action: "upload", r2_key: r2Key, trap_id: trapId, exp }, env);
  const uploadUrl = new URL(`/upload/${token}`, request.url).toString();

  return json({ upload_url: uploadUrl, r2_key: r2Key, expires_at: new Date(exp * 1000).toISOString() }, 200, env, request.headers.get("origin"));
}

async function handleUpload(request: Request, env: Env, token: string): Promise<Response> {
  const payload = await verifyToken(token, env);
  if (payload.action !== "upload") {
    throw new HttpError(403, "invalid_token_action");
  }
  if (payload.trap_id) {
    await requireTrapArmed(env, payload.trap_id);
  }

  const contentType = request.headers.get("content-type") || "video/mp4";
  await env.VIDEOS_BUCKET.put(payload.r2_key, request.body, {
    httpMetadata: { contentType },
    customMetadata: { uploaded_at: new Date().toISOString() },
  });

  return json({ ok: true, r2_key: payload.r2_key }, 200, env, request.headers.get("origin"));
}

async function handleCreateVideo(request: Request, env: Env): Promise<Response> {
  requireDeviceToken(request, env);

  const body = await readJson<CreateVideoRequest>(request);
  const trapId = requireText(body.trap_id, "trap_id");
  const capturedAt = requireIsoDate(body.captured_at, "captured_at");
  const r2Key = requireText(body.r2_key, "r2_key");
  await requireTrapArmed(env, trapId);

  const inserted = await supabaseFetch(env, "/rest/v1/videos", {
    method: "POST",
    headers: { Prefer: "return=representation" },
    body: JSON.stringify({
      trap_id: trapId,
      captured_at: capturedAt,
      r2_key: r2Key,
      hunter_note: body.hunter_note ?? null,
      status: "uploaded",
    }),
  });

  return corsResponse(inserted.body, inserted.status, env, getContentType(inserted), request.headers.get("origin"));
}

async function handleTrapState(request: Request, env: Env, trapId: string): Promise<Response> {
  requireDeviceToken(request, env);

  const trap = await getTrap(env, trapId);
  await upsertTrapHeartbeat(env, trapId, trap?.is_armed ?? true);
  const now = new Date().toISOString();

  return json(
    {
      trap_id: trapId,
      is_armed: trap?.is_armed ?? true,
      name: trap?.name ?? null,
      updated_at: trap?.updated_at ?? new Date().toISOString(),
      last_seen_at: now,
    },
    200,
    env,
    request.headers.get("origin"),
  );
}

async function handleTrapList(request: Request, env: Env): Promise<Response> {
  await requireSupabaseUser(request, env);

  const found = await supabaseFetch(
    env,
    "/rest/v1/traps?select=trap_id,name,is_armed,last_seen_at,updated_at,created_at&order=trap_id.asc",
    { method: "GET" },
  );

  return corsResponse(found.body, found.status, env, getContentType(found), request.headers.get("origin"));
}

async function handleTrapUpdate(request: Request, env: Env, trapId: string): Promise<Response> {
  const user = await requireSupabaseUser(request, env);
  await requireSupabaseAdmin(env, user.id);

  const body = await readJson<{ is_armed?: boolean; name?: string | null }>(request);
  if (typeof body.is_armed !== "boolean") {
    throw new HttpError(400, "missing_is_armed");
  }

  const updated = await supabaseFetch(env, `/rest/v1/traps?trap_id=eq.${encodeURIComponent(trapId)}`, {
    method: "PATCH",
    headers: { Prefer: "return=representation" },
    body: JSON.stringify({
      is_armed: body.is_armed,
      name: body.name ?? null,
      updated_at: new Date().toISOString(),
    }),
  });

  return corsResponse(updated.body, updated.status, env, getContentType(updated), request.headers.get("origin"));
}

async function handlePlayUrl(request: Request, env: Env, videoId: string): Promise<Response> {
  await requireSupabaseUser(request, env);

  const found = await supabaseFetch(
    env,
    `/rest/v1/videos?id=eq.${encodeURIComponent(videoId)}&select=id,r2_key`,
    { method: "GET" },
  );

  if (!found.ok) {
    return corsResponse(found.body, found.status, env, getContentType(found), request.headers.get("origin"));
  }

  const rows = (await found.json()) as Array<{ id: string; r2_key: string }>;
  if (rows.length === 0) {
    throw new HttpError(404, "video_not_found");
  }

  const exp = nowSeconds() + PLAY_TTL_SECONDS;
  const token = await signToken({ action: "play", r2_key: rows[0].r2_key, exp }, env);
  return json({ play_url: new URL(`/play/${token}`, request.url).toString(), expires_at: new Date(exp * 1000).toISOString() }, 200, env, request.headers.get("origin"));
}

async function handlePlay(request: Request, env: Env, token: string): Promise<Response> {
  const payload = await verifyToken(token, env);
  if (payload.action !== "play") {
    throw new HttpError(403, "invalid_token_action");
  }

  const object = await env.VIDEOS_BUCKET.get(payload.r2_key, {
    range: request.headers,
  });

  if (!object) {
    throw new HttpError(404, "object_not_found");
  }

  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set("etag", object.httpEtag);
  headers.set("accept-ranges", "bytes");
  headers.set("cache-control", "private, max-age=300");
  addCors(headers, env, request.headers.get("origin"));

  const status = object.range ? 206 : 200;
  if (object.range) {
    const { start, end } = contentRangeBounds(request.headers.get("range"), object.range, object.size);
    headers.set("content-range", `bytes ${start}-${end}/${object.size}`);
    headers.set("content-length", String(end - start + 1));
  } else {
    headers.set("content-length", String(object.size));
  }

  if (request.method === "HEAD") {
    return new Response(null, { status, headers });
  }

  return new Response(object.body, { status, headers });
}

async function requireSupabaseUser(request: Request, env: Env): Promise<{ id: string; email?: string }> {
  const authorization = request.headers.get("authorization");
  if (!authorization?.startsWith("Bearer ")) {
    throw new HttpError(401, "missing_bearer_token");
  }

  const response = await fetch(`${env.SUPABASE_URL}/auth/v1/user`, {
    headers: {
      apikey: env.SUPABASE_ANON_KEY,
      authorization,
    },
  });

  if (!response.ok) {
    throw new HttpError(401, "invalid_user_token");
  }

  const user = (await response.json()) as { id?: string; email?: string };
  if (!user.id) {
    throw new HttpError(401, "invalid_user_token");
  }

  return { id: user.id, email: user.email };
}

function requireDeviceToken(request: Request, env: Env): void {
  const token = request.headers.get("x-device-token");
  if (!token || token !== env.DEVICE_API_KEY) {
    throw new HttpError(401, "invalid_device_token");
  }
}

async function requireTrapArmed(env: Env, trapId: string): Promise<void> {
  const trap = await getTrap(env, trapId);
  if (trap && !trap.is_armed) {
    throw new HttpError(409, "trap_disarmed");
  }
}

async function requireSupabaseAdmin(env: Env, userId: string): Promise<void> {
  const response = await supabaseFetch(
    env,
    `/rest/v1/profiles?id=eq.${encodeURIComponent(userId)}&select=role&limit=1`,
    { method: "GET" },
  );

  if (!response.ok) {
    throw new HttpError(502, "profile_lookup_failed");
  }

  const rows = (await response.json()) as Array<{ role?: string }>;
  if (rows[0]?.role !== "admin") {
    throw new HttpError(403, "admin_required");
  }
}

async function getTrap(env: Env, trapId: string): Promise<TrapRow | null> {
  const response = await supabaseFetch(
    env,
    `/rest/v1/traps?trap_id=eq.${encodeURIComponent(trapId)}&select=trap_id,name,is_armed,last_seen_at,updated_at,created_at&limit=1`,
    { method: "GET" },
  );

  if (!response.ok) {
    throw new HttpError(502, "trap_lookup_failed");
  }

  const rows = (await response.json()) as TrapRow[];
  return rows[0] ?? null;
}

async function upsertTrapHeartbeat(env: Env, trapId: string, isArmed: boolean): Promise<void> {
  const response = await supabaseFetch(env, "/rest/v1/traps?on_conflict=trap_id", {
    method: "POST",
    headers: { Prefer: "resolution=merge-duplicates,return=minimal" },
    body: JSON.stringify({
      trap_id: trapId,
      is_armed: isArmed,
      last_seen_at: new Date().toISOString(),
    }),
  });

  if (!response.ok) {
    console.error("Failed to update trap heartbeat", await response.text());
  }
}

async function supabaseFetch(env: Env, path: string, init: RequestInit): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("apikey", env.SUPABASE_SERVICE_ROLE_KEY);
  headers.set("authorization", `Bearer ${env.SUPABASE_SERVICE_ROLE_KEY}`);
  headers.set("content-type", "application/json");

  return fetch(`${env.SUPABASE_URL}${path}`, { ...init, headers });
}

async function readJson<T>(request: Request): Promise<T> {
  try {
    return await request.json<T>();
  } catch {
    throw new HttpError(400, "invalid_json");
  }
}

function requireText(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim() === "") {
    throw new HttpError(400, `missing_${field}`);
  }
  return value.trim();
}

function requireIsoDate(value: unknown, field: string): string {
  const text = requireText(value, field);
  if (Number.isNaN(Date.parse(text))) {
    throw new HttpError(400, `invalid_${field}`);
  }
  return text;
}

function buildR2Key(trapId: string, capturedAt: string, filename: string): string {
  const safeTrapId = sanitizePathPart(trapId);
  const safeFilename = sanitizeFilename(filename);
  const match = capturedAt.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!match) {
    throw new HttpError(400, "invalid_captured_at");
  }
  const [, year, month, day] = match;
  const unique = crypto.randomUUID().slice(0, 8);
  return `videos/${safeTrapId}/${year}/${month}/${day}/${unique}-${safeFilename}`;
}

function sanitizePathPart(value: string): string {
  return value.trim().replace(/[^A-Za-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "") || "unknown";
}

function sanitizeFilename(value: string): string {
  return value.trim().split(/[\\/]/).pop()?.replace(/[^A-Za-z0-9._-]+/g, "-") || "video.mp4";
}

async function signToken(payload: TokenPayload, env: Env): Promise<string> {
  const body = base64UrlEncode(JSON.stringify(payload));
  const signature = await hmac(body, env.WORKER_SIGNING_SECRET);
  return `${body}.${signature}`;
}

async function verifyToken(token: string, env: Env): Promise<TokenPayload> {
  const [body, signature] = token.split(".");
  if (!body || !signature) {
    throw new HttpError(403, "invalid_token");
  }

  const expected = await hmac(body, env.WORKER_SIGNING_SECRET);
  if (signature !== expected) {
    throw new HttpError(403, "invalid_token_signature");
  }

  const payload = JSON.parse(base64UrlDecode(body)) as TokenPayload;
  if (payload.exp < nowSeconds()) {
    throw new HttpError(403, "expired_token");
  }
  return payload;
}

async function hmac(message: string, secret: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(message));
  return base64UrlEncodeBytes(new Uint8Array(signature));
}

function base64UrlEncode(value: string): string {
  return base64UrlEncodeBytes(new TextEncoder().encode(value));
}

function base64UrlEncodeBytes(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function base64UrlDecode(value: string): string {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  const binary = atob(padded);
  return new TextDecoder().decode(Uint8Array.from(binary, (char) => char.charCodeAt(0)));
}

function nowSeconds(): number {
  return Math.floor(Date.now() / 1000);
}

function json(body: unknown, status: number, env: Env, requestOrigin: string | null = null): Response {
  return corsResponse(JSON.stringify(body), status, env, "application/json", requestOrigin);
}

function corsResponse(
  body: BodyInit | null,
  status: number,
  env: Env,
  contentType = "application/json",
  requestOrigin: string | null = null,
): Response {
  const headers = new Headers({ "content-type": contentType });
  addCors(headers, env, requestOrigin);
  return new Response(body, { status, headers });
}

function getContentType(response: Response): string {
  return response.headers.get("content-type") || "application/json";
}

function contentRangeBounds(rangeHeader: string | null, range: R2Range, totalSize: number): { start: number; end: number } {
  const parsedFromHeader = parseHttpRange(rangeHeader, totalSize);
  if (parsedFromHeader) {
    return parsedFromHeader;
  }

  if ("suffix" in range && typeof range.suffix === "number") {
    const start = Math.max(totalSize - range.suffix, 0);
    return { start, end: totalSize - 1 };
  }

  const rangeWithOffset = range as { offset?: number; length?: number };
  const start = typeof rangeWithOffset.offset === "number" ? rangeWithOffset.offset : 0;
  const length = typeof rangeWithOffset.length === "number" ? rangeWithOffset.length : totalSize - start;
  return { start, end: Math.min(start + length - 1, totalSize - 1) };
}

function parseHttpRange(rangeHeader: string | null, totalSize: number): { start: number; end: number } | null {
  if (!rangeHeader) {
    return null;
  }

  const match = rangeHeader.match(/^bytes=(\d*)-(\d*)$/i);
  if (!match) {
    return null;
  }

  const [, startText, endText] = match;

  if (startText === "" && endText === "") {
    return null;
  }

  if (startText === "") {
    const suffixLength = Number(endText);
    if (!Number.isFinite(suffixLength) || suffixLength <= 0) {
      return null;
    }
    const start = Math.max(totalSize - suffixLength, 0);
    return { start, end: totalSize - 1 };
  }

  const start = Number(startText);
  if (!Number.isFinite(start) || start < 0 || start >= totalSize) {
    return null;
  }

  if (endText === "") {
    return { start, end: totalSize - 1 };
  }

  const end = Number(endText);
  if (!Number.isFinite(end) || end < start) {
    return null;
  }

  return { start, end: Math.min(end, totalSize - 1) };
}

function addCors(headers: Headers, env: Env, requestOrigin: string | null = null): void {
  headers.set("access-control-allow-origin", resolveCorsOrigin(requestOrigin, env.APP_ORIGIN));
  headers.set("access-control-allow-methods", "GET,POST,PUT,PATCH,OPTIONS");
  headers.set("access-control-allow-headers", "authorization,content-type,x-device-token");
}

function resolveCorsOrigin(requestOrigin: string | null, fallbackOrigin: string): string {
  if (!requestOrigin) {
    return fallbackOrigin;
  }

  try {
    const originUrl = new URL(requestOrigin);
    if (originUrl.hostname === "localhost" || originUrl.hostname === "127.0.0.1") {
      return requestOrigin;
    }

    const fallbackUrl = new URL(fallbackOrigin);
    if (
      originUrl.protocol === "https:" &&
      (originUrl.hostname === fallbackUrl.hostname ||
        originUrl.hostname.endsWith(`.${fallbackUrl.hostname}`))
    ) {
      return requestOrigin;
    }
  } catch {
    return fallbackOrigin;
  }

  return fallbackOrigin;
}

class HttpError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

type TokenPayload = {
  action: "upload" | "play";
  r2_key: string;
  trap_id?: string;
  exp: number;
};
