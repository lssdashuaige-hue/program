revoke insert on table public.messages from authenticated;
revoke insert on table public.messages from anon;

drop policy if exists messages_insert_own_user_role
on public.messages;
