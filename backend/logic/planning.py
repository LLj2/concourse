"""Plan generation — rule engine (Sessions 6-7).

Two plans, per the build plan:
  - MASTER plan: a deterministic rule engine converts measured scores + self-rated
    soft dimensions + time-to-exam + weekly hours into a per-area weekly minute
    allocation. CV-fit is a strategy modifier only, never a daily driver.
  - DAILY plan: on demand, turns today's available minutes + energy into an
    ordered task list drawn from the active master allocation.

The numbers are rule-based and testable. The LLM only *narrates* the rationale
(schema-validated), it never decides the allocation. Plans are stored in the
`plans` table; generating a new master plan supersedes the previous active one
and records what triggered it (event-driven replan, `trigger_kind`).
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.ai import client as ai
from backend.logic import scoring as sc
from backend.logic import catalog as cat

# Study areas the planner allocates across. Reasoning skills are measured;
# eu_knowledge and test_strategy are driven by self-ratings until measured.
AREAS = ["verbal", "numerical", "abstract", "eu_knowledge", "test_strategy"]
AREA_LABEL = {
    "verbal": "Verbal reasoning",
    "numerical": "Numerical reasoning",
    "abstract": "Abstract reasoning",
    "eu_knowledge": "EU knowledge",
    "test_strategy": "Test strategy & mocks",
}
REASONING = ("verbal", "numerical", "abstract")
BASELINE_WEIGHT = 0.6  # unmeasured reasoning skill: needs a baseline, weight it up
MIN_SLICE_MIN = 15     # don't allocate slivers smaller than this


def _area_weights(profile: dict) -> dict:
    """Derive a raw weight per area from the profile. Higher = more time needed."""
    measured = profile.get("measured", {})
    self_rated = profile.get("self_rated", {}) or {}
    weights = {}

    # Reasoning: weight by measured gap; unmeasured -> baseline weight.
    for sk in REASONING:
        m = measured.get(sk)
        if m and m.get("score") is not None:
            weights[sk] = max(0.1, (100.0 - float(m["score"])) / 100.0)
        else:
            weights[sk] = BASELINE_WEIGHT

    # EU knowledge: measured if present, else from self eu_breadth (1-5).
    m_eu = measured.get("eu_knowledge")
    if m_eu and m_eu.get("score") is not None:
        weights["eu_knowledge"] = max(0.1, (100.0 - float(m_eu["score"])) / 100.0)
    else:
        eu = self_rated.get("eu_breadth")
        weights["eu_knowledge"] = (5 - eu) / 5.0 if eu else 0.4

    # Test strategy: from self strategy rating (1-5).
    strat = self_rated.get("strategy")
    weights["test_strategy"] = (5 - strat) / 5.0 if strat else 0.4

    return weights


def _time_to_exam_tilt(weights: dict, weeks_to_exam: Optional[int]) -> dict:
    """Closer to the exam -> tilt toward test strategy / mocks (exam readiness)."""
    if not weeks_to_exam:
        return weights
    if weeks_to_exam <= 4:
        weights = dict(weights)
        weights["test_strategy"] *= 1.6
    elif weeks_to_exam <= 8:
        weights = dict(weights)
        weights["test_strategy"] *= 1.25
    return weights


def compute_allocation(profile: dict) -> dict:
    """Pure function: profile -> {area: minutes_per_week}. Deterministic, testable."""
    constraints = profile.get("constraints", {}) or {}
    weekly_hours = constraints.get("weekly_hours") or 5
    total_min = int(weekly_hours) * 60

    weights = _time_to_exam_tilt(_area_weights(profile), constraints.get("weeks_to_exam"))
    wsum = sum(weights.values()) or 1.0

    # Proportional split, rounded to 15-min blocks, drop slivers, renormalise.
    raw = {a: total_min * weights[a] / wsum for a in AREAS}
    alloc = {a: int(round(raw[a] / 15.0)) * 15 for a in AREAS}
    alloc = {a: mins for a, mins in alloc.items() if mins >= MIN_SLICE_MIN}

    # Fix rounding drift so the total matches weekly minutes.
    drift = total_min - sum(alloc.values())
    if alloc and drift:
        top = max(alloc, key=lambda a: alloc[a])
        alloc[top] = max(MIN_SLICE_MIN, alloc[top] + drift)

    return {
        "weekly_minutes": total_min,
        "by_area": alloc,
        "weights": {a: round(weights[a], 3) for a in AREAS},
    }


_RATIONALE_SCHEMA = {
    "type": "object",
    "properties": {
        "rationale_md": {
            "type": "string",
            "description": "2-4 sentence markdown explaining why time is split this way, grounded in the scores and time-to-exam. Mention the single biggest priority.",
        }
    },
    "required": ["rationale_md"],
}


def _narrate_rationale(profile: dict, allocation: dict) -> Optional[str]:
    if not ai.is_configured():
        return None
    competition = allocation.get("competition") or {}
    comp_tests = competition.get("tests") or []
    try:
        out = ai.generate_json(
            schema=_RATIONALE_SCHEMA,
            system=(
                "You are an EPSO prep coach explaining a weekly study allocation to "
                "the candidate. Be concrete and grounded in the numbers provided; "
                "name the top priority; tie the focus to the tests THIS competition "
                "actually uses; do not invent scores; keep it short."
            ),
            user=(
                "Profile + allocation (JSON):\n"
                + json.dumps(
                    {
                        "measured": {k: v.get("score") for k, v in profile.get("measured", {}).items()},
                        "self_rated_1to5": profile.get("self_rated", {}),
                        "constraints": profile.get("constraints", {}),
                        "competition": {
                            "title": competition.get("title"),
                            "grade": competition.get("grade"),
                            "tests_you_will_face": cat.labels_for(comp_tests),
                        },
                        "weekly_minutes_by_area": allocation["by_area"],
                    },
                    default=str,
                )
                + "\n\nWrite the rationale. This is a first DRAFT plan that will "
                "sharpen as the candidate practises — frame it that way."
            ),
            tool_name="plan_rationale",
        )
        return out.get("rationale_md")
    except Exception:
        return None  # rationale is best-effort; never block plan generation


def generate_master_plan(
    db: Session,
    user_id: str,
    trigger_kind: str = "manual",
    trigger_event_id: Optional[str] = None,
) -> dict:
    """Compute + persist a master plan, superseding the previous active one."""
    profile = sc.build_profile(db, user_id)
    allocation = compute_allocation(profile)

    # Resolve the candidate's competition + the tests they'll actually face, and
    # attach to the allocation so it's persisted and shown on the plan. This
    # informs the narrative + which areas we surface — NOT the measured numeric
    # split (Risk-2: competition is a strategy modifier, not a daily driver).
    constraints = dict(profile.get("constraints") or {})
    constraints["target_competition_ref"] = cat.profile_target_ref(db, user_id)
    allocation["competition"] = cat.resolve_for_profile(db, constraints)

    rationale = _narrate_rationale(profile, allocation)

    # Supersede the current active master plan.
    inserted = db.execute(
        text(
            """
            insert into plans (user_id, kind, period_start, allocation, rationale_md, trigger_kind, trigger_event_id)
            values (:u, 'master', current_date, cast(:alloc as jsonb), :r, :tk, :te)
            returning id
            """
        ),
        {
            "u": user_id,
            "alloc": json.dumps(allocation),
            "r": rationale,
            "tk": trigger_kind,
            "te": trigger_event_id,
        },
    ).first()
    new_id = inserted[0]
    db.execute(
        text(
            """
            update plans set superseded_by = :new
            where user_id = :u and kind = 'master' and id <> :new and superseded_by is null
            """
        ),
        {"new": new_id, "u": user_id},
    )
    db.execute(
        text("insert into events (user_id, kind, payload) values (:u, 'plan_generated', :p)"),
        {"u": user_id, "p": json.dumps({"plan_id": str(new_id), "trigger": trigger_kind})},
    )
    db.commit()
    return {
        "plan_id": str(new_id),
        "allocation": allocation,
        "rationale_md": rationale,
        "trigger_kind": trigger_kind,
    }


def active_master_plan(db: Session, user_id: str) -> Optional[dict]:
    row = db.execute(
        text(
            """
            select id, allocation, rationale_md, created_at, trigger_kind
            from plans
            where user_id = :u and kind = 'master' and superseded_by is null
            order by created_at desc limit 1
            """
        ),
        {"u": user_id},
    ).mappings().first()
    if not row:
        return None
    alloc = row["allocation"]
    if isinstance(alloc, str):
        alloc = json.loads(alloc)
    return {
        "plan_id": str(row["id"]),
        "allocation": alloc,
        "rationale_md": row["rationale_md"],
        "trigger_kind": row["trigger_kind"],
        "created_at": row["created_at"].isoformat(),
    }


def generate_daily_plan(
    db: Session,
    user_id: str,
    minutes_available: Optional[int] = None,
    energy: str = "medium",
) -> dict:
    """Turn the active master allocation into today's ordered task list."""
    master = active_master_plan(db, user_id)
    if not master:
        return {"tasks": [], "minutes": 0, "needs_plan": True}

    by_area = master["allocation"]["by_area"]
    weekly_total = sum(by_area.values()) or 1
    # default to an even slice of the week (assume ~5 study days)
    minutes = minutes_available or max(MIN_SLICE_MIN, int(round(weekly_total / 5 / 15)) * 15)

    # Rank areas by weekly weight; high energy -> hardest (top) area first.
    ranked = sorted(by_area.items(), key=lambda kv: kv[1], reverse=True)
    tasks = []
    remaining = minutes
    for area, wk_min in ranked:
        if remaining < MIN_SLICE_MIN:
            break
        share = max(MIN_SLICE_MIN, int(round((wk_min / weekly_total) * minutes / 15)) * 15)
        share = min(share, remaining)
        tasks.append({"area": area, "label": AREA_LABEL.get(area, area), "minutes": share})
        remaining -= share

    if energy == "low":
        # lighter day: gentler ordering (easiest-weighted first), trim last task
        tasks = list(reversed(tasks))

    return {
        "tasks": tasks,
        "minutes": sum(t["minutes"] for t in tasks),
        "energy": energy,
        "needs_plan": False,
    }
