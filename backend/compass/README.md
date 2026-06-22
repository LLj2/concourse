# Compass — the adaptive practice engine

> **All Compass code lives here.** This package is intentionally sealed: existing app code does not import from `backend/compass/`, and Compass reads from the shared schema (`items`, `users`, `events`, etc.) but does not modify the legacy modules under `backend/logic/`, `backend/ai/`, or `backend/auth/`.
>
> **To remove Compass entirely:** `rm -rf backend/compass/` + `git rm backend/db/migrations/003_*.sql` + revert the one `include_router(compass.api.router)` line in `backend/main.py`. The rest of the app keeps working.

## Why isolated

Compass is the strategic moat — it's also the highest-uncertainty piece of the product. If the cognitive-dimensions schema turns out to be wrong, if the LLM-generated items are too noisy, or if pattern detection doesn't produce useful insights, we need to be able to **rip it out without unwinding the planner**. Keeping it in its own namespace from day one makes that surgical instead of archaeological.

It also makes the blast radius of every change to Compass visible: any file change under `backend/compass/` is a Compass change; nothing else is.

## Folder structure

| Path | Purpose | Lands in |
|---|---|---|
| `compass/__init__.py` | Package marker | Commit 1 |
| `compass/few_shot/` | Real EPSO items used as LLM prompt anchors | Commit 1 (verbal anchors); commit 2+ (other skills if/when) |
| `compass/prompts/` | Per-skill generation prompts | Commit 2 |
| `compass/generate_item.py` | `generate_item(skill, difficulty, target_dims, …) -> dict` | Commit 2 |
| `compass/practice.py` | Practice picker, session lifecycle, mastery updates | Commit 3 |
| `compass/api.py` | FastAPI router mounted at `/api/compass/*` and `/compass` | Commit 3+ |
| `compass/patterns.py` | LLM pattern-analysis worker | Commit 5 |
| `compass/validation.py` | Discrimination + predictivity + emergent-cluster queries | Commit 6 |
| `compass/static/` | `compass.html` and any Compass-specific frontend | Commit 4 |

## URL namespace

Every Compass-served URL sits under one prefix:

| URL | Purpose |
|---|---|
| `GET /compass` | Practice page (skill + length picker) |
| `POST /api/compass/practice/start` | Begin a practice session |
| `POST /api/compass/practice/answer` | Submit an answer |
| `POST /api/compass/practice/end` | Manual quit |
| `GET /api/compass/practice/recent` | Recent sessions for `/me` widget |
| `GET /api/compass/insight` | Latest LLM-generated insight for `/me` panel |
| `POST /api/compass/patterns/refresh` | Force a pattern-analysis run (testing) |
| `GET /api/compass/admin/health` | Dimension-health dashboard (admin-gated) |

`/me` still lives in `backend/main.py`. It calls `/api/compass/insight` and `/api/compass/practice/recent` if available — both endpoints return 404 cleanly if Compass is removed, and `/me` degrades gracefully.

## Schema touch-points

Migration 003 (`backend/db/migrations/003_dimensions_and_practice.sql`) is the only schema work Compass needs. It is:

- **Additive on `items`**: 6 new nullable columns. Existing rows keep working.
- **Sibling table on `item_responses`**: relaxes `session_id` to NULLABLE, adds `practice_session_id`, adds a CHECK constraint enforcing exactly one is set per row.
- **New tables**: `practice_sessions`, `dimension_mastery`, `pattern_analyses`.

A rollback script lives at `backend/db/migrations/003_rollback.sql` — drop the new tables, drop the new columns, restore `item_responses.session_id NOT NULL`. Safe to run if nothing has been written to the Compass tables yet.

## Dependencies — what Compass reads, what it writes

| Resource | Compass reads | Compass writes |
|---|---|---|
| `users` | id, email | — |
| `skills` | id | — |
| `items` (existing rows) | all | — |
| `items` (new generated rows) | all | `dimensions`, `option_diagnostics`, `topic_tag`, `source='generated'`, etc. |
| `item_responses` | by user_id | new rows with `practice_session_id` set |
| `practice_sessions` | own | own |
| `dimension_mastery` | own | own |
| `pattern_analyses` | own | own |
| `events` | own kinds (`practice_completed`, `pattern_updated`, `dimension_mastery_updated`) | append-only |

Existing code (`backend/logic/diagnostic.py`, `scoring.py`, `planning.py`, `adherence.py`) does not import anything under `backend/compass/`. The opposite would be a code smell — review-flag any such import.

## How to extend Compass

When adding a new feature to Compass:

1. Put new modules under `backend/compass/`.
2. Mount new routes on `compass.api.router` (which is already prefix-aware).
3. If you need to read existing tables, use raw SQL or your own narrow query helpers — don't reach into `backend/logic/*` modules.
4. If you need a new DB object, write a new migration (`004_compass_*.sql`) that's additive only.

If you find yourself wanting to modify a file outside `backend/compass/` for a Compass change, **stop and reconsider**. That's the moment isolation pays off — re-route the change so it can live inside the namespace instead.
