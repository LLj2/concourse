# Stefano's spec vs. Concourse — cross-walk

> Source spec: `EPSO Adaptive Learning Tool — Feature Specification & User Flow.docx` (Stefano, 2026-06-23).
> Cross-walked against: code on `main` at commit `96c50d3`, plus `ROADMAP.md`.
> Drafted 2026-06-23. Mapping owner: Giovanni. Review owner: Leonardo + Stefano.

This document is a four-way map: **(1) what Stefano specified**, **(2) what we already shipped**, **(3) what was already in the plan but not built**, **(4) what is new in Stefano's spec and needs to be added to the plan**.

Stefano framed the system as nine "threads" (persistent AI chat contexts). In Concourse those map to a mix of: existing pages (`/intake`, `/profile`, `/plan`, `/diagnostic`, `/me`, `/compass`), the Compass adaptive engine, and a handful of features we have not yet built. The cross-walk is organised thread-by-thread because Stefano organised the spec that way; the implementation will not be literally "nine threads" but the *capabilities* line up.

---

## Quick read: the headline gaps

After reading the full spec, the **five real product gaps** Stefano's document surfaces that the current plan does not cover are:

1. **Vacancy-notice ingestion + canonical competition brief** (his Thread 1). Today we pre-seed `target_competition` as a free-text string at intake; we never parse a notice, never produce a brief, never expose it to the user. **This is a real feature, not currently in our plan.**
2. **CV-based eligibility check + competency-alignment matrix** (his Thread 2). Today we collect a CV-fit modifier *concept* in the schema but no CV upload, no eligibility verdict, no alignment matrix. **Was sketched in the roadmap (CV-fit modifier) but deferred; Stefano's spec makes it more substantive.**
3. **Multi-skill practice for numerical / abstract / EU-knowledge / FRMCQ / EUFTE** (his Threads 5b, 5c, 6, 7). Today Compass is verbal-only. **Was in COMPASS_ROADMAP as "post-v1" but Stefano's spec treats them as first-class.**
4. **NotebookLM-style audio study materials** (his Thread 9). Today, nothing. **Parked in our roadmap as "post-MVP, ~session 7 if time"; Stefano explicitly calls this a "wow effect, almost-free, super useful while commuting" feature and elevates it.**
5. **"Let's study now" daily-plan one-click flow** (his Thread 4 user-flow note). Today, `/plan` shows the master plan but does not have a single dominant CTA that launches today's session. **Not in the plan as a UX item.**

The other four threads in Stefano's spec (3 Master Plan, 4 Daily Plan, 5a Verbal Reasoning, 8 Performance Tracker) are **substantially shipped** — Compass v1 + Leonardo's planning/scoring modules cover them at v1 quality.

A separate finding: **Stefano's "automation everywhere" inline comments** are the most important UX correction in the doc. He repeatedly says "this is automatic, the user doesn't need to prompt anything." Our current loop already works this way; the spec confirms we got the orchestration shape right.

---

## Thread-by-thread cross-walk

### Thread 1 — HQ & Vacancy Analysis 🟡 PARTIAL

| Stefano's spec says | We have today | Status |
|---|---|---|
| User uploads vacancy notice PDF | Intake form asks free-text `target_competition` (dropdown of canned values: `AD5_generalist`, `AD7_ict`, `AST`, `other`) | ❌ |
| Pre-uploaded competition notices, user picks from dropdown | A 4-option dropdown only; no per-competition data behind it | ❌ |
| LLM extracts structured competition brief (test phases, pass scores, scoring logic, eligibility, dates, language requirements) | Nothing equivalent | ❌ |
| Auto-summary offered to user ("do you want to see a summary?") with skip option | No competition brief surface at all | ❌ |
| `tools/epso_benchmark/news_scrape.py` already pulls **75 EPSO/ORSEU/EuropApp news articles** including some competition notices | Leonardo's scraper, output git-ignored under `tools/epso_benchmark/data/` | ✅ raw data exists |

**Net gap:** the *raw material* exists (Leonardo's scraper pulled 60 EPSO news/notices). What is missing is:
- A canonical competition catalog in the DB (probably a new table `competitions`)
- An ingestion pipeline that takes a notice PDF/URL → LLM extraction → structured row in `competitions`
- A user-facing competition picker that reads from this catalog
- An auto-generated brief surfaced on `/intake` or `/me`

**Priority recommendation:** medium. Today the product works because users self-declare `target_competition` and the plan engine doesn't deeply use the specifics. Brief production is a real "wow effect" Stefano flags but does not gate the practice loop.

---

### Thread 2 — Profile & GAP Analysis 🟡 PARTIAL

| Stefano's spec says | We have today | Status |
|---|---|---|
| CV upload (mandatory for specialist, optional for generalist) | Intake collects no CV; schema has `profiles.cv_storage_path` column but it is unused | 🟡 schema only |
| Eligibility check (education + experience vs. Annex II) | Nothing | ❌ |
| Competency alignment matrix (CV vs. field duty areas) | Nothing | ❌ |
| Strengths / gaps surface in plain English to the user | Closest: `/profile` page renders an LLM-generated soft-dimension narrative (Leonardo's session 4) | 🟡 narrative yes, no eligibility verdict |
| Priority ranking by `gap_score = weight × (1 - readiness)` | Nothing | ❌ |
| Optional self-assessment Likerts | ✅ Intake has `self_habits_score`, `self_strategy_score`, `self_eu_breadth_score` | ✅ |
| Optional past EPSO test results / mock scores | The 5-item calibration on `/diagnostic` produces verbal scores; no path to import external scores | 🟡 partial |
| **Optimistic-but-realistic framing** ("with proper study you drastically increase your chances") | The current `/profile` narrative is neutral; does not frame chances | ❌ |
| First "wow effect" moment | The `/profile` page has it partially via the LLM narrative | 🟡 |

**Net gap:** CV upload + LLM eligibility check + competency-alignment matrix + framing.

**Priority recommendation:** **high**. Stefano explicitly frames this as the first user "wow" moment, and the schema is already designed for it (`cv_storage_path`, `cv_fit_modifier`). Leonardo's session-4 LLM narrative is the right shape; we just need to feed it richer inputs.

---

### Thread 3 — Master Plan ✅ MOSTLY SHIPPED

| Stefano's spec says | We have today | Status |
|---|---|---|
| Phase-based preparation calendar (foundations → practice → simulation) | Leonardo's `backend/logic/planning.py` produces per-skill weekly minute allocation | 🟡 minutes not phases |
| Weekly effort allocation per test component | ✅ | ✅ |
| Measurable milestones ("80% accuracy on numerical by week 4") | ❌ — current plan produces minutes, not accuracy targets | ❌ |
| Phased review weeks built in | ❌ | ❌ |
| **Theory study material inferred from competition notice** (e.g. PM methodologies, EU policies) — Stefano's note | ❌ — Compass generates *practice items* but not theory content | ❌ |
| User reviews and approves before storage | ❌ — currently the plan is auto-generated and committed | ❌ |
| Live plan revisions from Thread 8 / Compass replan trigger | `replan_signal()` exists; tells `/me` to suggest a refresh; user clicks regenerate | ✅ |

**Net gap:** phases (vs minutes), measurable milestones, theory content suggestions, user-in-the-loop approval step.

**Priority recommendation:** medium. The plan engine works at v1 quality and the replan loop is wired. Phases + milestones is a meaningful upgrade for the "what should I do this week?" question; user approval is a UX add.

---

### Thread 4 — Daily Plan & Execution 🟡 PARTIAL

| Stefano's spec says | We have today | Status |
|---|---|---|
| Daily session plan: ordered activities with durations | ✅ — `generate_daily_plan()` produces an ordered task list from `weekly_hours` + energy pattern | ✅ |
| Specific exercise prescriptions linked to a target component | Plans reference `skill_id` but no deep-link into Compass yet | 🟡 |
| Post-session debrief prompts | ❌ | ❌ |
| Auto-link from daily plan into Compass with right skill/length pre-set | ❌ — deferred to a future follow-up per ROADMAP §4.5 | ❌ |
| **"Let's study now" big-button on home page with dashboard of evolution** — Stefano's UX note | ❌ — `/me` has the recent-sessions panel but no single dominant CTA | ❌ |
| Micro-adjustments to master plan based on flags | The trigger exists (`replan_signal`); the user-facing micro-adjustment UX does not | 🟡 |

**Net gap:** a clear daily CTA on `/me`, deep-linking from plan slots into `/compass`, the debrief flow.

**Priority recommendation:** **high for the CTA**; medium for the rest. The CTA is a one-day UX change that meaningfully changes the daily-open habit, which is a kill-criterion-sensitive variable (week-3 retention).

---

### Thread 5a — Verbal Reasoning ✅ SHIPPED (Compass v1)

| Stefano's spec says | We have today | Status |
|---|---|---|
| MCQ practice 5-20 items per session, calibrated difficulty | ✅ Compass `/compass` page (10/20/40 lengths, adaptive ±1 difficulty) | ✅ |
| Immediate feedback + explanations per answer | ✅ | ✅ |
| Session summary (score, avg time, error pattern analysis) | ✅ end-screen | ✅ |
| Flagged recurring error types (calculation, distractor traps, etc.) | ✅ — distractor-class tags per option; pattern-analysis LLM identifies clusters | ✅ |
| Structured log to Thread 8 | ✅ — `events.practice_completed` + `dimension_mastery` table | ✅ |
| EPSO-style item generation | ✅ — `backend/compass/generate_item.py` with 10 real EPSO anchors | ✅ |

**Net gap:** none of substance. Compass v1 covers verbal end-to-end at higher resolution than Stefano's spec (dimension tagging + per-option misconception classes + LLM pattern analysis).

---

### Thread 5b — Numerical Reasoning Clinic 🟡 SCHEMA YES, CONTENT NO

| Stefano's spec says | We have today | Status |
|---|---|---|
| Numerical MCQ with data tables, charts, text scenarios | ❌ no items in bank; generator is verbal-only | ❌ |
| "Clinic mode" — user submits a question type they find hard, system diagnoses + teaches + graduated practice | ❌ | ❌ |
| Adaptive practice across difficulty | The Compass engine already supports any `skill_id` — just no items for numerical | 🟡 engine yes, no items |

**Net gap:** the whole numerical content pipeline.

**Why this is hard:** the 5 EPSO numerical samples we have are all chart-based — the question text alone ("How much greater is the total GDP of the eurozone than that of Japan?") is meaningless without the embedded chart image. Text-only generation cannot replicate the real format. Options:
- (a) Generate items that include the data **inline as a small Markdown table** (sacrifices realism but works text-only)
- (b) Generate items whose data is delivered via a sidecar image that we generate
- (c) Stick with text-only "clinic" mode that teaches techniques and uses simpler text scenarios

**Priority recommendation:** medium. Stefano flags the **clinic sub-mode** as especially useful — that one is reachable with text-only items because it's diagnostic-and-teach, not exam-realism. Recommend shipping (c) first as "Compass v1.5 numerical clinic" and treating full numerical-with-charts as v2.

---

### Thread 5c — Abstract Reasoning ❌ NOT VIABLE TEXT-ONLY

| Stefano's spec says | We have today | Status |
|---|---|---|
| Abstract MCQ with visual patterns | ❌ — Compass is text-only | ❌ |
| Spec suggests "describes visual patterns in text form (or uses Unicode/ASCII representations)" | This works at the prompt level but produces a different test than real EPSO | ❌ |

**Net gap:** image generation, or honest scope cut.

**Priority recommendation:** **low for v1.5**; **defer** until either we add image generation (Anthropic's image-out is not in Claude yet; would need DALL-E or similar) or until pilot data shows users actually need it. EPSO weighting confirms abstract is the lowest-weight reasoning component in AD5/AD7 anyway.

---

### Thread 6 — Field MCQ Clinic ❌ NOT BUILT

| Stefano's spec says | We have today | Status |
|---|---|---|
| Field-specific MCQs from Annex II duty taxonomy | ❌ | ❌ |
| Topic-area coverage map | ❌ | ❌ |
| Substantive explanations referencing professional concepts + EU frameworks | ❌ | ❌ |
| Deep-research mode for background knowledge building | ❌ | ❌ |

**Net gap:** the entire FRMCQ feature.

**What we have that helps:** COGNITIVE_DIMENSIONS.md §2.4 designed FRMCQ dimensions (`authority_level_required`, `concept_application`, `version_sensitivity`, `operational_role_mapping`, etc.). The schema is ready; the generator + content domain inputs are not.

**Priority recommendation:** **high for AD7 specialist users**, low for AD5 generalist. FRMCQ is **the** ranking instrument for AD7 ICT (Stefano confirmed this in the cognitive-dimensions exercise). If we want to sell to AD7 candidates, this is the most important Compass feature after verbal.

---

### Thread 7 — EUFTE & Written Communication Lab ❌ NOT BUILT

| Stefano's spec says | We have today | Status |
|---|---|---|
| Timed EUFTE writing simulation | ❌ | ❌ |
| Structured feedback against 5 official anchors (relevance, structure, register, language, info use) | ❌ | ❌ |
| Annotated writing sample with inline commentary | ❌ | ❌ |
| EU terminology glossaries + institutional style refs | ❌ | ❌ |
| Source documents to write from (briefing notes, press releases, policy texts) | Leonardo's news scraper has 75 articles that could feed this | 🟡 source data exists |

**Net gap:** the entire EUFTE feature.

**What we have that helps:** COGNITIVE_DIMENSIONS.md §2.5 designed 9 written-test dimensions (`output_type_recognition`, `synthesis_transformation`, `audience_register_calibration`, etc.). And Leonardo's news scrape provides the source material.

**Priority recommendation:** **medium-high**. EUFTE counts 15% of AD5 ranking score (Stefano's deep-research output verified) and is mandatory for every in-scope competition. Bigger ROI than abstract reasoning. Generator architecture would be different (open-text grading, not MCQ).

---

### Thread 8 — Performance Tracker & Adaptive Loop ✅ SHIPPED (Compass v1)

| Stefano's spec says | We have today | Status |
|---|---|---|
| Running performance dashboard per test type | ✅ — `/me` shows recent practice + insight panel | ✅ |
| Weekly trend analysis (improving / stable / regressing) | 🟡 pattern_analyses contains this info; dashboard doesn't render trends explicitly | 🟡 |
| Flagged persistent weak areas | ✅ — pattern-analysis LLM produces focus_dimensions + insight_md | ✅ |
| Adaptive plan adjustments — concrete recommendations to reallocate time | The replan signal fires; `/plan` can regenerate; not as concrete as Stefano's example ("from 3 to 5 sessions per week") | 🟡 |
| Pre-exam readiness assessment (probability of passing each component) | ❌ — not built | ❌ |
| Pattern detection triggered after 2-3 sessions, not weekly | ✅ — `should_refresh` runs after every session if ≥20 tagged answers + 30-min cooldown | ✅ |

**Net gap:** trend graph in the UI, more concrete reallocation recommendations, pre-exam readiness assessment.

**Priority recommendation:** medium. The core adaptive loop works. Trend graphs and pre-exam readiness are polish that helps the user *perceive* the system is working, distinct from whether it *is* working.

---

### Thread 9 — NotebookLM Content Studio ❌ NOT BUILT

| Stefano's spec says | We have today | Status |
|---|---|---|
| Curated source documents formatted for NotebookLM upload | ❌ | ❌ |
| Prompt templates for NotebookLM Audio Overview / Study Guide | ❌ | ❌ |
| Suggested podcast scripts or study guide outlines | ❌ | ❌ |
| Topical revision summaries | ❌ | ❌ |
| Content library index | ❌ | ❌ |

**Net gap:** everything.

**What we have that helps:** Leonardo's news scrape (75 articles), plus the 8 EPSO sample items, plus eventually anything generated by Compass — all of these can be source material for NotebookLM podcasts.

**Stefano's framing:** "almost free features that definitely create the wow effect. Super useful while commuting. Super boost for Field-Related knowledge in specialistic competitions."

**Roadmap today:** "Parked: NotebookLM prompt + content-pack library (`/labs` route) → ~session 7 if time."

**Priority recommendation:** **medium-high**. Stefano's framing is correct — this is "almost free" because Concourse does not generate audio, it generates *prompts and source packs that the user pastes into NotebookLM*. It is text generation on top of content we already have. Estimated effort: ~half a session for a v1 `/labs/notebooklm` page.

---

## Summary table — the 9 threads at a glance

| Thread | Stefano name | Status | Priority to move next |
|---|---|---|---|
| 1 | HQ & Vacancy Analysis | 🟡 raw data only (scraper) | Medium — needs ingestion pipeline + brief surface |
| 2 | Profile & GAP Analysis | 🟡 partial (Likerts + soft narrative, no CV/eligibility/matrix) | **High** — first wow moment, schema ready |
| 3 | Master Plan | ✅ shipped (minutes, no phases/milestones) | Medium — phases + milestones + theory-content suggestions |
| 4 | Daily Plan & Execution | 🟡 plan engine ✅; CTA + deep-link missing | **High** for the CTA (retention-sensitive) |
| 5a | Verbal Reasoning | ✅ shipped via Compass v1 | Done |
| 5b | Numerical Reasoning Clinic | ❌ no content | Medium — clinic mode reachable text-only |
| 5c | Abstract Reasoning | ❌ no content; image-dependent | Low — defer |
| 6 | Field MCQ Clinic (FRMCQ) | ❌ schema designed only | **High for AD7**, low for AD5 |
| 7 | EUFTE & Written Communication | ❌ schema designed; source data exists | Medium-high — 15% of AD5 ranking |
| 8 | Performance Tracker & Adaptive Loop | ✅ shipped via Compass v1 | Done; trend graph polish later |
| 9 | NotebookLM Content Studio | ❌ parked in roadmap | **Medium-high** — "almost free" wow feature |

---

## What is already in the ROADMAP and how Stefano's spec changes it

**Already on the roadmap, no change needed:**
- ✅ Master plan (§3 — shipped)
- ✅ Daily plan (§3 — shipped)
- ✅ Verbal calibration + practice (§4.5 Compass M1+M2+M3 — shipped)
- ✅ Adherence tracking (§3 — shipped via Leonardo's session 8)
- ✅ Replan trigger (§3 — shipped)

**On the roadmap, scope refined by Stefano's spec:**
- 🟡 **CV-fit modifier** (§3 Session 4 line, marked deferred) → Stefano elevates this to a first-class "GAP analysis" capability with eligibility verdict + alignment matrix + framing. Bring it forward.
- 🟡 **NotebookLM prompt + content-pack library** (§7 parked, "~session 7 if time") → Stefano elevates as wow feature. Promote from "parked" to scheduled.
- 🟡 **Compass numerical / abstract / EU-knowledge banks** (§4.5 "diagnostic breadth, replaced by Compass") → Stefano makes them concrete user-facing features with distinct UX (numerical *clinic* mode, EU-knowledge as theory + practice). Refine scope.

**Not on the roadmap at all (new from Stefano's spec):**
- 🆕 **Vacancy-notice ingestion** + canonical competition catalog + auto-generated brief (Thread 1)
- 🆕 **CV upload + eligibility check + competency-alignment matrix** (Thread 2 specifics — beyond the current CV-fit modifier sketch)
- 🆕 **FRMCQ generator + field duty taxonomy** (Thread 6) — schema exists, content + UX do not
- 🆕 **EUFTE writing simulation + 5-anchor feedback grader** (Thread 7)
- 🆕 **"Let's study now" home-page CTA + deep-link from plan slots into Compass** (Thread 4 user-flow note)
- 🆕 **Trend graphs + pre-exam readiness assessment on `/me`** (Thread 8 polish)
- 🆕 **Phased master plan with accuracy milestones** (Thread 3 refinement)
- 🆕 **Theory study material suggestions in the plan** (Thread 3 refinement)

---

## Recommended changes to add to ROADMAP §4.5 and §6

**§4.5 — extend the Compass M3 entry with explicit "what's next" sub-section:**

```
### Compass v1.x — content breadth (post-pilot)
Per Stefano spec 2026-06-23. Order = priority within Compass.

- Compass v1.5 — FRMCQ generator (AD7 ICT primary). Reuses generate_item() with
  new prompt builder, field duty taxonomy as content_domain seed, source material
  drawn from Leonardo's news scrape and uploaded reference docs.
- Compass v1.6 — EUFTE writing simulator. Open-text generator + LLM grader against
  5 official anchors. New table `eufte_attempts` with annotated-text storage.
- Compass v1.7 — Numerical reasoning clinic. Text-only graduated practice on
  technique types (compound %, ratio inversion, data tables). Defer
  chart-based numerical to v2.
- Compass v2 — abstract reasoning. Requires image generation; defer.
```

**§6 — extend pre-launch hardening with the four new features that block "good pilot":**

```
- Vacancy-notice ingestion + competition catalog: at minimum, pre-seed
  AD5/AD7 ICT/AST notices manually, surface as a competition picker on /intake.
  Full LLM-ingestion of new notices is post-pilot.
- CV upload + eligibility check (Thread 2): supabase storage, LLM extraction,
  alignment matrix on /profile. Mandatory for AD7, optional for AD5.
- "Let's study now" CTA on /me: single-button daily entry point that picks
  today's slot from the daily plan, deep-links into Compass with skill+length
  pre-set.
- NotebookLM prompt + content-pack library: a /labs/notebooklm page that
  takes a topic + competition family and outputs a NotebookLM-ready source
  doc + Audio Overview prompt. Stefano-flagged wow feature.
```

**§7 — open decisions, add:**

```
- [ ] **Competition catalog: pre-seeded or user-uploaded notices first?**
      Pre-seeding the 3-4 in-scope competitions is faster to ship; user-upload
      is more generalisable. Recommend pre-seed for pilot, add upload post-pilot.
- [ ] **Abstract reasoning scope cut?** Image-dependent. Stefano's spec
      proposes Unicode/ASCII representation as a fallback. Decide: ship
      ASCII version, defer entirely, or invest in image-gen.
- [ ] **FRMCQ AD7-first or all-fields?** AD7 ICT is in scope; do we want to
      also cover AD7 audit, economics, law, etc. at v1.5 or only ICT?
```

---

## Two strategic observations

**1. Stefano's automation comments confirm our orchestration is right.** The spec is full of "[STEFANO] this is automatic, the user doesn't need to prompt anything." Concourse already operates this way — the user signs up, the calibration runs, the plan generates, the practice triggers replan. The "9 threads" framing is a *design abstraction* he used to organise the capabilities. The implementation can keep its current shape (pages + Compass engine) without literally building nine chat threads.

**2. The five biggest user-perceived gaps converge on the same idea.** Vacancy ingestion, CV+GAP analysis, the "let's study now" CTA, NotebookLM packs, and the trend dashboard are all **moments where the user feels the system knows them and is doing the work for them.** Three of these are reachable in one or two evenings of work each. The pilot's week-3 retention number is probably more sensitive to these than to whether we have numerical generation working.

**Recommendation:** before opening pilot recruiting, ship the "high-priority" items from Stefano's spec (CV/GAP analysis upgrade + "let's study now" CTA + at minimum a competition picker), plus the NotebookLM `/labs` page if it really is half a session. That's ~3-5 sessions of work and gets us into pilot with a meaningfully more complete experience than verbal-only Compass alone.

---

**End of cross-walk.**

Send feedback to Giovanni. When Stefano + Leonardo agree on the new priority ordering, we update `ROADMAP.md` accordingly (single source of truth per `CLAUDE.md`) and start scheduling commits.
