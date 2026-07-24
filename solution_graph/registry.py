from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .canonical import canonical_digest
from .validation import validate_fixture, validate_manifest


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_fixture_registry(root: Path | str) -> dict[str, Any]:
    root = Path(root)
    manifests = [validate_manifest(_read(path)) for path in sorted(root.glob("manifest-*.json"))]
    observations_path = root / "observations.json"
    observations_doc = _read(observations_path)
    observations = observations_doc.get("observations", [])
    registry = {
        "schema": "FixtureRegistry/v1",
        "manifests": manifests,
        "observations": observations,
    }
    registry["snapshot_id"] = canonical_digest({"manifests": manifests, "observations": observations})
    return validate_fixture(registry)
