import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { LogOut, Play, RefreshCw } from "lucide-react";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "./supabase";
import type { Profile, Trap, Video } from "./types";
import "./styles.css";

const apiBaseUrl = import.meta.env.VITE_WORKER_API_URL as string | undefined;

// 屋久島フィールド投入 (2026-08-11 15:30 JST) 以降の動画は全件表示する。
// それ以前はベンチテストの動画なので従来どおり直近だけ見えれば足りる。
const FIELD_DEPLOY_CUTOFF = "2026-08-11T15:30:00+09:00";

function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [loadingSession, setLoadingSession] = useState(true);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoadingSession(false);
    });

    const { data } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
    });

    return () => data.subscription.unsubscribe();
  }, []);

  if (loadingSession) {
    return <div className="screen center">読み込み中...</div>;
  }

  return session ? <VideoDashboard session={session} /> : <LoginScreen />;
}

function LoginScreen() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });
    setSubmitting(false);
    if (signInError) {
      setError("メールアドレスまたはパスワードを確認してください。");
    }
  }

  return (
    <main className="login-shell">
      <section className="login-panel">
        <div>
          <p className="eyebrow">Wildlife Cam</p>
          <h1>罠カメラ動画管理</h1>
        </div>
        <form onSubmit={handleSubmit} className="login-form">
          <label>
            メールアドレス
            <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required />
          </label>
          <label>
            パスワード
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required />
          </label>
          {error && <p className="error">{error}</p>}
          <button type="submit" disabled={submitting}>{submitting ? "ログイン中..." : "ログイン"}</button>
        </form>
      </section>
    </main>
  );
}

function VideoDashboard({ session }: { session: Session }) {
  const [videos, setVideos] = useState<Video[]>([]);
  const [traps, setTraps] = useState<Trap[]>([]);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [selectedVideo, setSelectedVideo] = useState<Video | null>(null);
  const [playUrl, setPlayUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingTraps, setLoadingTraps] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updatingTrapId, setUpdatingTrapId] = useState<string | null>(null);
  const videosLoaded = useRef(false);
  const trapsLoaded = useRef(false);
  const videosRequestInFlight = useRef(false);
  const trapsRequestInFlight = useRef(false);

  const formattedCount = useMemo(() => new Intl.NumberFormat("ja-JP").format(videos.length), [videos.length]);
  const latestVideoByTrap = useMemo(() => {
    const latest = new Map<string, Video>();
    for (const video of videos) {
      const current = latest.get(video.trap_id);
      if (!current || new Date(video.captured_at).getTime() > new Date(current.captured_at).getTime()) {
        latest.set(video.trap_id, video);
      }
    }
    return latest;
  }, [videos]);

  async function loadVideos() {
    if (videosRequestInFlight.current) return;
    videosRequestInFlight.current = true;
    try {
      // フィールド投入以降は撮り逃しの確認が目的なので全件出す。
      // (2000 は暴走時の安全弁。5分間隔運用なら約1週間分に相当)
      const { data, error: queryError } = await supabase
        .from("videos")
        .select("id,trap_id,captured_at,status,hunter_note,created_at")
        .gte("captured_at", FIELD_DEPLOY_CUTOFF)
        .order("captured_at", { ascending: false })
        .order("created_at", { ascending: false })
        .limit(2000);

      if (queryError) {
        setError(queryError.message);
        return;
      }
      const incoming = (data ?? []) as Video[];
      setVideos((current) => mergeVideos(current, incoming));
    } finally {
      videosLoaded.current = true;
      videosRequestInFlight.current = false;
      setLoading(false);
    }
  }

  async function loadProfile() {
    const { data, error: profileError } = await supabase
      .from("profiles")
      .select("id,role")
      .eq("id", session.user.id)
      .maybeSingle();

    if (profileError) {
      setError(profileError.message);
      return;
    }

    setProfile((data ?? null) as Profile | null);
  }

  async function loadTraps() {
    if (!apiBaseUrl) {
      setError("VITE_WORKER_API_URL が未設定です。");
      trapsLoaded.current = true;
      setLoadingTraps(false);
      return;
    }

    if (trapsRequestInFlight.current) return;
    trapsRequestInFlight.current = true;
    try {
      const response = await fetch(`${apiBaseUrl}/traps`, {
        headers: { authorization: `Bearer ${session.access_token}` },
      });

      if (!response.ok) {
        setError("監視状態を取得できませんでした。");
        return;
      }

      const data = (await response.json()) as Trap[];
      setTraps((current) => (sameTraps(current, data) ? current : data));
    } catch {
      setError("監視状態を取得できませんでした。");
    } finally {
      trapsLoaded.current = true;
      trapsRequestInFlight.current = false;
      setLoadingTraps(false);
    }
  }

  useEffect(() => {
    void loadDashboard();
    const pollingId = window.setInterval(() => {
      void Promise.all([loadVideos(), loadTraps()]);
    }, 20_000);

    return () => window.clearInterval(pollingId);
  }, [session.access_token, session.user.id]);

  async function loadDashboard() {
    setError(null);
    if (!videosLoaded.current) setLoading(true);
    if (!trapsLoaded.current) setLoadingTraps(true);
    await Promise.all([loadVideos(), loadTraps(), loadProfile()]);
  }

  async function openPlayer(video: Video) {
    if (!apiBaseUrl) {
      setError("VITE_WORKER_API_URL が未設定です。");
      return;
    }

    setSelectedVideo(video);
    setPlayUrl(null);
    setError(null);

    const response = await fetch(`${apiBaseUrl}/play-url/${video.id}`, {
      headers: { authorization: `Bearer ${session.access_token}` },
    });

    if (!response.ok) {
      setError("再生URLを取得できませんでした。");
      setSelectedVideo(null);
      return;
    }

    const body = (await response.json()) as { play_url: string };
    setPlayUrl(body.play_url);
  }

  async function patchTrap(trap: Trap, payload: Record<string, unknown>, failMessage: string): Promise<boolean> {
    if (profile?.role !== "admin") {
      setError("この操作は admin のみ可能です。");
      return false;
    }

    setUpdatingTrapId(trap.trap_id);
    setError(null);

    try {
      const response = await fetch(`${apiBaseUrl}/traps/${encodeURIComponent(trap.trap_id)}`, {
        method: "PATCH",
        headers: {
          authorization: `Bearer ${session.access_token}`,
          "content-type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        setError(failMessage);
        return false;
      }

      const rows = (await response.json()) as Trap[];
      if (rows[0]) {
        setTraps((current) => current.map((row) => (row.trap_id === trap.trap_id ? rows[0] : row)));
      }
      return true;
    } catch {
      setError(failMessage);
      return false;
    } finally {
      setUpdatingTrapId(null);
    }
  }

  async function toggleTrapArmed(trap: Trap) {
    await patchTrap(
      trap,
      { is_armed: !trap.is_armed, name: trap.name },
      "監視状態を更新できませんでした。",
    );
  }

  async function saveTrapConfig(trap: Trap, recordSeconds: number | null, cooldownSeconds: number | null) {
    return patchTrap(
      trap,
      // is_armed / name は現在値を明示的に送り、設定保存が監視状態を変えないことを保証する。
      {
        is_armed: trap.is_armed,
        name: trap.name,
        record_seconds: recordSeconds,
        cooldown_seconds: cooldownSeconds,
      },
      "録画設定を更新できませんでした。",
    );
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Wildlife Cam</p>
          <h1>動画一覧</h1>
        </div>
        <div className="topbar-actions">
          <button className="icon-button" onClick={loadDashboard} title="更新" aria-label="更新">
            <RefreshCw size={18} />
          </button>
          <button className="icon-button" onClick={() => supabase.auth.signOut()} title="ログアウト" aria-label="ログアウト">
            <LogOut size={18} />
          </button>
        </div>
      </header>

      <section className="summary-bar">
        <span>表示件数</span>
        <strong>{formattedCount}</strong>
      </section>

      {error && <p className="error">{error}</p>}

      <section className="trap-panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Trap Control</p>
            <h2>監視状態</h2>
          </div>
          {profile && <span className="role-chip">{profile.role === "admin" ? "admin" : "viewer"}</span>}
        </div>
        {loadingTraps ? (
          <p className="empty-panel">監視状態を読み込み中...</p>
        ) : traps.length === 0 ? (
          <p className="empty-panel">まだ trap が登録されていません。Pi が `/traps/:trap_id` を叩くと自動作成されます。</p>
        ) : (
          <div className="trap-grid">
            {traps.map((trap) => (
              <article key={trap.trap_id} className="trap-card">
                <div>
                  <p className="trap-id mono">{trap.trap_id}</p>
                  <div className="trap-meta-list">
                    <p className="trap-meta">
                      最終イベント: {latestVideoByTrap.get(trap.trap_id) ? formatDateTime(latestVideoByTrap.get(trap.trap_id)!.captured_at) : "記録なし"}
                    </p>
                    <p className="trap-meta">
                      最終アップロード: {latestVideoByTrap.get(trap.trap_id) ? formatDateTime(latestVideoByTrap.get(trap.trap_id)!.created_at) : "記録なし"}
                    </p>
                    <p className="trap-meta">
                      デバイス最終確認: {trap.last_seen_at ? formatDateTime(trap.last_seen_at) : "未確認"}
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  className={`armed-toggle ${trap.is_armed ? "armed" : "disarmed"}`}
                  onClick={() => toggleTrapArmed(trap)}
                  disabled={profile?.role !== "admin" || updatingTrapId === trap.trap_id}
                >
                  <span>{trap.is_armed ? "監視中" : "停止中"}</span>
                </button>
                <TrapConfigForm
                  trap={trap}
                  canEdit={profile?.role === "admin"}
                  saving={updatingTrapId === trap.trap_id}
                  onSave={saveTrapConfig}
                />
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>罠ID</th>
              <th>撮影日時</th>
              <th>ステータス</th>
              <th>メモ</th>
              <th className="action-cell">再生</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={5} className="empty">読み込み中...</td></tr>
            ) : videos.length === 0 ? (
              <tr><td colSpan={5} className="empty">動画はまだ登録されていません。</td></tr>
            ) : (
              videos.map((video) => (
                <tr key={video.id}>
                  <td className="mono">{video.trap_id}</td>
                  <td>{formatDateTime(video.captured_at)}</td>
                  <td><StatusBadge status={video.status} /></td>
                  <td>{video.hunter_note || ""}</td>
                  <td className="action-cell">
                    <button className="play-button" onClick={() => openPlayer(video)} title="再生" aria-label="再生">
                      <Play size={17} />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>

      {selectedVideo && (
        <div className="modal-backdrop" onClick={() => setSelectedVideo(null)}>
          <section className="player-modal" onClick={(event) => event.stopPropagation()}>
            <header>
              <div>
                <p className="eyebrow">{selectedVideo.trap_id}</p>
                <h2>{formatDateTime(selectedVideo.captured_at)}</h2>
              </div>
              <button onClick={() => setSelectedVideo(null)}>閉じる</button>
            </header>
            {playUrl ? <video src={playUrl} controls autoPlay /> : <div className="video-loading">再生準備中...</div>}
          </section>
        </div>
      )}
    </main>
  );
}

function TrapConfigForm({
  trap,
  canEdit,
  saving,
  onSave,
}: {
  trap: Trap;
  canEdit: boolean;
  saving: boolean;
  onSave: (trap: Trap, recordSeconds: number | null, cooldownSeconds: number | null) => Promise<boolean>;
}) {
  const [recordText, setRecordText] = useState(trap.record_seconds?.toString() ?? "");
  const [cooldownText, setCooldownText] = useState(trap.cooldown_seconds?.toString() ?? "");
  const [localError, setLocalError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  // ポーリングでサーバ値が変わったら入力欄も追従させる (編集途中は上書きしない)。
  const dirty =
    recordText !== (trap.record_seconds?.toString() ?? "") ||
    cooldownText !== (trap.cooldown_seconds?.toString() ?? "");
  useEffect(() => {
    if (!dirty) {
      setRecordText(trap.record_seconds?.toString() ?? "");
      setCooldownText(trap.cooldown_seconds?.toString() ?? "");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trap.record_seconds, trap.cooldown_seconds]);

  function parseField(text: string, min: number, max: number, label: string): number | null | "error" {
    const trimmed = text.trim();
    if (trimmed === "") return null; // 空欄 = デバイス既定に戻す
    const num = Number(trimmed);
    if (!Number.isFinite(num) || Math.round(num) !== num || num < min || num > max) {
      setLocalError(`${label}は ${min}〜${max} の整数で入力してください。`);
      return "error";
    }
    return num;
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setLocalError(null);
    const record = parseField(recordText, 1, 120, "録画時間(秒)");
    if (record === "error") return;
    const cooldown = parseField(cooldownText, 0, 86400, "撮影間隔(秒)");
    if (cooldown === "error") return;
    const ok = await onSave(trap, record, cooldown);
    if (ok) {
      setSavedAt(Date.now());
      window.setTimeout(() => setSavedAt(null), 4000);
    }
  }

  return (
    <form className="trap-config" onSubmit={handleSubmit}>
      <div className="trap-config-fields">
        <label>
          録画時間(秒)
          <input
            type="number"
            inputMode="numeric"
            min={1}
            max={120}
            placeholder="既定 10"
            value={recordText}
            onChange={(event) => setRecordText(event.target.value)}
            disabled={!canEdit || saving}
          />
        </label>
        <label>
          撮影間隔(秒)
          <input
            type="number"
            inputMode="numeric"
            min={0}
            max={86400}
            placeholder="既定 0"
            value={cooldownText}
            onChange={(event) => setCooldownText(event.target.value)}
            disabled={!canEdit || saving}
          />
        </label>
      </div>
      <p className="trap-config-hint">300秒=5分間隔。空欄はデバイス既定に戻します。反映まで最大約20秒。</p>
      {localError && <p className="error">{localError}</p>}
      <button type="submit" disabled={!canEdit || saving || !dirty}>
        {saving ? "保存中..." : savedAt ? "保存しました" : "設定を保存"}
      </button>
    </form>
  );
}

function StatusBadge({ status }: { status: Video["status"] }) {
  return <span className={`status status-${status}`}>{statusLabel(status)}</span>;
}

function statusLabel(status: Video["status"]): string {
  const labels = {
    uploaded: "アップロード済み",
    reviewed: "確認済み",
    false_trigger: "誤検知",
    needs_action: "要対応",
  };
  return labels[status];
}

function mergeVideos(current: Video[], incoming: Video[]): Video[] {
  const merged = new Map(current.map((video) => [video.id, video]));
  for (const video of incoming) merged.set(video.id, video);

  const next = [...merged.values()]
    .sort((left, right) => {
      const capturedDifference = new Date(right.captured_at).getTime() - new Date(left.captured_at).getTime();
      return capturedDifference || new Date(right.created_at).getTime() - new Date(left.created_at).getTime();
    })
    .slice(0, 2000);

  if (next.length === current.length && next.every((video, index) => sameVideo(video, current[index]))) {
    return current;
  }
  return next;
}

function sameVideo(left: Video, right: Video): boolean {
  return left.id === right.id
    && left.trap_id === right.trap_id
    && left.captured_at === right.captured_at
    && left.status === right.status
    && left.hunter_note === right.hunter_note
    && left.created_at === right.created_at;
}

function sameTraps(current: Trap[], incoming: Trap[]): boolean {
  return current.length === incoming.length && current.every((trap, index) => {
    const next = incoming[index];
    return next !== undefined
      && trap.trap_id === next.trap_id
      && trap.name === next.name
      && trap.is_armed === next.is_armed
      && trap.last_seen_at === next.last_seen_at
      && trap.updated_at === next.updated_at
      && trap.created_at === next.created_at
      && trap.record_seconds === next.record_seconds
      && trap.cooldown_seconds === next.cooldown_seconds;
  });
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("ja-JP", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

createRoot(document.getElementById("root")!).render(<App />);
