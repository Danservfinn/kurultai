from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

from .registry import load_fixture_registry
from .resolver import resolve_objective, simulate_plan
from .schema_runtime import ContractError


def _walk(value: Any) -> Iterable[tuple[str | None, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key), child
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield None, child
            yield from _walk(child)


def _reject_request_locations(payload: dict[str, Any]) -> None:
    for key, value in _walk(payload):
        lowered = key.lower() if key else ""
        if lowered in {
            "path",
            "url",
            "uri",
            "objective_path",
            "environment_path",
            "plan_path",
            "registry_path",
            "manifest_path",
        }:
            raise ContractError("request-controlled paths and URLs are forbidden")
        if isinstance(value, str) and value.startswith(("http://", "https://", "file://")):
            raise ContractError("request-controlled paths and URLs are forbidden")


def _require_exact_payload(payload: dict[str, Any], keys: set[str]) -> None:
    if not isinstance(payload, dict):
        raise ContractError("request body must be a JSON object")
    if set(payload) != keys:
        raise ContractError("request body fields are invalid")
    _reject_request_locations(payload)


class SolutionGraphService:
    """Read-only facade over one fixed registry snapshot."""

    def __init__(self, registry: dict[str, Any]) -> None:
        self._registry = deepcopy(registry)
        self.registry_snapshot = self._registry["snapshot_id"]

    @classmethod
    def from_registry_root(cls, root: Path | str) -> "SolutionGraphService":
        return cls(load_fixture_registry(root))

    def resolve(self, payload: dict[str, Any]) -> dict[str, Any]:
        _require_exact_payload(payload, {"objective", "environment"})
        return resolve_objective(
            deepcopy(payload["objective"]),
            deepcopy(payload["environment"]),
            deepcopy(self._registry),
        )

    def simulate(self, route_plan_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        _require_exact_payload(payload, {"plan", "objective", "environment"})
        plan = payload["plan"]
        if not isinstance(plan, dict):
            raise ContractError("plan must be an object")
        body_plan_id = plan.get("plan_id")
        if body_plan_id != route_plan_id:
            raise ContractError("route plan_id must match body plan.plan_id")
        return simulate_plan(
            deepcopy(plan),
            deepcopy(payload["objective"]),
            deepcopy(payload["environment"]),
            deepcopy(self._registry),
        )
