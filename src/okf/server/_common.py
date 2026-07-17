"""Shared server helpers."""

from __future__ import annotations

import re

SLUG_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
RESERVED_USERNAMES = frozenset({"api", "static", "health", "www", "default"})


def validate_slug(value: str) -> None:
    """Raise ValueError if value is not a valid OKF slug."""
    if not value or not SLUG_RE.match(value):
        raise ValueError(f"invalid slug: {value!r}")
