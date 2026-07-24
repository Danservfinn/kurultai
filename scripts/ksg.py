#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from solution_graph.registry import load_fixture_registry
from solution_graph.resolver import resolve_objective, simulate_plan
from solution_graph.validation import ContractError, validate_fixture, validate_manifest


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def emit(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="ksg", description="Offline read-only Kurultai Solution Graph resolver")
    sub = root.add_subparsers(dest="command", required=True)
    resolve = sub.add_parser("resolve", help="resolve an objective without invoking artifact code")
    resolve.add_argument("objective", type=Path)
    resolve.add_argument("--environment", type=Path, required=True)
    resolve.add_argument("--registry", type=Path, required=True)
    simulate = sub.add_parser("simulate", help="replay and validate a saved plan without invoking artifact code")
    simulate.add_argument("plan", type=Path)
    simulate.add_argument("--objective", type=Path, required=True)
    simulate.add_argument("--environment", type=Path, required=True)
    simulate.add_argument("--registry", type=Path, required=True)
    manifest = sub.add_parser("verify-manifest", help="validate one public manifest")
    manifest.add_argument("manifest", type=Path)
    fixture = sub.add_parser("verify-fixture", help="validate a fixture registry directory")
    fixture.add_argument("registry", type=Path)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "resolve":
            result = resolve_objective(read_json(args.objective), read_json(args.environment), load_fixture_registry(args.registry))
            emit(result)
            return 0 if result["status"] == "resolved" else 2
        if args.command == "simulate":
            result = simulate_plan(
                read_json(args.plan),
                read_json(args.objective),
                read_json(args.environment),
                load_fixture_registry(args.registry),
            )
            emit(result)
            return 0 if result["status"] == "pass" else 2
        if args.command == "verify-manifest":
            manifest = validate_manifest(read_json(args.manifest))
            emit({"schema": "ValidationResult/v1", "status": "valid", "artifact_id": manifest["artifact_id"]})
            return 0
        if args.command == "verify-fixture":
            fixture = validate_fixture(load_fixture_registry(args.registry))
            emit({"schema": "ValidationResult/v1", "status": "valid", "snapshot_id": fixture["snapshot_id"], "artifact_count": len(fixture["manifests"])})
            return 0
    except (ContractError, OSError, json.JSONDecodeError, TypeError, KeyError, AttributeError, OverflowError) as exc:
        emit({"schema": "ValidationResult/v1", "status": "invalid", "reason_codes": ["contract_invalid"], "detail": str(exc)})
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
