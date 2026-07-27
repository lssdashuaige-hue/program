drop policy if exists "memories_insert_own" on public.memories;
drop policy if exists "memories_update_own" on public.memories;

create policy "memories_insert_confirmed_own"
on public.memories
for insert
to authenticated
with check (
  (select auth.uid()) = user_id
  and confirmed = true
  and (
    source_message_id is null
    or exists (
      select 1
      from public.messages m
      where m.id = source_message_id
        and m.user_id = (select auth.uid())
    )
  )
);

create policy "memories_update_confirmed_own"
on public.memories
for update
to authenticated
using ((select auth.uid()) = user_id)
with check (
  (select auth.uid()) = user_id
  and confirmed = true
  and (
    source_message_id is null
    or exists (
      select 1
      from public.messages m
      where m.id = source_message_id
        and m.user_id = (select auth.uid())
    )
  )
);
