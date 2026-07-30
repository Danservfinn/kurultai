from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from hulagu.control.health import HealthCheck, HealthStatus, build_health_report
from hulagu.control.metrics import AggregateMetrics, project_control_room

ROOT = Path(__file__).parents[2]


def passing_checks() -> tuple[HealthCheck, ...]:
    return (
        HealthCheck("database", HealthStatus.PASS, latency_ms=4),
        HealthCheck("provider", HealthStatus.PASS, latency_ms=8),
        HealthCheck("vault", HealthStatus.PASS, latency_ms=2),
    )


def test_health_fails_closed_for_each_required_dependency() -> None:
    for failed_name in ("database", "provider", "vault"):
        checks = tuple(
            HealthCheck(check.name, HealthStatus.FAIL if check.name == failed_name else check.status, latency_ms=check.latency_ms)
            for check in passing_checks()
        )
        report = build_health_report(checks, generated_at="2026-07-30T12:00:00Z")
        assert report["status"] == "fail"
        assert failed_name in report["failed_dependencies"]


def test_health_rejects_missing_required_dependency_instead_of_passing() -> None:
    report = build_health_report(passing_checks()[:-1], generated_at="2026-07-30T12:00:00Z")
    assert report["status"] == "fail"
    assert report["missing_dependencies"] == ["vault"]


def test_control_room_projection_is_aggregate_redacted_and_deterministic() -> None:
    projection = project_control_room(
        AggregateMetrics(
            run_counts={"succeeded": 7, "failed": 1},
            state_counts={"READY": 2},
            error_class_counts={"provider_timeout": 1},
            latency_ms={"p50": 20, "p95": 80},
            proof_debt=("G3 native PostgreSQL evidence",),
            build_refs=("sha256:" + "c" * 64,),
            correlation_ids=("opaque-1",),
        ),
        build_health_report(passing_checks(), generated_at="2026-07-30T12:00:00Z"),
    )
    serialized = json.dumps(projection, sort_keys=True)
    assert projection["schema_version"] == "HulaguControlRoomProjection/v1"
    assert projection["health"]["status"] == "pass"
    assert projection["metrics"]["run_counts"] == {"failed": 1, "succeeded": 7}
    for forbidden in ("tenant_id", "telegram", "cv", "profile", "query", "/Volumes/KurultaiVault"):
        assert forbidden not in serialized.lower()


def test_frozen_doctor_entrypoint_is_read_only_json_by_default() -> None:
    completed = subprocess.run(
        [sys.executable, "deploy/scripts/doctor.py", "--json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert completed.returncode == 1
    report = json.loads(completed.stdout)
    assert report["mutation_performed"] is False
    assert report["mode"] == "read_only"
    assert "usage:" not in completed.stderr


@pytest.mark.parametrize(
    "reason",
    (
        "contact person@example.test",
        "call +1-415-555-0199",
        "telegram route available",
        "private path /Volumes/KurultaiVault/customer",
        "https://example.test/role?query=private",
    ),
)
def test_health_reason_rejects_customer_shaped_values(reason: str) -> None:
    with pytest.raises(ValueError, match="reason"):
        HealthCheck("database", HealthStatus.FAIL, reason=reason)


@pytest.mark.parametrize(
    "health",
    (
        {"schema_version": "HulaguHealth/v1", "nested": {"email": "person@example.test"}},
        {
            "schema_version": "HulaguHealth/v1",
            "generated_at": "2026-07-30T12:00:00Z",
            "status": "pass",
            "missing_dependencies": [],
            "failed_dependencies": [],
            "checks": [],
            "arbitrary": "customer material",
        },
    ),
)
def test_control_room_rejects_health_outside_closed_typed_schema(health: dict[str, object]) -> None:
    metrics = AggregateMetrics({}, {}, {}, {}, (), (), ())
    with pytest.raises(ValueError, match="health projection"):
        project_control_room(metrics, health)
