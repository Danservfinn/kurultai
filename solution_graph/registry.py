from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical import canonical_digest
from .schema_runtime import ContractError, load_json_file
from .validation import validate_fixture, validate_manifest, validate_observation_set


_MAX_MANIFESTS = 128


def _regular_json_files(root: Path) -> list[Path]:
    paths = sorted(root.glob("manifest-*.json"))
    if len(paths) > _MAX_MANIFESTS:
        raise ContractError("fixture registry exceeds maximum manifest count")
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ContractError("fixture registry entries must be regular JSON files")
    return paths


def _read_object(path: Path) -> dict[str, Any]:
    value = load_json_file(path)
    if not isinstance(value, dict):
        raise ContractError("JSON document must be an object")
    return value


def load_fixture_registry(root: Path | str) -> dict[str, Any]:
    unresolved_root = Path(root)
    if unresolved_root.is_symlink():
        raise ContractError("fixture registry root must not be a symlink")
    root = unresolved_root.resolve(strict=True)
    if not root.is_dir():
        raise ContractError("fixture registry root must be a regular directory")
    manifests = [validate_manifest(_read_object(path)) for path in _regular_json_files(root)]
    observations_path = root / "observations.json"
    observations_doc = validate_observation_set(_read_object(observations_path))
    observations = observations_doc["observations"]
    registry = {
        "schema": "FixtureRegistry/v1",
        "manifests": manifests,
        "observations": observations,
    }
    registry["snapshot_id"] = canonical_digest({"manifests": manifests, "observations": observations})
    return validate_fixture(registry)
