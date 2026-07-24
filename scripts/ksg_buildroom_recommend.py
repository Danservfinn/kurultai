#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from solution_graph.buildroom import recommend_for_buildroom
from solution_graph.registry import load_fixture_registry
from solution_graph.schema_runtime import ContractError, load_json_file, validate_contract_schema


def _read_object(path: Path) -> dict:
    value = load_json_file(path)
    if not isinstance(value, dict):
        raise ContractError("JSON document must be an object")
    return value


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Emit a recommendation-only Solution Graph Buildroom projection")
    p.add_argument("objective", type=Path)
    p.add_argument("--environment", required=True, type=Path)
    p.add_argument("--registry", required=True, type=Path)
    p.add_argument("--room-id", required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        projection = recommend_for_buildroom(
            room_id=args.room_id,
            objective=_read_object(args.objective),
            environment=_read_object(args.environment),
            registry=load_fixture_registry(args.registry),
        )
        validate_contract_schema(projection)
    except (ContractError, OSError, ValueError, json.JSONDecodeError) as exc:
        error = {
            "schema": "ValidationResult/v1",
            "status": "invalid",
            "reason_codes": ["contract_invalid"],
            "detail": str(exc)[:512],
        }
        validate_contract_schema(error)
        print(json.dumps(error, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2
    sys.stdout.write(json.dumps(projection, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
