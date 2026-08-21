-- Read-only hosted preflight for migrations 0006 and 0007.
-- Run only after a separate read-only Supabase authorization. This script
-- returns metadata and aggregate counts; it performs no writes.

select version, name
from supabase_migrations.schema_migrations
order by version;

select table_name, column_name, data_type, is_nullable, column_default
from information_schema.columns
where table_schema = 'public'
  and table_name in ('profiles', 'messages', 'memories')
  and column_name in (
    'review_contract_version', 'verification_contract_version',
    'bounded_response_kind', 'memory_enabled_at', 'lineage_id',
    'supersedes_id', 'original_content', 'status', 'version',
    'version_origin', 'confirmed_at', 'paused_at', 'superseded_at'
  )
order by table_name, ordinal_position;

select
  relname as table_name,
  n_live_tup::bigint as estimated_rows,
  pg_total_relation_size(relid) as total_bytes
from pg_stat_user_tables
where schemaname = 'public'
  and relname in ('profiles', 'conversations', 'messages', 'memories', 'themes')
order by relname;

select
  count(*)::bigint as memories_total,
  count(*) filter (where memory.confirmed is distinct from true)::bigint
    as unconfirmed,
  count(*) filter (
    where char_length(memory.content) not between 1 and 8000
  )::bigint as invalid_length,
  count(*) filter (where memory.source_message_id is null)::bigint
    as missing_source,
  count(*) filter (
    where memory.source_message_id is not null and source.id is null
  )::bigint as dangling_source,
  count(*) filter (
    where source.id is not null
      and source.user_id is distinct from memory.user_id
  )::bigint as cross_user_source,
  count(*) filter (
    where source.id is not null and source.role is distinct from 'user'
  )::bigint as non_user_source,
  count(*) filter (
    where source.id is not null
      and source.content is distinct from memory.content
  )::bigint as non_exact_source
from public.memories memory
left join public.messages source on source.id = memory.source_message_id;

-- Every blocker count above except memories_total must be zero before 0007.
select
  count(*) filter (where memory_enabled = true)::bigint
    as profiles_that_will_be_opted_out,
  count(*)::bigint as profiles_total
from public.profiles;

select
  count(*) filter (
    where role = 'assistant'
      and client_turn_id is not null
      and response_source = 'review'
      and support_mode = 'reflection'
      and risk_level = 'none'
  )::bigint as durable_assistants_to_mark_legacy,
  count(*)::bigint as messages_total
from public.messages;

select
  c.relname,
  c.relrowsecurity,
  c.relforcerowsecurity
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relname in ('profiles', 'conversations', 'messages', 'memories', 'themes')
order by c.relname;

select table_name, grantee, privilege_type
from information_schema.role_table_grants
where table_schema = 'public'
  and table_name in ('profiles', 'conversations', 'messages', 'memories', 'themes')
  and grantee in ('anon', 'authenticated', 'service_role')
order by grantee, table_name, privilege_type;

select
  count(*) filter (
    where state <> 'idle'
      and xact_start is not null
      and pg_catalog.now() - xact_start > interval '60 seconds'
  )::bigint as active_transactions_over_60_seconds,
  count(*) filter (where wait_event_type = 'Lock')::bigint
    as sessions_waiting_on_locks
from pg_stat_activity
where datname = current_database();

select mode, granted, count(*)::bigint as lock_count
from pg_locks
where relation in (
  'public.profiles'::regclass,
  'public.messages'::regclass,
  'public.memories'::regclass
)
group by mode, granted
order by granted, mode;

select
  current_setting('lock_timeout') as lock_timeout,
  current_setting('statement_timeout') as statement_timeout;
