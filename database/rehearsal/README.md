# Local database migration rehearsal

This directory contains an isolated, synthetic-data rehearsal for migrations
`0001` through `0007`. It never reads Supabase project configuration or
environment credentials and it does not make network calls at runtime.

Run it from this directory:

```text
npm run rehearse
```

The command prints one JSON document using the
`pas-local-database-rehearsal/v1` evidence schema. A zero exit code means every
required check passed. Any failed or blocked check produces a non-zero exit
code; expected negative tests are only passes when PostgreSQL actually rejects
the unsafe operation.

The rehearsal covers:

- blank replay of `bootstrap.sql` and migrations `0001`-`0007` in order;
- upgrade of representative data created at the `0001`-`0005` schema;
- a historical `confirmed=false` memory upgrade negative case that must abort
  `0007` without leaving partial DDL or data changes;
- RLS, column privileges, the three PAS-027 mutation RPCs, and the narrow
  exact-source `SECURITY DEFINER` predicate;
- exact-source memory writes, content tampering, `expected_version=NULL`,
  two-user isolation, and cross-user lineage references;
- transaction atomicity when either migration `0006` or `0007` is forced to
  fail;
- a non-destructive forward freeze that disables every authenticated memory
  mutation while preserving RLS-scoped reads, followed by a narrow resume that
  keeps every profile opted out until explicit consent;
- a physical `dumpDataDir` snapshot taken at the `0005` boundary and restored
  into an independent instance after a simulated `0006`-`0007` upgrade;
- an in-memory `pg_dump` logical data backup restored into a newly migrated
  database, including post-restore RLS isolation.

## What this proves—and what it does not

PGlite is PostgreSQL compiled to WebAssembly, so this exercises PostgreSQL DDL,
constraints, transactions, roles, grants, policies, functions, triggers, and a
real `pg_dump` parser locally. `bootstrap.sql` supplies only the small
`auth.users` and `auth.uid()` contract required by these migrations.

It does **not** emulate hosted Supabase Auth, PostgREST/Data API behavior,
Realtime, the Supabase migration-history ledger, production extensions,
production data shape, locks under production traffic, or Supabase backup/PITR
operations. Passing this rehearsal is therefore necessary local evidence, not
authorization to migrate a hosted project. A hosted read-only preflight,
verified backup/restore plan, maintenance window, and separately approved
migration run are still required.

## Rollback meaning

`forward_freeze_after_0007.sql` is a safe forward freeze. It keeps all new
columns, constraints, policies, and rows; opts every profile out; revokes all
authenticated memory mutation privileges; and leaves owner-scoped reads
available. It never restores the old broad write surface.

`resume_after_forward_freeze.sql` restores only the exact grants created by
`0007`. It does not opt anyone back in. A destructive disaster rollback is
instead rehearsed from a pre-migration physical snapshot restored into an
independent database.
