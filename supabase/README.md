# Supabase migration-only CLI map

This directory is the pinned, migration-only Supabase CLI view of the database
migrations. It is not a hosted product configuration. Never run
`supabase config push` from this directory; hosted Auth, API, Storage, and
network settings are reviewed and managed separately.

The canonical authored SQL remains in `database/migrations/`; every mapped SQL
file here must stay byte-identical to its source file.

The hosted project already contains the semantic `0001` schema but has no
ledger row for it. For that reason this hosted deployment map deliberately
excludes `0001_initial_schema.sql`. Do not add it, replay it, or use
`migration repair` to manufacture a row.

| Hosted CLI version | Source file | SHA-256 |
| --- | --- | --- |
| `20260727034958` | `0002_confirmed_memory_writes.sql` | `91941bb25d7d805a1ba4eb8bc7c58ed1d9e14e8773c3c9d4f82378caf6130251` |
| `20260814091709` | `0003_conversation_history.sql` | `5d9b6c62065a0b1aeb551ef7d4054aa613879ac3ca55b704665b669e69ad4859` |
| `20260814091937` | `0004_conversation_owner_fk_index.sql` | `a302fcf6c3a6330150348d5656ec110a2ed99d282b9a0151a9acdd9cbd5abbdb` |
| `20260814093334` | `0005_backend_only_conversation_writes.sql` | `f6f7ef1d9972ae24bd12ec834a486835a0b27e68b74d7be997de8eb557ca1545` |
| `20260821094736` | `0006_dual_gate_message_provenance.sql` | `024217bca725e2f8c76904a03092076672fe15326a96341a2ee19991ae898d33` |
| `20260821094738` | `0007_user_data_control.sql` | `d0d0144a6ec77401f11246ef3eef24ed3efc8c6d46c4d87179d5430b7e0268e2` |

Run `npm run verify:supabase-map` from `database/rehearsal` before any
migration dry-run. The hosted dry-run must not use `--include-all`, roles, or
seed data and must propose exactly the final two files. A dry-run is evidence,
not permission to apply them.
