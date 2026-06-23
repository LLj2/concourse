# CLAUDE.md — guardrails for any Claude Code instance on this repo

This file is auto-loaded into every Claude Code session in this project. Keep it
short and high-signal. It encodes the team's working rules so every instance (and
every teammate's instance) behaves consistently. When a rule here changes, edit
this file — it's the shared, version-controlled memory.

## What this is
**Concourse** — an AI-orchestrated EPSO exam-prep planner. Flagship feature:
**Compass**, the adaptive practice engine. Read `OVERVIEW.md` once for full context.

## Docs & status — the single-source rule
- **`ROADMAP.md` is the ONLY place status/checkboxes live** (done/next). Other docs
  explain the *how*, never track done/to-do. Don't duplicate status — that's how
  docs drifted on 2026-06-22.
- Doc map: `ROADMAP.md` (product status + sequence) · `COMPASS_ROADMAP.md` (the
  single Compass build doc) · `COGNITIVE_DIMENSIONS.md` (schema/data) · `OVERVIEW.md`
  (onboarding narrative, points to ROADMAP for status) · `HANDOFF.md`/`CONTEXT.md`
  (stack + original analysis). `PRACTICE_FEATURE_PLAN.md` is **superseded** by
  `COMPASS_ROADMAP.md` — don't edit it.
- After merging real work, tick the matching box in `ROADMAP.md`.

## Stack — no new toolchain
Python 3 / FastAPI + uvicorn · SQLAlchemy 2.0 (sync) · raw SQL migrations in
`backend/db/migrations/` · Supabase Postgres (EU) + Auth · Anthropic **Haiku 4.5**
via `backend/ai/client.py` (forced JSON-schema tool calls) · hand-rolled HTML/CSS/JS
in `backend/static/` (no build step) · Railway auto-deploy on push to `main`.
Mirror `dora-mvp`/`quizventure` patterns; don't introduce new frameworks.

## Database — dev == prod right now
- There is **one Supabase project**, used as both dev and prod (no real users yet).
- **A fresh prod Supabase is a MANDATORY gate before the closed pilot** (ROADMAP §6,
  issue #3). Until then, the current DB is dev/staging.
- **Coordinate before running a migration** on the shared DB (ping the team) and pick
  a window when no one is testing. Migrations must be **idempotent + transactional**.

## Compass code is sealed
All Compass code lives under **`backend/compass/`** and is exposed at `/api/compass/*`.
Do **not** modify `backend/logic/`, `backend/ai/client.py`, or `backend/auth/` from
Compass work. See `backend/compass/README.md`.

## Scraper ethics (`tools/epso_benchmark/`)
- Output under `data/` is **internal calibration only**, **git-ignored**, and **must
  not be served to users** (EPSO samples are "not training materials").
- **Honour `robots.txt`** and site opt-outs. EuTraining is intentionally **disabled**
  (robots disallows AI bots + `ai-train=no`); don't bypass it by spoofing a browser UA.
- Be polite: single-threaded, self-identifying User-Agent, backoff. `--delay` ≥ 1.5s.

## Cost discipline
Dev and prod start on Haiku 4.5. Bank-first generation; `COMPASS_DAILY_GEN_CAP`
guards runaway loops. An Anthropic billing alert is set at $20/month — keep an eye on it.

## Secrets & git
- Never commit secrets. `.env`, `*SECRETS*.md`, `HANDOVER_*.md`, and scraper `data/`
  are git-ignored — keep it that way.
- Commit/push only when asked. The team uses feature branches (`giovanni/*`,
  `leonardo/*`); `main` auto-deploys to Railway, so don't push half-done work to it.
