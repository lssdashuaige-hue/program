create extension if not exists pgcrypto;

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  memory_enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text,
  status text not null default 'active' check (status in ('active', 'archived')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null check (role in ('user', 'assistant', 'system')),
  content text not null,
  created_at timestamptz not null default now()
);

create table public.memories (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  source_message_id uuid references public.messages(id) on delete set null,
  kind text not null check (kind in ('experience', 'reflection', 'pattern', 'need')),
  content text not null,
  confidence text not null default 'low' check (confidence in ('low', 'medium', 'high')),
  confirmed boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.themes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text not null,
  status text not null default 'exploring'
    check (status in ('exploring', 'integrating', 'completed', 'paused')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index conversations_user_created_idx on public.conversations (user_id, created_at desc);
create index messages_conversation_created_idx on public.messages (conversation_id, created_at);
create index messages_user_created_idx on public.messages (user_id, created_at desc);
create index memories_user_kind_idx on public.memories (user_id, kind);
create index memories_source_message_idx on public.memories (source_message_id);
create index themes_user_status_idx on public.themes (user_id, status);

revoke all on table public.profiles from anon;
revoke all on table public.conversations from anon;
revoke all on table public.messages from anon;
revoke all on table public.memories from anon;
revoke all on table public.themes from anon;
revoke all on table public.profiles from authenticated;
revoke all on table public.conversations from authenticated;
revoke all on table public.messages from authenticated;
revoke all on table public.memories from authenticated;
revoke all on table public.themes from authenticated;

grant usage on schema public to authenticated;
grant select, insert, update, delete on table public.profiles to authenticated;
grant select, insert, update, delete on table public.conversations to authenticated;
grant select, insert on table public.messages to authenticated;
grant select, insert, update, delete on table public.memories to authenticated;
grant select, insert, update, delete on table public.themes to authenticated;

alter table public.profiles enable row level security;
alter table public.conversations enable row level security;
alter table public.messages enable row level security;
alter table public.memories enable row level security;
alter table public.themes enable row level security;

create policy "profiles_select_own" on public.profiles for select to authenticated
  using ((select auth.uid()) = id);
create policy "profiles_insert_own" on public.profiles for insert to authenticated
  with check ((select auth.uid()) = id);
create policy "profiles_update_own" on public.profiles for update to authenticated
  using ((select auth.uid()) = id) with check ((select auth.uid()) = id);
create policy "profiles_delete_own" on public.profiles for delete to authenticated
  using ((select auth.uid()) = id);

create policy "conversations_own_all" on public.conversations for all to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

create policy "messages_select_own" on public.messages for select to authenticated
  using ((select auth.uid()) = user_id);

create policy "messages_insert_own_user_role" on public.messages for insert to authenticated
  with check (
    (select auth.uid()) = user_id
    and role = 'user'
    and exists (
      select 1 from public.conversations c
      where c.id = conversation_id and c.user_id = (select auth.uid())
    )
  );

create policy "memories_select_own" on public.memories for select to authenticated
  using ((select auth.uid()) = user_id);
create policy "memories_insert_own" on public.memories for insert to authenticated
  with check (
    (select auth.uid()) = user_id
    and (
      source_message_id is null
      or exists (
        select 1 from public.messages m
        where m.id = source_message_id and m.user_id = (select auth.uid())
      )
    )
  );
create policy "memories_update_own" on public.memories for update to authenticated
  using ((select auth.uid()) = user_id)
  with check (
    (select auth.uid()) = user_id
    and (
      source_message_id is null
      or exists (
        select 1 from public.messages m
        where m.id = source_message_id and m.user_id = (select auth.uid())
      )
    )
  );
create policy "memories_delete_own" on public.memories for delete to authenticated
  using ((select auth.uid()) = user_id);

create policy "themes_own_all" on public.themes for all to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
