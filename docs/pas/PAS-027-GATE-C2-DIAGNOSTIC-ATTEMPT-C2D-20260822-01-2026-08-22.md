# PAS-027 Gate C2 diagnostic attempt C2D-20260822-01 — 2026-08-22

## Decision

**FAIL_CLOSED / FINGERPRINT_NOT_OBTAINED / ORDINAL_CONSUMED / GATE_C2_NOT_PASSED**

The separately authorized diagnostic attempt bound candidate manifest
`bc92087362e070871bb5b575ad932468868147aca5522fa814c1a3b57b3fff20`
to ordinal `C2D-20260822-01`. The one-shot contract was installed, the ordinal
was frozen, and exactly one Docker client process was invoked. The process
ended before the first container bootstrap phase. No `psql` phase, server
marker or fingerprint was observed.

This result is terminal for the ordinal. It must not be retried, supplemented,
combined with another run or treated as migration/deployment evidence.

## Immutable identity

- Candidate manifest SHA-256:
  `bc92087362e070871bb5b575ad932468868147aca5522fa814c1a3b57b3fff20`
- One-shot contract SHA-256:
  `d286e12b4dfb021ac6526d3311d50c4b9d7fc670856b34fed48399a6ce78ad2c`
- Ordinal freeze SHA-256:
  `e632022564fc9bc33bf7118549d48d72473bc14ecf9a41dcb1a5fec8fc9f7b50`
- Terminal result SHA-256:
  `e35f245be867d282ff2dcfb185382146c60abcfe99250891a0a0b3948324b311`
- Runner SHA-256:
  `9fb59d73e0779f6efbb2fc1fa92aad2d471101cf6ab22e9e0cd9a7701b6c6a7a`
- Module SHA-256:
  `00a43580b00c556d668103a6c872e275b0dc47af2a4331d60471778030f6a092`
- Frozen fingerprint source SHA-256:
  `ce69928afc1abe6697a3f1d1091ef988a4e1c8bccc70edc93ae3e1b53abe41f3`
- Generated read-only SQL SHA-256:
  `77bfe4f139a620481e2c7e6160b083a375a7a791c85042e6acf3516190341339`

## Safe terminal evidence

- Status: `FAIL_CLOSED`
- Conclusion: `ONLINE_DIAGNOSTIC_FINGERPRINT_FAILED`
- Safe category: `DOCKER_OR_SHELL_START`
- Host child-process invocations: `1 / 1`
- Retries: `0`
- Follow-up queries: `0`
- Process duration: `77 ms`
- Process exit code: `1`
- Container bootstrap phases: `0`
- `psql` exit marker: absent
- Server-connected marker: absent
- Fingerprint: absent
- Raw stdout/stderr persisted: `false`
- Password persisted: `false`
- Fingerprint SQL persisted: `false`
- Current evidence directory contents: the safe terminal JSON only

The report sets `hosted_contacted=true` conservatively immediately before the
single Docker attempt. `server_connected=false` is the authoritative evidence
that no database connection was observed. The retained stderr length and hash
cannot be reversed into a specific daemon, context, image, argument,
entrypoint or shell cause. The terminal root cause therefore remains unknown.

## Boundary audit

The attempt did not run migration list, `db push --dry-run`, migration apply,
migration repair, deployment or DeepSeek. It installed no fallback connection,
performed no follow-up query and retained no raw child output.

A preliminary local launcher command referenced a PowerShell path that did not
exist. It stopped before loading the diagnostic runner and before any freeze,
Docker process or hosted contact. It was not an online attempt and did not
consume the ordinal. The terminal attempt described above is the only
contract-counted diagnostic process.

## Required successor state

Candidate `C2D-CANDIDATE-20260822-01`, its contract and ordinal are consumed
predecessor evidence and must remain immutable. Any successor must first:

1. improve startup-failure observability using secret-safe fixed categories;
2. pass synthetic conflict and secret tests;
3. pass a separate local Docker bootstrap probe with `--network none`,
   `--pull=never`, empty stdin and zero PG/SQL/`psql` surface;
4. freeze a new candidate manifest with no execution contract installed; and
5. receive a fresh, separately explicit ordinal authorization.

Steps 1–4 were later completed offline by successor
`C2D-CANDIDATE-20260822-02`, manifest SHA-256
`84c9390440ddc60adc9f3c37972cdb64e0f17ee26c3434036cb257af567592dd`.
That successor remains `FROZEN_NOT_AUTHORIZED`: step 5 has not occurred, and no
new execution contract or ordinal is installed.

Even a later successful diagnostic would not itself complete Gate C2 or
authorize migration or deployment.
