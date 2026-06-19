-- Concourse — initial schema for Supabase Postgres (EU region)
-- Run via the Supabase SQL editor, or via psql against the pooler URL.
-- All datetimes are TIMESTAMPTZ in UTC. Display layer converts to user TZ.

-- =============================================================================
-- Users (lightweight; Supabase Auth handles credentials separately if used)
-- =============================================================================
create table if not exists users (
    id uuid primary key default gen_random_uuid(),
    email text not null unique,
    created_at timestamptz not null default now(),
    -- UTM captured at signup, persisted for CAC attribution
    utm_source text,
    utm_medium text,
    utm_campaign text,
    utm_content text,
    utm_term text,
    -- Stripe lifecycle
    stripe_customer_id text unique,
    stripe_subscription_id text unique,
    subscription_status text,  -- 'trialing' | 'active' | 'past_due' | 'canceled' | null
    trial_ends_at timestamptz
);

-- =============================================================================
-- Profile (intake answers + soft-dimension Likerts + CV pointer)
-- =============================================================================
create table if not exists profiles (
    user_id uuid primary key references users(id) on delete cascade,
    -- target competition (free text for MVP; AD5/AD7 most common)
    target_competition text,
    weeks_to_exam int,
    weekly_hours int,
    energy_pattern jsonb,                 -- {"morning": "high", "evening": "low"}
    -- self-assessment (replaces a long mandatory diagnostic at intake)
    has_prior_epso_experience boolean,
    last_epso_test_at date,               -- null if never
    -- Likert 1-5 scales for soft dimensions the LLM cannot infer reliably
    self_habits_score int,                -- preparation habits
    self_strategy_score int,              -- test strategy familiarity
    self_eu_breadth_score int,            -- self-reported EU knowledge breadth
    -- CV
    cv_storage_path text,                 -- Supabase storage path
    cv_fit_modifier jsonb,                -- LLM output: {"reasoning_skew_pct": 20, "go_no_go": "ok", "alternatives": [...]}
    -- timestamps
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- =============================================================================
-- Diagnostic item bank
-- =============================================================================
-- Skills we measure
create table if not exists skills (
    id text primary key,           -- 'verbal' | 'numerical' | 'abstract' | 'eu_knowledge'
    display_name text not null
);

create table if not exists items (
    id uuid primary key default gen_random_uuid(),
    skill_id text not null references skills(id),
    difficulty int not null,       -- 1 easy, 2 medium, 3 hard
    prompt text not null,
    options jsonb not null,        -- ['A', 'B', 'C', 'D']
    correct_index int not null,
    explanation text,
    -- calibration (filled in over time as users answer)
    times_shown int not null default 0,
    times_correct int not null default 0,
    -- soft-deletable
    archived boolean not null default false,
    source text,                   -- 'authored' | 'licensed:<vendor>' | 'imported'
    created_at timestamptz not null default now()
);
create index if not exists idx_items_skill_active on items(skill_id, archived) where archived = false;

-- =============================================================================
-- Diagnostic sessions (each measurement event)
-- =============================================================================
create table if not exists diagnostic_sessions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    skill_id text not null references skills(id),
    -- 'intake' = optional baseline, 'periodic' = ongoing measurement
    kind text not null check (kind in ('intake', 'periodic')),
    started_at timestamptz not null default now(),
    completed_at timestamptz,
    score numeric,                 -- 0-100, percent correct
    items_answered int not null default 0,
    median_time_ms int
);
create index if not exists idx_diag_user_skill on diagnostic_sessions(user_id, skill_id, completed_at desc);

create table if not exists item_responses (
    id uuid primary key default gen_random_uuid(),
    session_id uuid not null references diagnostic_sessions(id) on delete cascade,
    item_id uuid not null references items(id),
    selected_index int,
    is_correct boolean,
    time_taken_ms int,
    answered_at timestamptz not null default now()
);

-- =============================================================================
-- External logs (Layer B — paste/screenshot from EUTraining, ORSEU, etc.)
-- This is first-class because Stefano flagged that EPSO users *will* log.
-- =============================================================================
create table if not exists external_logs (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    skill_id text references skills(id),     -- nullable if user did not specify
    source_platform text,                    -- 'eutraining' | 'orseu' | 'epsoready' | 'other'
    items_attempted int,
    items_correct int,
    score_pct numeric,
    raw_input text,                          -- original paste / OCR text
    parsed_payload jsonb,                    -- LLM extraction result
    logged_at timestamptz not null default now()
);
create index if not exists idx_external_user_skill on external_logs(user_id, skill_id, logged_at desc);

-- =============================================================================
-- Plans (master + daily, generated by the rule engine)
-- =============================================================================
create table if not exists plans (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    -- 'master' = the per-week allocation; 'daily' = today's session
    kind text not null check (kind in ('master', 'daily')),
    -- ISO week start date (Monday) for master plans; date for daily
    period_start date not null,
    period_end date,
    -- per-skill allocation in minutes/week (for master) or task list (for daily)
    allocation jsonb not null,
    rationale_md text,                       -- LLM-narrated reasoning
    superseded_by uuid references plans(id),
    created_at timestamptz not null default now(),
    -- what triggered this plan (so we can show "plan updated because X")
    trigger_kind text,                       -- 'intake' | 'manual' | 'diagnostic' | 'external_log' | 'weekly_floor'
    trigger_event_id uuid                    -- references events.id (no FK to keep loose coupling)
);
create index if not exists idx_plans_user_active on plans(user_id, kind, period_start desc) where superseded_by is null;

-- =============================================================================
-- Adherence (Layer C — one-tap daily confirmation)
-- =============================================================================
create table if not exists adherence (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    plan_id uuid references plans(id),
    day date not null,
    status text not null check (status in ('done', 'partial', 'skipped')),
    minutes_actual int,                      -- optional numeric entry
    note text,
    logged_at timestamptz not null default now(),
    unique (user_id, day)
);

-- =============================================================================
-- Events (audit + replan triggers + analytics fallback)
-- =============================================================================
create table if not exists events (
    id uuid primary key default gen_random_uuid(),
    user_id uuid references users(id) on delete cascade,
    kind text not null,                      -- 'signup' | 'trial_started' | 'paid' | 'diagnostic_completed' | 'external_log_added' | 'plan_generated' | ...
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);
create index if not exists idx_events_user_kind on events(user_id, kind, created_at desc);

-- =============================================================================
-- Seed: skills
-- =============================================================================
insert into skills(id, display_name) values
    ('verbal', 'Verbal reasoning'),
    ('numerical', 'Numerical reasoning'),
    ('abstract', 'Abstract reasoning'),
    ('eu_knowledge', 'EU knowledge')
on conflict (id) do nothing;
