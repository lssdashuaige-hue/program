# PAS-027 Gate C2 diagnostic attempt C2D-20260822-02 — 2026-08-22

## Decision

**FAIL_CLOSED / TLS_CA / FINGERPRINT_NOT_OBTAINED / ORDINAL_CONSUMED / GATE_C2_NOT_PASSED**

The separately authorized one-shot diagnostic bound frozen candidate manifest
`84c9390440ddc60adc9f3c37972cdb64e0f17ee26c3434036cb257af567592dd`
to ordinal `C2D-20260822-02`. Its contract was installed and independently
checked before any password prompt or hosted action. After local secure password
input, the ordinal was frozen and exactly one Docker child process was invoked.
The container reached `PSQL_STARTED`, then failed closed in the allowlisted
category `TLS_CA`. No server connection or fingerprint was observed.

This result is terminal for the ordinal. It must not be retried, supplemented,
combined with another run or treated as migration/deployment evidence.

## Immutable identity

- Candidate manifest SHA-256:
  `84c9390440ddc60adc9f3c37972cdb64e0f17ee26c3434036cb257af567592dd`
- One-shot contract SHA-256:
  `ea5d036ba624e5b83dfec45f465cf874472898de5fc542545963f7266773c449`
- Ordinal freeze SHA-256:
  `6ccd17b71208238e6a6e00500e4ca2dd78b202c671199b6295ec232e47470fbf`
- Terminal result SHA-256:
  `ac27ea2f73e59eb5e4d67515e71eb05302da8400aeea4dfcf7a3585a10d62348`
- Runner SHA-256:
  `d916909ffca1fe221e87612f6b0d33e8b31b0fac622b9a7fce4299579b3a5422`
- Module SHA-256:
  `30afe26c5e27636264404a1053040cf725434413da016bf9b4d5e615f63fe41e`
- Frozen fingerprint source SHA-256:
  `ce69928afc1abe6697a3f1d1091ef988a4e1c8bccc70edc93ae3e1b53abe41f3`
- Generated read-only SQL SHA-256:
  `77bfe4f139a620481e2c7e6160b083a375a7a791c85042e6acf3516190341339`
- Protected preauthorization audit SHA-256:
  `9f42901287abe2a5759cef15eb51a73e190646edc9fee62c50de5f7f30c5e48c`
- Protected terminal audit SHA-256:
  `686223039cfe524d566f58f701d6b80ecb7c311c92fba786d4701e24612f636a`
- Protected post-terminal state audit SHA-256:
  `90263272c2f71861fc49b2066945fc3a0d0b98b3cce3ed191ddeac0179ac2a75`

## Safe terminal evidence

- Status: `FAIL_CLOSED`
- Conclusion: `ONLINE_DIAGNOSTIC_FINGERPRINT_FAILED`
- Safe category: `TLS_CA`
- Host child-process invocations: `1 / 1`
- Authorized maximum `psql` invocations per Docker process: `1`
- Observed `psql` invocation: one invocation reached `PSQL_STARTED`
- Retries: `0`
- Follow-up queries: `0`
- Process duration: `6119 ms`
- Process exit code: `2`
- `psql` exit code: `2`
- Last bootstrap phase: `PSQL_STARTED`
- Phase and exit-code contracts: valid
- Timed out: `false`
- Termination and output capture confirmed: `true`
- Server-connected marker: `false`
- Fingerprint: absent
- Raw stdout/stderr persisted: `false`
- Password persisted: `false`
- Fingerprint SQL persisted: `false`
- Terminal evidence directory contents: the safe terminal JSON only

The allowlisted classifier matched a CA/trust signal and no server-connected
marker was observed. Raw child output was intentionally destroyed, so this
record cannot replay the message or assert one unique root cause. An explicit,
protected project Server root certificate is the leading remediation
hypothesis because current Supabase `psql` guidance calls for that trust root;
it remains a hypothesis until validated in a new frozen candidate. This attempt
does not validate the supplied password, database contents or migration ledger.

## Boundary audit

The frozen contract allowed at most one Docker process and one `psql`
invocation, with zero retries and zero follow-up queries. The terminal phases
show that the one invocation reached `PSQL_STARTED`; they do not show a
successful database connection. The report otherwise matches those limits. It
did not run migration list, `db push --dry-run`, migration apply, migration
repair, deployment or DeepSeek. It used no fallback connection and retained no
raw child output. The predecessor Gate C2 runner, contract, freeze and result
hashes remain unchanged.

The terminal candidate manifest and contract remain installed as protected
evidence. The existing ordinal freeze is checked before password input and
before Docker, so the same ordinal cannot be executed again. A protected
post-terminal state audit records that guard without invoking an external
process.

## Required successor state

Candidate `C2D-CANDIDATE-20260822-02`, its contract and ordinal are consumed
predecessor evidence and must remain immutable. Before any later hosted
diagnostic:

1. extend the existing deterministic TLS-CA and certificate-file fixtures;
2. implement and offline-review a protected, hash-bound project Server root
   certificate input as the leading remediation hypothesis;
3. if that design passes review, obtain the current certificate locally from
   the Supabase dashboard without sending it through chat, bind its hash and
   pass the network-disabled, password-free local bootstrap probe;
4. independently review and freeze a new candidate without a contract; and
5. obtain a fresh explicit authorization binding that new manifest to a new
   diagnostic ordinal.

Even a later successful diagnostic would not itself complete Gate C2 or
authorize migration or deployment.
