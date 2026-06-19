# Concourse

AI-orchestrated study planner for EPSO candidates. Measures real reasoning skill, ingests external practice scores, and rewrites the plan whenever the data changes.

> Stack mirrors [`dora`](https://github.com/giovannifoglietta/dora-mvp) and [`quizventure`](https://github.com/giovannifoglietta/quizventure) on purpose. Same Python/FastAPI/Supabase/Railway pattern, no new toolchain.

## Quick start (local)

```bash
git clone https://github.com/giovannifoglietta/concourse.git
cd concourse
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in keys, see below
uvicorn backend.main:app --reload
```

Browse to:

- `http://localhost:8000/` — landing page
- `http://localhost:8000/health` — health check + config sanity

## External setup (do these once)

The repo runs locally without any external services, but the full app needs three accounts wired up. **Stack is identical to dora — same flow, same gotchas.**

### 1. Supabase (database, EU region)

1. Create a new project at [supabase.com](https://supabase.com), region **eu-central-1** (Frankfurt) for GDPR.
2. In the Supabase dashboard → SQL Editor, paste and run `backend/db/migrations/001_init.sql`.
3. Project Settings → Database → Connection string → choose **Transaction pooler**.
   - Use the URL on **port 6543** (Railway cannot reach the direct IPv6 endpoint — same as dora).
   - Set as `DATABASE_URL` in `.env`.

### 2. Railway (hosting)

1. Create a new project at [railway.app](https://railway.app), connect the GitHub repo.
2. Set environment variables (copy from `.env.example`, fill values).
3. Auto-deploys on push to `main`. Railway reads the Procfile.

### 3. PostHog (analytics, EU region)

1. Create a project at [eu.posthog.com](https://eu.posthog.com).
2. Copy the **Project API Key** → `POSTHOG_PUBLIC_KEY` in `.env`.
3. The frontend reads this from `/config.js` at runtime.

### 4. Anthropic (LLM)

Re-use the same key from dora/quizventure. Set as `ANTHROPIC_API_KEY`.

### 5. Stripe (added in session 9, not week 1)

Skip until we wire payments.

## Tasks for Giovanni before next session

- [ ] Create Supabase project (EU region) and run the migration
- [ ] Create Railway service and connect GitHub
- [ ] Create PostHog project and copy the public key
- [ ] Fill `.env` locally and confirm `/health` shows `db_configured: true`

## Repo layout

```
concourse/
├── backend/
│   ├── main.py                      # FastAPI app, /health, /, /config.js
│   ├── config.py                    # Pydantic Settings
│   ├── ai/                          # Anthropic calls (added session 4+)
│   ├── auth/                        # signup / login (session 2)
│   ├── db/
│   │   ├── database.py              # SQLAlchemy engine (Supabase pooler)
│   │   └── migrations/
│   │       └── 001_init.sql         # initial schema
│   ├── logic/                       # rule engine (sessions 6+)
│   ├── integrations/                # Stripe, OCR, PostHog server-side (later)
│   ├── models/                      # SQLAlchemy ORM
│   └── static/
│       └── index.html               # landing page with PostHog + UTM capture
├── requirements.txt
├── Procfile
├── .env.example
└── README.md
```

## What ships when

| Session | Goal | End state |
|---------|------|-----------|
| 1 | Foundations (this session) | Repo on GitHub, deployed to Railway, PostHog on landing page, UTM captured, schema migrated |
| 2 | Auth + intake | Supabase Auth, intake form, profile row persisted |
| 3 | Diagnostic instrument v0 | 5–7 item adaptive verbal mini-test, scored and stored |
| 4 | Scoring + profile page | Combined score view, CV-fit modifier, profile UI |
| 5+ | Plan generation, daily plan, external logs, replan engine, Stripe, pilot | … |
