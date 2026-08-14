do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'conversations_id_user_id_key'
      and conrelid = 'public.conversations'::regclass
  ) then
    alter table public.conversations
      add constraint conversations_id_user_id_key unique (id, user_id);
  end if;
end;
$$;

alter table public.messages
  add column if not exists client_turn_id uuid,
  add column if not exists response_source text,
  add column if not exists support_mode text,
  add column if not exists risk_level text;

alter table public.messages
  drop constraint if exists messages_conversation_id_fkey;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'messages_conversation_owner_fkey'
      and conrelid = 'public.messages'::regclass
  ) then
    alter table public.messages
      add constraint messages_conversation_owner_fkey
      foreign key (conversation_id, user_id)
      references public.conversations (id, user_id)
      on delete cascade;
  end if;
end;
$$;

alter table public.messages
  drop constraint if exists messages_reviewed_history_shape_check;

alter table public.messages
  add constraint messages_reviewed_history_shape_check
  check (
    (
      role = 'assistant'
      and (
        (
          client_turn_id is null
          and response_source is null
          and support_mode is null
          and risk_level is null
        )
        or (
          client_turn_id is not null
          and response_source = 'review'
          and support_mode = 'reflection'
          and risk_level = 'none'
        )
      )
    )
    or (
      role = 'user'
      and response_source is null
      and support_mode is null
      and risk_level is null
    )
    or (
      role = 'system'
      and client_turn_id is null
      and response_source is null
      and support_mode is null
      and risk_level is null
    )
  );

create unique index if not exists messages_user_turn_role_key
on public.messages (user_id, client_turn_id, role)
where client_turn_id is not null;

create index if not exists conversations_user_updated_idx
on public.conversations (user_id, updated_at desc, id desc);

alter table public.messages
  drop constraint if exists messages_content_length_check;

alter table public.messages
  add constraint messages_content_length_check
  check (char_length(content) between 1 and 20000);

alter table public.conversations
  drop constraint if exists conversations_title_length_check;

alter table public.conversations
  add constraint conversations_title_length_check
  check (title is null or char_length(title) between 1 and 120);

grant select, insert, update, delete on table public.conversations to service_role;
grant select, insert on table public.messages to service_role;

create or replace function public.touch_conversation_after_message_insert()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  update public.conversations
  set updated_at = now()
  where id = new.conversation_id
    and user_id = new.user_id;
  return new;
end;
$$;

revoke all on function public.touch_conversation_after_message_insert() from public;
revoke all on function public.touch_conversation_after_message_insert() from anon;
revoke all on function public.touch_conversation_after_message_insert() from authenticated;

drop trigger if exists messages_touch_conversation_after_insert
on public.messages;

create trigger messages_touch_conversation_after_insert
after insert on public.messages
for each row
execute function public.touch_conversation_after_message_insert();
