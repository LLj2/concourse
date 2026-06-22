-- Concourse — Compass commit 1: cognitive dimensions + practice sessions
-- Schema-only migration. No Python changes; existing calibration flow keeps working.
-- Idempotent: safe to re-run (uses if not exists / add column if not exists).
--
-- Scope (per COMPASS_ROADMAP.md M1 / COGNITIVE_DIMENSIONS.md):
--   1. Items get dimension/option_diagnostics/competition_family/content_domain/topic_tag/derived JSONB
--   2. New tables: practice_sessions, dimension_mastery, pattern_analyses
--   3. item_responses: add practice_session_id (nullable, sibling to session_id),
--      relax session_id to NULL-able, add CHECK enforcing exactly one is set,
--      add distractor_class_picked text[] for the picked-misconception trail
--   4. Indexes for hot paths
--
-- Run from a Python session against the SQLAlchemy engine (see run_migration_003.py),
-- or paste into Supabase SQL Editor.

begin;

-- =============================================================================
-- 1. Extend items with cognitive-dimension tagging
-- =============================================================================

alter table items add column if not exists competition_family text;
alter table items add column if not exists content_domain    text[];
alter table items add column if not exists dimensions        jsonb;
alter table items add column if not exists option_diagnostics jsonb;
alter table items add column if not exists derived           jsonb;
alter table items add column if not exists topic_tag         text;

-- existing items.source already exists (default null) — no change needed.
-- existing items default values stay; null dimensions are explicit "not yet tagged".

-- Index for the practice picker's "unseen item at target dimension" query.
-- Partial index: only active items, only those with dimensions assigned.
create index if not exists idx_items_skill_diff_active
    on items(skill_id, difficulty, archived) where archived = false;

create index if not exists idx_items_topic_tag
    on items(skill_id, topic_tag) where archived = false and topic_tag is not null;

-- =============================================================================
-- 2. Practice sessions (sibling to diagnostic_sessions)
-- =============================================================================

create table if not exists practice_sessions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    skill_id text not null references skills(id),
    started_at timestamptz not null default now(),
    completed_at timestamptz,
    items_attempted int not null default 0,
    items_correct int not null default 0,
    -- target length the user picked: short=10, standard=20, long=40
    target_length int not null default 20 check (target_length between 1 and 100),
    -- if this session was launched from a daily plan slot
    plan_id uuid references plans(id),
    -- median item time at finalization, for the dimensional end-screen
    median_time_ms int
);

create index if not exists idx_practice_user_skill
    on practice_sessions(user_id, skill_id, completed_at desc);

-- =============================================================================
-- 3. item_responses: add practice_session_id + distractor trail
-- =============================================================================

-- Relax session_id to allow practice rows where it's null.
-- All existing rows have session_id set (diagnostic only so far) — no data change.
alter table item_responses alter column session_id drop not null;

-- New sibling FK. Nullable; exactly one of (session_id, practice_session_id) is set per row.
alter table item_responses add column if not exists practice_session_id uuid
    references practice_sessions(id) on delete cascade;

-- Trail of misconception tags the user picked when wrong.
-- Read from items.option_diagnostics[selected_index].distractor_classes at answer time.
alter table item_responses add column if not exists distractor_class_picked text[];

-- Exactly-one constraint. Idempotent via the do-block.
do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'item_responses_session_xor'
    ) then
        alter table item_responses add constraint item_responses_session_xor
            check (
                (session_id is not null and practice_session_id is null)
             or (session_id is null and practice_session_id is not null)
            );
    end if;
end$$;

create index if not exists idx_item_responses_practice
    on item_responses(practice_session_id) where practice_session_id is not null;

-- =============================================================================
-- 4. Dimension mastery (per-user × skill × dimension-value rolling accuracy)
-- =============================================================================

-- One row per (user, skill, dimension_name, dimension_value). Updated on every answer.
-- Composite PK enforces uniqueness — the practice engine upserts on this.
create table if not exists dimension_mastery (
    user_id          uuid not null references users(id) on delete cascade,
    skill_id         text not null references skills(id),
    dimension_name   text not null,
    -- Stringified value for ord/bool/cat. The dimensions JSONB on items carries the typed value;
    -- we serialize to text here so the PK works across types.
    dimension_value  text not null,
    attempts         int not null default 0,
    correct          int not null default 0,
    last_updated     timestamptz not null default now(),
    primary key (user_id, skill_id, dimension_name, dimension_value)
);

-- Hot query: per-user mastery dump for the LLM pattern-analysis pass.
create index if not exists idx_mastery_user_skill
    on dimension_mastery(user_id, skill_id);

-- =============================================================================
-- 5. Pattern analyses (LLM output: focus dimensions + plain-English insight)
-- =============================================================================

-- Append-only. Latest row per (user, skill) wins.
create table if not exists pattern_analyses (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    skill_id text not null references skills(id),
    generated_at timestamptz not null default now(),
    -- [{dimension_name, dimension_value}, ...] — drives the next session's slot targets
    focus_dimensions jsonb not null,
    -- 80-150 word plain-English insight rendered on /me
    insight_md text,
    -- Anthropic model id used for the analysis call (audit + drift detection)
    model_version text,
    -- Full LLM payload for debugging / future replay (patterns, evidence_dims, confidence)
    payload jsonb
);

create index if not exists idx_pattern_user_skill_recent
    on pattern_analyses(user_id, skill_id, generated_at desc);

-- =============================================================================
-- 6. Lightweight assertions (smoke tests that the migration didn't break existing data)
-- =============================================================================

-- These run inside the transaction. If any fail, the migration rolls back.

do $$
declare
    n_skills int;
    n_verbal_items int;
    n_existing_responses int;
begin
    select count(*) into n_skills from skills;
    if n_skills < 4 then
        raise exception 'expected at least 4 skills, found %', n_skills;
    end if;

    select count(*) into n_verbal_items from items where skill_id = 'verbal' and not archived;
    if n_verbal_items < 8 then
        raise exception 'expected at least 8 verbal items, found %', n_verbal_items;
    end if;

    -- All existing item_responses should still pass the XOR (they all have session_id set).
    select count(*) into n_existing_responses
    from item_responses
    where not ((session_id is not null and practice_session_id is null)
            or (session_id is null and practice_session_id is not null));
    if n_existing_responses > 0 then
        raise exception 'XOR constraint would reject % existing rows', n_existing_responses;
    end if;

    raise notice 'migration 003 passed: % skills, % verbal items, % responses XOR-clean',
        n_skills, n_verbal_items,
        (select count(*) from item_responses);
end$$;

commit;
