create extension if not exists pgcrypto;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null,
  role text not null default 'viewer' check (role in ('admin', 'viewer')),
  created_at timestamptz not null default now()
);

create table if not exists public.videos (
  id uuid primary key default gen_random_uuid(),
  trap_id text not null,
  captured_at timestamptz not null,
  r2_key text not null unique,
  status text not null default 'uploaded' check (status in ('uploaded', 'reviewed', 'false_trigger', 'needs_action')),
  hunter_note text,
  species text,
  confidence numeric check (confidence is null or (confidence >= 0 and confidence <= 1)),
  animal_size text,
  points integer,
  analysis_status text,
  analyzed_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists public.traps (
  trap_id text primary key,
  name text,
  is_armed boolean not null default true,
  last_seen_at timestamptz,
  updated_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create index if not exists videos_captured_at_idx on public.videos (captured_at desc);
create index if not exists videos_trap_id_idx on public.videos (trap_id);
create index if not exists videos_status_idx on public.videos (status);
create index if not exists traps_is_armed_idx on public.traps (is_armed);

alter table public.profiles enable row level security;
alter table public.videos enable row level security;
alter table public.traps enable row level security;

create or replace function public.is_admin()
returns boolean
language sql
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.profiles
    where id = auth.uid()
      and role = 'admin'
  );
$$;

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email, role)
  values (new.id, coalesce(new.email, ''), 'viewer')
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
after insert on auth.users
for each row execute procedure public.handle_new_user();

drop policy if exists "profiles_select_own" on public.profiles;
create policy "profiles_select_own"
on public.profiles for select
to authenticated
using (id = auth.uid() or public.is_admin());

drop policy if exists "profiles_update_admin" on public.profiles;
create policy "profiles_update_admin"
on public.profiles for update
to authenticated
using (public.is_admin())
with check (public.is_admin());

drop policy if exists "videos_select_authenticated_profiles" on public.videos;
create policy "videos_select_authenticated_profiles"
on public.videos for select
to authenticated
using (
  exists (
    select 1
    from public.profiles
    where id = auth.uid()
  )
);

drop policy if exists "videos_update_admin" on public.videos;
create policy "videos_update_admin"
on public.videos for update
to authenticated
using (public.is_admin())
with check (public.is_admin());

drop policy if exists "traps_select_authenticated_profiles" on public.traps;
create policy "traps_select_authenticated_profiles"
on public.traps for select
to authenticated
using (
  exists (
    select 1
    from public.profiles
    where id = auth.uid()
  )
);

drop policy if exists "traps_insert_admin" on public.traps;
create policy "traps_insert_admin"
on public.traps for insert
to authenticated
with check (public.is_admin());

drop policy if exists "traps_update_admin" on public.traps;
create policy "traps_update_admin"
on public.traps for update
to authenticated
using (public.is_admin())
with check (public.is_admin());

-- Initial admin promotion after creating your first Supabase Auth user:
-- update public.profiles set role = 'admin' where email = 'you@example.com';
