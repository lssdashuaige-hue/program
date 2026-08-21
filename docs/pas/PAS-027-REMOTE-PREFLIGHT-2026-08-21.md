# PAS-027 hosted read-only preflight — 2026-08-21

## Decision

**GATE_A_PASS_WITH_DOCUMENTED_LEDGER_EXCEPTION**

The hosted project is suitable for the next separately authorized stage:
creating fresh logical backups and proving an independent restore. This report
does **not** authorize migration apply, migration repair, deployment, or any
other hosted write.

## Scope and integrity

- Frozen local checkpoint: `3aec129`
- Hosted access: metadata and aggregate read-only queries only
- Local query guard: all 11 statements in
  `database/rehearsal/preflight_before_0006_0007.sql` were verified to start
  with `SELECT` before execution
- The 11 statements were then executed and recorded separately because the SQL
  interface returns only the last result set for a multi-statement request
- No message, memory, profile, identity, email, or other user content was read
- No migration, ledger repair, DDL, DML, deployment, or DeepSeek call occurred

## Hosted evidence

| Check | Result |
| --- | --- |
| Project health | `ACTIVE_HEALTHY` |
| Hosted database | PostgreSQL 17.6.1, GA |
| Organization plan | Free |
| Database size | 11 MB |
| Public business rows | profiles 0; conversations 0; messages 0; memories 0; themes 0 |
| Other aggregate data | Auth users 2; Auth identities 2; Storage buckets 0; Storage objects 0 |
| 0006/0007 target columns | 0 present |
| Legacy memory blockers | all 0: unconfirmed, invalid length, missing/dangling source, cross-user source, non-user source, non-exact source |
| Migration impact | 0 profiles to opt out; 0 messages to mark legacy |
| RLS | enabled on all five public business tables |
| Long transactions / lock waiters | 0 / 0 |
| Locks on profiles/messages/memories | none at the observation time |
| Session timeouts | `lock_timeout=0`; `statement_timeout=2min` |
| Security advisor | one non-migration warning: leaked-password protection disabled |
| Performance advisor | two informational unused-index notices on empty tables |

The complete hosted column, constraint, index, policy, trigger, function, RLS,
and grant metadata matched the repository's 0001–0005 semantic boundary.
The existing trigger function is security-invoker with an empty search path;
PUBLIC, anon, and authenticated do not have execute permission.

## Migration-ledger reconciliation

The hosted ledger contains exactly these four migrations:

1. `20260727034958 confirmed_memory_writes`
2. `20260814091709 conversation_history`
3. `20260814091937 conversation_owner_fk_index`
4. `20260814093334 backend_only_conversation_writes`

They correspond to repository migrations 0002–0005. Remote statement hashes
matched the trimmed local content for 0002, 0004, and 0005; the whitespace-
normalized hash matched for 0003. The initial 0001 schema is fully present but
has no ledger row.

This is a documented ledger exception, not unexplained schema drift. Migration
0001 must not be replayed. `migration repair` changes tracking state only and
must not be used without a later, explicit hosted-write authorization.

## Apply blockers (P1)

1. No fresh hosted logical roles/schema/data backup has been created and
   independently restored.
2. The hosted timestamp ledger and repository `000x` files do not yet have a
   pinned-version Supabase CLI deployment mapping. An authorized hosted
   dry-run must propose only reviewed 0006 and 0007 migrations.
3. `lock_timeout=0` is not acceptable for migration apply; the apply session
   needs a measured bounded value and a fresh lock/transaction check.
4. RPO, RTO, restore owner, maintenance/write freeze, rollback authority, and
   backend cutover owner are not yet recorded.
5. The PG17.6 and Supabase CLI execution path has not been replayed in an
   official disposable local Supabase stack; PGlite validates PostgreSQL
   semantics but not CLI ledger integration.
6. Hosted postflight and two-user Auth/PostgREST smoke tests remain pending.

There are no P0 findings. The security-advisor password warning should be fixed
before public launch, but it is not a 0006/0007 migration blocker.

## Next authorization boundary

The next authorization should permit only:

- read-only hosted logical dumps of roles, schema, and data;
- recording dump timestamps and hashes without secrets;
- restoring the dumps only into a disposable isolated environment;
- comparing schema, aggregate row counts, constraints, ownership, and RLS.

It must continue to prohibit migration apply, migration repair, deployment,
production writes, and DeepSeek calls.

## Current references

- Supabase migration workflow:
  https://supabase.com/docs/guides/deployment/database-migrations
- Supabase local/remote CLI workflow:
  https://supabase.com/docs/guides/local-development/cli-workflows
- Supabase backups:
  https://supabase.com/docs/guides/platform/backups
