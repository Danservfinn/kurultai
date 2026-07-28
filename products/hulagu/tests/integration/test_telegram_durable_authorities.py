from __future__ import annotations

import shutil
from pathlib import Path
from typing import Protocol, cast

from test_migrations import MIGRATIONS, load_migrator, postgres_cluster, psql


class MigratorProtocol(Protocol):
    MIGRATIONS_DIR: Path

    def migrate(self, dsn: str) -> int: ...


def enrollment_ingress_sql(
    update_id: int,
    *,
    subject: str = "a" * 64,
    nonce_hash: str = "c" * 64,
    callback_query_id: str | None = None,
    per_subject_limit: int = 2,
    global_limit: int = 3,
) -> str:
    callback_sql = "NULL" if callback_query_id is None else f"'{callback_query_id}'"
    return (
        "SELECT outcome || ':' || COALESCE(enrollment_id::text,'') "
        "FROM hulagu_api.admit_telegram_enrollment_ingress("
        f"7,{update_id},{callback_sql},{update_id + 1},'{subject}',repeat('b',64),"
        f"'telegram-consent-v1','{nonce_hash}',now()+interval '15 minutes',"
        f"now()+interval '1 day',{per_subject_limit},{global_limit},60)"
    )


def test_enrollment_ingress_dedupes_before_durable_rate_and_authority_mutation() -> None:
    with postgres_cluster() as dsn:
        first = psql(dsn, enrollment_ingress_sql(20), user="hulagu_app").stdout.strip()
        enrollment_id = first.removeprefix("enrollment_started:")
        assert enrollment_id and first == f"enrollment_started:{enrollment_id}"

        duplicate = psql(
            dsn,
            enrollment_ingress_sql(20, nonce_hash="d" * 64),
            user="hulagu_app",
        ).stdout.strip()
        assert duplicate == f"duplicate_update:{enrollment_id}"
        assert psql(
            dsn,
            "SELECT rate_count || ':' || consent_nonce_hash FROM hulagu.enrollments",
        ).stdout.strip() == f"1:{'c' * 64}"

        outcomes = [
            psql(dsn, enrollment_ingress_sql(update_id), user="hulagu_app").stdout.strip().split(":", 1)[0]
            for update_id in range(21, 25)
        ]
        assert outcomes == ["enrollment_resumed", "rate_limited", "rate_limited", "rate_limited"]
        assert psql(dsn, "SELECT rate_count FROM hulagu.enrollments").stdout.strip() == "2"
        assert psql(
            dsn,
            "SELECT admitted_count FROM hulagu.telegram_preconsent_windows WHERE bot_id=7",
        ).stdout.strip() == "2"
        assert psql(dsn, "SELECT count(*) FROM hulagu.inbound_updates").stdout.strip() == "5"
        assert psql(
            dsn,
            "SELECT hulagu_api.telegram_polling_offset(7)",
            user="hulagu_app",
        ).stdout.strip() == "25"
        assert psql(dsn, "SELECT count(*) FROM hulagu.tenants").stdout.strip() == "0"
        assert psql(dsn, "SELECT count(*) FROM hulagu.outbox_messages").stdout.strip() == "0"


def test_outbox_delivery_claims_record_terminal_outcomes_and_cap_failed_attempts() -> None:
    tenant_id = "71000000-0000-4000-8000-000000000001"
    retry_id = "72000000-0000-4000-8000-000000000001"
    unknown_id = "72000000-0000-4000-8000-000000000002"
    delivered_id = "72000000-0000-4000-8000-000000000003"
    stale_id = "72000000-0000-4000-8000-000000000004"
    lease_one = "1" * 64
    lease_two = "2" * 64

    def app_sql(dsn: str, sql: str) -> str:
        return psql(
            dsn,
            f"BEGIN; SET LOCAL app.tenant_id='{tenant_id}'; {sql}; COMMIT;",
            user="hulagu_app",
        ).stdout.strip()

    def claim(dsn: str, lease_hash: str) -> list[str]:
        return app_sql(
            dsn,
            "SELECT outbox_id || '|' || delivery_key || '|' || attempt || '|' || "
            "lifecycle_epoch || '|' || work_epoch "
            f"FROM hulagu_api.claim_outbox_delivery('{lease_hash}',10,60) ORDER BY outbox_id",
        ).splitlines()

    def record(dsn: str, message_id: str, attempt: int, lease_hash: str, outcome: str) -> str:
        error_class = "NULL" if outcome == "delivered" else "'synthetic_transport_failure'"
        return app_sql(
            dsn,
            "SELECT hulagu_api.record_outbox_delivery("
            f"'{message_id}',{attempt},'{lease_hash}',4,0,'{outcome}',{error_class})",
        )

    with postgres_cluster() as dsn:
        psql(
            dsn,
            f"INSERT INTO hulagu.tenants(id,state,lifecycle_epoch) VALUES('{tenant_id}','READY',4);"
            "INSERT INTO hulagu.outbox_messages("
            "tenant_id,id,kind,payload,lifecycle_epoch,work_epoch,state,delivery_key,max_attempts"
            ") VALUES "
            f"('{tenant_id}','{retry_id}','ordinary','{{}}',4,0,'pending','stable:retry',2),"
            f"('{tenant_id}','{unknown_id}','ordinary','{{}}',4,0,'pending','stable:unknown',2),"
            f"('{tenant_id}','{delivered_id}','ordinary','{{}}',4,0,'pending','stable:delivered',2),"
            f"('{tenant_id}','{stale_id}','ordinary','{{}}',3,0,'pending','stable:stale',2);",
        )

        assert claim(dsn, lease_one) == [
            f"{retry_id}|stable:retry|1|4|0",
            f"{unknown_id}|stable:unknown|1|4|0",
            f"{delivered_id}|stable:delivered|1|4|0",
        ]
        assert claim(dsn, "9" * 64) == []
        assert psql(
            dsn,
            f"SELECT state FROM hulagu.outbox_messages WHERE id='{stale_id}'",
        ).stdout.strip() == "cancelled"

        assert record(dsn, retry_id, 1, lease_one, "failed") == "failed"
        assert record(dsn, unknown_id, 1, lease_one, "delivery_unknown") == "delivery_unknown"
        assert record(dsn, delivered_id, 1, lease_one, "delivered") == "delivered"

        assert claim(dsn, lease_two) == [f"{retry_id}|stable:retry|2|4|0"]
        assert record(dsn, retry_id, 2, lease_two, "failed") == "failed"
        assert claim(dsn, "3" * 64) == []
        assert psql(
            dsn,
            "SELECT delivery_key || ':' || state || ':' || attempt_count FROM "
            "hulagu.outbox_messages ORDER BY delivery_key",
        ).stdout.splitlines() == [
            "stable:delivered:delivered:1",
            "stable:retry:failed:2",
            "stable:stale:cancelled:0",
            "stable:unknown:delivery_unknown:1",
        ]


def test_stale_record_cannot_cancel_claimed_nonordinary_or_mismatched_work() -> None:
    tenant_id = "71000000-0000-4000-8000-000000000011"
    deletion_id = "72000000-0000-4000-8000-000000000011"
    ordinary_id = "72000000-0000-4000-8000-000000000012"
    lease_hash = "a" * 64

    with postgres_cluster() as dsn:
        psql(
            dsn,
            f"INSERT INTO hulagu.tenants(id,state,lifecycle_epoch) VALUES('{tenant_id}','PAUSED',5);"
            "INSERT INTO hulagu.outbox_messages("
            "tenant_id,id,kind,payload,lifecycle_epoch,work_epoch,state,delivery_key,"
            "attempt_count,lease_token_hash,lease_expires_at"
            ") VALUES "
            f"('{tenant_id}','{deletion_id}','deletion_control','{{}}',4,9,'claimed','stable:delete',"
            f"1,'{lease_hash}',now()+interval '1 minute'),"
            f"('{tenant_id}','{ordinary_id}','ordinary','{{}}',4,9,'claimed','stable:ordinary',"
            f"1,'{lease_hash}',now()+interval '1 minute');",
        )

        def record(message_id: str, work_epoch: int) -> str:
            return psql(
                dsn,
                "BEGIN; "
                f"SET LOCAL app.tenant_id='{tenant_id}'; "
                "SELECT hulagu_api.record_outbox_delivery("
                f"'{message_id}',1,'{lease_hash}',4,{work_epoch},'failed','synthetic'); COMMIT;",
                user="hulagu_app",
            ).stdout.strip()

        assert record(deletion_id, 9) == "rejected"
        assert record(ordinary_id, 8) == "rejected"
        assert psql(
            dsn,
            "SELECT delivery_key || ':' || kind || ':' || state || ':' || work_epoch "
            "FROM hulagu.outbox_messages ORDER BY delivery_key",
        ).stdout.splitlines() == [
            "stable:delete:deletion_control:claimed:9",
            "stable:ordinary:ordinary:claimed:9",
        ]


def test_global_preconsent_limit_and_callback_replay_are_durable_across_connections() -> None:
    with postgres_cluster() as dsn:
        first_subject = "a" * 64
        second_subject = "d" * 64
        assert psql(
            dsn,
            enrollment_ingress_sql(
                1,
                subject=first_subject,
                callback_query_id="callback-1",
                per_subject_limit=10,
                global_limit=1,
            ),
            user="hulagu_app",
        ).stdout.strip().startswith("enrollment_started:")
        rate_before = psql(dsn, "SELECT rate_count FROM hulagu.enrollments").stdout.strip()

        callback_replay = psql(
            dsn,
            enrollment_ingress_sql(
                2,
                subject=second_subject,
                nonce_hash="e" * 64,
                callback_query_id="callback-1",
                per_subject_limit=10,
                global_limit=1,
            ),
            user="hulagu_app",
        ).stdout.strip()
        assert callback_replay.startswith("duplicate_callback:")
        assert psql(dsn, "SELECT rate_count FROM hulagu.enrollments").stdout.strip() == rate_before

        globally_limited = psql(
            dsn,
            enrollment_ingress_sql(
                3,
                subject=second_subject,
                nonce_hash="e" * 64,
                per_subject_limit=10,
                global_limit=1,
            ),
            user="hulagu_app",
        ).stdout.strip()
        assert globally_limited == "rate_limited:"
        assert psql(dsn, "SELECT count(*) FROM hulagu.enrollments").stdout.strip() == "1"
        assert psql(dsn, "SELECT count(*) FROM hulagu.inbound_updates").stdout.strip() == "2"
        assert psql(
            dsn,
            "SELECT hulagu_api.telegram_polling_offset(7)",
            user="hulagu_app",
        ).stdout.strip() == "4"


def test_runtime_authorities_roll_back_and_expose_only_exact_app_grants() -> None:
    with postgres_cluster() as dsn:
        psql(
            dsn,
            f"BEGIN; {enrollment_ingress_sql(9)}; ROLLBACK;",
            user="hulagu_app",
        )
        assert psql(dsn, "SELECT count(*) FROM hulagu.enrollments").stdout.strip() == "0"
        assert psql(dsn, "SELECT count(*) FROM hulagu.inbound_updates").stdout.strip() == "0"
        assert psql(dsn, "SELECT count(*) FROM hulagu.telegram_polling_offsets").stdout.strip() == "0"
        assert psql(dsn, "SELECT count(*) FROM hulagu.telegram_preconsent_windows").stdout.strip() == "0"

        routines = psql(
            dsn,
            "SELECT p.proname || ':' || pg_get_userbyid(p.proowner) || ':' || "
            "array_to_string(p.proconfig, ',') || ':' || "
            "has_function_privilege('public',p.oid,'EXECUTE') || ':' || "
            "has_function_privilege('hulagu_app',p.oid,'EXECUTE') || ':' || "
            "has_function_privilege('hulagu_runner',p.oid,'EXECUTE') || ':' || "
            "has_function_privilege('hulagu_deletion',p.oid,'EXECUTE') "
            "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE n.nspname='hulagu_api' AND p.proname IN "
            "('admit_telegram_enrollment_ingress','claim_outbox_delivery','record_outbox_delivery') "
            "ORDER BY p.proname",
        ).stdout.splitlines()
        assert routines == [
            "admit_telegram_enrollment_ingress:hulagu_owner:search_path=pg_catalog:false:true:false:false",
            "claim_outbox_delivery:hulagu_owner:search_path=pg_catalog:false:true:false:false",
            "record_outbox_delivery:hulagu_owner:search_path=pg_catalog:false:true:false:false",
        ]
        assert psql(
            dsn,
            "SELECT count(*) FROM information_schema.role_table_grants WHERE grantee IN "
            "('hulagu_app','hulagu_runner','hulagu_deletion') AND table_schema='hulagu' "
            "AND table_name='telegram_preconsent_windows'",
        ).stdout.strip() == "0"


def test_forward_upgrade_normalizes_legacy_sent_outbox_rows(tmp_path: Path) -> None:
    first_ten = tmp_path / "migrations"
    first_ten.mkdir()
    for path in sorted(MIGRATIONS.glob("*.sql"))[:10]:
        shutil.copyfile(path, first_ten / path.name)

    with postgres_cluster(migrate=False) as dsn:
        migrator = cast(MigratorProtocol, load_migrator())
        migrator.MIGRATIONS_DIR = first_ten
        assert migrator.migrate(dsn) == 10
        tenant_id = "73000000-0000-4000-8000-000000000001"
        psql(
            dsn,
            f"INSERT INTO hulagu.tenants(id,state) VALUES('{tenant_id}','READY');"
            "INSERT INTO hulagu.outbox_messages("
            "tenant_id,kind,payload,lifecycle_epoch,work_epoch,state,delivery_key"
            f") VALUES('{tenant_id}','ordinary','{{}}',0,0,'sent','legacy:sent'),"
            f"('{tenant_id}','ordinary','{{}}',0,0,'claimed','legacy:unleased-claim');",
        )

        migrator.MIGRATIONS_DIR = MIGRATIONS
        assert migrator.migrate(dsn) == 3
        assert psql(
            dsn,
            "SELECT state || ':' || attempt_count || ':' || max_attempts || ':' || "
            "(delivered_at IS NOT NULL) FROM hulagu.outbox_messages ORDER BY delivery_key",
        ).stdout.splitlines() == [
            "delivered:0:3:true",
            "pending:0:3:false",
        ]
