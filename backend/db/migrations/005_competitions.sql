-- Concourse — migration 005: Competition Catalog table (foundation flow)
-- Holds the factual EPSO competition data scraped by
-- tools/epso_benchmark/catalog_scrape.py (ref, grade, deadline, selection tests,
-- official Notice link). Feeds the gap analysis + Draft plan: the plan tells the
-- candidate which tests THEIR competition actually uses.
--
-- Loaded by tools/epso_benchmark/load_catalog.py (upsert by ref). The data is
-- public, official competition-notice information — product reference data.
--
-- Idempotent + transactional. DO NOT run on the shared Supabase without
-- coordinating on Slack (CLAUDE.md "Database" rule).

begin;

create table if not exists competitions (
    id uuid primary key default gen_random_uuid(),
    -- slug (detail-page segment) is the natural key: one row per competition page.
    -- ref is NOT unique — multi-field competitions (e.g. EPSO/AD/429/26 fields 1-4)
    -- share one base reference across several detail pages.
    slug text unique,                 -- 'graduate-administrators', 'data-science', …
    ref text,                         -- 'EPSO/AD/427/26' (null for upcoming announcements)
    url text,
    title text not null,
    grade text,                       -- 'AD 5'
    grade_family text,                -- 'AD' | 'AST' | 'AST-SC' | 'FG'
    field text,                       -- sub-field for multi-field competitions
    status text,                      -- 'open' | 'in-progress' | 'upcoming' | 'closed'
    deadline date,
    tests jsonb,                      -- ['reasoning','eu_knowledge', ...] (canonical names)
    notice_url text,
    eligibility_url text,
    summary text,
    updated_at timestamptz not null default now()
);
create index if not exists idx_competitions_status on competitions(status);
create index if not exists idx_competitions_grade_family on competitions(grade_family);
create index if not exists idx_competitions_ref on competitions(ref);

-- Link a candidate to the specific competition they're targeting (optional;
-- the Draft plan falls back to a grade-family test map when this is null).
alter table profiles add column if not exists target_competition_ref text;

commit;
