"""Pluggable per-service download providers."""
from .base import MEDIA_MIME, PlaylistNotSupported, Provider, UnsupportedURL
from .registry import (
    DEFAULT_PROVIDER,
    PROVIDERS,
    catalog,
    detect,
    get_provider,
    resolve,
)

__all__ = [
    "Provider",
    "MEDIA_MIME",
    "PlaylistNotSupported",
    "UnsupportedURL",
    "PROVIDERS",
    "DEFAULT_PROVIDER",
    "catalog",
    "detect",
    "get_provider",
    "resolve",
]
