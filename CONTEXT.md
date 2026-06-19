# Concourse — Project Context & Conversation Log
_EPSO Adaptive Preparation Planner · context captured June 18, 2026_

> Working name: **Concourse** (renameable). Alternatives considered: Cadence, Praxis, Kompass, Laureate.
> Companion file: `EPSO-Planner-MVP-Build-Plan.md` (the detailed build plan) lives in this same folder.

---

## 1. The idea (from the original blueprint)

An **AI-orchestrated study planner** for candidates preparing for EPSO and similar EU recruitment competitions (initial focus: AD5 generalists, AD7 ICT/specialists; an AD5/AD7 wave is expected autumn 2026).

Candidates today prepare in a **fragmented, unstructured** way — juggling question-bank platforms (EUTraining, ORSEU, EPSOready, EPSO Genius, EuropApp), books, spreadsheets, and ad-hoc LLM chats — with no single system tying their CV, target competition, time constraints, and performance into a coherent plan. Tech-savvy candidates build private LLM workflows and out-compete less AI-literate peers.

**Positioning:** not a question bank. A **content-agnostic orchestration layer** that tells candidates what to do each day, points them at content they already pay for elsewhere, and adapts weekly to their performance. Complementary to existing providers (potential referral/revenue-share partners), not competitive.

**Core loop:** intake → scoring → master plan → daily plans → logging → weekly re-planning.

**Scoring matrix (8 dimensions, 1–5 each):** verbal / numerical / abstract reasoning, EU knowledge, digital skills, test strategy, prep habits, CV–vacancy fit. A rule-based engine converts scores + weights + time-to-exam + weekly hours + energy into the plans.

**Economics (from blueprint):** LLM cost ~1–2 €/user/3mo; total product cost ~5–8 € (use 10 € as conservative). Subscription 20–25 €/mo. CAC scenarios 15 / 30 / 50 €. Margin stays positive even in the pessimistic CAC case but thin.

---

## 2. Critique — the 5 risks I flagged

1. **Manual logging won't happen.** The whole adaptive loop depends on users faithfully logging external results. They won't. This is the #1 retention killer and the blueprint treated it as a one-liner. *(High confidence.)*
2. **CV–vacancy fit is over-weighted.** Made the top strategy driver, but its *daily actionability* is thin — once the competition is chosen, "your fit is weak" produces anxiety, not study tasks. *(Moderate.)*
3. **LLM CV-scoring is noisy and unvalidated.** Scoring reasoning skills 1–5 from a CV has no ground truth; wrong baselines poison every downstream plan. This is the real core and was the least-specified part. *(High.)*
4. **The September deadline is driving scope** backward from the monetization wave, pressuring a ship before scoring is trustworthy and logging is proven.
5. **Defensibility is thin.** The "data moat" only exists if logging works (see #1). The orchestration layer is copyable by incumbents who already own content + users. Real defense = vertical EPSO depth + first-mover.

---

## 3. Reframed hypothesis (what we're actually testing)

User's stated main hypotheses, in priority order:
1. **People will pay** for the service.
2. **CAC is acceptable** relative to margin.

Key correction: CAC and willingness-to-pay do **not** require a perfect adaptive loop — a shell could fake them. The real risk is a **false positive**: pay once, churn week two, misread copywriting as PMF. So the signal that matters is **durable use**, and we instrument three things:
- **Conversion**: trial-start → paid, by channel.
- **Durability**: week-3 active retention (the true PMF tell).
- **CAC**: cost per trial-start and per paid user, by channel.

User explicitly rejected the scrappy Notion/concierge approach — wants a **real, functioning MVP** built and tested properly.

---

## 4. Decisions made this session

- **Pay test:** Free trial → paid conversion. *I pushed back* (it delays the pay signal and muddies CAC); user kept it. Mitigation adopted: **7-day trial, card required up front** to filter tire-kickers, pull the pay decision forward, and keep a clean CAC funnel. Single plan at ~24.99 €/mo; no 3-month prepay bundle yet.
- **Build role:** I scope + we **vibe-code it together** here, step by step, user driving.
- **Logging:** user asked for 3 options (below); recommendation is to compose them in layers.

### The 3 logging solutions
- **A — In-app weekly micro-diagnostic (the spine, recommended core).** A ~10-min adaptive skill-check the product runs weekly. *This is* the performance data; doubles as baseline scoring (fixes Risk 3) and the data moat (fixes Risk 5). Needs ~15–25 calibrated items per reasoning skill + a short EU quiz. Reliable, no dependence on user discipline.
- **B — Screenshot/paste → LLM parse (convenience layer).** User drops a screenshot of their EUTraining/ORSEU results; LLM extracts skill + score. Low friction, cheap, leverages existing behavior. Parsing reliability varies; still needs the user to remember.
- **C — One-tap adherence confirmation (habit layer).** Daily 👍/partial/✗ on the day's plan + optional quick numeric entry. Near-zero friction, builds the daily-open habit. Adherence ≠ performance.
- **Rule:** A is load-bearing; C is the cheap daily hook; B only if time allows. Never let the loop *depend* on B or C.

### How the architecture fixes the 5 risks
The core decision — **the product generates its own performance data (Solution A) instead of relying on the user to log it** — fixes Risks 1, 3, and 5 at once. CV-fit (Risk 2) is demoted to a one-time intake **strategy modifier** (not a daily driver). The build sequence (Risk 4) front-loads the credibility-critical diagnostics + scoring + plan generation and defers polish.

---

## 5. MVP scope, stack, sequence (summary — full detail in build-plan file)

**Must-have:** auth + intake (competition, CV, constraints) · diagnostic engine (adaptive verbal/numerical/abstract + EU quiz) · scoring (measured reasoning + LLM soft dimensions + CV-fit modifier) + profile viz · master plan · on-demand daily plan · logging layers A+C · weekly re-planning · Stripe trial + paywall + per-channel analytics.

**Out of scope:** integrated question bank, podcast/NotebookLM, general chatbot, gamification/social, 3-month prepay tier, multi-plan pricing.

**Stack:** Next.js + Tailwind · Next API routes (or thin FastAPI later) · Supabase (Postgres + auth + CV storage, EU region) · Stripe · mid-tier LLM with JSON-schema-validated calls · PostHog (funnels/retention/UTM) · Vercel + Supabase hosting.

**~12-week sequence to mid-Sept:** wk1–2 auth/intake/schema + analytics wiring → wk3–4 diagnostic engine + item set → wk5 scoring + profile → wk6–7 plan generation → wk8 logging A+C + re-planning → wk9 Stripe + funnel → wk10–11 closed pilot (10–30 users, watch wk-3 retention) → wk12 public launch for AD5/AD7 wave + turn on paid channels.

**Kill criteria:** trial→paid < ~8–10% (card-up-front) = pricing/value problem · week-3 active < ~30% of paid = hollow product · blended CAC > 3-mo contribution margin with no path down = channel economics fail.

---

## 6. Open items / next steps

- Finalize the product name (rename folder if not "Concourse").
- Confirm card-up-front for the trial (the plan depends on it).
- Source/author the diagnostic item set (~15–25 per reasoning skill + EU quiz) — this is the credibility bottleneck.
- Decide which acquisition channels to instrument first (EPSO communities, LinkedIn, coach partnerships).
- Begin build at week 1: auth + intake + Supabase schema + PostHog/UTM wiring.
