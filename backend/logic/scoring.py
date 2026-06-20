"""Profile scoring + LLM-narrated insights (Session 4).

Combines three sources into one profile, per the build plan's Risk-3 fix:
  - MEASURED reasoning skills (real % correct from diagnostics) — the trustworthy
    numbers. Currently: verbal. Numerical/abstract/EU follow once item banks exist.
  - SELF-RATED soft dimensions (1-5 Likerts from intake) — habits, strategy,
    EU-knowledge breadth. The LLM may *narrate* these but does not invent the
    reasoning numbers.
  - CONSTRAINTS from intake (weeks to exam, weekly hours, prior experience).

The LLM produces only a narrated strategy note (strengths, focus areas, a
go/no-go read), never the measured scores. Output is JSON-schema-validated.
The narrative is cached as an `events` row (kind='profile_generated') so we don't
pay for a regeneration on every page load and avoid a schema change.
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.ai import client as ai

SKILL_NAMES = {
    "verbal": "Verbal reasoning",
    "numerical": "Numerical reasoning",
    "abstract": "Abstract reasoning",
    "eu_knowledge": "EU knowledge",
}


def build_profile(db: Session, user_id: str) -> dict:
    """Assemble the structured profile (no LLM). Pure read of DB state."""
    prof = db.execute(
        text(
            """
            select target_competition, weeks_to_exam, weekly_hours, energy_pattern,
                   has_prior_epso_experience, last_epso_test_at,
                   self_habits_score, self_strategy_score, self_eu_breadth_score
            from profiles where user_id = :u
            """
        ),
        {"u": user_id},
    ).mappings().first()

    # Latest measured score per skill from completed diagnostics
    measured_rows = db.execute(
        text(
            """
            select distinct on (skill_id) skill_id, score, completed_at
            from diagnostic_sessions
            where user_id = :u and completed_at is not null
            order by skill_id, completed_at desc
            """
        ),
        {"u": user_id},
    ).mappings().all()
    measured = {
        r["skill_id"]: {
            "skill": r["skill_id"],
            "label": SKILL_NAMES.get(r["skill_id"], r["skill_id"]),
            "score": float(r["score"]) if r["score"] is not None else None,
            "measured_at": r["completed_at"].isoformat() if r["completed_at"] else None,
        }
        for r in measured_rows
    }

    self_rated = {}
    constraints = {}
    if prof:
        self_rated = {
            "habits": prof["self_habits_score"],
            "strategy": prof["self_strategy_score"],
            "eu_breadth": prof["self_eu_breadth_score"],
        }
        constraints = {
            "target_competition": prof["target_competition"],
            "weeks_to_exam": prof["weeks_to_exam"],
            "weekly_hours": prof["weekly_hours"],
            "energy_pattern": prof["energy_pattern"],
            "has_prior_epso_experience": prof["has_prior_epso_experience"],
        }

    # Completeness: what's missing to make scoring trustworthy
    missing = []
    if not prof or not prof["target_competition"]:
        missing.append("intake")
    if "verbal" not in measured:
        missing.append("verbal_diagnostic")

    return {
        "measured": measured,
        "self_rated": self_rated,
        "constraints": constraints,
        "completeness": {"missing": missing, "ready_for_plan": len(missing) == 0},
    }


# JSON schema the LLM must satisfy. Forced via tool use -> always valid.
NARRATIVE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "2-3 sentence read of where this candidate stands.",
        },
        "strengths": {
            "type": "array",
            "items": {"type": "string"},
            "description": "1-3 concrete strengths grounded in the data.",
        },
        "focus_areas": {
            "type": "array",
            "items": {"type": "string"},
            "description": "1-3 areas to prioritise, grounded in measured gaps and time-to-exam.",
        },
        "strategy_note": {
            "type": "string",
            "description": "One actionable strategic note given weeks-to-exam and weekly hours.",
        },
        "go_no_go": {
            "type": "string",
            "enum": ["on_track", "tight", "at_risk"],
            "description": "Feasibility read for the target competition in the time available.",
        },
    },
    "required": ["summary", "strengths", "focus_areas", "strategy_note", "go_no_go"],
}

_SYSTEM = (
    "You are an EPSO preparation coach. You are given a candidate's MEASURED "
    "reasoning scores (0-100, from real adaptive tests), their SELF-RATED soft "
    "dimensions (1-5), and their constraints. Write a short, grounded, honest "
    "profile read. Rules: never invent scores; base strengths/focus strictly on "
    "the data given; if a skill is unmeasured, treat it as unknown, not weak; be "
    "concrete and EPSO-specific; no fluff. Calibrate go_no_go from measured gaps "
    "vs weeks_to_exam and weekly_hours."
)


def generate_narrative(db: Session, user_id: str, profile: dict) -> dict:
    """Call the LLM for a schema-validated narrative and cache it as an event."""
    user_msg = (
        "Candidate data (JSON):\n"
        + json.dumps(
            {
                "measured": {k: v["score"] for k, v in profile["measured"].items()},
                "self_rated_1to5": profile["self_rated"],
                "constraints": profile["constraints"],
            },
            default=str,
        )
        + "\n\nProduce the profile read."
    )
    narrative = ai.generate_json(
        schema=NARRATIVE_SCHEMA, system=_SYSTEM, user=user_msg, tool_name="profile_read"
    )
    db.execute(
        text("insert into events (user_id, kind, payload) values (:u, 'profile_generated', :p)"),
        {"u": user_id, "p": json.dumps(narrative)},
    )
    db.commit()
    return narrative


def latest_narrative(db: Session, user_id: str) -> Optional[dict]:
    """Most recent cached narrative, or None."""
    row = db.execute(
        text(
            """
            select payload, created_at from events
            where user_id = :u and kind = 'profile_generated'
            order by created_at desc limit 1
            """
        ),
        {"u": user_id},
    ).mappings().first()
    if not row:
        return None
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return {"narrative": payload, "generated_at": row["created_at"].isoformat()}
