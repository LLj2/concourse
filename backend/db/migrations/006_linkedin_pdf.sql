-- Concourse — migration 006: LinkedIn profile PDF (foundation flow)
-- Per #product (2026-06-25): there's no clean way to pull a LinkedIn profile via
-- URL/API/scraping. The chosen path is the user's own "Save to PDF" export
-- (desktop: profile → More → Save to PDF), uploaded and parsed like a CV. We store
-- it as a second document alongside the CV; its text feeds the CV-fit read.
--
-- Idempotent + transactional. Coordinate before running on the shared DB.

begin;

alter table profiles add column if not exists linkedin_pdf_path        text;
alter table profiles add column if not exists linkedin_pdf_filename    text;
alter table profiles add column if not exists linkedin_pdf_uploaded_at timestamptz;

commit;
