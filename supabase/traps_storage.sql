-- 罠カードにSD使用率を表示するための列追加
-- 適用方法: Supabase ダッシュボード > SQL Editor に貼り付けて Run
alter table public.traps add column if not exists storage_pct integer
  check (storage_pct is null or (storage_pct >= 0 and storage_pct <= 100));
