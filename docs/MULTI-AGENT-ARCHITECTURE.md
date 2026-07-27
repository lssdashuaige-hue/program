# PAS Multi-Agent Architecture

## Purpose

PAS uses multiple internal roles to improve psychological safety without
turning the product into a collection of autonomous agents. The user continues
to experience one stable PAS companion.

The architecture preserves:

- PAS-001: PAS helps a person understand themselves instead of defining them.
- PAS-002: psychological interpretations remain tentative and revisable.
- PAS-003: the user interacts with a reflective companion, not an authority.
- PAS-007: safety, autonomy, reality orientation, and non-dependency are system
  boundaries.

## Phase 1: Reflection and Review

```text
User message
  → Reflection Agent
  → draft response
  → Review Agent
  → approved or rewritten final response
  → user
  → future memory-update hook
```

### Reflection Agent

The Reflection Agent:

- understands and mirrors the user's stated experience;
- asks at most one useful exploratory question;
- may offer tentative, plural psychological hypotheses;
- does not diagnose, label, or present an interpretation as fact.

### Review Agent

The Review Agent is internal and never speaks to the user as a separate
identity. It checks the draft for:

- diagnosis, identity labels, and unsupported certainty;
- reinforcement of hopelessness, isolation, paranoia, or negative absolutes;
- language that encourages emotional dependence on AI;
- violations of autonomy or reality orientation;
- mishandling of possible immediate danger;
- departures from PAS-001, PAS-002, PAS-003, or PAS-007.

If the draft is safe, the reviewer preserves it. If not, the reviewer rewrites
it into a useful PAS response rather than returning a generic refusal.

### Safety invariant

An unreviewed Reflection Agent draft is never sent to the user. If review
cannot complete, the API fails closed with a temporary service error.

## Phase 2: Memory Agent

The Memory Agent will run only after the final reviewed response. Its output
will be a candidate memory, not a durable fact.

```text
Reviewed interaction
  → Memory Agent
  → candidate memory
  → explicit user confirmation
  → durable memory
```

It must distinguish:

- user-reported experience;
- the user's own reflection;
- a tentative repeated pattern;
- an AI hypothesis that must not be saved as fact.

The Memory Agent foundation is implemented behind
`MEMORY_AGENT_ENABLED=false`. It can generate a typed candidate for later user
confirmation, but it cannot write to Supabase. Durable confirmation remains
blocked until authenticated user identity and an explicit confirmation endpoint
are implemented.

## Phase 3: Full architecture

Additional agents or services may later cover context retrieval, risk
classification, memory revision, and evaluation. They must remain behind one
stable user-facing PAS identity, use typed handoffs, and preserve the Phase 1
safety invariant.

The architecture should expand only when measured failure cases justify a new
role. Agent count is not a product goal.
