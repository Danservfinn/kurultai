"""Fail-closed, customer-free aggregate health evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from .privacy import unsafe_operator_value

_REQUIRED_DEPENDENCIES: Final[frozenset[str]] = frozenset({"database", "provider", "vault"})


class HealthStatus(StrEnum):
    PASS = "pass"  # nosec B105
    FAIL = "fail"
    NOT_EVALUATED = "not_evaluated"


@dataclass(frozen=True, slots=True)
class HealthCheck:
    name: str
    status: HealthStatus
    latency_ms: int | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.name or not self.name.replace("_", "").isalnum():
            raise ValueError("invalid health dependency name")
        if self.latency_ms is not None and not 0 <= self.latency_ms <= 300_000:
            raise ValueError("invalid health latency")
        if self.reason is not None and (
            not self.reason or len(self.reason) > 120 or unsafe_operator_value(self.reason)
        ):
            raise ValueError("invalid health reason")


def build_health_report(checks: tuple[HealthCheck, ...], *, generated_at: str) -> dict[str, object]:
    """Build a bounded report; a missing or non-passing required check is unhealthy."""

    if not generated_at or len(checks) > 32:
        raise ValueError("invalid health report")
    by_name: dict[str, HealthCheck] = {}
    for check in checks:
        if check.name in by_name:
            raise ValueError("duplicate health dependency")
        by_name[check.name] = check

    missing = sorted(_REQUIRED_DEPENDENCIES - by_name.keys())
    failed = sorted(
        name
        for name in _REQUIRED_DEPENDENCIES
        if name in by_name and by_name[name].status is not HealthStatus.PASS
    )
    status = HealthStatus.FAIL if missing or failed else HealthStatus.PASS
    return {
        "schema_version": "HulaguHealth/v1",
        "generated_at": generated_at,
        "status": status.value,
        "missing_dependencies": missing,
        "failed_dependencies": failed,
        "checks": [
            {
                "name": check.name,
                "status": check.status.value,
                "latency_ms": check.latency_ms,
                "reason": check.reason,
            }
            for check in sorted(checks, key=lambda item: item.name)
        ],
    }
