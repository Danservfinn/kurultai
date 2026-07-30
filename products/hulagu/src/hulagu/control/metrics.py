"""Schema-bounded aggregate metrics for the customer-free control room."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from .health import HealthCheck, HealthStatus

_SAFE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
_SAFE_REFERENCE = re.compile(r"^(?:sha256:[0-9a-f]{64}|[A-Za-z][A-Za-z0-9_.:-]{0,127})$")


@dataclass(frozen=True, slots=True)
class AggregateMetrics:
    run_counts: Mapping[str, int]
    state_counts: Mapping[str, int]
    error_class_counts: Mapping[str, int]
    latency_ms: Mapping[str, int]
    proof_debt: tuple[str, ...]
    build_refs: tuple[str, ...]
    correlation_ids: tuple[str, ...]


def _bounded_counts(values: Mapping[str, int], *, maximum: int = 100) -> dict[str, int]:
    if len(values) > maximum:
        raise ValueError("too many aggregate metric keys")
    result: dict[str, int] = {}
    for name, value in values.items():
        if not _SAFE_NAME.fullmatch(name) or not isinstance(value, int) or not 0 <= value <= 10**12:
            raise ValueError("invalid aggregate metric")
        result[name] = value
    return dict(sorted(result.items()))


def _bounded_labels(values: tuple[str, ...], *, maximum: int, references: bool = False) -> list[str]:
    if len(values) > maximum:
        raise ValueError("too many aggregate labels")
    result: list[str] = []
    for value in values:
        if not value or len(value) > 160 or "\n" in value or "\r" in value:
            raise ValueError("invalid aggregate label")
        if references and not _SAFE_REFERENCE.fullmatch(value):
            raise ValueError("invalid aggregate reference")
        lowered = value.lower()
        if any(marker in lowered for marker in ("@", "/volumes/", "telegram", "tenant_id", "cv text", "search query")):
            raise ValueError("customer-shaped aggregate label")
        result.append(value)
    return sorted(result)


def _closed_health_projection(health: Mapping[str, object]) -> dict[str, object]:
    expected_keys = {
        "schema_version",
        "generated_at",
        "status",
        "missing_dependencies",
        "failed_dependencies",
        "checks",
    }
    if set(health) != expected_keys or health.get("schema_version") != "HulaguHealth/v1":
        raise ValueError("invalid health projection")
    generated_at = health.get("generated_at")
    status = health.get("status")
    missing = health.get("missing_dependencies")
    failed = health.get("failed_dependencies")
    checks = health.get("checks")
    if (
        not isinstance(generated_at, str)
        or not 1 <= len(generated_at) <= 128
        or status not in {item.value for item in HealthStatus}
        or not isinstance(missing, list)
        or not isinstance(failed, list)
        or not isinstance(checks, list)
        or len(checks) > 32
    ):
        raise ValueError("invalid health projection")
    allowed_dependencies = {"database", "provider", "vault"}
    if any(not isinstance(name, str) or name not in allowed_dependencies for name in [*missing, *failed]):
        raise ValueError("invalid health projection")
    normalized_checks: list[dict[str, object]] = []
    try:
        for raw in checks:
            if not isinstance(raw, Mapping) or set(raw) != {"name", "status", "latency_ms", "reason"}:
                raise ValueError("invalid health projection")
            raw_name = raw["name"]
            raw_status = raw["status"]
            latency = raw["latency_ms"]
            reason = raw["reason"]
            if (
                not isinstance(raw_name, str)
                or not isinstance(raw_status, str)
                or raw_status not in {item.value for item in HealthStatus}
                or (latency is not None and (not isinstance(latency, int) or isinstance(latency, bool)))
                or (reason is not None and not isinstance(reason, str))
            ):
                raise ValueError("invalid health projection")
            check = HealthCheck(raw_name, HealthStatus(raw_status), latency_ms=latency, reason=reason)
            normalized_checks.append(
                {"name": check.name, "status": check.status.value, "latency_ms": check.latency_ms, "reason": check.reason}
            )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("invalid health projection") from error
    return {
        "schema_version": "HulaguHealth/v1",
        "generated_at": generated_at,
        "status": status,
        "missing_dependencies": sorted(missing),
        "failed_dependencies": sorted(failed),
        "checks": sorted(normalized_checks, key=lambda item: str(item["name"])),
    }


def project_control_room(metrics: AggregateMetrics, health: Mapping[str, object]) -> dict[str, object]:
    """Project only the closed aggregate schema admitted by plan §5.3."""

    return {
        "schema_version": "HulaguControlRoomProjection/v1",
        "health": _closed_health_projection(health),
        "metrics": {
            "run_counts": _bounded_counts(metrics.run_counts),
            "state_counts": _bounded_counts(metrics.state_counts),
            "error_class_counts": _bounded_counts(metrics.error_class_counts),
            "latency_ms": _bounded_counts(metrics.latency_ms),
            "proof_debt": _bounded_labels(metrics.proof_debt, maximum=50),
            "build_refs": _bounded_labels(metrics.build_refs, maximum=50, references=True),
            "correlation_ids": _bounded_labels(metrics.correlation_ids, maximum=100, references=True),
        },
    }
