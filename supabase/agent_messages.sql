-- エージェントチャット (読み取り専用窓口) 用テーブル
-- 適用方法: Supabase ダッシュボード > SQL Editor に貼り付けて Run
--
-- 設計:
--   - Web (認証済みユーザー) は「質問の投稿」と「全メッセージの閲覧」のみ可能 (RLS)
--   - エージェントの返信と状態遷移は Worker (service role) だけが行う
--   - 操作系のエンドポイントはそもそも存在しない (Web=状態確認専用の設計判断)

create table if not exists public.agent_messages (
  id uuid primary key default gen_random_uuid(),
  trap_id text not null,
  role text not null check (role in ('user', 'agent')),
  author_id uuid references auth.users(id) on delete set null,
  author_email text,
  -- user質問は2000字(RLSで強制)・agent返信は4000字までを許容
  content text not null check (char_length(content) between 1 and 4000),
  -- user メッセージ: pending(未回答) -> answered / agent メッセージ: 常に answered
  status text not null default 'pending' check (status in ('pending', 'answered')),
  reply_to uuid references public.agent_messages(id) on delete set null,
  created_at timestamptz not null default now()
);

create index if not exists agent_messages_trap_created_idx
  on public.agent_messages (trap_id, created_at desc);
create index if not exists agent_messages_pending_idx
  on public.agent_messages (trap_id, status) where (role = 'user' and status = 'pending');

alter table public.agent_messages enable row level security;

-- 認証済みユーザー (admin/viewer とも) は全メッセージを閲覧できる
drop policy if exists "agent_messages_select_authenticated" on public.agent_messages;
create policy "agent_messages_select_authenticated"
  on public.agent_messages for select
  to authenticated
  using (true);

-- 認証済みユーザーは「自分名義の user メッセージ」だけ投稿できる
-- (agent 役の挿入・status/reply_to の操作は service role = Worker 専用)
-- author_email は JWT のメールに固定 (なりすまし・プロンプト注入の迂回路を塞ぐ)
-- 未回答の持ち込みは1人3件まで (LLM呼び出しコストの増幅を抑える)
drop policy if exists "agent_messages_insert_own_question" on public.agent_messages;
create policy "agent_messages_insert_own_question"
  on public.agent_messages for insert
  to authenticated
  with check (
    role = 'user'
    and status = 'pending'
    and reply_to is null
    and author_id = auth.uid()
    and author_email = (auth.jwt() ->> 'email')
    and char_length(content) <= 2000
    and (
      select count(*) from public.agent_messages m
      where m.author_id = auth.uid() and m.role = 'user' and m.status = 'pending'
    ) < 3
  );

-- update/delete のポリシーは意図的に作らない (authenticated からは不可)
