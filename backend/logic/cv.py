"""CV upload + profile links (foundation flow, 2026-06-25 planning call).

The candidate's CV (mandatory for specialist competitions, optional otherwise)
plus optional LinkedIn / portfolio / other links feed the gap analysis and the
master plan. CV-fit stays a one-time STRATEGY MODIFIER, never a daily allocation
driver (Risk-2 fix, see ROADMAP §8) — this module only stores the artefacts;
the LLM CV-fit read (writing profiles.cv_fit_modifier) is a separate step.

Storage: the file goes to a PRIVATE Supabase Storage bucket via the Storage REST
API using the service_role key (server-side only). We persist a pointer
(profiles.cv_storage_path) plus metadata; the file itself never transits our DB.
Reads use short-lived signed URLs so the bucket can stay private.
"""
from __future__ import annotations

import json
import re
from typing import Optional

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.config import settings

# Accepted CV formats. Keep tight — these are what EPSO candidates actually send.
ALLOWED_EXT = {".pdf": "application/pdf",
               ".doc": "application/msword",
               ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
MAX_BYTES = 10 * 1024 * 1024  # 10 MB — generous for a CV, blocks abuse.

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


class CvError(Exception):
    """Raised for caller-fixable problems (bad type, too big, storage refusal).
    The route maps this to a 4xx/502 rather than a 500."""
    def __init__(self, code: str, status: int = 400):
        super().__init__(code)
        self.code = code
        self.status = status


def is_configured() -> bool:
    """True when server-side Storage uploads are possible."""
    return bool(settings.supabase_url and settings.supabase_service_role_key)


def _ext_of(filename: str) -> str:
    i = filename.rfind(".")
    return filename[i:].lower() if i != -1 else ""


def _storage_base() -> str:
    return f"{settings.supabase_url}/storage/v1/object"


def _storage_headers(content_type: Optional[str] = None) -> dict:
    h = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }
    if content_type:
        h["Content-Type"] = content_type
    return h


def _clean_url(value: Optional[str]) -> Optional[str]:
    """Normalise an optional link field: trim, empty -> None, require http(s)."""
    if not value:
        return None
    v = value.strip()
    if not v:
        return None
    if not _URL_RE.match(v):
        v = "https://" + v  # forgive a pasted "linkedin.com/in/…"
    return v


def save_cv(db: Session, user_id: str, filename: str, data: bytes) -> dict:
    """Validate + upload the CV to Storage, then persist the pointer on profiles.

    Returns {storage_path, filename}. Raises CvError on a bad file or storage
    failure. Upserts profiles so this works before intake is completed.
    """
    if not is_configured():
        raise CvError("cv_storage_not_configured", status=503)

    ext = _ext_of(filename)
    if ext not in ALLOWED_EXT:
        raise CvError("unsupported_file_type")
    if not data:
        raise CvError("empty_file")
    if len(data) > MAX_BYTES:
        raise CvError("file_too_large", status=413)

    # Deterministic path per user so a re-upload overwrites the previous CV
    # (x-upsert) instead of leaving orphans. One CV per candidate.
    storage_path = f"{user_id}/cv{ext}"
    url = f"{_storage_base()}/{settings.supabase_cv_bucket}/{storage_path}"

    try:
        with httpx.Client(timeout=30) as client:
            r = client.post(
                url,
                headers={**_storage_headers(ALLOWED_EXT[ext]), "x-upsert": "true"},
                content=data,
            )
    except httpx.HTTPError as e:
        raise CvError(f"storage_unreachable: {e}", status=502)
    if r.status_code >= 400:
        raise CvError(f"storage_rejected: {r.status_code} {r.text}", status=502)

    db.execute(
        text(
            """
            insert into profiles (user_id, cv_storage_path, cv_filename, cv_uploaded_at)
            values (:u, :p, :f, now())
            on conflict (user_id) do update set
                cv_storage_path = excluded.cv_storage_path,
                cv_filename     = excluded.cv_filename,
                cv_uploaded_at  = excluded.cv_uploaded_at,
                updated_at      = now()
            """
        ),
        {"u": user_id, "p": storage_path, "f": filename},
    )
    db.execute(
        text("insert into events (user_id, kind, payload) values (:u, 'cv_uploaded', :p)"),
        {"u": user_id, "p": json.dumps({"filename": filename, "bytes": len(data)})},
    )
    db.commit()
    return {"storage_path": storage_path, "filename": filename}


def save_links(
    db: Session,
    user_id: str,
    linkedin_url: Optional[str] = None,
    portfolio_url: Optional[str] = None,
    other_links: Optional[list] = None,
) -> dict:
    """Persist the optional profile links. Upserts profiles. Returns the cleaned set."""
    linkedin = _clean_url(linkedin_url)
    portfolio = _clean_url(portfolio_url)
    others = [u for u in (_clean_url(x) for x in (other_links or [])) if u]

    db.execute(
        text(
            """
            insert into profiles (user_id, linkedin_url, portfolio_url, other_links)
            values (:u, :li, :pf, cast(:ot as jsonb))
            on conflict (user_id) do update set
                linkedin_url  = excluded.linkedin_url,
                portfolio_url = excluded.portfolio_url,
                other_links   = excluded.other_links,
                updated_at    = now()
            """
        ),
        {"u": user_id, "li": linkedin, "pf": portfolio, "ot": json.dumps(others)},
    )
    db.commit()
    return {"linkedin_url": linkedin, "portfolio_url": portfolio, "other_links": others}


def signed_url(storage_path: str, expires_in: int = 3600) -> Optional[str]:
    """Mint a short-lived download URL for a private-bucket object, or None."""
    if not is_configured() or not storage_path:
        return None
    url = f"{settings.supabase_url}/storage/v1/object/sign/{settings.supabase_cv_bucket}/{storage_path}"
    try:
        with httpx.Client(timeout=15) as client:
            r = client.post(url, headers=_storage_headers("application/json"),
                            json={"expiresIn": expires_in})
        if r.status_code >= 400:
            return None
        signed = r.json().get("signedURL")
        return f"{settings.supabase_url}/storage/v1{signed}" if signed else None
    except httpx.HTTPError:
        return None


def get_status(db: Session, user_id: str) -> dict:
    """Current CV + links for the dashboard / flow gating. No LLM, cheap to poll."""
    row = db.execute(
        text(
            """
            select cv_storage_path, cv_filename, cv_uploaded_at,
                   linkedin_url, portfolio_url, other_links
            from profiles where user_id = :u
            """
        ),
        {"u": user_id},
    ).mappings().first()
    if not row:
        return {"has_cv": False, "configured": is_configured()}
    other = row["other_links"]
    if isinstance(other, str):
        other = json.loads(other)
    return {
        "has_cv": bool(row["cv_storage_path"]),
        "filename": row["cv_filename"],
        "uploaded_at": row["cv_uploaded_at"].isoformat() if row["cv_uploaded_at"] else None,
        "download_url": signed_url(row["cv_storage_path"]) if row["cv_storage_path"] else None,
        "linkedin_url": row["linkedin_url"],
        "portfolio_url": row["portfolio_url"],
        "other_links": other or [],
        "configured": is_configured(),
    }
