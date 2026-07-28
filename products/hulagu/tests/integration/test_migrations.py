from __future__ import annotations

import getpass
import importlib.util
import os
import shutil
import socket
import subprocess
import tempfile
from collections.abc import Iterator
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
        assert psql(dsn, "SELECT count(*) FROM public.hulagu_schema_migrations WHERE status = 'succeeded'").stdout.strip() == "7"
        required = {
            "tenants", "enrollments", "identity_bindings", "inbound_updates", "customer_profiles",
            "profile_answers", "source_documents", "search_runs", "job_attempts", "provider_requests",
            "search_candidates", "candidate_decisions", "wiki_publications", "outbox_messages", "receipts",
            "deletion_jobs", "deletion_tombstones", "deletion_receipts", "retention_jobs", "global_storage_state",
        }
        rows = psql(dsn, "SELECT tablename FROM pg_tables WHERE schemaname='hulagu'").stdout.splitlines()
        assert required <= set(rows)


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
            "'outbox_messages','receipts','retention_jobs') AND (NOT c.relrowsecurity OR NOT c.relforcerowsecurity)",
        ).stdout.strip()
        assert missing_force == "0"
        policies = psql(dsn, "SELECT count(*) FROM pg_policies WHERE schemaname='hulagu' AND qual IS NOT NULL AND with_check IS NOT NULL").stdout.strip()
        assert int(policies) >= 14


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


def test_no_ephemeral_cluster_leaks_from_helper() -> None:
    before = set(Path(tempfile.gettempdir()).glob("hulagu-pg-*"))
    with postgres_cluster():
        pass
    after = set(Path(tempfile.gettempdir()).glob("hulagu-pg-*"))
    assert after == before
