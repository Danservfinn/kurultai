from __future__ import annotations

import hashlib
import importlib.util
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).parents[2]
_SPEC = importlib.util.spec_from_file_location("hulagu_storage_coordination_helpers", ROOT / "tests" / "integration" / "test_migrations.py")
assert _SPEC is not None and _SPEC.loader is not None
_HELPERS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HELPERS)
postgres_cluster = _HELPERS.postgres_cluster
psql = _HELPERS.psql


def _tenant(dsn: str, marker: str) -> str:
    enrollment = psql(
        dsn,
        "SELECT hulagu_api.resolve_enrollment("
        f"repeat('{marker}',64),repeat('{marker}',64),'privacy-v1',repeat('{marker}',64),"
        "now()+interval '10 minutes')",
        user="hulagu_app",
    ).stdout.strip()
    return psql(
        dsn,
        f"SELECT hulagu_api.promote_consented_enrollment('{enrollment}','privacy-v1',repeat('{marker}',64))",
        user="hulagu_app",
    ).stdout.strip()


def _app(dsn: str, tenant_id: str, sql: str, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return psql(
        dsn,
        f"BEGIN; SET LOCAL app.tenant_id='{tenant_id}'; {sql}; COMMIT;",
        user="hulagu_app",
        check=check,
    )


def _operator(dsn: str, tenant_id: str, sql: str) -> subprocess.CompletedProcess[str]:
    return psql(
        dsn,
        "BEGIN; SET LOCAL ROLE hulagu_migrator; "
        f"SET LOCAL app.tenant_id='{tenant_id}'; {sql}; COMMIT;",
    )


def _backup_operator(dsn: str, sql: str, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return psql(
        dsn,
        f"BEGIN; SET LOCAL ROLE hulagu_migrator; {sql}; COMMIT;",
        check=check,
    )


def _begin_backup(dsn: str, token_hash: str) -> str:
    return _backup_operator(
        dsn,
        f"SELECT hulagu_api.begin_backup_coordination('{token_hash}')",
    ).stdout.strip()


def _restart_postgres(dsn: str) -> None:
    data_directory = psql(dsn, "SHOW data_directory").stdout.strip()
    subprocess.run(
        ["/opt/homebrew/bin/pg_ctl", "-D", data_directory, "-m", "fast", "-w", "restart"],
        check=True,
        env={**os.environ, "LC_ALL": "C"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=30,
    )


def test_tenant_over_quota_is_refused_upload_and_search_while_global_pressure_is_normal() -> None:
    with postgres_cluster() as dsn:
        tenant_id = _tenant(dsn, "a")
        _operator(dsn, tenant_id, "SELECT hulagu_api.configure_tenant_storage(100,100)")

        upload = _app(
            dsn,
            tenant_id,
            "SELECT hulagu_api.admit_tenant_storage('upload',1)",
            check=False,
        )
        search = _app(
            dsn,
            tenant_id,
            "SELECT hulagu_api.admit_tenant_storage('search',1)",
            check=False,
        )

        assert upload.returncode != 0
        assert search.returncode != 0
        assert "tenant storage quota exceeded" in upload.stderr
        assert "tenant storage quota exceeded" in search.stderr
        assert psql(
            dsn,
            "SELECT pressure_state FROM hulagu.global_storage_state WHERE singleton",
        ).stdout.strip() == "normal"


def test_tenant_under_quota_is_admitted_while_another_tenant_is_over_quota() -> None:
    with postgres_cluster() as dsn:
        over_tenant = _tenant(dsn, "b")
        under_tenant = _tenant(dsn, "c")
        _operator(dsn, over_tenant, "SELECT hulagu_api.configure_tenant_storage(100,100)")
        _operator(dsn, under_tenant, "SELECT hulagu_api.configure_tenant_storage(100,20)")

        denied = _app(
            dsn,
            over_tenant,
            "SELECT hulagu_api.admit_tenant_storage('upload',1)",
            check=False,
        )
        admitted = _app(
            dsn,
            under_tenant,
            "SELECT hulagu_api.admit_tenant_storage('search',30)",
        ).stdout.strip()

        assert denied.returncode != 0
        assert admitted
        assert psql(
            dsn,
            "SELECT tenant_id || ':' || accounted_bytes || ':' || reserved_bytes "
            "FROM hulagu.tenant_storage_state ORDER BY tenant_id",
        ).stdout.splitlines() == sorted(
            [
                f"{over_tenant}:100:0",
                f"{under_tenant}:20:30",
            ]
        )


def test_storage_reservation_settles_actual_bytes_exactly_once() -> None:
    with postgres_cluster() as dsn:
        tenant_id = _tenant(dsn, "f")
        _operator(dsn, tenant_id, "SELECT hulagu_api.configure_tenant_storage(100,10)")
        reservation_id = _app(
            dsn,
            tenant_id,
            "SELECT hulagu_api.admit_tenant_storage('upload',30)",
        ).stdout.strip()

        assert _app(
            dsn,
            tenant_id,
            f"SELECT hulagu_api.settle_tenant_storage('{reservation_id}',20)",
        ).stdout.strip() == "t"
        assert _app(
            dsn,
            tenant_id,
            f"SELECT hulagu_api.settle_tenant_storage('{reservation_id}',20)",
        ).stdout.strip() == "f"
        assert psql(
            dsn,
            "SELECT accounted_bytes || ':' || reserved_bytes FROM hulagu.tenant_storage_state",
        ).stdout.strip() == "30:0"
        assert psql(dsn, "SELECT count(*) FROM hulagu.tenant_storage_reservations").stdout.strip() == "0"


def test_tenant_quota_accounting_survives_postgres_restart() -> None:
    with postgres_cluster() as dsn:
        tenant_id = _tenant(dsn, "e")
        _operator(dsn, tenant_id, "SELECT hulagu_api.configure_tenant_storage(100,0)")
        reservation_id = _app(
            dsn,
            tenant_id,
            "SELECT hulagu_api.admit_tenant_storage('upload',25)",
        ).stdout.strip()

        _restart_postgres(dsn)

        assert psql(
            dsn,
            "SELECT s.accounted_bytes || ':' || s.reserved_bytes || ':' || r.id "
            "FROM hulagu.tenant_storage_state AS s "
            "JOIN hulagu.tenant_storage_reservations AS r USING (tenant_id)",
        ).stdout.strip() == f"0:25:{reservation_id}"
        denied = _app(
            dsn,
            tenant_id,
            "SELECT hulagu_api.admit_tenant_storage('search',80)",
            check=False,
        )
        assert denied.returncode != 0
        assert "tenant storage quota exceeded" in denied.stderr


def test_storage_admission_is_refused_in_backup_read_only_mode() -> None:
    token_hash = hashlib.sha256(b"storage-backup-token").hexdigest()
    with postgres_cluster() as dsn:
        tenant_id = _tenant(dsn, "7")
        _operator(dsn, tenant_id, "SELECT hulagu_api.configure_tenant_storage(100,0)")
        _begin_backup(dsn, token_hash)

        blocked = _app(
            dsn,
            tenant_id,
            "SELECT hulagu_api.admit_tenant_storage('upload',1)",
            check=False,
        )

        assert blocked.returncode != 0
        assert "backup lock held" in blocked.stderr


def test_storage_settlement_is_refused_in_backup_read_only_mode() -> None:
    token_hash = hashlib.sha256(b"settlement-backup-token").hexdigest()
    with postgres_cluster() as dsn:
        tenant_id = _tenant(dsn, "8")
        _operator(dsn, tenant_id, "SELECT hulagu_api.configure_tenant_storage(100,0)")
        reservation_id = _app(
            dsn,
            tenant_id,
            "SELECT hulagu_api.admit_tenant_storage('upload',25)",
        ).stdout.strip()
        _begin_backup(dsn, token_hash)

        blocked = _app(
            dsn,
            tenant_id,
            f"SELECT hulagu_api.settle_tenant_storage('{reservation_id}',20)",
            check=False,
        )

        assert blocked.returncode != 0
        assert "backup lock held" in blocked.stderr


def test_begin_backup_drains_claimed_jobs_and_cancels_claimed_ordinary_outbox() -> None:
    token_hash = hashlib.sha256(b"drain-backup-token").hexdigest()
    lease_hash = hashlib.sha256(b"write-lease-token").hexdigest()
    run_id = "80500000-0000-4000-8000-000000000001"
    job_id = "80500000-0000-4000-8000-000000000002"
    outbox_id = "80500000-0000-4000-8000-000000000003"
    with postgres_cluster() as dsn:
        tenant_id = _tenant(dsn, "9")
        _app(
            dsn,
            tenant_id,
            "INSERT INTO hulagu.search_runs(tenant_id,id,state,query_plan,budget) "
            f"VALUES('{tenant_id}','{run_id}','running','{{}}','{{}}');"
            "INSERT INTO hulagu.job_attempts("
            "tenant_id,id,run_id,attempt,immutable_input_digest,lifecycle_epoch,work_epoch,state"
            f") VALUES('{tenant_id}','{job_id}','{run_id}',1,repeat('a',64),0,0,'queued');"
            "INSERT INTO hulagu.outbox_messages("
            "tenant_id,id,kind,payload,lifecycle_epoch,work_epoch,state,delivery_key"
            f") VALUES('{tenant_id}','{outbox_id}','ordinary','{{}}',0,0,'pending','backup:drain')",
        )
        assert psql(
            dsn,
            f"SELECT job_id FROM hulagu_api.claim_job('{job_id}','{lease_hash}',60)",
            user="hulagu_runner",
        ).stdout.strip() == job_id
        assert _app(
            dsn,
            tenant_id,
            f"SELECT outbox_id FROM hulagu_api.claim_outbox_delivery('{lease_hash}',10,60)",
        ).stdout.strip() == outbox_id

        _begin_backup(dsn, token_hash)

        assert psql(
            dsn,
            f"SELECT state || ':' || (lease_token_hash IS NULL) || ':' || (lease_expires_at IS NULL) "
            f"FROM hulagu.job_attempts WHERE id='{job_id}'",
        ).stdout.strip() == "expired:true:true"
        assert psql(
            dsn,
            f"SELECT state || ':' || (lease_token_hash IS NULL) || ':' || (lease_expires_at IS NULL) "
            f"FROM hulagu.outbox_messages WHERE id='{outbox_id}'",
        ).stdout.strip() == "cancelled:true:true"
        assert psql(
            dsn,
            "SELECT hulagu_api.complete_job("
            f"'{job_id}',1,'{lease_hash}',repeat('a',64),0,0,repeat('b',64))",
            user="hulagu_runner",
        ).stdout.strip() == "f"
        assert _app(
            dsn,
            tenant_id,
            "SELECT hulagu_api.record_outbox_delivery("
            f"'{outbox_id}',1,'{lease_hash}',0,0,'delivered',NULL)",
        ).stdout.strip() == "rejected"


def test_real_job_and_outbox_claims_are_refused_while_backup_lock_is_held() -> None:
    token_hash = hashlib.sha256(b"real-claim-fence-token").hexdigest()
    lease_hash = hashlib.sha256(b"real-claim-fence-lease").hexdigest()
    run_id = "80600000-0000-4000-8000-000000000001"
    job_id = "80600000-0000-4000-8000-000000000002"
    outbox_id = "80600000-0000-4000-8000-000000000003"
    with postgres_cluster() as dsn:
        tenant_id = _tenant(dsn, "6")
        _begin_backup(dsn, token_hash)
        _app(
            dsn,
            tenant_id,
            "INSERT INTO hulagu.search_runs(tenant_id,id,state,query_plan,budget) "
            f"VALUES('{tenant_id}','{run_id}','running','{{}}','{{}}');"
            "INSERT INTO hulagu.job_attempts("
            "tenant_id,id,run_id,attempt,immutable_input_digest,lifecycle_epoch,work_epoch,state"
            f") VALUES('{tenant_id}','{job_id}','{run_id}',1,repeat('a',64),0,0,'queued');"
            "INSERT INTO hulagu.outbox_messages("
            "tenant_id,id,kind,payload,lifecycle_epoch,work_epoch,state,delivery_key"
            f") VALUES('{tenant_id}','{outbox_id}','ordinary','{{}}',0,0,'pending','backup:fence')",
        )
        job_claim = psql(
            dsn,
            f"SELECT job_id FROM hulagu_api.claim_job('{job_id}','{lease_hash}',60)",
            user="hulagu_runner",
            check=False,
        )
        outbox_claim = _app(
            dsn,
            tenant_id,
            f"SELECT outbox_id FROM hulagu_api.claim_outbox_delivery('{lease_hash}',10,60)",
            check=False,
        )
        assert job_claim.returncode != 0 and "backup lock held" in job_claim.stderr
        assert outbox_claim.returncode != 0 and "backup lock held" in outbox_claim.stderr
        assert psql(dsn, f"SELECT state FROM hulagu.job_attempts WHERE id='{job_id}'").stdout.strip() == "queued"
        assert psql(dsn, f"SELECT state FROM hulagu.outbox_messages WHERE id='{outbox_id}'").stdout.strip() == "pending"


def test_publication_claim_is_refused_while_backup_lock_is_held() -> None:
    token_hash = hashlib.sha256(b"backup-token").hexdigest()
    tenant_id = "81000000-0000-4000-8000-000000000001"
    publication_id = "81000000-0000-4000-8000-000000000002"
    with postgres_cluster() as dsn:
        psql(dsn, f"INSERT INTO hulagu.tenants(id,state) VALUES('{tenant_id}','READY')")
        _app(
            dsn,
            tenant_id,
            "INSERT INTO hulagu.wiki_publications("
            "tenant_id,id,generation,manifest_digest,storage_ref,visibility_state,"
            "lifecycle_epoch,work_epoch,publication_sequence"
            f") VALUES('{tenant_id}','{publication_id}',1,repeat('a',64),"
            f"'/tenants/{tenant_id}/wiki/generations/1','staged',0,0,1)",
        )
        _begin_backup(dsn, token_hash)

        blocked = _app(
            dsn,
            tenant_id,
            f"SELECT hulagu_api.claim_publication('{publication_id}')",
            check=False,
        )

        assert blocked.returncode != 0
        assert "backup lock held" in blocked.stderr


def test_deletion_claim_is_refused_while_backup_lock_is_held() -> None:
    token_hash = hashlib.sha256(b"backup-token").hexdigest()
    delivery_hash = hashlib.sha256(b"delivery-token").hexdigest()
    nonce_hash = hashlib.sha256(b"backup-lock-deletion-nonce").hexdigest()
    with postgres_cluster() as dsn:
        tenant_id = _tenant(dsn, "d")
        psql(dsn, f"UPDATE hulagu.tenants SET deletion_nonce_hash='{nonce_hash}' WHERE id='{tenant_id}'")
        deletion_id = _app(
            dsn,
            tenant_id,
            f"SELECT hulagu_api.request_deletion('{nonce_hash}','ciphertext',repeat('b',64))",
        ).stdout.strip()
        _begin_backup(dsn, token_hash)

        blocked = psql(
            dsn,
            f"SELECT hulagu_api.claim_deletion_delivery('{deletion_id}','{delivery_hash}')",
            user="hulagu_deletion",
            check=False,
        )

        assert blocked.returncode != 0
        assert "backup lock held" in blocked.stderr


def test_retention_claim_is_refused_while_backup_lock_is_held() -> None:
    token_hash = hashlib.sha256(b"retention-backup-token").hexdigest()
    tenant_id = "82000000-0000-4000-8000-000000000001"
    retention_id = "82000000-0000-4000-8000-000000000002"
    with postgres_cluster() as dsn:
        psql(dsn, f"INSERT INTO hulagu.tenants(id,state) VALUES('{tenant_id}','READY')")
        _app(
            dsn,
            tenant_id,
            "INSERT INTO hulagu.retention_jobs(tenant_id,id,scope,state,lifecycle_epoch) "
            f"VALUES('{tenant_id}','{retention_id}','document','pending',0)",
        )
        _begin_backup(dsn, token_hash)

        blocked = _app(
            dsn,
            tenant_id,
            "SELECT hulagu_api.claim_retention(10)",
            check=False,
        )

        assert blocked.returncode != 0
        assert "backup lock held" in blocked.stderr


def test_snapshot_manifest_is_recorded_and_release_resumes_normal_claims() -> None:
    token_hash = hashlib.sha256(b"release-backup-token").hexdigest()
    tenant_id = "83000000-0000-4000-8000-000000000001"
    publication_id = "83000000-0000-4000-8000-000000000002"
    retention_id = "83000000-0000-4000-8000-000000000003"
    artifact_publication_id = "83000000-0000-4000-8000-000000000004"
    run_id = "83000000-0000-4000-8000-000000000005"
    job_id = "83000000-0000-4000-8000-000000000006"
    outbox_id = "83000000-0000-4000-8000-000000000007"
    lease_hash = hashlib.sha256(b"release-resume-lease").hexdigest()
    with postgres_cluster() as dsn:
        psql(dsn, f"INSERT INTO hulagu.tenants(id,state) VALUES('{tenant_id}','READY')")
        _app(
            dsn,
            tenant_id,
            "INSERT INTO hulagu.wiki_publications("
            "tenant_id,id,generation,manifest_digest,storage_ref,visibility_state,"
            "lifecycle_epoch,work_epoch,publication_sequence"
            f") VALUES('{tenant_id}','{publication_id}',1,repeat('a',64),"
            f"'/tenants/{tenant_id}/wiki/generations/1','staged',0,0,1),"
            f"('{tenant_id}','{artifact_publication_id}',2,repeat('b',64),"
            f"'/tenants/{tenant_id}/wiki/generations/2','active',0,0,2);"
            "INSERT INTO hulagu.retention_jobs(tenant_id,id,scope,state,lifecycle_epoch) "
            f"VALUES('{tenant_id}','{retention_id}','publication','pending',0)",
        )
        backup_id = _begin_backup(dsn, token_hash)
        manifest = (
            f"[{{\"tenant_id\":\"{tenant_id}\",\"generation\":2,"
            f"\"digest\":\"{'b' * 64}\"}}]"
        )

        manifest_record = _backup_operator(
            dsn,
            "SELECT hulagu_api.record_backup_snapshot("
            f"'{token_hash}','snapshot-0001','{manifest}'::jsonb)",
            check=False,
        )
        assert manifest_record.returncode == 0, manifest_record.stderr
        manifest_digest = manifest_record.stdout.strip()
        released = _backup_operator(
            dsn,
            f"SELECT hulagu_api.release_backup_coordination('{token_hash}')",
        ).stdout.strip()

        assert released == "t"
        assert manifest_digest == psql(
            dsn,
            f"SELECT encode(digest('{manifest}'::jsonb::text,'sha256'),'hex')",
        ).stdout.strip()
        assert psql(
            dsn,
            "SELECT backup_id || ':' || state || ':' || database_snapshot_id || ':' || "
            "artifact_manifest_digest FROM hulagu.backup_generations",
        ).stdout.strip() == f"{backup_id}:released:snapshot-0001:{manifest_digest}"
        assert _app(
            dsn,
            tenant_id,
            f"SELECT hulagu_api.claim_publication('{publication_id}')",
        ).stdout.strip() == "t"
        assert _app(
            dsn,
            tenant_id,
            "SELECT hulagu_api.claim_retention(10)",
        ).stdout.strip() == retention_id
        _app(
            dsn,
            tenant_id,
            "INSERT INTO hulagu.search_runs(tenant_id,id,state,query_plan,budget) "
            f"VALUES('{tenant_id}','{run_id}','running','{{}}','{{}}');"
            "INSERT INTO hulagu.job_attempts("
            "tenant_id,id,run_id,attempt,immutable_input_digest,lifecycle_epoch,work_epoch,state"
            f") VALUES('{tenant_id}','{job_id}','{run_id}',1,repeat('a',64),0,0,'queued');"
            "INSERT INTO hulagu.outbox_messages("
            "tenant_id,id,kind,payload,lifecycle_epoch,work_epoch,state,delivery_key"
            f") VALUES('{tenant_id}','{outbox_id}','ordinary','{{}}',0,0,'pending','backup:resume')",
        )
        assert psql(
            dsn,
            f"SELECT job_id FROM hulagu_api.claim_job('{job_id}','{lease_hash}',60)",
            user="hulagu_runner",
        ).stdout.strip() == job_id
        assert _app(
            dsn,
            tenant_id,
            f"SELECT outbox_id FROM hulagu_api.claim_outbox_delivery('{lease_hash}',10,60)",
        ).stdout.strip() == outbox_id


def test_snapshot_manifest_rejects_malformed_duplicate_and_unpinned_entries() -> None:
    token_hash = hashlib.sha256(b"manifest-contract-token").hexdigest()
    tenant_id = "83500000-0000-4000-8000-000000000001"
    publication_id = "83500000-0000-4000-8000-000000000002"
    staged_publication_id = "83500000-0000-4000-8000-000000000003"
    digest = "c" * 64
    valid_entry = f'{{"tenant_id":"{tenant_id}","generation":7,"digest":"{digest}"}}'
    invalid_manifests = [
        "null",
        "1",
        "{}",
        "[]",
        "[1]",
        '[{"unexpected":true}]',
        f'[{valid_entry[:-1]},"unknown":true}}]',
        f'[{{"tenant_id":"{tenant_id}","generation":7}}]',
        f'[{{"tenant_id":"not-a-uuid","generation":7,"digest":"{digest}"}}]',
        f'[{{"tenant_id":"{tenant_id}","generation":0,"digest":"{digest}"}}]',
        f'[{{"tenant_id":"{tenant_id}","generation":1.5,"digest":"{digest}"}}]',
        f'[{{"tenant_id":"{tenant_id}","generation":"7","digest":"{digest}"}}]',
        f'[{{"tenant_id":"{tenant_id}","generation":7,"digest":"{"C" * 64}"}}]',
        f'[{valid_entry},{valid_entry}]',
        f'[{{"tenant_id":"{tenant_id}","generation":8,"digest":"{digest}"}}]',
        f'[{{"tenant_id":"{tenant_id}","generation":6,"digest":"{digest}"}}]',
    ]
    with postgres_cluster() as dsn:
        psql(dsn, f"INSERT INTO hulagu.tenants(id,state) VALUES('{tenant_id}','READY')")
        _app(
            dsn,
            tenant_id,
            "INSERT INTO hulagu.wiki_publications("
            "tenant_id,id,generation,manifest_digest,storage_ref,visibility_state,"
            "lifecycle_epoch,work_epoch,publication_sequence"
            f") VALUES('{tenant_id}','{publication_id}',7,'{digest}',"
            f"'/tenants/{tenant_id}/wiki/generations/7','active',0,0,1),"
            f"('{tenant_id}','{staged_publication_id}',6,'{digest}',"
            f"'/tenants/{tenant_id}/wiki/generations/6','staged',0,0,2)",
        )
        _begin_backup(dsn, token_hash)
        for manifest in invalid_manifests:
            rejected = _backup_operator(
                dsn,
                "SELECT hulagu_api.record_backup_snapshot("
                f"'{token_hash}','snapshot-invalid','{manifest}'::jsonb)",
                check=False,
            )
            assert rejected.returncode != 0, manifest

        oversized = _backup_operator(
            dsn,
            "SELECT hulagu_api.record_backup_snapshot("
            f"'{token_hash}','snapshot-oversized',(SELECT jsonb_agg(jsonb_build_object("
            f"'tenant_id','{tenant_id}','generation',7,'digest','{digest}')) "
            "FROM generate_series(1,10001)))",
            check=False,
        )
        assert oversized.returncode != 0
        assert "invalid bounded backup snapshot metadata" in oversized.stderr

        valid_record = _backup_operator(
            dsn,
            "SELECT hulagu_api.record_backup_snapshot("
            f"'{token_hash}','snapshot-valid','[{valid_entry}]'::jsonb)",
            check=False,
        )
        assert valid_record.returncode == 0, valid_record.stderr
        valid_digest = valid_record.stdout.strip()
        immutable = _backup_operator(
            dsn,
            "SELECT hulagu_api.record_backup_snapshot("
            f"'{token_hash}','snapshot-rewrite','[{valid_entry}]'::jsonb)",
            check=False,
        )
        assert len(valid_digest) == 64
        assert immutable.returncode != 0
        assert "backup snapshot already recorded" in immutable.stderr


def test_backup_lock_waits_for_an_in_flight_publication_claim() -> None:
    token_hash = hashlib.sha256(b"concurrent-backup-token").hexdigest()
    tenant_id = "84000000-0000-4000-8000-000000000001"
    publication_id = "84000000-0000-4000-8000-000000000002"
    with postgres_cluster() as dsn:
        psql(dsn, f"INSERT INTO hulagu.tenants(id,state) VALUES('{tenant_id}','READY')")
        _app(
            dsn,
            tenant_id,
            "INSERT INTO hulagu.wiki_publications("
            "tenant_id,id,generation,manifest_digest,storage_ref,visibility_state,"
            "lifecycle_epoch,work_epoch,publication_sequence"
            f") VALUES('{tenant_id}','{publication_id}',1,repeat('a',64),"
            f"'/tenants/{tenant_id}/wiki/generations/1','staged',0,0,1)",
        )
        publisher = subprocess.Popen(
            ["/opt/homebrew/bin/psql", "-X", "-q", "-A", "-t", f"{dsn}&user=hulagu_app"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert publisher.stdin is not None and publisher.stdout is not None
        try:
            publisher.stdin.write(
                "BEGIN;"
                f"SET LOCAL app.tenant_id='{tenant_id}';"
                f"SELECT hulagu_api.claim_publication('{publication_id}');"
                "SELECT 'publication_claim_held';\n"
            )
            publisher.stdin.flush()
            while publisher.stdout.readline().strip() != "publication_claim_held":
                pass

            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_begin_backup, dsn, token_hash)
                time.sleep(0.25)
                assert not future.done(), "backup lock bypassed an in-flight publication claim"
                publisher.stdin.write("COMMIT; \\q\n")
                publisher.stdin.flush()
                assert future.result(timeout=10)
        finally:
            if publisher.poll() is None:
                publisher.kill()
            publisher.communicate(timeout=5)


def test_backup_serializes_after_in_flight_real_claims_without_lock_order_deadlock() -> None:
    lease_hash = hashlib.sha256(b"in-flight-real-claim-lease").hexdigest()
    tenant_id = "84500000-0000-4000-8000-000000000001"
    run_id = "84500000-0000-4000-8000-000000000002"
    job_id = "84500000-0000-4000-8000-000000000003"
    outbox_id = "84500000-0000-4000-8000-000000000004"
    for claim_kind in ("job", "outbox"):
        token_hash = hashlib.sha256(f"in-flight-{claim_kind}-backup".encode()).hexdigest()
        with postgres_cluster() as dsn:
            psql(dsn, f"INSERT INTO hulagu.tenants(id,state) VALUES('{tenant_id}','READY')")
            _app(
                dsn,
                tenant_id,
                "INSERT INTO hulagu.search_runs(tenant_id,id,state,query_plan,budget) "
                f"VALUES('{tenant_id}','{run_id}','running','{{}}','{{}}');"
                "INSERT INTO hulagu.job_attempts("
                "tenant_id,id,run_id,attempt,immutable_input_digest,lifecycle_epoch,work_epoch,state"
                f") VALUES('{tenant_id}','{job_id}','{run_id}',1,repeat('a',64),0,0,'queued');"
                "INSERT INTO hulagu.outbox_messages("
                "tenant_id,id,kind,payload,lifecycle_epoch,work_epoch,state,delivery_key"
                f") VALUES('{tenant_id}','{outbox_id}','ordinary','{{}}',0,0,'pending','backup:serialize')",
            )
            if claim_kind == "job":
                user = "hulagu_runner"
                claim_sql = f"SELECT job_id FROM hulagu_api.claim_job('{job_id}','{lease_hash}',60);"
            else:
                user = "hulagu_app"
                claim_sql = (
                    f"SET LOCAL app.tenant_id='{tenant_id}';"
                    f"SELECT outbox_id FROM hulagu_api.claim_outbox_delivery('{lease_hash}',10,60);"
                )
            claimant = subprocess.Popen(
                ["/opt/homebrew/bin/psql", "-X", "-q", "-A", "-t", f"{dsn}&user={user}"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            assert claimant.stdin is not None and claimant.stdout is not None
            try:
                claimant.stdin.write(f"BEGIN;{claim_sql}SELECT 'real_claim_held';\n")
                claimant.stdin.flush()
                while claimant.stdout.readline().strip() != "real_claim_held":
                    pass
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(_begin_backup, dsn, token_hash)
                    time.sleep(0.25)
                    assert not future.done(), f"backup bypassed in-flight {claim_kind} claim"
                    claimant.stdin.write("COMMIT; \\q\n")
                    claimant.stdin.flush()
                    assert future.result(timeout=10)
            finally:
                if claimant.poll() is None:
                    claimant.kill()
                claimant.communicate(timeout=5)
            expected = "expired" if claim_kind == "job" else "cancelled"
            table = "job_attempts" if claim_kind == "job" else "outbox_messages"
            row_id = job_id if claim_kind == "job" else outbox_id
            assert psql(dsn, f"SELECT state FROM hulagu.{table} WHERE id='{row_id}'").stdout.strip() == expected


def test_storage_and_backup_capabilities_have_exact_role_grants() -> None:
    with postgres_cluster() as dsn:
        assert psql(
            dsn,
            "SELECT count(*) FROM information_schema.role_table_grants "
            "WHERE grantee IN ('hulagu_app','hulagu_runner','hulagu_deletion','hulagu_migrator') "
            "AND table_schema='hulagu' AND table_name IN ("
            "'tenant_storage_state','tenant_storage_reservations','backup_coordination','backup_generations')",
        ).stdout.strip() == "0"
        routines = psql(
            dsn,
            "SELECT p.proname || ':' || pg_get_userbyid(p.proowner) || ':' || "
            "coalesce(array_to_string(p.proconfig,','),'') || ':' || "
            "has_function_privilege('public',p.oid,'EXECUTE') || ':' || "
            "has_function_privilege('hulagu_app',p.oid,'EXECUTE') || ':' || "
            "has_function_privilege('hulagu_migrator',p.oid,'EXECUTE') || ':' || "
            "has_function_privilege('hulagu_runner',p.oid,'EXECUTE') || ':' || "
            "has_function_privilege('hulagu_deletion',p.oid,'EXECUTE') "
            "FROM pg_proc AS p JOIN pg_namespace AS n ON n.oid=p.pronamespace "
            "WHERE n.nspname='hulagu_api' AND p.proname IN ("
            "'configure_tenant_storage','admit_tenant_storage','settle_tenant_storage',"
            "'begin_backup_coordination','record_backup_snapshot','release_backup_coordination',"
            "'claim_job','claim_outbox_delivery','claim_publication','claim_retention',"
            "'claim_deletion_delivery') ORDER BY p.proname",
        ).stdout.splitlines()
        assert routines == [
            "admit_tenant_storage:hulagu_owner:search_path=pg_catalog:false:true:false:false:false",
            "begin_backup_coordination:hulagu_owner:search_path=pg_catalog:false:false:true:false:false",
            "claim_deletion_delivery:hulagu_owner:search_path=pg_catalog:false:false:false:false:true",
            "claim_job:hulagu_owner:search_path=pg_catalog:false:false:false:true:false",
            "claim_outbox_delivery:hulagu_owner:search_path=pg_catalog:false:true:false:false:false",
            "claim_publication:hulagu_owner:search_path=pg_catalog:false:true:false:false:false",
            "claim_retention:hulagu_owner:search_path=pg_catalog:false:true:false:false:false",
            "configure_tenant_storage:hulagu_owner:search_path=pg_catalog:false:false:true:false:false",
            "record_backup_snapshot:hulagu_owner:search_path=pg_catalog:false:false:true:false:false",
            "release_backup_coordination:hulagu_owner:search_path=pg_catalog:false:false:true:false:false",
            "settle_tenant_storage:hulagu_owner:search_path=pg_catalog:false:true:false:false:false",
        ]
