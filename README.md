# PAS

Psychological AI System — an AI-assisted self-exploration platform.

> 不是定义你，而是帮助你理解自己。

PAS 的目标是通过镜像、开放探索、用户确认的动态记忆和现实检验，帮助用户逐渐形成理解自己的能力。它不是心理诊断、人格测试或现实关系的替代品。

## Current milestone

PAS Alpha foundation:

- Next.js 16 frontend；
- FastAPI backend；
- Supabase-ready PostgreSQL schema with row-level security；
- versioned identity, reflection, and safety prompts；
- local health and reflection API contract；
- formal PAS-001～025 product and engineering specifications。

完整设计基线见 [docs/pas/README.md](docs/pas/README.md)。

## Project structure

```text
.
├── frontend/   # Next.js App Router application
├── backend/    # FastAPI service
├── database/   # Supabase/PostgreSQL migrations
├── prompts/    # PAS identity, reflection, and safety rules
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

## Project status

- GitHub: [lssdashuaige-hue/program](https://github.com/lssdashuaige-hue/program)
- Supabase: `PAS` project created in Singapore with the initial RLS-protected schema applied
- Production deployment: not created
