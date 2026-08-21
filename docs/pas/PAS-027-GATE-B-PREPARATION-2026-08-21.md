# PAS-027 Gate B preparation — 2026-08-21 (historical)

## Superseding status

**SUPERSEDED_BY_GATE_B_TECHNICAL_RESTORE_PASS**

This file is preserved as the preparation and failed-attempt history. Gate B
run `20260821-03` subsequently completed one successful hosted read-only dump
and an ACL-faithful isolated restore. The current completion record is
`PAS-027-GATE-B-COMPLETION-2026-08-21.md`. Statements below that say Gate B
had not run describe the earlier point in time and must not be used as current
release status.

## Historical decision at preparation time

**READY_FOR_USER-INITIATED_SECURE_SOURCE_DUMP**

Gate A remains passed with the documented migration-ledger exception. Gate B
has not been executed and must not be reported as passed. No hosted migration,
migration repair, deployment, database write, or DeepSeek call occurred.

## Completed preparation

- Source project identity was confirmed read-only as PAS
  (`qhynfdiiicebnjfukwaw`, Singapore, `ACTIVE_HEALTHY`, PostgreSQL 17.6.1).
- Supabase CLI `2.111.0` was downloaded from the signed GitHub release into an
  isolated tools directory outside the repository.
- The Windows x64 release archive SHA-256 was independently compared with the
  release checksum and matched exactly:
  `0b7078233f4a98556f60c24d27b103a0ab1d9b9df4a6782744d66af99cc5730e`.
- The exact CLI reported version `2.111.0`.
- Read-only dry runs were generated for the official roles, schema, and data
  dump forms. They used a deliberately fake local connection string and made
  no database connection.
- Docker Desktop `4.87.0` was installed from the exact winget package after
  winget verified the installer hash. The installed Docker client is
  `29.7.2`.
- CPU firmware virtualization and second-level address translation are both
  enabled. The system has approximately 88 GB of free space on drive C.
- Repository HEAD was `cd8ea908e78cfedab537272f1085ec2c27154d99` and the
  worktree was clean before this evidence note was added.

## Continued preparation after WSL activation

- WSL `2.7.12.0` and kernel `6.18.33.2-2` are active. Docker Desktop `4.87.0`
  now exposes a healthy local Linux engine through the `desktop-linux` context
  and `npipe:////./pipe/dockerDesktopLinuxEngine` only.
- Supabase CLI `2.111.0` pulled the official
  `public.ecr.aws/supabase/postgres:17.6.1.156` image. Its verified immutable
  image ID is
  `sha256:ca7871b587ca2c401ac0f325df6249c9aa0d25647ded34631158efc51176767f`.
- The CLI's first empty-stack start attempt tried to publish PostgreSQL on
  `0.0.0.0:55432`; Windows rejected the bind and the CLI stopped and removed
  the container before any backup existed. That path was rejected rather than
  weakening the isolation boundary.
- A replacement restore target was created directly from the same immutable
  official Supabase PostgreSQL image with `--network none`, no published ports,
  no mounts, and a distinct local identity. It is healthy, reports PostgreSQL
  `17.6`, and contains the expected managed `auth` and `storage` schemas plus
  Supabase platform roles.
- The direct hosted database endpoint is IPv6-only and is not routable from
  this host. The official Singapore shared-pooler session endpoint is reachable
  over IPv4 on port `5432`; official documentation confirms this is the
  supported fallback for IPv4-only clients.
- A source-dump executor was independently reviewed against the exact CLI
  `2.111.0` roles, schema, and data `--use-copy` dry runs. The reviewed executor
  SHA-256 is
  `7483623aff28350f63d2b60ec720d530edd61131c4a9ccb8f90ed37cd21f4f2b`.
  It pins the image by digest, verifies the local Docker pipe before prompting,
  sets `default_transaction_read_only=on`, sends the masked password through
  process stdin directly into container tmpfs, and uses atomic protected output
  files. The password is not written to the host, command line, logs, or chat.

## Current blocking input

Gate B still has not connected to the source database or created a backup. The
Codex command environment cannot display an interactive Windows password form
on the user's desktop. Two attempted form launches were stopped while still at
the prompt; no source dump container, password file, result file, or database
connection was created.

The remaining action is for the user to launch the local reviewed wrapper
`pas-gate-b-work/启动-Gate-B-安全只读备份.cmd` and enter the existing database
password in its masked local form. The password must not be posted in chat and
must not be reset merely to unblock this exercise. After the three dumps
complete, Codex can resume automatically from the protected result metadata,
restore only into the already-proven isolated target, and perform Gate B
verification.

## Required execution invariants

- Source identity must equal `qhynfdiiicebnjfukwaw`; the restore target must
  be a different, disposable local database.
- The source is used only by the three supported dump commands. The target is
  the only database that may receive restore writes.
- Roles, schema, and data files are written outside the Git repository into a
  current-user-only directory; their contents and connection strings are never
  printed or included in the evidence report.
- Each file must be non-empty and record UTC start/end time, byte length, and
  SHA-256. Restore must consume the unchanged files.
- Restore order is roles, schema, then data in a single error-stopping restore
  operation. Any error leaves Gate B failed.
- The restored database must reproduce the 0005 boundary, migration ledger,
  exact aggregate counts, RLS, policies, grants, functions, ownership, and
  legacy-memory blocker counts from Gate A, except that the official dump
  deliberately excludes `supabase_migrations`; the hosted ledger remains
  verified by the separate Gate A evidence and must not be repaired to force a
  match.
- The official schema dump deliberately excludes hosted Auth/Storage schemas
  and reserved roles. Recovery evidence must therefore be scoped to restored
  business objects plus Auth/Storage data coverage; it must not claim a
  byte-for-byte clone of the entire hosted cluster.
- Auth coverage (two users) and Storage coverage (zero buckets/objects) must be
  stated explicitly; a public-schema-only restore is insufficient.
- Actual backup cut time and restore duration must be recorded as RPO/RTO
  evidence. Retention, restoration owner, and rollback decision authority
  remain operational decisions that must be named before migration apply.

## Still prohibited

- `db push`, `migration up`, `migration repair`, migration apply, or SQL writes
  against the hosted project;
- restore commands whose target identity has not been proven different from
  production;
- deployment, normal-write cutover, or DeepSeek evaluation;
- treating this preparation record as a backup or recovery proof.
