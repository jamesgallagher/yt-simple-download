"""X (Twitter) — impersonation for anti-scraping; login cookies (X_COOKIES) for
sensitive/age-gated posts. A post with multiple clips resolves to the first."""
from __future__ import annotations

from .base import Provider


class X(Provider):
    name = "x"
    display_name = "X"
    domains = ("x.com", "twitter.com")  # mobile.* matched via suffix
    placeholder = "https://x.com/user/status/..."

    video_qualities = {"best": None, "1080p": 1080, "720p": 720, "480p": 480}
    audio_qualities = {"best": "320", "192": "192", "128": "128"}

    needs_impersonation = True
    cookie_envs = ("X_COOKIES", "TWITTER_COOKIES")
    playlist_mode = "first"  # a tweet can carry several videos -> take the first
    auth_hint = "X needs login cookies for sensitive/age-restricted posts (X_COOKIES)."
