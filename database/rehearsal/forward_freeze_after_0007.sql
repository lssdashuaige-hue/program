-- Safe forward freeze after 0007.
--
-- This is deliberately non-destructive: it preserves the current schema,
-- constraints, policies, and every memory row. It disables all authenticated
-- long-term-memory mutations while keeping RLS-scoped SELECT/export available.
begin;

update public.profiles
set memory_enabled = false,
    memory_enabled_at = null,
    updated_at = pg_catalog.now()
where memory_enabled is distinct from false
   or memory_enabled_at is not null;

revoke execute on function public.set_memory_enabled(boolean)
from authenticated;
revoke execute on function public.is_exact_owned_user_message(uuid, text)
from authenticated;
revoke execute on function public.revise_memory(uuid, integer, text)
from authenticated;
revoke execute on function public.delete_memory_lineage(uuid)
from authenticated;

revoke insert, update, delete on table public.memories
from authenticated;

commit;
