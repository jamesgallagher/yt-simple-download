"""Central configuration, loaded once from environment variables.

Every secret and tunable lives here so nothing is hard-coded in the repo.
See .env.example for the full list and defaults.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip())
    except (ValueError, AttributeError):
        return default


def _redis_url() -> str:
    explicit = os.environ.get("REDIS_URL", "").strip()
    if explicit:
        return explicit
    password = os.environ.get("REDIS_PASSWORD", "").strip()
    host = os.environ.get("REDIS_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = _int("REDIS_PORT", 6379)
    auth = f":{password}@" if password else ""
    return f"redis://{auth}{host}:{port}/0"


@dataclass(frozen=True)
class Settings:
    # Auth: both must be set to enable basic auth. Blank/missing => disabled.
    app_user: str = os.environ.get("APP_USER", "").strip()
    app_password: str = os.environ.get("APP_PASSWORD", "").strip()

    # Worker pool size, clamped to a sane range.
    workers: int = max(1, min(5, _int("WORKERS", 1)))

    # yt-dlp self-update on container start.
    auto_update: bool = _bool("AUTO_UPDATE", True)

    # Ephemeral storage.
    tmp_dir: Path = Path(os.environ.get("TMP_DIR", "/downloads"))
    retention_hours: float = float(_int("RETENTION_HOURS", 6))

    # Optional cookies file (age-restricted / bot-check content).
    cookies_file: str = os.environ.get("YT_COOKIES", "").strip()

    # Directory holding per-provider cookie files, e.g. /config/cookies/x.txt.
    cookies_dir: str = os.environ.get("COOKIES_DIR", "/config/cookies").strip() or "/config/cookies"

    # Raw extra args passed through to yt-dlp (advanced / escape hatch).
    extra_ytdlp_args: str = os.environ.get("EXTRA_YTDLP_ARGS", "").strip()

    # Infra.
    redis_url: str = _redis_url()
    queue_name: str = os.environ.get("QUEUE_NAME", "downloads").strip() or "downloads"
    port: int = _int("PORT", 8080)

    # Per-job hard timeout (seconds) for a download.
    job_timeout: int = _int("JOB_TIMEOUT", 3600)

    @property
    def auth_enabled(self) -> bool:
        return bool(self.app_user and self.app_password)

    @property
    def retention_seconds(self) -> float:
        return self.retention_hours * 3600.0


settings = Settings()
