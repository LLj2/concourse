"""Run migration 004 (CV metadata + profile links) against the Supabase pooler.

Idempotent + transactional (the .sql file wraps itself in BEGIN/COMMIT).
Coordinate on Slack before running on the shared DB.

Usage:
    python scripts/run_migration_004.py
"""
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.db.database import engine


def main() -> None:
    sql_path = (Path(__file__).parent.parent / "backend" / "db" / "migrations"
                / "004_cv_profile_links.sql")
    sql = sql_path.read_text()
    print(f"Executing {sql_path.name} ({len(sql)} bytes)...")

    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text(sql))

    with engine.connect() as conn:
        cols = conn.execute(text("""
            select column_name from information_schema.columns
            where table_name = 'profiles'
              and column_name in ('cv_filename','cv_uploaded_at','linkedin_url',
                                  'portfolio_url','other_links')
            order by column_name
        """)).all()
        print(f"new profiles columns: {[r[0] for r in cols]}")


if __name__ == "__main__":
    main()
