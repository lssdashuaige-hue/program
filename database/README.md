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
