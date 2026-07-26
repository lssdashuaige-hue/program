# Database

The SQL files in `migrations/` are designed for Supabase PostgreSQL.

The initial schema uses `auth.users` as the account source of truth, enables
row-level security on every public table, and limits every authenticated user
to rows they own.

Apply the migration only after a Supabase project has been selected.
