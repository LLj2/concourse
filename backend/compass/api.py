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

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.compass import patterns as compass_patterns
from backend.compass import practice
from backend.compass import validation as compass_validation
from backend.config import settings
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

@router.post("/api/compass/patterns/refresh")
def compass_patterns_refresh(
    payload: dict = Body(default={}),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Manually trigger a pattern analysis for this user.

    Body: {"skill_id": "verbal", "force": false}.
    Honors should_refresh() unless force=true. Returns the saved analysis dict
    or {"skipped": true, "reason": "..."} on a soft skip.
    """
    skill_id = (payload or {}).get("skill_id", "verbal")
    force = bool((payload or {}).get("force"))
    if not force:
        ok, reason = compass_patterns.should_refresh(db, user_id=user["user_id"], skill_id=skill_id)
        if not ok:
            return {"skipped": True, "reason": reason}
    result = compass_patterns.run_pattern_analysis(
        db, user_id=user["user_id"], skill_id=skill_id, force=True
    )
    if result is None:
        return {"skipped": True, "reason": "llm_failure_see_logs"}
    return {"ok": True, "analysis": result}


@router.get("/api/compass/insight")
def compass_insight(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Latest pattern analysis for the user (any skill, most-recent wins).

    Returns 404 with a structured body when no analysis exists yet (the /me
    page hides the panel on 404).
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


# =============================================================================
# Admin: dimension-health dashboard
# =============================================================================
#
# Gated by ?pin=<ADMIN_PIN>. Same dev-PIN pattern as dora's practitioner panel —
# good enough for an internal tool with no real users yet. Bring back proper auth
# (cookie + session table) before going live with users.

def _check_admin_pin(pin: Optional[str]) -> None:
    if not pin or pin != settings.admin_pin:
        raise HTTPException(status_code=401, detail="admin_pin_required_or_invalid")


@router.get("/admin/compass/health", response_class=HTMLResponse)
def compass_health_dashboard(
    pin: Optional[str] = Query(default=None),
    skill: str = Query(default="verbal"),
    db: Session = Depends(get_db),
):
    """Server-rendered HTML page with discrimination + predictivity + emergent
    rows. Read-only; uses ?pin=<ADMIN_PIN> for access."""
    _check_admin_pin(pin)

    disc = compass_validation.discrimination_check(db, skill)
    pred = compass_validation.predictivity_check(db, skill)
    emrg = compass_validation.emergent_patterns(db, skill)

    # Build the discrimination table
    if disc["rows"]:
        disc_html = ['<table><thead><tr><th>Dimension</th><th>Value</th>'
                     '<th>Top quartile %</th><th>Bottom quartile %</th>'
                     '<th>Gap (pp)</th><th>Total attempts</th></tr></thead><tbody>']
        for r in disc["rows"]:
            gap_str = f"{r.gap_pct_points:+.1f}" if r.gap_pct_points is not None else "—"
            disc_html.append(
                f"<tr><td>{r.dimension_name}</td><td>{r.dimension_value}</td>"
                f"<td>{r.top_quartile_accuracy_pct or '—'}</td>"
                f"<td>{r.bottom_quartile_accuracy_pct or '—'}</td>"
                f"<td><b>{gap_str}</b></td>"
                f"<td>{r.n_attempts_total}</td></tr>"
            )
        disc_html.append("</tbody></table>")
        disc_table = "".join(disc_html)
    else:
        disc_table = (
            f'<p style="color:#888"><em>Insufficient data — need ≥{disc["min_users_threshold"]} '
            f'users with mastery data; currently {disc["n_users"]}.</em></p>'
        )

    pred_block = (
        f'<p style="color:#888"><em>Status: {pred["status"]}. '
        f'Users with re-calibration data: {pred["n_users_with_recalibration"]} '
        f'(need ≥{pred["min_users_threshold"]}).</em></p>'
    )

    emrg_block = (
        f'<p style="color:#888"><em>Status: {emrg["status"]}. '
        f'Practice users on this skill: {emrg["n_practice_users"]} '
        f'(need ≥{emrg["min_users_threshold"]} for the monthly LLM pass).</em></p>'
    )

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Compass — dimension health ({skill})</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 1100px; margin: 30px auto; padding: 0 24px; color: #0f1d3a; }}
h1 {{ font-size: 22px; }}
h2 {{ font-size: 16px; color: #1e63d6; margin-top: 28px; border-bottom: 1px solid #e5e9f2; padding-bottom: 6px; }}
.note {{ background: #fff8e1; padding: 10px 14px; border-left: 3px solid #d99c12; border-radius: 4px; font-size: 13px; margin-bottom: 18px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
th, td {{ border: 1px solid #e5e9f2; padding: 6px 10px; text-align: left; }}
th {{ background: #f0f4fb; }}
tr:nth-child(even) td {{ background: #fafbfc; }}
.skill-picker {{ font-size: 14px; }}
.skill-picker a {{ margin-right: 12px; color: #1e63d6; text-decoration: none; }}
.skill-picker a.current {{ font-weight: 700; color: #0f1d3a; }}
</style></head><body>
<h1>Compass — dimension health</h1>
<div class="skill-picker">
  Skill:
  <a href="?pin={pin}&skill=verbal" class="{'current' if skill == 'verbal' else ''}">verbal</a>
  <a href="?pin={pin}&skill=numerical" class="{'current' if skill == 'numerical' else ''}">numerical</a>
  <a href="?pin={pin}&skill=abstract" class="{'current' if skill == 'abstract' else ''}">abstract</a>
  <a href="?pin={pin}&skill=eu_knowledge" class="{'current' if skill == 'eu_knowledge' else ''}">eu_knowledge</a>
</div>
<div class="note"><b>How to read this.</b> Discrimination = does the dimension separate strong from weak users?
Predictivity = does mastery now correlate with future score? Emergent = LLM pass for patterns not in the v1 schema.
Big gaps mean the dimension is doing real work; small gaps mean it's a candidate for removal.</div>

<h2>1. Discrimination — top vs bottom quartile</h2>
<p style="font-size:13px;color:#555">Users with mastery data: <b>{disc['n_users']}</b>
(threshold: {disc['min_users_threshold']}).</p>
{disc_table}

<h2>2. Predictivity — mastery now → future score</h2>
{pred_block}

<h2>3. Emergent patterns — LLM pass for what we missed</h2>
{emrg_block}
</body></html>"""
    return HTMLResponse(content=html)
