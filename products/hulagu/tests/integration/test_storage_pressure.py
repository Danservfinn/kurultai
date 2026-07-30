from __future__ import annotations

import importlib.util
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from hulagu.control.retention import AdmissionOperation, PressureState, StorageAdmissionController

ROOT = Path(__file__).parents[2]
_SPEC = importlib.util.spec_from_file_location("hulagu_task9_storage_pg_helpers", ROOT / "tests" / "integration" / "test_migrations.py")
assert _SPEC is not None and _SPEC.loader is not None
_HELPERS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HELPERS)
postgres_cluster = _HELPERS.postgres_cluster
psql = _HELPERS.psql


def test_tenant_quota_counts_concurrent_reservations_and_cannot_be_exceeded() -> None:
    controller = StorageAdmissionController()
    controller.configure("tenant-a", quota_bytes=100, accounted_bytes=40)
    first = controller.reserve("tenant-a", AdmissionOperation.UPLOAD, 50)
    with pytest.raises(PermissionError, match="quota"):
        controller.reserve("tenant-a", AdmissionOperation.SEARCH, 11)
    controller.settle("tenant-a", first, actual_bytes=45)
    assert controller.usage("tenant-a") == (85, 0, 100)


@pytest.mark.parametrize("state", [PressureState.LOW, PressureState.CRITICAL])
def test_pressure_refuses_upload_and_search_but_preserves_status_cancel_delete(state: PressureState) -> None:
    controller = StorageAdmissionController()
    controller.configure("tenant-a", quota_bytes=1000, accounted_bytes=0)
    controller.set_pressure(state, measured_bytes=900)
    for operation in (AdmissionOperation.UPLOAD, AdmissionOperation.SEARCH):
        with pytest.raises(PermissionError, match="pressure"):
            controller.reserve("tenant-a", operation, 1)
    for operation in (AdmissionOperation.STATUS, AdmissionOperation.CANCEL, AdmissionOperation.DELETE):
        assert controller.admit_control(operation)


def test_backup_read_only_lock_fences_storage_admission_and_settlement() -> None:
    controller = StorageAdmissionController()
    controller.configure("tenant-a", quota_bytes=100, accounted_bytes=0)
    reservation = controller.reserve("tenant-a", AdmissionOperation.UPLOAD, 10)
    controller.set_backup_read_only(True)
    with pytest.raises(PermissionError, match="backup"):
        controller.reserve("tenant-a", AdmissionOperation.SEARCH, 1)
    with pytest.raises(PermissionError, match="backup"):
        controller.settle("tenant-a", reservation, actual_bytes=10)


def test_real_postgres_concurrent_quota_reservations_admit_only_one() -> None:
    psycopg = pytest.importorskip("psycopg")
    tenant = "91000000-0000-4000-8000-000000000001"
    with postgres_cluster() as dsn:
        psql(
            dsn,
            f"INSERT INTO hulagu.tenants(id,state) VALUES('{tenant}','READY');"
            f"INSERT INTO hulagu.tenant_storage_state(tenant_id,quota_bytes,accounted_bytes) VALUES('{tenant}',100,0);",
        )

        def reserve() -> str:
            try:
                with psycopg.connect(dsn, user="hulagu_app") as connection, connection.cursor() as cursor:
                    cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant,))
                    cursor.execute("SELECT hulagu_api.admit_tenant_storage('upload',60)")
                    row = cursor.fetchone()
                    assert row is not None
                    return "admitted"
            except Exception as exc:  # noqa: BLE001 - concurrent authority outcome is classified
                assert "quota" in str(exc)
                return "refused"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = sorted(pool.map(lambda _: reserve(), range(2)))
        assert outcomes == ["admitted", "refused"]
        assert psql(
            dsn,
            f"SELECT reserved_bytes FROM hulagu.tenant_storage_state WHERE tenant_id='{tenant}'",
        ).stdout.strip() == "60"


def test_real_postgres_low_water_and_backup_lock_refuse_new_admission() -> None:
    tenant = "91000000-0000-4000-8000-000000000002"
    with postgres_cluster() as dsn:
        psql(
            dsn,
            f"INSERT INTO hulagu.tenants(id,state) VALUES('{tenant}','READY');"
            f"INSERT INTO hulagu.tenant_storage_state(tenant_id,quota_bytes,accounted_bytes) VALUES('{tenant}',100,0);"
            "UPDATE hulagu.global_storage_state SET pressure_state='low', measured_bytes=99 WHERE singleton;",
        )
        refused = psql(
            dsn,
            "BEGIN;"
            f"SET LOCAL app.tenant_id='{tenant}';"
            "SELECT hulagu_api.admit_tenant_storage('search',1);"
            "COMMIT;",
            user="hulagu_app",
            check=False,
        )
        assert refused.returncode != 0 and "pressure" in refused.stderr
        psql(dsn, "UPDATE hulagu.global_storage_state SET pressure_state='normal' WHERE singleton")
        psql(dsn, "SELECT hulagu_api.begin_backup_coordination(repeat('f',64))")
        locked = psql(
            dsn,
            "BEGIN;"
            f"SET LOCAL app.tenant_id='{tenant}';"
            "SELECT hulagu_api.admit_tenant_storage('upload',1);"
            "COMMIT;",
            user="hulagu_app",
            check=False,
        )
        assert locked.returncode != 0 and "backup lock" in locked.stderr
