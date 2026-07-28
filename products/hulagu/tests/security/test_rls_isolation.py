from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "integration"))

from test_migrations import postgres_cluster, psql

TENANT_A = "00000000-0000-4000-8000-00000000000a"
TENANT_B = "00000000-0000-4000-8000-00000000000b"
PROFILE_A = "10000000-0000-4000-8000-00000000000a"
PROFILE_B = "10000000-0000-4000-8000-00000000000b"
RUN_B = "20000000-0000-4000-8000-00000000000b"


def seed_two_tenants(dsn: str) -> None:
    psql(
        dsn,
        f"INSERT INTO hulagu.tenants(id,state) VALUES ('{TENANT_A}','READY'),('{TENANT_B}','READY');"
        f"INSERT INTO hulagu.customer_profiles(tenant_id,id,profile_version,profile_json,state) VALUES "
        f"('{TENANT_A}','{PROFILE_A}',1,'{{}}','confirmed'),('{TENANT_B}','{PROFILE_B}',1,'{{}}','confirmed');"
        f"INSERT INTO hulagu.search_runs(tenant_id,id,state,query_plan,budget,work_epoch) VALUES "
        f"('{TENANT_B}','{RUN_B}','queued','{{}}','{{}}',0);",
    )


def app_sql(dsn: str, sql: str, *, check: bool = True):
    return psql(
        dsn,
        f"BEGIN; SET LOCAL app.tenant_id='{TENANT_A}'; SET LOCAL app.actor='telegram-customer'; "
        f"SET LOCAL app.correlation_id='security-test'; {sql}; COMMIT;",
        user="hulagu_app",
        check=check,
    )


def test_missing_context_and_forged_ids_cannot_cross_rls_or_composite_fks() -> None:
    with postgres_cluster() as dsn:
        seed_two_tenants(dsn)
        assert psql(dsn, "SELECT count(*) FROM hulagu.customer_profiles", user="hulagu_app").stdout.strip() == "0"
        assert app_sql(dsn, "SELECT count(*) FROM hulagu.customer_profiles").stdout.strip() == "1"
        assert app_sql(dsn, f"SELECT count(*) FROM hulagu.customer_profiles WHERE id='{PROFILE_B}'").stdout.strip() == "0"
        assert app_sql(dsn, f"UPDATE hulagu.customer_profiles SET state='draft' WHERE id='{PROFILE_B}' RETURNING id").stdout.strip() == ""
        forged = app_sql(
            dsn,
            f"INSERT INTO hulagu.search_candidates(tenant_id,id,run_id,listing_key,evidence) "
            f"VALUES ('{TENANT_A}',gen_random_uuid(),'{RUN_B}','forged','{{}}')",
            check=False,
        )
        assert forged.returncode != 0


def test_tenant_storage_references_are_confined_and_cross_tenant_outbox_is_hidden() -> None:
    with postgres_cluster() as dsn:
        seed_two_tenants(dsn)
        bad = app_sql(
            dsn,
            f"INSERT INTO hulagu.source_documents(tenant_id,id,digest,parser_state,retention_state,storage_ref) "
            f"VALUES ('{TENANT_A}',gen_random_uuid(),repeat('a',64),'pending','active','/tenants/{TENANT_B}/cv.pdf')",
            check=False,
        )
        assert bad.returncode != 0
        psql(
            dsn,
            f"INSERT INTO hulagu.outbox_messages(tenant_id,id,kind,payload,lifecycle_epoch,work_epoch,state,delivery_key) "
            f"VALUES ('{TENANT_B}',gen_random_uuid(),'ordinary','{{}}',0,0,'pending','security-test:cross-tenant')",
        )
        assert app_sql(dsn, "SELECT count(*) FROM hulagu.outbox_messages").stdout.strip() == "0"


def test_outbox_and_retention_claims_derive_authority_from_installed_context() -> None:
    with postgres_cluster() as dsn:
        seed_two_tenants(dsn)
        outbox_a = "30000000-0000-4000-8000-00000000000a"
        outbox_b = "30000000-0000-4000-8000-00000000000b"
        retention_a = "40000000-0000-4000-8000-00000000000a"
        retention_b = "40000000-0000-4000-8000-00000000000b"
        psql(
            dsn,
            f"INSERT INTO hulagu.outbox_messages(tenant_id,id,kind,payload,lifecycle_epoch,work_epoch,state,delivery_key) VALUES "
            f"('{TENANT_A}','{outbox_a}','ordinary','{{}}',0,0,'pending','security-test:claim-a'),"
            f"('{TENANT_B}','{outbox_b}','ordinary','{{}}',0,0,'pending','security-test:claim-b');"
            f"INSERT INTO hulagu.retention_jobs(tenant_id,id,scope,state,lifecycle_epoch) VALUES "
            f"('{TENANT_A}','{retention_a}','receipt','pending',0),"
            f"('{TENANT_B}','{retention_b}','receipt','pending',0);",
        )
        outbox = app_sql(dsn, "SELECT hulagu_api.claim_outbox(10)").stdout.splitlines()
        retention = app_sql(dsn, "SELECT hulagu_api.claim_retention(10)").stdout.splitlines()
        assert outbox == [outbox_a]
        assert retention == [retention_a]
        forged = app_sql(dsn, f"SELECT hulagu_api.claim_outbox('{TENANT_B}',10)", check=False)
        assert forged.returncode != 0


def test_telegram_ingress_authority_rejects_forged_subject_and_search_path_shadowing() -> None:
    with postgres_cluster() as dsn:
        psql(
            dsn,
            "CREATE SCHEMA attacker;"
            "CREATE TABLE attacker.telegram_polling_offsets(bot_id bigint,next_update_id bigint);"
            "INSERT INTO attacker.telegram_polling_offsets VALUES(7,999);",
        )
        assert psql(
            dsn,
            "SET search_path=attacker,public; SELECT hulagu_api.telegram_polling_offset(7)",
            user="hulagu_app",
        ).stdout.strip() == "0"

        forged = psql(
            dsn,
            "SELECT hulagu_api.persist_telegram_ingress("
            "7,1,NULL,2,repeat('9',64),'processed',now()+interval '1 day')",
            user="hulagu_app",
            check=False,
        )
        assert forged.returncode != 0
        assert psql(dsn, "SELECT count(*) FROM hulagu.inbound_updates").stdout.strip() == "0"
        assert psql(dsn, "SELECT count(*) FROM hulagu.telegram_polling_offsets").stdout.strip() == "0"
        assert psql(
            dsn,
            "SELECT count(*) FROM information_schema.role_table_grants WHERE grantee='hulagu_app' "
            "AND table_schema='hulagu' AND table_name IN "
            "('enrollments','identity_bindings','inbound_updates','telegram_polling_offsets')",
        ).stdout.strip() == "0"
