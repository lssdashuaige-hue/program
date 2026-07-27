# PAS Alpha Architecture

```text
Browser
  → Next.js frontend
  → FastAPI API
     → Reflection Agent
     → Review Agent
     → final reviewed response
     → future Memory Agent hook
     → Supabase PostgreSQL
```

- The browser receives only public configuration.
- Supabase secret or service credentials stay in the backend.
- Every user-data table in an exposed schema uses row-level security.
- Memory requires explicit user confirmation before becoming durable.
- The `/chat` endpoint preserves its public response contract while internally
  running Reflection Agent → Review Agent when `OPENAI_API_KEY` is configured.
- An unreviewed Reflection Agent draft is never returned if the Review Agent
  fails. The endpoint returns a temporary service error instead.
- Without a configured provider API key, the endpoint keeps a deterministic
  safe scaffold so local development remains usable.
- The model gateway supports OpenAI Responses API and DeepSeek Chat Completions.
  `LLM_PROVIDER=auto` selects DeepSeek when only `DEEPSEEK_API_KEY` is present,
  otherwise OpenAI when only `OPENAI_API_KEY` is present. Explicit provider
  selection remains available.
- Phase 1 does not write memory. Phase 2 will add a Memory Agent after the final
  reviewed response, and only user-confirmed information may become durable.
- Cloud resources are created only after organization, region, cost, and scope confirmation.

The authoritative architecture and implementation requirements are maintained in:

- [PAS-008 Technical Architecture](pas/PAS-008-TECHNICAL-ARCHITECTURE.md)
- [PAS-013 Product Requirements Document](pas/PAS-013-PRD.md)
- [PAS-016 AI Core Implementation](pas/PAS-016-AI-CORE-IMPLEMENTATION.md)
- [PAS-018 Safety Guardrails](pas/PAS-018-SAFETY-GUARDRAILS.md)
- [PAS-023 Data Privacy & Trust](pas/PAS-023-DATA-PRIVACY-TRUST.md)
