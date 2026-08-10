"""Provider registry — the ordered list, name lookup, and URL detection."""
from __future__ import annotations

from typing import Optional

from .base import Provider
from .facebook import Facebook
from .instagram import Instagram
from .reddit import Reddit
from .tiktok import TikTok
from .twitter import X
from .youtube import YouTube

# Order controls the service selector; YouTube first (the default).
PROVIDERS = [YouTube(), Facebook(), Reddit(), X(), Instagram(), TikTok()]
DEFAULT_PROVIDER = "youtube"

_BY_NAME = {p.name: p for p in PROVIDERS}


def get_provider(name: str) -> Optional[Provider]:
    return _BY_NAME.get(name or "")


def detect(url: str) -> Optional[Provider]:
    """Return the provider whose domains match this URL, or None."""
    for provider in PROVIDERS:
        if provider.matches(url):
            return provider
    return None


def resolve(name: str, url: str) -> Optional[Provider]:
    """URL detection is authoritative; fall back to the named selection."""
    return detect(url) or get_provider(name)


def catalog() -> list:
    return [p.summary() for p in PROVIDERS]
