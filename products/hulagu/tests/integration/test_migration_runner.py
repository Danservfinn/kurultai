from __future__ import annotations

import hashlib
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from test_migrations import EXPECTED_MIGRATIONS, MIGRATIONS, load_migrator, postgres_cluster, psql, run_migrator


def test_runner_has_one_fixed_forward_entrypoint_and_no_down_mode() -> None:
    module = load_migrator()
    assert module.MIGRATIONS_DIR == MIGRATIONS.resolve()
    assert not hasattr(module, "downgrade")
    assert "--down" not in Path(module.__file__).read_text()


def test_runner_records_filename_and_sha256_history() -> None:
    with postgres_cluster() as dsn:
        rows = psql(
            dsn,
            "SELECT filename || ':' || checksum FROM public.hulagu_schema_migrations "
            "WHERE status='succeeded' ORDER BY version",
        ).stdout.splitlines()
        expected = [f"{name}:{hashlib.sha256((MIGRATIONS / name).read_bytes()).hexdigest()}" for name in EXPECTED_MIGRATIONS]
        assert rows == expected


def test_runner_refuses_checksum_drift_without_disclosing_dsn() -> None:
    with postgres_cluster() as dsn:
        psql(dsn, "UPDATE public.hulagu_schema_migrations SET checksum = repeat('0', 64) WHERE version = 1")
        result = run_migrator(dsn, check=False)
        assert result.returncode != 0
        assert "checksum drift" in result.stderr.lower()
        assert dsn not in result.stdout + result.stderr


def test_runner_refuses_unknown_history_gap() -> None:
    with postgres_cluster() as dsn:
        psql(
            dsn,
            "INSERT INTO public.hulagu_schema_migrations(version,filename,checksum,status) "
            "VALUES (99,'0099_unknown.sql',repeat('f',64),'succeeded')",
        )
        result = run_migrator(dsn, check=False)
        assert result.returncode != 0
        assert "unknown migration history" in result.stderr.lower()


def test_runner_uses_postgresql_advisory_lock() -> None:
    source = Path(load_migrator().__file__).read_text()
    assert "pg_advisory" in source


def test_two_synchronized_migrators_serialize_the_whole_run() -> None:
    with postgres_cluster(migrate=False) as dsn:
        locker = subprocess.Popen(
            ["/opt/homebrew/bin/psql", "-X", "-A", "-t", dsn],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert locker.stdin is not None and locker.stdout is not None
        try:
            locker.stdin.write("SELECT pg_catalog.pg_advisory_lock(7240901442); SELECT 'locked';\n")
            locker.stdin.flush()
            while locker.stdout.readline().strip() != "locked":
                pass

            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(run_migrator, dsn, check=False) for _ in range(2)]
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    waiters = psql(dsn, "SELECT count(*) FROM pg_stat_activity WHERE wait_event='advisory'").stdout.strip()
                    if int(waiters) >= 2:
                        break
                    time.sleep(0.05)
                else:
                    raise AssertionError("migrators did not reach the synchronized advisory-lock boundary")

                locker.stdin.write("SELECT pg_catalog.pg_advisory_unlock(7240901442); \\q\n")
                locker.stdin.flush()
                results = [future.result() for future in futures]
        finally:
            if locker.poll() is None:
                locker.kill()
            locker.communicate(timeout=5)

        assert [result.returncode for result in results] == [0, 0]
        assert sorted(result.stdout.strip() for result in results) == [
            "migration succeeded: applied=0",
            "migration succeeded: applied=14",
        ]
