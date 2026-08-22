# PAS-027 Gate C2 diagnostic preparation — 2026-08-22

## Decision

**STATIC_GO_CANDIDATE_ONLY / NOT_AUTHORIZED / GATE_C2_NOT_PASSED**

The offline observability repair required after terminal Gate C2 attempt
`20260821-01` is complete. A detached candidate is frozen for a future,
separately authorized diagnostic-only hosted read-only fingerprint. No online
execution contract or diagnostic ordinal is installed.

This decision does not authorize or complete `migration list`,
`db push --dry-run`, migration apply, migration repair, deployment, or
DeepSeek validation.

## Frozen identity

- Diagnostic source branch: `codex/gate-c2-diagnostic`
- Diagnostic source HEAD:
  `81196adc9dd96240fc19990183370d2a01788535`
- Product runtime baseline:
  `88cd8d397c037738b4142378e778194445bab725`
- Candidate ID: `C2D-CANDIDATE-20260822-01`
- Candidate manifest SHA-256:
  `bc92087362e070871bb5b575ad932468868147aca5522fa814c1a3b57b3fff20`
- Runner SHA-256:
  `9fb59d73e0779f6efbb2fc1fa92aad2d471101cf6ab22e9e0cd9a7701b6c6a7a`
- Module SHA-256:
  `00a43580b00c556d668103a6c872e275b0dc47af2a4331d60471778030f6a092`
- Tests SHA-256:
  `85fcc4671551fea401a1a79c5b383c6e2f2a660085aaf083464ab20ac4487a31`
- Frozen fingerprint source SHA-256:
  `ce69928afc1abe6697a3f1d1091ef988a4e1c8bccc70edc93ae3e1b53abe41f3`
- Generated read-only fingerprint SHA-256:
  `77bfe4f139a620481e2c7e6160b083a375a7a791c85042e6acf3516190341339`

The detached candidate and its verification evidence have protected ACLs
limited to the local operator and SYSTEM. The candidate manifest is the
fingerprint that any later one-shot contract must bind.

## Observability and safety changes

- Fixed phase markers, numeric process/`psql` exits, canonical SQLSTATEs,
  byte counts, hashes, and allowlisted categories replace generic failure text.
- Unknown or malformed `PAS_C2D_V1` protocol lines and non-canonical
  fingerprint stdout fail the output contract.
- Conflicting SQLSTATEs or strong failure signals fail closed; a nominal zero
  exit cannot override an error signal.
- Password variants are scanned in raw, escaped, normalized, encoded, UTF-8,
  UTF-16LE, and UTF-16BE forms before evidence publication.
- Raw child output is not written. Docker uses `--log-driver=none`.
- Evidence files receive exact ACLs before evidence bytes are written and are
  published by same-directory atomic rename without overwriting prior files.
- Evidence paths reject junctions and other reparse points before creating a
  missing directory.
- The container has a BusyBox-compatible 90-second deadline with a five-second
  kill grace. Host termination and output-capture waits are also bounded, and
  unconfirmed lifecycle state cannot pass.
- The future online evidence root is durable and distinct from the temporary
  local-development evidence root.
- The runner contains one Docker child-process call site and one `psql` line;
  retries, follow-up queries, alternate connections, Supabase CLI commands,
  deployment, and DeepSeek are absent.

## Verification

- Source and detached-copy offline suites: PASS
- PowerShell parser errors: `0`
- Classifier/conflict, SQLSTATE/exit, secret, atomic/old-file, static surface,
  old-chain, and LocalPreflight checks: PASS
- LocalPreflight hosted contact: `false`
- LocalPreflight diagnostic process invocations: `0`
- Local bounded-termination probe: PASS
- Fixed local PostgreSQL image timeout syntax probe: PASS with
  `--network none`, `--pull=never`, and `--log-driver=none`
- Independent final review: `P0=0`, `P1=0`, `P2=0`
- Frozen components and byte lengths match the candidate manifest: true
- Protected candidate paths verified: `10`
- Partial evidence files: `0`
- Future execution contract present: `false`
- Online diagnostic freeze present: `false`

The terminal `20260821-01` runner, contract, freeze, and result hashes were
rechecked and remain unchanged. Its FAIL_CLOSED result remains authoritative.

## Required next authorization

The next request may authorize only one diagnostic-only read-only fingerprint
bound to candidate manifest
`bc92087362e070871bb5b575ad932468868147aca5522fa814c1a3b57b3fff20`
and a fresh `C2D-YYYYMMDD-NN` ordinal. The resulting contract must retain one
process, one connection, zero retries, zero follow-up queries, and zero raw
output persistence.

Even a successful diagnostic is not Gate C2 PASS. Its result may only inform a
later, separately frozen and separately authorized complete Gate C2 dry-run.
Migration and deployment remain blocked.
