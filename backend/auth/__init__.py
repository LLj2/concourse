"""Auth via Supabase Auth (magic-link OTP) + signed session cookie.

Flow:
1. POST /api/auth/signup { email, utm } -> Supabase /auth/v1/otp sends magic link.
   We stash UTM in a short-lived signed cookie keyed to the email so we can
   read it on the callback (Supabase doesn't carry custom data through OTP).
2. User clicks link -> hits Supabase's redirect -> Supabase redirects to
   GET /auth/callback#access_token=... (URL fragment, client-side only).
   We serve a small HTML page that reads the fragment, POSTs the token to
   /api/auth/exchange, which verifies it server-side, upserts the user row
   with UTM, and sets the long-lived session cookie.
3. Subsequent requests carry the session cookie. get_current_user() decodes it.
"""
from __future__ import annotations

import json
import time
from typing import Optional
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, Cookie, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from pydantic import BaseModel, EmailStr
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.config import settings
from backend.db.database import get_db

router = APIRouter()

SESSION_COOKIE = "concourse_session"
UTM_COOKIE = "concourse_pending_utm"
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 days
UTM_MAX_AGE = 60 * 60  # 1 hour — must outlive the user clicking the magic link

_serializer = URLSafeTimedSerializer(settings.session_secret, salt="concourse-session")


# ---------- public helpers ----------

def make_session(user_id: str, email: str) -> str:
    return _serializer.dumps({"user_id": user_id, "email": email})


def read_session(token: str) -> Optional[dict]:
    try:
        return _serializer.loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def get_current_user(
    session: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict:
    if not session:
        raise HTTPException(status_code=401, detail="not_authenticated")
    payload = read_session(session)
    if not payload:
        raise HTTPException(status_code=401, detail="invalid_session")
    return payload


def get_optional_user(
    session: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE),
) -> Optional[dict]:
    if not session:
        return None
    return read_session(session)


# ---------- request models ----------

class SignupRequest(BaseModel):
    email: EmailStr
    utm: Optional[dict] = None


class ExchangeRequest(BaseModel):
    access_token: str


# ---------- routes ----------

@router.post("/api/auth/signup")
async def signup(req: SignupRequest, response: Response):
    """Send a magic link via Supabase Auth. Stash UTM in a signed cookie."""
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    redirect_to = f"{settings.public_base_url}/auth/callback"
    # GoTrue's REST API reads the post-auth redirect from the `redirect_to`
    # query param, NOT from a body field. (`options.email_redirect_to` is the
    # JS SDK shape and is silently ignored here, so links fell back to the
    # Supabase Site URL and landed on `/` instead of `/auth/callback`.)
    url = f"{settings.supabase_url}/auth/v1/otp?redirect_to={quote(redirect_to, safe='')}"

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            url,
            headers={
                "apikey": settings.supabase_anon_key,
                "Content-Type": "application/json",
            },
            json={
                "email": req.email,
                "create_user": True,
            },
        )
    if r.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"supabase_otp_failed: {r.text}")

    # Persist UTM to a short-lived cookie keyed to this signup
    if req.utm:
        utm_token = _serializer.dumps({"email": req.email, "utm": req.utm})
        response.set_cookie(
            key=UTM_COOKIE,
            value=utm_token,
            max_age=UTM_MAX_AGE,
            httponly=True,
            secure=settings.app_env == "production",
            samesite="lax",
        )
    return {"ok": True, "message": "check_email"}


@router.get("/auth/callback", response_class=HTMLResponse)
def callback_landing():
    """Magic link returns here with the access token in the URL fragment.
    Fragment is client-only; this page extracts it and POSTs to /api/auth/exchange.
    """
    return HTMLResponse(
        """<!doctype html><html><head><meta charset="utf-8"><title>Signing in…</title>
<style>body{font-family:-apple-system,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;background:#f7f9fc;color:#0f1d3a}
.card{background:#fff;padding:32px 28px;border-radius:10px;border:1px solid #e5e9f2;text-align:center}
.spinner{width:24px;height:24px;border:3px solid #e5e9f2;border-top-color:#1e63d6;border-radius:50%;animation:s 1s linear infinite;margin:0 auto 16px}
@keyframes s{to{transform:rotate(360deg)}}
.err{color:#c03;margin-top:12px;font-size:13px}
</style></head>
<body><div class="card"><div class="spinner"></div><div>Signing you in…</div><div id="err" class="err"></div></div>
<script>
(async function(){
  var hash = window.location.hash.replace(/^#/, '');
  var params = new URLSearchParams(hash);
  var token = params.get('access_token');
  if (!token) {
    document.getElementById('err').textContent = 'Missing access token. Try the link again.';
    return;
  }
  try {
    var r = await fetch('/api/auth/exchange', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({access_token: token})
    });
    if (!r.ok) throw new Error(await r.text());
    var data = await r.json();
    window.location.replace(data.next || '/intake');
  } catch (e) {
    document.getElementById('err').textContent = 'Sign-in failed: ' + e.message;
  }
})();
</script></body></html>"""
    )


@router.post("/api/auth/exchange")
async def exchange(
    req: ExchangeRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Verify the access token with Supabase, upsert user row, set session cookie."""
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    # Fetch the user from Supabase using the access token
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{settings.supabase_url}/auth/v1/user",
            headers={
                "apikey": settings.supabase_anon_key,
                "Authorization": f"Bearer {req.access_token}",
            },
        )
    if r.status_code >= 400:
        raise HTTPException(status_code=401, detail=f"token_invalid: {r.text}")
    user = r.json()
    sb_user_id = user.get("id")
    email = user.get("email")
    if not sb_user_id or not email:
        raise HTTPException(status_code=401, detail="user_missing_fields")

    # Read pending UTM (if any) from the short-lived cookie
    utm = {}
    pending = request.cookies.get(UTM_COOKIE)
    if pending:
        try:
            payload = _serializer.loads(pending, max_age=UTM_MAX_AGE)
            if payload.get("email") == email:
                utm = payload.get("utm") or {}
        except (BadSignature, SignatureExpired):
            pass

    # Upsert into our users table. Supabase's auth.users.id (UUID) is reused.
    db.execute(
        text(
            """
            insert into users (id, email, utm_source, utm_medium, utm_campaign, utm_content, utm_term)
            values (:id, :email, :s, :m, :c, :ct, :t)
            on conflict (id) do update set
                email = excluded.email,
                utm_source    = coalesce(users.utm_source,    excluded.utm_source),
                utm_medium    = coalesce(users.utm_medium,    excluded.utm_medium),
                utm_campaign  = coalesce(users.utm_campaign,  excluded.utm_campaign),
                utm_content   = coalesce(users.utm_content,   excluded.utm_content),
                utm_term      = coalesce(users.utm_term,      excluded.utm_term)
            """
        ),
        {
            "id": sb_user_id,
            "email": email,
            "s": utm.get("utm_source"),
            "m": utm.get("utm_medium"),
            "c": utm.get("utm_campaign"),
            "ct": utm.get("utm_content"),
            "t": utm.get("utm_term"),
        },
    )
    # Log the signup event (idempotent-ish; we accept duplicates here)
    db.execute(
        text("insert into events (user_id, kind, payload) values (:u, 'signup', :p)"),
        {"u": sb_user_id, "p": json.dumps({"utm": utm})},
    )
    db.commit()

    # Decide where to send the user — to intake if no profile, /me otherwise
    has_profile = db.execute(
        text("select 1 from profiles where user_id = :u"), {"u": sb_user_id}
    ).first()
    next_path = "/me" if has_profile else "/intake"

    # Set the long-lived session cookie + clear the UTM cookie
    response.set_cookie(
        key=SESSION_COOKIE,
        value=make_session(sb_user_id, email),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
    )
    response.delete_cookie(UTM_COOKIE)

    return JSONResponse({"ok": True, "next": next_path})


@router.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}
