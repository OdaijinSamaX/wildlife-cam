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
};
