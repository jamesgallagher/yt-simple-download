"""Facebook — public videos best-effort with curl_cffi impersonation; login
cookies (FB_COOKIES) for private/gated content."""
from __future__ import annotations

from .base import Provider


class Facebook(Provider):
    name = "facebook"
    display_name = "Facebook"
    domains = ("facebook.com", "fb.watch", "fb.me")  # www./m./web. matched via suffix
    placeholder = "https://www.facebook.com/watch/?v=..."

    video_qualities = {"best": None, "1080p": 1080, "720p": 720, "480p": 480, "360p": 360}
    audio_qualities = {"best": "320", "192": "192", "128": "128"}

    needs_impersonation = True
    cookie_envs = ("FB_COOKIES",)
    playlist_mode = "reject"
    auth_hint = "Some Facebook videos need login cookies (FB_COOKIES)."
