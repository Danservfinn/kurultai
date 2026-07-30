from __future__ import annotations

import getpass
import hashlib
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).parents[2]
MIGRATIONS = ROOT / "migrations"
MIGRATOR = ROOT / "deploy" / "scripts" / "migrate.py"
EXPECTED_MIGRATIONS = [
    "0001_roles_and_extensions.sql",
    "0002_tenants_and_identity.sql",
    "0003_profiles_documents_search.sql",
    "0004_wiki_outbox_receipts.sql",
    "0005_deletion_retention_global_control.sql",
    "0006_rls_policies.sql",
    "0007_security_definer_functions.sql",
    "0008_telegram_durability.sql",
    "0009_telegram_ingress_authority.sql",
    "0010_consent_reference_transition.sql",
    "0011_telegram_runtime_durability.sql",
    "0012_encrypted_ordinary_routes.sql",
    "0013_storage_quota_backup_coordination.sql",
    "0014_parser_job_queue.sql",
    "0015_deletion_single_use_tombstone_contract.sql",
    "0016_app_deletion_route_binding_lookup.sql",
]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def psql(dsn: str, sql: str, *, user: str | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    target = dsn if user is None else f"{dsn}&user={user}"
    return subprocess.run(
        ["/opt/homebrew/bin/psql", "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", target, "-c", sql],
        check=check,
        capture_output=True,
        text=True,
        timeout=30,
    )


def run_migrator(dsn: str, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "python", str(MIGRATOR), "--dsn", dsn],
        cwd=ROOT,
        check=check,
        capture_output=True,
        text=True,
        timeout=60,
    )


@contextmanager
def postgres_cluster(*, migrate: bool = True) -> Iterator[str]:
    base = Path(tempfile.mkdtemp(prefix="hulagu-pg-"))
    data = base / "data"
    port = _free_port()
    postgres_env = {**os.environ, "LC_ALL": "C"}
    subprocess.run(
        ["/opt/homebrew/bin/initdb", "-D", str(data), "--auth-local=trust", "--auth-host=trust", "--no-sync"],
        check=True,
        capture_output=True,
        env=postgres_env,
        text=True,
        timeout=30,
    )
    options = f"-h 127.0.0.1 -p {port} -F -c fsync=off -c synchronous_commit=off"
    try:
        subprocess.run(
            [
                "/opt/homebrew/bin/pg_ctl",
                "-D",
                str(data),
                "-l",
                str(base / "postgres.log"),
                "-o",
                options,
                "-w",
                "start",
            ],
            check=True,
            capture_output=True,
            env=postgres_env,
            text=True,
            timeout=30,
        )
        dsn = f"postgresql:///?host=127.0.0.1&port={port}&dbname=postgres&user={getpass.getuser()}"
        if migrate:
            run_migrator(dsn)
        yield dsn
    finally:
        subprocess.run(
            ["/opt/homebrew/bin/pg_ctl", "-D", str(data), "-m", "immediate", "-w", "stop"],
            check=False,
            capture_output=True,
            env=postgres_env,
            text=True,
            timeout=30,
        )
        shutil.rmtree(base, ignore_errors=True)


def load_migrator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("hulagu_migrate", MIGRATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exact_ordered_forward_only_migration_set_exists() -> None:
    assert MIGRATIONS.is_dir()
    assert sorted(path.name for path in MIGRATIONS.glob("*.sql")) == EXPECTED_MIGRATIONS
    assert all(" down " not in f" {path.read_text().lower()} " for path in MIGRATIONS.glob("*.sql"))


def test_migrations_apply_exactly_once_and_create_required_catalog() -> None:
    with postgres_cluster() as dsn:
        run_migrator(dsn)
        assert psql(dsn, "SELECT count(*) FROM public.hulagu_schema_migrations WHERE status = 'succeeded'").stdout.strip() == "16"
        required = {
            "tenants", "enrollments", "identity_bindings", "inbound_updates", "customer_profiles",
            "profile_answers", "source_documents", "search_runs", "job_attempts", "provider_requests",
            "search_candidates", "candidate_decisions", "wiki_publications", "outbox_messages", "receipts",
            "deletion_jobs", "deletion_tombstones", "deletion_receipts", "retention_jobs", "global_storage_state",
            "telegram_polling_offsets", "telegram_preconsent_windows", "tenant_storage_state",
            "tenant_storage_reservations", "backup_coordination", "backup_generations",
            "parser_jobs",
        }
        rows = psql(dsn, "SELECT tablename FROM pg_tables WHERE schemaname='hulagu'").stdout.splitlines()
        assert required <= set(rows)


def test_telegram_durability_schema_enforces_replay_offset_and_delivery_keys() -> None:
    with postgres_cluster() as dsn:
        tenant_a = "70000000-0000-4000-8000-00000000000a"
        tenant_b = "70000000-0000-4000-8000-00000000000b"
        enrollment = psql(
            dsn,
            "INSERT INTO hulagu.enrollments(subject_digest,subject_fence_digest,notice_version,consent_nonce_hash,expires_at) "
            "VALUES(repeat('a',64),repeat('b',64),'v1',repeat('c',64),now()+interval '1 hour') RETURNING id",
        ).stdout.strip()
        psql(
            dsn,
            f"INSERT INTO hulagu.inbound_updates(bot_id,update_id,callback_query_id,enrollment_id,outcome_class,expires_at) "
            f"VALUES(7,1,'callback-1','{enrollment}','processed',now()+interval '1 day')",
        )
        replay = psql(
            dsn,
            f"INSERT INTO hulagu.inbound_updates(bot_id,update_id,callback_query_id,enrollment_id,outcome_class,expires_at) "
            f"VALUES(7,2,'callback-1','{enrollment}','processed',now()+interval '1 day')",
            check=False,
        )
        assert replay.returncode != 0

        psql(dsn, "INSERT INTO hulagu.telegram_polling_offsets(bot_id,next_update_id) VALUES(7,2)")
        psql(dsn, "UPDATE hulagu.telegram_polling_offsets SET next_update_id=3 WHERE bot_id=7")
        assert psql(dsn, "SELECT next_update_id FROM hulagu.telegram_polling_offsets WHERE bot_id=7").stdout.strip() == "3"
        negative = psql(
            dsn,
            "INSERT INTO hulagu.telegram_polling_offsets(bot_id,next_update_id) VALUES(8,-1)",
            check=False,
        )
        assert negative.returncode != 0

        psql(
            dsn,
            f"INSERT INTO hulagu.tenants(id,state) VALUES('{tenant_a}','READY'),('{tenant_b}','READY');"
            f"INSERT INTO hulagu.outbox_messages(tenant_id,kind,payload,lifecycle_epoch,work_epoch,state,delivery_key) VALUES"
            f"('{tenant_a}','ordinary','{{}}',0,0,'pending','run-1:event-1'),"
            f"('{tenant_b}','ordinary','{{}}',0,0,'pending','run-1:event-1')",
        )
        duplicate = psql(
            dsn,
            f"INSERT INTO hulagu.outbox_messages(tenant_id,kind,payload,lifecycle_epoch,work_epoch,state,delivery_key) "
            f"VALUES('{tenant_a}','ordinary','{{}}',0,0,'pending','run-1:event-1')",
            check=False,
        )
        assert duplicate.returncode != 0
        assert psql(
            dsn,
            "SELECT count(*) FROM information_schema.role_table_grants WHERE grantee IN "
            "('hulagu_app','hulagu_runner','hulagu_deletion') AND table_schema='hulagu' "
            "AND table_name='telegram_polling_offsets'",
        ).stdout.strip() == "0"


def test_app_reads_only_its_bounded_bot_polling_offset_through_authority_function() -> None:
    with postgres_cluster() as dsn:
        psql(dsn, "INSERT INTO hulagu.telegram_polling_offsets(bot_id,next_update_id) VALUES(7,41),(8,99)")

        assert psql(
            dsn,
            "SELECT hulagu_api.telegram_polling_offset(7)",
            user="hulagu_app",
        ).stdout.strip() == "41"
        assert psql(
            dsn,
            "SELECT hulagu_api.telegram_polling_offset(9)",
            user="hulagu_app",
        ).stdout.strip() == "0"
        assert psql(
            dsn,
            "SELECT hulagu_api.telegram_polling_offset(0)",
            user="hulagu_app",
            check=False,
        ).returncode != 0
        assert psql(
            dsn,
            "SELECT count(*) FROM hulagu.telegram_polling_offsets",
            user="hulagu_app",
            check=False,
        ).returncode != 0


def test_app_atomically_persists_enrollment_ingress_and_polling_offset() -> None:
    with postgres_cluster() as dsn:
        subject = "a" * 64
        psql(
            dsn,
            "BEGIN;"
            "SELECT hulagu_api.resolve_enrollment("
            f"'{subject}',repeat('b',64),'notice-v1',repeat('c',64),now()+interval '15 minutes');"
            "SELECT hulagu_api.persist_telegram_ingress("
            f"7,41,NULL,42,'{subject}','enrollment_started',now()+interval '1 day');"
            "COMMIT;",
            user="hulagu_app",
        )

        assert psql(
            dsn,
            "SELECT bot_id || ':' || update_id || ':' || (enrollment_id IS NOT NULL) || ':' || (tenant_id IS NULL) "
            "FROM hulagu.inbound_updates",
        ).stdout.strip() == "7:41:true:true"
        assert psql(
            dsn,
            "SELECT hulagu_api.telegram_polling_offset(7)",
            user="hulagu_app",
        ).stdout.strip() == "42"


def test_consent_promotion_ingress_derives_tenant_and_writes_one_stable_outbox_effect() -> None:
    with postgres_cluster() as dsn:
        subject = "d" * 64
        enrollment_id = psql(
            dsn,
            "SELECT hulagu_api.resolve_enrollment("
            f"'{subject}',repeat('e',64),'notice-v1',repeat('f',64),now()+interval '15 minutes')",
            user="hulagu_app",
        ).stdout.strip()

        psql(
            dsn,
            "BEGIN;"
            f"SELECT hulagu_api.promote_consented_enrollment('{enrollment_id}','notice-v1',repeat('f',64));"
            "UPDATE hulagu.tenants SET lifecycle_epoch=3 WHERE id=current_setting('app.tenant_id')::uuid;"
            "SELECT hulagu_api.persist_telegram_ingress("
            f"7,42,'callback-1',43,'{subject}','consent_promoted',now()+interval '1 day',"
            "'run-1:event-1','ordinary','{\"event_id\":\"event-1\",\"sealed_route\":{"
            "\"active_key_version\":1,\"route_generation\":1,\"ciphertext\":\"cipher\","
            "\"active_wrapped_data_key\":\"wrapped\","
            "\"binding_digest\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\"}}'::jsonb);"
            "COMMIT;",
            user="hulagu_app",
        )

        assert psql(dsn, "SELECT count(*) FROM hulagu.tenants").stdout.strip() == "1"
        assert psql(dsn, "SELECT count(*) FROM hulagu.enrollments").stdout.strip() == "0"
        assert psql(
            dsn,
            "SELECT (tenant_id IS NOT NULL) || ':' || (enrollment_id IS NULL) "
            "FROM hulagu.inbound_updates WHERE bot_id=7 AND update_id=42",
        ).stdout.strip() == "true:true"
        assert psql(
            dsn,
            "SELECT delivery_key || ':' || state || ':' || lifecycle_epoch || ':' || work_epoch "
            "FROM hulagu.outbox_messages",
        ).stdout.strip() == "run-1:event-1:pending:3:0"
        assert psql(
            dsn,
            "SELECT hulagu_api.telegram_polling_offset(7)",
            user="hulagu_app",
        ).stdout.strip() == "43"


def test_confirmed_deletion_states_reject_ingress_and_roll_back_all_effects() -> None:
    with postgres_cluster() as dsn:
        for index, state in enumerate(("DELETE_PENDING", "DELETING"), start=1):
            tenant_id = f"70000000-0000-4000-8000-{index:012d}"
            subject = str(index) * 64
            bot_id = 20 + index
            psql(
                dsn,
                f"INSERT INTO hulagu.tenants(id,state,lifecycle_epoch) VALUES('{tenant_id}','{state}',8);"
                "INSERT INTO hulagu.identity_bindings(tenant_id,subject_digest,subject_fence_digest) "
                f"VALUES('{tenant_id}','{subject}',repeat('f',64));",
            )

            rejected = psql(
                dsn,
                "SELECT hulagu_api.persist_telegram_ingress("
                f"{bot_id},91,NULL,92,'{subject}','processed',now()+interval '1 day',"
                f"'deletion-fence-{index}','ordinary','{{}}'::jsonb)",
                user="hulagu_app",
                check=False,
            )

            assert rejected.returncode != 0
            assert psql(
                dsn,
                f"SELECT count(*) FROM hulagu.inbound_updates WHERE bot_id={bot_id}",
            ).stdout.strip() == "0"
            assert psql(
                dsn,
                f"SELECT count(*) FROM hulagu.outbox_messages WHERE tenant_id='{tenant_id}'",
            ).stdout.strip() == "0"
            assert psql(
                dsn,
                f"SELECT hulagu_api.telegram_polling_offset({bot_id})",
                user="hulagu_app",
            ).stdout.strip() == "0"


def test_duplicate_callback_after_deletion_state_leaves_all_effects_unchanged() -> None:
    with postgres_cluster() as dsn:
        for index, state in enumerate(("DELETE_PENDING", "DELETING"), start=1):
            tenant_id = f"70500000-0000-4000-8000-{index:012d}"
            subject = str(index + 3) * 64
            bot_id = 40 + index
            callback_id = f"deleted-callback-{index}"
            psql(
                dsn,
                f"INSERT INTO hulagu.tenants(id,state,lifecycle_epoch) VALUES('{tenant_id}','READY',8);"
                "INSERT INTO hulagu.identity_bindings(tenant_id,subject_digest,subject_fence_digest) "
                f"VALUES('{tenant_id}','{subject}',repeat('f',64));",
            )
            assert psql(
                dsn,
                "SELECT hulagu_api.persist_telegram_ingress("
                f"{bot_id},100,'{callback_id}',101,'{subject}','processed',now()+interval '1 day',"
                f"'deletion-replay-{index}:initial','ordinary','{{}}'::jsonb)",
                user="hulagu_app",
            ).stdout.strip() == "recorded"
            psql(
                dsn,
                f"UPDATE hulagu.tenants SET state='{state}', lifecycle_epoch=9 WHERE id='{tenant_id}'",
            )

            rejected = psql(
                dsn,
                "SELECT hulagu_api.persist_telegram_ingress("
                f"{bot_id},101,'{callback_id}',102,'{subject}','processed',now()+interval '1 day',"
                f"'deletion-replay-{index}:late','ordinary','{{}}'::jsonb)",
                user="hulagu_app",
                check=False,
            )

            assert rejected.returncode != 0
            assert psql(
                dsn,
                f"SELECT count(*) FROM hulagu.inbound_updates WHERE bot_id={bot_id}",
            ).stdout.strip() == "1"
            assert psql(
                dsn,
                f"SELECT count(*) FROM hulagu.outbox_messages WHERE tenant_id='{tenant_id}'",
            ).stdout.strip() == "1"
            assert psql(
                dsn,
                f"SELECT hulagu_api.telegram_polling_offset({bot_id})",
                user="hulagu_app",
            ).stdout.strip() == "101"


def test_duplicate_update_after_deletion_state_leaves_offset_row_unchanged() -> None:
    with postgres_cluster() as dsn:
        tenant_id = "70600000-0000-4000-8000-000000000001"
        subject = "6" * 64
        psql(
            dsn,
            f"INSERT INTO hulagu.tenants(id,state,lifecycle_epoch) VALUES('{tenant_id}','READY',8);"
            "INSERT INTO hulagu.identity_bindings(tenant_id,subject_digest,subject_fence_digest) "
            f"VALUES('{tenant_id}','{subject}',repeat('f',64));",
        )
        ingress_sql = (
            "SELECT hulagu_api.persist_telegram_ingress("
            f"46,100,NULL,101,'{subject}','processed',now()+interval '1 day',"
            "'deleted-update:initial','ordinary','{}'::jsonb)"
        )
        assert psql(dsn, ingress_sql, user="hulagu_app").stdout.strip() == "recorded"
        offset_row_before = psql(
            dsn,
            "SELECT next_update_id || ':' || xmin::text "
            "FROM hulagu.telegram_polling_offsets WHERE bot_id=46",
        ).stdout.strip()
        psql(
            dsn,
            f"UPDATE hulagu.tenants SET state='DELETING', lifecycle_epoch=9 WHERE id='{tenant_id}'",
        )

        rejected = psql(dsn, ingress_sql, user="hulagu_app", check=False)

        assert rejected.returncode != 0
        assert psql(dsn, "SELECT count(*) FROM hulagu.inbound_updates WHERE bot_id=46").stdout.strip() == "1"
        assert psql(
            dsn,
            f"SELECT count(*) FROM hulagu.outbox_messages WHERE tenant_id='{tenant_id}'",
        ).stdout.strip() == "1"
        assert psql(
            dsn,
            "SELECT next_update_id || ':' || xmin::text "
            "FROM hulagu.telegram_polling_offsets WHERE bot_id=46",
        ).stdout.strip() == offset_row_before


def test_concurrent_lifecycle_revocation_serializes_before_ingress_commit() -> None:
    with postgres_cluster() as dsn:
        tenant_id = "70000000-0000-4000-8000-000000000099"
        subject = "9" * 64
        psql(
            dsn,
            f"INSERT INTO hulagu.tenants(id,state,lifecycle_epoch) VALUES('{tenant_id}','READY',8);"
            "INSERT INTO hulagu.identity_bindings(tenant_id,subject_digest,subject_fence_digest) "
            f"VALUES('{tenant_id}','{subject}',repeat('f',64));",
        )
        revoker = subprocess.Popen(
            ["/opt/homebrew/bin/psql", "-X", "-q", "-A", "-t", dsn],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert revoker.stdin is not None and revoker.stdout is not None
        try:
            revoker.stdin.write(
                "BEGIN;"
                f"UPDATE hulagu.tenants SET state='DELETING', lifecycle_epoch=9 WHERE id='{tenant_id}';"
                "SELECT 'revoked';\n"
            )
            revoker.stdin.flush()
            while revoker.stdout.readline().strip() != "revoked":
                pass

            ingress_sql = (
                "/* ingress_lifecycle_fence_probe */ SELECT hulagu_api.persist_telegram_ingress("
                f"29,91,NULL,92,'{subject}','processed',now()+interval '1 day',"
                "'revocation-race','ordinary','{}'::jsonb)"
            )
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(psql, dsn, ingress_sql, user="hulagu_app", check=False)
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    waiters = psql(
                        dsn,
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE query LIKE '%ingress_lifecycle_fence_probe%' AND wait_event_type='Lock'",
                    ).stdout.strip()
                    if int(waiters) >= 1:
                        break
                    if future.done():
                        raise AssertionError("ingress bypassed the concurrent lifecycle fence")
                    time.sleep(0.05)
                else:
                    raise AssertionError("ingress did not reach the lifecycle serialization boundary")

                revoker.stdin.write("COMMIT; \\q\n")
                revoker.stdin.flush()
                rejected = future.result(timeout=10)
        finally:
            if revoker.poll() is None:
                revoker.kill()
            revoker.communicate(timeout=5)

        assert rejected.returncode != 0
        assert psql(dsn, "SELECT state || ':' || lifecycle_epoch FROM hulagu.tenants").stdout.strip() == "DELETING:9"
        assert psql(dsn, "SELECT count(*) FROM hulagu.inbound_updates WHERE bot_id=29").stdout.strip() == "0"
        assert psql(dsn, "SELECT count(*) FROM hulagu.outbox_messages").stdout.strip() == "0"
        assert psql(
            dsn,
            "SELECT hulagu_api.telegram_polling_offset(29)",
            user="hulagu_app",
        ).stdout.strip() == "0"


def test_duplicate_callback_serializes_with_concurrent_lifecycle_revocation() -> None:
    with postgres_cluster() as dsn:
        tenant_id = "70900000-0000-4000-8000-000000000099"
        subject = "8" * 64
        psql(
            dsn,
            f"INSERT INTO hulagu.tenants(id,state,lifecycle_epoch) VALUES('{tenant_id}','READY',8);"
            "INSERT INTO hulagu.identity_bindings(tenant_id,subject_digest,subject_fence_digest) "
            f"VALUES('{tenant_id}','{subject}',repeat('f',64));",
        )
        assert psql(
            dsn,
            "SELECT hulagu_api.persist_telegram_ingress("
            f"39,100,'revoked-callback',101,'{subject}','processed',now()+interval '1 day',"
            "'revoked-callback:initial','ordinary','{}'::jsonb)",
            user="hulagu_app",
        ).stdout.strip() == "recorded"

        revoker = subprocess.Popen(
            ["/opt/homebrew/bin/psql", "-X", "-q", "-A", "-t", dsn],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert revoker.stdin is not None and revoker.stdout is not None
        try:
            revoker.stdin.write(
                "BEGIN;"
                f"UPDATE hulagu.tenants SET state='DELETING', lifecycle_epoch=9 WHERE id='{tenant_id}';"
                "SELECT 'revoked';\n"
            )
            revoker.stdin.flush()
            while revoker.stdout.readline().strip() != "revoked":
                pass

            duplicate_sql = (
                "/* duplicate_callback_lifecycle_fence_probe */ "
                "SELECT hulagu_api.persist_telegram_ingress("
                f"39,101,'revoked-callback',102,'{subject}','processed',now()+interval '1 day',"
                "'revoked-callback:late','ordinary','{}'::jsonb)"
            )
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(psql, dsn, duplicate_sql, user="hulagu_app", check=False)
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    waiters = psql(
                        dsn,
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE query LIKE '%duplicate_callback_lifecycle_fence_probe%' "
                        "AND wait_event_type='Lock'",
                    ).stdout.strip()
                    if int(waiters) >= 1:
                        break
                    if future.done():
                        raise AssertionError("duplicate callback bypassed the concurrent lifecycle fence")
                    time.sleep(0.05)
                else:
                    raise AssertionError("duplicate callback did not reach the lifecycle serialization boundary")

                revoker.stdin.write("COMMIT; \\q\n")
                revoker.stdin.flush()
                rejected = future.result(timeout=10)
        finally:
            if revoker.poll() is None:
                revoker.kill()
            revoker.communicate(timeout=5)

        assert rejected.returncode != 0
        assert psql(dsn, "SELECT state || ':' || lifecycle_epoch FROM hulagu.tenants").stdout.strip() == "DELETING:9"
        assert psql(dsn, "SELECT count(*) FROM hulagu.inbound_updates WHERE bot_id=39").stdout.strip() == "1"
        assert psql(dsn, "SELECT count(*) FROM hulagu.outbox_messages").stdout.strip() == "1"
        assert psql(
            dsn,
            "SELECT hulagu_api.telegram_polling_offset(39)",
            user="hulagu_app",
        ).stdout.strip() == "101"


def test_update_and_callback_replays_are_harmless_and_advance_only_durable_offset() -> None:
    with postgres_cluster() as dsn:
        tenant_id = "71000000-0000-4000-8000-000000000001"
        subject = "1" * 64
        psql(
            dsn,
            f"INSERT INTO hulagu.tenants(id,state) VALUES('{tenant_id}','READY');"
            "INSERT INTO hulagu.identity_bindings(tenant_id,subject_digest,subject_fence_digest) "
            f"VALUES('{tenant_id}','{subject}',repeat('2',64));",
        )
        first_call = (
            "SELECT hulagu_api.persist_telegram_ingress("
            f"7,50,'callback-replay',51,'{subject}','processed',now()+interval '1 day',"
            "'run-2:event-1','ordinary','{}'::jsonb)"
        )
        assert psql(dsn, first_call, user="hulagu_app").stdout.strip() == "recorded"
        assert psql(dsn, first_call, user="hulagu_app").stdout.strip() == "duplicate_update"
        assert psql(
            dsn,
            "SELECT hulagu_api.persist_telegram_ingress("
            f"7,51,'callback-replay',52,'{subject}','processed',now()+interval '1 day',"
            "'run-2:event-2','ordinary','{}'::jsonb)",
            user="hulagu_app",
        ).stdout.strip() == "duplicate_callback"

        assert psql(dsn, "SELECT count(*) FROM hulagu.inbound_updates").stdout.strip() == "1"
        assert psql(dsn, "SELECT count(*) FROM hulagu.outbox_messages").stdout.strip() == "1"
        assert psql(
            dsn,
            "SELECT hulagu_api.telegram_polling_offset(7)",
            user="hulagu_app",
        ).stdout.strip() == "52"


def test_delivery_key_collision_rolls_back_ingress_and_offset_atomically() -> None:
    with postgres_cluster() as dsn:
        tenant_id = "72000000-0000-4000-8000-000000000001"
        subject = "3" * 64
        psql(
            dsn,
            f"INSERT INTO hulagu.tenants(id,state,lifecycle_epoch) VALUES('{tenant_id}','READY',4);"
            "INSERT INTO hulagu.identity_bindings(tenant_id,subject_digest,subject_fence_digest) "
            f"VALUES('{tenant_id}','{subject}',repeat('4',64));",
        )
        psql(
            dsn,
            "SELECT hulagu_api.persist_telegram_ingress("
            f"7,60,NULL,61,'{subject}','processed',now()+interval '1 day',"
            "'stable-event','ordinary','{\"event\":1}'::jsonb)",
            user="hulagu_app",
        )
        collision = psql(
            dsn,
            "SELECT hulagu_api.persist_telegram_ingress("
            f"7,61,NULL,62,'{subject}','processed',now()+interval '1 day',"
            "'stable-event','ordinary','{\"event\":2}'::jsonb)",
            user="hulagu_app",
            check=False,
        )
        assert collision.returncode != 0
        assert psql(dsn, "SELECT count(*) FROM hulagu.inbound_updates").stdout.strip() == "1"
        assert psql(dsn, "SELECT count(*) FROM hulagu.outbox_messages").stdout.strip() == "1"
        assert psql(
            dsn,
            "SELECT hulagu_api.telegram_polling_offset(7)",
            user="hulagu_app",
        ).stdout.strip() == "61"


def test_failed_ingress_rolls_back_consent_promotion_and_leaves_prior_offset() -> None:
    with postgres_cluster() as dsn:
        subject = "5" * 64
        enrollment_id = psql(
            dsn,
            "SELECT hulagu_api.resolve_enrollment("
            f"'{subject}',repeat('6',64),'notice-v1',repeat('7',64),now()+interval '15 minutes')",
            user="hulagu_app",
        ).stdout.strip()
        failed = psql(
            dsn,
            "BEGIN;"
            f"SELECT hulagu_api.promote_consented_enrollment('{enrollment_id}','notice-v1',repeat('7',64));"
            "SELECT hulagu_api.persist_telegram_ingress("
            f"7,70,NULL,71,'{subject}','consent_promoted',now()+interval '1 day',"
            "'stable-failure','deletion_completion','{}'::jsonb);"
            "COMMIT;",
            user="hulagu_app",
            check=False,
        )
        assert failed.returncode != 0
        assert psql(dsn, "SELECT count(*) FROM hulagu.enrollments").stdout.strip() == "1"
        assert psql(dsn, "SELECT count(*) FROM hulagu.tenants").stdout.strip() == "0"
        assert psql(dsn, "SELECT count(*) FROM hulagu.inbound_updates").stdout.strip() == "0"
        assert psql(dsn, "SELECT count(*) FROM hulagu.outbox_messages").stdout.strip() == "0"
        assert psql(
            dsn,
            "SELECT hulagu_api.telegram_polling_offset(7)",
            user="hulagu_app",
        ).stdout.strip() == "0"


def test_ingress_authority_accepts_no_tenant_or_epoch_authority_from_caller() -> None:
    with postgres_cluster() as dsn:
        arguments = psql(
            dsn,
            "SELECT pg_get_function_arguments(p.oid) FROM pg_proc AS p "
            "JOIN pg_namespace AS n ON n.oid=p.pronamespace "
            "WHERE n.nspname='hulagu_api' AND p.proname='persist_telegram_ingress'",
        ).stdout.strip()
        assert "tenant" not in arguments
        assert "lifecycle" not in arguments
        assert "work_epoch" not in arguments


def test_terminal_dedupe_advances_offset_without_identity_or_tenant_reference() -> None:
    with postgres_cluster() as dsn:
        assert psql(
            dsn,
            "SELECT hulagu_api.persist_telegram_ingress("
            "7,80,NULL,81,NULL,'terminal_dedupe',now()+interval '1 day')",
            user="hulagu_app",
        ).stdout.strip() == "recorded"
        assert psql(
            dsn,
            "SELECT enrollment_id IS NULL AND tenant_id IS NULL FROM hulagu.inbound_updates "
            "WHERE bot_id=7 AND update_id=80",
        ).stdout.strip() == "t"
        assert psql(
            dsn,
            "SELECT hulagu_api.telegram_polling_offset(7)",
            user="hulagu_app",
        ).stdout.strip() == "81"

        active_without_subject = psql(
            dsn,
            "SELECT hulagu_api.persist_telegram_ingress("
            "8,1,NULL,2,NULL,'processed',now()+interval '1 day')",
            user="hulagu_app",
            check=False,
        )
        assert active_without_subject.returncode != 0
        assert psql(
            dsn,
            "SELECT hulagu_api.telegram_polling_offset(8)",
            user="hulagu_app",
        ).stdout.strip() == "0"


def test_ordinary_outbox_schema_rejects_plaintext_routes_and_bounds_encrypted_envelopes() -> None:
    tenant_id = "73000000-0000-4000-8000-000000000001"
    with postgres_cluster() as dsn:
        psql(dsn, f"INSERT INTO hulagu.tenants(id,state) VALUES('{tenant_id}','READY')")
        plaintext = psql(
            dsn,
            "INSERT INTO hulagu.outbox_messages("
            "tenant_id,kind,payload,lifecycle_epoch,work_epoch,state,delivery_key"
            f") VALUES('{tenant_id}','ordinary',"
            "'{\"chat_id\":42,\"event_id\":\"event\",\"text\":\"text\"}',"
            "0,0,'pending','plaintext-route')",
            check=False,
        )
        assert plaintext.returncode != 0

        psql(
            dsn,
            "INSERT INTO hulagu.outbox_messages("
            "tenant_id,kind,payload,lifecycle_epoch,work_epoch,state,delivery_key"
            f") VALUES('{tenant_id}','ordinary',"
            "'{\"event_id\":\"event\",\"text\":\"text\",\"sealed_route\":{"
            "\"active_key_version\":1,\"route_generation\":1,"
            "\"ciphertext\":\"cipher\",\"active_wrapped_data_key\":\"wrapped\","
            "\"binding_digest\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\"}}',"
            "0,0,'pending','encrypted-route')",
        )


def test_runtime_roles_and_rls_catalog_fail_closed() -> None:
    with postgres_cluster() as dsn:
        role_rows = psql(
            dsn,
            "SELECT rolname || ':' || rolbypassrls || ':' || rolsuper || ':' || rolcreaterole "
            "FROM pg_roles WHERE rolname LIKE 'hulagu_%' ORDER BY rolname",
        ).stdout
        assert "hulagu_app:false:false:false" in role_rows
        assert "hulagu_runner:false:false:false" in role_rows
        assert "hulagu_deletion:false:false:false" in role_rows
        assert "hulagu_owner:true:false:false" in role_rows
        missing_force = psql(
            dsn,
            "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='hulagu' AND c.relname IN "
            "('tenants','identity_bindings','customer_profiles','profile_answers','source_documents','search_runs',"
            "'job_attempts','provider_requests','search_candidates','candidate_decisions','wiki_publications',"
            "'outbox_messages','receipts','retention_jobs','tenant_storage_state','tenant_storage_reservations',"
            "'parser_jobs') "
            "AND (NOT c.relrowsecurity OR NOT c.relforcerowsecurity)",
        ).stdout.strip()
        assert missing_force == "0"
        policies = psql(dsn, "SELECT count(*) FROM pg_policies WHERE schemaname='hulagu' AND qual IS NOT NULL AND with_check IS NOT NULL").stdout.strip()
        assert int(policies) >= 17


def test_security_definer_routines_are_hardened() -> None:
    with postgres_cluster() as dsn:
        rows = psql(
            dsn,
            "SELECT p.proname || '|' || pg_get_userbyid(p.proowner) || '|' || coalesce(array_to_string(p.proconfig, ','),'') || '|' || "
            "has_function_privilege('public', p.oid, 'EXECUTE') FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE n.nspname='hulagu_api' AND p.prosecdef ORDER BY p.proname",
        ).stdout.splitlines()
        assert rows
        assert all("|hulagu_owner|search_path=pg_catalog|f" in row for row in rows)
        definitions = psql(
            dsn,
            "SELECT pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE n.nspname='hulagu_api' AND p.prosecdef",
        ).stdout
        assert "hulagu." in definitions
        assert "EXECUTE " not in definitions.upper()


def _seed_single_use_deletion_tenant(dsn: str, tenant_id: str, *, epoch: int, nonce_hash: str) -> None:
    psql(
        dsn,
        f"INSERT INTO hulagu.tenants(id,state,lifecycle_epoch,deletion_nonce_hash) "
        f"VALUES('{tenant_id}','READY',{epoch},'{nonce_hash}');"
        "INSERT INTO hulagu.identity_bindings(tenant_id,subject_digest,subject_fence_digest) "
        f"VALUES('{tenant_id}',repeat('a',64),repeat('b',64));",
    )


def _request_deletion_sql(tenant_id: str, nonce_hash: str) -> str:
    return (
        "BEGIN;"
        f"SET LOCAL app.tenant_id='{tenant_id}';"
        f"SELECT hulagu_api.request_deletion('{nonce_hash}','encrypted-route-envelope',repeat('c',64));"
        "COMMIT;"
    )


def test_deletion_request_consumes_nonce_once_and_removes_two_argument_bypass() -> None:
    tenant_id = "74000000-0000-4000-8000-000000000001"
    nonce_hash = hashlib.sha256(b"single-use-deletion-nonce").hexdigest()
    with postgres_cluster() as dsn:
        _seed_single_use_deletion_tenant(dsn, tenant_id, epoch=7, nonce_hash=nonce_hash)

        assert psql(
            dsn,
            "SELECT pg_catalog.to_regprocedure('hulagu_api.request_deletion(text,text)') IS NULL",
        ).stdout.strip() == "t"
        assert psql(
            dsn,
            "SELECT pg_catalog.to_regprocedure('hulagu_api.request_deletion(text,text,text)') IS NOT NULL",
        ).stdout.strip() == "t"
        assert psql(
            dsn,
            f"BEGIN;SET LOCAL app.tenant_id='{tenant_id}';"
            "SELECT hulagu_api.request_deletion('encrypted-route-envelope',repeat('c',64));COMMIT;",
            user="hulagu_app",
            check=False,
        ).returncode != 0

        forged = psql(
            dsn,
            _request_deletion_sql(tenant_id, "0" * 64),
            user="hulagu_app",
            check=False,
        )
        assert forged.returncode != 0
        assert psql(
            dsn,
            f"SELECT state || ':' || lifecycle_epoch || ':' || (deletion_nonce_hash='{nonce_hash}') "
            f"FROM hulagu.tenants WHERE id='{tenant_id}'",
        ).stdout.strip() == "READY:7:true"

        deletion_id = psql(
            dsn,
            _request_deletion_sql(tenant_id, nonce_hash),
            user="hulagu_app",
        ).stdout.strip()
        assert deletion_id
        replay = psql(
            dsn,
            _request_deletion_sql(tenant_id, nonce_hash),
            user="hulagu_app",
            check=False,
        )
        assert replay.returncode != 0
        assert psql(
            dsn,
            f"SELECT state || ':' || lifecycle_epoch || ':' || (deletion_nonce_hash IS NULL) "
            f"FROM hulagu.tenants WHERE id='{tenant_id}'",
        ).stdout.strip() == "DELETING:8:true"
        assert psql(
            dsn,
            f"SELECT count(*) || ':' || bool_and(deletion_epoch=8) || ':' || "
            f"bool_and(encrypted_subject_digest LIKE 'hts1.%') || ':' || "
            f"bool_and(encrypted_subject_digest NOT LIKE '%' || repeat('b',64) || '%') "
            f"FROM hulagu.deletion_jobs WHERE target_tenant_id='{tenant_id}'",
        ).stdout.strip() == "1:true:true:true"

        direct_duplicate = psql(
            dsn,
            "INSERT INTO hulagu.deletion_jobs("
            "target_tenant_id,encrypted_subject_digest,deletion_epoch,encrypted_route,"
            "route_binding_digest,state,expires_at) "
            "SELECT target_tenant_id,encrypted_subject_digest,deletion_epoch,"
            "'other-route',repeat('d',64),'pending',now()+interval '1 day' "
            f"FROM hulagu.deletion_jobs WHERE deletion_id='{deletion_id}'",
            check=False,
        )
        assert direct_duplicate.returncode != 0
        assert "deletion_jobs_one_active_target_idx" in direct_duplicate.stderr

        privileges = psql(
            dsn,
            "SELECT has_function_privilege('public','hulagu_api.request_deletion(text,text,text)','EXECUTE') || ':' || "
            "has_function_privilege('hulagu_app','hulagu_api.request_deletion(text,text,text)','EXECUTE') || ':' || "
            "has_function_privilege('hulagu_deletion','hulagu_api.request_deletion(text,text,text)','EXECUTE')",
        ).stdout.strip()
        assert privileges == "false:true:false"
        assert psql(
            dsn,
            "SELECT count(*) FROM information_schema.role_table_grants "
            "WHERE grantee IN ('hulagu_app','hulagu_runner','hulagu_deletion','hulagu_readonly') "
            "AND table_schema='hulagu' "
            "AND table_name IN ('deletion_tombstones','tombstone_fence_keys')",
        ).stdout.strip() == "0"


def test_real_random_port_postgres_serializes_concurrent_deletion_requests() -> None:
    tenant_id = "74000000-0000-4000-8000-000000000002"
    nonce_hash = hashlib.sha256(b"concurrent-deletion-nonce").hexdigest()
    with postgres_cluster() as dsn:
        _seed_single_use_deletion_tenant(dsn, tenant_id, epoch=11, nonce_hash=nonce_hash)
        locker = subprocess.Popen(
            ["/opt/homebrew/bin/psql", "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", dsn],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert locker.stdin is not None and locker.stdout is not None
        try:
            locker.stdin.write(
                f"BEGIN; SELECT id FROM hulagu.tenants WHERE id='{tenant_id}' FOR UPDATE; SELECT 'locked';\n"
            )
            locker.stdin.flush()
            while locker.stdout.readline().strip() != "locked":
                pass

            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(
                        psql,
                        dsn,
                        _request_deletion_sql(tenant_id, nonce_hash),
                        user="hulagu_app",
                        check=False,
                    )
                    for _ in range(2)
                ]
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    waiters = psql(
                        dsn,
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE wait_event_type='Lock' AND query LIKE '%hulagu_api.request_deletion%'",
                    ).stdout.strip()
                    if int(waiters) >= 2:
                        break
                    time.sleep(0.05)
                else:
                    raise AssertionError("concurrent requests did not reach the tenant-row lock")

                locker.stdin.write("COMMIT; \\q\n")
                locker.stdin.flush()
                results = [future.result() for future in futures]
        finally:
            if locker.poll() is None:
                locker.kill()
            locker.communicate(timeout=5)

        assert sorted(result.returncode == 0 for result in results) == [False, True]
        assert psql(
            dsn,
            f"SELECT state || ':' || lifecycle_epoch FROM hulagu.tenants WHERE id='{tenant_id}'",
        ).stdout.strip() == "DELETING:12"
        assert psql(
            dsn,
            f"SELECT count(*) FROM hulagu.deletion_jobs WHERE target_tenant_id='{tenant_id}'",
        ).stdout.strip() == "1"


def test_deletion_claim_and_finalize_replay_create_one_terminal_effect() -> None:
    tenant_id = "74000000-0000-4000-8000-000000000003"
    nonce_hash = hashlib.sha256(b"terminal-deletion-nonce").hexdigest()
    delivery_token = "synthetic-terminal-delivery-token"
    delivery_token_hash = hashlib.sha256(delivery_token.encode()).hexdigest()
    erasure_token = "synthetic-terminal-erasure-token"
    erasure_token_hash = hashlib.sha256(erasure_token.encode()).hexdigest()
    with postgres_cluster() as dsn:
        _seed_single_use_deletion_tenant(dsn, tenant_id, epoch=2, nonce_hash=nonce_hash)
        deletion_id = psql(
            dsn,
            _request_deletion_sql(tenant_id, nonce_hash),
            user="hulagu_app",
        ).stdout.strip()

        assert psql(
            dsn,
            f"SELECT hulagu_api.claim_deletion_erasure('{deletion_id}','{erasure_token_hash}')",
            user="hulagu_deletion",
        ).stdout.strip() == tenant_id
        assert psql(
            dsn,
            f"SELECT hulagu_api.complete_deletion_erasure('{deletion_id}','{erasure_token}')",
            user="hulagu_deletion",
        ).stdout.strip() == "t"
        claimed = json.loads(
            psql(
                dsn,
                f"SELECT hulagu_api.claim_deletion_delivery('{deletion_id}','{delivery_token_hash}')",
                user="hulagu_deletion",
            ).stdout
        )
        assert claimed == {"status": "claimed", "encrypted_route": "encrypted-route-envelope"}
        assert psql(
            dsn,
            f"SELECT hulagu_api.claim_deletion_delivery('{deletion_id}','{delivery_token_hash}') IS NULL",
            user="hulagu_deletion",
        ).stdout.strip() == "f"

        assert psql(
            dsn,
            f"SELECT hulagu_api.complete_deletion_delivery('{deletion_id}','{delivery_token}','delivered')",
            user="hulagu_deletion",
        ).stdout.strip() == "delivered"
        assert psql(
            dsn,
            f"SELECT hulagu_api.finalize_deletion('{deletion_id}','{delivery_token}','failed')",
            user="hulagu_deletion",
        ).stdout.strip() == "delivered"
        assert psql(
            dsn,
            f"SELECT hulagu_api.complete_deletion_delivery('{deletion_id}','{delivery_token}','delivery_unknown')",
            user="hulagu_deletion",
        ).stdout.strip() == "delivered"

        assert psql(
            dsn,
            f"SELECT count(*) FROM hulagu.deletion_receipts WHERE deletion_id='{deletion_id}'",
        ).stdout.strip() == "1"
        assert psql(dsn, "SELECT count(*) FROM hulagu.deletion_tombstones").stdout.strip() == "1"
        assert psql(
            dsn,
            "SELECT string_agg(column_name,',' ORDER BY ordinal_position) "
            "FROM information_schema.columns "
            "WHERE table_schema='hulagu' AND table_name='deletion_tombstones'",
        ).stdout.strip() == (
            "schema_version,encrypted_subject_digest,deletion_epoch,completed_at,"
            "backup_expiry_horizon,rekey_state"
        )
        assert psql(
            dsn,
            f"SELECT state || ':' || (target_tenant_id IS NULL) || ':' || "
            f"(encrypted_route IS NULL) || ':' || (encrypted_subject_digest IS NULL) "
            f"FROM hulagu.deletion_jobs WHERE deletion_id='{deletion_id}'",
        ).stdout.strip() == "complete:true:true:true"
        assert psql(dsn, f"SELECT count(*) FROM hulagu.tenants WHERE id='{tenant_id}'").stdout.strip() == "0"

        blocked = psql(
            dsn,
            "SELECT hulagu_api.resolve_enrollment("
            "repeat('d',64),repeat('b',64),'notice-v1',repeat('e',64),now()+interval '10 minutes')",
            user="hulagu_app",
            check=False,
        )
        assert blocked.returncode != 0
        assert "re-enrollment barred" in blocked.stderr

        psql(
            dsn,
            "UPDATE hulagu.deletion_tombstones "
            "SET encrypted_subject_digest = "
            "left(encrypted_subject_digest,length(encrypted_subject_digest)-1) || "
            "CASE right(encrypted_subject_digest,1) WHEN 'A' THEN 'B' ELSE 'A' END",
        )
        tampered = psql(
            dsn,
            "SELECT hulagu_api.resolve_enrollment("
            "repeat('f',64),repeat('b',64),'notice-v1',repeat('e',64),now()+interval '10 minutes')",
            user="hulagu_app",
            check=False,
        )
        assert tampered.returncode != 0
        assert "invalid authenticated deletion tombstone" in tampered.stderr


def test_deletion_workflow_orders_erasure_before_claim_and_persists_exact_outcome() -> None:
    tenant_id = "74000000-0000-4000-8000-000000000004"
    nonce_hash = hashlib.sha256(b"ordered-deletion-nonce").hexdigest()
    erasure_token = "synthetic-erasure-token"
    erasure_token_hash = hashlib.sha256(erasure_token.encode()).hexdigest()
    delivery_token = "synthetic-delivery-token"
    delivery_token_hash = hashlib.sha256(delivery_token.encode()).hexdigest()
    with postgres_cluster() as dsn:
        _seed_single_use_deletion_tenant(dsn, tenant_id, epoch=4, nonce_hash=nonce_hash)
        deletion_id = psql(dsn, _request_deletion_sql(tenant_id, nonce_hash), user="hulagu_app").stdout.strip()
        assert psql(
            dsn,
            f"SELECT state FROM hulagu.deletion_jobs WHERE deletion_id='{deletion_id}'",
        ).stdout.strip() == "pending"
        assert psql(
            dsn,
            f"SELECT hulagu_api.claim_deletion_erasure('{deletion_id}','{erasure_token_hash}')",
            user="hulagu_deletion",
        ).stdout.strip() == tenant_id
        assert psql(
            dsn,
            f"SELECT hulagu_api.complete_deletion_erasure('{deletion_id}','{erasure_token}')",
            user="hulagu_deletion",
        ).stdout.strip() == "t"
        assert psql(
            dsn,
            f"SELECT state || ':' || (target_tenant_id IS NULL) FROM hulagu.deletion_jobs WHERE deletion_id='{deletion_id}'",
        ).stdout.strip() == "delivery_pending:true"

        claimed = json.loads(
            psql(
                dsn,
                f"SELECT hulagu_api.claim_deletion_delivery('{deletion_id}','{delivery_token_hash}')",
                user="hulagu_deletion",
            ).stdout
        )
        assert claimed == {"status": "claimed", "encrypted_route": "encrypted-route-envelope"}
        assert psql(
            dsn,
            f"SELECT encrypted_route IS NULL FROM hulagu.deletion_jobs WHERE deletion_id='{deletion_id}'",
        ).stdout.strip() == "t"
        assert psql(
            dsn,
            f"SELECT hulagu_api.complete_deletion_delivery('{deletion_id}','{delivery_token}','failed')",
            user="hulagu_deletion",
        ).stdout.strip() == "failed"
        assert psql(
            dsn,
            f"SELECT hulagu_api.deletion_delivery_outcome('{deletion_id}')",
            user="hulagu_deletion",
        ).stdout.strip() == "failed"
        assert psql(
            dsn,
            f"SELECT outcome FROM hulagu.deletion_receipts WHERE deletion_id='{deletion_id}'",
        ).stdout.strip() == "failed"


def test_app_role_reads_only_live_deletion_binding_through_bounded_function() -> None:
    tenant_id = "74000000-0000-4000-8000-000000000016"
    nonce_hash = hashlib.sha256(b"app-binding-lookup-nonce").hexdigest()
    erasure_token = "synthetic-app-binding-erasure-token"
    erasure_hash = hashlib.sha256(erasure_token.encode()).hexdigest()
    delivery_hash = hashlib.sha256(b"synthetic-app-binding-delivery-token").hexdigest()
    with postgres_cluster() as dsn:
        _seed_single_use_deletion_tenant(dsn, tenant_id, epoch=6, nonce_hash=nonce_hash)
        deletion_id = psql(dsn, _request_deletion_sql(tenant_id, nonce_hash), user="hulagu_app").stdout.strip()
        psql(
            dsn,
            f"SELECT hulagu_api.claim_deletion_erasure('{deletion_id}','{erasure_hash}');"
            f"SELECT hulagu_api.complete_deletion_erasure('{deletion_id}','{erasure_token}');"
            f"SELECT hulagu_api.claim_deletion_delivery('{deletion_id}','{delivery_hash}');",
            user="hulagu_deletion",
        )

        assert psql(
            dsn,
            f"SELECT route_key_version || '|' || route_binding_digest "
            f"FROM hulagu_api.app_deletion_route_binding('{deletion_id}')",
            user="hulagu_app",
        ).stdout.strip() == "1|" + "c" * 64
        assert psql(
            dsn,
            "SELECT count(*) FROM hulagu_api.app_deletion_route_binding("
            "'74000000-0000-4000-8000-000000000099')",
            user="hulagu_app",
        ).stdout.strip() == "0"
        privileges = psql(
            dsn,
            "SELECT has_function_privilege('public','hulagu_api.app_deletion_route_binding(uuid)','EXECUTE') || ':' || "
            "has_function_privilege('hulagu_app','hulagu_api.app_deletion_route_binding(uuid)','EXECUTE') || ':' || "
            "has_function_privilege('hulagu_runner','hulagu_api.app_deletion_route_binding(uuid)','EXECUTE') || ':' || "
            "has_function_privilege('hulagu_deletion','hulagu_api.app_deletion_route_binding(uuid)','EXECUTE') || ':' || "
            "has_function_privilege('hulagu_readonly','hulagu_api.app_deletion_route_binding(uuid)','EXECUTE')",
        ).stdout.strip()
        assert privileges == "false:true:false:false:false"
        assert psql(
            dsn,
            "SELECT count(*) FROM information_schema.role_table_grants "
            "WHERE grantee='hulagu_app' AND table_schema='hulagu' AND table_name='deletion_jobs'",
        ).stdout.strip() == "0"


def test_committed_delivery_claim_restarts_as_durable_unknown_without_second_projection() -> None:
    tenant_id = "74000000-0000-4000-8000-000000000005"
    nonce_hash = hashlib.sha256(b"restart-deletion-nonce").hexdigest()
    erasure_token = "synthetic-restart-erasure-token"
    erasure_hash = hashlib.sha256(erasure_token.encode()).hexdigest()
    delivery_token = "synthetic-restart-delivery-token"
    delivery_hash = hashlib.sha256(delivery_token.encode()).hexdigest()
    with postgres_cluster() as dsn:
        _seed_single_use_deletion_tenant(dsn, tenant_id, epoch=5, nonce_hash=nonce_hash)
        deletion_id = psql(dsn, _request_deletion_sql(tenant_id, nonce_hash), user="hulagu_app").stdout.strip()
        psql(
            dsn,
            f"SELECT hulagu_api.claim_deletion_erasure('{deletion_id}','{erasure_hash}');"
            f"SELECT hulagu_api.complete_deletion_erasure('{deletion_id}','{erasure_token}');",
            user="hulagu_deletion",
        )
        first = json.loads(
            psql(
                dsn,
                f"SELECT hulagu_api.claim_deletion_delivery('{deletion_id}','{delivery_hash}')",
                user="hulagu_deletion",
            ).stdout
        )
        restarted = json.loads(
            psql(
                dsn,
                f"SELECT hulagu_api.claim_deletion_delivery('{deletion_id}','{delivery_hash}')",
                user="hulagu_deletion",
            ).stdout
        )
        assert first["status"] == "claimed"
        assert restarted == {"status": "ambiguous"}
        assert psql(
            dsn,
            f"SELECT hulagu_api.complete_deletion_delivery('{deletion_id}','{delivery_token}','delivery_unknown')",
            user="hulagu_deletion",
        ).stdout.strip() == "delivery_unknown"
        assert psql(
            dsn,
            f"SELECT hulagu_api.complete_deletion_delivery('{deletion_id}','{delivery_token}','delivered')",
            user="hulagu_deletion",
        ).stdout.strip() == "delivery_unknown"


def test_0015_fails_closed_before_mutation_when_0014_deletion_is_active() -> None:
    with postgres_cluster(migrate=False) as dsn:
        migration_0015 = EXPECTED_MIGRATIONS.index("0015_deletion_single_use_tombstone_contract.sql")
        for filename in EXPECTED_MIGRATIONS[:migration_0015]:
            psql(dsn, (MIGRATIONS / filename).read_text())
        psql(
            dsn,
            "INSERT INTO hulagu.deletion_jobs(target_tenant_id,subject_fence_digest,encrypted_route,"
            "route_binding_digest,state,expires_at) VALUES"
            "('74000000-0000-4000-8000-000000000006',repeat('a',64),'route',repeat('b',64),"
            "'delivery_pending',now()+interval '1 day')",
        )
        result = psql(dsn, (MIGRATIONS / EXPECTED_MIGRATIONS[migration_0015]).read_text(), check=False)

        assert result.returncode != 0
        assert "active pre-0015 deletion jobs require authenticated completion" in result.stderr
        assert psql(
            dsn,
            "SELECT count(*) FROM information_schema.columns WHERE table_schema='hulagu' "
            "AND table_name='tenants' AND column_name='deletion_nonce_hash'",
        ).stdout.strip() == "0"


def test_0015_fails_closed_when_legacy_plaintext_tombstones_exist() -> None:
    with postgres_cluster(migrate=False) as dsn:
        migration_0015 = EXPECTED_MIGRATIONS.index("0015_deletion_single_use_tombstone_contract.sql")
        for filename in EXPECTED_MIGRATIONS[:migration_0015]:
            psql(dsn, (MIGRATIONS / filename).read_text())
        psql(
            dsn,
            "INSERT INTO hulagu.deletion_tombstones(subject_fence_digest,key_version,barred_until) "
            "VALUES(repeat('f',64),1,now()+interval '1 day')",
        )

        result = psql(
            dsn,
            (MIGRATIONS / EXPECTED_MIGRATIONS[migration_0015]).read_text(),
            check=False,
        )

        assert result.returncode != 0
        assert "unsafe legacy plaintext deletion tombstones" in result.stderr
        assert psql(
            dsn,
            "SELECT subject_fence_digest FROM hulagu.deletion_tombstones",
        ).stdout.strip() == "f" * 64


def test_no_ephemeral_cluster_leaks_from_helper() -> None:
    before = set(Path(tempfile.gettempdir()).glob("hulagu-pg-*"))
    with postgres_cluster():
        pass
    after = set(Path(tempfile.gettempdir()).glob("hulagu-pg-*"))
    assert after == before
