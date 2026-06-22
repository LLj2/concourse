# EPSO benchmark scraper — progress note

**Date:** 2026-06-22 · **Owner:** Leo · Status: **working POC, English AST set complete**

Internal calibration tool that harvests EPSO's *publicly published* sample
reasoning questions so we can understand the real test format/difficulty and
calibrate our own authored items (ROADMAP decision #5). Internal research only —
not a user-facing question bank (out of MVP scope).

## What we built

- `scrape.py` — extracts EPSO sample questions from the H5P embed endpoint.
- `download_images.py` — pulls the stimulus images (tables/diagrams) via the
  `.h5p` export packages.
- `README.md` — usage + ethics/scope notes. Output lives in `data/` (git-ignored).

## Key technical findings

- **No browser / no login needed for reasoning samples.** EPSO builds them with
  H5P. Full content (passage, question, options, `correct` flag) is static JSON at
  `GET /h5p/<content_id>/embed` → `window.H5PIntegration`. This was the unlock —
  initial assumption (TAO Cloud + LTI auth) was only true for *some* categories.
- **Stimulus images** (numerical tables, abstract diagrams) aren't in the page;
  they ship inside the per-content `.h5p` export zip
  (`/sites/default/files/tmp/exports/interactive-content-<id>.h5p`) under
  `content/images/`. We download + extract those.
- **EPSO rate-limits hard (HTTP 429).** Crawler is single-threaded, identifies
  itself, sleeps between requests, and backs off (3→6→12→24→48s). Full multilingual
  crawl gets throttled badly; English-only is fast and representative.

## What we accomplished

**English AST set: 25 items, fully extracted + verified.**

| Type | Items | Options | Stimulus |
|---|---|---|---|
| Verbal | 10 | 4 (A–D) | text passage (~700–800 chars) — complete |
| Numerical | 5 | 5 (A–E) | data table → **15 images downloaded** |
| Abstract | 10 | 5 (A–E) | diagram series → (incl. above) |

All single-best-answer. Verified one numerical table image visually (GDP/area/
population table) — matches its question. Output: `data/benchmark.json`,
`data/images/<id>/*.jpg`, `data/summary.md`.

### Calibration takeaway

- **Verbal** is fully reproducible from text → we can build a faithful text-only
  benchmark and calibrate authored verbal items against it.
- **Numerical / Abstract** are image-based → the question text alone is just a
  shell; the real stimulus is the downloaded image. Calibrate these against the
  images, not the text.

## Open points

- [ ] **More categories.** We only did AST so far. To also cover AD6–9,
      secretaries, translators and FG I–IV we just re-run the scraper on those
      pages (English-only, slow delays so we don't trip the 429 rate-limit).
- [ ] **Some tests we can't reach.** AD5 graduates (maybe others) run live on
      "TAO Cloud", which sits behind a login — our trick doesn't work there. We
      logged their URLs as `tao_refs` in `benchmark.json`; separate decision
      needed on whether they're worth the extra effort.
- [ ] **Other languages.** EPSO publishes in 24 languages; we only grabbed
      English. Not needed to learn the test format, so deferred — and it'd mean
      much slower crawling to stay polite.
