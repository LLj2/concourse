# Compass — Build Roadmap

> **Feature:** Compass — Concourse's adaptive practice engine.
> **Owner:** Giovanni (primary), Stefano (content), Leonardo (review + infra).
> **Branch:** `giovanni/practice-mode` (off `main`, after `giovanni/cognitive-dimensions` merges).
> **Target:** end-to-end working on Railway in ~2 weeks of evening sessions; soft-launch to pilot users 2 weeks after that.
> **Reference docs:** `OVERVIEW.md` (project), `COGNITIVE_DIMENSIONS.md` (schema), `PRACTICE_FEATURE_PLAN.md` (engineering plan).

---

## 0. What "done" looks like

Compass ships when **all five** of these are true:

1. A logged-in user can start a practice session in any of 4 skills, pick a length (10 / 20 / 40 items), answer adaptively-served questions, and see a result screen that **names the cognitive pattern** behind their wrong answers ("most errors clustered on two-step calculations").
2. The item bank is **self-filling** — bank-first lookup with LLM-generated fallback, items tagged with cognitive dimensions and per-option misconception classes at generation time.
3. `/me` shows a **"What we have learned about you"** insight panel that updates after every session, rendered from an LLM pass over the user's dimension-mastery matrix.
4. The replan trigger fires on practice completion. Daily plan items deep-link into targeted practice sessions.
5. An admin dashboard at `/admin/dimensions/health` shows which dimensions are discriminating, which are predictive, and what emergent patterns are surfacing — so the v1 schema can correct itself with real data.

If any of the five is missing at launch, we stay in beta.

---

## 1. Phasing — six commits, three milestones

We organize the 6 commits into three milestones so each milestone independently makes the product better, even if we pause:

| Milestone | Commits | What the user can do after this | Days of work |
|---|---|---|---|
| **M1 — Foundation** | 1, 2 | Nothing user-visible yet, but the engine can generate a single tagged item end-to-end | ~2.5 sessions |
| **M2 — Practice loop live** | 3, 4 | Sign up → calibrate → practice 20 items → see a dimensional result | ~2 sessions |
| **M3 — The moat** | 5, 6 | Pattern detection + insight panel + dimension-health dashboard | ~2 sessions |

Each milestone is independently deployable. If we ship M1+M2 but not M3, Compass works as a smarter practice mode. If we ship all three, it's the moat.

---

## 2. The 6 commits, in order

### Commit 1 — Schema migration 003 (dimensions, practice, mastery, patterns)

**Branch:** `giovanni/practice-mode`
**Effort:** ~90 min
**Risk:** low (additive only, no data loss)

**What lands:**

`backend/db/migrations/003_dimensions_and_practice.sql`:

```sql
-- Items extended with cognitive dimensions
alter table items add column competition_family text;
alter table items add column content_domain text[];
alter table items add column dimensions jsonb;
alter table items add column option_diagnostics jsonb;
alter table items add column derived jsonb;
alter table items add column topic_tag text;
alter table items add column source text default 'authored';

-- Practice sessions (sibling to diagnostic_sessions)
create table practice_sessions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    skill_id text not null references skills(id),
    started_at timestamptz not null default now(),
    completed_at timestamptz,
    items_attempted int not null default 0,
    items_correct int not null default 0,
    target_length int not null default 20,
    plan_id uuid references plans(id)
);

-- Item responses now point to either diagnostic OR practice
alter table item_responses add column practice_session_id uuid
    references practice_sessions(id) on delete cascade;
alter table item_responses add column distractor_class_picked text[];

-- Mastery: one row per user × skill × dimension-value
create table dimension_mastery (
    user_id uuid not null references users(id) on delete cascade,
    skill_id text not null references skills(id),
    dimension_name text not null,
    dimension_value text not null,  -- stringified value for ordinals/booleans/cats
    attempts int not null default 0,
    correct int not null default 0,
    last_updated timestamptz not null default now(),
    primary key (user_id, skill_id, dimension_name, dimension_value)
);

-- Pattern analyses: append-only, latest row wins per user×skill
create table pattern_analyses (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    skill_id text not null references skills(id),
    generated_at timestamptz not null default now(),
    focus_dimensions jsonb not null,
    insight_md text,
    model_version text,
    payload jsonb
);
create index idx_pattern_user_skill on pattern_analyses(user_id, skill_id, generated_at desc);
```

**Acceptance:**
- `python -m scripts.run_migration 003` succeeds against the Supabase pooler
- `select count(*) from items where dimensions is null` returns 8 (the existing verbal items, intentionally null until we backfill)
- Insert a dummy `practice_sessions` + `item_responses` + `dimension_mastery` row through `psql` to confirm constraints work

**Coordination:** ping Leonardo on WhatsApp before running migration on the shared Supabase. Same db is dev + prod right now (per `ROADMAP §6`), so this is mildly risky — we run it during a window when no one is testing.

---

### Commit 2 — Item generation pipeline

**Effort:** 1.5 sessions (~3 hours total; most is prompt tuning with Stefano)
**Risk:** medium (prompt quality drives item quality drives user trust)

**What lands:**

- `backend/compass/generate_item.py` — single function `generate_item(skill_id, difficulty, target_dimensions, recent_topic_tags, content_domain=None)` returning a validated item dict.
- `backend/compass/prompts/` directory — one prompt file per skill (`verbal.py`, `numerical.py`, etc.), holding the system prompt + few-shot examples + the per-skill dimension schema.
- `backend/compass/item_schema.py` — the JSON schema each skill's output must match (programmatic, generated from `COGNITIVE_DIMENSIONS.md`).
- A `scripts/test_generate.py` CLI for prompt iteration.

> All Compass code lives under `backend/compass/` per the isolation contract (`backend/compass/README.md`). The legacy `backend/ai/client.py` is reused as a dependency (it's the generic Anthropic wrapper), but everything Compass-specific is in the sealed package.

**The flow:**
1. Caller specifies `(skill, difficulty, target_dimensions={"inference_depth": "multi_premise_inference"}, recent_topic_tags=["etias","gdpr"])`.
2. Builder loads the skill's system prompt + 3-5 few-shot examples (real EPSO items + their dimension tags), appends "generate ONE new item with these dimensions and avoiding these topics," and the output JSON schema.
3. `backend.ai.client.generate_json()` (existing) makes the call with forced tool use.
4. Returned dict goes through `validate_item()`:
   - 4 distinct options
   - `correct_index` in 0-3
   - `dimensions` dict has all required keys for this skill, values match the schema
   - `option_diagnostics` has 3 entries (one per wrong option) each with ≥1 valid `distractor_classes` from the canonical 17
   - `topic_tag` is 1-3 words
5. On validation failure → one retry with stricter prompt → if still bad, return None + log `events.generation_failed`.
6. Cost guard: per-user daily generation counter (default 50/day; configurable via env var `COMPASS_DAILY_GEN_CAP`). Hitting cap → return None + log `events.generation_capped`.

**The big risk:** EPSO verbal items are subtle. Haiku 4.5 will produce 80% good, 15% awkward, 5% wrong. The mitigation is the few-shot examples — they ARE the prompt.

**Update 2026-06-22 — anchors are already in the repo.** `backend/compass/few_shot/verbal_epso_anchors.json` carries 10 real EPSO AST verbal-reasoning items (passage + 4 options + correct index + source URL) extracted from EPSO's public sample tests. Commit 2 wires 3-5 of these into the generation prompt and we're done — no Stefano-authoring session needed for verbal. Stefano's review can shift to *spot-checking generated output quality* (~1 hour after first 30 generated items) rather than authoring anchors from scratch.

For **numerical** and **abstract**: the same benchmark folder has them but they're image-dependent (numerical: chart in image; abstract: pattern series IS the image). Text-only generation doesn't apply. Numerical/abstract generators are post-v1 once we add either image generation or text-table item authoring.

**Acceptance:**
- `python -m scripts.test_generate verbal 2 --dims '{"inference_depth":"multi_premise_inference"}'` prints a valid item that an EPSO-aware reader would not flag as wrong
- Run it 10 times, eyeball quality, ≥7/10 pass Stefano's sniff test before we move on
- Item inserted into `items` table renders correctly on the existing `/diagnostic` page

**What we skip until later:** numerical and abstract prompts ship as stubs with TODO; we tune them properly in M2 before commit 4 needs them. FRMCQ and written-test generation are deferred entirely until commits 3-6 are working for the reasoning skills.

---

### Milestone 1 done. Pause point: M1 alone gives us a tested generator but no user-visible change.

---

### Commit 3 — Bank-first practice picker + practice API

**Effort:** 1 session
**Risk:** low

**What lands:**

`backend/logic/practice.py`:

```python
def start_practice_session(db, user_id, skill_id, target_length) -> str: ...
def pick_practice_item(db, session_id) -> NextItem | None: ...
def record_practice_answer(db, session_id, item_id, selected_index, time_taken_ms) -> dict: ...
def finalize_practice_session(db, session_id) -> dict: ...
def update_dimension_mastery(db, user_id, item_id, is_correct) -> None: ...
```

`pick_practice_item` is the strategic core. Algorithm:

1. Look up the user's latest `pattern_analyses` row for this skill. If none → start with uniform distribution over dimensions.
2. From `dimension_mastery`, compute current weakest dimension values (attempts ≥ 3, lowest accuracy).
3. Build a target distribution for this slot:
   - 60% probability: pick a focus dimension from `pattern_analyses.focus_dimensions`
   - 30% probability: pick a non-focus weak dimension
   - 10% probability: pick a strong dimension (control / regression detection)
4. With the picked dimension as a constraint, run an unseen-item query against `items`:
   ```sql
   select * from items
   where skill_id = :s and archived = false
     and dimensions ->> :dim_name = :dim_value
     and difficulty = :target_difficulty
     and id not in (select item_id from item_responses where user_id = :u)
   limit 1;
   ```
5. If no item → call `generate_item(skill_id, target_difficulty, {dim_name: dim_value}, recent_tags)` and insert with `source='generated'`.
6. Either way, return the item.

Difficulty adapts via the same ±1 rule as the calibration engine (`backend/logic/diagnostic.py::_difficulty_for_next` — reused).

`update_dimension_mastery` walks the item's `dimensions` JSON, and for each dimension value, increments the appropriate row in `dimension_mastery` (upsert pattern).

`record_practice_answer` also logs the user's distractor-class pick (if wrong) by reading `item.option_diagnostics[selected_index].distractor_classes`.

**API endpoints** in `backend/main.py`:
- `POST /api/practice/start { skill_id, target_length }` → returns session_id + first item
- `POST /api/practice/answer { session_id, item_id, selected_index, time_taken_ms }` → returns feedback (correct + explanation + distractor class if wrong) + next item OR final summary
- `POST /api/practice/end { session_id }` → manual quit
- `GET /api/practice/recent` → last 5 sessions for `/me` widget

**Acceptance:** smoke-test as in the diagnostic engine (`python -m scripts.smoke_practice`) — create a fake user, start a 10-item verbal session, answer all 10, confirm `dimension_mastery` has rows populated, `events.practice_completed` is logged.

---

### Commit 4 — Practice UI + `/me` insight panel

**Effort:** 1 session
**Risk:** low (mostly HTML)

**What lands:**

`backend/static/practice.html` — modeled exactly on `diagnostic.html` (proven pattern):
- Top bar: skill picker (4 buttons: Verbal / Numerical / Abstract / EU Knowledge), length picker (10 / 20 / 40)
- Question card: prompt, 4 options, Submit button
- After answer: feedback line (correct/wrong + brief), full explanation, "Next" button
- Running counter ("12/20 answered · 8 correct")
- End-of-session screen: the **dimensional insight line** — "Most of your errors clustered on items requiring two-step calculation (2/6 correct vs 11/14 on single-step). Tomorrow's plan slot adjusts accordingly."
- Subtle "Report this question" link on each item → flips `archived=true` on the item

`backend/static/me.html` (additions):
- **"Practice" card** with last 3 sessions, hyperlinked to a session-detail view (basic)
- **"What we have learned about you" panel** rendering `pattern_analyses.insight_md` as a markdown blob (max 200 words). Only shows after the user has done ≥20 practice items in any skill.

Daily-plan-item rendering update: items with `task_type = "practice"` deep-link to `/practice?skill=X&length=20&from_plan=<plan_id>`.

**Acceptance — manual browser test:**
1. Log in → start verbal practice, length 20.
2. Answer 20 items.
3. End screen names a real cognitive pattern from the user's responses (eyeball check that the language is honest, not vague).
4. Return to `/me`. Practice card shows the recent session. Insight panel renders.
5. Click into the daily plan. A "practice numerical" item deep-links into the practice page with skill prefilled.

---

### Milestone 2 done. Pause point: M1+M2 = a fully working adaptive practice engine. Sellable. The moat is missing.

---

### Commit 5 — Pattern-analysis worker

**Effort:** 1 session
**Risk:** medium (LLM output is the user-facing voice)

**What lands:**

`backend/logic/patterns.py`:

```python
def compute_dimension_summary(db, user_id, skill_id) -> dict: ...
def run_pattern_analysis(db, user_id, skill_id) -> dict: ...
def latest_pattern(db, user_id, skill_id) -> dict | None: ...
def should_refresh(db, user_id, skill_id) -> bool: ...
```

`run_pattern_analysis` is the LLM call:

- Input: dimension mastery table for this user+skill (compact JSON), plus user's overall score, plus distractor-class frequencies for wrong answers, plus the last 3 practice-session summaries.
- System prompt is direct:
  > You are a psychometrician reading a user's response patterns on an EPSO-style {skill} test. Identify the 1-3 most actionable failure patterns. Distinguish surface patterns ("weak on percentages") from underlying patterns ("weak whenever calculations chain, regardless of topic"). Cite the supporting numbers. Recommend 3-5 focus dimensions for the next session. Be honest: if the data is noisy or insufficient, say so.
- Output schema (forced tool call):
  ```json
  {
    "patterns": [
      {"summary": "string (1 sentence)", "evidence_dims": ["dim_name", ...], "depth": "surface" | "underlying", "confidence": 0.0-1.0}
    ],
    "focus_dimensions": [{"dimension_name": "...", "dimension_value": "..."}],
    "insight_md": "string, plain English, 80-150 words"
  }
  ```
- Writes the row to `pattern_analyses`, emits `events.pattern_updated`.
- Cost guard: skip if a fresh analysis exists from <30 min ago.

**Trigger:** automatically called inside `finalize_practice_session` if the user has ≥20 responses in this skill since the last analysis. Also exposed as `POST /api/patterns/refresh` for testing.

**Integration with replan:**
- Leonardo's `backend/logic/adherence.py::replan_signal` is extended: a fresh `pattern_updated` event (within 24h) in the absence of a recent plan refresh emits a "refresh suggested" hint on `GET /api/plan` so `/me` can show a banner.

**Acceptance:**
- Run two 20-item verbal sessions on a fake user, deliberately answering wrong on `inference_depth=multi_premise_inference` items. Trigger analysis.
- `pattern_analyses` has a row. `focus_dimensions` includes `inference_depth=multi_premise_inference`. `insight_md` mentions multi-premise reasoning. Language is honest, not generic.
- `/me` shows the insight panel updated, and a "refresh your plan" banner appears.

---

### Commit 6 — Validation pipeline (the schema's self-correcting layer)

**Effort:** 1 session + admin auth glue
**Risk:** low (read-only queries; no production behavior changes)

**What lands:**

`backend/logic/validation.py`:

```python
def discrimination_check(db, skill_id, min_users=20) -> list[dict]: ...
def predictivity_check(db, skill_id, min_users=20) -> list[dict]: ...
def emergent_patterns(db, skill_id, lookback_days=30) -> list[dict]: ...
```

**Discrimination check** — for each dimension value, compute accuracy of users in the top-quartile of overall skill score vs bottom-quartile. Gap < 10 percentage points → flag as "non-discriminating" (candidate for removal in schema v2). Gap > 25 pp → flag as "highly discriminating" (candidate for higher weighting).

**Predictivity check** — for each user who has retaken a calibration after ≥30 days of practice, correlate their `dimension_mastery` accuracy at time T-30 with their calibration score at time T. Dimensions whose mastery correlates positively with future score = predictive. Use Spearman correlation; report dimensions with |ρ| > 0.3.

**Emergent patterns** — a monthly LLM call (manual for now, scheduled later): feed it the response history for wrong-answered items, ask it to identify error clusters that don't map cleanly onto any single existing dimension. Output: candidate new dimensions for v2 with supporting numbers.

**Admin route** in `backend/main.py`:
- `GET /admin/dimensions/health` — gated by a simple admin password (env var `ADMIN_PIN`), renders three tables on a server-side HTML page. No fancy UI; readable.

**Cost:** validation queries are pure SQL (free). Emergent-patterns LLM call is ~1 cent each, run monthly.

**Acceptance:**
- Seed 50 synthetic users with known patterns (script: half are weak on multi-step, half are weak on quantifiers).
- Run discrimination check. Confirm `operation_steps` and `quantifier_scope` show large discrimination gaps. Confirm a synthetically-noise dimension shows a small gap.
- Run emergent-patterns LLM call on the synthetic data, confirm it surfaces ≥1 sensible pattern.

---

## 3. Timeline — a calendar view

Assuming **2-3 evening sessions per week** (90 min each) for Giovanni:

| Week | Sessions | Commits | Compass status |
|---|---|---|---|
| **Week 1** (this week) | 2-3 | Commit 1 ships; Commit 2 prompt tuning with Stefano | M1 nearly done |
| **Week 2** | 2-3 | Commit 2 ships; Commit 3 ships; Commit 4 starts | M1 done, M2 in flight |
| **Week 3** | 2-3 | Commit 4 ships; Commit 5 ships | M2 done, M3 in flight |
| **Week 4** | 1-2 | Commit 6 ships; pilot recruiting starts | M3 done. **Compass v1 live.** |
| **Weeks 5-6** | parallel | Pilot users on Compass; weekly review of `/admin/dimensions/health` | First real data |
| **Week 7** | with Stefano | Schema v2 review based on real data | Compass v1.1 planned |

Soft target: **Compass v1 live by 2026-07-20** (4 weeks from today).
Hard target: **first 10 pilot users practicing daily on Compass by 2026-07-31** (5 weeks).

If the schedule slips, the M1/M2/M3 phasing means we can ship M1+M2 as "Compass v0.5" and still have a sellable practice engine without the insight layer.

---

## 4. What blocks the build right now

**Three open product decisions before commit 1:**

1. ~~**Few-shot anchors for the verbal generator.**~~ ✅ Resolved 2026-06-22: 10 real EPSO AST verbal items extracted from the `epso_benchmark_data` download into `backend/ai/few_shot/verbal_epso_anchors.json`. Commit 2 wires them in directly.
2. **Daily generation cap default.** 50 items/user/day proposed. *Decision needed: before commit 2.*
3. **Practice vs. Calibration on `/me`.** Equal billing or Calibration as headline? Proposal: equal. *Decision needed: before commit 4.*

**Two infra dependencies on Leonardo's track:**

- **Custom SMTP** (Resend or similar) — not strictly blocking Compass but needed before pilot recruiting in week 4, otherwise magic-link delivery is unreliable.
- **Dev/staging Supabase split** — currently a shared DB. Running migration 003 means we briefly disrupt anyone using the production DB. Coordinate timing.

---

## 5. Risks tracked through the build

| Risk | Impact | Mitigation | Owner |
|---|---|---|---|
| Generated EPSO items are awkward or wrong | Trust collapse on day 1 | Stefano-authored few-shot anchors; sample of 30 audited before public flip; user-flag and archive | Giovanni + Stefano |
| Pattern-analysis insights are too generic | Insight panel feels dumb, defeats the moat | Be honest in the prompt: if data is noisy, say so. Run on real data before launch, iterate prompt. | Giovanni |
| Generation latency hurts UX | Users wait 3s between items | Bank-first (most items cached), pre-generate next 2 in background after each answer, skeleton UI | Giovanni |
| LLM cost runs over | Bleeds margin | Bank-first amortizes cost as bank grows; daily per-user cap; monitor Anthropic dashboard weekly | Giovanni |
| Schema v1 dimensions don't predict outcomes | We built on a wrong taxonomy | Commit 6 — the validation pipeline — exists specifically for this. v2 review with Stefano in week 7 | Giovanni + Stefano |
| Three people touching same files | Merge conflicts | Coordinate offline before starting; Leonardo on infra not Compass during M1-M2 | All |

---

## 6. How we report progress to the channel

Lightweight, no formal stand-ups:

- **End of each commit:** drop a one-line message in Slack — "Commit X shipped: [thing]. Try it on Railway." Plus the deploy URL if visible.
- **End of each milestone (M1, M2, M3):** a 100-word recap in Slack — what works now, what changed, what's next.
- **Weekly:** Giovanni updates `COMPASS_ROADMAP.md` (this file) with crossed-out commits and any timeline drift. Commit goes to `main` directly per the lightweight workflow.

---

## 7. After Compass v1 — the v1.1 backlog

Things we deliberately defer; track here so they don't get lost:

- **Numerical, abstract, EU-knowledge item bank seeding** — let the generator fill these organically through user practice. Authoring as a backup if the generator quality is shaky.
- **FRMCQ practice mode** — needs domain content from Stefano (DAMA-DMBOK / GDPR / AI Act materials). Separate, parallel content workstream.
- **Written-test practice** — generation prompts harder; defer until reasoning skills are working.
- **Multi-skill sessions** — "practice 30 minutes mixed" picker that interleaves skills based on time-of-day energy.
- **Confidence rating** — let users self-rate confidence per answer; surfaces metacognition gaps.
- **Spaced repetition** — bring back archived-but-relevant items after 14 days for memory reinforcement.
- **Practice streaks** — daily-open gamification. Stefano was lukewarm on gamification but a simple streak is cheap.

These are explicitly out of scope for v1. Reopen after pilot data lands.

---

**End of roadmap.** Owned by Giovanni, reviewable by Leonardo + Stefano via the repo. Update as work lands.
