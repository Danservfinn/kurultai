"""Hulagu source-contract package."""

from __future__ import annotations

import json
import re
import runpy
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from jsonschema import Draft202012Validator, FormatChecker

_SCHEMA_NAMES = frozenset(
    {
        "action-token-v1",
        "backup-manifest-v1",
        "candidate-bundle-v1",
        "deletion-tombstone-v1",
        "durable-event-v1",
        "health-report-v1",
        "parsed-cv-v1",
        "provider-response-v1",
        "receipt-v1",
        "search-plan-v1",
        "telegram-update-v1",
        "wiki-manifest-v1",
    }
)
_RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")


def declared_schema_names() -> tuple[str, ...]:
    """Return the closed, versioned schema inventory."""
    return tuple(sorted(_SCHEMA_NAMES))


def load_schema(name: str) -> dict[str, Any]:
    """Load a declared schema; arbitrary filenames are never accepted."""
    if name not in _SCHEMA_NAMES:
        raise ValueError(f"undeclared schema: {name}")
    schema_path = Path(__file__).parents[2] / "schemas" / f"{name}.schema.json"
    return json.loads(schema_path.read_text(encoding="utf-8"))


def _format_checker() -> FormatChecker:
    """Return deterministic format checks without optional ambient dependencies."""
    checker = FormatChecker()

    @checker.checks("uuid", raises=(ValueError, AttributeError))
    def valid_uuid(value: object) -> bool:
        return isinstance(value, str) and str(uuid.UUID(value)) == value.casefold()

    @checker.checks("date-time", raises=(ValueError, TypeError))
    def valid_datetime(value: object) -> bool:
        if not isinstance(value, str) or not _RFC3339.fullmatch(value):
            return False
        datetime.fromisoformat(value.removesuffix("Z") + ("+00:00" if value.endswith("Z") else ""))
        return True

    @checker.checks("uri")
    def valid_uri(value: object) -> bool:
        if not isinstance(value, str):
            return False
        parsed = urlparse(value)
        return bool(parsed.scheme and (parsed.netloc or parsed.scheme == "urn"))

    return checker


def schema_validator(name: str) -> Draft202012Validator:
    """Build the mandatory strict validator for a declared schema."""
    return Draft202012Validator(load_schema(name), format_checker=_format_checker())


def _run_repository_script(name: str) -> None:
    script = Path(__file__).parents[2] / "deploy" / "scripts" / name
    runpy.run_path(str(script), run_name="__main__")


def doctor_main() -> None:
    _run_repository_script("doctor.py")


def verify_plan_gate_main() -> None:
    _run_repository_script("verify_plan_gate.py")


__all__ = ["declared_schema_names", "load_schema", "schema_validator"]
