# EPSO sample-question benchmark scraper

Internal calibration tool. Collects EPSO's **publicly published sample reasoning
questions** so we can understand the real test *format, difficulty and structure*
and calibrate our own authored items (ROADMAP decision #5: "frame the in-product
check as a measurement instrument, not a practice tool").

## How it works

EPSO's reasoning samples are built with [H5P](https://h5p.org/). Each question is
an `H5P.MultiChoice` (or a container library) whose full content — passage,
question stem, options and the `correct` flag — is served as static JSON from a
public embed endpoint:

```
GET /h5p/<content_id>/embed   ->  window.H5PIntegration = { contents: { "cid-N": { jsonContent: "..." } } }
```

So **no headless browser and no login are needed** for these. The scraper:

1. Starts from the 9 sample-test category index pages.
2. Crawls internal sub-pages (per language / test type), depth-limited and polite.
3. On each page, finds `data-content-id="N"` H5P iframes.
4. Fetches `/h5p/N/embed`, parses `H5PIntegration`, normalizes each question.
5. Records `taocloud.org` LTI links as a **coverage gap** (those live tests — e.g.
   AD5 — sit behind LTI auth and are *not* extractable this way).

## Usage

```bash
# one category (recommended first run / POC)
venv/Scripts/python.exe tools/epso_benchmark/scrape.py --only 13624 --max-depth 1

# everything
venv/Scripts/python.exe tools/epso_benchmark/scrape.py

# politer / slower
venv/Scripts/python.exe tools/epso_benchmark/scrape.py --delay 2.5
```

Category node ids: `13571` AD5 · `13572` AD6-9 · `13624` AST · `13568` AST/SC ·
`13625` lawyer-linguists · `13573` lawyer-linguists (CoJ) · `13574` translators ·
`19144` FG I-II · `19145` FG III-IV.

## Output (`data/`, git-ignored)

| file | contents |
|---|---|
| `benchmark.json` | normalized items + `tao_refs` coverage gaps + crawl stats |
| `summary.md` | calibration stats: counts by category/type/library, option-count distribution, question-length stats, TAO gap |
| `raw_embeds/<id>.json` | per-content parsed H5P params (cache + audit trail) |

Re-running reuses `raw_embeds/` as a cache, so it won't re-hit the server for
content already fetched.

## News / notices / analysis scraper (`news_scrape.py`)

Extends the tool beyond reasoning *samples* to the surrounding editorial text —
official EPSO competition notices/news plus third-party analyses (the "ingest
concourses text / analyses / news" item from #product). Scoped as an **extension
of the internal calibration tool**, not user-facing content.

```bash
venv/Scripts/python.exe tools/epso_benchmark/news_scrape.py                 # all enabled sources
venv/Scripts/python.exe tools/epso_benchmark/news_scrape.py --source epso    # one source
venv/Scripts/python.exe tools/epso_benchmark/news_scrape.py --source orseu --max-articles 20
```

| source | where | status |
|---|---|---|
| `epso` | `eu-careers.europa.eu/en/news` (notices + news) | enabled |
| `orseu` | `orseu-concours.com/fr/blog` | enabled |
| `europapp` | `europapp.eu` blog sitemaps (EN + ES) | enabled |
| `eutraining` | `eutraining.eu` | **disabled** — robots.txt disallows AI bots + `ai-train=no`, Cloudflare 403 to non-browser UAs. Not scraped pending a separate decision. |

- Honours each host's `robots.txt` (stdlib `urllib.robotparser`); disallowed URLs
  are skipped, not fetched. Same polite `Crawler` as `scrape.py`.
- Output under `data/news/`: `articles.json`, `summary.md`, `raw/<source>/*.html`
  (raw cache = audit trail + offline re-parse). The article-link regexes are
  permissive and may need a tweak after the first live run (every URL is validated
  by the extractor, so over-capture is harmless).

## Scope & ethics — read before sharing output

- EPSO marks these samples *"for illustration purposes only … not training
  materials."* This dataset is for **internal calibration only**. Do **not** serve
  the scraped text to users — an integrated question bank is explicitly **out of
  MVP scope** (ROADMAP §7).
- The `data/` directory is git-ignored on purpose; do not commit scraped text.
- The crawler is single-threaded, identifies itself via `User-Agent`, sleeps
  between requests and backs off on errors. Keep `--delay` ≥ 1s. Don't parallelize.
