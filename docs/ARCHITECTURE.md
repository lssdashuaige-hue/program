# PAS Alpha Architecture

```text
Browser
  → Next.js frontend
  → FastAPI API
     → conversation and safety pipeline
     → LLM adapter
     → Supabase PostgreSQL
```

- The browser receives only public configuration.
- Supabase secret or service credentials stay in the backend.
- Every user-data table in an exposed schema uses row-level security.
- Memory requires explicit user confirmation before becoming durable.
- The current `/chat` endpoint is a deterministic scaffold; a versioned model adapter will replace it in a later sprint.
- Cloud resources are created only after organization, region, cost, and scope confirmation.

The authoritative architecture and implementation requirements are maintained in:

- [PAS-008 Technical Architecture](pas/PAS-008-TECHNICAL-ARCHITECTURE.md)
- [PAS-013 Product Requirements Document](pas/PAS-013-PRD.md)
- [PAS-016 AI Core Implementation](pas/PAS-016-AI-CORE-IMPLEMENTATION.md)
- [PAS-018 Safety Guardrails](pas/PAS-018-SAFETY-GUARDRAILS.md)
- [PAS-023 Data Privacy & Trust](pas/PAS-023-DATA-PRIVACY-TRUST.md)
