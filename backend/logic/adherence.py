"""Logging Layer C — one-tap adherence + replan signals (Session 8).

The cheap daily habit hook: "Did you do today's plan?" -> done / partial / skipped
(+ optional minutes + note). Near-zero friction; builds the daily-open habit and
gives the planner something to adapt to even from non-test-takers.

Adherence never drives the allocation by itself (adherence != performance), but a
breached weekly floor is a replan *trigger*. Replanning is event-driven: this
module exposes `replan_signal()` which the plan endpoint reads to suggest a
refresh when (a) new measured data landed since the active plan, or (b) the
weekly floor is breached. The actual regenerate stays an explicit call with the
right `trigger_kind` (no surprise rewrites).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

VALID_STATUS = ("done", "partial", "skipped")
WEEKLY_FLOOR_SKIPS = 2  # >= this many skips in the last 7 days -> floor breached


def log_adherence(
    db: Session,
    user_id: str,
    status: str,
    minutes_actual: Optional[int] = None,
    note: Optional[str] = None,
    plan_id: Optional[str] = None,
) -> dict:
    """Upsert today's adherence (one row per user per day)."""
    if status not in VALID_STATUS:
        raise ValueError(f"invalid status: {status}")
    db.execute(
        text(
            """
            insert into adherence (user_id, plan_id, day, status, minutes_actual, note)
            values (:u, :p, current_date, :s, :m, :n)
            on conflict (user_id, day) do update set
                status = excluded.status,
                minutes_actual = excluded.minutes_actual,
                note = excluded.note,
                plan_id = coalesce(excluded.plan_id, adherence.plan_id),
                logged_at = now()
            """
        ),
        {"u": user_id, "p": plan_id, "s": status, "m": minutes_actual, "n": note},
    )
    db.execute(
        text("insert into events (user_id, kind, payload) values (:u, 'adherence_logged', cast(:p as jsonb))"),
        {"u": user_id, "p": f'{{"status": "{status}"}}'},
    )
    db.commit()
    return today_status(db, user_id)


def today_status(db: Session, user_id: str) -> dict:
    row = db.execute(
        text(
            "select status, minutes_actual, note from adherence where user_id = :u and day = current_date"
        ),
        {"u": user_id},
    ).mappings().first()
    return {"logged": row is not None, **(dict(row) if row else {})}


def week_summary(db: Session, user_id: str) -> dict:
    """Last 7 days: counts by status + a simple streak of consecutive logged days."""
    rows = db.execute(
        text(
            """
            select day, status from adherence
            where user_id = :u and day >= current_date - interval '6 days'
            order by day desc
            """
        ),
        {"u": user_id},
    ).mappings().all()
    counts = {s: 0 for s in VALID_STATUS}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"counts": counts, "days_logged": len(rows)}


def replan_signal(db: Session, user_id: str) -> dict:
    """Should we suggest regenerating the plan? Event-driven, no cron needed.

    Triggers:
      - diagnostic: a diagnostic completed after the active plan was generated
        (new measured data the allocation hasn't seen).
      - weekly_floor: >= WEEKLY_FLOOR_SKIPS skips in the last 7 days.
    Returns {suggested: bool, trigger_kind: str|None, reason: str|None}.
    """
    plan = db.execute(
        text(
            """
            select id, created_at from plans
            where user_id = :u and kind = 'master' and superseded_by is null
            order by created_at desc limit 1
            """
        ),
        {"u": user_id},
    ).mappings().first()
    if not plan:
        return {"suggested": False, "trigger_kind": None, "reason": None}

    newer_diag = db.execute(
        text(
            """
            select count(*) from diagnostic_sessions
            where user_id = :u and completed_at is not null and completed_at > :since
            """
        ),
        {"u": user_id, "since": plan["created_at"]},
    ).scalar()
    if newer_diag and newer_diag > 0:
        return {
            "suggested": True,
            "trigger_kind": "diagnostic",
            "reason": "New diagnostic results are in — refresh your plan to use them.",
        }

    skips = db.execute(
        text(
            """
            select count(*) from adherence
            where user_id = :u and status = 'skipped'
              and day >= current_date - interval '6 days'
            """
        ),
        {"u": user_id},
    ).scalar()
    if skips and skips >= WEEKLY_FLOOR_SKIPS:
        return {
            "suggested": True,
            "trigger_kind": "weekly_floor",
            "reason": f"{skips} skipped days this week — a lighter, rebalanced plan may help.",
        }

    return {"suggested": False, "trigger_kind": None, "reason": None}
