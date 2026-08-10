"""Reddit — yt-dlp merges v.redd.it DASH video+audio natively (needs ffmpeg,
which the image has). Public works anonymously; NSFW/private need cookies."""
from __future__ import annotations

from .base import Provider


class Reddit(Provider):
    name = "reddit"
    display_name = "Reddit"
    domains = ("reddit.com", "redd.it")  # www./old./new. and v.redd.it via suffix
    placeholder = "https://www.reddit.com/r/.../comments/..."

    video_qualities = {"best": None, "1080p": 1080, "720p": 720, "480p": 480}
    audio_qualities = {"best": "320", "192": "192", "128": "128"}

    needs_impersonation = False
    cookie_envs = ("REDDIT_COOKIES",)
    playlist_mode = "reject"
    auth_hint = "NSFW or private subreddits may need login cookies (REDDIT_COOKIES)."
