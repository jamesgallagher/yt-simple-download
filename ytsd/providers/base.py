"""Abstract provider framework.

Each supported service is its own Provider subclass with its own pipeline. The
base carries the shared, YouTube-proven machinery (format ladder, mp3/mkv
contract, trim sections, the EXTRA_YTDLP_ARGS escape hatch) so subclasses only
declare what makes them different: domains, quality ceilings, auth/cookies,
impersonation, playlist policy, and thumbnails.

Subclasses may override any method (probe / build_opts / download) when a
service genuinely needs bespoke handling; most only need to set attributes.
"""
from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from yt_dlp import YoutubeDL

from ..config import settings

MEDIA_MIME = {"mp3": "audio/mpeg", "mkv": "video/x-matroska"}


class PlaylistNotSupported(Exception):
    pass


class UnsupportedURL(Exception):
    pass


def _host(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().split("@")[-1].split(":")[0]
    except Exception:
        return ""


_UNSET = object()
_IMPERSONATE = _UNSET


def _impersonate_target():
    """Return an actually-available Chrome ImpersonateTarget, or None.

    Asks yt-dlp which impersonate targets its request handlers can really serve
    (depends on a compatible curl_cffi). Picks a Chrome target if present, else
    any available one. Returns None when none are available, so providers fall
    back to plain requests instead of yt-dlp hard-failing on a bad target.
    Cached after first call; never raises.
    """
    global _IMPERSONATE
    if _IMPERSONATE is not _UNSET:
        return _IMPERSONATE
    target = None
    try:
        from yt_dlp import YoutubeDL
        with YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            available = ydl._get_available_impersonate_targets() or []
        targets = [item[0] if isinstance(item, tuple) else item for item in available]
        target = next((t for t in targets if getattr(t, "client", "") == "chrome"), None)
        if target is None and targets:
            target = targets[0]
    except Exception:
        target = None
    _IMPERSONATE = target
    return _IMPERSONATE


def _extra_opts(extra: str) -> dict:
    """Parse EXTRA_YTDLP_ARGS into ydl_opts, keeping only overridden keys."""
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


def find_output(outdir: Path, ext: str) -> Optional[Path]:
    matches = sorted(outdir.glob(f"*{ext}"), key=lambda p: p.stat().st_mtime, reverse=True)
    if matches:
        return matches[0]
    files = [p for p in outdir.iterdir() if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


class Provider:
    # --- identity ---
    name: str = ""
    display_name: str = ""
    domains: tuple = ()
    placeholder: str = "https://..."

    # --- quality tiers (label -> max height / mp3 bitrate) ---
    video_qualities: dict = {"best": None, "1080p": 1080, "720p": 720, "480p": 480}
    audio_qualities: dict = {"best": "320", "192": "192", "128": "128"}

    # --- behaviour knobs ---
    needs_impersonation: bool = False
    cookie_envs: tuple = ()               # env var(s) holding a cookies.txt path
    playlist_mode: str = "reject"          # "reject" | "first"
    extra_opts: dict = {}                  # static ydl opts merged in (non-critical)
    auth_hint: str = ""                    # shown when cookies are likely required

    # ---------------------------------------------------------------- matching
    def matches(self, url: str) -> bool:
        host = _host(url)
        return any(host == d or host.endswith("." + d) for d in self.domains)

    # ---------------------------------------------------------------- cookies
    def cookie_file(self) -> Optional[str]:
        for env in self.cookie_envs:
            val = os.environ.get(env, "").strip()
            if val and os.path.exists(val):
                return val
        candidate = os.path.join(settings.cookies_dir, f"{self.name}.txt")
        return candidate if os.path.exists(candidate) else None

    # ---------------------------------------------------------------- thumbnail
    def thumbnail(self, info: dict) -> str:
        t = info.get("thumbnail")
        if t:
            return t
        thumbs = info.get("thumbnails") or []
        return thumbs[-1].get("url", "") if thumbs else ""

    # ---------------------------------------------------------------- shared opts
    def _auth_opts(self) -> dict:
        opts: dict = {}
        cf = self.cookie_file()
        if cf:
            opts["cookiefile"] = cf
        if self.needs_impersonation:
            target = _impersonate_target()
            if target is not None:
                opts["impersonate"] = target
        return opts

    def _playlist_opts(self) -> dict:
        if self.playlist_mode == "first":
            return {"playlist_items": "1"}
        return {"noplaylist": True}

    # ---------------------------------------------------------------- probe
    def probe(self, url: str) -> dict:
        opts = {"quiet": True, "no_warnings": True, "skip_download": True}
        opts.update(self._playlist_opts())
        opts.update(self._auth_opts())
        opts.update(self.extra_opts)

        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if info is None:
            raise RuntimeError("Could not read that link.")
        if info.get("_type") == "playlist" or info.get("entries") is not None:
            if self.playlist_mode == "reject":
                raise PlaylistNotSupported()
            entries = [e for e in (info.get("entries") or []) if e]
            if not entries:
                raise RuntimeError("No video found at that link.")
            info = entries[0]

        vid = info.get("id") or ""
        title = info.get("title") or info.get("description") or vid or "video"
        return {
            "id": vid,
            "title": str(title)[:300],
            "thumbnail": self.thumbnail(info),
            "duration": info.get("duration"),
            "uploader": info.get("uploader") or info.get("channel")
            or info.get("uploader_id") or "",
        }

    # ---------------------------------------------------------------- build opts
    def build_opts(self, media_format, quality, outdir: Path, base: str, hook,
                   start=None, end=None) -> dict:
        opts: dict = {
            "outtmpl": str(outdir / (base + ".%(ext)s")),
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "progress_hooks": [hook],
            "overwrites": True,
            "retries": 5,
            "fragment_retries": 5,
            "concurrent_fragment_downloads": 4,
        }
        opts.update(self._playlist_opts())
        opts.update(self._auth_opts())
        opts.update(self.extra_opts)

        if media_format == "mp3":
            opts["format"] = "ba/b"
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": self.audio_qualities.get(quality, "320"),
            }]
        else:  # mkv
            height = self.video_qualities.get(quality)
            if height:
                opts["format"] = (
                    f"bv*[height<={height}]+ba/b[height<={height}]/bv*+ba/b"
                )
            else:
                opts["format"] = "bv*+ba/b"
            opts["merge_output_format"] = "mkv"

        if start is not None or end is not None:
            from yt_dlp.utils import download_range_func
            s = start if start is not None else 0.0
            e = end if end is not None else float("inf")
            opts["download_ranges"] = download_range_func(None, [(s, e)])
            opts["force_keyframes_at_cuts"] = True

        extra = _extra_opts(settings.extra_ytdlp_args)
        if extra:
            # Our computed keys win to keep the mp3/mkv + section contract.
            opts = {**extra, **opts}
        return opts

    # ---------------------------------------------------------------- download
    def download(self, url, media_format, quality, outdir: Path, base: str, hook,
                 start=None, end=None) -> Optional[Path]:
        opts = self.build_opts(media_format, quality, outdir, base, hook, start, end)
        with YoutubeDL(opts) as ydl:
            ydl.download([url])
        ext = ".mp3" if media_format == "mp3" else ".mkv"
        return find_output(outdir, ext)

    # ---------------------------------------------------------------- ui summary
    def summary(self) -> dict:
        return {
            "name": self.name,
            "display": self.display_name,
            "placeholder": self.placeholder,
            "video": list(self.video_qualities.keys()),
            "audio": list(self.audio_qualities.keys()),
            "auth_hint": self.auth_hint,
            "cookies_configured": self.cookie_file() is not None,
        }
