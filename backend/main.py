import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Body
from fastapi.responses import FileResponse, RedirectResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.config import settings
from backend.auth import router as auth_router, get_current_user, get_optional_user
from backend.db.database import get_db

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
    return JSONResponse(content=dict(row), media_type="application/json")
