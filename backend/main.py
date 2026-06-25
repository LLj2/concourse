import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Body, UploadFile, File, Form
from fastapi.responses import FileResponse, RedirectResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.config import settings
from backend.auth import router as auth_router, get_current_user, get_optional_user
from backend.db.database import get_db
from backend.logic import diagnostic as dx
from backend.logic import scoring as sc
from backend.logic import planning as pl
from backend.logic import adherence as ad
from backend.logic import cv as cv
from backend.logic import catalog as cat
from backend.ai import client as ai

app = FastAPI(title="Concourse", version="0.1.0")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(auth_router)


# ---------- public pages ----------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "concourse",
        "env": settings.app_env,
        "db_configured": bool(settings.database_url),
        "supabase_configured": bool(settings.supabase_url and settings.supabase_anon_key),
    }


@app.get("/")
def root(user: Optional[dict] = Depends(get_optional_user)):
    if user:
        return RedirectResponse(url="/me", status_code=302)
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/config.js")
def public_config():
    body = (
        "window.__CONCOURSE__ = {"
        f"  posthogKey: '{settings.posthog_public_key}',"
        f"  posthogHost: '{settings.posthog_host}',"
        f"  appEnv: '{settings.app_env}'"
        "};"
    )
    return Response(content=body, media_type="application/javascript")


# ---------- authenticated pages ----------

@app.get("/intake")
def intake_page(user: dict = Depends(get_current_user)):
    return FileResponse(STATIC_DIR / "intake.html")


@app.get("/me")
def me_page(user: dict = Depends(get_current_user)):
    return FileResponse(STATIC_DIR / "me.html")


@app.get("/diagnostic")
def diagnostic_page(user: dict = Depends(get_current_user)):
    return FileResponse(STATIC_DIR / "diagnostic.html")


@app.get("/profile")
def profile_page(user: dict = Depends(get_current_user)):
    return FileResponse(STATIC_DIR / "profile.html")


@app.get("/plan")
def plan_page(user: dict = Depends(get_current_user)):
    return FileResponse(STATIC_DIR / "plan.html")


@app.get("/cv")
def cv_page(user: dict = Depends(get_current_user)):
    return FileResponse(STATIC_DIR / "cv.html")


# ---------- intake API ----------

@app.post("/api/intake")
def submit_intake(
    payload: dict = Body(...),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Persist the intake form into profiles. Idempotent (upsert)."""
    required = ["target_competition", "weeks_to_exam", "weekly_hours"]
    missing = [k for k in required if payload.get(k) in (None, "", [])]
    if missing:
        raise HTTPException(status_code=400, detail=f"missing_fields: {missing}")

    db.execute(
        text(
            """
            insert into profiles (
                user_id, target_competition, weeks_to_exam, weekly_hours,
                energy_pattern, has_prior_epso_experience, last_epso_test_at,
                self_habits_score, self_strategy_score, self_eu_breadth_score
            ) values (
                :u, :tc, :wte, :wh,
                cast(:ep as jsonb), :prior, :last,
                :h, :s, :eu
            )
            on conflict (user_id) do update set
                target_competition = excluded.target_competition,
                weeks_to_exam = excluded.weeks_to_exam,
                weekly_hours = excluded.weekly_hours,
                energy_pattern = excluded.energy_pattern,
                has_prior_epso_experience = excluded.has_prior_epso_experience,
                last_epso_test_at = excluded.last_epso_test_at,
                self_habits_score = excluded.self_habits_score,
                self_strategy_score = excluded.self_strategy_score,
                self_eu_breadth_score = excluded.self_eu_breadth_score,
                updated_at = now()
            """
        ),
        {
            "u": user["user_id"],
            "tc": payload.get("target_competition"),
            "wte": payload.get("weeks_to_exam"),
            "wh": payload.get("weekly_hours"),
            "ep": json.dumps(payload.get("energy_pattern") or {}),
            "prior": payload.get("has_prior_epso_experience"),
            "last": payload.get("last_epso_test_at") or None,
            "h": payload.get("self_habits_score"),
            "s": payload.get("self_strategy_score"),
            "eu": payload.get("self_eu_breadth_score"),
        },
    )
    db.execute(
        text("insert into events (user_id, kind, payload) values (:u, 'intake_completed', :p)"),
        {"u": user["user_id"], "p": json.dumps({"weeks_to_exam": payload.get("weeks_to_exam")})},
    )
    db.commit()
    return {"ok": True}


# ---------- CV + profile links API (foundation flow) ----------

@app.get("/api/cv")
def get_cv(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Current CV + links for this user (with a short-lived download URL)."""
    return cv.get_status(db, user["user_id"])


@app.post("/api/cv")
def post_cv(
    file: Optional[UploadFile] = File(default=None),
    linkedin_url: Optional[str] = Form(default=None),
    portfolio_url: Optional[str] = Form(default=None),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload a CV and/or save profile links. Both parts are optional so the
    user can add links now and the CV later — but at least one must be present."""
    if file is None and not (linkedin_url or portfolio_url):
        raise HTTPException(status_code=400, detail="nothing_to_save")

    result: dict = {}
    if file is not None:
        try:
            data = file.file.read()
            result["cv"] = cv.save_cv(db, user["user_id"], file.filename or "cv", data)
        except cv.CvError as e:
            raise HTTPException(status_code=e.status, detail=e.code)
        finally:
            file.file.close()

    result["links"] = cv.save_links(db, user["user_id"], linkedin_url, portfolio_url)
    return {"ok": True, **result}


@app.get("/api/me")
def get_me(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.execute(
        text(
            """
            select
                u.id, u.email, u.created_at, u.utm_source, u.utm_medium, u.utm_campaign,
                p.target_competition, p.weeks_to_exam, p.weekly_hours,
                p.energy_pattern,
                p.has_prior_epso_experience, p.last_epso_test_at,
                p.self_habits_score, p.self_strategy_score, p.self_eu_breadth_score
            from users u
            left join profiles p on p.user_id = u.id
            where u.id = :u
            """
        ),
        {"u": user["user_id"]},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="user_not_found")

    # Latest completed diagnostic score per skill, for the dashboard
    scores = db.execute(
        text(
            """
            select distinct on (skill_id)
                skill_id, score, completed_at
            from diagnostic_sessions
            where user_id = :u and completed_at is not null
            order by skill_id, completed_at desc
            """
        ),
        {"u": user["user_id"]},
    ).mappings().all()

    payload = dict(row)
    payload["latest_scores"] = [dict(s) for s in scores]
    # Return a plain dict so FastAPI's jsonable_encoder handles UUID/datetime/Decimal.
    return payload


# ---------- diagnostic API ----------

@app.post("/api/diagnostic/start")
def diagnostic_start(
    payload: dict = Body(...),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Begin a diagnostic session. Body: {skill_id, kind?}"""
    skill_id = payload.get("skill_id")
    if skill_id not in ("verbal", "numerical", "abstract", "eu_knowledge"):
        raise HTTPException(status_code=400, detail="invalid_skill_id")
    kind = payload.get("kind") or "periodic"
    session_id = dx.start_session(db, user["user_id"], skill_id, kind)
    item = dx.pick_next_item(db, session_id)
    if item is None:
        # no items in bank for this skill yet
        raise HTTPException(status_code=409, detail="no_items_available")
    return {
        "session_id": session_id,
        "item": {
            "item_id": item.item_id,
            "difficulty": item.difficulty,
            "prompt": item.prompt,
            "options": item.options,
        },
        "progress": {"answered": 0, "target": dx.TARGET_ITEMS},
    }


@app.post("/api/diagnostic/answer")
def diagnostic_answer(
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

    # Confirm session belongs to this user (prevent cross-user writes)
    sess = db.execute(
        text("select user_id from diagnostic_sessions where id = :s"),
        {"s": session_id},
    ).first()
    if sess is None or str(sess[0]) != user["user_id"]:
        raise HTTPException(status_code=403, detail="forbidden")

    result = dx.record_answer(db, session_id, item_id, int(selected_index), time_taken_ms)

    next_item = dx.pick_next_item(db, session_id)
    if next_item is None:
        final = dx.finalize_session(db, session_id)
        return {
            "feedback": result,
            "done": True,
            "final": final,
        }
    return {
        "feedback": result,
        "done": False,
        "next_item": {
            "item_id": next_item.item_id,
            "difficulty": next_item.difficulty,
            "prompt": next_item.prompt,
            "options": next_item.options,
        },
    }


# ---------- profile / scoring API (Session 4) ----------

@app.get("/api/profile")
def get_profile(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Computed profile (measured + self-rated + constraints) plus any cached
    LLM narrative. No LLM call here — cheap, safe to poll."""
    profile = sc.build_profile(db, user["user_id"])
    cached = sc.latest_narrative(db, user["user_id"])
    return {
        "profile": profile,
        "narrative": cached["narrative"] if cached else None,
        "narrative_generated_at": cached["generated_at"] if cached else None,
        "ai_configured": ai.is_configured(),
    }


@app.post("/api/profile/narrate")
def narrate_profile(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate (and cache) a JSON-schema-validated LLM narrative of the profile."""
    if not ai.is_configured():
        raise HTTPException(status_code=503, detail="ai_not_configured")
    profile = sc.build_profile(db, user["user_id"])
    if not profile["constraints"].get("target_competition"):
        raise HTTPException(status_code=400, detail="intake_incomplete")
    try:
        narrative = sc.generate_narrative(db, user["user_id"], profile)
    except Exception as e:  # transport / model error -> clean 502, not a 500 crash
        raise HTTPException(status_code=502, detail=f"ai_failed: {e}")
    return {"narrative": narrative}


# ---------- competition catalog API (foundation flow) ----------

@app.get("/api/competitions")
def get_competitions(
    status: Optional[str] = None,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Catalog of EPSO competitions (from the scraper). Empty list if the catalog
    table isn't loaded yet — callers degrade gracefully."""
    return {"competitions": cat.list_competitions(db, status=status)}


# ---------- plan API (Sessions 6-7) ----------

@app.get("/api/plan")
def get_plan(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Active master plan (or null if none yet) + event-driven replan signal."""
    return {
        "master": pl.active_master_plan(db, user["user_id"]),
        "replan": ad.replan_signal(db, user["user_id"]),
    }


@app.post("/api/plan/generate")
def post_plan_generate(
    payload: dict = Body(default={}),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """(Re)generate the master plan. Rule-based allocation; LLM rationale is
    best-effort. Requires a completed intake."""
    profile = sc.build_profile(db, user["user_id"])
    if not profile["constraints"].get("target_competition"):
        raise HTTPException(status_code=400, detail="intake_incomplete")
    trigger = payload.get("trigger_kind", "manual")
    return pl.generate_master_plan(db, user["user_id"], trigger_kind=trigger)


@app.post("/api/plan/daily")
def post_plan_daily(
    payload: dict = Body(default={}),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Today's session from the active master allocation."""
    minutes = payload.get("minutes")
    energy = payload.get("energy", "medium")
    if minutes is not None:
        try:
            minutes = int(minutes)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="invalid_minutes")
    return pl.generate_daily_plan(db, user["user_id"], minutes_available=minutes, energy=energy)


# ---------- adherence API (Session 8 — logging layer C) ----------

@app.get("/api/adherence")
def get_adherence(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Today's adherence + a 7-day summary."""
    return {
        "today": ad.today_status(db, user["user_id"]),
        "week": ad.week_summary(db, user["user_id"]),
    }


@app.post("/api/adherence")
def post_adherence(
    payload: dict = Body(...),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """One-tap daily confirmation. Body: {status, minutes?, note?, plan_id?}"""
    status = payload.get("status")
    if status not in ad.VALID_STATUS:
        raise HTTPException(status_code=400, detail="invalid_status")
    minutes = payload.get("minutes")
    if minutes is not None:
        try:
            minutes = int(minutes)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="invalid_minutes")
    today = ad.log_adherence(
        db, user["user_id"], status,
        minutes_actual=minutes, note=payload.get("note"), plan_id=payload.get("plan_id"),
    )
    # Surface whether this changes the replan picture (e.g. weekly floor breached).
    return {"today": today, "replan": ad.replan_signal(db, user["user_id"])}
