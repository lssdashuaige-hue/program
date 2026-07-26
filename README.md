# PAS

Psychological AI System — an AI-assisted self-exploration platform.

> 不是定义你，而是帮助你理解自己。

## Current milestone

PAS Alpha foundation:

- Next.js 16 frontend
- FastAPI backend
- Supabase-ready PostgreSQL schema with row-level security
- Versioned prompt files
- Local health and reflection API contract

## Project structure

```text
.
├── frontend/   # Next.js App Router application
├── backend/    # FastAPI service
├── database/   # Supabase/PostgreSQL migrations
├── prompts/    # PAS identity, reflection, and safety rules
└── docs/       # Product and architecture notes
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

Copy each `.env.example` to its local `.env` file before connecting cloud services.
