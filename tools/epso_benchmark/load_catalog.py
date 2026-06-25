"""
Load the scraped Competition Catalog into the app DB (`competitions` table).

Reads tools/epso_benchmark/data/catalog/competitions.json (produced by
catalog_scrape.py) and upserts each competition via the app's SQLAlchemy engine.
Run AFTER migration 005 has been applied (coordinate on Slack — shared DB).

Usage (from repo root, with the app's .env / DATABASE_URL available):
    python tools/epso_benchmark/load_catalog.py
    python tools/epso_benchmark/load_catalog.py --file path/to/competitions.json
    python tools/epso_benchmark/load_catalog.py --dry-run     # parse + print, no writes

Upsert keys: `ref` when present (open/in-progress competitions); otherwise `slug`
(ref-less upcoming announcements).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

# Make `backend` importable when run as a script from the repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import text  # noqa: E402

DEFAULT_FILE = Path(__file__).parent / "data" / "catalog" / "competitions.json"


def grade_family(grade: str | None, ref: str | None) -> str | None:
    if grade:
        return grade.split()[0]
    if ref and ref.startswith("EPSO/"):
        parts = ref.split("/")
        return parts[1] if len(parts) > 1 else None
    return None


def slug_of(rec: dict) -> str | None:
    url = rec.get("url")
    if url:
        return urlparse(url).path.rstrip("/").split("/")[-1] or None
    # ref-less announcement: derive a stable slug from the title
    title = (rec.get("title") or "").lower()
    s = "".join(c if c.isalnum() else "-" for c in title).strip("-")
    return ("upcoming-" + s[:60]) if s else None


# Upsert by slug (the natural key — one row per competition detail page).
_UPSERT = text(
    """
    insert into competitions
        (slug, ref, url, title, grade, grade_family, field, status, deadline,
         tests, notice_url, eligibility_url, summary, updated_at)
    values
        (:slug, :ref, :url, :title, :grade, :grade_family, :field, :status,
         :deadline, cast(:tests as jsonb), :notice_url, :eligibility_url, :summary, now())
    on conflict (slug) do update set
        ref = excluded.ref, url = excluded.url, title = excluded.title,
        grade = excluded.grade, grade_family = excluded.grade_family,
        field = excluded.field, status = excluded.status, deadline = excluded.deadline,
        tests = excluded.tests, notice_url = excluded.notice_url,
        eligibility_url = excluded.eligibility_url, summary = excluded.summary,
        updated_at = now()
    """
)


def to_params(rec: dict) -> dict:
    return {
        "ref": rec.get("ref"),
        "slug": slug_of(rec),
        "url": rec.get("url"),
        "title": rec.get("title") or "(untitled)",
        "grade": rec.get("grade"),
        "grade_family": grade_family(rec.get("grade"), rec.get("ref")),
        "field": rec.get("field"),
        "status": rec.get("status"),
        "deadline": rec.get("deadline") or None,
        "tests": json.dumps(rec.get("tests_detected") or rec.get("tests") or []),
        "notice_url": rec.get("notice_url"),
        "eligibility_url": rec.get("eligibility_url"),
        "summary": rec.get("summary") or None,
    }


def main():
    ap = argparse.ArgumentParser(description="Load Competition Catalog into the DB")
    ap.add_argument("--file", type=Path, default=DEFAULT_FILE)
    ap.add_argument("--dry-run", action="store_true", help="parse + print, no DB writes")
    args = ap.parse_args()

    if not args.file.exists():
        sys.exit(f"catalog file not found: {args.file} — run catalog_scrape.py first")
    data = json.loads(args.file.read_text(encoding="utf-8"))
    comps = data.get("competitions", [])
    print(f"{len(comps)} competition(s) in {args.file}")

    if args.dry_run:
        for rec in comps:
            p = to_params(rec)
            print(f"  [{p['ref'] or p['slug']}] {p['grade'] or '?'} — {p['title'][:60]} "
                  f"· {len(json.loads(p['tests']))} test(s)")
        print("dry-run: no writes")
        return

    from backend.db.database import SessionLocal  # noqa: E402
    if SessionLocal is None:
        sys.exit("DATABASE_URL is not set — cannot load")

    db = SessionLocal()
    n_up = n_skip = 0
    try:
        for rec in comps:
            p = to_params(rec)
            if not p["slug"]:
                n_skip += 1
                continue
            db.execute(_UPSERT, p)
            n_up += 1
        db.commit()
    finally:
        db.close()
    print(f"upserted {n_up}; skipped {n_skip} (no slug)")


if __name__ == "__main__":
    main()
