"""Compass validation pipeline — the schema's self-correcting layer.

Three read-only checks that surface to /admin/compass/health:

1. **Discrimination** — for each dimension *value*, compare accuracy of users
   in the top quartile of overall skill score vs bottom quartile. Big gap =
   the dimension is doing real work. Small gap = noise candidate for removal.

2. **Predictivity** — for users who have done multiple calibrations on the
   same skill, correlate dimension-mastery at time T with overall score at
   time T+N. Returns empty until we have re-calibration data on enough users.

3. **Emergent patterns** — placeholder for the monthly LLM pass that looks
   for error clusters not mapped to a v1 dimension. Stubbed as "needs more
   data" until we have ≥50 users. Real implementation is post-v1.

All three are pure SQL (free). Designed to be called from the admin page,
not from the user-facing app.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


# Minimum N before discrimination starts being meaningful.
MIN_USERS_FOR_DISCRIMINATION = 20

# Minimum N for emergent-pattern detection (lower-bound; the real number is higher).
MIN_USERS_FOR_EMERGENT = 50


@dataclass
class DimensionHealth:
    dimension_name: str
    dimension_value: str
    top_quartile_accuracy_pct: Optional[float]
    bottom_quartile_accuracy_pct: Optional[float]
    gap_pct_points: Optional[float]
    n_attempts_total: int


# =============================================================================
# 1. Discrimination check
# =============================================================================

def discrimination_check(db: Session, skill_id: str) -> dict:
    """Return per-dimension top-vs-bottom-quartile accuracy.

    Output shape:
        {
            "skill_id": "verbal",
            "n_users": 23,
            "min_users_threshold": 20,
            "rows": [DimensionHealth, ...]  — sorted by |gap| descending
        }

    When n_users < MIN_USERS_FOR_DISCRIMINATION, rows is empty (the check is
    not meaningful yet).
    """
    n_users = db.execute(
        text(
            """
            select count(distinct user_id)
            from dimension_mastery
            where skill_id = :s
            """
        ),
        {"s": skill_id},
    ).scalar() or 0
    n_users = int(n_users)

    if n_users < MIN_USERS_FOR_DISCRIMINATION:
        return {
            "skill_id": skill_id,
            "n_users": n_users,
            "min_users_threshold": MIN_USERS_FOR_DISCRIMINATION,
            "rows": [],
        }

    # SQL strategy:
    #   - per-user overall accuracy = total correct / total attempts in dimension_mastery
    #     (this overcounts because each answer touches multiple dimensions, but the
    #     per-user ordering is correct, which is all we need for quartile cutoffs).
    #   - quartile bin each user (top = 4th, bottom = 1st)
    #   - per (dimension_name, dimension_value), compute mean accuracy in top vs bottom
    rows = db.execute(
        text(
            """
            with user_score as (
                select user_id,
                       sum(correct)::float / nullif(sum(attempts), 0) as overall_acc,
                       sum(attempts) as total_attempts
                from dimension_mastery
                where skill_id = :s
                group by user_id
            ),
            user_quartile as (
                select user_id, overall_acc,
                       ntile(4) over (order by overall_acc) as q
                from user_score
                where overall_acc is not null
            ),
            per_dim as (
                select dm.dimension_name, dm.dimension_value, uq.q,
                       sum(dm.correct)::float / nullif(sum(dm.attempts), 0) as acc_in_q,
                       sum(dm.attempts) as attempts_in_q
                from dimension_mastery dm
                join user_quartile uq on uq.user_id = dm.user_id
                where dm.skill_id = :s
                group by dm.dimension_name, dm.dimension_value, uq.q
            )
            select dimension_name, dimension_value,
                   max(case when q = 4 then acc_in_q end) as top_acc,
                   max(case when q = 1 then acc_in_q end) as bot_acc,
                   sum(attempts_in_q) as n_attempts_total
            from per_dim
            group by dimension_name, dimension_value
            order by abs(coalesce(max(case when q=4 then acc_in_q end), 0)
                       - coalesce(max(case when q=1 then acc_in_q end), 0)) desc
            """
        ),
        {"s": skill_id},
    ).all()

    out_rows = []
    for r in rows:
        top = round(100.0 * r[2], 1) if r[2] is not None else None
        bot = round(100.0 * r[3], 1) if r[3] is not None else None
        gap = round(top - bot, 1) if (top is not None and bot is not None) else None
        out_rows.append(
            DimensionHealth(
                dimension_name=r[0],
                dimension_value=r[1],
                top_quartile_accuracy_pct=top,
                bottom_quartile_accuracy_pct=bot,
                gap_pct_points=gap,
                n_attempts_total=int(r[4] or 0),
            )
        )

    return {
        "skill_id": skill_id,
        "n_users": n_users,
        "min_users_threshold": MIN_USERS_FOR_DISCRIMINATION,
        "rows": out_rows,
    }


# =============================================================================
# 2. Predictivity check
# =============================================================================

def predictivity_check(db: Session, skill_id: str) -> dict:
    """Correlate per-user dimension mastery at time T with overall score at T+N.

    v1 implementation: requires users with ≥2 completed diagnostic_sessions on
    the same skill (re-calibration data). Until that data exists, returns
    'needs_recalibration_data'. The real Spearman-correlation logic lands when
    we have ≥10 users with re-calibrations.
    """
    n_recal_users = db.execute(
        text(
            """
            select count(*) from (
                select user_id, count(*) as n
                from diagnostic_sessions
                where skill_id = :s and completed_at is not null
                group by user_id
                having count(*) >= 2
            ) t
            """
        ),
        {"s": skill_id},
    ).scalar() or 0

    return {
        "skill_id": skill_id,
        "n_users_with_recalibration": int(n_recal_users),
        "min_users_threshold": 10,
        "status": (
            "needs_recalibration_data"
            if int(n_recal_users) < 10
            else "ready_implement_correlation"
        ),
        "rows": [],
    }


# =============================================================================
# 3. Emergent patterns (placeholder)
# =============================================================================

def emergent_patterns(db: Session, skill_id: str) -> dict:
    """Surface error clusters that don't map to a v1 dimension.

    v1 implementation: returns 'needs_more_data' until we have ≥50 users with
    practice activity. The real implementation runs an LLM pass over the
    response history; that lands post-v1.
    """
    n_users = db.execute(
        text(
            """
            select count(distinct ps.user_id)
            from practice_sessions ps
            join item_responses r on r.practice_session_id = ps.id
            join items i on i.id = r.item_id
            where i.skill_id = :s
            """
        ),
        {"s": skill_id},
    ).scalar() or 0

    return {
        "skill_id": skill_id,
        "n_practice_users": int(n_users),
        "min_users_threshold": MIN_USERS_FOR_EMERGENT,
        "status": (
            "needs_more_data"
            if int(n_users) < MIN_USERS_FOR_EMERGENT
            else "ready_implement_llm_pass"
        ),
        "candidate_emergent_dimensions": [],
    }
