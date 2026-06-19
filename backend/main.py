from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.config import settings

app = FastAPI(title="Concourse", version="0.1.0")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "concourse",
        "env": settings.app_env,
        "db_configured": bool(settings.database_url),
    }


@app.get("/")
def root():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/config.js")
def public_config():
    """Expose only the public-safe config to the frontend."""
    body = (
        "window.__CONCOURSE__ = {"
        f"  posthogKey: '{settings.posthog_public_key}',"
        f"  posthogHost: '{settings.posthog_host}',"
        f"  appEnv: '{settings.app_env}'"
        "};"
    )
    return Response(content=body, media_type="application/javascript")
