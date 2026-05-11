#!/usr/bin/env python3
from __future__ import annotations

import argparse, json, sys
from pathlib import Path
from typing import Any
from common import EXPECTED_ARTIFACTS, SCHEMA_DIR, load_json, resolve_room_path
try:
    import jsonschema  # type: ignore
except Exception:
    jsonschema = None

def fallback_validate(data: dict[str, Any], schema: dict[str, Any], label: str) -> list[str]:
    errors=[]
    for field in schema.get("required", []):
        if field not in data: errors.append(f"{label}: missing required field {field!r}")
    for key, value in data.items():
        spec=schema.get("properties", {}).get(key, {})
        if "enum" in spec and value not in spec["enum"]: errors.append(f"{label}: {key!r}={value!r} not in {spec['enum']!r}")
        if "const" in spec and value != spec["const"]: errors.append(f"{label}: {key!r} must be {spec['const']!r}")
        typ=spec.get("type")
        if typ == "array" and not isinstance(value, list): errors.append(f"{label}: {key!r} must be array")
        elif typ == "string" and not isinstance(value, str): errors.append(f"{label}: {key!r} must be string")
        elif typ == "boolean" and not isinstance(value, bool): errors.append(f"{label}: {key!r} must be boolean")
        elif typ == "number" and not isinstance(value, (int, float)): errors.append(f"{label}: {key!r} must be number")
    return errors

def validate_file(artifact_path: Path, schema_path: Path) -> list[str]:
    label=str(artifact_path)
    try:
        data=load_json(artifact_path); schema=load_json(schema_path)
    except json.JSONDecodeError as exc:
        return [f"{label}: invalid JSON at line {exc.lineno} column {exc.colno}: {exc.msg}"]
    except OSError as exc:
        return [f"{label}: {exc}"]
    if jsonschema is not None:
        validator=jsonschema.Draft202012Validator(schema)
        return [f"{label}: {'/'.join(map(str, error.path)) or '<root>'}: {error.message}" for error in sorted(validator.iter_errors(data), key=lambda e: list(e.path))]
    if not isinstance(data, dict): return [f"{label}: root must be object"]
    return fallback_validate(data, schema, label)

def _looks_like_local_artifact_ref(ref: str) -> bool:
    if "://" in ref or ref.startswith(("kanban:", "brain:", "receipt:", "cron:", "operator:", "web:", "manual:", "plan:")):
        return False
    if ":" in ref.partition("/")[0]:
        return False
    return "/" in ref and not ref.startswith(("/", ".."))


def validate_local_refs(room_dir: Path, artifact_path: Path) -> list[str]:
    try:
        data = load_json(artifact_path)
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, dict):
        return []
    errors=[]
    for key, value in data.items():
        if key.endswith("_refs") and isinstance(value, list):
            for ref in value:
                if isinstance(ref, str) and _looks_like_local_artifact_ref(ref) and not (room_dir / ref).exists():
                    errors.append(f"{artifact_path}: {key}: local artifact ref does not exist: {ref}")
    if isinstance(data.get("links"), list):
        for link in data["links"]:
            prefix=f"buildroom://{room_dir.name}/"
            if isinstance(link, str) and link.startswith(prefix):
                ref=link.removeprefix(prefix)
                if not (room_dir / ref).exists():
                    errors.append(f"{artifact_path}: links: local artifact ref does not exist: {ref}")
    return errors


def validate_room(room_dir: Path) -> list[str]:
    errors=[]
    for rel, schema_name in EXPECTED_ARTIFACTS.items():
        artifact=room_dir/rel
        if not artifact.exists(): errors.append(f"missing artifact: {rel}"); continue
        errors.extend(validate_file(artifact, SCHEMA_DIR/schema_name))
        errors.extend(validate_local_refs(room_dir, artifact))
    return errors

def main() -> int:
    parser=argparse.ArgumentParser(description="Validate a buildroom room against required artifacts and JSON Schemas.")
    parser.add_argument("room", type=Path)
    args=parser.parse_args(); room=resolve_room_path(args.room)
    errors=validate_room(room)
    if errors:
        print(f"buildroom validation failed for {room}:", file=sys.stderr)
        for error in errors: print(f"- {error}", file=sys.stderr)
        return 1
    print(f"buildroom validation passed: {room}"); return 0
if __name__ == "__main__": raise SystemExit(main())
