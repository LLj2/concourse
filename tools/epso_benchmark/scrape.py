"""
EPSO sample-question benchmark scraper (internal calibration tool).

Purpose
-------
The EPSO careers site publishes *sample* reasoning tests for familiarisation.
The reasoning samples are built with H5P (H5P.MultiChoice etc.) and their full
content — passage, question stem, options and the `correct` flag — is served as
static JSON from the public embed endpoint:  /h5p/<content_id>/embed
No headless browser and no LTI authentication are required for these.

Some categories (e.g. AD5 graduates) instead embed live tests on the TAO Cloud
platform behind an LTI flow. Those are NOT extractable here and are recorded as
`tao_lti` references so the coverage gap is explicit, never silently dropped.

Scope / ethics
--------------
EPSO marks these as "for illustration purposes only ... not training materials".
This tool is for INTERNAL calibration only (understand real test format,
difficulty and structure to calibrate our own authored items — ROADMAP decision
#5). Output is git-ignored and must not be served to users. The crawler is
deliberately polite: single-threaded, fixed delay, identifies itself, backs off.

Usage
-----
    python tools/epso_benchmark/scrape.py            # full crawl (all 9 categories)
    python tools/epso_benchmark/scrape.py --only 13624   # one category (POC)
    python tools/epso_benchmark/scrape.py --max-depth 1  # shallower crawl
    python tools/epso_benchmark/scrape.py --delay 2.0    # slower / politer

Outputs (under tools/epso_benchmark/data/, git-ignored):
    benchmark.json   normalized items + tao_lti references
    summary.md       calibration-oriented statistics
    raw_embeds/<id>.json   per-content parsed H5P params (cache + audit trail)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

BASE = "https://eu-careers.europa.eu"
USER_AGENT = (
    "ConcourseBenchmarkBot/0.1 (internal calibration research; "
    "contact leonardo.lamorgese@gmail.com)"
)

# The 9 sample-test category index pages (from /en/selection-procedure/epso-tests).
CATEGORIES = {
    "13571": "Graduates (Administrators AD5)",
    "13572": "Specialists (Administrators AD6-AD9)",
    "13624": "Assistants (AST 1-AST 9)",
    "13568": "Secretaries (AST/SC)",
    "13625": "Lawyer-linguists (Administrators)",
    "13573": "Lawyer-linguists - Court of Justice",
    "13574": "Translators (Administrators)",
    "19144": "Function Groups I-II (FG I-FG II)",
    "19145": "Function Groups III-IV (FG III-FG IV)",
}

# Optional friendly labels for known English sample sub-pages, so a focused run
# (e.g. --only 15357 15356 15355 --max-depth 0) gets readable attribution instead
# of bare node ids. Extend as more sub-pages are identified.
SUBPAGE_LABELS = {
    "15357": "AST - Verbal reasoning (EN)",
    "15356": "AST - Numerical reasoning (EN)",
    "15355": "AST - Abstract reasoning (EN)",
}
LABELS = {**CATEGORIES, **SUBPAGE_LABELS}

DATA_DIR = Path(__file__).parent / "data"
RAW_DIR = DATA_DIR / "raw_embeds"

# --- regexes -----------------------------------------------------------------
RE_H5P_IFRAME = re.compile(r'data-content-id="(\d+)"')
# Test sub-pages are numeric node links (e.g. /node/15357). We deliberately do
# NOT follow /en/<slug> links — those are site nav/footer/FAQ chrome and would
# explode the frontier across the whole site, wasting requests and tripping rate
# limits. Every real sample-test sub-page is reachable as /node/<id>.
RE_NODE_LINK = re.compile(r'href="(/(?:[a-z]{2}/)?node/\d+)"')
RE_TAO_LINK = re.compile(r'href="(https://[^"]*taocloud\.org[^"]*)"')
RE_H5PINTEGRATION = re.compile(r"H5PIntegration\s*=\s*(\{.*\})\s*;", re.S)
RE_TAGS = re.compile(r"<[^>]+>")
RE_WS = re.compile(r"\s+")


def clean_text(html: str | None) -> str:
    """Strip HTML tags and collapse the heavy H5P whitespace."""
    if not html:
        return ""
    txt = RE_TAGS.sub(" ", html)
    txt = (
        txt.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&#039;", "'")
        .replace("&quot;", '"')
    )
    return RE_WS.sub(" ", txt).strip()


class Crawler:
    def __init__(self, delay: float = 1.5, timeout: float = 30.0):
        self.delay = delay
        self.client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=timeout,
        )
        self.last_request = 0.0

    def get(self, url: str, *, retries: int = 6,
            headers: dict | None = None) -> httpx.Response | None:
        # politeness: never hammer; honour a fixed inter-request delay
        wait = self.delay - (time.monotonic() - self.last_request)
        if wait > 0:
            time.sleep(wait)
        for attempt in range(retries):
            try:
                r = self.client.get(url, headers=headers)
            except httpx.HTTPError as e:
                print(f"    ! {url} -> {e!r} (attempt {attempt+1})", file=sys.stderr)
                time.sleep(2 ** attempt)
                continue
            finally:
                self.last_request = time.monotonic()
            if r.status_code in (429, 500, 502, 503, 504):
                backoff = 2 ** attempt * 3  # 3,6,12,24,48s ... patient w/ EPSO rate limit
                print(f"    ! {r.status_code} on {url}; backing off {backoff}s",
                      file=sys.stderr)
                time.sleep(backoff)
                continue
            return r
        return None

    def close(self):
        self.client.close()


def parse_h5p_content(jc: dict, library: str) -> list[dict]:
    """Normalize an H5P jsonContent blob into 0+ benchmark items.

    Handles MultiChoice directly and recurses into common container libraries
    (QuestionSet / Column / SingleChoiceSet) so nested questions aren't lost.
    """
    items: list[dict] = []
    lib = library.split()[0] if library else ""

    if lib == "H5P.MultiChoice":
        answers = jc.get("answers", []) or []
        options = [clean_text(a.get("text")) for a in answers]
        correct = [i for i, a in enumerate(answers) if a.get("correct")]
        # The media object is always present, but only a real stimulus has a
        # `file.path`. Verbal items carry a decorative placeholder with no file;
        # numerical/abstract items keep their table/diagram here.
        img = (jc.get("media", {}).get("type", {}).get("params", {}) or {}).get("file")
        items.append({
            "type": "multiple_choice",
            "library": library,
            "question": clean_text(jc.get("question")),
            "options": options,
            "correct_indexes": correct,
            "n_options": len(options),
            "has_image": bool(img and img.get("path")),
            "image_path": img.get("path") if img else None,
        })

    elif lib == "H5P.SingleChoiceSet":
        for q in jc.get("choices", []) or []:
            answers = q.get("answers", []) or []
            opts = [clean_text(a) for a in answers]
            items.append({
                "type": "single_choice",
                "library": library,
                "question": clean_text(q.get("question")),
                "options": opts,
                # SingleChoiceSet convention: first answer is the correct one
                "correct_indexes": [0] if opts else [],
                "n_options": len(opts),
                "has_image": False,
            })

    elif lib in ("H5P.QuestionSet", "H5P.Column"):
        key = "questions" if lib == "H5P.QuestionSet" else "content"
        for sub in jc.get(key, []) or []:
            sub_params = sub.get("params") or sub
            sub_lib = sub.get("library", "")
            if isinstance(sub_params, dict):
                items.extend(parse_h5p_content(sub_params, sub_lib))

    else:
        items.append({
            "type": "unknown",
            "library": library,
            "question": clean_text(jc.get("question")),
            "options": [],
            "correct_indexes": [],
            "n_options": 0,
            "has_image": False,
            "raw_keys": sorted(jc.keys()),
        })
    return items


def extract_embed(crawler: Crawler, content_id: str) -> dict | None:
    """Fetch /h5p/<id>/embed and return {library, jsonContent dict}."""
    cache = RAW_DIR / f"{content_id}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))

    r = crawler.get(f"{BASE}/h5p/{content_id}/embed")
    if not r or r.status_code != 200:
        return None
    m = RE_H5PINTEGRATION.search(r.text)
    if not m:
        return None
    blob = m.group(1)
    try:
        integ = json.loads(blob)
    except json.JSONDecodeError:
        integ = json.loads(blob[: blob.rfind("}") + 1])
    contents = integ.get("contents", {})
    if not contents:
        return None
    c = next(iter(contents.values()))
    try:
        jc = json.loads(c["jsonContent"])
    except (KeyError, json.JSONDecodeError):
        return None
    out = {"content_id": content_id, "library": c.get("library", ""), "jsonContent": jc}
    cache.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def is_internal(url: str) -> bool:
    p = urlparse(url)
    return p.netloc in ("", "eu-careers.europa.eu")


def crawl(only: list[str] | None, max_depth: int, delay: float) -> dict:
    crawler = Crawler(delay=delay)
    roots = only or list(CATEGORIES)
    # frontier holds (url, depth, category_id)
    frontier: list[tuple[str, int, str]] = [
        (f"{BASE}/node/{nid}", 0, nid) for nid in roots
    ]
    visited: set[str] = set()
    seen_h5p: set[str] = set()
    items: list[dict] = []
    tao_refs: list[dict] = []

    try:
        while frontier:
            url, depth, cat = frontier.pop(0)
            norm = url.split("#")[0].rstrip("/")
            if norm in visited:
                continue
            visited.add(norm)
            r = crawler.get(url)
            if not r or r.status_code != 200:
                print(f"  [skip {r.status_code if r else 'ERR'}] {url}", file=sys.stderr)
                continue
            html = r.text
            cat_name = LABELS.get(cat, cat)

            # 1) H5P questions on this page
            ids = sorted(set(RE_H5P_IFRAME.findall(html)), key=int)
            for cid in ids:
                if cid in seen_h5p:
                    continue
                seen_h5p.add(cid)
                emb = extract_embed(crawler, cid)
                if not emb:
                    print(f"    - h5p {cid}: no content", file=sys.stderr)
                    continue
                for it in parse_h5p_content(emb["jsonContent"], emb["library"]):
                    it.update(content_id=cid, category=cat_name,
                              category_id=cat, source_url=url)
                    items.append(it)
                print(f"    + h5p {cid}: {emb['library']} -> "
                      f"{sum(1 for x in items if x['content_id']==cid)} item(s)")

            # 2) TAO / LTI references (not extractable — record the gap)
            for tao in set(RE_TAO_LINK.findall(html)):
                tao_refs.append({"category": cat_name, "category_id": cat,
                                 "source_url": url, "tao_url": tao[:120]})

            # 3) descend into internal sub-pages
            if depth < max_depth:
                for href in set(RE_NODE_LINK.findall(html)):
                    nxt = urljoin(BASE, href)
                    if is_internal(nxt) and nxt.split("#")[0].rstrip("/") not in visited:
                        frontier.append((nxt, depth + 1, cat))

            print(f"  [{cat}] depth {depth} done: {url}  "
                  f"(h5p ids: {len(ids)}, frontier: {len(frontier)})")
    finally:
        crawler.close()

    return {"items": items, "tao_refs": tao_refs,
            "pages_visited": len(visited), "h5p_contents": len(seen_h5p)}


def write_summary(result: dict) -> str:
    items = result["items"]
    by_cat = Counter(i["category"] for i in items)
    by_type = Counter(i["type"] for i in items)
    by_lib = Counter(i["library"] for i in items)
    opt_dist = Counter(i["n_options"] for i in items if i["type"] != "unknown")
    with_img = sum(1 for i in items if i["has_image"])
    q_lens = [len(i["question"]) for i in items if i["question"]]
    tao_by_cat = Counter(t["category"] for t in result["tao_refs"])

    lines = ["# EPSO sample-question benchmark — summary", ""]
    lines.append(f"- Pages visited: **{result['pages_visited']}**")
    lines.append(f"- H5P contents fetched: **{result['h5p_contents']}**")
    lines.append(f"- Extracted items: **{len(items)}**")
    lines.append(f"- Items with an image: **{with_img}**")
    if q_lens:
        q_lens.sort()
        lines.append(f"- Question length (chars): min {q_lens[0]}, "
                     f"median {q_lens[len(q_lens)//2]}, max {q_lens[-1]}")
    lines += ["", "## Items by category"]
    for k, v in by_cat.most_common():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Items by type"]
    for k, v in by_type.most_common():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Items by H5P library"]
    for k, v in by_lib.most_common():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Answer-option count distribution"]
    for k in sorted(opt_dist):
        lines.append(f"- {k} options: {opt_dist[k]} items")
    lines += ["", "## TAO/LTI references (NOT extractable — coverage gap)"]
    if tao_by_cat:
        for k, v in tao_by_cat.most_common():
            lines.append(f"- {k}: {v} live-platform links (questions behind LTI auth)")
    else:
        lines.append("- none found")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="EPSO sample-question benchmark scraper")
    ap.add_argument("--only", nargs="*", help="category node id(s) to crawl, e.g. 13624")
    ap.add_argument("--max-depth", type=int, default=2)
    ap.add_argument("--delay", type=float, default=1.5, help="seconds between requests")
    args = ap.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Crawling {'category ' + ','.join(args.only) if args.only else 'all 9 categories'} "
          f"(max-depth={args.max_depth}, delay={args.delay}s)\n")

    result = crawl(args.only, args.max_depth, args.delay)

    (DATA_DIR / "benchmark.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    summary = write_summary(result)
    (DATA_DIR / "summary.md").write_text(summary, encoding="utf-8")

    print("\n" + summary)
    print(f"Wrote {DATA_DIR/'benchmark.json'} and {DATA_DIR/'summary.md'}")


if __name__ == "__main__":
    main()
