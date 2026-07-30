"""Shared value-level privacy guards for operator-visible projections."""

from __future__ import annotations

import re
import unicodedata

_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_PHONE = re.compile(r"(?<!\w)(?:\+?\d[\s().-]*){7,15}(?!\w)")
_SECRET = re.compile(r"(?i)(?:bearer\s+\S+|sk-[A-Za-z0-9_-]{8,}|password\s*[:=]|api[_ -]?key\s*[:=])")
_PRIVATE_PATH = re.compile(r"(?i)(?:^|\s|['\"])(?:/Volumes/|/Users/|/private/|~/)")
_CUSTOMER_MARKER = re.compile(r"(?i)\b(?:telegram|tenant(?:_?id)?|profile|cv\s+text|search\s+query|return\s+route)\b")
_SENSITIVE_KEY_MARKERS = (
    "authorization",
    "credential",
    "secret",
    "token",
    "password",
    "email",
    "phone",
    "telegram",
    "chat",
    "userid",
    "user",
    "tenant",
    "profile",
    "cv",
    "query",
    "route",
    "path",
)


def normalized_key(value: str) -> str:
    """Collapse Unicode compatibility and format-character key bypasses."""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def sensitive_key(value: str) -> bool:
    normalized = normalized_key(value)
    return any(marker in normalized for marker in _SENSITIVE_KEY_MARKERS)


def unsafe_operator_value(value: str) -> bool:
    """Return true when free text is customer-, secret-, or private-path-shaped."""

    normalized = unicodedata.normalize("NFKC", value)
    lowered = normalized.casefold()
    return bool(
        _EMAIL.search(normalized)
        or _PHONE.search(normalized)
        or _SECRET.search(normalized)
        or _PRIVATE_PATH.search(normalized)
        or _CUSTOMER_MARKER.search(normalized)
        or (lowered.startswith(("http://", "https://")) and "?" in normalized)
    )
