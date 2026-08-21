alter table public.messages
  add column if not exists review_contract_version text,
  add column if not exists verification_contract_version text,
  add column if not exists bounded_response_kind text;

-- Durable client turns written before the dual-gate contract had only the
-- original Review gate. Preserve them for history without claiming that they
-- passed the current Review v2 + Final Verification v2 release contract.
update public.messages
set
  review_contract_version = 'legacy',
  verification_contract_version = 'legacy',
  bounded_response_kind = null
where role = 'assistant'
  and client_turn_id is not null
  and response_source = 'review'
  and support_mode = 'reflection'
  and risk_level = 'none'
  and review_contract_version is null
  and verification_contract_version is null;

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
          and review_contract_version is null
          and verification_contract_version is null
          and bounded_response_kind is null
        )
        or (
          client_turn_id is not null
          and response_source is not distinct from 'review'
          and support_mode is not distinct from 'reflection'
          and risk_level is not distinct from 'none'
          and (
            (
              review_contract_version is not distinct from 'legacy'
              and verification_contract_version is not distinct from 'legacy'
              and bounded_response_kind is null
            )
            or (
              review_contract_version is not distinct from '2'
              and verification_contract_version is not distinct from '1'
              and (
                bounded_response_kind is null
                or bounded_response_kind in (
                  'third_party_private_state',
                  'single_chat_diagnostic_request',
                  'personal_lifespan_conversion'
                )
              )
            )
            or (
              review_contract_version is not distinct from '2'
              and verification_contract_version is not distinct from '2'
              and (
                bounded_response_kind is null
                or bounded_response_kind in (
                  'third_party_private_state',
                  'single_chat_diagnostic_request',
                  'personal_lifespan_conversion',
                  'unavailable_cross_chat_context'
                )
              )
            )
          )
        )
      )
    )
    or (
      role = 'user'
      and response_source is null
      and support_mode is null
      and risk_level is null
      and review_contract_version is null
      and verification_contract_version is null
      and bounded_response_kind is null
    )
    or (
      role = 'system'
      and client_turn_id is null
      and response_source is null
      and support_mode is null
      and risk_level is null
      and review_contract_version is null
      and verification_contract_version is null
      and bounded_response_kind is null
    )
  );

-- Keep public history readable through the user's RLS-scoped token without
-- exposing the internal release-contract provenance columns through PostgREST.
-- A table-level SELECT privilege also covers columns added later, so replace it
-- with an explicit public projection only after the new constraint is in place.
-- Server-side persistence retains the table-level privileges required for
-- provenance validation and durable writes.
revoke select on table public.messages from anon, authenticated;

-- Also remove any unexpected column-level grants left by schema drift. Column
-- revokes do not override a table grant, which is why the table revoke comes
-- first.
revoke select (
  review_contract_version,
  verification_contract_version,
  bounded_response_kind
) on table public.messages from anon, authenticated;

grant select (
  id,
  conversation_id,
  client_turn_id,
  role,
  content,
  response_source,
  support_mode,
  risk_level,
  created_at
) on table public.messages to authenticated;

grant select, insert on table public.messages to service_role;
