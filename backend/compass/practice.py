"""Compass practice — the bank-first picker, session lifecycle, mastery updates.

This is the orchestration layer that turns Compass's primitives (item bank,
dimension tags, pattern analyses, the LLM generator) into a working practice loop.

Key design points:
1. **Bank-first.** Try `items` for an unseen-by-user, dimension-matching, active item.
   Only call generate_item() when nothing matches. After ~50 users the bank dominates.
2. **Slot targeting.** When a user has a pattern analysis, 60% of slots target the
   focus dimensions, 30% target the user's weakest non-focus dimensions, 10% are control
   (a strong dimension, to detect regression). When no analysis exists, fall back to
   uniform-random targeting.
3. **Never repeats.** An item never appears twice for the same user — calibration OR
   practice. The unseen filter joins against item_responses regardless of session type.
4. **Difficulty adapts.** Same ±1 rule as calibration: +1 on correct, -1 on incorrect,
   clamped to [1, 3]. Starts at the user's last calibration score band when known,
   default 2 otherwise.
5. **Mastery updates on every answer.** Each dimension value the item carries gets its
   row in dimension_mastery upserted: +1 attempts, +1 correct if right.

This module ONLY exports practice operations — it does not own the LLM call (that's
in generate_item.py) and does not own pattern analysis (commit 5). It reads
pattern_analyses; it writes dimension_mastery + practice_sessions + item_responses.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.compass import generate_item as gen


MIN_DIFFICULTY = 1
MAX_DIFFICULTY = 3
DEFAULT_DIFFICULTY = 2

# Slot distribution probabilities. Sum to 1.0.
P_FOCUS = 0.6
P_WEAK = 0.3
P_CONTROL = 0.1

# Dimensions to target per skill. Pulled from COGNITIVE_DIMENSIONS.md §2.2 (verbal).
# Numerical/abstract not yet supported (text-only generator).
_VERBAL_DIMENSIONS: list[str] = [
    "inference_depth",
    "external_knowledge_lure",
    "quantifier_scope",
    "negation_management",
    "partial_truth_completeness",
    "cross_sentence_integration",
    "cannot_say_vs_false_discrimination",
    "referent_tracking",
    "conditional_logic",
]


@dataclass
class NextItem:
    item_id: str
    difficulty: int
    prompt: str
    options: list
    # whether this item came from the bank (cheap) or was just generated (expensive)
    source: str  # 'bank' | 'generated'


# =============================================================================
# Session lifecycle
# =============================================================================

def start_practice_session(
    db: Session,
    *,
    user_id: str,
    skill_id: str,
    target_length: int = 20,
    plan_id: Optional[str] = None,
) -> str:
    """Create a practice_sessions row, return its id."""
    if skill_id != "verbal":
        raise ValueError(f"compass v1 supports skill_id='verbal' only; got {skill_id!r}")
    if not (1 <= target_length <= 100):
        raise ValueError(f"target_length must be 1-100, got {target_length}")

    row = db.execute(
        text(
            """
            insert into practice_sessions (user_id, skill_id, target_length, plan_id)
            values (:u, :s, :tl, :pid)
            returning id
            """
        ),
        {"u": user_id, "s": skill_id, "tl": target_length, "pid": plan_id},
    ).first()
    db.commit()
    return str(row[0])


def finalize_practice_session(db: Session, session_id: str) -> dict:
    """Compute summary statistics, mark completed, emit events.practice_completed."""
    rows = db.execute(
        text(
            """
            select i.difficulty, r.is_correct, r.time_taken_ms,
                   r.distractor_class_picked
            from item_responses r
            join items i on i.id = r.item_id
            where r.practice_session_id = :s
            """
        ),
        {"s": session_id},
    ).all()

    items_attempted = len(rows)
    items_correct = sum(1 for r in rows if r[1])
    accuracy_pct = round(100.0 * items_correct / items_attempted, 1) if items_attempted else 0.0
    times = sorted([r[2] for r in rows if r[2] is not None])
    median = times[len(times) // 2] if times else None

    # Distractor-class frequency for the dimensional end-screen
    dc_counts: dict[str, int] = {}
    for r in rows:
        for dc in (r[3] or []):
            dc_counts[dc] = dc_counts.get(dc, 0) + 1

    db.execute(
        text(
            """
            update practice_sessions
            set completed_at = now(),
                items_attempted = :ia,
                items_correct = :ic,
                median_time_ms = :mt
            where id = :s
            """
        ),
        {"ia": items_attempted, "ic": items_correct, "mt": median, "s": session_id},
    )

    sess = db.execute(
        text("select user_id, skill_id from practice_sessions where id = :s"),
        {"s": session_id},
    ).first()
    if sess is not None:
        db.execute(
            text("insert into events (user_id, kind, payload) values (:u, 'practice_completed', :p)"),
            {
                "u": sess[0],
                "p": json.dumps({
                    "session_id": session_id,
                    "skill_id": sess[1],
                    "items_attempted": items_attempted,
                    "items_correct": items_correct,
                    "accuracy_pct": accuracy_pct,
                }),
            },
        )
    db.commit()

    # Build the dimensional observation for the end-screen
    observation = _build_dimensional_observation(db, session_id)

    # Trigger pattern analysis if eligible (≥20 tagged answers, not refreshed recently).
    # Errors here are non-fatal — pattern analysis must never block a finished session.
    if sess is not None:
        try:
            from backend.compass import patterns as compass_patterns
            compass_patterns.run_pattern_analysis(db, user_id=str(sess[0]), skill_id=sess[1])
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "pattern analysis raised during finalize; swallowing"
            )

    return {
        "session_id": session_id,
        "items_attempted": items_attempted,
        "items_correct": items_correct,
        "accuracy_pct": accuracy_pct,
        "median_time_ms": median,
        "distractor_class_counts": dc_counts,
        "observation": observation,
    }


def _build_dimensional_observation(db: Session, session_id: str) -> Optional[str]:
    """Find the dimension value with the biggest accuracy gap in this session and return
    a single-sentence plain-English observation about it. None if no clean signal."""
    rows = db.execute(
        text(
            """
            select i.dimensions, r.is_correct
            from item_responses r
            join items i on i.id = r.item_id
            where r.practice_session_id = :s
              and i.dimensions is not null
            """
        ),
        {"s": session_id},
    ).all()
    if len(rows) < 4:
        return None

    # Aggregate per (dimension_name, value)
    by_dim: dict[tuple[str, str], list[bool]] = {}
    for dims, correct in rows:
        if not isinstance(dims, dict):
            continue
        for dname, dvalue in dims.items():
            by_dim.setdefault((dname, str(dvalue)), []).append(bool(correct))

    # Find a dimension where 2+ attempts exist AND accuracy is < 40% (a clear pain point)
    candidates: list[tuple[float, str, str, int, int]] = []
    for (dname, dvalue), correct_list in by_dim.items():
        n = len(correct_list)
        if n < 2:
            continue
        ncorrect = sum(correct_list)
        acc = ncorrect / n
        if acc < 0.4:
            candidates.append((acc, dname, dvalue, ncorrect, n))

    if not candidates:
        return None
    candidates.sort()  # lowest accuracy first
    acc, dname, dvalue, ncorrect, n = candidates[0]
    return (
        f"Most of the errors clustered on items where {dname} = {dvalue!r} "
        f"({ncorrect}/{n} correct). Tomorrow's plan slot will weight these more heavily."
    )


# =============================================================================
# Picker (the strategic core)
# =============================================================================

def pick_practice_item(db: Session, session_id: str) -> Optional[NextItem]:
    """Return the next adaptive item, or None if the session is over."""
    sess = db.execute(
        text(
            """
            select user_id, skill_id, items_attempted, target_length
            from practice_sessions
            where id = :s
            """
        ),
        {"s": session_id},
    ).first()
    if sess is None:
        return None
    user_id, skill_id, items_attempted, target_length = sess

    if items_attempted >= target_length:
        return None

    # 1. Decide the target difficulty (adaptive ±1; default 2)
    target_diff = _difficulty_for_next(db, session_id)

    # 2. Choose a target dimension based on the slot distribution
    target_dim = _choose_target_dimension(db, user_id=str(user_id), skill_id=skill_id)

    # 3. Try the bank — unseen by this user (any session), matching difficulty,
    #    and ideally matching the target dimension
    item = _query_bank(
        db,
        user_id=str(user_id),
        skill_id=skill_id,
        difficulty=target_diff,
        target_dim=target_dim,
    )
    if item is not None:
        return NextItem(
            item_id=str(item[0]),
            difficulty=int(item[1]),
            prompt=item[2],
            options=item[3] or [],
            source="bank",
        )

    # 4. Bank dry. Call the generator with the target dimension as a constraint.
    recent_tags = _recent_topic_tags(db, user_id=str(user_id), skill_id=skill_id)
    target_dims_dict = {target_dim["name"]: target_dim["value"]} if target_dim else None
    generated = gen.generate_item(
        skill_id=skill_id,
        difficulty=target_diff,
        target_dimensions=target_dims_dict,
        recent_topic_tags=recent_tags,
        user_id=str(user_id),
    )
    if generated is None:
        # generation failed or capped — last-resort fallback: any unseen item of any
        # difficulty / dimension. Returns None if even that's empty.
        fallback = _query_bank_fallback(db, user_id=str(user_id), skill_id=skill_id)
        if fallback is None:
            return None
        return NextItem(
            item_id=str(fallback[0]),
            difficulty=int(fallback[1]),
            prompt=fallback[2],
            options=fallback[3] or [],
            source="bank",
        )

    # Newly generated items default to archived=true (per COMPASS_AUTOAPPROVE_GENERATED=false).
    # The picker is allowed to serve generated items immediately to the user who triggered them —
    # the archived flag protects against OTHER users seeing un-audited items. We surface the
    # generated item directly by id.
    return NextItem(
        item_id=str(generated["id"]),
        difficulty=int(generated["difficulty"]),
        prompt=generated["prompt"],
        options=generated["options"],
        source="generated",
    )


# =============================================================================
# Answer recording + mastery upsert
# =============================================================================

def record_practice_answer(
    db: Session,
    *,
    session_id: str,
    item_id: str,
    selected_index: int,
    time_taken_ms: Optional[int],
) -> dict:
    """Record the response, update mastery, return feedback for the UI."""
    item = db.execute(
        text(
            """
            select correct_index, explanation, dimensions, option_diagnostics, skill_id
            from items where id = :i
            """
        ),
        {"i": item_id},
    ).first()
    if item is None:
        raise ValueError(f"item not found: {item_id}")
    correct_index, explanation, dims, option_diagnostics, skill_id = item
    is_correct = (selected_index == correct_index)

    # Look up the distractor classes the user picked (if wrong)
    distractor_classes: list[str] = []
    if not is_correct and option_diagnostics:
        for d in option_diagnostics:
            if d.get("index") == selected_index:
                distractor_classes = d.get("distractor_classes", [])
                break

    # Persist the response row
    db.execute(
        text(
            """
            insert into item_responses (
                practice_session_id, item_id, selected_index, is_correct,
                time_taken_ms, distractor_class_picked
            ) values (:s, :i, :sel, :c, :t, :dc)
            """
        ),
        {
            "s": session_id,
            "i": item_id,
            "sel": selected_index,
            "c": is_correct,
            "t": time_taken_ms,
            "dc": distractor_classes or None,
        },
    )

    # Bump counters on practice_sessions
    db.execute(
        text(
            """
            update practice_sessions
            set items_attempted = items_attempted + 1,
                items_correct = items_correct + (case when :c then 1 else 0 end)
            where id = :s
            """
        ),
        {"c": is_correct, "s": session_id},
    )

    # Item-level calibration counters (same pattern as diagnostic engine)
    db.execute(
        text(
            """
            update items
            set times_shown = times_shown + 1,
                times_correct = times_correct + (case when :c then 1 else 0 end)
            where id = :i
            """
        ),
        {"c": is_correct, "i": item_id},
    )

    # Dimension mastery upsert — one row per (user, skill, dimension_name, dimension_value)
    sess = db.execute(
        text("select user_id from practice_sessions where id = :s"),
        {"s": session_id},
    ).first()
    user_id = str(sess[0]) if sess else None
    if user_id and isinstance(dims, dict):
        for dname, dvalue in dims.items():
            db.execute(
                text(
                    """
                    insert into dimension_mastery (user_id, skill_id, dimension_name, dimension_value, attempts, correct)
                    values (:u, :s, :dn, :dv, 1, :c)
                    on conflict (user_id, skill_id, dimension_name, dimension_value) do update set
                        attempts = dimension_mastery.attempts + 1,
                        correct = dimension_mastery.correct + :c,
                        last_updated = now()
                    """
                ),
                {
                    "u": user_id,
                    "s": skill_id,
                    "dn": dname,
                    "dv": str(dvalue),
                    "c": 1 if is_correct else 0,
                },
            )

    db.commit()

    return {
        "is_correct": is_correct,
        "correct_index": correct_index,
        "explanation": explanation,
        "distractor_classes_picked": distractor_classes,
    }


# =============================================================================
# Helpers
# =============================================================================

def _difficulty_for_next(db: Session, session_id: str) -> int:
    """+1 on last correct, -1 otherwise. Default DEFAULT_DIFFICULTY when no answers yet."""
    last = db.execute(
        text(
            """
            select i.difficulty, r.is_correct
            from item_responses r
            join items i on i.id = r.item_id
            where r.practice_session_id = :s
            order by r.answered_at desc
            limit 1
            """
        ),
        {"s": session_id},
    ).first()
    if last is None:
        return DEFAULT_DIFFICULTY
    diff, correct = last
    target = diff + (1 if correct else -1)
    return max(MIN_DIFFICULTY, min(MAX_DIFFICULTY, target))


def _choose_target_dimension(
    db: Session,
    *,
    user_id: str,
    skill_id: str,
    rng: Optional[random.Random] = None,
) -> Optional[dict]:
    """Return {"name": ..., "value": ...} or None (= no dimension constraint).

    Logic:
      P_FOCUS  → pick from focus_dimensions in latest pattern_analyses (if any)
      P_WEAK   → pick user's weakest dimension value (by accuracy among ≥2-attempts rows)
      P_CONTROL→ pick user's strongest (regression detection)
      Fallback if either lookup is empty: return None (no constraint).
    """
    rng = rng or random

    # Latest pattern analysis for this skill (if any)
    pa = db.execute(
        text(
            """
            select focus_dimensions
            from pattern_analyses
            where user_id = :u and skill_id = :s
            order by generated_at desc
            limit 1
            """
        ),
        {"u": user_id, "s": skill_id},
    ).first()

    bucket = rng.random()
    if bucket < P_FOCUS and pa and pa[0]:
        focus = pa[0]  # JSONB list of {dimension_name, dimension_value}
        if isinstance(focus, list) and focus:
            chosen = rng.choice(focus)
            return {"name": chosen["dimension_name"], "value": str(chosen["dimension_value"])}

    # Weakest / strongest from mastery
    mastery = db.execute(
        text(
            """
            select dimension_name, dimension_value, attempts, correct
            from dimension_mastery
            where user_id = :u and skill_id = :s and attempts >= 2
            """
        ),
        {"u": user_id, "s": skill_id},
    ).all()

    if mastery:
        with_acc = [(r[0], r[1], r[3] / r[2]) for r in mastery]
        if bucket < P_FOCUS + P_WEAK:
            with_acc.sort(key=lambda x: x[2])  # weakest first
            name, value, _ = with_acc[0]
            return {"name": name, "value": str(value)}
        # control: strongest
        with_acc.sort(key=lambda x: -x[2])  # strongest first
        name, value, _ = with_acc[0]
        return {"name": name, "value": str(value)}

    # No pattern + no mastery yet: uniform random across the dimension keys.
    # Picking a dimension *name* without a target value still helps the bank-query
    # avoid repetition; we leave value=None (the picker handles that case).
    if skill_id == "verbal":
        return {"name": rng.choice(_VERBAL_DIMENSIONS), "value": None}
    return None


def _query_bank(
    db: Session,
    *,
    user_id: str,
    skill_id: str,
    difficulty: int,
    target_dim: Optional[dict],
) -> Optional[tuple]:
    """Try to find an unseen-by-user, active item at the target difficulty.
    Prefers items matching the target dimension; falls back to any difficulty match.
    Returns the row tuple (id, difficulty, prompt, options) or None.
    """
    # First attempt: matching dimension + target difficulty
    if target_dim and target_dim.get("value"):
        row = db.execute(
            text(
                """
                select i.id, i.difficulty, i.prompt, i.options
                from items i
                where i.skill_id = :sk
                  and not i.archived
                  and i.difficulty = :d
                  and i.dimensions is not null
                  and i.dimensions ->> :dn = :dv
                  and i.id not in (
                      select item_id from item_responses where
                        practice_session_id in (select id from practice_sessions where user_id = :u)
                        or session_id in (select id from diagnostic_sessions where user_id = :u)
                  )
                order by random()
                limit 1
                """
            ),
            {"sk": skill_id, "d": difficulty, "dn": target_dim["name"], "dv": target_dim["value"], "u": user_id},
        ).first()
        if row is not None:
            return row

    # Second attempt: just the target difficulty (no dimension constraint)
    row = db.execute(
        text(
            """
            select i.id, i.difficulty, i.prompt, i.options
            from items i
            where i.skill_id = :sk
              and not i.archived
              and i.difficulty = :d
              and i.id not in (
                  select item_id from item_responses where
                    practice_session_id in (select id from practice_sessions where user_id = :u)
                    or session_id in (select id from diagnostic_sessions where user_id = :u)
              )
            order by random()
            limit 1
            """
        ),
        {"sk": skill_id, "d": difficulty, "u": user_id},
    ).first()
    return row


def _query_bank_fallback(
    db: Session,
    *,
    user_id: str,
    skill_id: str,
) -> Optional[tuple]:
    """Last-resort: any unseen, active item of any difficulty."""
    return db.execute(
        text(
            """
            select i.id, i.difficulty, i.prompt, i.options
            from items i
            where i.skill_id = :sk
              and not i.archived
              and i.id not in (
                  select item_id from item_responses where
                    practice_session_id in (select id from practice_sessions where user_id = :u)
                    or session_id in (select id from diagnostic_sessions where user_id = :u)
              )
            order by random()
            limit 1
            """
        ),
        {"sk": skill_id, "u": user_id},
    ).first()


def _recent_topic_tags(db: Session, *, user_id: str, skill_id: str, limit: int = 8) -> list[str]:
    """Topics the user has seen recently — passed to the generator's avoid-list."""
    rows = db.execute(
        text(
            """
            select distinct i.topic_tag
            from item_responses r
            join items i on i.id = r.item_id
            where i.skill_id = :sk
              and i.topic_tag is not null
              and (
                  r.practice_session_id in (select id from practice_sessions where user_id = :u)
                  or r.session_id in (select id from diagnostic_sessions where user_id = :u)
              )
            order by 1
            limit :n
            """
        ),
        {"sk": skill_id, "u": user_id, "n": limit},
    ).all()
    return [r[0] for r in rows if r[0]]
