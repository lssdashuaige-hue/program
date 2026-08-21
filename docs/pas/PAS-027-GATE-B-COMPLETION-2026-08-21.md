# PAS-027 Gate B completion — 2026-08-21

## Decision

**TECHNICAL_BACKUP_AND_ISOLATED_RESTORE_PASS / RELEASE_GATE_CONDITIONAL**

Gate B run `20260821-03` completed exactly one successful hosted read-only
logical backup. Two earlier connection/preflight attempts produced no dump
files. No hosted source call occurred after the successful backup.

The frozen roles, schema, and data dumps were restored into an isolated
PostgreSQL 17 Supabase image. The corrected restore passed process and fidelity
gates; the first restore is retained as a negative control because it exposed
default-ACL broadening despite a successful SQL process exit.

## Verified technical evidence

- Restore order was roles, schema, then data in one error-stopping transaction.
- All 34 COPY targets matched; Auth contained two users and two identities;
  Storage contained no buckets or objects.
- Five business tables, five RLS flags, 11 policies, nine explicit indexes,
  21 validated constraints, functions, triggers, roles, memberships, role
  settings, ownership, and ACLs matched the expected source state.
- Two independent structural restores produced the same 13-category,
  200-item normalized fingerprint after excluding only the database name.
- The restore container used the frozen PostgreSQL 17 image, `network=none`,
  no published ports, and no mounts. No related temporary container remained.

Protected evidence is stored outside Git at:

`pas-gate-b-work/restore-20260821-03-acl-normalized/`

## Remaining release conditions

This technical PASS does not close the operational parts of Gate B. Before an
actual migration, the release owner must still record and execute:

- final backup after durable writes are frozen;
- accepted RPO and target RTO;
- restoration owner, rollback decision authority, and backend cutover owner;
- backup retention window and quota/disk confirmation.

No deployment, migration, ledger repair, DeepSeek call, or hosted write is
authorized by this record.
