from __future__ import annotations

import hashlib

from test_migrations import postgres_cluster, psql


def create_persisted_start(dsn: str, *, subject: str = "a" * 64, bot_id: int = 7) -> str:
    enrollment_id = psql(
        dsn,
        "SELECT hulagu_api.resolve_enrollment("
        f"'{subject}',repeat('b',64),'notice-v1',repeat('c',64),now()+interval '15 minutes')",
        user="hulagu_app",
    ).stdout.strip()
    assert psql(
        dsn,
        "SELECT hulagu_api.persist_telegram_ingress("
        f"{bot_id},1,NULL,2,'{subject}','enrollment_started',now()+interval '1 day')",
        user="hulagu_app",
    ).stdout.strip() == "recorded"
    return enrollment_id


def test_persisted_start_reference_transitions_atomically_to_promoted_tenant() -> None:
    with postgres_cluster() as dsn:
        subject = "a" * 64
        enrollment_id = create_persisted_start(dsn, subject=subject)

        tenant_id = psql(
            dsn,
            f"SELECT hulagu_api.promote_consented_enrollment('{enrollment_id}','notice-v1',repeat('c',64))",
            user="hulagu_app",
        ).stdout.strip()

        assert tenant_id
        assert psql(
            dsn,
            "SELECT outcome_class || ':' || (enrollment_id IS NULL) || ':' || (tenant_id IS NOT NULL) "
            "FROM hulagu.inbound_updates WHERE bot_id=7 AND update_id=1",
        ).stdout.strip() == "enrollment_started:true:true"
        assert psql(dsn, "SELECT count(*) FROM hulagu.enrollments").stdout.strip() == "0"


def test_invalid_nonce_leaves_persisted_start_and_offset_unchanged() -> None:
    with postgres_cluster() as dsn:
        enrollment_id = create_persisted_start(dsn)

        rejected = psql(
            dsn,
            f"SELECT hulagu_api.promote_consented_enrollment('{enrollment_id}','notice-v1',repeat('d',64))",
            user="hulagu_app",
            check=False,
        )

        assert rejected.returncode != 0
        assert psql(dsn, "SELECT count(*) FROM hulagu.tenants").stdout.strip() == "0"
        assert psql(
            dsn,
            "SELECT (enrollment_id IS NOT NULL) || ':' || (tenant_id IS NULL) "
            "FROM hulagu.inbound_updates WHERE bot_id=7 AND update_id=1",
        ).stdout.strip() == "true:true"
        assert psql(
            dsn,
            "SELECT hulagu_api.telegram_polling_offset(7)",
            user="hulagu_app",
        ).stdout.strip() == "2"


def test_later_transaction_failure_rolls_back_reference_transition() -> None:
    with postgres_cluster() as dsn:
        enrollment_id = create_persisted_start(dsn)

        failed = psql(
            dsn,
            "BEGIN;"
            f"SELECT hulagu_api.promote_consented_enrollment('{enrollment_id}','notice-v1',repeat('c',64));"
            "SELECT 1/0;"
            "COMMIT;",
            user="hulagu_app",
            check=False,
        )

        assert failed.returncode != 0
        assert psql(dsn, "SELECT count(*) FROM hulagu.tenants").stdout.strip() == "0"
        assert psql(dsn, "SELECT count(*) FROM hulagu.enrollments").stdout.strip() == "1"
        assert psql(
            dsn,
            "SELECT (enrollment_id IS NOT NULL) || ':' || (tenant_id IS NULL) "
            "FROM hulagu.inbound_updates WHERE bot_id=7 AND update_id=1",
        ).stdout.strip() == "true:true"


def test_promoted_start_and_duplicate_callback_keep_one_tenant_reference_and_effect() -> None:
    with postgres_cluster() as dsn:
        subject = "a" * 64
        enrollment_id = create_persisted_start(dsn, subject=subject)
        tenant_id = psql(
            dsn,
            f"SELECT hulagu_api.promote_consented_enrollment('{enrollment_id}','notice-v1',repeat('c',64))",
            user="hulagu_app",
        ).stdout.strip()
        first_callback = (
            "SELECT hulagu_api.persist_telegram_ingress("
            f"7,2,'consent-callback',3,'{subject}','consent_promoted',now()+interval '1 day',"
            "'consent:event-1','ordinary','{}'::jsonb)"
        )
        assert psql(dsn, first_callback, user="hulagu_app").stdout.strip() == "recorded"
        assert psql(
            dsn,
            "SELECT hulagu_api.persist_telegram_ingress("
            f"7,3,'consent-callback',4,'{subject}','consent_promoted',now()+interval '1 day',"
            "'consent:event-2','ordinary','{}'::jsonb)",
            user="hulagu_app",
        ).stdout.strip() == "duplicate_callback"

        assert psql(
            dsn,
            f"SELECT count(*) FROM hulagu.inbound_updates WHERE tenant_id='{tenant_id}' AND enrollment_id IS NULL",
        ).stdout.strip() == "2"
        assert psql(dsn, "SELECT count(*) FROM hulagu.outbox_messages").stdout.strip() == "1"
        assert psql(
            dsn,
            "SELECT hulagu_api.telegram_polling_offset(7)",
            user="hulagu_app",
        ).stdout.strip() == "4"


def test_deletion_terminalizes_promoted_start_before_tenant_erasure() -> None:
    with postgres_cluster() as dsn:
        enrollment_id = create_persisted_start(dsn)
        tenant_id = psql(
            dsn,
            f"SELECT hulagu_api.promote_consented_enrollment('{enrollment_id}','notice-v1',repeat('c',64))",
            user="hulagu_app",
        ).stdout.strip()
        deletion_id = psql(
            dsn,
            "BEGIN;"
            f"SET LOCAL app.tenant_id='{tenant_id}';"
            "SET LOCAL app.actor='telegram-customer';"
            "SET LOCAL app.correlation_id='delete-promoted-start';"
            "SELECT hulagu_api.request_deletion('ciphertext','route-binding-v1');"
            "COMMIT;",
            user="hulagu_app",
        ).stdout.strip()
        token = "delete-token"
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        assert psql(
            dsn,
            f"SELECT hulagu_api.claim_deletion_delivery('{deletion_id}','{token_hash}')",
            user="hulagu_deletion",
        ).stdout.strip() == "ciphertext"

        assert psql(
            dsn,
            f"SELECT hulagu_api.finalize_deletion('{deletion_id}','{token}')",
            user="hulagu_deletion",
        ).stdout.strip() == "t"
        assert psql(dsn, "SELECT count(*) FROM hulagu.tenants").stdout.strip() == "0"
        assert psql(
            dsn,
            "SELECT outcome_class || ':' || (enrollment_id IS NULL) || ':' || (tenant_id IS NULL) "
            "FROM hulagu.inbound_updates WHERE bot_id=7 AND update_id=1",
        ).stdout.strip() == "terminal_dedupe:true:true"
        assert psql(dsn, "SELECT count(*) FROM hulagu.deletion_receipts").stdout.strip() == "1"


def test_transition_routines_keep_fixed_search_path_and_exact_runtime_grants() -> None:
    with postgres_cluster() as dsn:
        rows = psql(
            dsn,
            "SELECT p.proname || ':' || pg_get_userbyid(p.proowner) || ':' || array_to_string(p.proconfig, ',') || ':' || "
            "has_function_privilege('public',p.oid,'EXECUTE') || ':' || "
            "has_function_privilege('hulagu_app',p.oid,'EXECUTE') || ':' || "
            "has_function_privilege('hulagu_deletion',p.oid,'EXECUTE') "
            "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE n.nspname='hulagu_api' AND p.proname IN "
            "('promote_consented_enrollment','finalize_deletion') ORDER BY p.proname",
        ).stdout.splitlines()

        assert rows == [
            "finalize_deletion:hulagu_owner:search_path=pg_catalog:false:false:true",
            "promote_consented_enrollment:hulagu_owner:search_path=pg_catalog:false:true:false",
        ]
