from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "integration"))

from test_migrations import postgres_cluster, psql

SUBJECT = "a" * 64
FENCE = "b" * 64
NOTICE = "privacy-v1"
NONCE = "c" * 64


def scalar(dsn: str, sql: str, *, user: str = "hulagu_app") -> str:
    return psql(dsn, sql, user=user).stdout.strip()


def create_tenant(dsn: str, subject: str = SUBJECT, fence: str = FENCE) -> str:
    enrollment = scalar(
        dsn,
        f"SELECT hulagu_api.resolve_enrollment('{subject}','{fence}','{NOTICE}','{NONCE}',now()+interval '10 minutes')",
    )
    return scalar(dsn, f"SELECT hulagu_api.promote_consented_enrollment('{enrollment}','{NOTICE}','{NONCE}')")


def request_deletion(dsn: str, tenant: str) -> str:
    return scalar(
        dsn,
        "BEGIN; "
        f"SET LOCAL app.tenant_id='{tenant}'; SET LOCAL app.actor='telegram-customer'; "
        "SET LOCAL app.correlation_id='delete'; "
        "SELECT hulagu_api.request_deletion('ciphertext','route-binding-v1'); COMMIT;",
    )


def claim_deletion(dsn: str, deletion_id: str, token: str = "delete-token") -> str:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    return scalar(
        dsn,
        f"SELECT hulagu_api.claim_deletion_delivery('{deletion_id}','{token_hash}')",
        user="hulagu_deletion",
    )


def test_preconsent_resolution_cannot_create_tenant_and_promotion_is_single_authority() -> None:
    with postgres_cluster() as dsn:
        enrollment = scalar(
            dsn,
            f"SELECT hulagu_api.resolve_enrollment('{SUBJECT}','{FENCE}','{NOTICE}','{NONCE}',now()+interval '10 minutes')",
        )
        assert enrollment
        assert psql(dsn, "SELECT count(*) FROM hulagu.tenants").stdout.strip() == "0"
        tenant = scalar(
            dsn,
            f"SELECT hulagu_api.promote_consented_enrollment('{enrollment}','{NOTICE}','{NONCE}')",
        )
        assert tenant
        assert psql(dsn, "SELECT count(*) FROM hulagu.tenants").stdout.strip() == "1"
        replay = psql(
            dsn,
            f"SELECT hulagu_api.promote_consented_enrollment('{enrollment}','{NOTICE}','{NONCE}')",
            user="hulagu_app",
            check=False,
        )
        assert replay.returncode != 0
        assert scalar(dsn, f"SELECT hulagu_api.resolve_existing_tenant('{SUBJECT}')") == tenant


def test_deletion_global_state_survives_tenant_erasure_and_minimizes_receipt() -> None:
    with postgres_cluster() as dsn:
        tenant = create_tenant(dsn)
        deletion_id = request_deletion(dsn, tenant)
        token = "delete-token"
        assert claim_deletion(dsn, deletion_id, token) == "ciphertext"
        assert scalar(dsn, f"SELECT hulagu_api.finalize_deletion('{deletion_id}','forged-token')", user="hulagu_deletion") == "f"
        assert psql(dsn, f"SELECT count(*) FROM hulagu.tenants WHERE id='{tenant}'").stdout.strip() == "1"
        assert scalar(dsn, f"SELECT hulagu_api.finalize_deletion('{deletion_id}','{token}')", user="hulagu_deletion") == "t"
        assert psql(dsn, f"SELECT count(*) FROM hulagu.tenants WHERE id='{tenant}'").stdout.strip() == "0"
        assert psql(dsn, f"SELECT target_tenant_id IS NULL AND encrypted_route IS NULL FROM hulagu.deletion_jobs WHERE deletion_id='{deletion_id}'").stdout.strip() == "t"
        columns = set(psql(dsn, "SELECT column_name FROM information_schema.columns WHERE table_schema='hulagu' AND table_name='deletion_receipts'").stdout.splitlines())
        assert not ({"tenant_id", "encrypted_route", "route_binding"} & columns)
        assert psql(dsn, f"SELECT count(*) FROM hulagu.deletion_receipts WHERE deletion_id='{deletion_id}'").stdout.strip() == "1"


def test_barred_subject_is_rejected_before_enrollment_state_is_created() -> None:
    with postgres_cluster() as dsn:
        tenant = create_tenant(dsn)
        deletion_id = request_deletion(dsn, tenant)
        assert claim_deletion(dsn, deletion_id) == "ciphertext"
        assert scalar(dsn, f"SELECT hulagu_api.finalize_deletion('{deletion_id}','delete-token')", user="hulagu_deletion") == "t"
        rotated_subject = "d" * 64
        blocked = psql(
            dsn,
            f"SELECT hulagu_api.resolve_enrollment('{rotated_subject}','{FENCE}','{NOTICE}','{NONCE}',now()+interval '10 minutes')",
            user="hulagu_app",
            check=False,
        )
        assert blocked.returncode != 0
        assert psql(dsn, f"SELECT count(*) FROM hulagu.enrollments WHERE subject_digest='{rotated_subject}'").stdout.strip() == "0"
        assert psql(dsn, "SELECT count(*) FROM hulagu.tenants").stdout.strip() == "0"


def test_deletion_preserves_stable_fence_across_subject_key_rotation() -> None:
    with postgres_cluster() as dsn:
        tenant = create_tenant(dsn)
        rotated_subject = "d" * 64
        psql(dsn, f"UPDATE hulagu.identity_bindings SET subject_digest='{rotated_subject}' WHERE tenant_id='{tenant}'")
        deletion_id = request_deletion(dsn, tenant)
        assert claim_deletion(dsn, deletion_id) == "ciphertext"
        assert scalar(dsn, f"SELECT hulagu_api.finalize_deletion('{deletion_id}','delete-token')", user="hulagu_deletion") == "t"
        assert psql(dsn, "SELECT subject_fence_digest FROM hulagu.deletion_tombstones").stdout.strip() == FENCE


def test_expired_deletion_authority_cannot_disclose_route_or_erase_tenant() -> None:
    with postgres_cluster() as dsn:
        tenant = create_tenant(dsn)
        deletion_id = request_deletion(dsn, tenant)
        psql(dsn, f"UPDATE hulagu.deletion_jobs SET expires_at=now()-interval '1 second' WHERE deletion_id='{deletion_id}'")
        assert claim_deletion(dsn, deletion_id) == ""
        assert scalar(dsn, f"SELECT hulagu_api.finalize_deletion('{deletion_id}','delete-token')", user="hulagu_deletion") == "f"
        assert psql(dsn, f"SELECT count(*) FROM hulagu.tenants WHERE id='{tenant}'").stdout.strip() == "1"

        active_tenant = create_tenant(dsn, "e" * 64, "f" * 64)
        active_deletion = request_deletion(dsn, active_tenant)
        assert claim_deletion(dsn, active_deletion) == "ciphertext"
        psql(dsn, f"UPDATE hulagu.deletion_jobs SET expires_at=now()-interval '1 second' WHERE deletion_id='{active_deletion}'")
        assert scalar(
            dsn,
            f"SELECT hulagu_api.finalize_deletion('{active_deletion}','delete-token')",
            user="hulagu_deletion",
        ) == "f"
        assert psql(dsn, f"SELECT count(*) FROM hulagu.tenants WHERE id='{active_tenant}'").stdout.strip() == "1"


def test_runtime_roles_have_no_direct_global_table_grants_and_health_is_redacted() -> None:
    with postgres_cluster() as dsn:
        grants = psql(
            dsn,
            "SELECT count(*) FROM information_schema.role_table_grants WHERE grantee IN "
            "('hulagu_app','hulagu_runner','hulagu_deletion') AND table_schema='hulagu' AND table_name IN "
            "('enrollments','inbound_updates','deletion_jobs','deletion_tombstones','deletion_receipts','global_storage_state')",
        ).stdout.strip()
        assert grants == "0"
        health = scalar(dsn, "SELECT hulagu_api.aggregate_health()::text")
        assert "tenant" not in health.lower()
        assert SUBJECT not in health and FENCE not in health


def test_runner_and_deletion_tokens_are_single_attempt_fences() -> None:
    with postgres_cluster() as dsn:
        tenant = "50000000-0000-4000-8000-000000000001"
        run_id = "50000000-0000-4000-8000-000000000002"
        job_id = "50000000-0000-4000-8000-000000000003"
        lease_hash = hashlib.sha256(b"lease-token").hexdigest()
        input_digest = "e" * 64
        psql(
            dsn,
            f"INSERT INTO hulagu.tenants(id,state) VALUES('{tenant}','READY');"
            f"INSERT INTO hulagu.search_runs(tenant_id,id,state,query_plan,budget,work_epoch) "
            f"VALUES('{tenant}','{run_id}','queued','{{}}','{{}}',0);"
            f"INSERT INTO hulagu.job_attempts(tenant_id,id,run_id,attempt,immutable_input_digest,lifecycle_epoch,work_epoch,state) "
            f"VALUES('{tenant}','{job_id}','{run_id}',1,'{input_digest}',0,0,'queued');",
        )
        claimed = scalar(dsn, f"SELECT job_id FROM hulagu_api.claim_job('{job_id}','{lease_hash}',60)", user="hulagu_runner")
        assert claimed == job_id
        forged = scalar(
            dsn,
            f"SELECT hulagu_api.complete_job('{job_id}',1,repeat('0',64),'{input_digest}',0,0,'result')",
            user="hulagu_runner",
        )
        assert forged == "f"
        completed = scalar(
            dsn,
            f"SELECT hulagu_api.complete_job('{job_id}',1,'{lease_hash}','{input_digest}',0,0,'result')",
            user="hulagu_runner",
        )
        assert completed == "t"
        missing = scalar(
            dsn,
            "SELECT hulagu_api.claim_deletion_delivery('ffffffff-ffff-4fff-8fff-ffffffffffff',repeat('f',64)) IS NULL",
            user="hulagu_deletion",
        )
        assert missing == "t"


def test_fail_job_rejects_stale_attempt_digest_epochs_state_and_expired_lease() -> None:
    with postgres_cluster() as dsn:
        tenant = "60000000-0000-4000-8000-000000000001"
        run_id = "60000000-0000-4000-8000-000000000002"
        input_digest = "e" * 64
        lease_hash = hashlib.sha256(b"lease-token").hexdigest()
        jobs = [f"60000000-0000-4000-8000-{suffix:012d}" for suffix in range(3, 10)]
        job_rows = "".join(
            f"INSERT INTO hulagu.job_attempts(tenant_id,id,run_id,attempt,immutable_input_digest,lifecycle_epoch,work_epoch,state) "
            f"VALUES('{tenant}','{job_id}','{run_id}',{attempt},'{input_digest}',3,4,'queued');"
            for attempt, job_id in enumerate(jobs, start=1)
        )
        psql(
            dsn,
            f"INSERT INTO hulagu.tenants(id,state,lifecycle_epoch) VALUES('{tenant}','READY',3);"
            f"INSERT INTO hulagu.search_runs(tenant_id,id,state,query_plan,budget,work_epoch) "
            f"VALUES('{tenant}','{run_id}','queued','{{}}','{{}}',4);"
            f"{job_rows}",
        )
        for job_id in jobs:
            assert scalar(
                dsn,
                f"SELECT job_id FROM hulagu_api.claim_job('{job_id}','{lease_hash}',60)",
                user="hulagu_runner",
            ) == job_id

        stale_calls = [
            (jobs[0], 99, input_digest, 3, 4),
            (jobs[1], 2, "f" * 64, 3, 4),
            (jobs[2], 3, input_digest, 2, 4),
            (jobs[3], 4, input_digest, 3, 5),
        ]
        for job_id, attempt, digest, lifecycle_epoch, work_epoch in stale_calls:
            assert scalar(
                dsn,
                f"SELECT hulagu_api.fail_job('{job_id}',{attempt},'{lease_hash}','{digest}',{lifecycle_epoch},{work_epoch})",
                user="hulagu_runner",
            ) == "f"

        psql(dsn, f"UPDATE hulagu.job_attempts SET lease_expires_at=now()-interval '1 second' WHERE id='{jobs[4]}'")
        assert scalar(
            dsn,
            f"SELECT hulagu_api.fail_job('{jobs[4]}',5,'{lease_hash}','{input_digest}',3,4)",
            user="hulagu_runner",
        ) == "f"
        psql(dsn, f"UPDATE hulagu.search_runs SET state='cancelled' WHERE id='{run_id}'")
        assert scalar(
            dsn,
            f"SELECT hulagu_api.fail_job('{jobs[5]}',6,'{lease_hash}','{input_digest}',3,4)",
            user="hulagu_runner",
        ) == "f"
        psql(dsn, f"UPDATE hulagu.search_runs SET state='queued' WHERE id='{run_id}'; UPDATE hulagu.tenants SET state='PAUSED' WHERE id='{tenant}'")
        assert scalar(
            dsn,
            f"SELECT hulagu_api.fail_job('{jobs[6]}',7,'{lease_hash}','{input_digest}',3,4)",
            user="hulagu_runner",
        ) == "f"
        assert psql(dsn, "SELECT count(*) FROM hulagu.job_attempts WHERE state <> 'claimed'").stdout.strip() == "0"
