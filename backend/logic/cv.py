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


# =============================================================================
# CV-fit read — extract the CV text and let the LLM assess fit for the target
# competition. This is a one-time STRATEGY MODIFIER (Risk-2): it narrates fit +
# go/no-go and is stored on profiles.cv_fit_modifier; it never drives the measured
# numeric allocation.
# =============================================================================

CV_FIT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string",
                    "description": "2-3 sentence read of how this CV fits the target competition."},
        "specialist_fit": {"type": "string", "enum": ["strong", "moderate", "weak", "unclear"],
                           "description": "Fit for the field-related / specialist requirements of this competition."},
        "relevant_strengths": {"type": "array", "items": {"type": "string"},
                               "description": "1-3 CV facts that genuinely help for this competition."},
        "gaps": {"type": "array", "items": {"type": "string"},
                 "description": "1-3 gaps vs the competition's profile, if any."},
        "go_no_go": {"type": "string", "enum": ["on_track", "tight", "at_risk"],
                     "description": "Feasibility read for this competition given the CV."},
        "alternatives": {"type": "array", "items": {"type": "string"},
                         "description": "Other EPSO competitions that might fit better, if any."},
        "strategy_note": {"type": "string",
                          "description": "One actionable note on using this background in prep."},
    },
    "required": ["summary", "specialist_fit", "go_no_go", "strategy_note"],
}

_FIT_SYSTEM = (
    "You are an EPSO preparation coach. You are given a candidate's CV text and the "
    "competition they target (with the tests it uses). Assess fit honestly and "
    "concretely. Rules: base everything strictly on the CV text given; never invent "
    "experience; if the CV text is thin or unreadable, set specialist_fit='unclear' "
    "and say so; CV-fit is a strategy modifier, not a score; be brief and EPSO-specific."
)


def extract_text(filename: str, data: bytes) -> str:
    """Extract plain text from a CV. PDF via pypdf, DOCX via python-docx; legacy
    .doc / unknown fall back to a best-effort decode."""
    ext = _ext_of(filename)
    if ext == ".pdf":
        try:
            import io
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            return "\n".join((p.extract_text() or "") for p in reader.pages).strip()
        except Exception as e:
            raise CvError(f"pdf_parse_failed: {e}", status=502)
    if ext == ".docx":
        try:
            import io
            from docx import Document
            doc = Document(io.BytesIO(data))
            return "\n".join(p.text for p in doc.paragraphs).strip()
        except Exception as e:
            raise CvError(f"docx_parse_failed: {e}", status=502)
    return data.decode("utf-8", errors="ignore").strip()


def download_cv_bytes(storage_path: str) -> Optional[bytes]:
    """Fetch the stored CV from the private bucket (server-side, service_role)."""
    if not is_configured() or not storage_path:
        return None
    url = f"{_storage_base()}/{settings.supabase_cv_bucket}/{storage_path}"
    try:
        with httpx.Client(timeout=30) as client:
            r = client.get(url, headers=_storage_headers())
    except httpx.HTTPError:
        return None
    return r.content if r.status_code < 400 else None


def _fit_user_msg(cv_text: str, competition: dict) -> str:
    # Bound tokens: a CV rarely needs more than a few thousand chars for a fit read.
    from backend.logic import catalog as cat
    return (
        "Candidate CV (text):\n" + cv_text[:6000]
        + "\n\nTarget competition:\n"
        + json.dumps({
            "title": competition.get("title"),
            "grade": competition.get("grade"),
            "tests": cat.labels_for(competition.get("tests") or []),
        }, default=str)
        + "\n\nProduce the CV-fit read."
    )


def analyze_fit(db: Session, user_id: str) -> dict:
    """Extract the CV text, run the LLM fit read, cache it on profiles. Raises
    CvError for caller-fixable problems."""
    from backend.ai import client as ai
    from backend.logic import catalog as cat
    if not ai.is_configured():
        raise CvError("ai_not_configured", status=503)

    row = db.execute(
        text("select cv_storage_path, cv_filename, target_competition, "
             "target_competition_ref from profiles where user_id = :u"),
        {"u": user_id},
    ).mappings().first()
    if not row or not row["cv_storage_path"]:
        raise CvError("no_cv", status=400)

    data = download_cv_bytes(row["cv_storage_path"])
    if not data:
        raise CvError("cv_download_failed", status=502)
    cv_text = extract_text(row["cv_filename"] or "cv", data)
    if len(cv_text) < 50:
        raise CvError("cv_text_unreadable", status=422)

    competition = cat.resolve_for_profile(db, {
        "target_competition": row["target_competition"],
        "target_competition_ref": row["target_competition_ref"],
    })
    fit = ai.generate_json(
        schema=CV_FIT_SCHEMA, system=_FIT_SYSTEM,
        user=_fit_user_msg(cv_text, competition), tool_name="cv_fit", max_tokens=900,
    )
    db.execute(
        text("update profiles set cv_fit_modifier = cast(:f as jsonb), updated_at = now() "
             "where user_id = :u"),
        {"f": json.dumps(fit), "u": user_id},
    )
    db.execute(
        text("insert into events (user_id, kind, payload) values (:u, 'cv_fit_generated', :p)"),
        {"u": user_id, "p": json.dumps({"specialist_fit": fit.get("specialist_fit"),
                                        "go_no_go": fit.get("go_no_go")})},
    )
    db.commit()
    return fit


def cached_fit(db: Session, user_id: str) -> Optional[dict]:
    """The stored cv_fit_modifier, or None."""
    row = db.execute(
        text("select cv_fit_modifier from profiles where user_id = :u"),
        {"u": user_id},
    ).mappings().first()
    if not row or not row["cv_fit_modifier"]:
        return None
    fit = row["cv_fit_modifier"]
    if isinstance(fit, str):
        fit = json.loads(fit)
    return fit


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
        return {"has_cv": False, "configured": is_configured(), "cv_fit": None}
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
        "cv_fit": cached_fit(db, user_id),
        "configured": is_configured(),
    }
