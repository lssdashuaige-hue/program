# PAS-027 database migration readiness runbook

Status as of 2026-08-22: **GATE_A_PASS**,
**GATE_B_TECHNICAL_PASS_RELEASE_CONDITIONAL**, **GATE_C1_PASS**, and
**GATE_C2_FAIL_CLOSED_NOT_PASSED**. Hosted ordinal `20260821-01` stopped at
the first read-only fingerprint before either migration CLI business command
ran. The offline observability repair now has a reviewed, protected candidate
with manifest SHA-256
`bc92087362e070871bb5b575ad932468868147aca5522fa814c1a3b57b3fff20`.
That candidate was bound to contract
`d286e12b4dfb021ac6526d3311d50c4b9d7fc670856b34fed48399a6ce78ad2c`
and consumed by terminal ordinal `C2D-20260822-01`. The attempt failed closed
before its first container bootstrap phase and produced no fingerprint. The
candidate, contract and ordinal must not be reused. See
`PAS-027-GATE-C2-DIAGNOSTIC-ATTEMPT-C2D-20260822-01-2026-08-22.md`.
The project is not ready for migration apply or deployment; any later hosted
request requires a newly frozen successor candidate and a separately explicit
new ordinal.

## Frozen local evidence

- Preservation checkpoint: `35507db checkpoint: add local PAS-027 data controls`
- Migration 0006 SHA-256:
  `024217bca725e2f8c76904a03092076672fe15326a96341a2ee19991ae898d33`
- Migration 0007 SHA-256:
  `d0d0144a6ec77401f11246ef3eef24ed3efc8c6d46c4d87179d5430b7e0268e2`
- Hosted deployment versions: `20260821094736` for 0006 and
  `20260821094738` for 0007
- Pinned Supabase CLI: `2.111.0`
- Official-stack Gate C1 result: PASS (`20260821T100712Z`)
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

1. **PGlite local rehearsal** — complete.
2. **Read-only hosted preflight (Gate A)** — complete.
3. **Technical backup and independent restore (Gate B)** — complete; release
   operations remain conditional on the final post-freeze backup and named
   RPO/RTO/owners.
4. **Official-stack CLI replay (Gate C1)** — complete.
5. **Hosted read-only migration dry-run (Gate C2)** — attempted under ordinal
   `20260821-01`, but failed closed before `migration list` or
   `db push --dry-run`; not passed and the ordinal is consumed.
6. **Migration apply authorization** — do not request until all remaining
   operational gates below are complete.
7. **Post-migration two-user Auth/PostgREST smoke (Gate D)** — required before
   normal writes resume.

## Gate A — read-only hosted preflight

- [x] Record the hosted PostgreSQL/Supabase versions and project health.
- [x] Run `database/rehearsal/preflight_before_0006_0007.sql` under read-only
      authorization.
- [x] Reconcile the hosted migration ledger with the repository. Do not use
      `migration repair` as if it changed schema; it only changes ledger state.
- [x] Confirm the hosted schema is exactly at the expected 0005 boundary and
      that the 0006/0007 columns are absent.
- [x] Require all legacy-memory blocker counts to be zero: unconfirmed,
      invalid length, missing/dangling source, cross-user source, non-user
      source, and non-exact source.
- [x] Record the number of durable assistant rows that 0006 will mark legacy.
- [x] Record table sizes, row counts, long transactions, lock waiters, and the
      existing RLS/grant snapshot.
- [x] If any blocker is non-zero, stop. Design a separate reviewed cleanup or
      user-reconfirmation migration; do not silently mark the text as a quote.

## Gate B — backup and recovery

- [ ] Stop application writes before taking the final backup.
- [x] Create fresh roles, schema, and data logical dumps using the supported
      Supabase CLI workflow; record hashes and timestamps without recording
      secrets.
- [x] Restore those dumps into a disposable PostgreSQL environment and compare
      schema, row counts, ownership, and representative constraints.
- [ ] Document the accepted RPO, target RTO, restoration owner, and decision
      authority.
- [ ] Confirm sufficient quota/disk and that backup retention meets the chosen
      rollback window.
- [x] Treat the local PGlite restore as rehearsal evidence only; it is not a
      verified hosted backup.

## Gate C — maintenance and apply plan

- [x] Freeze migration files and recheck both SHA-256 values above.
- [x] Pin the exact Supabase CLI version that will perform the migration. Using
      that same version, replay 0001–0007 in a disposable official local stack
      and confirm that the explicit transaction boundaries and migration ledger
      updates behave as expected. PGlite does not exercise the CLI migration
      parser or ledger integration.
- [ ] Under the separately authorized hosted preflight, run the supported
      migration dry-run and require that it proposes only the reviewed 0006 and
      0007 files. A dry-run result is evidence, not permission to apply.
      Attempt `20260821-01` did not reach either migration CLI command because
      the initial hosted read-only fingerprint process returned non-zero. See
      `PAS-027-GATE-C2-ATTEMPT-20260821-01-2026-08-22.md`. FAIL_CLOSED proves
      safe stopping, not Gate C2 completion; zero business-command attempts do
      not constitute a passing dry-run.
- [x] Complete the offline, secret-safe diagnostic observability repair; pass
      source and detached-copy local suites; obtain independent `P0=0`,
      `P1=0`, `P2=0` review; and freeze candidate manifest
      `bc92087362e070871bb5b575ad932468868147aca5522fa814c1a3b57b3fff20`.
      See `PAS-027-GATE-C2-DIAGNOSTIC-PREPARATION-2026-08-22.md`.
- [x] Obtain and execute the separately authorized diagnostic-only ordinal
      `C2D-20260822-01` bound to that manifest. It ended `FAIL_CLOSED` without a
      fingerprint, consumed the ordinal and did not complete Gate C2.
- [ ] Complete and freeze a new startup-observability candidate. Any later
      diagnostic authorization must cite that new manifest and a fresh ordinal;
      it must not reuse the predecessor manifest or contract.
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

The current state is **not suitable for asking for migration-apply or deployment
authorization**. Gate C2 did not pass; ordinals `20260821-01` and
`C2D-20260822-01` must not be retried. The first diagnostic candidate, its
contract and its ordinal are terminal predecessor evidence, not a future
execution target. A later hosted request is permissible only after a new
candidate is frozen without a contract and the request explicitly binds that
new manifest to a fresh diagnostic ordinal. It must still be a diagnostic-only
read-only fingerprint, not a migration dry-run. Direct migration authorization
also remains blocked by the operational
Gate B/C items: final backup after write freeze, accepted RPO/RTO, named
recovery/rollback/cutover authorities, bounded timeouts, maintenance mode, and
a fresh lock/transaction check.
