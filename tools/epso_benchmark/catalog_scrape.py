"""
EPSO Competition Catalog scraper (product data — feeds the Draft plan).

Purpose
-------
The 2026-06-25 planning call put a **Competition Catalog** first: import the
factual data of EPSO competition notices (reference, grade, profile, deadline,
selection-procedure structure, link to the official Notice) for competitions that
are **open**, **in progress** and **upcoming**. This feeds the gap analysis and
the Draft plan (which tests the candidate will actually face, by competition).

Scope / ethics — DIFFERENT from the sample-question scraper
-----------------------------------------------------------
`scrape.py` harvests EPSO *sample questions*, which EPSO marks "not training
materials" → that output is internal-only and git-ignored. THIS tool instead
collects *competition notices*: public, official, factual information (titles,
grades, deadlines, test structure) published on eu-careers.europa.eu and in the
EU Official Journal. That is reference data we intend to surface to users, not
copyrighted practice content. We are still polite and robots-respecting.

eu-careers.europa.eu robots.txt (Drupal) has no AI-bot block and no crawl
restriction on the job-opportunities pages, so this is straightforwardly allowed.

How it works
------------
1. Crawl the EPSO listing pages (open / in-progress / closed) and collect the
   competition detail URLs (pattern: /en/job-opportunities/<slug>).
2. Fetch each detail page and extract structured fields with regex + a keyword
   scan for the selection-procedure tests (no DOM parser; raw HTML is cached as
   an audit trail so a richer parse is always possible later).
3. The "upcoming" page lists announced-but-unpublished competitions as plain
   text (no detail pages yet) — captured as lightweight announcement records so
   the catalog can show "what's coming".

Reuses the single-threaded, self-identifying, backing-off `Crawler` and the
per-host `Robots` gate from the existing tool — no new deps, same politeness.

Usage
-----
    python tools/epso_benchmark/catalog_scrape.py                 # open + in-progress + upcoming
    python tools/epso_benchmark/catalog_scrape.py --status in-progress
    python tools/epso_benchmark/catalog_scrape.py --status open in-progress closed upcoming
    python tools/epso_benchmark/catalog_scrape.py --delay 3.0     # politer

Outputs (under tools/epso_benchmark/data/catalog/, git-ignored):
    competitions.json    structured records (ref, grade, deadline, tests, notice_url, ...)
    summary.md           counts by status / grade, tests-coverage stats
    raw/<slug>.html      cached detail-page HTML (audit trail + offline re-parse)
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

# Reuse the polite client + cleaner from the sample scraper and the robots gate +
# date normaliser from the news scraper. Same toolchain (httpx + stdlib), no new deps.
from scrape import BASE, Crawler, clean_text
from news_scrape import Robots, normalize_date

CATALOG_DIR = Path(__file__).parent / "data" / "catalog"
RAW_DIR = CATALOG_DIR / "raw"

# Listing pages per status. The "upcoming" page is plain text (no detail links yet).
LISTINGS = {
    "open":        f"{BASE}/en/job-opportunities/open-for-application",
    "in-progress": f"{BASE}/en/job-opportunities/in-progress",
    "closed":      f"{BASE}/en/job-opportunities/closed",
    "upcoming":    f"{BASE}/en/job-opportunities/upcoming",
}
# Default run: what's actionable for a candidate now or soon.
DEFAULT_STATUSES = ["open", "in-progress", "upcoming"]

# Listing slugs that are NOT competitions — never treat these as detail pages.
# (The listing pages also link to other job-opportunity categories.)
NON_DETAIL_SLUGS = {
    "open-for-application", "in-progress", "closed", "upcoming", "competition",
    "temporary-job-vacancies", "traineeships", "contract-staff",
    "seconded-national-experts", "interim-staff", "blue-book-traineeship",
    "reserve-lists", "permanent-positions",
}

# --- regexes -----------------------------------------------------------------
RE_OG_TITLE = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=(["\'])(.*?)\1', re.I | re.S)
RE_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
RE_H1 = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
RE_DESC = re.compile(
    r'<meta[^>]+(?:name|property)=["\'](?:og:)?description["\'][^>]+content=(["\'])(.*?)\1',
    re.I | re.S)
RE_HREF = re.compile(r'href=["\']([^"\'#]+)["\']', re.I)
# Detail link: /en/job-opportunities/<slug> (one segment, not a listing slug).
RE_DETAIL_HREF = re.compile(r'href=["\'](/en/job-opportunities/[a-z0-9][a-z0-9-]*)["\']', re.I)
# EPSO reference: EPSO/AD/427/26, EPSO/AST-SC/2/24, EPSO/AD/429/26 - 4 (field suffix)
RE_REF = re.compile(r"EPSO/[A-Z]{2,5}(?:-[A-Z]{2})?/\d+/\d+", re.I)
RE_REF_FIELD = re.compile(r"(EPSO/[A-Z]{2,5}(?:-[A-Z]{2})?/\d+/\d+)\s*[-–]\s*([A-Za-z0-9]+)", re.I)
# Grade: "AD 5", "AST 3", "AST-SC 1", "AD8"
RE_GRADE = re.compile(r"\b(AD|AST-SC|AST)\s*(\d{1,2})\b")
RE_DATE = re.compile(r"\b(\d{1,2}/\d{1,2}/20\d{2})\b")
RE_DEADLINE = re.compile(r"deadline[^0-9]{0,60}?(\d{1,2}/\d{1,2}/20\d{2})", re.I | re.S)
RE_NOTICE = re.compile(
    r'href=["\'](https?://[^"\']*(?:data\.europa\.eu/eli[^"\']*'
    r'|eur-lex\.europa\.eu[^"\']*|notice[^"\']*\.pdf|[^"\']*/oj))["\']', re.I)
RE_ELIG = re.compile(r'href=["\'](/en/[^"\']*(?:what-it-takes|eligibilit)[^"\']*)["\']', re.I)
RE_DROP = re.compile(
    r"<(script|style|nav|header|footer|form|noscript|aside)\b[^>]*>.*?</\1>", re.I | re.S)

# Selection-procedure tests we care about → canonical name. Keyword scan over the
# page text is robust to Drupal layout changes (tabs / steps / lists).
TEST_VOCAB = [
    ("verbal reasoning", "verbal_reasoning"),
    ("numerical reasoning", "numerical_reasoning"),
    ("abstract reasoning", "abstract_reasoning"),
    ("reasoning test", "reasoning"),
    ("eu knowledge", "eu_knowledge"),
    ("digital skills", "digital_skills"),
    ("situational judgement", "situational_judgement"),
    ("case study", "case_study"),
    ("free-text essay", "written_essay_eufte"),
    ("eufte", "written_essay_eufte"),
    ("written test", "written_test"),
    ("field-related", "field_related_mcq"),
    ("competency", "competency_test"),
    ("talent screener", "talent_screener"),
    ("assessment centre", "assessment_centre"),
    ("assessment center", "assessment_centre"),
    ("interview", "interview"),
    ("oral test", "oral"),
]


def _clean(s: str | None) -> str:
    return html.unescape(clean_text(s)) if s else ""


def _grp(m: re.Match | None) -> str | None:
    return m.group(m.lastindex) if (m and m.lastindex) else None


def _first(*cands: str | None) -> str:
    for c in cands:
        t = _clean(c)
        if t:
            return t
    return ""


def _strip_suffix(title: str) -> str:
    if " | " in title:
        head, tail = title.rsplit(" | ", 1)
        if head and len(tail) <= 30:
            return head.strip()
    return title


def detect_tests(page_text_lower: str) -> list[str]:
    """Which EPSO tests this competition's page mentions, canonicalised + de-duped."""
    found: list[str] = []
    for needle, canon in TEST_VOCAB:
        if needle in page_text_lower and canon not in found:
            found.append(canon)
    return found


def parse_detail(url: str, status: str, page: str) -> dict:
    title = _strip_suffix(_first(
        _grp(RE_OG_TITLE.search(page)), _grp(RE_H1.search(page)), _grp(RE_TITLE.search(page))))
    text = clean_text(RE_DROP.sub(" ", page))
    text_lower = text.lower()

    ref = None
    field = None
    mf = RE_REF_FIELD.search(page)
    if mf:
        ref, field = mf.group(1).upper(), mf.group(2)
    else:
        mr = RE_REF.search(page)
        ref = mr.group(0).upper() if mr else None

    grade = None
    mg = RE_GRADE.search(text)
    if mg:
        grade = f"{mg.group(1)} {mg.group(2)}"

    deadline = ""
    md = RE_DEADLINE.search(page) or RE_DEADLINE.search(text)
    if md:
        deadline = normalize_date(md.group(1))
    notice = _grp_href(RE_NOTICE.search(page))
    elig = _grp_href(RE_ELIG.search(page))
    if elig:
        elig = urljoin(BASE, elig)

    return {
        "status": status,
        "url": url,
        "ref": ref,
        "field": field,
        "title": title,
        "grade": grade,
        "deadline": deadline,
        "tests_detected": detect_tests(text_lower),
        "notice_url": notice,
        "eligibility_url": elig,
        "summary": _clean(_grp(RE_DESC.search(page))),
        "text_len": len(text),
    }


def _grp_href(m: re.Match | None) -> str | None:
    return m.group(1) if m else None


def slug_of(url: str) -> str:
    return urlparse(url).path.rstrip("/").split("/")[-1] or "index"


def discover_details(listing_url: str, crawler: Crawler, robots: Robots) -> list[str]:
    """Collect competition detail URLs from a listing page."""
    if not robots.allowed(listing_url):
        print(f"  ! robots disallows listing {listing_url}", file=sys.stderr)
        return []
    r = crawler.get(listing_url)
    if not r or r.status_code != 200:
        print(f"  ! listing {listing_url} -> {r.status_code if r else 'ERR'}", file=sys.stderr)
        return []
    urls, seen = [], set()
    for href in RE_DETAIL_HREF.findall(r.text):
        slug = href.rstrip("/").split("/")[-1].lower()
        if slug in NON_DETAIL_SLUGS:
            continue
        full = urljoin(BASE, href)
        if full not in seen:
            seen.add(full)
            urls.append(full)
    return urls


def scrape_status(status: str, crawler: Crawler, robots: Robots,
                  max_competitions: int) -> list[dict]:
    listing = LISTINGS[status]
    print(f"\n== status: {status} ==  ({listing})")

    if status == "upcoming":
        return scrape_upcoming(listing, crawler, robots)

    urls = discover_details(listing, crawler, robots)
    if max_competitions and len(urls) > max_competitions:
        print(f"  (capping {len(urls)} -> {max_competitions}; raise --max-competitions)")
        urls = urls[:max_competitions]
    print(f"  {len(urls)} competition page(s) to fetch")

    out_dir = RAW_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    for url in urls:
        if not robots.allowed(url):
            print(f"  - robots disallows {url}", file=sys.stderr)
            continue
        cache = out_dir / f"{slug_of(url)}.html"
        if cache.exists():
            page = cache.read_text(encoding="utf-8", errors="replace")
        else:
            r = crawler.get(url)
            if not r or r.status_code != 200:
                print(f"  ! {url} -> {r.status_code if r else 'ERR'}", file=sys.stderr)
                continue
            page = r.text
            cache.write_text(page, encoding="utf-8")
        rec = parse_detail(url, status, page)
        if not rec["title"]:
            print(f"  ~ no title, skipping {url}", file=sys.stderr)
            continue
        # A real competition always carries an EPSO reference or a grade; pages
        # without either are category/landing chrome (traineeships, vacancies…).
        if not rec["ref"] and not rec["grade"]:
            print(f"  ~ not a competition (no ref/grade), skipping {slug_of(url)}",
                  file=sys.stderr)
            continue
        records.append(rec)
        print(f"  + [{rec['ref'] or '?ref'}] {rec['grade'] or '?'} — "
              f"{rec['title'][:60]} · tests={','.join(rec['tests_detected']) or '—'}")
    return records


def scrape_upcoming(listing: str, crawler: Crawler, robots: Robots) -> list[dict]:
    """The upcoming page is plain text — capture announced competitions lightly:
    keep each line that names a grade (AD/AST) as an announcement record."""
    if not robots.allowed(listing):
        return []
    r = crawler.get(listing)
    if not r or r.status_code != 200:
        print(f"  ! upcoming {listing} -> {r.status_code if r else 'ERR'}", file=sys.stderr)
        return []
    text = clean_text(RE_DROP.sub(" ", r.text))
    # Split on sentence-ish boundaries; keep fragments that mention a grade.
    records: list[dict] = []
    for frag in re.split(r"[•\n\.;]| {2,}", text):
        frag = frag.strip()
        if not (8 < len(frag) < 160):
            continue
        mg = RE_GRADE.search(frag) or re.search(r"\b(AD|AST)\b", frag)
        if not mg:
            continue
        if not re.search(r"(202\d|expert|lawyer|translat|assistant|administrator|specialist|inspector)",
                         frag, re.I):
            continue
        records.append({
            "status": "upcoming", "url": None, "ref": None, "field": None,
            "title": frag, "grade": (f"{mg.group(1)} {mg.group(2)}"
                                     if mg.lastindex and mg.re is RE_GRADE else mg.group(1)),
            "deadline": "", "tests_detected": [], "notice_url": None,
            "eligibility_url": None, "summary": "", "text_len": len(frag),
        })
    # De-dupe identical fragments.
    uniq, seen = [], set()
    for rec in records:
        if rec["title"] not in seen:
            seen.add(rec["title"])
            uniq.append(rec)
    print(f"  {len(uniq)} upcoming announcement(s) captured (plain-text, best-effort)")
    return uniq


def write_summary(records: list[dict]) -> str:
    by_status = Counter(r["status"] for r in records)
    by_grade = Counter((r["grade"] or "?").split()[0] if r["grade"] else "?" for r in records)
    test_cov = Counter(t for r in records for t in r["tests_detected"])
    with_ref = sum(1 for r in records if r["ref"])
    with_notice = sum(1 for r in records if r["notice_url"])

    lines = ["# EPSO Competition Catalog — scrape summary", ""]
    lines.append(f"- Competitions captured: **{len(records)}**")
    lines.append(f"- With EPSO reference: {with_ref} · with Notice link: {with_notice}")
    lines += ["", "## By status"]
    for k, v in by_status.most_common():
        lines.append(f"- {k}: {v}")
    lines += ["", "## By grade (family)"]
    for k, v in by_grade.most_common():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Test coverage (how many competitions mention each test)"]
    for k, v in test_cov.most_common():
        lines.append(f"- {k}: {v}")
    lines += ["", "_Detail-page fields are regex-extracted; raw HTML is cached under "
              "`data/catalog/raw/` for a richer re-parse. Eligibility lives on a linked "
              "page + the official Notice (see `notice_url`) — not inlined here yet._"]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="EPSO Competition Catalog scraper")
    ap.add_argument("--status", nargs="*", choices=list(LISTINGS),
                    help=f"which listing(s) to scrape (default: {' '.join(DEFAULT_STATUSES)})")
    ap.add_argument("--max-competitions", type=int, default=0,
                    help="cap competitions per status (0 = no cap)")
    ap.add_argument("--delay", type=float, default=1.5, help="seconds between requests")
    args = ap.parse_args()

    statuses = args.status or DEFAULT_STATUSES
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Scraping EPSO competition catalog: {', '.join(statuses)}  (delay={args.delay}s)")

    crawler = Crawler(delay=args.delay)
    robots = Robots(crawler)
    records: list[dict] = []
    try:
        for status in statuses:
            records.extend(scrape_status(status, crawler, robots, args.max_competitions))
    finally:
        crawler.close()

    (CATALOG_DIR / "competitions.json").write_text(
        json.dumps({"competitions": records}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    summary = write_summary(records)
    (CATALOG_DIR / "summary.md").write_text(summary, encoding="utf-8")
    print("\n" + summary)
    print(f"Wrote {CATALOG_DIR/'competitions.json'} and {CATALOG_DIR/'summary.md'}")


if __name__ == "__main__":
    main()
