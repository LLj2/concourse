"""Competition Catalog reads — resolve which tests a candidate's competition uses.

The Draft plan tells the candidate which selection tests THEY will actually face.
That comes from the `competitions` table (populated from the EPSO catalog scraper,
see tools/epso_benchmark/catalog_scrape.py + load_catalog.py).

Everything here degrades gracefully: if the table doesn't exist yet (migration 005
not run) or the candidate's competition isn't matched, we fall back to a built-in
test map keyed by the intake's competition choice — so the Draft plan reflects the
right tests now, and gets sharper once the catalog is loaded.

Per Risk-2 (ROADMAP §8): the competition tests inform the *narrative* and which
areas we surface — they do NOT override the measured, rule-based time allocation.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

# Canonical test name -> human label (for narrative + UI).
TEST_LABELS = {
    "verbal_reasoning": "Verbal reasoning",
    "numerical_reasoning": "Numerical reasoning",
    "abstract_reasoning": "Abstract reasoning",
    "reasoning": "Reasoning tests",
    "eu_knowledge": "EU knowledge",
    "digital_skills": "Digital skills",
    "situational_judgement": "Situational judgement",
    "case_study": "Case study",
    "written_essay_eufte": "Written essay on EU matters (EUFTE)",
    "written_test": "Written test",
    "field_related_mcq": "Field-related MCQ",
    "competency_test": "Competency test",
    "talent_screener": "Talent screener",
    "assessment_centre": "Assessment centre",
    "interview": "Interview",
    "oral": "Oral test",
}

# Canonical test -> the planner study area it maps onto (AREAS in planning.py).
# Tests with no single area (e.g. competency/interview) map to None and only
# inform the narrative.
TEST_TO_AREA = {
    "verbal_reasoning": "verbal",
    "numerical_reasoning": "numerical",
    "abstract_reasoning": "abstract",
    "reasoning": None,            # generic reasoning -> all three; handled by caller
    "eu_knowledge": "eu_knowledge",
    "written_essay_eufte": "test_strategy",
    "written_test": "test_strategy",
    "case_study": "test_strategy",
    "field_related_mcq": "eu_knowledge",
    "situational_judgement": "test_strategy",
}

# Fallback test sets keyed by the intake dropdown value, grounded in the catalog
# (AD5 graduates: reasoning + EU knowledge + digital skills + EUFTE; AD7
# specialists: reasoning + field-related MCQ + written test).
FALLBACK_TESTS = {
    "AD5_generalist": ["verbal_reasoning", "numerical_reasoning", "abstract_reasoning",
                       "eu_knowledge", "digital_skills", "written_essay_eufte"],
    "AD7_ict":        ["verbal_reasoning", "numerical_reasoning", "abstract_reasoning",
                       "field_related_mcq", "written_test", "competency_test"],
    "AST":            ["verbal_reasoning", "numerical_reasoning", "abstract_reasoning",
                       "competency_test"],
    "other":          ["verbal_reasoning", "numerical_reasoning", "abstract_reasoning"],
}
_DEFAULT_TESTS = FALLBACK_TESTS["other"]


def labels_for(tests: list[str]) -> list[str]:
    return [TEST_LABELS.get(t, t) for t in tests]


def _row_to_competition(row) -> dict:
    tests = row["tests"]
    if isinstance(tests, str):
        import json
        tests = json.loads(tests)
    return {
        "slug": row.get("slug"),
        "ref": row["ref"],
        "title": row["title"],
        "grade": row["grade"],
        "status": row["status"],
        "deadline": row["deadline"].isoformat() if row.get("deadline") else None,
        "tests": tests or [],
        "notice_url": row.get("notice_url"),
    }


def _safe_query(db: Session, sql: str, params: dict):
    """Run a catalog query, returning None if the table isn't there yet."""
    try:
        return db.execute(text(sql), params).mappings()
    except SQLAlchemyError:
        db.rollback()  # undefined_table etc. — catalog not loaded; caller falls back
        return None


def list_competitions(db: Session, status: Optional[str] = None) -> list[dict]:
    """All catalog competitions (optionally filtered by status). Empty if not loaded."""
    sql = ("select slug, ref, title, grade, status, deadline, tests, notice_url "
           "from competitions")
    params: dict = {}
    if status:
        sql += " where status = :st"
        params["st"] = status
    sql += " order by (deadline is null), deadline asc, title"
    res = _safe_query(db, sql, params)
    return [_row_to_competition(r) for r in res] if res is not None else []


def set_target_ref(db: Session, user_id: str, ref: Optional[str]) -> bool:
    """Persist the candidate's chosen competition (slug/ref) on their profile.

    Runs inside a SAVEPOINT so that if migration 005 hasn't added the column yet,
    the failure rolls back only this statement — the surrounding intake commit is
    unaffected. Returns True if stored, False if skipped/unavailable.
    """
    if not ref:
        return False
    try:
        with db.begin_nested():
            db.execute(
                text("update profiles set target_competition_ref = :r, "
                     "updated_at = now() where user_id = :u"),
                {"r": ref, "u": user_id},
            )
        return True
    except SQLAlchemyError:
        return False  # column not there yet (pre-migration) — ignore, keep intake working


def profile_target_ref(db: Session, user_id: str) -> Optional[str]:
    """The candidate's chosen competition ref, or None (also None pre-migration)."""
    res = _safe_query(
        db, "select target_competition_ref from profiles where user_id = :u",
        {"u": user_id})
    row = res.first() if res is not None else None
    return row["target_competition_ref"] if row else None


def resolve_for_profile(db: Session, constraints: dict) -> dict:
    """Resolve the candidate's competition + tests for plan generation.

    Order: explicit target_competition_ref -> catalog row; else fallback map keyed
    by the intake competition value. Always returns a dict with `tests` + `source`.
    """
    ref = (constraints or {}).get("target_competition_ref")
    target = (constraints or {}).get("target_competition")

    if ref:
        # target_competition_ref may hold either a slug (natural key) or an EPSO
        # reference (which can match several multi-field rows) — take the first.
        res = _safe_query(
            db,
            "select slug, ref, title, grade, status, deadline, tests, notice_url "
            "from competitions where slug = :r or ref = :r "
            "order by (slug = :r) desc limit 1",
            {"r": ref},
        )
        row = res.first() if res is not None else None
        if row:
            comp = _row_to_competition(row)
            comp["source"] = "catalog"
            return comp

    tests = FALLBACK_TESTS.get(target or "", _DEFAULT_TESTS)
    return {
        "ref": ref,
        "title": target,
        "grade": None,
        "status": None,
        "deadline": None,
        "tests": tests,
        "source": "fallback",
    }


def emphasised_areas(tests: list[str]) -> list[str]:
    """Study areas the competition's tests imply (for surfacing in the narrative).
    'reasoning' (generic) implies all three reasoning areas."""
    areas: list[str] = []
    for t in tests:
        if t == "reasoning":
            for a in ("verbal", "numerical", "abstract"):
                if a not in areas:
                    areas.append(a)
            continue
        a = TEST_TO_AREA.get(t)
        if a and a not in areas:
            areas.append(a)
    return areas
