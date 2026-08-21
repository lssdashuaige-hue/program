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

`0006_dual_gate_message_provenance.sql` is the next local migration and has not
been applied to the hosted project by this repository change. It marks existing
durable assistant turns as `legacy`, records Review v2 + Final Verification v2
on new turns, and restricts bounded-response provenance to the four supported
kinds. Apply this migration before deploying backend code that selects the new
columns. Legacy pairs and historical Review v2 / Verifier v1 pairs remain
visible in history, but only `2`/`2` pairs are eligible for model context or
current idempotent replay.

`0007_user_data_control.sql` is also local-only and has not been applied. It
implements the PAS-027 active-database control contract: long-term memory
defaults to off, initial memories must exactly match an owned user message,
edits create an owner-confirmed version instead of overwriting the source,
and pause/delete operations are owner-scoped. Direct content updates and
partial version deletion are revoked; the narrow revision and lineage-delete
functions verify `auth.uid()` and the backend first performs an RLS-scoped
ownership read. This migration must follow `0006` and must not be deployed
until the migration ledger, verified backup, maintenance window, and two-user
PostgREST isolation test are ready.

The isolated rehearsal in `rehearsal/` replays migrations `0001` through
`0007`, validates PostgreSQL permissions and failure atomicity, and exercises
forward freeze plus backup recovery using synthetic data only. Run
`npm run rehearse` from that directory. A passing local rehearsal is evidence
for requesting a read-only hosted preflight, not permission to migrate the
hosted project. The complete gate checklist is in
`docs/pas/PAS-027-DATABASE-MIGRATION-RUNBOOK.md`.

The hosted migration ledger starts with the confirmed-memory migration even
though the initial schema is present. Do not replay `0001_initial_schema.sql`
against the existing project merely to fill that historical ledger gap.

The pinned Supabase CLI deployment view is in `../supabase/migrations/`. It
maps the four existing hosted timestamp versions to `0002`–`0005`, deliberately
omits the untracked `0001` baseline, and assigns frozen timestamp versions to
`0006` and `0007`. Run `npm run verify:supabase-map` from `rehearsal/` to prove
that every deployment file is byte-identical to its canonical source before a
dry-run. Gate C1's official PostgreSQL 17 / CLI 2.111.0 replay passed on
2026-08-21; the hosted dry-run and any migration apply still require separate
authorization.

The current backend and privacy UI select fields introduced by `0006` and
`0007`. Do not deploy them ahead of the database migrations, and do not run old
and new backend versions together after the stricter constraints are active.

On 2026-08-14, a live synthetic end-to-end check verified normal reviewed
pair writes, exact idempotent retry, restored second-turn context, browser
insert denial, and cross-user read/update/delete isolation. The temporary
users, conversations, and messages were removed after the check.
