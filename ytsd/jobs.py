"""The worker job: run yt-dlp for one URL and report progress to Redis.

Enqueued by the web app, executed by an RQ worker. The RQ job id is the public
id the browser polls. All state goes through store.set_status.
"""
from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from rq import get_current_job
from yt_dlp import YoutubeDL

from .config import settings
from .naming import pascal_filename
from .store import set_status

# Quality label -> max height (None = best available).
VIDEO_QUALITIES = {
    "best": None,
    "2160p": 2160,
    "1440p": 1440,
    "1080p": 1080,
    "720p": 720,
    "480p": 480,
    "360p": 360,
}

# Quality label -> mp3 bitrate (kbps). "best" == 320.
AUDIO_QUALITIES = {"best": "320", "320": "320", "192": "192", "128": "128"}

MEDIA_MIME = {"mp3": "audio/mpeg", "mkv": "video/x-matroska"}

# Base YouTube domains we accept (subdomains like m./music. are matched too).
_YOUTUBE_DOMAINS = ("youtube.com", "youtu.be", "youtube-nocookie.com")


class PlaylistNotSupported(Exception):
    pass


class NotYouTubeURL(Exception):
    pass


def is_youtube_url(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower().split("@")[-1].split(":")[0]
    except Exception:
        return False
    return any(host == d or host.endswith("." + d) for d in _YOUTUBE_DOMAINS)


def probe_metadata(url: str) -> dict:
    """Validate a URL is a single YouTube video and return light metadata.

    Used by the web UI to preview the video and unlock the download button.
    Raises NotYouTubeURL / PlaylistNotSupported / RuntimeError on failure.
    """
    if not is_youtube_url(url):
        raise NotYouTubeURL("Enter a YouTube video link.")

    opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True}
    if settings.cookies_file and os.path.exists(settings.cookies_file):
        opts["cookiefile"] = settings.cookies_file

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if info is None:
        raise RuntimeError("Could not read that video.")
    if info.get("_type") == "playlist" or info.get("entries") is not None:
        raise PlaylistNotSupported()

    vid = info.get("id") or ""
    title = info.get("title") or "Untitled"
    thumb = info.get("thumbnail") or (
        f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else ""
    )
    return {
        "id": vid,
        "title": title,
        "thumbnail": thumb,
        "duration": info.get("duration"),
        "uploader": info.get("uploader") or info.get("channel") or "",
    }


def _extra_opts(extra: str) -> dict:
    """Parse EXTRA_YTDLP_ARGS into ydl_opts, keeping only user-overridden keys.

    Best-effort: any failure returns {} so a bad extra-arg string never breaks
    downloads. Our own critical opts are layered on top of these afterwards.
    """
    if not extra.strip():
        return {}
    try:
        from yt_dlp import parse_options

        def ydl_opts_of(argv):
            parsed = parse_options(argv)
            return getattr(parsed, "ydl_opts", None) or parsed[-1]

        base = ydl_opts_of([])
        user = ydl_opts_of(shlex.split(extra))
        return {k: v for k, v in user.items() if base.get(k) != v}
    except Exception as exc:  # never fatal
        print(f"[ytsd] ignoring EXTRA_YTDLP_ARGS ({exc})", flush=True)
        return {}


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


def _build_opts(
    media_format: str,
    quality: str,
    outdir: Path,
    base: str,
    hook,
    start: Optional[float] = None,
    end: Optional[float] = None,
) -> dict:
    opts: dict = {
        "outtmpl": str(outdir / (base + ".%(ext)s")),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "progress_hooks": [hook],
        "overwrites": True,
        "retries": 5,
        "fragment_retries": 5,
        "concurrent_fragment_downloads": 4,
    }
    if settings.cookies_file and os.path.exists(settings.cookies_file):
        opts["cookiefile"] = settings.cookies_file

    # Trim to a time window (Advanced options). ffmpeg re-cuts at keyframes for
    # accurate boundaries.
    if start is not None or end is not None:
        from yt_dlp.utils import download_range_func

        s = start if start is not None else 0.0
        e = end if end is not None else float("inf")
        opts["download_ranges"] = download_range_func(None, [(s, e)])
        opts["force_keyframes_at_cuts"] = True

    if media_format == "mp3":
        opts["format"] = "ba/b"
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": AUDIO_QUALITIES.get(quality, "320"),
        }]
    else:  # mkv (video)
        height = VIDEO_QUALITIES.get(quality)
        if height:
            opts["format"] = (
                f"bv*[height<={height}]+ba/"
                f"b[height<={height}]/"
                f"bv*+ba/b"
            )
        else:
            opts["format"] = "bv*+ba/b"
        opts["merge_output_format"] = "mkv"

    extra = _extra_opts(settings.extra_ytdlp_args)
    if extra:
        # Our computed keys win over the escape hatch to keep the mp3/mkv contract.
        return {**extra, **opts}
    return opts


def _find_output(outdir: Path, ext: str) -> Optional[Path]:
    matches = sorted(outdir.glob(f"*{ext}"), key=lambda p: p.stat().st_mtime, reverse=True)
    if matches:
        return matches[0]
    files = [p for p in outdir.iterdir() if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def download_job(
    url: str,
    media_format: str,
    quality: str,
    start: Optional[float] = None,
    end: Optional[float] = None,
) -> dict:
    job = get_current_job()
    job_id = job.id if job else "local"

    try:
        set_status(job_id, status="probing", stage="Fetching video info", progress=0)

        probe_opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True}
        if settings.cookies_file and os.path.exists(settings.cookies_file):
            probe_opts["cookiefile"] = settings.cookies_file

        with YoutubeDL(probe_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if info is None:
            raise RuntimeError("Could not read that URL.")
        if info.get("_type") == "playlist" or info.get("entries") is not None:
            raise PlaylistNotSupported()

        title = info.get("title") or info.get("id") or "download"
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

        opts = _build_opts(media_format, quality, outdir, base, hook, start=start, end=end)
        with YoutubeDL(opts) as ydl:
            ydl.download([url])

        ext = ".mp3" if media_format == "mp3" else ".mkv"
        final = _find_output(outdir, ext)
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
    except Exception as exc:
        msg = str(exc).strip() or exc.__class__.__name__
        set_status(job_id, status="error", stage="Error", error=msg[:400])
        raise
