# PAS

Psychological AI System — an AI-assisted self-exploration platform.

> 不是定义你，而是帮助你理解自己。

PAS 的目标是通过镜像、开放探索、用户确认的动态记忆和现实检验，帮助用户逐渐形成理解自己的能力。它不是心理诊断、人格测试或现实关系的替代品。

## Current milestone

PAS Alpha foundation:

- Next.js 16 frontend；
- FastAPI backend；
- Supabase-ready PostgreSQL schema with row-level security；
- versioned identity, dialogue, reflection, review, memory, and safety prompts；
- local health and reflection API contract；
- formal PAS-001～026 product and engineering specifications。

完整设计基线见 [docs/pas/README.md](docs/pas/README.md)。

## Project structure

```text
.
├── frontend/   # Next.js App Router application
├── backend/    # FastAPI service
├── database/   # Supabase/PostgreSQL migrations
├── prompts/    # PAS identity, dialogue, reflection, review, memory, and safety rules
└── docs/       # Product, safety, privacy, and engineering specifications
```

## Local development

Frontend:

```powershell
cd frontend
npm.cmd run dev
```

Backend (Python 3.12 recommended):

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Copy each `.env.example` to its local `.env` file before connecting cloud services. Never commit real credentials.

For local conversation history, first add the PAS project's Supabase server
secret by double-clicking `配置Supabase服务端密钥.cmd`. The setup window masks the
secret and writes it only to the Git-ignored `backend/.env`. Use a Supabase
**secret** key, never a publishable/anon key, and restart the backend after
saving it.

Only a normal `review` response in `reflection` mode with `risk_level=none` is
eligible for history. Safety-guard, elevated-risk support, fallback responses,
internal drafts, review rationale, and memory-agent internals are never written
to conversation history.

## Internal PAS evaluations

The development-only evaluation page is available at `/internal/evals`. It runs
synthetic PAS boundary cases through the same Reflection → Review → optional
Memory pipeline used by `/chat`, then displays the internal review trace and
deterministic assertions.

The evaluation API is disabled by default. To enable it locally, set
`PAS_EVALS_ENABLED=true` and a unique `PAS_EVALS_ADMIN_TOKEN` of at least 24
characters in `backend/.env`. The page accepts this evaluation token only in
memory. It can run either the core or dialogue suite, retain a completed full
attempt while explicitly rerunning retryable infrastructure failures, and
export/import a versioned JSON report. The report never contains the evaluation
token. It never accepts an OpenAI, DeepSeek, or other provider API key.

The report distinguishes the first complete suite run from later subset
attempts; a combined coverage view is not presented as a clean first-pass run.
Imported JSON is explicitly marked as unsigned and structure-validated only;
it cannot be used to trigger subset reruns or presented as a live acceptance
result. A live report keeps at most 12 explicit retry attempts.
The local Alpha backend also rejects overlapping evaluation runs within one
process. This is a cost and stability guard, not a multi-worker production job
queue. In-progress synchronous runs cannot be recovered after the connection or
page is closed.

Evaluation runs use the model provider already selected by the backend and can
incur provider usage. Use synthetic cases only. Do not paste real user
conversations into the internal evaluation API.

## Project status

- GitHub: [lssdashuaige-hue/program](https://github.com/lssdashuaige-hue/program)
- Supabase: `PAS` project created in Singapore with the initial RLS-protected schema applied
- Production deployment: not created
