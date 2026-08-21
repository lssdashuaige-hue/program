begin;

-- PAS-027: long-term psychological memory is opt-in. Existing Alpha rows
-- were created under a default-true column, so they are conservatively
-- disabled until the owner explicitly enables memory again.
alter table public.profiles
  alter column memory_enabled set default false;

alter table public.profiles
  add column if not exists memory_enabled_at timestamptz;

update public.profiles
set memory_enabled = false,
    memory_enabled_at = null,
    updated_at = now()
where memory_enabled is distinct from false
   or memory_enabled_at is not null;

-- The enablement timestamp is an audit field, so clients cannot write it
-- directly. The authenticated RPC below derives both the owner and timestamp
-- on the database side. Display-name access remains column-scoped.
revoke insert, update, delete on table public.profiles from authenticated;
grant insert (id, display_name) on table public.profiles to authenticated;
grant update (display_name) on table public.profiles to authenticated;

create or replace function public.set_memory_enabled(p_enabled boolean)
returns table (
  memory_enabled boolean,
  memory_enabled_at timestamptz,
  updated_at timestamptz
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  current_user_id uuid := (select auth.uid());
  changed_at timestamptz := pg_catalog.now();
begin
  if current_user_id is null then
    raise exception 'authentication required' using errcode = '42501';
  end if;

  insert into public.profiles as profile (
    id,
    memory_enabled,
    memory_enabled_at,
    updated_at
  ) values (
    current_user_id,
    p_enabled,
    case when p_enabled then changed_at else null end,
    changed_at
  )
  on conflict (id) do update
  set memory_enabled = excluded.memory_enabled,
      memory_enabled_at = excluded.memory_enabled_at,
      updated_at = excluded.updated_at;

  return query
  select
    profile.memory_enabled,
    profile.memory_enabled_at,
    profile.updated_at
  from public.profiles as profile
  where profile.id = current_user_id;
end;
$$;

revoke all on function public.set_memory_enabled(boolean) from public;
revoke all on function public.set_memory_enabled(boolean) from anon;
grant execute on function public.set_memory_enabled(boolean) to authenticated;

alter table public.memories
  add column if not exists lineage_id uuid,
  add column if not exists supersedes_id uuid,
  add column if not exists original_content text,
  add column if not exists status text,
  add column if not exists version integer,
  add column if not exists version_origin text,
  add column if not exists confirmed_at timestamptz,
  add column if not exists paused_at timestamptz,
  add column if not exists superseded_at timestamptz;

-- Existing rows can only become source-quote version roots when the database
-- can prove that they are confirmed, non-empty, owner-matched copies of a
-- user message. Abort instead of silently upgrading unverified legacy text.
do $$
begin
  if exists (
    select 1
    from public.memories memory
    left join public.messages source
      on source.id = memory.source_message_id
    where memory.confirmed is distinct from true
       or char_length(memory.content) not between 1 and 8000
       or source.id is null
       or source.user_id is distinct from memory.user_id
       or source.role is distinct from 'user'
       or source.content is distinct from memory.content
  ) then
    raise exception 'legacy memories require confirmed, exact owned user-message sources before PAS-027 migration'
      using errcode = '23514';
  end if;
end;
$$;

update public.memories
set lineage_id = coalesce(lineage_id, id),
    original_content = coalesce(original_content, content),
    status = coalesce(status, 'active'),
    version = coalesce(version, 1),
    version_origin = coalesce(version_origin, 'source_quote'),
    confirmed_at = coalesce(confirmed_at, updated_at, created_at)
where lineage_id is null
   or original_content is null
   or status is null
   or version is null
   or version_origin is null
   or confirmed_at is null;

alter table public.memories
  alter column lineage_id set not null,
  alter column original_content set not null,
  alter column status set not null,
  alter column version set not null,
  alter column version_origin set not null,
  alter column confirmed_at set not null;

alter table public.memories
  drop constraint if exists memories_lineage_fk,
  drop constraint if exists memories_supersedes_fk,
  drop constraint if exists memories_id_user_id_key,
  drop constraint if exists memories_data_control_shape_check,
  drop constraint if exists memories_lineage_version_key;

alter table public.memories
  add constraint memories_id_user_id_key unique (id, user_id),
  add constraint memories_lineage_fk
    foreign key (lineage_id, user_id)
    references public.memories(id, user_id) on delete cascade,
  add constraint memories_supersedes_fk
    foreign key (supersedes_id, user_id)
    references public.memories(id, user_id) on delete cascade,
  add constraint memories_lineage_version_key unique (lineage_id, version),
  add constraint memories_data_control_shape_check check (
    char_length(content) between 1 and 8000
    and char_length(original_content) between 1 and 8000
    and status in ('active', 'paused', 'superseded')
    and version >= 1
    and version_origin in ('source_quote', 'user_revision')
    and confirmed = true
    and (
      (
        version = 1
        and version_origin = 'source_quote'
        and lineage_id = id
        and supersedes_id is null
        and content = original_content
      )
      or (
        version > 1
        and version_origin = 'user_revision'
        and lineage_id <> id
        and supersedes_id is not null
      )
    )
    and (status = 'paused') = (paused_at is not null)
    and (status = 'superseded') = (superseded_at is not null)
  );

drop policy if exists "memories_insert_confirmed_own" on public.memories;
drop policy if exists "memories_update_confirmed_own" on public.memories;

-- The messages table intentionally exposes only a public column projection to
-- authenticated clients. Use a narrow owner-bound predicate so the memory
-- policy can verify the private message owner without granting direct access
-- to messages.user_id.
create or replace function public.is_exact_owned_user_message(
  p_message_id uuid,
  p_content text
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select (select auth.uid()) is not null
    and exists (
      select 1
      from public.messages source
      where source.id = p_message_id
        and source.user_id = (select auth.uid())
        and source.role = 'user'
        and source.content = p_content
    )
$$;

revoke all on function public.is_exact_owned_user_message(uuid, text)
from public;
revoke all on function public.is_exact_owned_user_message(uuid, text)
from anon;
grant execute on function public.is_exact_owned_user_message(uuid, text)
to authenticated;

create policy "memories_insert_opted_in_source_quote"
on public.memories
for insert
to authenticated
with check (
  (select auth.uid()) = user_id
  and exists (
    select 1
    from public.profiles p
    where p.id = (select auth.uid())
      and p.memory_enabled = true
  )
  and confirmed = true
  and version = 1
  and version_origin = 'source_quote'
  and lineage_id = id
  and supersedes_id is null
  and status = 'active'
  and paused_at is null
  and superseded_at is null
  and content = original_content
  and public.is_exact_owned_user_message(source_message_id, content)
);

create policy "memories_update_status_own"
on public.memories
for update
to authenticated
using (
  (select auth.uid()) = user_id
  and status in ('active', 'paused')
)
with check (
  (select auth.uid()) = user_id
  and status in ('active', 'paused')
);

revoke insert, update, delete on table public.memories from authenticated;
grant insert (
  id,
  user_id,
  lineage_id,
  source_message_id,
  supersedes_id,
  kind,
  content,
  original_content,
  confidence,
  confirmed,
  status,
  version,
  version_origin,
  confirmed_at,
  paused_at,
  superseded_at,
  created_at,
  updated_at
) on table public.memories to authenticated;
grant update (status, paused_at, updated_at)
on table public.memories to authenticated;

create or replace function public.revise_memory(
  p_memory_id uuid,
  p_expected_version integer,
  p_content text
)
returns setof public.memories
language plpgsql
security definer
set search_path = ''
as $$
declare
  current_row public.memories%rowtype;
  next_id uuid := pg_catalog.gen_random_uuid();
  changed_at timestamptz := pg_catalog.now();
begin
  if (select auth.uid()) is null then
    raise exception 'authentication required' using errcode = '42501';
  end if;
  if p_content is null
     or char_length(btrim(p_content)) = 0
     or char_length(p_content) > 8000 then
    raise exception 'invalid memory revision' using errcode = '23514';
  end if;

  select *
  into current_row
  from public.memories
  where id = p_memory_id
    and user_id = (select auth.uid())
  for update;

  if not found then
    return;
  end if;
  if p_expected_version is null
     or current_row.status = 'superseded'
     or current_row.version is distinct from p_expected_version then
    raise exception 'memory version conflict' using errcode = '40001';
  end if;

  update public.memories
  set status = 'superseded',
      paused_at = null,
      superseded_at = changed_at,
      updated_at = changed_at
  where id = current_row.id
    and user_id = (select auth.uid());

  insert into public.memories (
    id,
    user_id,
    lineage_id,
    source_message_id,
    supersedes_id,
    kind,
    content,
    original_content,
    confidence,
    confirmed,
    status,
    version,
    version_origin,
    confirmed_at,
    paused_at,
    superseded_at,
    created_at,
    updated_at
  ) values (
    next_id,
    current_row.user_id,
    current_row.lineage_id,
    current_row.source_message_id,
    current_row.id,
    current_row.kind,
    p_content,
    current_row.original_content,
    current_row.confidence,
    true,
    case when current_row.status = 'paused' then 'paused' else 'active' end,
    current_row.version + 1,
    'user_revision',
    changed_at,
    case when current_row.status = 'paused' then changed_at else null end,
    null,
    changed_at,
    changed_at
  );

  return query
  select m.*
  from public.memories m
  where m.id = next_id
    and m.user_id = (select auth.uid());
end;
$$;

revoke all on function public.revise_memory(uuid, integer, text) from public;
revoke all on function public.revise_memory(uuid, integer, text) from anon;
grant execute on function public.revise_memory(uuid, integer, text)
to authenticated;

create or replace function public.delete_memory_lineage(p_lineage_id uuid)
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  deleted_count integer;
begin
  if (select auth.uid()) is null then
    raise exception 'authentication required' using errcode = '42501';
  end if;

  delete from public.memories
  where lineage_id = p_lineage_id
    and user_id = (select auth.uid());
  get diagnostics deleted_count = row_count;
  return deleted_count;
end;
$$;

revoke all on function public.delete_memory_lineage(uuid) from public;
revoke all on function public.delete_memory_lineage(uuid) from anon;
grant execute on function public.delete_memory_lineage(uuid) to authenticated;

commit;
