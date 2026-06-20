"""Adaptive diagnostic engine.

Picks items one at a time from `items` table, adapting difficulty by recent answers.
- Starts at difficulty 2 (or wherever the user's last score lives, if known).
- +1 difficulty on correct, -1 on incorrect, clamped to [1, 3].
- Never repeats an item within a session.
- Stops after `target_items` (default 5) or when item bank is exhausted.

Scoring: difficulty-weighted percent. A correct answer at d=3 is worth 3, at d=1 is worth 1.
Score = 100 * sum(weight * correct) / sum(weight). Range 0-100.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


TARGET_ITEMS = 5
MIN_DIFFICULTY = 1
MAX_DIFFICULTY = 3


@dataclass
class NextItem:
    item_id: str
    difficulty: int
    prompt: str
    options: list


def start_session(db: Session, user_id: str, skill_id: str, kind: str = "periodic") -> str:
    """Create a new diagnostic_sessions row, return its id."""
    if kind not in ("intake", "periodic"):
        raise ValueError(f"invalid kind: {kind}")
    row = db.execute(
        text(
            """
            insert into diagnostic_sessions (user_id, skill_id, kind)
            values (:u, :s, :k)
            returning id
            """
        ),
        {"u": user_id, "s": skill_id, "k": kind},
    ).first()
    db.commit()
    return str(row[0])


def _difficulty_for_next(db: Session, session_id: str, default: int = 2) -> int:
    """Look at the last response in the session; +1 if correct, -1 if not.
    No responses yet -> start at default.
    """
    last = db.execute(
        text(
            """
            select i.difficulty, r.is_correct
            from item_responses r
            join items i on i.id = r.item_id
            where r.session_id = :s
            order by r.answered_at desc
            limit 1
            """
        ),
        {"s": session_id},
    ).first()
    if last is None:
        return default
    diff, correct = last
    target = diff + (1 if correct else -1)
    return max(MIN_DIFFICULTY, min(MAX_DIFFICULTY, target))


def pick_next_item(db: Session, session_id: str) -> Optional[NextItem]:
    """Return the next adaptive item, or None if the session should end."""
    sess = db.execute(
        text("select user_id, skill_id, items_answered from diagnostic_sessions where id = :s"),
        {"s": session_id},
    ).first()
    if sess is None:
        return None
    _user_id, skill_id, items_answered = sess
    if items_answered >= TARGET_ITEMS:
        return None

    target_diff = _difficulty_for_next(db, session_id)

    # Find an unseen item at the target difficulty. If none, fall back to the
    # closest available difficulty.
    item = db.execute(
        text(
            """
            select i.id, i.difficulty, i.prompt, i.options
            from items i
            where i.skill_id = :sk
              and not i.archived
              and i.id not in (
                  select item_id from item_responses where session_id = :s
              )
            order by abs(i.difficulty - :d) asc, random()
            limit 1
            """
        ),
        {"sk": skill_id, "s": session_id, "d": target_diff},
    ).first()
    if item is None:
        return None
    return NextItem(
        item_id=str(item[0]),
        difficulty=int(item[1]),
        prompt=item[2],
        options=item[3] or [],
    )


def record_answer(
    db: Session,
    session_id: str,
    item_id: str,
    selected_index: int,
    time_taken_ms: Optional[int],
) -> dict:
    """Persist the response, bump items_answered, return correctness + explanation."""
    item = db.execute(
        text("select correct_index, explanation from items where id = :i"),
        {"i": item_id},
    ).first()
    if item is None:
        raise ValueError(f"item not found: {item_id}")
    correct_index, explanation = item
    is_correct = selected_index == correct_index

    db.execute(
        text(
            """
            insert into item_responses (session_id, item_id, selected_index, is_correct, time_taken_ms)
            values (:s, :i, :sel, :c, :t)
            """
        ),
        {"s": session_id, "i": item_id, "sel": selected_index, "c": is_correct, "t": time_taken_ms},
    )
    db.execute(
        text(
            """
            update diagnostic_sessions set items_answered = items_answered + 1 where id = :s
            """
        ),
        {"s": session_id},
    )
    # Update item-level calibration counts (best-effort)
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
    db.commit()
    return {
        "is_correct": is_correct,
        "correct_index": correct_index,
        "explanation": explanation,
    }


def finalize_session(db: Session, session_id: str) -> dict:
    """Compute the difficulty-weighted score, mark session complete.
    Returns {score, items_answered, median_time_ms}.
    """
    rows = db.execute(
        text(
            """
            select i.difficulty, r.is_correct, r.time_taken_ms
            from item_responses r
            join items i on i.id = r.item_id
            where r.session_id = :s
            """
        ),
        {"s": session_id},
    ).all()
    if not rows:
        # No answers logged — mark complete with score 0
        db.execute(
            text(
                """
                update diagnostic_sessions
                set completed_at = now(), score = 0, median_time_ms = null
                where id = :s
                """
            ),
            {"s": session_id},
        )
        db.commit()
        return {"score": 0.0, "items_answered": 0, "median_time_ms": None}

    weighted_sum = sum(r[0] for r in rows)
    weighted_correct = sum(r[0] for r in rows if r[1])
    score = 100.0 * weighted_correct / weighted_sum if weighted_sum else 0.0

    times = sorted([r[2] for r in rows if r[2] is not None])
    median = times[len(times) // 2] if times else None

    db.execute(
        text(
            """
            update diagnostic_sessions
            set completed_at = now(), score = :sc, median_time_ms = :m
            where id = :s
            """
        ),
        {"sc": round(score, 1), "m": median, "s": session_id},
    )
    # Log an event so replan triggers can read this later
    sess = db.execute(
        text("select user_id, skill_id from diagnostic_sessions where id = :s"),
        {"s": session_id},
    ).first()
    if sess is not None:
        import json
        db.execute(
            text(
                "insert into events (user_id, kind, payload) values (:u, 'diagnostic_completed', :p)"
            ),
            {
                "u": sess[0],
                "p": json.dumps({"session_id": session_id, "skill_id": sess[1], "score": round(score, 1)}),
            },
        )
    db.commit()
    return {
        "score": round(score, 1),
        "items_answered": len(rows),
        "median_time_ms": median,
    }
