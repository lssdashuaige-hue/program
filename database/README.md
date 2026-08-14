# Database

The SQL files in `migrations/` are designed for Supabase PostgreSQL.

The initial schema uses `auth.users` as the account source of truth, enables
row-level security on every public table, and limits every authenticated user
to rows they own.

The initial migration is applied to the `PAS` Supabase project
(`qhynfdiiicebnjfukwaw`) in Singapore. Keep this file as the reproducible
baseline for new environments.

`0002_confirmed_memory_writes.sql` is also applied. It requires browser-created
memory rows to belong to the authenticated user and to have
`confirmed = true`, matching the explicit confirmation UI.

The hosted project also has the conversation-history migrations applied:

- `0003_conversation_history.sql` adds reviewed-turn provenance, idempotent
  client turn IDs, and the composite conversation-owner foreign key.
- `0004_conversation_owner_fk_index.sql` adds the supporting owner index.
- `0005_backend_only_conversation_writes.sql` removes direct browser message
  inserts, so only the backend can persist a complete reviewed pair.

The hosted migration ledger starts with the confirmed-memory migration even
though the initial schema is present. Do not replay `0001_initial_schema.sql`
against the existing project merely to fill that historical ledger gap.

On 2026-08-14, a live synthetic end-to-end check verified normal reviewed
pair writes, exact idempotent retry, restored second-turn context, browser
insert denial, and cross-user read/update/delete isolation. The temporary
users, conversations, and messages were removed after the check.
