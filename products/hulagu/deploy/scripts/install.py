"""Dry-run-first Hulagu installation enrollment and bootstrap planner."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import plistlib
import stat
import subprocess  # nosec B404
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol

from hulagu.control.doctor import SECRET_INVENTORY

INSTALL_RECORD = Path("/Users/kublai/Library/Application Support/Kurultai/Hulagu/install.json")
VAULT_PATH = Path("/Volumes/KurultaiVault")
POSTGRES_HOME = Path("/opt/homebrew/opt/postgresql@16")
MIGRATIONS_DIR = Path(__file__).parents[2] / "migrations"


class SystemInspector(Protocol):
    def inspect_vault(self, path: Path) -> tuple[str, bool, int, int]: ...
    def inspect_engine(self, executable: Path, socket_path: Path) -> tuple[str, str]: ...


class BootstrapEffect(Protocol):
    def apply(self) -> None: ...


class NativePostgresBootstrap:
    """One-time native bootstrap; ordinary launchd startup never calls this effect."""

    def __init__(
        self,
        *,
        data_root: Path = VAULT_PATH / "hulagu",
        postgres_home: Path = POSTGRES_HOME,
        migrations_dir: Path = MIGRATIONS_DIR,
        secret_reader: Callable[[str], str] | None = None,
    ) -> None:
        self._data_root = data_root
        self._bin = postgres_home / "bin"
        self._migrations = migrations_dir
        self._secret_reader = secret_reader or self._read_keychain

    @staticmethod
    def _read_keychain(item: str) -> str:
        completed = subprocess.run(  # nosec B603
            ["/usr/bin/security", "find-generic-password", "-w", "-s", item],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
            env={"PATH": "/usr/bin:/bin"},
        )
        value = completed.stdout.rstrip("\n")
        if not 16 <= len(value) <= 256 or "\x00" in value or "\n" in value or "\r" in value:
            raise ValueError("invalid PostgreSQL password authority")
        return value

    @staticmethod
    def _sql_literal(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    def _run(self, argv: list[str], *, input_text: str | None = None) -> None:
        if not argv or any("\x00" in item or "\n" in item for item in argv):
            raise ValueError("invalid PostgreSQL bootstrap command")
        subprocess.run(  # nosec B603
            argv,
            input=input_text,
            text=True,
            check=True,
            capture_output=True,
            timeout=120,
            env={"PATH": "/usr/bin:/bin"},
        )

    def apply(self) -> None:
        pgdata = self._data_root / "postgres"
        socket_dir = self._data_root / "run" / "postgres"
        logs = self._data_root / "logs"
        private = self._data_root / "private"
        for directory in (self._data_root, socket_dir, logs, private):
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(directory, 0o700)
        if pgdata.exists():
            raise FileExistsError("PostgreSQL data directory already exists")
        initdb = self._bin / "initdb"
        pg_ctl = self._bin / "pg_ctl"
        psql = self._bin / "psql"
        for executable in (initdb, pg_ctl, psql):
            _validate_executable(executable)
        self._run([str(initdb), "-D", str(pgdata), "--auth-local=peer", "--auth-host=reject"])
        configuration = pgdata / "postgresql.auto.conf"
        with configuration.open("a", encoding="utf-8") as handle:
            handle.write("listen_addresses = ''\n")
            handle.write(f"unix_socket_directories = '{socket_dir}'\n")
        self._run(
            [
                str(pg_ctl),
                "-D",
                str(pgdata),
                "-l",
                str(logs / "bootstrap.log"),
                "-o",
                f"-c listen_addresses= -c unix_socket_directories={socket_dir}",
                "-w",
                "start",
            ]
        )
        try:
            passwords = {
                "hulagu_app": self._secret_reader("com.kurultai.hulagu.postgres-app-password.v1"),
                "hulagu_runner": self._secret_reader("com.kurultai.hulagu.postgres-runner-password.v1"),
                "hulagu_deletion": self._secret_reader(
                    "com.kurultai.hulagu.postgres-deletion-password.v1"
                ),
            }
            role_sql = f"""
DO $bootstrap$
BEGIN
  CREATE ROLE hulagu_app LOGIN PASSWORD {self._sql_literal(passwords["hulagu_app"])};
  CREATE ROLE hulagu_runner LOGIN PASSWORD {self._sql_literal(passwords["hulagu_runner"])};
  CREATE ROLE hulagu_deletion LOGIN PASSWORD {self._sql_literal(passwords["hulagu_deletion"])};
EXCEPTION WHEN duplicate_object THEN RAISE EXCEPTION 'Hulagu roles already exist';
END
$bootstrap$;
CREATE DATABASE hulagu;
"""
            self._run(
                [str(psql), "-X", "-v", "ON_ERROR_STOP=1", "-h", str(socket_dir), "postgres"],
                input_text=role_sql,
            )
            for migration in sorted(self._migrations.glob("*.sql")):
                self._run(
                    [str(psql), "-X", "-v", "ON_ERROR_STOP=1", "-h", str(socket_dir), "-d", "hulagu"],
                    input_text=migration.read_text(),
                )
        finally:
            self._run([str(pg_ctl), "-D", str(pgdata), "-m", "fast", "-w", "stop"])


class NativeInspector:
    """Inspect fixed explicit paths only; never discover through PATH or Docker contexts."""

    def inspect_vault(self, path: Path) -> tuple[str, bool, int, int]:
        completed = subprocess.run(  # nosec B603
            ["/usr/sbin/diskutil", "info", "-plist", str(path)],
            check=True,
            capture_output=True,
            timeout=10,
            env={"PATH": "/usr/bin:/bin"},
        )
        payload = plistlib.loads(completed.stdout)
        usage = os.statvfs(path)
        return (
            str(payload.get("VolumeUUID") or ""),
            bool(payload.get("Encrypted") or payload.get("FileVault")),
            usage.f_blocks * usage.f_frsize,
            usage.f_bavail * usage.f_frsize,
        )

    def inspect_engine(self, executable: Path, socket_path: Path) -> tuple[str, str]:
        mode = socket_path.lstat().st_mode
        if not stat.S_ISSOCK(mode):
            raise ValueError("engine endpoint is not a Unix socket")
        digest = "sha256:" + hashlib.sha256(executable.read_bytes()).hexdigest()
        completed = subprocess.run(  # nosec B603
            [str(executable), "-H", f"unix://{socket_path}", "version", "--format", "{{json .Client}}"],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
            env={"PATH": "/usr/bin:/bin"},
        )
        version = completed.stdout.strip()
        if not version:
            raise ValueError("engine effective state cannot be inspected")
        return digest, version[:500]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hulagu-install")
    parser.add_argument("--enroll-vault-uuid")
    parser.add_argument("--enroll-container-cli", type=Path)
    parser.add_argument("--engine-socket", type=Path)
    parser.add_argument("--bootstrap-postgres", action="store_true")
    parser.add_argument("--apply", action="store_true")
    return parser


def _load_record(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": "HulaguInstall/v1"}
    if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise PermissionError("installation record permissions are unsafe")
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or value.get("schema_version") != "HulaguInstall/v1":
        raise ValueError("invalid installation record")
    return value


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    os.chmod(path, 0o600)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


@contextmanager
def _record_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    lock_path = path.with_name(f".{path.name}.lock")
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        os.chmod(lock_path, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _validate_executable(path: Path) -> None:
    if not path.is_absolute():
        raise ValueError("container executable must be absolute")
    if path.is_symlink():
        raise ValueError("container executable symlink is forbidden")
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError("container executable is absent or unexecutable")


def _validate_socket(path: Path) -> None:
    if not path.is_absolute() or str(path).startswith(("tcp:", "http:", "https:")):
        raise ValueError("engine endpoint must be an absolute local Unix socket")
    if path.is_symlink() or not path.exists():
        raise ValueError("engine socket is absent or drifted")


def run(
    argv: list[str] | None = None,
    *,
    inspector: SystemInspector | None = None,
    record_path: Path = INSTALL_RECORD,
    bootstrap_effect: BootstrapEffect | None = None,
) -> dict[str, object]:
    args = _parser().parse_args(argv)
    inspector = inspector or NativeInspector()
    if (args.enroll_container_cli is None) != (args.engine_socket is None):
        raise ValueError("container executable and engine socket must be enrolled together")

    current = _load_record(record_path)
    proposed = dict(current)
    updates: dict[str, Any] = {}
    changes: list[dict[str, object]] = []

    if args.enroll_vault_uuid is not None:
        observed_uuid, encrypted, capacity, free = inspector.inspect_vault(VAULT_PATH)
        if not observed_uuid or args.enroll_vault_uuid != observed_uuid:
            raise ValueError("proposed vault UUID does not match mounted volume")
        if not encrypted:
            raise ValueError("proposed vault is not encrypted APFS")
        vault_updates = {"vault_path": str(VAULT_PATH), "vault_uuid": observed_uuid}
        proposed.update(vault_updates)
        updates.update(vault_updates)
        changes.append({
            "kind": "vault_enrollment",
            "path": str(VAULT_PATH),
            "old_uuid": current.get("vault_uuid"),
            "proposed_uuid": observed_uuid,
            "encrypted": True,
            "capacity_bytes": capacity,
            "free_bytes": free,
            "affected_services": ["postgres", "app", "runner", "deletion"],
        })

    if args.enroll_container_cli is not None and args.engine_socket is not None:
        _validate_executable(args.enroll_container_cli)
        _validate_socket(args.engine_socket)
        digest, version = inspector.inspect_engine(args.enroll_container_cli, args.engine_socket)
        if not digest.startswith("sha256:") or len(digest) != 71 or not version:
            raise ValueError("invalid inspected container engine identity")
        container_updates = {
            "container_cli": str(args.enroll_container_cli),
            "container_cli_sha256": digest,
            "container_cli_version": version,
            "engine_socket": str(args.engine_socket),
        }
        proposed.update(container_updates)
        updates.update(container_updates)
        changes.append({
            "kind": "container_enrollment",
            "absolute_executable": str(args.enroll_container_cli),
            "executable_sha256": digest,
            "executable_version": version,
            "local_engine_endpoint": f"unix://{args.engine_socket}",
            "affected_services": ["runner"],
        })

    if args.bootstrap_postgres:
        if current.get("vault_uuid") is None:
            raise PermissionError("PostgreSQL bootstrap requires prior approved vault enrollment")
        changes.append({
            "kind": "postgres_bootstrap",
            "executable_home": str(POSTGRES_HOME),
            "pgdata": str(VAULT_PATH / "hulagu" / "postgres"),
            "socket": str(VAULT_PATH / "hulagu" / "run" / "postgres"),
            "listen_addresses": "",
            "roles": ["hulagu_app", "hulagu_runner", "hulagu_deletion"],
        })
        proposed["postgres_bootstrapped"] = True
        updates["postgres_bootstrapped"] = True

    inventory = [
        {"family": item.family, "reader": item.reader, "name": item.keychain_item, "version": item.version}
        for item in SECRET_INVENTORY
    ]
    updates.update({"schema_version": "HulaguInstall/v1", "keychain_items": inventory})
    proposed.update(updates)
    report: dict[str, object] = {
        "schema_version": "HulaguInstallPlan/v1",
        "record_path": str(record_path),
        "mutation_performed": False,
        "changes": changes,
        "current_enrollment": current,
        "proposed_enrollment": proposed,
        "role_mapping": {
            "app": "hulagu_app",
            "runner": "hulagu_runner",
            "deletion": "hulagu_deletion",
        },
        "keychain_items": inventory,
        "service_mutations": [
            {"label": f"com.kurultai.hulagu-{service}", "operation": "render_and_bootstrap"}
            for service in ("postgres", "app", "runner", "deletion")
        ],
    }
    if args.apply:
        if not changes:
            raise ValueError("--apply requires an explicit enrollment or bootstrap operation")
        with _record_lock(record_path):
            merged = _load_record(record_path)
            if args.bootstrap_postgres:
                enrolled_uuid = merged.get("vault_uuid")
                observed_uuid, encrypted, _capacity, _free = inspector.inspect_vault(VAULT_PATH)
                if not encrypted or not enrolled_uuid or observed_uuid != enrolled_uuid:
                    raise PermissionError("mounted encrypted vault identity drifted")
                (bootstrap_effect or NativePostgresBootstrap()).apply()
            merged.update(updates)
            _atomic_write(record_path, merged)
        report["mutation_performed"] = True
    return report


def main(argv: list[str] | None = None) -> int:
    report = run(argv)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
