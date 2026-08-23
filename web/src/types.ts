export type Video = {
  id: string;
  trap_id: string;
  captured_at: string;
  status: "uploaded" | "reviewed" | "false_trigger" | "needs_action";
  hunter_note: string | null;
  created_at: string;
};

export type Profile = {
  id: string;
  role: "admin" | "viewer";
};

export type Trap = {
  trap_id: string;
  name: string | null;
  is_armed: boolean;
  last_seen_at: string | null;
  updated_at: string;
  created_at: string;
  // 録画設定 (Worker が R2 の trap-config から合成して返す)。null = デバイス既定。
  record_seconds: number | null;
  cooldown_seconds: number | null;
  motion_sustain_seconds: number | null;
  // デバイス申告のSD使用率% (arm ポーリング同乗)。80%で回収要請の目安
  storage_pct?: number | null;
};

export type AgentMessage = {
  id: string;
  trap_id: string;
  role: "user" | "agent";
  author_email: string | null;
  content: string;
  status: "pending" | "answered";
  reply_to: string | null;
  created_at: string;
};
