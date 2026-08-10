"""FastAPI web layer: serve the page, enqueue jobs, report status, stream files.

The web process only ever writes to the queue and reads status/results; all the
heavy lifting happens in the worker.
"""
from __future__ import annotations

import asyncio
import secrets
import shutil
import time
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.requests import Request

from . import __version__
from .config import settings
from .jobs import download_job, parse_timecode
from .providers import DEFAULT_PROVIDER, PlaylistNotSupported, catalog, detect
from .queue import get_queue
from .store import get_status, set_status

BASE_DIR = Path(__file__).resolve().parent

# Changes every process start, so a new image never serves stale JS/CSS even if
# Cloudflare or the browser cached the previous build's assets.
ASSET_VER = str(int(time.time()))

app = FastAPI(title="yt-simple-download", version=__version__)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

_security = HTTPBasic(auto_error=False)


# ---------------------------------------------------------------- auth
def require_auth(credentials: HTTPBasicCredentials | None = Depends(_security)) -> None:
    if not settings.auth_enabled:
        return
    ok = credentials is not None and secrets.compare_digest(
        credentials.username, settings.app_user
    ) and secrets.compare_digest(credentials.password, settings.app_password)
    if not ok:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )


# ---------------------------------------------------------------- models
class ProbeRequest(BaseModel):
    url: str


class JobRequest(BaseModel):
    url: str
    provider: str | None = None  # selector hint; URL detection is authoritative
    format: str  # "mp3" | "mkv"
    quality: str = "best"
    start: str | None = None  # Advanced: trim start (SS / MM:SS / HH:MM:SS)
    end: str | None = None    # Advanced: trim end


# ---------------------------------------------------------------- routes
@app.get("/", response_class=HTMLResponse)
def index(request: Request, _: None = Depends(require_auth)):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "version": __version__,
            "asset_ver": ASSET_VER,
            "providers": catalog(),
            "default_provider": DEFAULT_PROVIDER,
        },
    )


@app.get("/healthz")
def healthz():
    return {"ok": True, "version": __version__}


@app.post("/api/probe")
def probe(req: ProbeRequest, _: None = Depends(require_auth)):
    url = req.url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Enter a valid http(s) URL.")

    provider = detect(url)
    if provider is None:
        raise HTTPException(status_code=400, detail="That link isn't from a supported service.")

    try:
        meta = provider.probe(url)
    except PlaylistNotSupported:
        raise HTTPException(status_code=400, detail="Playlists are not supported")
    except Exception:
        # If the service likely needs cookies and none are configured, say so.
        if provider.auth_hint and provider.cookie_file() is None:
            detail = provider.auth_hint
        else:
            detail = f"Could not read that {provider.display_name} link. Check it."
        raise HTTPException(status_code=400, detail=detail)

    meta["provider"] = provider.name
    meta["provider_display"] = provider.display_name
    return meta


@app.post("/api/jobs")
def create_job(req: JobRequest, _: None = Depends(require_auth)):
    url = req.url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Enter a valid http(s) URL.")

    provider = detect(url)
    if provider is None:
        raise HTTPException(status_code=400, detail="That link isn't from a supported service.")

    if req.format not in ("mp3", "mkv"):
        raise HTTPException(status_code=400, detail="Format must be mp3 or mkv.")

    allowed = provider.audio_qualities if req.format == "mp3" else provider.video_qualities
    quality = req.quality if req.quality in allowed else "best"

    # Advanced: optional trim window.
    try:
        start = parse_timecode(req.start)
        end = parse_timecode(req.end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if start is not None and end is not None and end <= start:
        raise HTTPException(status_code=400, detail="End time must be after start time.")

    job = get_queue().enqueue(
        download_job, url, provider.name, req.format, quality, start, end,
        job_timeout=settings.job_timeout,
        result_ttl=int(settings.retention_seconds),
        failure_ttl=int(settings.retention_seconds),
    )
    set_status(job.id, status="queued", stage="Queued", progress=0)
    return {"id": job.id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str, _: None = Depends(require_auth)):
    data = get_status(job_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Unknown or expired job.")
    return {
        "id": job_id,
        "status": data.get("status", "unknown"),
        "stage": data.get("stage", ""),
        "progress": int(data.get("progress", 0) or 0),
        "title": data.get("title", ""),
        "filename": data.get("filename", ""),
        "error": data.get("error", ""),
    }


@app.get("/api/jobs/{job_id}/file")
def job_file(job_id: str, _: None = Depends(require_auth)):
    data = get_status(job_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Unknown or expired job.")
    if data.get("status") != "ready":
        raise HTTPException(status_code=409, detail="File is not ready yet.")

    path = Path(data.get("path", ""))
    # Guard against path escaping the temp dir.
    try:
        path.relative_to(settings.tmp_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file path.")
    if not path.is_file():
        raise HTTPException(status_code=410, detail="File has been cleaned up.")

    return FileResponse(
        str(path),
        media_type=data.get("media", "application/octet-stream"),
        filename=data.get("filename", path.name),
    )


# ---------------------------------------------------------------- cleanup
async def _sweeper():
    """Delete job directories older than retention. Belt-and-braces alongside
    the purge-on-start; keeps a long-running container tidy."""
    while True:
        try:
            cutoff = time.time() - settings.retention_seconds
            root = settings.tmp_dir
            if root.is_dir():
                for child in root.iterdir():
                    try:
                        if child.is_dir() and child.stat().st_mtime < cutoff:
                            shutil.rmtree(child, ignore_errors=True)
                    except OSError:
                        pass
        except Exception as exc:  # sweeper must never die
            print(f"[ytsd] sweeper error: {exc}", flush=True)
        await asyncio.sleep(600)


@app.on_event("startup")
async def _on_startup():
    settings.tmp_dir.mkdir(parents=True, exist_ok=True)
    asyncio.create_task(_sweeper())
