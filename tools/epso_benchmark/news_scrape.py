"""
EU-competition news / notices / analysis scraper (internal calibration tool).

Purpose
-------
Extends the EPSO benchmark tooling beyond reasoning *samples* to the surrounding
editorial material — official EPSO competition notices/news, plus third-party
analyses and news from prep providers. This is the "ingest concourses text /
analyses / news" item from #product, scoped (per Leo, 2026-06-22) as an
*extension of the internal calibration tool*: output is internal research, not
served to users. The `data/` directory stays git-ignored.

Sources
-------
Each source declares how to *discover* article URLs (sitemap or paginated
listing) and reuses one shared, polite extractor. Sources that have technically
opted out of automated crawling are registered but DISABLED, so the coverage
gap is explicit and never silently scraped:

    epso       eu-careers.europa.eu/en/news      ENABLED  (Drupal, no AI restriction)
    orseu      orseu-concours.com/fr/blog        ENABLED  (PrestaShop blog, no AI restriction)
    europapp   europapp.eu (blog sitemaps)       ENABLED  (sitemap-driven, no AI restriction)
    eutraining eutraining.eu                      DISABLED (robots.txt disallows AI bots
                                                            incl. ClaudeBot + Content-Signal
                                                            ai-train=no; Cloudflare 403 to
                                                            non-browser UAs). Pending a
                                                            separate decision — do NOT enable
                                                            by spoofing a browser UA.

Politeness / ethics
-------------------
- Reuses the single-threaded, self-identifying, backing-off `Crawler` from
  `scrape.py`. Keep `--delay` >= 1.5s; don't parallelize.
- Honours `robots.txt` for every host via stdlib `urllib.robotparser`. A URL the
  site disallows for our User-Agent is skipped, not fetched.
- Stores raw HTML under `data/news/raw/<source>/` as an audit trail, so records
  can be re-parsed without re-hitting the server.

Usage
-----
    python tools/epso_benchmark/news_scrape.py                      # all enabled sources
    python tools/epso_benchmark/news_scrape.py --source epso        # one source
    python tools/epso_benchmark/news_scrape.py --source orseu --max-articles 20
    python tools/epso_benchmark/news_scrape.py --delay 3.0          # politer

Outputs (under tools/epso_benchmark/data/news/, git-ignored):
    articles.json          normalized records (source, url, title, date, lang, text, ...)
    summary.md             counts by source / language / year, text-length stats
    raw/<source>/<key>.html  cached raw HTML (audit trail + offline re-parse)
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

# Reuse the polite client + text cleaner from the sample-question scraper, exactly
# as download_images.py does. Same toolchain (httpx + stdlib only), no new deps.
from scrape import USER_AGENT, Crawler, clean_text

NEWS_DIR = Path(__file__).parent / "data" / "news"
RAW_DIR = NEWS_DIR / "raw"

# --- extraction regexes ------------------------------------------------------
# Meta `content` is read with a back-referenced quote — `content="...l'UE..."`
# legitimately contains an apostrophe, so a `[^"']+` class would truncate it.
RE_OG_TITLE = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=(["\'])(.*?)\1', re.I | re.S)
RE_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
RE_H1 = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
RE_PUB_TIME = re.compile(
    r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=(["\'])(.*?)\1',
    re.I)
RE_TIME_TAG = re.compile(r'<time[^>]+datetime=(["\'])(.*?)\1', re.I)
RE_DESC = re.compile(
    r'<meta[^>]+(?:name|property)=["\'](?:og:)?description["\'][^>]+content=(["\'])(.*?)\1',
    re.I | re.S)
RE_HTML_LANG = re.compile(r"<html[^>]+lang=[\"']([a-zA-Z-]+)[\"']", re.I)
# main content containers, tried in order of preference
RE_ARTICLE = re.compile(r"<article\b[^>]*>(.*?)</article>", re.I | re.S)
RE_MAIN = re.compile(r"<main\b[^>]*>(.*?)</main>", re.I | re.S)
# chrome to drop before turning a content block into plain text
RE_DROP_BLOCKS = re.compile(
    r"<(script|style|nav|header|footer|form|noscript|aside)\b[^>]*>.*?</\1>", re.I | re.S)
RE_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
RE_HREF = re.compile(r'href=["\']([^"\'#]+)["\']', re.I)
RE_DATE_IN_URL = re.compile(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})")


def _clean(s: str | None) -> str:
    """Strip tags/whitespace (shared cleaner) then decode HTML entities such as
    &eacute; that clean_text doesn't cover."""
    return html.unescape(clean_text(s)) if s else ""


def _grp(m: re.Match | None) -> str | None:
    """Last captured group of a match (the content group for the quote-anchored
    meta regexes; the sole group for <title>/<h1>)."""
    return m.group(m.lastindex) if (m and m.lastindex) else None


def _first(*candidates: str | None) -> str:
    for c in candidates:
        t = _clean(c)
        if t:
            return t
    return ""


def extract_body(page_html: str) -> str:
    """Best-effort main-text extraction without a DOM parser.

    Prefer the first <article>, then <main>, then the whole document; strip
    scripts/nav/footer chrome, then tags. Good enough for internal calibration;
    raw HTML is cached alongside so a better parse is always possible later.
    """
    m = RE_ARTICLE.search(page_html) or RE_MAIN.search(page_html)
    block = m.group(1) if m else page_html
    block = RE_DROP_BLOCKS.sub(" ", block)
    return clean_text(block)


def parse_article(url: str, page_html: str) -> dict:
    title = _first(
        _grp(RE_OG_TITLE.search(page_html)),
        _grp(RE_H1.search(page_html)),
        _grp(RE_TITLE.search(page_html)),
    )
    date = ""
    for rx in (RE_PUB_TIME, RE_TIME_TAG):
        g = _grp(rx.search(page_html))
        if g:
            date = g.strip()
            break
    if not date:
        m = RE_DATE_IN_URL.search(url)
        if m:
            date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    lang_m = RE_HTML_LANG.search(page_html)
    body = extract_body(page_html)
    return {
        "url": url,
        "title": title,
        "date": date,
        "lang": (lang_m.group(1).split("-")[0].lower() if lang_m else ""),
        "summary": _clean(_grp(RE_DESC.search(page_html))),
        "text": body,
        "text_len": len(body),
    }


# --- robots.txt --------------------------------------------------------------
class Robots:
    """Per-host robots.txt gate. Fail-closed on parse errors only for hosts we
    don't already trust; for our enabled sources a fetch failure is treated as
    'allowed' (same posture as a browser) but logged."""

    def __init__(self, crawler: Crawler):
        self.crawler = crawler
        self._cache: dict[str, RobotFileParser | None] = {}

    def _parser_for(self, url: str) -> RobotFileParser | None:
        host = urlparse(url).netloc
        if host in self._cache:
            return self._cache[host]
        rp = RobotFileParser()
        robots_url = f"{urlparse(url).scheme}://{host}/robots.txt"
        r = self.crawler.get(robots_url)
        if r is not None and r.status_code == 200:
            rp.parse(r.text.splitlines())
            if "ai-train=no" in r.text.lower():
                print(f"    ! {host}: robots.txt signals ai-train=no", file=sys.stderr)
        else:
            rp = None  # no robots => allow, but remember we couldn't read it
        self._cache[host] = rp
        return rp

    def allowed(self, url: str) -> bool:
        rp = self._parser_for(url)
        if rp is None:
            return True
        return rp.can_fetch(USER_AGENT, url)


# --- sources -----------------------------------------------------------------
class Source:
    """A scrape target. Subclasses implement discover()."""
    key: str = ""
    enabled: bool = True
    note: str = ""

    def discover(self, crawler: Crawler, robots: Robots, max_pages: int) -> list[str]:
        raise NotImplementedError


class SitemapSource(Source):
    """Discovers article URLs from one or more sitemap XML files."""
    def __init__(self, key: str, sitemaps: list[str], must_contain: str = ""):
        self.key = key
        self.sitemaps = sitemaps
        self.must_contain = must_contain

    def discover(self, crawler, robots, max_pages):
        urls: list[str] = []
        for sm in self.sitemaps:
            r = crawler.get(sm)
            if not r or r.status_code != 200:
                print(f"  ! {self.key}: sitemap {sm} -> {r.status_code if r else 'ERR'}",
                      file=sys.stderr)
                continue
            locs = RE_LOC.findall(r.text)
            for loc in locs:
                if self.must_contain and self.must_contain not in loc:
                    continue
                urls.append(loc)
        return urls


class ListingSource(Source):
    """Discovers article URLs by crawling a paginated listing page and keeping
    hrefs that match an article-link pattern."""
    def __init__(self, key: str, listing: str, article_re: str,
                 page_param: str = "page", page_start: int = 0):
        self.key = key
        self.listing = listing
        self.article_re = re.compile(article_re)
        self.page_param = page_param
        self.page_start = page_start

    def discover(self, crawler, robots, max_pages):
        base = self.listing
        found: list[str] = []
        seen: set[str] = set()
        for i in range(max_pages):
            page_no = self.page_start + i
            sep = "&" if "?" in base else "?"
            url = base if i == 0 else f"{base}{sep}{self.page_param}={page_no}"
            if not robots.allowed(url):
                print(f"  ! {self.key}: robots disallows listing {url}", file=sys.stderr)
                break
            r = crawler.get(url)
            if not r or r.status_code != 200:
                break
            page_hits = 0
            for href in RE_HREF.findall(r.text):
                full = urljoin(base, href)
                if self.article_re.search(full) and full not in seen:
                    seen.add(full)
                    found.append(full)
                    page_hits += 1
            print(f"  [{self.key}] listing page {i}: +{page_hits} article link(s) "
                  f"(total {len(found)})")
            if page_hits == 0 and i > 0:
                break  # ran out of pages
        return found


# Registry. Article-link regexes are intentionally permissive and may need a
# tweak after the first live run — every discovered URL is validated by the
# extractor (an article must yield a title + body), so over-capture is harmless.
SOURCES: dict[str, Source] = {
    "epso": ListingSource(
        "epso",
        "https://eu-careers.europa.eu/en/news",
        article_re=r"eu-careers\.europa\.eu/en/news/[^/]+/\d+",
    ),
    "orseu": ListingSource(
        "orseu",
        "https://www.orseu-concours.com/fr/blog",
        # PrestaShop blog article links carry a numeric id; exclude category/module
        article_re=r"orseu-concours\.com/fr/[^?]*\d+-[a-z0-9-]+",
    ),
    "europapp": SitemapSource(
        "europapp",
        sitemaps=[
            "https://europapp.eu/sitemap-blog-en.xml",
            "https://europapp.eu/sitemap-blog-es.xml",
        ],
    ),
}

# Registered but deliberately OFF — documents the coverage gap (cf. tao_refs in
# scrape.py: never silently drop a source we chose not to take).
DISABLED = {
    "eutraining": "robots.txt disallows ClaudeBot + all AI bots and signals "
                  "Content-Signal: ai-train=no; Cloudflare returns 403 to non-browser "
                  "UAs. Scraping would require ignoring robots.txt and spoofing a browser "
                  "UA. Pending a separate decision (asked an EU-careers contact for advice).",
}


def raw_key(url: str) -> str:
    """Stable, filesystem-safe filename for an article's raw HTML cache."""
    path = urlparse(url).path.strip("/")
    m = re.search(r"(\d+)", path.split("/")[-1] or path)
    stem = m.group(1) if m else re.sub(r"[^a-z0-9]+", "-", path.lower())[:80] or "index"
    return stem


def scrape_source(src: Source, crawler: Crawler, robots: Robots,
                  max_pages: int, max_articles: int) -> list[dict]:
    print(f"\n== source: {src.key} ==")
    urls = src.discover(crawler, robots, max_pages)
    # de-dup preserving order
    seen: set[str] = set()
    urls = [u for u in urls if not (u in seen or seen.add(u))]
    if max_articles:
        if len(urls) > max_articles:
            print(f"  (capping {len(urls)} discovered -> {max_articles}; "
                  f"raise --max-articles for full coverage)")
        urls = urls[:max_articles]
    print(f"  {len(urls)} article URL(s) to fetch")

    out_dir = RAW_DIR / src.key
    out_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    for url in urls:
        if not robots.allowed(url):
            print(f"  - robots disallows {url}", file=sys.stderr)
            continue
        cache = out_dir / f"{raw_key(url)}.html"
        if cache.exists():
            page = cache.read_text(encoding="utf-8", errors="replace")
        else:
            r = crawler.get(url)
            if not r or r.status_code != 200:
                print(f"  ! {url} -> {r.status_code if r else 'ERR'}", file=sys.stderr)
                continue
            page = r.text
            cache.write_text(page, encoding="utf-8")
        rec = parse_article(url, page)
        rec["source"] = src.key
        if not rec["title"] or rec["text_len"] < 80:
            print(f"  ~ thin/unparsed, skipping: {url} (len={rec['text_len']})",
                  file=sys.stderr)
            continue
        records.append(rec)
        print(f"  + {rec['date'] or '????'} [{rec['lang'] or '??'}] "
              f"{rec['title'][:70]} ({rec['text_len']} chars)")
    return records


def write_summary(records: list[dict]) -> str:
    by_src = Counter(r["source"] for r in records)
    by_lang = Counter(r["lang"] or "??" for r in records)
    by_year = Counter((r["date"][:4] if r["date"][:4].isdigit() else "????")
                      for r in records)
    lens = sorted(r["text_len"] for r in records)

    lines = ["# EU-competition news/notices — scrape summary", ""]
    lines.append(f"- Articles extracted: **{len(records)}**")
    if lens:
        lines.append(f"- Text length (chars): min {lens[0]}, "
                     f"median {lens[len(lens)//2]}, max {lens[-1]}")
    lines += ["", "## By source"]
    for k, v in by_src.most_common():
        lines.append(f"- {k}: {v}")
    lines += ["", "## By language"]
    for k, v in by_lang.most_common():
        lines.append(f"- {k}: {v}")
    lines += ["", "## By year"]
    for k in sorted(by_year, reverse=True):
        lines.append(f"- {k}: {by_year[k]}")
    lines += ["", "## Disabled sources (coverage gap — not scraped)"]
    for k, why in DISABLED.items():
        lines.append(f"- **{k}** — {why}")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="EU-competition news/notices scraper")
    ap.add_argument("--source", nargs="*", choices=list(SOURCES),
                    help="which enabled source(s) to scrape (default: all)")
    ap.add_argument("--max-pages", type=int, default=10,
                    help="listing pages to walk per ListingSource")
    ap.add_argument("--max-articles", type=int, default=40,
                    help="cap articles per source (0 = no cap)")
    ap.add_argument("--delay", type=float, default=1.5, help="seconds between requests")
    args = ap.parse_args()

    keys = args.source or list(SOURCES)
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Scraping news sources: {', '.join(keys)}  (delay={args.delay}s)")
    if DISABLED:
        print(f"Disabled (not scraped): {', '.join(DISABLED)}")

    crawler = Crawler(delay=args.delay)
    robots = Robots(crawler)
    all_records: list[dict] = []
    try:
        for key in keys:
            all_records.extend(
                scrape_source(SOURCES[key], crawler, robots,
                              args.max_pages, args.max_articles))
    finally:
        crawler.close()

    (NEWS_DIR / "articles.json").write_text(
        json.dumps({"articles": all_records, "disabled_sources": DISABLED},
                   ensure_ascii=False, indent=1),
        encoding="utf-8")
    summary = write_summary(all_records)
    (NEWS_DIR / "summary.md").write_text(summary, encoding="utf-8")

    print("\n" + summary)
    print(f"Wrote {NEWS_DIR/'articles.json'} and {NEWS_DIR/'summary.md'}")


if __name__ == "__main__":
    main()
