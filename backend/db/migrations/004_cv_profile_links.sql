-- Concourse — migration 004: CV metadata + profile links (foundation flow)
-- Per the 2026-06-25 planning call: CV upload (Supabase Storage) + optional
-- LinkedIn / portfolio / other links feed the gap analysis and master plan.
--
-- profiles.cv_storage_path and profiles.cv_fit_modifier already exist (001_init).
-- This migration only ADDS the surrounding metadata + link columns.
--
-- Idempotent (add column if not exists) + transactional. Safe to re-run.
-- DO NOT run on the shared dev/prod Supabase without coordinating on Slack —
-- pick a window when no teammate is mid-test (CLAUDE.md "Database" rule).

begin;

alter table profiles add column if not exists cv_filename    text;       -- original upload name, for display
alter table profiles add column if not exists cv_uploaded_at timestamptz; -- when the current CV landed
alter table profiles add column if not exists linkedin_url   text;
alter table profiles add column if not exists portfolio_url  text;
alter table profiles add column if not exists other_links    jsonb;       -- ["https://…", …] extra docs/sites

commit;
