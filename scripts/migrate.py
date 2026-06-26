"""Apply all DB migrations in order — the single entry point.

Every migration in backend/db/migrations/ is idempotent (`create ... if not
exists`, `add column if not exists`) and 003+ wrap themselves in BEGIN/COMMIT, so
running the whole chain is safe and repeatable. Use this both for the current
shared Supabase (run ONCE — it's a shared DB, teammates don't re-run) and for the
mandatory fresh PROD Supabase before the pilot (ROADMAP §6): point .env at the new
DB and run this once.

Usage (from repo root, with .env / DATABASE_URL set):
    python scripts/migrate.py                  # apply every migration in order
    python scripts/migrate.py --load-catalog   # …then load the Competition Catalog
    python scripts/migrate.py --only 004 005   # apply only matching migrations
    python scripts/migrate.py --list           # show what would run, do nothing
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

MIG_DIR = REPO / "backend" / "db" / "migrations"
LOADER = REPO / "tools" / "epso_benchmark" / "load_catalog.py"


def main() -> None:
    ap = argparse.ArgumentParser(description="Apply Concourse DB migrations in order")
    ap.add_argument("--only", nargs="*", help="run only migrations whose filename "
                    "contains one of these tokens (e.g. 004 005)")
    ap.add_argument("--load-catalog", action="store_true",
                    help="after migrating, load the scraped Competition Catalog")
    ap.add_argument("--list", action="store_true", help="list migrations, then exit")
    args = ap.parse_args()

    files = sorted(MIG_DIR.glob("*.sql"))
    if args.only:
        files = [f for f in files if any(tok in f.name for tok in args.only)]
    if not files:
        sys.exit("no migrations matched")

    print(f"{len(files)} migration(s) to apply:")
    for f in files:
        print(f"  - {f.name}")
    if args.list:
        return

    # Imported here (not at module load) so --list / --help don't require the DB
    # driver or a configured DATABASE_URL.
    from backend.db.database import engine
    if engine is None:
        sys.exit("DATABASE_URL is not set — nothing to run against")

    # AUTOCOMMIT: each file governs its own transaction (003+ carry BEGIN/COMMIT;
    # 001/002 are idempotent DDL/seeds that autocommit per statement).
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        for f in files:
            print(f"-> applying {f.name} ({f.stat().st_size} bytes)")
            conn.execute(text(f.read_text()))
    print("✓ migrations applied.")

    if args.load_catalog:
        print("\n-> loading Competition Catalog…")
        rc = subprocess.run([sys.executable, str(LOADER)]).returncode
        if rc != 0:
            sys.exit(f"catalog load failed (exit {rc}) — run {LOADER.name} manually")


if __name__ == "__main__":
    main()
