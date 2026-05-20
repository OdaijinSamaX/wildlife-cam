import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { LogOut, Play, RefreshCw } from "lucide-react";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "./supabase";
import type { Profile, Trap, Video } from "./types";
import "./styles.css";

const apiBaseUrl = import.meta.env.VITE_WORKER_API_URL as string | undefined;

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

  const formattedCount = useMemo(() => new Intl.NumberFormat("ja-JP").format(videos.length), [videos.length]);

  async function loadVideos() {
    setLoading(true);
    setError(null);
    const { data, error: queryError } = await supabase
      .from("videos")
      .select("id,trap_id,captured_at,status,hunter_note,created_at")
      .order("captured_at", { ascending: false })
      .order("created_at", { ascending: false })
      .limit(100);

    setLoading(false);
    if (queryError) {
      setError(queryError.message);
      return;
    }
    setVideos((data ?? []) as Video[]);
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
      return;
    }

    setLoadingTraps(true);
    const response = await fetch(`${apiBaseUrl}/traps`, {
      headers: { authorization: `Bearer ${session.access_token}` },
    });
    setLoadingTraps(false);

    if (!response.ok) {
      setError("監視状態を取得できませんでした。");
      return;
    }

    const data = (await response.json()) as Trap[];
    setTraps(data);
  }

  useEffect(() => {
    void loadDashboard();
  }, []);

  async function loadDashboard() {
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

  async function toggleTrapArmed(trap: Trap) {
    if (profile?.role !== "admin") {
      setError("監視の切り替えは admin のみ可能です。");
      return;
    }

    setUpdatingTrapId(trap.trap_id);
    setError(null);

    const nextIsArmed = !trap.is_armed;
    const response = await fetch(`${apiBaseUrl}/traps/${encodeURIComponent(trap.trap_id)}`, {
      method: "PATCH",
      headers: {
        authorization: `Bearer ${session.access_token}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        is_armed: nextIsArmed,
        name: trap.name,
      }),
    });
    setUpdatingTrapId(null);

    if (!response.ok) {
      setError("監視状態を更新できませんでした。");
      return;
    }

    const rows = (await response.json()) as Trap[];
    if (rows[0]) {
      setTraps((current) => current.map((row) => (row.trap_id === trap.trap_id ? rows[0] : row)));
    }
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
                  <p className="trap-meta">
                    最終疎通: {trap.last_seen_at ? formatDateTime(trap.last_seen_at) : "未確認"}
                  </p>
                </div>
                <button
                  type="button"
                  className={`armed-toggle ${trap.is_armed ? "armed" : "disarmed"}`}
                  onClick={() => toggleTrapArmed(trap)}
                  disabled={profile?.role !== "admin" || updatingTrapId === trap.trap_id}
                >
                  <span>{trap.is_armed ? "監視中" : "停止中"}</span>
                </button>
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

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("ja-JP", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

createRoot(document.getElementById("root")!).render(<App />);
