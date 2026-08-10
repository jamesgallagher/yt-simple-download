"""TikTok — public videos work without login; impersonation defeats the
signature-based 403 blocks. Cookies (TIKTOK_COOKIES) help with region/age gates.
Note: photo/slideshow posts are images, not video, and may not download."""
from __future__ import annotations

from .base import Provider


class TikTok(Provider):
    name = "tiktok"
    display_name = "TikTok"
    domains = ("tiktok.com",)  # www./m./vm./vt. matched via suffix
    placeholder = "https://www.tiktok.com/@user/video/..."

    video_qualities = {"best": None, "1080p": 1080, "720p": 720}
    audio_qualities = {"best": "320", "192": "192", "128": "128"}

    needs_impersonation = True
    cookie_envs = ("TIKTOK_COOKIES",)
    playlist_mode = "reject"
    auth_hint = "Public TikToks work without login; cookies help region/age-gated."
