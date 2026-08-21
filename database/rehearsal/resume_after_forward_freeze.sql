-- Resume the exact PAS-027 authenticated privileges after a safe forward
-- freeze. Profiles remain opted out; each owner must explicitly call
-- set_memory_enabled(true) again before a new source-quote memory can be saved.
begin;

revoke insert, update, delete on table public.memories
from authenticated;

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

grant execute on function public.set_memory_enabled(boolean)
to authenticated;
grant execute on function public.is_exact_owned_user_message(uuid, text)
to authenticated;
grant execute on function public.revise_memory(uuid, integer, text)
to authenticated;
grant execute on function public.delete_memory_lineage(uuid)
to authenticated;

commit;
