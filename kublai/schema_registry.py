"""Flat frontmatter schema registry for the brain wiki."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class SchemaError(ValueError):
    """Raised when frontmatter does not satisfy a registered schema."""


@dataclass(frozen=True)
class SchemaRegistry:
    root: Path

    def __init__(self, root: str | Path):
        object.__setattr__(self, "root", Path(root).expanduser())

    def schema_path(self, page_type: str, schema_version: int = 1) -> Path:
        return self.root / page_type / f"v{schema_version}.schema.json"

    def load(self, page_type: str, schema_version: int = 1) -> dict[str, Any]:
        path = self.schema_path(page_type, schema_version)
        if not path.exists():
            path = self.schema_path("default", 1)
        return json.loads(path.read_text(encoding="utf-8"))

    def validate_frontmatter(self, page_type: str, frontmatter: dict[str, Any], schema_version: int = 1) -> None:
        schema = self.load(page_type, schema_version)
        required = schema.get("required") or []
        missing = [key for key in required if key not in frontmatter]
        if missing:
            raise SchemaError(f"{page_type} missing required frontmatter keys: {missing}")
        for key in schema.get("flat_only", []):
            value = frontmatter.get(key)
            if isinstance(value, dict):
                raise SchemaError(f"{page_type}.{key} must be flat")

    def publishable_fields(self, page_type: str, schema_version: int = 1) -> list[str]:
        return list(self.load(page_type, schema_version).get("publishable_fields") or [])

    def edge_sidecar_fields(self, page_type: str, schema_version: int = 1) -> list[str]:
        return list(self.load(page_type, schema_version).get("edge_sidecar_fields") or [])
