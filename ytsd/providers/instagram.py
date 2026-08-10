"""Instagram — the strict one. Since 2023 almost all content is behind a login
wall, so IG_COOKIES is effectively required. Impersonation + a gentle request
pace reduce rate-limit/action-block risk. Carousels resolve to the first item."""
from __future__ import annotations

from .base import Provider


class Instagram(Provider):
    name = "instagram"
    display_name = "Instagram"
    domains = ("instagram.com", "instagr.am", "ig.me")
    placeholder = "https://www.instagram.com/reel/..."

    video_qualities = {"best": None, "1080p": 1080, "720p": 720}
    audio_qualities = {"best": "320", "192": "192", "128": "128"}

    needs_impersonation = True
    cookie_envs = ("IG_COOKIES", "INSTAGRAM_COOKIES")
    playlist_mode = "first"  # carousel posts -> first media
    # Be gentle: aggressive fetching with account cookies triggers action-blocks.
    extra_opts = {"sleep_interval_requests": 1}
    auth_hint = "Instagram usually requires login cookies — set IG_COOKIES."
