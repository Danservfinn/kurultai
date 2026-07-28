"""Forward-only, checksum-pinned Hulagu PostgreSQL migration entrypoint."""

from __future__ import annotations

import argparse
import hashlib
import re

# Safe here because the executable and argv shape are fixed; no shell is used.
import subprocess  # nosec B404
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

MIGRATIONS_DIR = (Path(__file__).parents[2] / "migrations").resolve()
PSQL = Path("/opt/homebrew/bin/psql")
MIGRATION_LOCK = 7_240_901_442
MIGRATION_NAME = re.compile(r"^(?P<version>[0-9]{4})_[a-z0-9_]+\.sql$")
LOCK_ACQUIRED = "hulagu-migration-lock-acquired"
HISTORY_SUCCESS_SQL = """
INSERT INTO public.hulagu_schema_migrations(version,filename,checksum,status,error_class)
VALUES (:'version'::integer, :'filename', :'checksum', 'succeeded', NULL)
ON CONFLICT(version) DO UPDATE SET filename=EXCLUDED.filename,checksum=EXCLUDED.checksum,
status='succeeded',error_class=NULL,applied_at=pg_catalog.now();
"""
HISTORY_FAILURE_SQL = """
INSERT INTO public.hulagu_schema_migrations(version,filename,checksum,status,error_class)
VALUES (:'version'::integer, :'filename', :'checksum', 'failed', :'error_class')
ON CONFLICT(version) DO UPDATE SET filename=EXCLUDED.filename,checksum=EXCLUDED.checksum,
status='failed',error_class=EXCLUDED.error_class,applied_at=pg_catalog.now();
"""


class MigrationError(RuntimeError):
    pass


def _psql(
    dsn: str,
    sql: str,
    *,
    check: bool = True,
    variables: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    argv = [str(PSQL), "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1"]
    for key, value in sorted((variables or {}).items()):
        argv.extend(("-v", f"{key}={value}"))
    argv.append(dsn)
    completed = subprocess.run(  # nosec B603
        argv,
        input=sql,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if check and completed.returncode != 0:
        sanitized = completed.stderr.replace(dsn, "<redacted-dsn>").strip()
        raise MigrationError(f"PostgreSQL migration command failed: {sanitized}")
    return completed


def _migration_files() -> list[tuple[int, Path, str]]:
    if not MIGRATIONS_DIR.is_dir():
        raise MigrationError("fixed migrations directory is absent")
    result: list[tuple[int, Path, str]] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        match = MIGRATION_NAME.fullmatch(path.name)
        if match is None:
            raise MigrationError(f"invalid migration filename: {path.name}")
        version = int(match.group("version"))
        result.append((version, path, hashlib.sha256(path.read_bytes()).hexdigest()))
    expected = list(range(1, len(result) + 1))
    if [version for version, _, _ in result] != expected:
        raise MigrationError("migration filename gap or duplicate")
    return result


@contextmanager
def _migration_lock(dsn: str) -> Iterator[None]:
    argv = [str(PSQL), "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", dsn]
    process = subprocess.Popen(  # nosec B603
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if process.stdin is None or process.stdout is None:
        process.kill()
        raise MigrationError("failed to open PostgreSQL migration lock session")
    try:
        process.stdin.write(
            f"SELECT pg_catalog.pg_advisory_lock({MIGRATION_LOCK}); SELECT '{LOCK_ACQUIRED}';\n"
        )
        process.stdin.flush()
        for line in process.stdout:
            if line.strip() == LOCK_ACQUIRED:
                break
        else:
            stderr = process.stderr.read() if process.stderr is not None else ""
            sanitized = stderr.replace(dsn, "<redacted-dsn>").strip()
            raise MigrationError(f"PostgreSQL migration lock failed: {sanitized}")
        yield
    finally:
        if process.poll() is None:
            process.stdin.write(f"SELECT pg_catalog.pg_advisory_unlock({MIGRATION_LOCK}); \\q\n")
            process.stdin.flush()
            try:
                process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()


def _ensure_history(dsn: str) -> None:
    _psql(
        dsn,
        """
        CREATE TABLE IF NOT EXISTS public.hulagu_schema_migrations (
          version integer PRIMARY KEY,
          filename text NOT NULL,
          checksum text NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
          status text NOT NULL CHECK (status IN ('succeeded','failed')),
          applied_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
          error_class text
        );
        REVOKE ALL ON public.hulagu_schema_migrations FROM PUBLIC;
        """,
    )


def _history(dsn: str) -> dict[int, tuple[str, str, str]]:
    rows = _psql(
        dsn,
        "SELECT version,filename,checksum,status FROM public.hulagu_schema_migrations ORDER BY version;",
    ).stdout.splitlines()
    history: dict[int, tuple[str, str, str]] = {}
    for row in rows:
        version, filename, checksum, status = row.split("|")
        history[int(version)] = (filename, checksum, status)
    return history


def migrate(dsn: str) -> int:
    files = _migration_files()
    applied = 0
    with _migration_lock(dsn):
        _ensure_history(dsn)
        known = {version: (path.name, checksum) for version, path, checksum in files}
        history = _history(dsn)
        unknown = sorted(set(history) - set(known))
        if unknown:
            raise MigrationError(f"unknown migration history: {unknown}")
        for version, (filename, checksum, status) in history.items():
            expected_filename, expected_checksum = known[version]
            if filename != expected_filename or checksum != expected_checksum:
                raise MigrationError(f"checksum drift at migration {version:04d}")
            if status not in {"succeeded", "failed"}:
                raise MigrationError(f"invalid migration status at {version:04d}")

        for version, path, checksum in files:
            if history.get(version, ("", "", ""))[2] == "succeeded":
                continue
            statement = f"BEGIN;\n{path.read_text()}\n{HISTORY_SUCCESS_SQL}\nCOMMIT;"
            variables = {"version": str(version), "filename": path.name, "checksum": checksum}
            completed = _psql(dsn, statement, check=False, variables=variables)
            if completed.returncode != 0:
                error_class = "postgresql_migration_error"
                _psql(
                    dsn,
                    HISTORY_FAILURE_SQL,
                    variables={**variables, "error_class": error_class},
                )
                sanitized = completed.stderr.replace(dsn, "<redacted-dsn>").strip()
                raise MigrationError(f"migration {path.name} failed: {sanitized}")
            applied += 1
    return applied


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply fixed forward-only Hulagu migrations")
    parser.add_argument("--dsn", required=True)
    args = parser.parse_args()
    try:
        applied = migrate(args.dsn)
    except (MigrationError, OSError, subprocess.SubprocessError) as exc:
        print(f"migration failed: {exc}", file=sys.stderr)
        return 1
    print(f"migration succeeded: applied={applied}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
