# PAS-027 database migration readiness runbook

Status as of 2026-08-21: **LOCAL_REHEARSAL_CLEAR** and
**READY_FOR_REMOTE_PREFLIGHT_AUTH**. This is not authorization to apply a
hosted migration.

## Frozen local evidence

- Preservation checkpoint: `35507db checkpoint: add local PAS-027 data controls`
- Migration 0006 SHA-256:
  `024217bca725e2f8c76904a03092076672fe15326a96341a2ee19991ae898d33`
- Migration 0007 SHA-256:
  `d0d0144a6ec77401f11246ef3eef24ed3efc8c6d46c4d87179d5430b7e0268e2`
- Local engine: PGlite 0.5.5 / PostgreSQL 18.3 WASM
- Rehearsal result: 13 passed, 0 failed, 0 blocked

Run the evidence suite with:

```text
cd database/rehearsal
npm run rehearse
```

The suite proves local PostgreSQL semantics for blank replay, representative
upgrade data, grants, RLS, exact-source memory writes, two-user isolation,
failure atomicity, forward freeze/resume, and physical plus logical recovery.
It does not prove hosted Supabase Auth, PostgREST, migration ledger state,
production locks, or hosted backup recovery.

## Changes made after the preservation checkpoint

- Migration 0006 now has an explicit transaction boundary.
- Migration 0007 aborts when legacy memory cannot be proven to be a confirmed,
  exact copy of an owned user message.
- Initial memory writes use a narrow owner-bound `SECURITY DEFINER` predicate;
  private `messages.user_id` remains hidden from the public history projection.
- Memory lineage and supersedes foreign keys now bind `(id, user_id)`, preventing
  cross-user cascade edges at the database layer.
- `revise_memory` rejects a null expected version and uses null-safe comparison.
- The emergency response is a non-destructive forward freeze, not a broad
  compatibility down migration.

## Authorization stages

1. **Local rehearsal** — complete.
2. **Read-only hosted preflight** — may now be requested separately.
3. **Backup creation and independent restore verification** — not yet done.
4. **Migration apply authorization** — do not request until all gates below are
   complete.
5. **Post-migration two-user Auth/PostgREST smoke** — required before normal
   writes resume.

## Gate A — read-only hosted preflight

- [ ] Record the hosted PostgreSQL/Supabase versions and project health.
- [ ] Run `database/rehearsal/preflight_before_0006_0007.sql` under read-only
      authorization.
- [ ] Reconcile the hosted migration ledger with the repository. Do not use
      `migration repair` as if it changed schema; it only changes ledger state.
- [ ] Confirm the hosted schema is exactly at the expected 0005 boundary and
      that the 0006/0007 columns are absent.
- [ ] Require all legacy-memory blocker counts to be zero: unconfirmed,
      invalid length, missing/dangling source, cross-user source, non-user
      source, and non-exact source.
- [ ] Record the number of durable assistant rows that 0006 will mark legacy.
- [ ] Record table sizes, row counts, long transactions, lock waiters, and the
      existing RLS/grant snapshot.
- [ ] If any blocker is non-zero, stop. Design a separate reviewed cleanup or
      user-reconfirmation migration; do not silently mark the text as a quote.

## Gate B — backup and recovery

- [ ] Stop application writes before taking the final backup.
- [ ] Create fresh roles, schema, and data logical dumps using the supported
      Supabase CLI workflow; record hashes and timestamps without recording
      secrets.
- [ ] Restore those dumps into a disposable PostgreSQL environment and compare
      schema, row counts, ownership, and representative constraints.
- [ ] Document the accepted RPO, target RTO, restoration owner, and decision
      authority.
- [ ] Confirm sufficient quota/disk and that backup retention meets the chosen
      rollback window.
- [ ] Treat the local PGlite restore as rehearsal evidence only; it is not a
      verified hosted backup.

## Gate C — maintenance and apply plan

- [ ] Freeze migration files and recheck both SHA-256 values above.
- [ ] Pin the exact Supabase CLI version that will perform the migration. Using
      that same version, replay 0001–0007 in a disposable official local stack
      and confirm that the explicit transaction boundaries and migration ledger
      updates behave as expected. PGlite does not exercise the CLI migration
      parser or ledger integration.
- [ ] Under the separately authorized hosted preflight, run the supported
      migration dry-run and require that it proposes only the reviewed 0006 and
      0007 files. A dry-run result is evidence, not permission to apply.
- [ ] Set bounded `lock_timeout` and `statement_timeout` appropriate to the
      measured hosted sizes.
- [ ] Enter a maintenance mode that stops durable message and memory writes.
- [ ] Confirm there are no long transactions or blocking locks.
- [ ] Apply 0006 exactly once, verify its ledger row and schema, then apply 0007
      exactly once. Do not blindly replay 0007: replay would opt profiles out
      again.
- [ ] Do not run old and new backend versions concurrently. The new backend
      needs the new columns; the old backend cannot satisfy the new durable
      provenance contract.
- [ ] Keep normal writes disabled until postflight and two-user smoke pass.

## Gate D — postflight before reopening writes

- [ ] Run `database/rehearsal/postflight_after_0006_0007.sql` and require every
      invalid count to be zero and every named constraint to be validated.
- [ ] Confirm all profiles are opted out immediately after migration.
- [ ] Confirm authenticated clients can read only the public message projection
      and cannot read internal release provenance columns.
- [ ] Confirm the four PAS-027 helper/RPC functions have empty search paths,
      authenticated-only execution, and no anon/PUBLIC execution.
- [ ] Reload the PostgREST schema cache if required by the hosted environment.
- [ ] Using two disposable users, verify own public history, cross-user zero
      rows, exact-source memory acceptance after explicit opt-in, tamper
      rejection, version revision, pause/resume, lineage deletion, export, and
      account deletion.
- [ ] Verify no secret, raw exception, internal provenance, or other user's data
      appears in API responses or logs.

## Failure and recovery decisions

- Before writes reopen: restore the verified pre-migration backup into an
  isolated database, validate it, and switch both database and application back
  together. Never use ledger repair as schema rollback.
- After writes reopen: first enter maintenance mode and run
  `database/rehearsal/forward_freeze_after_0007.sql`. It preserves rows and
  reads while revoking every authenticated memory mutation. Prefer a reviewed
  forward fix.
- `database/rehearsal/resume_after_forward_freeze.sql` restores only the narrow
  0007 grants and keeps every profile opted out; owners must explicitly opt in
  again.
- Restoring an older backup after new writes exist can lose data. It requires an
  explicit RPO decision and reconciliation plan.

## Residual risks that local rehearsal cannot close

- Hosted ledger/schema drift and current data shape.
- Supabase CLI migration batching and ledger integration; the local PGlite
  rehearsal validates PostgreSQL behavior, not the CLI execution layer.
- PostgREST column/RPC exposure and JWT-to-role behavior.
- Production lock duration, WAL/IO impact, and connection-pool behavior.
- Actual Supabase backup/PITR availability and restore correctness.
- The migration currently allows authenticated clients to provide memory
  timestamps; those timestamps must not be treated as trusted audit evidence.
- The version-chain RPC preserves adjacency, but database constraints do not
  independently prove every same-user parent has `version = child.version - 1`.

## Readiness decision

The current local state is suitable for asking for a **separate read-only hosted
preflight authorization**. It is **not yet suitable for asking for direct
migration-apply authorization**. That later request requires Gate A and Gate B
to be completed with real hosted evidence and a named maintenance/recovery plan.
