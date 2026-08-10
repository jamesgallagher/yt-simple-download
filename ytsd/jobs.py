"""The worker job: resolve a provider, run its pipeline, report progress.

Enqueued by the web app, executed by an RQ worker. The RQ job id is the public
id the browser polls. All state goes through store.set_status. The actual
download work lives in the per-service provider pipelines (ytsd/providers).
"""
from __future__ import annotations

from typing import Optional

from rq import get_current_job

from .config import settings
from .naming import pascal_filename
from .providers import (
    MEDIA_MIME,
    PlaylistNotSupported,
    UnsupportedURL,
    resolve,
)
from .store import set_status


def parse_timecode(value: Optional[str]) -> Optional[float]:
    """Parse a timecode into seconds. Accepts SS, MM:SS, HH:MM:SS (decimals ok).

    Returns None for blank input; raises ValueError for anything unparseable.
    """
    if value is None:
        return None
    s = value.strip()
    if not s:
        return None
    try:
        parts = [float(p) for p in s.split(":")]
    except ValueError:
        raise ValueError(f"Invalid time: {value!r}")
    if len(parts) == 1:
        seconds = parts[0]
    elif len(parts) == 2:
        seconds = parts[0] * 60 + parts[1]
    elif len(parts) == 3:
        seconds = parts[0] * 3600 + parts[1] * 60 + parts[2]
    else:
        raise ValueError(f"Invalid time: {value!r}")
    if seconds < 0:
        raise ValueError("Time cannot be negative.")
    return float(seconds)


def download_job(
    url: str,
    provider_name: str,
    media_format: str,
    quality: str,
    start: Optional[float] = None,
    end: Optional[float] = None,
) -> dict:
    job = get_current_job()
    job_id = job.id if job else "local"

    try:
        provider = resolve(provider_name, url)
        if provider is None:
            raise UnsupportedURL("That link isn't from a supported service.")

        set_status(job_id, status="probing", stage="Fetching info",
                   progress=0, provider=provider.display_name)

        meta = provider.probe(url)
        title = meta.get("title") or "video"
        base = pascal_filename(title)

        outdir = settings.tmp_dir / job_id
        outdir.mkdir(parents=True, exist_ok=True)

        last = {"pct": -1}

        def hook(d):
            status = d.get("status")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                done = d.get("downloaded_bytes") or 0
                pct = int(done * 100 / total) if total else 0
                if pct != last["pct"]:
                    last["pct"] = pct
                    set_status(job_id, status="downloading", stage="Downloading", progress=pct)
            elif status == "finished":
                set_status(job_id, status="processing", stage="Converting", progress=100)

        set_status(job_id, status="downloading", stage="Downloading",
                   progress=0, title=title)

        final = provider.download(url, media_format, quality, outdir, base, hook, start, end)
        if final is None:
            raise RuntimeError("Download finished but no output file was produced.")

        set_status(job_id, status="ready", stage="Ready", progress=100,
                   title=title, filename=final.name, path=str(final),
                   media=MEDIA_MIME.get(media_format, "application/octet-stream"))
        return {"filename": final.name, "path": str(final)}

    except PlaylistNotSupported:
        set_status(job_id, status="error", stage="Error",
                   error="Playlists are not supported")
        raise
    except UnsupportedURL as exc:
        set_status(job_id, status="error", stage="Error", error=str(exc))
        raise
    except Exception as exc:
        msg = str(exc).strip() or exc.__class__.__name__
        set_status(job_id, status="error", stage="Error", error=msg[:400])
        raise
