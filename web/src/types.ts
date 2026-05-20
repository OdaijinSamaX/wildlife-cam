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
};
