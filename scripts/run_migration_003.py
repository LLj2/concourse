"""Run migration 003 against the Supabase pooler.

Idempotent. The migration is wrapped in BEGIN/COMMIT internally; if any
assertion fails it rolls back.

Usage:
    python scripts/run_migration_003.py
"""
import sys
from pathlib import Path

from sqlalchemy import text

# Add repo root to sys.path so `backend.*` imports work when called directly.
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.db.database import engine


def main() -> None:
    sql_path = Path(__file__).parent.parent / "backend" / "db" / "migrations" / "003_dimensions_and_practice.sql"
    sql = sql_path.read_text()
    print(f"Executing {sql_path.name} ({len(sql)} bytes)...")

    # The migration file already has BEGIN/COMMIT — use engine.connect() so we
    # don't get a nested transaction from SQLAlchemy.
    with engine.connect() as conn:
        # AUTOCOMMIT lets the script's own BEGIN/COMMIT govern transaction boundaries.
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text(sql))

    # Post-migration assertions visible to the operator.
    with engine.connect() as conn:
        items_cols = conn.execute(text("""
            select column_name from information_schema.columns
            where table_name = 'items'
              and column_name in ('dimensions', 'option_diagnostics', 'competition_family', 'content_domain', 'topic_tag', 'derived')
            order by column_name
        """)).all()
        print(f"new items columns: {[r[0] for r in items_cols]}")

        new_tables = conn.execute(text("""
            select table_name from information_schema.tables
            where table_schema = 'public'
              and table_name in ('practice_sessions', 'dimension_mastery', 'pattern_analyses')
            order by table_name
        """)).all()
        print(f"new tables: {[r[0] for r in new_tables]}")

        n_items = conn.execute(text("select count(*) from items where skill_id='verbal' and not archived")).scalar()
        print(f"verbal items still queryable: {n_items}")

        # The XOR constraint should be in pg_constraint
        xor = conn.execute(text("""
            select conname from pg_constraint where conname = 'item_responses_session_xor'
        """)).first()
        print(f"XOR constraint installed: {xor is not None}")


if __name__ == "__main__":
    main()
