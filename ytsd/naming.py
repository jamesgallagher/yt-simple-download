"""Turn a video title into a filesystem-safe PascalCase name.

Rule (from the spec):
    "James Gallagher - Best Video Highlights"  ->  "JamesGallagher-BestVideoHighlights"

- Unicode is folded to ASCII.
- Illegal / punctuation characters are dropped.
- Each whitespace-separated word is PascalCased (first letter upper, rest kept).
- Hyphens are preserved as segment joiners (" - " collapses to "-").
- Result is truncated to a safe length; empty results fall back to a default.
"""
from __future__ import annotations

import re
import unicodedata

_MAX_LEN = 150
_ALLOWED = re.compile(r"[^A-Za-z0-9\- ]+")
_MULTI_HYPHEN = re.compile(r"-{2,}")


def pascal_filename(title: str, fallback: str = "download") -> str:
    if not title:
        return fallback

    # Fold accents/unicode down to plain ASCII.
    norm = unicodedata.normalize("NFKD", title)
    ascii_only = norm.encode("ascii", "ignore").decode("ascii")

    # Drop anything that isn't a letter, digit, hyphen, or space.
    cleaned = _ALLOWED.sub(" ", ascii_only)

    # Split into hyphen-separated segments; PascalCase the words in each.
    segments = []
    for segment in cleaned.split("-"):
        words = segment.split()
        if not words:
            continue
        pascal = "".join(w[:1].upper() + w[1:] for w in words)
        if pascal:
            segments.append(pascal)

    name = "-".join(segments)
    name = _MULTI_HYPHEN.sub("-", name).strip("-")

    if not name:
        return fallback
    return name[:_MAX_LEN].strip("-") or fallback


if __name__ == "__main__":  # quick self-check
    cases = {
        "James Gallagher - Best Video Highlights": "JamesGallagher-BestVideoHighlights",
        "  spider-man  no way home ": "Spider-ManNoWayHome",
        "café déjà vu!!!": "CafeDejaVu",
        "🔥 EPIC / clip [4K] 🔥": "EPICClip4K",
        "": "download",
        "///": "download",
    }
    for src, expected in cases.items():
        got = pascal_filename(src)
        flag = "OK " if got == expected else "XX "
        print(f"{flag}{src!r} -> {got!r} (expected {expected!r})")
