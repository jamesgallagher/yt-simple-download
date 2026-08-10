"""YouTube — the standard pipeline. Behaviour is intentionally identical to the
original implementation (anonymous, full quality ladder, id-based thumbnail)."""
from __future__ import annotations

from .base import Provider


class YouTube(Provider):
    name = "youtube"
    display_name = "YouTube"
    domains = ("youtube.com", "youtu.be", "youtube-nocookie.com")
    placeholder = "https://www.youtube.com/watch?v=..."

    video_qualities = {
        "best": None, "2160p": 2160, "1440p": 1440, "1080p": 1080,
        "720p": 720, "480p": 480, "360p": 360,
    }
    audio_qualities = {"best": "320", "320": "320", "192": "192", "128": "128"}

    needs_impersonation = False
    cookie_envs = ("YT_COOKIES",)
    playlist_mode = "reject"
    auth_hint = ""

    def thumbnail(self, info: dict) -> str:
        t = super().thumbnail(info)
        if t:
            return t
        vid = info.get("id")
        return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else ""
