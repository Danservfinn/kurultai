from __future__ import annotations

import hashlib
import time
from dataclasses import replace
from pathlib import Path

import pytest
from test_migrations import postgres_cluster, psql

from hulagu.domain.profile import Profile
from hulagu.runner_app import ParserLease, PostgresParserJobQueue, RunnerApp, RunnerCrash

TENANT = "00000000-0000-4000-8000-000000000001"
SAFE_PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n"


class FakeExecutor:
    def execute(self, input_payload: bytes, *, expected_digest: str) -> bytes:
        assert input_payload == SAFE_PDF
        return (
            '{"schema_version":"ParsedCv/v1","document_sha256":"'
            + expected_digest
            + '","fields":[]}'
        ).encode()


def _queue(dsn: str, tenant_root: Path) -> PostgresParserJobQueue:
    return PostgresParserJobQueue(dsn, tenant_root=tenant_root)


def test_app_enqueue_survives_fresh_connection_runner_restart_and_real_lease_expiry(tmp_path: Path) -> None:
    with postgres_cluster() as dsn:
        psql(dsn, f"INSERT INTO hulagu.tenants(id,state) VALUES('{TENANT}','READY')")
        tenant_root = tmp_path / "vault"
        input_path = tenant_root / TENANT / "quarantine" / "cv.pdf"
        input_path.parent.mkdir(parents=True)
        input_path.write_bytes(SAFE_PDF)
        digest = hashlib.sha256(SAFE_PDF).hexdigest()

        job, created = _queue(dsn, tenant_root).enqueue(
            tenant_id=TENANT,
            document_digest=digest,
            input_path=input_path,
        )
        assert created is True

        crashing = RunnerApp(
            _queue(dsn, tenant_root),
            FakeExecutor(),
            work_root=tmp_path / "work",
            clock=lambda: 0,
            lease_seconds=1,
            crash_after_claim=True,
        )
        with pytest.raises(RunnerCrash):
            crashing.run_once()

        time.sleep(1.1)
        restarted = RunnerApp(
            _queue(dsn, tenant_root),
            FakeExecutor(),
            work_root=tmp_path / "work",
            clock=lambda: 0,
            lease_seconds=1,
        )
        assert restarted.run_once() == "succeeded"
        assert psql(
            dsn,
            f"SELECT state || ':' || attempt FROM hulagu.parser_jobs WHERE id='{job.job_id}'",
        ).stdout.strip() == "succeeded:2"


def test_parser_completion_is_fully_cas_fenced_and_deletion_cannot_resurrect(tmp_path: Path) -> None:
    with postgres_cluster() as dsn:
        psql(dsn, f"INSERT INTO hulagu.tenants(id,state) VALUES('{TENANT}','READY')")
        tenant_root = tmp_path / "vault"
        input_path = tenant_root / TENANT / "quarantine" / "cv.pdf"
        input_path.parent.mkdir(parents=True)
        input_path.write_bytes(SAFE_PDF)
        digest = hashlib.sha256(SAFE_PDF).hexdigest()
        queue = _queue(dsn, tenant_root)
        job, _ = queue.enqueue(tenant_id=TENANT, document_digest=digest, input_path=input_path)
        lease = queue.claim(lease_seconds=30)
        assert lease is not None
        profile = Profile(version=1)

        mutations: tuple[ParserLease, ...] = (
            replace(lease, attempt=lease.attempt + 1),
            replace(lease, token="wrong-token"),
            replace(lease, immutable_input_digest="f" * 64),
            replace(lease, lifecycle_epoch=lease.lifecycle_epoch + 1),
            replace(lease, work_epoch=lease.work_epoch + 1),
        )
        for stale in mutations:
            assert queue.complete(stale, result_digest="e" * 64, profile=profile) is False
        assert psql(dsn, f"SELECT state FROM hulagu.parser_jobs WHERE id='{job.job_id}'").stdout.strip() == "claimed"

        psql(
            dsn,
            f"UPDATE hulagu.tenants SET state='DELETING', lifecycle_epoch=lifecycle_epoch+1 WHERE id='{TENANT}'",
        )
        assert queue.complete(lease, result_digest="e" * 64, profile=profile) is False
        assert queue.fail(lease) is False
        assert psql(dsn, f"SELECT state FROM hulagu.parser_jobs WHERE id='{job.job_id}'").stdout.strip() == "claimed"
        assert queue.claim(lease_seconds=30) is None


def test_parser_queue_routines_have_bounded_grants_and_no_runtime_table_grants() -> None:
    with postgres_cluster() as dsn:
        direct = psql(
            dsn,
            "SELECT grantee || ':' || privilege_type FROM information_schema.role_table_grants "
            "WHERE table_schema='hulagu' AND table_name='parser_jobs' "
            "AND grantee IN ('hulagu_app','hulagu_runner') ORDER BY 1",
        ).stdout.strip()
        assert direct == ""
        grants = psql(
            dsn,
            "SELECT routine_name || ':' || grantee FROM information_schema.routine_privileges "
            "WHERE routine_schema='hulagu_api' AND routine_name LIKE '%parser_job%' "
            "AND grantee IN ('hulagu_app','hulagu_runner') ORDER BY 1",
        ).stdout.splitlines()
        assert grants == [
            "claim_parser_job:hulagu_runner",
            "complete_parser_job:hulagu_runner",
            "enqueue_parser_job:hulagu_app",
            "fail_parser_job:hulagu_runner",
        ]


def test_parser_job_inputs_are_immutable_and_real_fail_routine_is_terminal(tmp_path: Path) -> None:
    with postgres_cluster() as dsn:
        psql(dsn, f"INSERT INTO hulagu.tenants(id,state) VALUES('{TENANT}','READY')")
        tenant_root = tmp_path / "vault"
        input_path = tenant_root / TENANT / "quarantine" / "cv.pdf"
        input_path.parent.mkdir(parents=True)
        input_path.write_bytes(SAFE_PDF)
        queue = _queue(dsn, tenant_root)
        job, _ = queue.enqueue(
            tenant_id=TENANT,
            document_digest=hashlib.sha256(SAFE_PDF).hexdigest(),
            input_path=input_path,
        )
        immutable_update = psql(
            dsn,
            f"UPDATE hulagu.parser_jobs SET immutable_input_digest=repeat('f',64) WHERE id='{job.job_id}'",
            check=False,
        )
        assert immutable_update.returncode != 0

        lease = queue.claim(lease_seconds=30)
        assert lease is not None
        assert queue.fail(lease) is True
        assert psql(
            dsn,
            f"SELECT state || ':' || attempt FROM hulagu.parser_jobs WHERE id='{job.job_id}'",
        ).stdout.strip() == "failed:1"
        assert queue.complete(lease, result_digest="e" * 64, profile=Profile(version=1)) is False
