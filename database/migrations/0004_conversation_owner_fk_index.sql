create index if not exists messages_conversation_user_created_idx
  on public.messages (conversation_id, user_id, created_at);
