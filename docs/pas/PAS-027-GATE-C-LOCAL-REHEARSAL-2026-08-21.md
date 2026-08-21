# PAS-027 Gate C1 local official-stack rehearsal — 2026-08-21

## Decision

**GATE_C1_PASS / READY_FOR_SEPARATELY_AUTHORIZED_HOSTED_DRY_RUN**

This is not a migration-apply decision. It closes the local CLI/parser/ledger
part of Gate C and permits only a later, separately authorized hosted read-only
dry-run.

## Frozen inputs

- Repository pre-run HEAD: `cd8ea908e78cfedab537272f1085ec2c27154d99`
- Supabase CLI: `2.111.0`
- CLI executable SHA-256:
  `d8bdfc3b3009ee4276d2f733361ea42200419fac9196676a98f9aa9f2e5a53a6`
- CLI archive SHA-256:
  `0b7078233f4a98556f60c24d27b103a0ab1d9b9df4a6782744d66af99cc5730e`
- PostgreSQL image ID:
  `sha256:ca7871b587ca2c401ac0f325df6249c9aa0d25647ded34631158efc51176767f`
- Gate C runner SHA-256:
  `e128782b2cb90e0a580611d5fad33b35b0d3b95bf09950f63e9304c2eb3a8937`
- Atomic result SHA-256:
  `8d4166ac733b39577c186abc582b1b370fc43392a7ed9fcfd85726a30a56fc40`

The hosted deployment map contains the four exact versions already present in
the hosted ledger and two new versions:

1. `20260727034958_confirmed_memory_writes.sql`
2. `20260814091709_conversation_history.sql`
3. `20260814091937_conversation_owner_fk_index.sql`
4. `20260814093334_backend_only_conversation_writes.sql`
5. `20260821094736_dual_gate_message_provenance.sql`
6. `20260821094738_user_data_control.sql`

The map deliberately excludes `0001_initial_schema.sql`: Gate A proved that
its schema exists on the hosted project but has no ledger row. No migration
repair or replay was performed.

## Unified run result

The final run `20260821T100712Z` passed all gates in one atomic JSON report:

- blank official PostgreSQL 17 replay through 0001–0007: PASS;
- hosted-boundary simulation with untracked 0001 and CLI-ledger 0002–0005:
  PASS;
- synthetic two-user upgrade through 0006 then 0007: PASS;
- 13 PAS-027 columns, six named validated constraints, RLS, 11 policies,
  restricted column projection, RPC privileges, legacy provenance, memory
  backfill, and default opt-out postflight: PASS;
- second migration execution reported up to date and did not replay 0007: PASS;
- original 0006 failure injection: SQLSTATE `22P02`; schema/ACL/ledger
  fingerprint unchanged and no 0006 ledger row: PASS;
- original 0007 legacy-memory rejection: SQLSTATE `23514`; fingerprint
  unchanged, 0006 retained, and no 0007 ledger row: PASS;
- CLI `migration list` under `default_transaction_read_only=on`: PASS;
- CLI `db push --dry-run` under the same read-only setting proposed exactly
  the two frozen 0006/0007 deployment files; before/after fingerprint was
  identical: PASS.

Every scenario used a fresh container with no mounts, the fixed image, a
`127.0.0.1`-only database port, and a Docker network with IP masquerading
disabled. All Gate C temporary containers and networks were removed. The Gate
B restore database was not reused or modified.

Protected evidence is stored outside Git at:

`pas-gate-c-work/evidence-20260821T100712Z/`

## Post-review migration-config diagnostic

An independent review found that the generated default `supabase/config.toml`
also described local Auth, API, Storage, and network products. Although the
Gate C commands did not apply those settings, retaining them created an
avoidable future `supabase config push` misuse risk. The tracked file was
therefore reduced to a migration-only CLI configuration, and both that file
and `supabase/README.md` now explicitly prohibit hosted config push.

The targeted diagnostic `20260821T103836Z` then re-ran only the
hosted-boundary `migration list` and read-only `db push --dry-run` path using
that exact tracked config:

- tracked config SHA-256, recorded config SHA-256, and evidence snapshot
  SHA-256 all equal
  `4e980428fc79cb5a472edf647896edb23af9a5fb55489c961839d5390fbed188`;
- the evidence records `migration_config_source=explicit-local-path` and
  contains the exact `migration-config.toml` snapshot;
- the fixed CLI again proposed exactly the two frozen 0006/0007 files;
- the schema/ACL/ledger fingerprint was unchanged;
- no hosted project was contacted and cleanup ended with zero related
  containers and zero related networks.

Diagnostic runner SHA-256:
`6c228974950221f7d87290b9c93bca6dc0d22049b15419877dcdb51db69a9878`.
Atomic diagnostic JSON SHA-256:
`95f6bf0e81bcdec8e5efd95551e5e786ba9a498d354da2fe837d3cb50e2847df`.
Protected evidence is stored at
`pas-gate-c-work/evidence-20260821T103836Z/`.

This diagnostic binds the hardened config to the already-tested CLI path; it
does not replace, splice, or broaden the complete `20260821T100712Z` Gate C1
run and does not change the decision boundary above.

## Authorization boundary

A hosted dry-run still requires explicit user authorization and secure local
password input. Its required result is exactly the same two migration files;
any other proposal is a stop condition. Do not use `--include-all`, roles,
seed, `migration repair`, or a write-capable migration command.

Migration apply remains blocked by the missing maintenance/write-freeze
mechanism, final post-freeze backup, bounded timeouts derived from a fresh
preflight, named RPO/RTO and recovery/cutover authorities, and Gate D.

No hosted Supabase project was contacted, no hosted state was modified, no
deployment or DeepSeek call occurred, and 0006/0007 were not applied online.
