# Concourse — Handoff

> **Audience:** Leonardo (new owner) and Stefano (collaborator), picking up a working scaffold from Giovanni.
> **Last updated:** 2026-06-20
> **Stack mirrors:** [`dora-mvp`](https://github.com/giovannifoglietta/dora-mvp) and [`quizventure`](https://github.com/giovannifoglietta/quizventure) — same Python 3 / FastAPI / Supabase pooler / Anthropic SDK / Railway auto-deploy / hand-rolled HTML pattern. No new toolchain.

## 1. The product, in one paragraph

Concourse is an AI-orchestrated study planner for EPSO candidates. The product generates its own performance data (short in-product calibration quizzes) instead of depending on the user to log external practice, and rewrites the plan whenever new data lands (in-product mini-test, parsed external score, daily adherence). Position: a content-agnostic orchestration layer, not a question bank. Pricing: €24.99/mo with a 7-day card-up-front trial. The two hypotheses we are testing are (a) people will pay and (b) CAC is acceptable; the signal that matters is durable use, measured by week-3 retention.

The product context lives in two repo files that should be read first by anyone joining:

- `CONTEXT.md` — the conversation log: blueprint, 5 risks, decisions
- `EPSO-Planner-MVP-Build-Plan.md` — the original 12-week plan
- `Concourse-MVP-Features-and-Action-Plan_2026-06-18.docx` — the version Stefano and Leonardo commented on; the comments are reflected in the code (optional intake, external logs as first-class, event-driven replan trigger)

## 2. Where we are

Two coding sessions in. The repo runs locally and the auth + intake loop is end-to-end testable.

| Session | Goal | Status |
|---|---|---|
| 1 | Foundations: FastAPI skeleton, Supabase pooler, schema, landing page with PostHog + UTM | Done |
| 2 | Auth (Supabase magic-link), short intake form, `/me` profile page | Done; not deployed yet |
| 3 | Diagnostic instrument v0 — 5–7 item adaptive verbal mini-test | Next |
| 4 | Scoring + profile rendering | Next |
| 5–8 | Plan generation, daily plan, external logs, replan engine, Stripe | Sequenced, not started |

## 3. Stack and key choices

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.13 (3.9 locally on macOS) | Same as dora and quizventure |
| Web | FastAPI + uvicorn | Async-friendly, no build step |
| ORM | SQLAlchemy 2.0 (sync) | Pragmatic for MVP scale |
| DB | Supabase Postgres, EU region (eu-west-1) | Managed, GDPR-friendly, free tier |
| Auth | Supabase Auth (magic-link OTP) | Zero-password, free SMTP via Supabase |
| AI | Anthropic SDK, Haiku 4.5 (`claude-haiku-4-5-20251001`) | Same key Giovanni uses on dora/quizventure |
| Frontend | Hand-rolled HTML/CSS/JS in `backend/static/` | No build step, fast iteration |
| Hosting | Railway, GitHub-connected, auto-deploy on push to `main` | Same flow as the other two projects |

**Key decisions baked into the schema (see `backend/db/migrations/001_init.sql`):**

1. **Optional intake calibration.** Profile carries self-assessment Likerts (`self_habits_score`, `self_strategy_score`, `self_eu_breadth_score`) and prior-experience flags. The 5-7 item mini-test is offered, not forced. Reflects Stefano + Leo's "1-hour intake = funnel killer" feedback.
2. **External logs are first-class.** `external_logs` table for paste/screenshot from EUTraining/ORSEU. Reflects Stefano's "users will log external results" insight.
3. **Replan is event-driven.** `plans.trigger_kind` records what fired the replan: `intake | manual | diagnostic | external_log | weekly_floor`. Reflects Stefano's "this is the real selling point."
4. **UTM persisted on `users`.** First-touch UTM captured at signup for CAC attribution.
5. **Multi-tenant from day one.** Every table scopes by `user_id`.

## 4. Quick start — running locally

```bash
git clone https://github.com/llj2/concourse.git    # or whichever the new URL is post-transfer
cd concourse
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                # fill in secrets — see §5
uvicorn backend.main:app --reload
```

Browse to:

- `http://localhost:8000/` — landing page
- `http://localhost:8000/health` — should return `{"db_configured": true, "supabase_configured": true}`
- `http://localhost:8000/intake` and `/me` — return 401 unless logged in (correct)

## 5. Environment variables

Get the actual values from Giovanni securely (1Password share, Signal, etc.). **Do not paste them in chat or email.** Ask Giovanni to rotate the DB password and Anthropic key before handing them over.

| Var | Required | Where to get |
|---|---|---|
| `ANTHROPIC_API_KEY` | yes | Anthropic Console (or reuse Giovanni's after rotation) |
| `DATABASE_URL` | yes | Supabase → Project Settings → Database → Transaction pooler → port 6543 |
| `SUPABASE_URL` | yes | Supabase → Project Settings → API → Project URL |
| `SUPABASE_ANON_KEY` | yes | Supabase → Project Settings → API → `anon` `public` |
| `SESSION_SECRET` | yes | Any 32+ random chars: `openssl rand -hex 32` |
| `APP_ENV` | yes | `production` on Railway, `development` locally |
| `PUBLIC_BASE_URL` | yes | `http://localhost:8000` locally; Railway URL in production |
| `POSTHOG_PUBLIC_KEY` | optional | eu.posthog.com, set when analytics matter |
| `POSTHOG_HOST` | optional | `https://eu.posthog.com` |
| `STRIPE_SECRET_KEY` | session 9 | Stripe dashboard |
| `STRIPE_WEBHOOK_SECRET` | session 9 | Stripe dashboard |
| `STRIPE_PRICE_ID` | session 9 | Stripe dashboard |

## 6. Deploy to Railway

Leonardo's account has Pro; Giovanni's is maxed out on free. Deploy under Leonardo's Railway.

1. **railway.com** → New Project → Deploy from GitHub repo → pick the transferred `concourse` repo.
2. Railway autodetects Python and reads the `Procfile`. Service builds and deploys in ~2 min.
3. **Service → Variables → Raw editor** → paste the env block from Giovanni. Set `APP_ENV=production`.
4. **Service → Settings → Networking → Generate Domain.** Copy the URL (looks like `concourse-production-xxxx.up.railway.app`).
5. Set `PUBLIC_BASE_URL` to that Railway URL. Save. Railway redeploys.
6. **In Supabase** → Authentication → URL Configuration:
   - Site URL: the Railway URL (https://...)
   - Redirect URLs: add `https://<railway>/auth/callback` and `https://<railway>/**`
   - Save.

## 7. The repo, file by file

```
concourse/
├── backend/
│   ├── main.py               # FastAPI app: /, /health, /config.js, /intake, /me, /api/intake, /api/me
│   ├── config.py             # Pydantic Settings, .env-driven
│   ├── auth/__init__.py      # Supabase magic-link signup, callback, signed session cookie, get_current_user()
│   ├── db/
│   │   ├── database.py       # SQLAlchemy engine with prepare_threshold=None for Supabase pooler
│   │   └── migrations/001_init.sql   # full initial schema
│   ├── ai/                   # empty — for session 4+
│   ├── logic/                # empty — for sessions 6+ (rule engine)
│   ├── integrations/         # empty — Stripe, OCR, server-side PostHog
│   ├── models/               # empty — SQLAlchemy ORM if/when we move off raw SQL
│   └── static/
│       ├── index.html        # landing page with signup modal, PostHog snippet, UTM capture
│       ├── intake.html       # short intake form (5 sections)
│       └── me.html           # dashboard that reads /api/me
├── requirements.txt
├── Procfile
├── .env.example
├── .gitignore
└── README.md
```

## 8. How auth actually works

1. User clicks "Start trial" on `/`. Modal opens, asks for email.
2. Frontend POSTs `/api/auth/signup` with email + UTM (read from localStorage).
3. Server proxies to Supabase `/auth/v1/otp` with the magic-link redirect = `<PUBLIC_BASE_URL>/auth/callback`. Stashes UTM in a 1-hour signed cookie.
4. User clicks the magic link in the email. Lands on `/auth/callback#access_token=...`.
5. The callback page is plain HTML; client-side JS extracts the fragment, POSTs to `/api/auth/exchange`.
6. Server verifies the access token with Supabase `/auth/v1/user`, upserts a row into our `users` table (carrying UTM), sets a 30-day signed session cookie (`concourse_session` via `itsdangerous`), redirects to `/intake` (or `/me` if profile already exists).
7. Subsequent requests authenticate via `get_current_user()` which decodes the cookie.

## 9. How three of us work the repo with Claude Code

Each engineer runs Claude Code locally in their own clone, on their own branch.

**Setup (one-time, per engineer):**
```bash
git clone <repo>
cd concourse
git config user.name "Your Name"
git config user.email "your@email.com"
```

### Current workflow — MVP phase, before public launch

We are deliberately keeping this **lightweight to move fast**: no pull requests and no required approvals. You work on a branch and merge it into `main` yourself when it's ready. (Branches still matter — they let the three of us work in parallel and keep `main` deployable.)

**Per-feature workflow:**
```bash
# start of a feature
git fetch origin
git checkout main
git pull
git checkout -b leonardo/diagnostic-engine    # or stefano/... or giovanni/...

# work with Claude Code, commit often

# when it's ready, merge it into main yourself and push
git checkout main
git pull
git merge leonardo/diagnostic-engine
git push origin main          # pushing to main auto-deploys to Railway (~2 min)
```

You don't need to memorize the git — just tell Claude *"merge my branch into main and push."*

**Small or urgent changes** — a hotfix, a copy tweak, a config change — can go **straight to `main` without a branch**. Do it with care: a push to `main` is live in ~2 minutes with no second look. If unsure, ask Claude to sanity-check the diff first.

**Reviewing is optional but encouraged for anything non-trivial.** You don't have to read code — point Claude at your branch or diff and ask it to review before you merge.

**Coordinate offline *before* you start.** Since nothing gates a merge now, a quick WhatsApp — "I'm taking diagnostics", "I've got Stripe", "I'm on the item bank" — is what keeps two of us from editing the same files at once. Conflicts are recoverable but waste time.

> ⚠️ **This is temporary, by agreement.** It optimizes for speed during the MVP build. **Before we go live with real users we will revisit this** and bring back a heavier process — pull requests plus at least one review (4 eyes), likely enforced with branch protection on `main`. Until then: branch, merge, ship.

**Tell Claude at the start of each session** which branch you are on and what the goal is. Example: *"I am Leonardo on branch `leonardo/diagnostic-engine`. Today: implement the 5-7 item adaptive harness for verbal reasoning. We have items in the `items` table, skill_id='verbal', difficulty 1-3."*

## 10. What's next — session 3

The diagnostic instrument. ~90 min. Outline:

1. Author or source 8 calibrated verbal-reasoning items, insert into `items` table (difficulty 1-3 mix).
2. Build `backend/static/diagnostic.html` — adaptive harness: starts at difficulty 2, +1 on correct, -1 on incorrect, 5-7 items total.
3. Build `POST /api/diagnostic/start` and `POST /api/diagnostic/answer` endpoints.
4. Persist responses to `item_responses`, finalize a session score (0-100, percent correct weighted by difficulty).
5. Show the score on a "diagnostic complete" page, then redirect to `/me` with the new score visible.

Critical credibility bottleneck: **item authoring**. We need 15-25 calibrated items per skill at steady state, but 8 verbal items are enough to ship session 3. Stefano flagged that EUTraining-style realism is hard to match — frame the in-product check as a *measurement instrument*, not a practice tool. Practice happens on EUTraining; measurement happens here.

## 11. Open product items (recap from comments)

These came from Stefano's and Leonardo's review of the v1 plan and are not yet built:

1. **Pause-at-€5 subscription** for users between concorsi (Stefano + Leonardo). Parked as v1.1, after MVP launch.
2. **NotebookLM prompt + content pack library** (Stefano). Static content + a `/labs` route. Targeted for around session 7.
3. **Decision needed: source vs. author the diagnostic items.** Sourcing licensed EPSO items is fast but costs and constrains; authoring is free but slow.
4. **First acquisition channels** to instrument (EPSO communities, LinkedIn, coach partnerships) and the paid-test budget.

## 12. Contact and decision log

- `CONTEXT.md` — original blueprint and risk analysis
- `EPSO-Planner-MVP-Build-Plan.md` — the 12-week plan
- `Concourse-MVP-Features-and-Action-Plan_2026-06-18.docx` — the doc Stefano + Leonardo commented on
- This file — the engineering handoff

When in doubt about a design choice, run `git log -p <file>` to see how it evolved. Commits explain *why*, not just *what*.

---

Welcome to the team.
