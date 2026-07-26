# PAS Alpha architecture

```text
Browser → Next.js frontend → FastAPI API → LLM adapter
                                      ↘ Supabase PostgreSQL
```

- The browser receives only public configuration.
- Supabase secret/service credentials stay in the backend.
- Every public database table has row-level security.
- Memory requires explicit user confirmation before it is treated as durable.
- The current `/chat` endpoint is a deterministic scaffold; an OpenAI adapter
  will replace it in a later sprint.
