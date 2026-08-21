-- Read-only postflight for migrations 0006 and 0007.
-- Run before application writes are re-enabled. No content is returned.

select version, name
from supabase_migrations.schema_migrations
where name in ('dual_gate_message_provenance', 'user_data_control')
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

select conname, convalidated, pg_get_constraintdef(oid, true) as definition
from pg_constraint
where conrelid in ('public.messages'::regclass, 'public.memories'::regclass)
  and conname in (
    'messages_reviewed_history_shape_check',
    'memories_id_user_id_key',
    'memories_lineage_fk',
    'memories_supersedes_fk',
    'memories_lineage_version_key',
    'memories_data_control_shape_check'
  )
order by conname;

select
  count(*) filter (
    where role = 'assistant'
      and client_turn_id is not null
      and review_contract_version = 'legacy'
      and verification_contract_version = 'legacy'
      and bounded_response_kind is null
  )::bigint as legacy_durable_assistants,
  count(*) filter (
    where role in ('user', 'system')
      and (
        review_contract_version is not null
        or verification_contract_version is not null
        or bounded_response_kind is not null
      )
  )::bigint as invalid_nonassistant_provenance,
  count(*) filter (
    where bounded_response_kind is not null
      and bounded_response_kind not in (
        'third_party_private_state',
        'single_chat_diagnostic_request',
        'personal_lifespan_conversion',
        'unavailable_cross_chat_context'
      )
  )::bigint as invalid_bounded_kind
from public.messages;

select
  count(*) filter (where memory_enabled = true)::bigint
    as profiles_still_opted_in,
  count(*)::bigint as profiles_total
from public.profiles;

select
  count(*) filter (
    where memory.confirmed is distinct from true
       or memory.lineage_id is null
       or memory.original_content is null
       or memory.status not in ('active', 'paused', 'superseded')
       or memory.version < 1
       or memory.version_origin not in ('source_quote', 'user_revision')
  )::bigint as invalid_memory_shape,
  count(*) filter (
    where memory.version_origin = 'source_quote'
      and (
        source.id is null
        or source.user_id is distinct from memory.user_id
        or source.role is distinct from 'user'
        or source.content is distinct from memory.content
      )
  )::bigint as invalid_source_quote
from public.memories memory
left join public.messages source on source.id = memory.source_message_id;

select count(*)::bigint as cross_user_lineage_edges
from (
  select memory.id
  from public.memories memory
  join public.memories root on root.id = memory.lineage_id
  where memory.user_id is distinct from root.user_id
  union all
  select memory.id
  from public.memories memory
  join public.memories parent on parent.id = memory.supersedes_id
  where memory.user_id is distinct from parent.user_id
) invalid_edges;

select
  has_table_privilege('authenticated', 'public.messages', 'select')
    as authenticated_message_table_select_must_be_false,
  has_column_privilege('authenticated', 'public.messages', 'content', 'select')
    as authenticated_public_message_content_must_be_true,
  has_column_privilege(
    'authenticated', 'public.messages', 'review_contract_version', 'select'
  ) as authenticated_internal_review_must_be_false,
  has_table_privilege('anon', 'public.memories', 'select')
    as anon_memory_select_must_be_false,
  has_table_privilege('authenticated', 'public.memories', 'delete')
    as authenticated_direct_memory_delete_must_be_false;

select
  p.oid::regprocedure as function_name,
  p.prosecdef,
  p.proconfig,
  has_function_privilege('authenticated', p.oid, 'execute')
    as authenticated_execute,
  has_function_privilege('anon', p.oid, 'execute') as anon_execute,
  exists (
    select 1
    from aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) acl
    where acl.grantee = 0 and acl.privilege_type = 'EXECUTE'
  ) as public_execute
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public'
  and p.proname in (
    'set_memory_enabled', 'is_exact_owned_user_message',
    'revise_memory', 'delete_memory_lineage',
    'touch_conversation_after_message_insert'
  )
order by p.oid::regprocedure::text;

select tablename, policyname, cmd, roles
from pg_policies
where schemaname = 'public'
  and tablename in ('profiles', 'conversations', 'messages', 'memories', 'themes')
order by tablename, policyname;
