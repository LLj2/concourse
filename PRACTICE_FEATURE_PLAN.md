# Practice & Adaptive Learning — Feature Plan

> **Goal:** turn Concourse from a planner that *measures* into a platform where students *train*. Built on top of what already exists (diagnostic engine, scoring, planning, replan trigger, Anthropic client).
> **Status:** ready to start coding once cognitive-dimensions v1 is signed off (it is — Stefano confirmed 2026-06-22).
> **Branches:** all work under `giovanni/practice-mode`. Stefano OK'd the schema, Leonardo on standby for review.

---

## 0. The strategic premise

Other prep platforms know **whether** you got a question right. Concourse knows **why** you got it wrong, **what pattern** that wrongness fits, and **what to give you next**. This is the moat — and it requires three things to work together:

1. **A bank that fills itself.** Items are generated on demand when the bank is dry, tagged with cognitive dimensions at generation time, and never repeat for the same user.
2. **A response engine that finds patterns, not just scores.** Per-user, per-dimension mastery rolls forward on every answer. An LLM pass reads the matrix and writes back "focus on these 3 dimensions next."
3. **A feedback loop on the schema itself.** The dimensions are v1 hypotheses. Once we have real data (50-100 users), we kill the dimensions that don't discriminate, promote the ones that predict outcomes, and surface emergent patterns we hadn't anticipated.

This plan delivers all three.

---

## 1. What already exists (we build on this, we don't replace it)

| Module | What it does | We extend it how |
|---|---|---|
| `backend/logic/diagnostic.py` | Adaptive 5-item calibration; bank-only pick; difficulty-weighted score | Add `pick_practice_item()` (bank-first then generate); session length up to 40 |
| `backend/logic/scoring.py` | `build_profile()` joins measured scores + Likerts + soft narrative | Reads dimension mastery; profile includes per-dimension strengths/weaknesses |
| `backend/logic/planning.py` | Master-plan rule engine: skill weights × time-to-exam × hours → minutes | Slots reference dimension targets, not just skills |
| `backend/logic/adherence.py` | Daily tap + `replan_signal()` (event-driven) | Replan also fires on practice session completion + on pattern-analysis update |
| `backend/ai/client.py` | `generate_json()` with forced tool-call + JSON-schema validation | Reused for item generation and pattern analysis (no new abstraction) |
| `items` table | `skill_id`, `difficulty`, `prompt`, `options`, `correct_index`, `explanation` | Add `dimensions` jsonb, `option_diagnostics` jsonb, `competition_family`, `content_domain` |
| `item_responses` table | `selected_index`, `is_correct`, `time_taken_ms` | Add `practice_session_id` (nullable; sibling to existing `session_id`) |
| `diagnostic_sessions` | Calibration sessions | Stays as-is. Practice gets its own `practice_sessions` table |

**Important constraint:** the cognitive-dimensions schema from `COGNITIVE_DIMENSIONS.md` is the spec. ~9 dimensions per skill (numerical / verbal / abstract / FRMCQ / written) + 17 distractor-class tags + 3 meta tags. All declared by the LLM at generation time, validated by the JSON schema.

---

## 2. Architecture in one diagram

```
                    ┌─────────────────────────────────────────────┐
                    │  /practice page                              │
                    │  user clicks "practice verbal, 20 items"     │
                    └─────────────┬───────────────────────────────┘
                                  │
                                  ▼
                  ┌──────────────────────────────────┐
                  │  POST /api/practice/start         │
                  │  body: { skill_id, length }       │
                  └─────────────┬────────────────────┘
                                │
                ┌───────────────▼──────────────────────────────────┐
                │  pick_practice_item(user, skill)                  │
                │  1. read latest pattern_analyses → focus dims    │
                │  2. build slot target (60% focus / 30% weak /     │
                │      10% control)                                  │
                │  3. query items: unseen, matching dim target      │
                │  4. if no bank hit → generate_item(target dims)   │
                └───────────────┬──────────────────────────────────┘
                                │
                                ▼
                  ┌──────────────────────────────────┐
                  │  POST /api/practice/answer        │
                  │  → record_answer()                │
                  │  → update dimension_mastery       │
                  │  → record distractor class chosen │
                  │  → pick next item (loop)          │
                  └─────────────┬────────────────────┘
                                │
                                ▼ (on session end OR every N answers)
                  ┌──────────────────────────────────┐
                  │  run_pattern_analysis(user)       │
                  │  Anthropic call over mastery      │
                  │  matrix → focus_dimensions JSON   │
                  │  + plain-English insight string   │
                  │  written to pattern_analyses      │
                  └─────────────┬────────────────────┘
                                │
                                ▼
                  ┌──────────────────────────────────┐
                  │  events: practice_completed       │
                  │  + pattern_updated                │
                  │  → replan_signal() picks up       │
                  │  → /me shows "plan refresh"       │
                  └──────────────────────────────────┘
```

The arrows that already exist in the codebase (record_answer, replan_signal, events) are reused. The new code sits in the boxes labelled with `generate_item`, `pick_practice_item`, `dimension_mastery`, `run_pattern_analysis`.

---

## 3. Build sequence — 6 commits on `giovanni/practice-mode`

Each commit is a working, deployable unit. Merge each to `main` once smoke-tested (per HANDOFF §9, "branch and merge yourself"). Total estimated effort: 4-5 evening sessions.

### Commit 1 — Schema migration 003 (cognitive dimensions)

**Files:** `backend/db/migrations/003_dimensions.sql`

What it does:
- Adds to `items`: `competition_family text`, `content_domain text[]`, `dimensions jsonb`, `option_diagnostics jsonb`, `derived jsonb`, `source text default 'authored'`, `topic_tag text`.
- New table `practice_sessions` (id, user_id, skill_id, started_at, completed_at, items_attempted, items_correct, target_length, plan_id nullable).
- Alters `item_responses`: add `practice_session_id uuid nullable` (sibling to existing `session_id` for diagnostic). Adds a CHECK ensuring exactly one of the two is set per row.
- New table `dimension_mastery` (user_id, skill_id, dimension_name, dimension_value_str, attempts int, correct int, last_updated). Composite PK on (user_id, skill_id, dimension_name, dimension_value_str). One row per dimension *value* per user so we can track "verbal/inference_depth/multi_premise_inference = 31% over 13 attempts."
- New table `pattern_analyses` (id, user_id, generated_at, focus_dimensions jsonb, insight_md text, model_version text, payload jsonb). Append-only; latest row wins.
- Indexes on `(user_id, skill_id)` for mastery lookups, `(user_id, completed_at desc)` for session history.

Smoke test: run migration; `select count(*) from items where dimensions is null` returns 8 (existing verbal items); new tables exist and accept inserts.

**No code changes in this commit.** Just SQL. Keeps the diff readable and rollbackable.

---

### Commit 2 — Item generation pipeline

**Files:**
- `backend/ai/generate_item.py` (new)
- `backend/ai/prompts.py` (new, holds the per-skill generation prompts)

What it does:
- `generate_item(skill_id, difficulty, target_dimensions, recent_topic_tags, content_domain=None) -> dict` returns a fully validated item ready to insert.
- Uses `backend.ai.client.generate_json()` with a forced JSON schema requiring: `prompt`, `options` (exactly 4 distinct strings), `correct_index` (0-3), `explanation`, `topic_tag`, `dimensions` (per-skill dict matching the schema in `COGNITIVE_DIMENSIONS.md`), `option_diagnostics` (one entry per wrong option with `distractor_classes` from the canonical 17-tag pool).
- The prompt is built per skill from a system prompt + few-shot examples + the target dimensions. Few-shot examples are 2-3 authored items per skill (from the 8 verbal items we already have, plus authored examples Stefano can sign off).
- Validates: 4 distinct options, correct_index in range, dimensions dict matches expected keys, distractor_classes are in the canonical pool, topic_tag is short (1-3 words).
- On validation failure → retry once with a stricter prompt; on second failure → return None and log the event.
- Cost guard: a per-user daily generation cap (50 items/day default, configurable via env). Returns None and logs `generation_capped` if exceeded.

Smoke test: `python -m scripts.test_generate verbal 2 '{"inference_depth":"multi_premise_inference"}'` prints a valid item to stdout. Insert manually, serve via existing `/diagnostic` endpoint, confirm it renders.

**Risk in this commit:** prompt quality for EPSO-style items. Mitigation: spend 30-45 min with Stefano calibrating the verbal prompt against 5-10 real EPSO items (he has the sample tests). Repeat per skill before flipping the generator on. Numerical and abstract prompts can wait until commit 4.

---

### Commit 3 — Bank-first practice picker + practice sessions API

**Files:**
- `backend/logic/practice.py` (new)
- `backend/main.py` (add `/api/practice/*` routes)

What it does:
- `start_practice_session(db, user_id, skill_id, target_length)` → creates a row in `practice_sessions`, returns id.
- `pick_practice_item(db, session_id)` → the strategic core:
  1. Read latest `pattern_analyses.focus_dimensions` for this user+skill. If none yet → use a uniform distribution over dimensions.
  2. Build a target slot: 60% on focus dimensions, 30% on weakest non-focus dimensions (computed from mastery table), 10% on strongest dimensions as "control" (used to detect regression).
  3. Query `items` for unseen-by-this-user items matching the target. Difficulty follows ±1 adaptive rule (reuse `_difficulty_for_next` logic from diagnostic).
  4. If nothing matches → call `generate_item(target_dimensions)`, insert with `source='generated'`, return.
- `record_practice_answer(db, session_id, item_id, selected_index, time_taken_ms)`:
  - Reuses `dx.record_answer` for the item_responses row + item calibration counters.
  - Calls `update_dimension_mastery(db, user_id, item_id, is_correct)` — increments attempts/correct per dimension value the item carries.
  - Records the distractor class chosen if the answer was wrong (added column `item_responses.distractor_class_picked text[]`).
- `finalize_practice_session(db, session_id)` writes summary + emits `events.practice_completed`.
- Endpoints: `POST /api/practice/start`, `POST /api/practice/answer`, `POST /api/practice/end` (manual exit), `GET /api/practice/recent`.

Smoke test: create a test user → call start (verbal, 10 items) → answer 10 → confirm `dimension_mastery` has ~9 dimensions × multiple values populated, `events` shows the completion, accuracy is consistent.

---

### Commit 4 — Practice UI + dimension-aware feedback

**Files:**
- `backend/static/practice.html` (new — modeled on `diagnostic.html`)
- `backend/static/me.html` (extend: practice card + recent sessions)

What it does:
- Practice page: skill picker (4 buttons), length picker (10 / 20 / 40), then one-question-at-a-time UI identical to diagnostic. Differences:
  - Running counter at top ("12 / 20 answered, 8 correct").
  - After each answer: feedback + explanation + "next question" CTA.
  - End-of-session screen: accuracy %, time per item, **the diagnostic line** ("most of your errors clustered on items requiring two-step calculation — 2/6 correct vs 11/14 on single-step. Tomorrow's plan slot adjusts.").
  - Subtle "Report this question" link → flips `archived=true` on the item.
- `/me` dashboard adds:
  - **"Practice" card** with last 3 sessions, hyperlinked.
  - **"What we've learned about you"** panel rendering `pattern_analyses.insight_md` (markdown, max 200 words) — this is the differentiator the user feels.
- Daily plan items with `task_type=practice` deep-link to `/practice?skill=X&length=20&from_plan=<id>` so users land in practice from the plan.

Smoke test (manual, in browser): full flow — login, start verbal practice, answer 20 items, see the diagnostic message, return to `/me`, see the insight panel updated.

---

### Commit 5 — Pattern-analysis worker

**Files:**
- `backend/logic/patterns.py` (new)
- `backend/main.py` (hook into `finalize_practice_session` + a manual `/api/patterns/refresh` endpoint)

What it does:
- `compute_dimension_summary(db, user_id, skill_id)` → reads `dimension_mastery`, returns the per-dimension accuracy table for one skill.
- `run_pattern_analysis(db, user_id, skill_id)` is the LLM call:
  - Input: the dimension summary, plus the user's overall score and recent distractor-class picks.
  - Prompt asks for: 1-3 patterns explaining failure modes, citing the supporting numbers, distinguishing surface patterns ("weak on percentages") from deep ones ("weak whenever a calculation chains, regardless of topic"), and recommending 3-5 focus dimensions for the next session.
  - Output schema: `{patterns: [{summary, evidence_dims, depth: "surface"|"underlying", confidence: 0-1}], focus_dimensions: [string], insight_md: string}`.
  - Writes to `pattern_analyses`, emits `events.pattern_updated`.
- Trigger logic: runs automatically on `finalize_practice_session` if the user has ≥20 responses in this skill since the last analysis. Manual refresh via `/api/patterns/refresh` for testing.
- Cost guard: cap at 1 analysis per user per skill per 30 min (skip if a fresh one exists).

Smoke test: run two 20-item practice sessions for a test user with deliberate weakness on multi-step items. Confirm `pattern_analyses` has a row, focus_dimensions includes `operation_steps:2-3` or `operation_steps:3`, insight_md mentions chained calculations.

---

### Commit 6 — Empirical-validation pipeline (the feedback loop on the schema itself)

**Files:**
- `backend/logic/validation.py` (new)
- `backend/main.py` (add `GET /admin/dimensions/health` — admin-only)

What it does:
This is the commit that makes the schema **self-correcting** over time. Three queries that surface to an admin dashboard once we have ≥100 users:

1. **Discrimination check.** For each dimension, compare accuracy of top-quartile users vs bottom-quartile (by overall skill score). Dimensions where the gap is < 10 percentage points are flagged "non-discriminating" → candidates for removal.
2. **Predictivity check.** For each user with a completed second diagnostic (the 5-item calibration retaken later), correlate their dimension-mastery vector at time T with their score at time T+N. Dimensions whose mastery correlates with future score = predictive → promote in the LLM prompt weighting.
3. **Emergent pattern detection.** A monthly LLM pass over the responses table looks for **clusters of co-occurring errors that don't map to a single dimension** ("these 23 users got items wrong specifically when two operations chained AND the base was non-obvious — we don't have a tag for that combination"). Output: candidate new dimensions for v2.

Surface: `/admin/dimensions/health` shows three tables:
- Dimensions ranked by discrimination power (high = good)
- Dimensions ranked by predictivity (correlation with future score)
- Top 5 candidate new dimensions from emergent clusters

This is what makes the cognitive-dimensions schema a living thing, not a frozen v1. It also gives us hard data to take back to Stefano for v2 sign-off after the pilot.

Smoke test: write the queries against synthetic data (script that seeds 50 users with known patterns); confirm dimensions designed to be non-discriminating show up as flagged.

---

## 4. Risks & mitigations

### Risk 1 — LLM-generated items have ~15-20% quality issues

EPSO verbal/numerical items are subtle. Haiku 4.5 will produce 80% good items, 15% awkward, 5% wrong.

**Mitigations:**
- **Few-shot examples** in the generation prompt from real EPSO sample tests (we have these — Stefano confirmed). Tuning the prompt with examples is the highest-ROI work in this whole project.
- **Bank-first** means bad items get answered once then never seen again, so noise washes out as the bank grows.
- **"Report this question"** button (commit 4) flips `archived=true`, removes from the bank.
- **Pre-launch audit:** before opening practice to real users, manually review a sample of 30 generated items per skill. Drop any that are wrong; tune the prompt if a pattern emerges.

### Risk 2 — Generation latency

Haiku returns a JSON tool call in ~2-3s, occasionally 6s. If every item is generated, the user waits 3s between answers = poor UX.

**Mitigations:**
- **Bank-first** is the architectural mitigation. After 100 users have practiced, 90%+ of items come from the bank instantly.
- **Pre-generate** the next 3 items in the background after a user answers, so by the time they finish reading the next one is ready.
- **Skeleton UI** — render the question card with a loading state, then fill it in. Hides latency.

### Risk 3 — Cost runaway

At ~2-3¢ per generated item, a power user doing 40 items/day where 30 are generated is ~80¢/day = $24/month. Above the LLM cost target.

**Mitigations:**
- **Bank-first** controls this — bank-served items cost nothing.
- **Daily per-user generation cap** (50 items/day default; configurable). User hits the cap → message: "you've practiced a lot today — come back tomorrow."
- **Pattern-analysis call cap** — once per 30 min per user per skill.
- **Monitor:** `events.generation_capped` and the Anthropic billing dashboard.

### Risk 4 — Schema drift between v1 and reality

Some of our v1 dimensions won't predict anything. Worse, real failure patterns will emerge that we haven't tagged.

**Mitigation:** the entire commit 6 (`backend/logic/validation.py`) exists for this. Three automatic checks tell us which dimensions to kill, promote, or add — driven by real student data, not opinion.

### Risk 5 — Practice ≠ calibration scoring confusion

If practice answers feed the same `score` field as calibration, the calibration baseline becomes noise.

**Mitigation:** they don't. Practice writes to `practice_sessions` and `dimension_mastery`. Calibration writes to `diagnostic_sessions` and `score` on profile. The replan engine reads **both** — calibration for the trusted baseline, practice mastery for high-volume signal. Two separate columns in scoring.

---

## 5. Timeline (your own pace; rough estimates)

| Commit | Effort | Can do in parallel? |
|---|---|---|
| 1 — Schema migration | 1 session (~90 min) | No (everything depends on it) |
| 2 — Item generation | 1.5 sessions (the prompt tuning with Stefano is most of the time) | After commit 1 |
| 3 — Practice picker + API | 1 session | After commit 2 (needs the generator) |
| 4 — UI | 1 session | Can start after commit 3 stub APIs return |
| 5 — Pattern analysis | 1 session | After commit 3 (needs mastery data) |
| 6 — Validation pipeline | 1 session, plus admin auth glue | Last (needs real users to mean anything) |

Total: 5-7 sessions over ~1.5 weeks if you're working evenings. The most variable item is the prompt tuning in commit 2 — could be 30 min if the verbal prompt clicks immediately, could be 3 hours across two attempts.

---

## 6. Coordination with Leonardo and Stefano

**Leonardo:** don't touch `backend/logic/diagnostic.py` or `backend/db/migrations/` until commit 1 lands. Drop him a WhatsApp before starting: *"Sto facendo practice-mode questa settimana, tocco diagnostic.py, main.py, e aggiungo migration 003. Vado avanti senza PR, te lo facco quando è in main."*

**Stefano:**
- ~45 min on the verbal-generation prompt before commit 2. He gives 5-10 real EPSO items as few-shot anchors, we tune the system prompt together.
- ~1 hour reviewing a sample of 30 generated items before flipping on the generator publicly.
- ~3 hours total for inter-rater calibration (the test from `COGNITIVE_DIMENSIONS.md §6.5`) — can be done after commit 5 ships, doesn't block.

**Both:**
- After commit 6 ships and we have 50+ users practicing, schedule a 1-hour review of the dimension-health dashboard. This is where the v1→v2 dimension list gets refined with real data.

---

## 7. What success looks like

By the end of these 6 commits and ~2 weeks of real-user practice:

- A new user can sign up, calibrate, then practice 4 skills × varying lengths, with items generated to target *their* weak patterns.
- The `/me` dashboard renders 2-3 LLM-generated insight sentences that feel personal ("you handle one-step percentages fine but struggle with two-step ones").
- Daily plan items deep-link into practice sessions targeted at the user's weakest dimensions.
- The admin dashboard tells us which dimensions are doing work and which aren't.
- The item bank has grown from 8 (current) to ~200-500 items spanning all 4 skills, with the bulk of practice being bank-served (cost-controlled).
- We can take real data back to Stefano and discuss v2 of the dimension schema.

This is the moat operating end-to-end.

---

## 8. Out of scope (deliberately)

These come later, not in this feature:

- **External-log paste (Layer B)** — Stefano was lukewarm on this; you decided in-platform is the moat. We dropped Layer B from the MVP.
- **Numerical, abstract, EU-knowledge item banks** beyond what gets generated organically. Sourcing or authoring ~15-25 calibrated seed items per skill is a parallel content workstream Stefano can lead. This plan delivers the engine; the seed content is its own task.
- **NotebookLM prompt library** — separate post-MVP feature; doesn't block.
- **Stripe + payments** — separate workstream, your earlier decision to focus on the core product before monetization.
- **Multi-language items** — Italian first if/when we localize; not in scope here.

---

## 9. Open decisions before commit 1

Three things to settle today or tomorrow:

1. **Few-shot examples for the generator** — does Stefano have a clean source of 5-10 real EPSO verbal items + their correct answers we can use as anchors? If yes, we go straight into commit 2 prompt-tuning. If no, we author them ourselves (~30 min with Stefano).
2. **Daily generation cap default** — 50 items/user/day is my proposal. Higher = more cost, lower = potential UX hit on heavy users. Confirm 50 or override.
3. **Where does "Practice" sit in `/me` navigation** — equal billing with Calibration, or visually subordinate to it? My proposal: equal. Practice is the daily verb; calibration is the periodic measurement.

Settle these and I cut commit 1 tonight.

---

**End of plan.**

Companion docs in the repo:
- `COGNITIVE_DIMENSIONS.md` — the schema this builds on
- `HANDOFF.md` — overall stack and workflow
- `ROADMAP.md` — Leonardo's overall project tracker
