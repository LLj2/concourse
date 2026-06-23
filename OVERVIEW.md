# Concourse — Project Overview

> **For anyone joining the team Slack.** Read this once and you have the full context: what we are building, why, where we are, and what comes next.
>
> Last updated: 2026-06-22. Maintained on `main` — if something here is out of date, fix it and commit.

---

## What we are building

Concourse is an AI-orchestrated study planner for candidates preparing for European Personnel Selection Office (EPSO) competitions and CAST recruitment, targeting the AD5/AD7 wave expected in autumn 2026.

The product positions as a **content-agnostic orchestration layer**, not a question bank. It intakes the candidate, measures real reasoning skill in-product through short adaptive tests, generates a master plan and daily plans tailored to the time available, and rewrites the plan whenever new performance data lands.

One-line: **other prep platforms tell you what to study; Concourse figures out what is wrong with your reasoning and trains you on it specifically.**

Pricing target (not yet implemented): €24.99/mo behind a 7-day trial with card-up-front.

---

## Why this is a real product and not a wrapper

Three things sit underneath. If they hold, this works. If any breaks, we kill it.

**Hypothesis 1: people will pay for an AI-orchestrated EPSO planner.** The Italian-and-EU EPSO prep market today is a patchwork of EUTraining, ORSEU, EPSOready, books, and ad-hoc LLM chats. Candidates pay for content but no one ties their CV, target competition, time constraints, and live performance into a coherent daily plan. The bet is that for €25/mo a candidate will pay for that orchestration layer, even if the underlying content lives elsewhere.

**Hypothesis 2: customer acquisition cost is sane.** EPSO communities, LinkedIn, coach partnerships, possibly paid channels. The trial design is built to read CAC cleanly: 7 days, card up front, single plan, no muddy bundles.

**The strategic moat:** the product generates its own performance data through short adaptive in-product tests, rather than relying on the user to paste their EUTraining results. Once enough users practice in-app, we own a per-user record of measured skill trajectories that no incumbent can replicate without building the same instrument. This data moat is what powers the personalization that separates us from "another planner."

**Kill criteria, decided up front, honored later:**
- Trial → paid < ~8-10% with card-up-front → pricing or value problem.
- Week-3 active < ~30% of paid → product is hollow; conversion was a mirage.
- Blended CAC > 3-month contribution margin (~€50-65) with no path down → channel economics don't work.

---

## Where we are right now (2026-06-22)

The product is **live on a Railway URL with end-to-end auth + intake + diagnostic + plan generation working**, and **Compass M1 (commits 1–2: schema + item generation) has landed**. Eight sessions of vibe-coding so far, mostly evenings and weekends.

> **Live status table moved.** To avoid two trackers drifting, the per-phase done/next status now lives **only** in `ROADMAP.md` §3 (the single source of truth). This file keeps the narrative; check the ROADMAP for what's done.

Live URL (test it): https://web-production-71010.up.railway.app

---

## The flagship feature: **Compass**

This is the bet that turns Concourse from "a smart planner" into "the place EPSO candidates train every day." Build sequence designed, scoped to 6 commits over ~2 weeks of evening sessions.

### What Compass is

A platform-native practice engine that:

1. **Tests the student** with generated questions tagged on a structured set of cognitive dimensions (what mental operation does this question test — multi-step calculation, base-referent selection, quantifier scope, etc.)
2. **Records the results** at three levels of detail: stem-level (did you get it right), dimension-level (which underlying skills you exercised), and option-level (which misconception you fell for when you got it wrong)
3. **Finds patterns** through an LLM pass over the user's response history: "this user handles single-step percentages fine but falls apart whenever a calculation chains, regardless of topic"
4. **Tailors the next session** by generating items that target the user's specific weak patterns
5. **Refines its own schema over time** through a built-in validation pipeline that surfaces which dimensions discriminate, which predict outcomes, and which patterns are emerging that we hadn't yet tagged

### Why this is the moat, not a feature

Other prep platforms know **whether** you got a question right. Compass knows **why** you got it wrong, **what pattern** that wrongness fits, and **what to give you next**. After 50-100 users practice for a few weeks, the engine has a per-user "fingerprint" of cognitive strengths and weaknesses that nobody can replicate without building the same instrument and running it on the same volume of candidates. Stefano's intuition that "EUTraining is closer to the real exam" stays true — Compass is positioned as a measurement instrument and skill-builder, not as an exam simulator. They complement.

### The three layers in plain English

**Layer 1 — Tagging.** Every question carries metadata: 8-9 cognitive dimensions per skill (numerical, verbal, abstract reasoning + FRMCQ for specialists + written test), plus ~17 distractor classes (wrong_base, polarity_reversal, obsolete_rule, etc.). The full schema is in `COGNITIVE_DIMENSIONS.md`. Two independent AI deep-research runs (Claude Research + ChatGPT Deep Research) converged on this list; Stefano signed off the priority assessment (High/Medium/Low) on 2026-06-22.

**Layer 2 — Pattern detection.** As a user answers, a `dimension_mastery` table grows: per-user, per-dimension, attempts and correct count. An LLM pass periodically reads this table and writes back 1-3 plain-English patterns ("you consistently underperform on items requiring two-step calculation, citing 31% vs 89% on single-step") plus a list of focus dimensions for the next session.

**Layer 3 — Adaptive generation.** When the user starts practice, the picker reads the focus dimensions, builds a target slot distribution (60% focus areas, 30% other weak areas, 10% control), and tries the bank first. If no bank item matches the target, it calls Anthropic Haiku 4.5 to generate one with the dimension targets declared in a JSON schema. Bad items can be flagged and archived by users. Bank-first design controls cost — after the bank fills up, most items are served instantly with no LLM call.

### Why the schema is v1 not v∞

Some of our cognitive dimensions will predict real outcomes. Others won't. We don't know which yet. **The build includes a validation pipeline that surfaces three things automatically once we have ~100 users:**

- Which dimensions discriminate (top-quartile vs bottom-quartile users score differently on this dimension) — non-discriminating dimensions get killed.
- Which dimensions predict (mastery at time T correlates with score at time T+N) — predictive ones get reinforced.
- Which emergent patterns we missed (clusters of co-occurring errors that don't map to any tag we have) — these become candidate v2 dimensions.

The schema corrects itself with data. We are not freezing v1 and praying.

### Build plan in one screen

| Commit | What | Effort |
|---|---|---|
| 1 | Schema migration 003 — add dimensions JSONB, option_diagnostics JSONB, practice_sessions, dimension_mastery, pattern_analyses tables | ~90 min |
| 2 | Item generation pipeline — Anthropic call with forced JSON schema, prompt tuned with Stefano on real EPSO few-shot examples | 1.5 sessions |
| 3 | Bank-first practice picker + practice sessions API | 1 session |
| 4 | Practice UI + "what we have learned about you" panel on /me | 1 session |
| 5 | Pattern-analysis worker (LLM finds the patterns and writes them back) | 1 session |
| 6 | Validation pipeline — the schema's self-correcting layer | 1 session |

Full plan in `COMPASS_ROADMAP.md`. Live commit status in `ROADMAP.md` §4.5.

---

## The team and how we work

**Giovanni** — product direction, business framing, GDPR/legal, ops with external collaborators (you).
**Leonardo** (GitHub `LLj2`) — repo owner, Railway deployment, primary engineer; shipped sessions 4, 6-7, 8 over the weekend.
**Stefano** (GitHub `Stefog86`) — EPSO domain expert (AD7 background), content design, item-quality audits, cognitive-dimension validation.

**Workflow (per `HANDOFF.md §9`):** during the MVP build phase we are explicitly lightweight — no PRs, no required reviews. Each engineer works on a branch named `<name>/<feature>`, merges to `main` themselves when ready, and Railway auto-deploys. Small or urgent fixes can go straight to `main` with care. Coordinate offline before starting — "I'm taking practice mode, touching diagnostic.py and main.py" — so we don't step on each other. Heavier process (PRs + 4-eyes review + branch protection) returns before public launch.

The reasoning: at three engineers shipping evenings, formal review slows us more than it protects. We will eat occasional conflicts; we will not eat 24-hour PR delays.

---

## Where to find things

- **Repo:** https://github.com/LLj2/concourse
- **Live deploy:** https://web-production-71010.up.railway.app
- **Database:** Supabase project `pyxtjeivttswfnyushtw`, region eu-west-1 (Frankfurt area; GDPR-friendly)
- **Hosting:** Railway, auto-deploys on push to `main` (Leonardo's Pro account)
- **LLM:** Anthropic Haiku 4.5 (`claude-haiku-4-5-20251001`), called via `backend/ai/client.py` with forced JSON schema validation

### Canonical docs in the repo

| File | Read it when |
|---|---|
| `OVERVIEW.md` | First time onboarding (this file) |
| `CONTEXT.md` | Want the conversation log and the original 5-risk analysis |
| `EPSO-Planner-MVP-Build-Plan.md` | Original 12-week MVP plan, pre-pivot to FastAPI |
| `HANDOFF.md` | Onboarding as a new engineer — full stack, env vars, deploy steps |
| `ROADMAP.md` | Single source of truth for done/next, tied to kill criteria |
| `COGNITIVE_DIMENSIONS.md` | The Compass schema — every dimension, type, definition, rationale |
| `COMPASS_ROADMAP.md` | The single Compass build doc (6 commits, phasing, risks) |
| `PRACTICE_FEATURE_PLAN.md` | ⚠️ superseded by `COMPASS_ROADMAP.md` — kept for history only |
| `CLAUDE.md` | Guardrails auto-loaded by any Claude Code instance on this repo |
| `Concourse-MVP-Features-and-Action-Plan_2026-06-18.docx` | Original feature deck reviewed by Stefano and Leonardo |

### Stack at a glance

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.13 (3.9 locally on Mac) | Same as Giovanni's prior projects (dora, quizventure) — zero new toolchain |
| Web | FastAPI + uvicorn | Async-friendly, no build step |
| ORM | SQLAlchemy 2.0 (sync) | Pragmatic at this scale |
| Database | Supabase Postgres EU | Managed, GDPR-friendly, free tier still active |
| Auth | Supabase Auth (magic-link OTP) | Zero-password, free SMTP |
| AI | Anthropic Haiku 4.5 | Cheap, fast, Italian-strong, forced JSON tool calls |
| Frontend | Hand-rolled HTML/CSS/JS in `backend/static/` | No build step — fast iteration |
| Hosting | Railway, GitHub-connected | Auto-deploy on push to main |
| Analytics | PostHog (EU region) | Funnels, retention, UTM capture |

---

## What is happening this week

1. **Stefano sign-off on Compass cognitive dimensions: done** (2026-06-22). His ✅ on the High/Medium/Low priority assessment unblocked the build.
2. **Compass M1 shipped** (2026-06-22): commit 1 (schema migration 003) and commit 2 (item generation pipeline) are both on `main`. Few-shot anchors and the gen-cap default are resolved (see `ROADMAP.md` §4.5). One product decision still open: "Practice" vs. "Calibration" positioning on `/me` (needed for commit 4).
3. **Giovanni** is on **commit 3** (bank-first practice picker) on `giovanni/practice-mode`.
4. **Leonardo** continues on infra hardening + the EPSO content scrapers (`tools/epso_benchmark/`); dev/staging Supabase split is deferred to a pre-pilot gate (`ROADMAP.md` §6).
5. **Stefano** spends ~1 hour reviewing a sample of ~30 generated items before we flip the generator on publicly (`COMPASS_AUTOAPPROVE_GENERATED`).

---

## What is intentionally out of scope right now

These come later, in this order:

1. **External-log paste** (Layer B from the original plan) — Stefano was lukewarm, Giovanni decided the in-platform practice is the moat. Dropped from MVP.
2. **Stripe + payments** — separate workstream, deferred until the product loop is real.
3. **CV upload + CV-fit modifier** — designed but not yet built; lands when the practice loop is closed.
4. **NotebookLM prompt + content-pack library** — separate post-MVP feature; doesn't block.
5. **Pause-at-€5 subscription** for users between concorsi (Stefano + Leonardo suggested) — v1.1, after launch.
6. **Numerical, abstract, EU-knowledge item banks** as a content workstream — Stefano-owned in parallel with the Compass engine work.

---

## The bet, in one paragraph

We are building a study product that converts more candidates than any current EPSO platform because it knows them better than they know themselves. The engine tags every question on the cognitive operations it tests, every wrong answer on the misconception it represents, and uses both signals to find patterns no individual question could reveal. After 50-100 users have practiced for two weeks, we have data no one else has — about which cognitive sub-skills actually predict EPSO outcomes, about which weaknesses cluster together, and about which of our v1 tagging dimensions earn their keep. That data refines the engine, which sells the next 100 users, which sharpens the data further. If the loop holds, we own this segment. If it does not, we will know within twelve weeks because the kill criteria are wired in from day one.

---

**End of overview.** Drop questions in the Slack channel or open an issue on the repo. PRs are welcome but not required until we revisit the workflow before public launch.
