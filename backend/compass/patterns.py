"""Compass pattern analysis — the LLM that turns a dimension-mastery matrix
into 1-3 plain-English patterns + focus dimensions for the next session.

Trigger model:
  - Called from practice.finalize_practice_session after a session ends.
  - Skips if the user has < MIN_RESPONSES_FOR_ANALYSIS dimension-tagged answers
    in this skill (not enough signal).
  - Skips if a fresh analysis exists from < MIN_REFRESH_INTERVAL_MIN ago
    (cost guard — at most one LLM call per user per skill per 30 min).
  - On error: logs `events.pattern_analysis_failed` and returns None. The
    caller swallows — pattern analysis must never block a practice session.

What it writes:
  - One row in `pattern_analyses` (append-only; latest row wins per user×skill).
  - One `events.pattern_updated` event.

What it reads:
  - `dimension_mastery` (the rolling accuracy table).
  - `practice_sessions` (last 3 sessions for context).
  - `item_responses` (distractor-class frequencies for wrong answers).
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.ai import client as ai_client

log = logging.getLogger(__name__)

# Skip pattern analysis below this many tagged answers — too noisy.
MIN_RESPONSES_FOR_ANALYSIS = 20

# Don't run more often than this per (user, skill). Pure cost guard.
MIN_REFRESH_INTERVAL_MIN = 30

# Anthropic model used (logged on the row for drift detection).
MODEL_VERSION = "claude-haiku-4-5"


# =============================================================================
# Output schema — the JSON shape the LLM must produce
# =============================================================================

ANALYSIS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["patterns", "focus_dimensions", "insight_md"],
    "properties": {
        "patterns": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["summary", "evidence_dims", "depth", "confidence"],
                "properties": {
                    "summary": {
                        "type": "string",
                        "minLength": 30,
                        "maxLength": 240,
                        "description": "One-sentence plain-English description of the pattern.",
                    },
                    "evidence_dims": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string"},
                        "description": "Names of dimensions that support this pattern (e.g. 'inference_depth', 'quantifier_scope').",
                    },
                    "depth": {
                        "type": "string",
                        "enum": ["surface", "underlying"],
                        "description": "'surface' = topic-level pattern. 'underlying' = cognitive-operation pattern that explains errors across topics.",
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "description": "How confident the pattern is. Be honest — low confidence is fine when the data is sparse.",
                    },
                },
            },
        },
        "focus_dimensions": {
            "type": "array",
            "minItems": 1,
            "maxItems": 5,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["dimension_name", "dimension_value"],
                "properties": {
                    "dimension_name": {"type": "string"},
                    "dimension_value": {"type": "string"},
                },
            },
            "description": "3-5 dimension values to target in the next session's slot distribution.",
        },
        "insight_md": {
            "type": "string",
            "minLength": 80,
            "maxLength": 700,
            "description": "Plain-English summary for the /me 'What we have learned about you' panel. 80-150 words. Address the user directly ('you'). Cite the specific numbers from the mastery summary.",
        },
    },
}


# =============================================================================
# Public API
# =============================================================================

def latest_pattern(db: Session, *, user_id: str, skill_id: str) -> Optional[dict]:
    """Return the most recent pattern_analyses row for (user, skill), or None."""
    row = db.execute(
        text(
            """
            select id, generated_at, focus_dimensions, insight_md, model_version, payload
            from pattern_analyses
            where user_id = :u and skill_id = :s
            order by generated_at desc
            limit 1
            """
        ),
        {"u": user_id, "s": skill_id},
    ).mappings().first()
    return dict(row) if row else None


def should_refresh(db: Session, *, user_id: str, skill_id: str) -> tuple[bool, str]:
    """Return (yes_no, reason) — whether we should run the LLM analysis now.

    Reason is one of: 'no_recent_analysis_and_enough_data' | 'fresh_enough_already'
    | 'insufficient_data' | 'no_tagged_responses'.
    """
    # Enough tagged responses to bother?
    n_tagged = db.execute(
        text(
            """
            select count(*)
            from item_responses r
            join items i on i.id = r.item_id
            join practice_sessions ps on ps.id = r.practice_session_id
            where ps.user_id = :u
              and i.skill_id = :s
              and i.dimensions is not null
            """
        ),
        {"u": user_id, "s": skill_id},
    ).scalar()
    if not n_tagged:
        return (False, "no_tagged_responses")
    if int(n_tagged) < MIN_RESPONSES_FOR_ANALYSIS:
        return (False, "insufficient_data")

    # Recent analysis exists?
    recent = db.execute(
        text(
            """
            select generated_at from pattern_analyses
            where user_id = :u and skill_id = :s
              and generated_at >= now() - (interval '1 minute' * :mins)
            order by generated_at desc limit 1
            """
        ),
        {"u": user_id, "s": skill_id, "mins": MIN_REFRESH_INTERVAL_MIN},
    ).first()
    if recent is not None:
        return (False, "fresh_enough_already")

    return (True, "no_recent_analysis_and_enough_data")


def compute_dimension_summary(db: Session, *, user_id: str, skill_id: str) -> dict:
    """Build the structured input the LLM sees.

    Returns a dict shaped like:
        {
            "overall_accuracy_pct": 62.5,
            "n_tagged_responses": 35,
            "dimensions": [
                {"name": "inference_depth", "value": "multi_premise_inference",
                 "attempts": 6, "correct": 2, "accuracy_pct": 33.3},
                ...
            ],
            "distractor_class_counts": {"scope_strengthening": 4, "outside_knowledge": 2, ...},
            "recent_sessions": [
                {"completed_at": "2026-06-23T...", "items_attempted": 5, "items_correct": 3, "accuracy_pct": 60.0},
                ...
            ]
        }
    """
    # Per-dimension mastery
    dim_rows = db.execute(
        text(
            """
            select dimension_name, dimension_value, attempts, correct
            from dimension_mastery
            where user_id = :u and skill_id = :s
            order by attempts desc, dimension_name, dimension_value
            """
        ),
        {"u": user_id, "s": skill_id},
    ).all()

    dimensions = []
    total_attempts = 0
    total_correct = 0
    for name, value, attempts, correct in dim_rows:
        if not attempts:
            continue
        acc = round(100.0 * correct / attempts, 1)
        dimensions.append(
            {
                "name": name,
                "value": value,
                "attempts": int(attempts),
                "correct": int(correct),
                "accuracy_pct": acc,
            }
        )
        total_attempts += int(attempts)
        total_correct += int(correct)

    # NB: total_attempts here counts every dim-row attempt, which double-counts the
    # underlying answer across the 9 dimensions on each item. For "overall accuracy"
    # use practice_sessions instead.
    sess_rows = db.execute(
        text(
            """
            select items_attempted, items_correct, completed_at
            from practice_sessions
            where user_id = :u and skill_id = :s and completed_at is not null
            order by completed_at desc
            limit 3
            """
        ),
        {"u": user_id, "s": skill_id},
    ).mappings().all()

    recent_sessions = []
    sess_total_a = 0
    sess_total_c = 0
    for r in sess_rows:
        ia = int(r["items_attempted"]) if r["items_attempted"] is not None else 0
        ic = int(r["items_correct"]) if r["items_correct"] is not None else 0
        sess_total_a += ia
        sess_total_c += ic
        recent_sessions.append(
            {
                "completed_at": r["completed_at"].isoformat() if r["completed_at"] else None,
                "items_attempted": ia,
                "items_correct": ic,
                "accuracy_pct": round(100.0 * ic / ia, 1) if ia else 0.0,
            }
        )

    overall_acc = round(100.0 * sess_total_c / sess_total_a, 1) if sess_total_a else 0.0

    # Distractor-class frequencies for wrong answers
    dc_rows = db.execute(
        text(
            """
            select unnest(distractor_class_picked) as dc, count(*) as n
            from item_responses r
            join practice_sessions ps on ps.id = r.practice_session_id
            join items i on i.id = r.item_id
            where ps.user_id = :u
              and i.skill_id = :s
              and r.is_correct = false
              and r.distractor_class_picked is not null
            group by 1
            order by n desc
            """
        ),
        {"u": user_id, "s": skill_id},
    ).all()
    distractor_class_counts = {dc: int(n) for dc, n in dc_rows}

    # n_tagged_responses = unique item answers with a tagged item
    n_tagged = db.execute(
        text(
            """
            select count(*)
            from item_responses r
            join items i on i.id = r.item_id
            join practice_sessions ps on ps.id = r.practice_session_id
            where ps.user_id = :u
              and i.skill_id = :s
              and i.dimensions is not null
            """
        ),
        {"u": user_id, "s": skill_id},
    ).scalar() or 0

    return {
        "overall_accuracy_pct": overall_acc,
        "n_tagged_responses": int(n_tagged),
        "dimensions": dimensions,
        "distractor_class_counts": distractor_class_counts,
        "recent_sessions": recent_sessions,
    }


def run_pattern_analysis(
    db: Session,
    *,
    user_id: str,
    skill_id: str,
    force: bool = False,
) -> Optional[dict]:
    """Run the LLM pattern analysis. Returns the saved row dict, or None if
    skipped (insufficient data / fresh-enough / LLM failure).

    `force=True` bypasses the should_refresh gate — use for admin refresh
    endpoint / smoke tests.
    """
    if not force:
        ok, reason = should_refresh(db, user_id=user_id, skill_id=skill_id)
        if not ok:
            log.info("pattern analysis skipped: user=%s skill=%s reason=%s", user_id, skill_id, reason)
            return None

    summary = compute_dimension_summary(db, user_id=user_id, skill_id=skill_id)

    system_prompt = (
        "You are a psychometrician advising an EPSO candidate on their reasoning patterns. "
        "Given a dimension-mastery summary for one skill, identify 1-3 actionable failure patterns. "
        "Distinguish SURFACE patterns ('weak on percentage questions') from UNDERLYING patterns "
        "('weak whenever a calculation chains, regardless of topic'). Cite the specific numbers from "
        "the summary. Be honest about confidence — when the data is sparse or noisy, say so. "
        "Recommend 3-5 dimension values to target in the next practice session. "
        "Write a plain-English insight (80-150 words) for the user, addressing them directly as 'you' "
        "and naming the dimensions and numbers that justify your read. "
        "Do not invent data: every claim must trace to a number in the summary."
    )

    user_prompt = (
        "Here is the candidate's practice-mastery summary for skill: "
        + skill_id
        + ".\n\nSummary (JSON):\n"
        + json.dumps(summary, indent=2, ensure_ascii=False)
        + "\n\nProduce the analysis via the tool call."
    )

    try:
        analysis = ai_client.generate_json(
            schema=ANALYSIS_SCHEMA,
            system=system_prompt,
            user=user_prompt,
            tool_name="emit_pattern_analysis",
            max_tokens=1500,
        )
    except Exception as exc:
        log.exception("pattern_analysis LLM call failed")
        db.execute(
            text(
                "insert into events (user_id, kind, payload) values (:u, 'pattern_analysis_failed', :p)"
            ),
            {
                "u": user_id,
                "p": json.dumps({"skill_id": skill_id, "error": str(exc)[:500]}),
            },
        )
        db.commit()
        return None

    # Persist
    row = db.execute(
        text(
            """
            insert into pattern_analyses (user_id, skill_id, focus_dimensions, insight_md, model_version, payload)
            values (:u, :s, cast(:fd as jsonb), :im, :mv, cast(:pl as jsonb))
            returning id, generated_at, focus_dimensions, insight_md, model_version, payload
            """
        ),
        {
            "u": user_id,
            "s": skill_id,
            "fd": json.dumps(analysis["focus_dimensions"]),
            "im": analysis["insight_md"],
            "mv": MODEL_VERSION,
            "pl": json.dumps({"patterns": analysis["patterns"], "summary_input": summary}),
        },
    ).mappings().first()

    db.execute(
        text(
            "insert into events (user_id, kind, payload) values (:u, 'pattern_updated', :p)"
        ),
        {
            "u": user_id,
            "p": json.dumps(
                {
                    "skill_id": skill_id,
                    "pattern_analysis_id": str(row["id"]),
                    "n_patterns": len(analysis["patterns"]),
                    "n_focus_dimensions": len(analysis["focus_dimensions"]),
                }
            ),
        },
    )
    db.commit()
    return dict(row)
