"""Run migration 005 (Competition Catalog table) against the Supabase pooler.

Idempotent + transactional (the .sql file wraps itself in BEGIN/COMMIT).
Coordinate on Slack before running on the shared DB. After it succeeds, load the
catalog data:  python tools/epso_benchmark/load_catalog.py

Usage:
    python scripts/run_migration_005.py
"""
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.db.database import engine


def main() -> None:
    sql_path = (Path(__file__).parent.parent / "backend" / "db" / "migrations"
                / "005_competitions.sql")
    sql = sql_path.read_text()
    print(f"Executing {sql_path.name} ({len(sql)} bytes)...")

    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text(sql))

    with engine.connect() as conn:
        has_table = conn.execute(text("""
            select 1 from information_schema.tables
            where table_schema = 'public' and table_name = 'competitions'
        """)).first()
        print(f"competitions table installed: {has_table is not None}")

        has_ref = conn.execute(text("""
            select 1 from information_schema.columns
            where table_name = 'profiles' and column_name = 'target_competition_ref'
        """)).first()
        print(f"profiles.target_competition_ref installed: {has_ref is not None}")

        n = conn.execute(text("select count(*) from competitions")).scalar()
        print(f"competitions rows: {n} (run load_catalog.py to populate)")


if __name__ == "__main__":
    main()
