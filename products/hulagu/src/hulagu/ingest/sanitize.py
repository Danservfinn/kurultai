"""Deterministic Unicode sanitization and draft-profile projection."""

from __future__ import annotations

import json
import unicodedata

from ..domain.profile import Profile, ProfileField
from .parser import ParsedCv


def sanitize_text(value: str, *, max_length: int) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    cleaned = "".join(" " if unicodedata.category(character) in {"Cc", "Cf"} else character for character in normalized)
    bounded = " ".join(cleaned.split())
    return bounded[:max_length]


def draft_profile(parsed: ParsedCv) -> Profile:
    fields: list[ProfileField] = []
    for field in parsed.fields:
        if isinstance(field.value, str):
            value = sanitize_text(field.value, max_length=4_000)
        elif isinstance(field.value, list):
            sanitized = [sanitize_text(item, max_length=1_000) if isinstance(item, str) else item for item in field.value]
            value = json.dumps(sanitized, ensure_ascii=False, separators=(",", ":"))
        else:
            value = json.dumps(field.value, ensure_ascii=False, separators=(",", ":"))
        fields.append(
            ProfileField(
                field_id=sanitize_text(field.field_id, max_length=128),
                value=value,
                source="cv",
                confidence=field.confidence,
                source_span=None if field.source_span is None else sanitize_text(field.source_span, max_length=256),
            )
        )
    return Profile(version=1, fields=tuple(fields))
