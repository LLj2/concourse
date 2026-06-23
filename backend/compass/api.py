"""Compass FastAPI router — every Compass-served URL lives here.

Mounted from main.py with one line:
    from backend.compass.api import router as compass_router
    app.include_router(compass_router)

Removing Compass = remove that one line + `rm -rf backend/compass/` + revert
migration 003. The legacy /api/diagnostic/* and /api/me etc. keep working.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.compass import practice
from backend.db.database import get_db

router = APIRouter()

STATIC_DIR = Path(__file__).parent / "static"


# =============================================================================
# Page
# =============================================================================

@router.get("/compass")
def compass_page(user: dict = Depends(get_current_user)):
    """The practice UI page. Single page; skill+length picker on it."""
    return FileResponse(STATIC_DIR / "compass.html")


# =============================================================================
# Practice API
# =============================================================================

@router.post("/api/compass/practice/start")
def practice_start(
    payload: dict = Body(...),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Begin a practice session. Body: {skill_id, target_length, plan_id?}"""
    skill_id = payload.get("skill_id")
    if skill_id != "verbal":
        raise HTTPException(status_code=400, detail="compass v1 supports skill_id='verbal' only")
    target_length = int(payload.get("target_length", 20))
    plan_id = payload.get("plan_id")

    session_id = practice.start_practice_session(
        db,
        user_id=user["user_id"],
        skill_id=skill_id,
        target_length=target_length,
        plan_id=plan_id,
    )
    nxt = practice.pick_practice_item(db, session_id)
    if nxt is None:
        # Empty bank AND generator failed — surface as 409
        raise HTTPException(
            status_code=409,
            detail="no items available and generation unavailable",
        )

    return {
        "session_id": session_id,
        "item": {
            "item_id": nxt.item_id,
            "difficulty": nxt.difficulty,
            "prompt": nxt.prompt,
            "options": nxt.options,
            "source": nxt.source,  # 'bank' | 'generated' (mostly internal; UI can ignore)
        },
        "progress": {"answered": 0, "target": target_length},
    }


@router.post("/api/compass/practice/answer")
def practice_answer(
    payload: dict = Body(...),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit an answer. Body: {session_id, item_id, selected_index, time_taken_ms?}"""
    session_id = payload.get("session_id")
    item_id = payload.get("item_id")
    selected_index = payload.get("selected_index")
    time_taken_ms = payload.get("time_taken_ms")
    if not session_id or not item_id or selected_index is None:
        raise HTTPException(status_code=400, detail="missing_fields")

    # Cross-user protection: confirm the session belongs to this user
    sess = db.execute(
        text("select user_id, target_length, items_attempted from practice_sessions where id = :s"),
        {"s": session_id},
    ).first()
    if sess is None or str(sess[0]) != user["user_id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    target_length, items_attempted = sess[1], sess[2]

    feedback = practice.record_practice_answer(
        db,
        session_id=session_id,
        item_id=item_id,
        selected_index=int(selected_index),
        time_taken_ms=time_taken_ms,
    )

    # Decide whether to serve a next item or finalize
    items_attempted_now = items_attempted + 1
    if items_attempted_now >= target_length:
        final = practice.finalize_practice_session(db, session_id)
        return {"feedback": feedback, "done": True, "final": final}

    nxt = practice.pick_practice_item(db, session_id)
    if nxt is None:
        # Bank empty + gen failed mid-session — finalize early
        final = practice.finalize_practice_session(db, session_id)
        return {"feedback": feedback, "done": True, "final": final, "early_end": True}

    return {
        "feedback": feedback,
        "done": False,
        "next_item": {
            "item_id": nxt.item_id,
            "difficulty": nxt.difficulty,
            "prompt": nxt.prompt,
            "options": nxt.options,
            "source": nxt.source,
        },
        "progress": {"answered": items_attempted_now, "target": target_length},
    }


@router.post("/api/compass/practice/end")
def practice_end(
    payload: dict = Body(...),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Manual quit — finalize early. Body: {session_id}"""
    session_id = payload.get("session_id")
    sess = db.execute(
        text("select user_id from practice_sessions where id = :s"),
        {"s": session_id},
    ).first()
    if sess is None or str(sess[0]) != user["user_id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    final = practice.finalize_practice_session(db, session_id)
    return {"ok": True, "final": final}


@router.get("/api/compass/practice/recent")
def practice_recent(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Last 5 completed sessions — for the /me panel."""
    rows = db.execute(
        text(
            """
            select id, skill_id, started_at, completed_at,
                   items_attempted, items_correct, target_length
            from practice_sessions
            where user_id = :u and completed_at is not null
            order by completed_at desc
            limit 5
            """
        ),
        {"u": user["user_id"]},
    ).mappings().all()
    return {"sessions": [dict(r) for r in rows]}


# =============================================================================
# Insight panel (read of latest pattern_analyses)
# =============================================================================

@router.get("/api/compass/insight")
def compass_insight(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Latest pattern analysis for the user (any skill, most-recent wins).

    Returns 404 with a structured body when no analysis exists yet (the /me
    page hides the panel on 404). The pattern-analysis worker lands in commit 5;
    until then this always returns 404, which is the correct degradation.
    """
    row = db.execute(
        text(
            """
            select skill_id, insight_md, focus_dimensions, generated_at
            from pattern_analyses
            where user_id = :u
            order by generated_at desc
            limit 1
            """
        ),
        {"u": user["user_id"]},
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="no_insight_yet")
    return dict(row)


# =============================================================================
# Item-flag (user reports a bad question)
# =============================================================================

@router.post("/api/compass/items/{item_id}/flag")
def flag_item(
    item_id: str,
    payload: dict = Body(default={}),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Soft-archive the item so the picker never serves it again."""
    reason = (payload or {}).get("reason", "user_reported")
    res = db.execute(
        text("update items set archived = true where id = :i and not archived"),
        {"i": item_id},
    )
    db.execute(
        text("insert into events (user_id, kind, payload) values (:u, 'item_flagged', :p)"),
        {"u": user["user_id"], "p": '{"item_id":"' + item_id + '","reason":"' + reason + '"}'},
    )
    db.commit()
    return {"ok": True, "archived_now": (res.rowcount or 0) > 0}
