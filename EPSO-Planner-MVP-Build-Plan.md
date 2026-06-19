# EPSO Adaptive Planner — MVP Build Plan
_Drafted June 18, 2026 · target launch: first half September 2026 (~12 weeks)_

## 0. What we are actually testing

Stated hypotheses, in priority order:

1. **People will pay** for an AI-orchestrated EPSO planner.
2. **CAC is acceptable** relative to contribution margin.

The trap: a free trial + a pretty shell can produce a *false positive* on (1) — people convert once, churn in week two, and you misread copywriting as product-market fit. The signal that survives a real ad budget is **durable use**, not a single payment. So we instrument for three things, not one:

- **Conversion**: trial-start → paid, by channel.
- **Durability**: still active in week 3 (this is the real PMF tell).
- **CAC**: cost per trial-start and cost per paid, by channel.

**Kill criteria (decide these now, honor them):**
- Trial→paid < ~8–10% with card-up-front → pricing or value problem.
- Week-3 active < ~30% of paid → product is hollow; conversion was a mirage.
- Blended CAC > 3-month contribution margin (~50–65 € at 25 €/mo) with no path down → channel economics don't work.

## 1. Payment & trial design (the test rig)

- **7-day free trial, card required at signup.** Non-negotiable for a clean CAC read. Card-up-front pulls the pay decision forward and filters tire-kickers.
- Stripe. Single plan to start: **24.99 €/mo**, positioned between low-cost question packs and premium coaching. Do not offer the 3-month-prepay bundle yet — it muddies the monthly conversion signal.
- Trial gives full product. The conversion event is the auto-charge on day 7.
- **Per-channel tracking from day one** (UTM → signup → trial-start → paid). Without this you cannot answer the CAC question, which is half the point.

## 2. Product architecture that fixes the 5 risks

The elegant move: **make the product generate its own performance data instead of depending on the user to log it.** This single decision fixes three of the five risks at once.

**Risk 1 — manual logging won't happen.** Solved by the in-app weekly micro-diagnostic (see §3, Solution A) as the *spine* of performance data. External logging becomes supplementary, not load-bearing.

**Risk 2 — CV-fit weighted too high.** Demote it. CV-fit produces *one* output at intake: a strategy modifier (e.g. "fit is weak → +20% emphasis on reasoning, flag alternative competitions") and a go/no-go note. It is **not** a daily allocation driver. Daily allocation is driven by measured skill gaps.

**Risk 3 — LLM CV-scoring is noisy / unvalidated.** Do not score reasoning skills from the CV. Score them with **short in-app adaptive diagnostics** at intake (real items, real % correct, real timing). The LLM scores only the soft dimensions where it's defensible (habits, strategy, EU-knowledge breadth from a short quiz) and *narrates* the plan. Numbers come from measurement, not inference.

**Risk 4 — September deadline pressure.** Sequenced build (§6) front-loads the credibility-critical pieces (diagnostics, scoring, plan generation) and defers polish. Re-planning ships before the soft features.

**Risk 5 — thin defensibility.** The data moat is real *only because* performance data is captured in-product (Risk 1's fix). Scattered external logs can't be a moat; a growing per-user record of measured skill trajectories can.

## 3. The logging problem — 3 solutions

You asked for three. They are not mutually exclusive; the recommendation is to compose them in layers.

### Solution A — In-app weekly micro-diagnostic *(the spine — recommended core)*
A short (~10 min) adaptive skill-check the product administers weekly. This *is* the performance data that feeds re-planning, and it doubles as baseline scoring (fixes Risk 3) and the data moat (fixes Risk 5).
- **Pros:** reliable, calibrated, zero dependence on user discipline, solves three risks simultaneously, content-light (~15–25 calibrated items per reasoning skill is enough to baseline + track).
- **Cons:** you must author/source and roughly calibrate items; some users may resent "more tests" — frame it as the thing that makes the plan smart.

### Solution B — Screenshot / paste → LLM parse *(the convenience layer)*
User drops a screenshot or pastes their EUTraining/ORSEU/EPSOready results screen; the LLM extracts skill + score + count. Captures the practice they already do, cheaply (your LLM cost is ~1–2 €/user/3mo).
- **Pros:** very low friction, leverages existing behavior, no manual typing.
- **Cons:** parsing reliability varies by each platform's UI; still requires the user to *remember*; no ground-truth control over the items.

### Solution C — One-tap adherence confirmation *(the habit layer)*
A daily "Did you do today's plan?" → 👍 / partial / ✗, plus optional quick numeric entry. Captures *adherence* even when no scores exist.
- **Pros:** near-zero friction, builds the daily-open habit, gives the planner something to adapt to even from non-test-takers.
- **Cons:** adherence ≠ performance; thin signal for re-planning quality on its own.

**Recommendation:** A is the load-bearing spine (build first), C is the daily habit hook (cheap, build second), B is a convenience upgrade (build only if time allows before launch). Never let the adaptive loop *depend* on B or C.

## 4. MVP feature scope

Must-have for launch:
1. Auth + onboarding/intake (competition, CV upload, constraints: weeks-to-exam, hrs/week, energy pattern).
2. **Diagnostic engine** — adaptive micro-tests for verbal/numerical/abstract + short EU-knowledge quiz.
3. Scoring: measured numbers (reasoning) + LLM-scored soft dimensions + CV-fit strategy modifier → profile visualization.
4. Master plan generation (rule-based: scores × weights × time-to-exam × weekly hours → per-skill weekly allocation).
5. On-demand daily plan (time + energy → today's session).
6. Logging layers A (weekly diagnostic) + C (one-tap adherence).
7. Weekly automated re-planning from logged + diagnostic data.
8. Stripe trial + paywall + per-channel analytics.

Explicitly out of scope for MVP: integrated question bank, podcast/NotebookLM, general chatbot, gamification, social, the 3-month prepay tier, multi-plan pricing.

## 5. Tech stack (for vibe-coding together)

- **Front-end:** Next.js (App Router) + Tailwind. Single codebase, fast to iterate.
- **Back-end:** Next.js API routes or a thin FastAPI service — start with API routes to avoid a second deploy target.
- **DB + auth:** Supabase (Postgres + auth + storage for CV files in one). Fastest path; GDPR-friendly EU region.
- **Payments:** Stripe (Checkout + Billing for trial logic).
- **LLM:** a mid-tier model (cost ~1–2 €/user/3mo confirmed). All calls wrapped in typed functions with JSON-schema validation + logging.
- **Analytics:** PostHog (funnels, retention cohorts, UTM capture) — this is what answers the CAC/durability questions.
- **Hosting:** Vercel + Supabase. Minimal ops.

## 6. Build sequence (12 weeks to mid-September)

- **Weeks 1–2:** Auth, intake, CV upload, Supabase schema. UTM + PostHog wiring from the very start.
- **Weeks 3–4:** Diagnostic engine + item set (the credibility core). Get ~15–25 items/reasoning skill + EU quiz.
- **Week 5:** Scoring + profile visualization. LLM scoring functions for soft dimensions.
- **Weeks 6–7:** Master plan + daily plan generation (rule engine). CV-fit as strategy modifier only.
- **Week 8:** Logging layers A + C; weekly re-planning logic.
- **Week 9:** Stripe trial + paywall; conversion funnel instrumentation.
- **Weeks 10–11:** Closed pilot (10–30 users), watch week-3 retention, fix the biggest drop-off.
- **Week 12:** Public launch for the AD5/AD7 wave; turn on paid acquisition channels and read CAC.

## 7. What success looks like by launch

You can answer, with real numbers: (a) trial→paid conversion with card-up-front, (b) week-3 active retention of paying users, (c) CAC by channel. If those three are healthy, you've validated the actual business — not just that a plan can be generated.
