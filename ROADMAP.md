# Concourse — Roadmap

> **Shared, trackable plan.** Tick boxes as work lands. Keep this file honest — it is the single source of truth for "what's done / what's next."
> **Last updated:** 2026-06-25 (planning call re-prioritised toward the foundation flow — see §4.6)
> **Target launch:** first half of September 2026 (~12 weeks from the 2026-06-18 plan).
> **Sources:** `CONTEXT.md`, `EPSO-Planner-MVP-Build-Plan.md`, `HANDOFF.md`, `OVERVIEW.md`, `COGNITIVE_DIMENSIONS.md`, `COMPASS_ROADMAP.md`. This roadmap does not invent scope beyond those.

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
| Session 4 | Scoring + profile + first JSON-schema-validated LLM call | ✅ Done (2026-06-20) |
| Sessions 6–7 | Plan generation (master + daily rule engine) | ✅ Done (2026-06-20) |
| Session 8 | Logging layer C (adherence) + event-driven replan | ✅ Done (2026-06-20) |
| **Compass — flagship feature** | **Adaptive practice engine: dimension-tagged items, pattern detection, self-correcting schema** | 🟡 **In flight — M1 done** (commits 1–2 merged 2026-06-22); M2–M3 next. See §4.5 |
| Diagnostic breadth | Numerical/abstract/EU item banks | 🟡 Replaced by Compass — generation pipeline produces them on demand |
| Session 9 | Stripe trial + paywall + funnel instrumentation | ⛔ Blocked — Stripe account/owner (#4); deferred until Compass v1 ships |
| Layer B | Screenshot/paste → LLM parse | ❌ Dropped — Compass platform-native testing is the moat instead |
| Pilot | Closed pilot (10–30 users) on Compass, watch week-3 retention | ⬜ Not started — gated on Compass v1 |
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

## 4.5. Compass — flagship feature rollout 🟡 IN FLIGHT

**Compass is the adaptive practice engine that turns Concourse from a planner into the place EPSO candidates train every day.** It is the strategic moat: every question carries cognitive-dimension metadata; every wrong answer carries a misconception tag; an LLM pass finds patterns no individual question could reveal; the next session is generated to target the user's specific weak patterns; the dimension schema itself self-corrects with real data.

See `COMPASS_ROADMAP.md` for the full 6-commit build plan (phasing, risks, calendar). Sub-list here mirrors that file's milestones — tick boxes as commits land.

**Why this matters strategically.** Other prep platforms know *whether* you got a question right. Compass knows *why*, *what pattern* the wrongness fits, and *what to give you next*. After 50-100 users practice for a few weeks, we own per-user cognitive fingerprints no one else has — and the validation pipeline (commit 6) tells us which dimensions are actually predictive so we improve the schema with data, not opinion.

### Cognitive-dimensions schema ✅
- [x] **Schema v1 designed** — 46 dimensions across numerical / verbal / abstract / FRMCQ / written, plus 17 distractor classes + 3 meta dimensions. Merged from two independent AI deep-research runs (Claude Research + ChatGPT Deep Research), 2026-06-22.
- [x] **Stefano sign-off** on the High/Medium/Low priority assessment (2026-06-22).
- [x] **Word-doc review document** generated and shared (`Concourse-Cognitive-Dimensions-for-Stefano_2026-06-22.docx`).
- [x] **Documented** in `COGNITIVE_DIMENSIONS.md` (full schema) + `OVERVIEW.md` (the channel-onboarding doc) + `COMPASS_ROADMAP.md` (the engineering plan).

### Milestone M1 — Foundation (commits 1–2, ~2.5 sessions)
- [x] **Commit 1** — Schema migration 003 (`f2be545`, 2026-06-22): `items` +6 JSONB/typed cols, new `practice_sessions`, `dimension_mastery`, `pattern_analyses` tables, `item_responses` XOR constraint. Idempotent, single transaction with in-tx assertions. Code sealed under `backend/compass/`.
- [x] **Commit 2** — Item generation pipeline (`e779257`, 2026-06-22): `backend/compass/generate_item.py` + `item_schema.py` + `prompts/verbal.py`, JSON-schema-validated via forced tool-call, 10 real EPSO verbal few-shot anchors. Cost guard `COMPASS_DAILY_GEN_CAP` (shipped default **200 org-global** for dev, not 50/user — revisit per-user in commit 4); generated items land `archived=true` until audited.

### Milestone M2 — Practice loop live (commits 3–4, ~2 sessions)
- [ ] **Commit 3** — Bank-first practice picker + sessions API: 60% focus / 30% weak / 10% control distribution; reads `pattern_analyses.focus_dimensions`; generates only when bank is dry. `POST /api/practice/start|answer|end`.
- [ ] **Commit 4** — Practice UI + insight panel: `/practice` page (skill+length picker, immediate feedback, dimensional end-screen); `/me` "What we have learned about you" panel renders `pattern_analyses.insight_md`; daily plan items deep-link into targeted practice.

### Milestone M3 — The moat (commits 5–6, ~2 sessions)
- [ ] **Commit 5** — Pattern-analysis worker: LLM reads `dimension_mastery` matrix, writes 1-3 plain-English patterns + focus dimensions per user×skill. Triggered on session end (≥20 responses since last analysis). Extends Leonardo's `replan_signal()` to fire on `pattern_updated`.
- [ ] **Commit 6** — Validation pipeline: `/admin/dimensions/health` shows discrimination check (top-quartile vs bottom-quartile accuracy per dimension), predictivity check (mastery at T vs score at T+N), emergent-pattern detection (monthly LLM pass surfacing clusters that don't map to v1 dimensions). This makes the schema self-correcting.

### Open decisions (commit-1 ones now resolved by the shipped code)
- [x] **Few-shot EPSO items** for the verbal generator — resolved: 10 real EPSO AST verbal items extracted from `epso_benchmark_data` live in `backend/compass/few_shot/verbal_epso_anchors.json`. No authoring session needed; Stefano's review shifts to spot-checking generated output.
- [x] **Daily generation cap default** — shipped at `COMPASS_DAILY_GEN_CAP=200` (org-global, dev). Revisit a per-user cap in commit 4 when real users exist.
- [ ] **Practice vs. Calibration positioning on `/me`** — still open; needed for commit 4 (Practice UI). Equal billing (recommended) vs Calibration headline.

### Infra dependencies (Leonardo's track)
- [ ] **Custom SMTP** (Resend) — not blocking Compass build, but needed before pilot in week 4 for reliable magic-link delivery.
- [ ] **Dev/staging Supabase split** (issue #3) — **decided 2026-06-23: not now.** No real users yet, so the current project stays as dev/staging and we cut a fresh **prod** Supabase as a mandatory pre-pilot gate (see §6). Migration 003 therefore just runs on the current DB — only pick a window when no teammate is mid-test (ping on WhatsApp first).

### Calendar target (~4 weeks)
- **Week 1** (2026-06-22 → 2026-06-28): ✅ Commit 1 **and** Commit 2 both shipped 2026-06-22 (ahead of plan — M1 done day 1). Commit 3 next.
- **Week 2**: Commit 2 ships; Commit 3 ships; Commit 4 starts. **End of week 2 = Compass v0.5 (M1+M2 done, practice loop live, no insight layer).**
- **Week 3**: Commit 4 ships; Commit 5 ships. Insight panel renders for real users.
- **Week 4** (target 2026-07-20): Commit 6 ships. **Compass v1 live.**
- **Weeks 5-6**: 10-30 pilot users on Compass, weekly review of `/admin/dimensions/health`.
- **Week 7**: Stefano review on real data → schema v2 plan.

If any week slips: M1+M2 alone (Compass v0.5) is independently sellable. The moat (M3) is the upside, not the floor.

**Re-prioritised 2026-06-25:** the planning call put Compass *behind* the end-to-end foundation flow (§4.6). Compass's practice loop survives as the "reasoning-pattern exercises" half of that flow; M2–M3 continue once the foundation is demoable.

### Cost framing (2026-06-22)
- **Dev runs on Haiku 4.5** (`$1.00/$5.00 per MTok`, 5× cheaper than Opus 4.8). Set `ANTHROPIC_MODEL=claude-haiku-4-5` in dev `.env`.
- **Production starts on Haiku too** — escalate to Sonnet 4.6 (`$3/$15`) only if item-generation quality is unacceptable; reserve Opus 4.8 for tasks that genuinely need it.
- **Bank-first picker** (commit 3) amortizes generation cost as the bank grows — after ~50 users, 90%+ of items are bank-served, free.
- **Per-user daily generation cap** (commit 2, env-configurable) prevents runaway loops.
- **Pattern-analysis caching** (commit 5) uses `cache_control: {type: "ephemeral"}` — cached prompt reads cost ~10% of base rate.
- **Anthropic billing alert** set at $20/month at console.anthropic.com to catch surprises early.

---

## 4.6. Planning call 2026-06-25 — foundation-flow re-prioritisation 🟡 IN FLIGHT

The team worked off `Concourse-Build-Stack-Rank_2026-06-23.docx` and agreed to lead
with the **end-to-end foundation flow** before extending Compass:

**Competition Catalog → CV upload → ~5 intake questions → gap analysis → Master Plan
(free preview) → 🔒 paywall → "Let's Study Now" daily plan + exercises.**

Much of the spine already exists (intake, scoring/gap, master plan, daily plan — §4 &
§5). The genuinely new pieces and decisions:

- [~] **Competition Catalog Table** (NEW top priority) — auto-import EPSO *bandi* data
  (ref, grade, profile, deadline, selection-procedure tests, link to the official
  Notice) for open / in-progress / upcoming competitions; feeds gap analysis + Draft
  plan. **Scraper built 2026-06-25** (`tools/epso_benchmark/catalog_scrape.py`, reuses
  the existing polite Crawler+Robots) — validated live: 7 in-progress competitions
  parsed, AD5-vs-AD7 test mixes differentiated, 7/7 with reference + Notice link;
  `upcoming` (plain-text announcements) still best-effort. **Remaining:** a
  `competitions` table + loader so the app reads it; wire the candidate's chosen
  competition's tests into the Draft plan. *Owner: Leonardo (was Giovanni in the
  minute — Leonardo took the scraper; coordinate with Giovanni so it isn't rebuilt).*
- [~] **CV upload** — Supabase Storage (private `cvs` bucket) + optional LinkedIn /
  portfolio links; mandatory for specialist competitions, optional otherwise. *Owner:
  Leonardo.* **Scaffolded 2026-06-25:** `backend/logic/cv.py`, `POST/GET /api/cv`,
  `/cv` page, `me.html` CTA, migration `004_cv_profile_links.sql` (schema already had
  `cv_storage_path`). **Remaining:** run migration 004 (coordinate on Slack), create
  the `cvs` bucket, set `SUPABASE_SERVICE_ROLE_KEY`, add `python-multipart` to the
  deployed env, then the LLM CV-fit read that writes `profiles.cv_fit_modifier`.
- [ ] **Paywall at the Master Plan** — free preview of the plan for everyone; subscribe
  for full plan / advanced study sessions. Moves payments *earlier* than §5 Session 9
  (which deferred Stripe behind Compass v1). `users` already carries the Stripe columns.
- [ ] **Master Plan as the trust moment** — show it immediately after gap analysis;
  possible rename **Master Plan → "draft plan"**; copy must say it evolves with real
  performance.
- [ ] **~5 intake questions** grounded in the chosen *bando* + CV (refine existing
  intake), balancing direct self-assessment vs pure AI inference.
- [ ] **Exercises: theory vs reasoning-pattern split** — AI-generated theory **plus**
  reasoning-pattern items (numerical/verbal/abstract) that test exam *archetypes*, not a
  full mock. Users can input results (incl. **screenshots**) to refine the internal
  score → this **revives "Layer B"**, previously marked Dropped (§3, Layer B row).
- [ ] **Exercise DB sourcing** — direct scraping of test sites is blocked (Cloudflare /
  `ai-train=no`); buy reliable digital materials or extract from training materials +
  GPT chats; legal prudence + scalability prioritised. *Owner: Stefano.*
- [ ] **AI prompts grounded in test-taking literature**, with weakness analysis driving
  session personalisation.

**Owners & near-term:** Leonardo → foundation layer + Master Plan flow demoable **by Sun
2026-06-28** (+ CV upload); Stefano → exercise sources; Giovanni → catalog script + UI
polish next week. GDPR note: CVs are personal data — reinforces the erasure/DPA items in §6.

---

## 5. Next — remaining MVP build

Sequencing follows `EPSO-Planner-MVP-Build-Plan.md §6`. The credibility-critical pieces (diagnostics → scoring → plan generation) are front-loaded; polish is deferred.

### Session 4 — Scoring + profile  ✅ DONE (2026-06-20)
- [x] Combine measured reasoning score + Likert self-scores + constraints into a profile view (`backend/logic/scoring.py`, `/profile`).
- [x] First **LLM call** (Anthropic Haiku 4.5) via `backend/ai/client.py` `generate_json()` — forced tool call = **JSON-schema-validated** output; narrative cached as a `profile_generated` event.
- [x] Measured numbers stay measured; LLM only narrates (Risk-3 fix). go/no-go read included.
- [~] CV-fit strategy modifier — deferred: no CV upload exists yet. The LLM narrative covers the go/no-go read; CV-fit lands when CV upload is built.
- [x] Profile visualization (`/profile`, linked from `/me`).

### Diagnostic breadth (build plan §4.2 — beyond verbal v0)  🟡 Replaced by Compass
**The "source vs. author items" decision is no longer blocking** — Compass's generation pipeline (§4.5, commit 2) produces dimension-tagged items on demand. The 8 verbal seed items stay; numerical / abstract / EU-knowledge banks grow organically as users practice. Stefano-authored few-shot anchors per skill keep generation quality high.

- [x] Decision resolved: in-platform generation instead of bulk authoring/sourcing.
- [ ] Numerical / abstract / EU-knowledge prompts tuned with Stefano few-shot anchors (part of Compass commit 2).

### Sessions 6–7 — Plan generation  ✅ DONE (2026-06-20)
- [x] Master plan: rule engine over score gaps × soft dims × time-to-exam tilt × weekly hours → per-area weekly minutes (`backend/logic/planning.py`, sums exactly to budget).
- [x] On-demand daily plan: available minutes + energy → today's ordered task list.
- [x] LLM-narrated `rationale_md` (schema-validated, best-effort — never blocks generation).
- [x] Supersede-on-regenerate (exactly one active master plan); `/plan` page.

### Session 8 — Logging layers + re-planning  ✅ DONE (2026-06-20)
- [x] **Layer A** (the spine): weekly in-app micro-diagnostic feeding re-planning (Session 3 is the first instance).
- [x] **Layer C** (habit hook): one-tap daily adherence (done/partial/skipped + optional minutes/note), `backend/logic/adherence.py`.
- [x] **Event-driven re-planning**: `replan_signal()` suggests a refresh on new diagnostic or weekly-floor breach, surfaced in `GET /api/plan`; regenerate is explicit with the right `trigger_kind`.
- [ ] **Automated weekly cron** for re-planning — deferred (infra; current model is event-driven/on-demand).
- [ ] **Layer B** (convenience, only if time allows): screenshot/paste → LLM parse into `external_logs`. **Never let the loop depend on B or C.**

### Session 9 — Payments + funnel
- [ ] Stripe: single plan **24.99 €/mo**, **7-day trial, card required up front**. No 3-month prepay bundle yet (muddies the monthly signal).
- [ ] Paywall; conversion event = the day-7 auto-charge.
- [ ] Per-channel funnel instrumentation: UTM → signup → trial-start → paid (PostHog).

### Weeks 10–11 — Closed pilot
**Gated on Compass v1 (§4.5 M3) shipping. Pilot users practice on Compass, not on a generic prep tool.**
- [ ] Recruit 10–30 users.
- [ ] Watch **week-3 retention**; fix the single biggest drop-off.
- [ ] Weekly review of `/admin/dimensions/health` to validate the cognitive-dimensions schema with real data.

### Week 12 — Public launch
- [ ] Launch for the AD5/AD7 wave.
- [ ] Turn on paid acquisition channels; read CAC by channel.

---

## 6. Pre-launch hardening (must clear before real users)

Tracked so they don't get lost behind feature work:
- [ ] **Custom SMTP** (e.g. Resend) → kills the ~2/hour built-in email rate limit, makes email production-grade, and **activates the 6-digit OTP code path** (template editing requires SMTP). Fixes the Gmail link-scanner problem for real users.
- [ ] **Cut a fresh production Supabase before the first real users — MANDATORY GATE.** Decided 2026-06-23: don't split now (no real users yet), so the current project (`pyxtjeivttswfnyushtw`) stays as **dev/staging**. Before the closed pilot recruits real people (§5 weeks 10–11 — *this*, not public launch, is when metrics must be clean), create a clean **prod** Supabase, run migrations `001→003` on it, point Railway prod at it, and keep the current one as dev. Keeps pilot/launch metrics (conversion, week-3 retention, CAC — §1) uncontaminated by test data. → **issue #3**.
- [ ] **Diagnostic engine hardening** (validate answered item, 4xx-not-500 on bad input, calibration skew) → **issue #2**.
- [ ] **Rotate secrets** exposed in cleartext during handover: `SESSION_SECRET`, DB password, anon key, Anthropic key, and the `service_role` key (`HANDOVER_SECRETS.md §7`). Delete `HANDOVER_SECRETS.md` once stored in password managers.
- [ ] **Clean production** of all test users/rows before the first real signup (done once on 2026-06-20; redo right before launch).
- [ ] **GDPR**: privacy policy + lawful basis, account-deletion / data-export (erasure) flow, analytics consent, signed DPAs with Supabase **and** Anthropic. (Foundation is EU-region; paperwork + erasure flow still owed.)
- [ ] **Revisit the dev workflow** — bring back PRs + at least one review (4 eyes), likely branch protection on `main` (`HANDOFF.md §9` notes this is temporary).

---

## 7. Open decisions (recap from CONTEXT.md / HANDOFF.md)

- [x] **Source vs. author diagnostic items** — resolved 2026-06-22: in-platform generation via Compass (§4.5).
- [x] **LLM model tier for dev** — resolved 2026-06-22: Haiku 4.5 in dev; production starts on Haiku and escalates only if quality demands it.
- [x] **Dev/staging Supabase split timing** — resolved 2026-06-23: don't split now; the current DB stays dev/staging and a fresh prod Supabase is a mandatory pre-pilot gate (§6). Unblocks Compass migration 003, which now just runs on the current DB.
- [ ] **Few-shot EPSO items** for the verbal generator (Stefano) — needed before Compass commit 2.
- [ ] **First acquisition channels** to instrument (EPSO communities, LinkedIn, coach partnerships) + the paid-test budget.
- [ ] **Stripe account owner** (revenue flows there) — not yet created; deferred until Compass v1 ships.
- [ ] **Product name** — "Concourse" is the working name; "Compass" is the flagship feature name (decided 2026-06-22).

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

- **This file is the single source of truth for status.** Done/next and tick boxes live **only here**. The other docs explain the *how*, never the *done/to-do* — don't track status in two places (that's how `COMPASS_ROADMAP.md` and the §4.5 boxes drifted on 2026-06-22).
- Update the status table (§3) and tick boxes (§4.5–§6) as work merges.
- New non-trivial findings → open a GitHub issue and link it here (see #2, #3).
- When the workflow changes (PRs/branch protection before launch), update `HANDOFF.md §9` and the §6 checkbox here.

**Doc map** (what each file is for — keep it to one role each):
- `ROADMAP.md` — product status + sequence (here). The only status tracker.
- `COMPASS_ROADMAP.md` — the single Compass build doc (engineering detail, phasing, risks). `PRACTICE_FEATURE_PLAN.md` is **superseded** by it.
- `COGNITIVE_DIMENSIONS.md` — the dimensions schema (data, not a plan).
- `OVERVIEW.md` — team onboarding narrative; points here for status.
- `HANDOFF.md` / `CONTEXT.md` / `EPSO-Planner-MVP-Build-Plan.md` — stack/handoff + original analysis.
- `CLAUDE.md` — the always-loaded guardrails for any Claude Code instance on this repo.
