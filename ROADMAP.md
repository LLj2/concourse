# Concourse — Roadmap

> **Shared, trackable plan.** Tick boxes as work lands. Keep this file honest — it is the single source of truth for "what's done / what's next."
> **Last updated:** 2026-06-20
> **Target launch:** first half of September 2026 (~12 weeks from the 2026-06-18 plan).
> **Sources:** `CONTEXT.md`, `EPSO-Planner-MVP-Build-Plan.md`, `HANDOFF.md`. This roadmap does not invent scope beyond those.

---

## 1. What we're testing (don't lose sight of this)

Two hypotheses, in priority order:
1. **People will pay** for an AI-orchestrated EPSO planner.
2. **CAC is acceptable** relative to contribution margin.

The trap is a **false positive**: people convert once, churn in week two, and we misread copywriting as product-market fit. So we instrument three things, not one:
- **Conversion** — trial-start → paid, by channel.
- **Durability** — still active in **week 3** (the real PMF tell).
- **CAC** — cost per trial-start and per paid user, by channel.

**Kill criteria (decided up front — honor them):**
- Trial→paid `< ~8–10%` with card-up-front → pricing or value problem.
- Week-3 active `< ~30%` of paid → product is hollow; conversion was a mirage.
- Blended CAC `>` 3-month contribution margin (~50–65 € at ~25 €/mo) with no path down → channel economics don't work.

**What success looks like at launch:** we can answer with real numbers (a) trial→paid with card-up-front, (b) week-3 active retention of paying users, (c) CAC by channel.

---

## 2. Product in one line

A **content-agnostic orchestration layer** (not a question bank) for EPSO candidates (initial focus: AD5 generalists, AD7 ICT/specialists; AD5/AD7 wave expected autumn 2026). It **generates its own performance data** via short in-product adaptive diagnostics instead of depending on users to log external practice, and **re-plans** whenever new data lands.

**Core loop:** intake → scoring → master plan → daily plans → logging → weekly re-planning.

The architectural keystone (fixes Risks 1, 3, 5 at once): **the product measures skill in-app rather than inferring it from a CV or relying on manual logging.** CV-fit is demoted to a one-time intake *strategy modifier*, never a daily allocation driver.

---

## 3. Status at a glance

| Phase | Scope | Status |
|---|---|---|
| Session 1 | Foundations: FastAPI, Supabase pooler, schema, landing + PostHog/UTM | ✅ Done |
| Session 2 | Auth (magic-link), intake form, `/me` | ✅ Done |
| Session 3 | Diagnostic engine v0 — adaptive verbal mini-test | ✅ Done & deployed (2026-06-20) |
| Session 4 | Scoring + profile rendering | ⏭️ **Next** |
| Sessions 5–8 | Plan generation, daily plan, logging A+C, weekly re-plan | ⬜ Not started |
| Session 9 | Stripe trial + paywall + funnel instrumentation | ⬜ Not started |
| Pilot | Closed pilot (10–30 users), watch week-3 retention | ⬜ Not started |
| Launch | Public launch for AD5/AD7 wave, turn on paid channels | ⬜ Not started |

---

## 4. Done

### Session 1 — Foundations ✅
- FastAPI skeleton, Supabase Postgres (EU `eu-west-1`) via transaction pooler (`prepare_threshold=None`).
- Schema migrated (`001_init.sql`): optional intake calibration, `external_logs` first-class, event-driven replan (`plans.trigger_kind`), UTM on `users`, multi-tenant by `user_id`.
- Landing page with PostHog snippet + first-touch UTM capture.

### Session 2 — Auth + intake ✅
- Supabase magic-link signup/callback, signed 30-day session cookie (`itsdangerous`), `get_current_user()`.
- Short intake form (optional calibration Likerts + prior-experience flags), `/me` profile page, `/api/intake`, `/api/me`.

### Session 3 — Diagnostic engine v0 ✅ (merged 2026-06-20)
- 8 calibrated verbal items (`002_seed_verbal_items.sql`, difficulty 1–3), idempotent seed.
- Adaptive picker (`backend/logic/diagnostic.py`): start d2, ±1 clamped [1,3], no in-session repeats, 5 items, difficulty-weighted score.
- `POST /api/diagnostic/start|answer`, `/diagnostic` UI with immediate feedback + explanations; `/me` shows CTA + latest scores.
- Logs `events.diagnostic_completed` for the future replan trigger.

### Infra hardening this session ✅
- Fixed magic-link redirect (GoTrue `redirect_to` query param) — links now reach `/auth/callback`.
- Fixed session cookie never being sent on login (return plain dict, not a second `JSONResponse`).
- Built 6-digit OTP code login path (`/api/auth/verify-otp`) — **dormant until custom SMTP is set up** (Supabase locks template editing behind SMTP). Signup UI is link-primary with code as fallback.
- Fixed `/api/me` 500 on UUID/datetime serialization (shipped inside Session 3).
- Documented the lightweight branch-and-merge workflow (`HANDOFF.md §9`) for the MVP phase.

---

## 5. Next — remaining MVP build

Sequencing follows `EPSO-Planner-MVP-Build-Plan.md §6`. The credibility-critical pieces (diagnostics → scoring → plan generation) are front-loaded; polish is deferred.

### Session 4 — Scoring + profile  ⏭️ NEXT
- [ ] Combine measured reasoning score + Likert self-scores + CV-fit modifier into a profile view.
- [ ] First **LLM call** (Anthropic Haiku 4.5) for soft dimensions, wrapped in a typed function with **JSON-schema validation + logging** (per build plan §5 and Giovanni's PR note).
- [ ] CV-fit = one-time intake **strategy modifier** + go/no-go note only (Risk 2 mitigation). Not a daily driver.
- [ ] Profile visualization on `/me`.

### Diagnostic breadth (build plan §4.2 — beyond verbal v0)
- [ ] Numerical reasoning items + harness.
- [ ] Abstract reasoning items + harness.
- [ ] Short EU-knowledge quiz.
- [ ] Reach ~15–25 calibrated items **per reasoning skill** for steady state (8 verbal shipped is enough to demo, not to run).
- [ ] **Decision: source vs. author items** (licensed = fast but costs/constrains; authored = free but slow). This is the credibility bottleneck — see Open Decisions.

### Sessions 6–7 — Plan generation
- [ ] Master plan: rule engine over scores × weights × time-to-exam × weekly hours × energy → per-skill weekly allocation (minutes/week).
- [ ] On-demand daily plan: time + energy → today's session.
- [ ] LLM-narrated rationale (`rationale_md`) — "plan updated because X".

### Session 8 — Logging layers + re-planning
- [ ] **Layer A** (the spine): weekly in-app micro-diagnostic feeding re-planning. (Session 3 is the first instance of this.)
- [ ] **Layer C** (habit hook): one-tap daily adherence (👍 / partial / ✗ + optional numeric).
- [ ] Weekly automated **re-planning** from diagnostic + adherence data (event-driven via `plans.trigger_kind`).
- [ ] **Layer B** (convenience, only if time allows): screenshot/paste → LLM parse of EUTraining/ORSEU/EPSOready results into `external_logs`. **Never let the loop depend on B or C.**

### Session 9 — Payments + funnel
- [ ] Stripe: single plan **24.99 €/mo**, **7-day trial, card required up front**. No 3-month prepay bundle yet (muddies the monthly signal).
- [ ] Paywall; conversion event = the day-7 auto-charge.
- [ ] Per-channel funnel instrumentation: UTM → signup → trial-start → paid (PostHog).

### Weeks 10–11 — Closed pilot
- [ ] Recruit 10–30 users.
- [ ] Watch **week-3 retention**; fix the single biggest drop-off.

### Week 12 — Public launch
- [ ] Launch for the AD5/AD7 wave.
- [ ] Turn on paid acquisition channels; read CAC by channel.

---

## 6. Pre-launch hardening (must clear before real users)

Tracked so they don't get lost behind feature work:
- [ ] **Custom SMTP** (e.g. Resend) → kills the ~2/hour built-in email rate limit, makes email production-grade, and **activates the 6-digit OTP code path** (template editing requires SMTP). Fixes the Gmail link-scanner problem for real users.
- [ ] **Separate dev/staging Supabase from production** — currently a single shared DB; test data mixes with real. → **issue #3**.
- [ ] **Diagnostic engine hardening** (validate answered item, 4xx-not-500 on bad input, calibration skew) → **issue #2**.
- [ ] **Rotate secrets** exposed in cleartext during handover: `SESSION_SECRET`, DB password, anon key, Anthropic key, and the `service_role` key (`HANDOVER_SECRETS.md §7`). Delete `HANDOVER_SECRETS.md` once stored in password managers.
- [ ] **Clean production** of all test users/rows before the first real signup (done once on 2026-06-20; redo right before launch).
- [ ] **GDPR**: privacy policy + lawful basis, account-deletion / data-export (erasure) flow, analytics consent, signed DPAs with Supabase **and** Anthropic. (Foundation is EU-region; paperwork + erasure flow still owed.)
- [ ] **Revisit the dev workflow** — bring back PRs + at least one review (4 eyes), likely branch protection on `main` (`HANDOFF.md §9` notes this is temporary).

---

## 7. Open decisions (recap from CONTEXT.md / HANDOFF.md)

- [ ] **Source vs. author diagnostic items** — the credibility bottleneck. Stefano flagged EUTraining-style realism is hard to match; frame the in-product check as a *measurement instrument*, not a practice tool.
- [ ] **First acquisition channels** to instrument (EPSO communities, LinkedIn, coach partnerships) + the paid-test budget.
- [ ] **Stripe account owner** (revenue flows there) — not yet created.
- [ ] **Product name** — "Concourse" is the working name (renameable).

### Parked (post-MVP, from review comments)
- Pause-at-€5 subscription for users between concorsi → **v1.1**, after launch.
- NotebookLM prompt + content-pack library (`/labs` route) → ~session 7 if time.

### Explicitly out of scope for MVP
Integrated question bank · podcast/NotebookLM · general chatbot · gamification/social · 3-month prepay tier · multi-plan pricing.

---

## 8. The 5 risks and how the build answers them

| # | Risk | Mitigation in the build |
|---|---|---|
| 1 | Manual logging won't happen | In-app weekly micro-diagnostic (Layer A) is the spine; external logging is supplementary |
| 2 | CV-fit over-weighted | Demoted to a one-time intake strategy modifier + go/no-go; not a daily driver |
| 3 | LLM CV-scoring is noisy | Reasoning measured by adaptive diagnostics (real % + timing); LLM only scores defensible soft dimensions + narrates |
| 4 | September deadline pressure | Sequence front-loads diagnostics/scoring/plan; polish deferred |
| 5 | Thin defensibility | Data moat is real *because* performance data is captured in-product (depends on Risk 1's fix) |

---

## 9. Stack note — plan vs. reality

The original `EPSO-Planner-MVP-Build-Plan.md §5` proposed **Next.js + Vercel**. The actual build (per `HANDOFF.md`) deliberately mirrors the team's `dora-mvp` / `quizventure` pattern instead, to avoid a new toolchain:

- **Python 3 / FastAPI + uvicorn**, SQLAlchemy 2.0 (sync), raw SQL migrations.
- **Supabase** Postgres (EU) + Auth; **Anthropic** Haiku 4.5 (`claude-haiku-4-5-20251001`).
- **Hand-rolled HTML/CSS/JS** in `backend/static/` (no build step).
- **Railway** auto-deploy on push to `main`.

Product scope, sequence, hypotheses, and kill criteria are unchanged — only the implementation stack differs. Treat this roadmap's stack references as FastAPI/Railway, not Next.js/Vercel.

---

## 10. How to use this file

- Update the status table (§3) and tick boxes (§5–6) as work merges.
- New non-trivial findings → open a GitHub issue and link it here (see #2, #3).
- When the workflow changes (PRs/branch protection before launch), update `HANDOFF.md §9` and the §6 checkbox here.
