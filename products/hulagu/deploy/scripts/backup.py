"""Offline encrypted, signed, manifest-pinned Hulagu backup utility."""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib
import json
import os
import shutil
import stat
import subprocess  # nosec B404
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID, uuid4

_ENVELOPE_PREFIX = b"HULAGU-BACKUP-AES256-CBC-HMAC-SHA256-V1\0"


class BackupCoordinator(Protocol):
    def begin(self) -> str: ...

    def record(self, lock_token: str, snapshot_id: str, artifact_manifest: list[dict[str, object]]) -> None: ...

    def release(self, lock_token: str) -> None: ...

    def abort(self, lock_token: str) -> None: ...


class PostgresBackupCoordinator:
    """Transaction-scoped adapter over the frozen 0013 backup coordination functions."""

    def __init__(
        self,
        dsn: str,
        *,
        connect: Callable[[str], Any] | None = None,
        token_source: Callable[[], bytes] | None = None,
    ) -> None:
        if not dsn or "host=" not in dsn:
            raise ValueError("a Unix-socket PostgreSQL DSN is required")
        host = dsn.split("host=", 1)[1].split()[0].strip("'\"")
        if not host.startswith("/"):
            raise ValueError("backup coordination PostgreSQL must use a Unix socket")
        self._dsn = dsn
        self._connect_override = connect
        self._token_source = token_source or (lambda: os.urandom(32))
        self._sessions: dict[str, tuple[Any, Any, str]] = {}

    def _connect(self) -> Any:
        if self._connect_override is not None:
            return self._connect_override(self._dsn)
        try:
            psycopg = importlib.import_module("psycopg")
        except ImportError as exc:
            raise RuntimeError("psycopg is required for PostgreSQL backup coordination") from exc
        return psycopg.connect(self._dsn)

    @staticmethod
    def _close(connection: Any, cursor: Any) -> None:
        cursor.close()
        connection.close()

    def begin(self) -> str:
        token_bytes = self._token_source()
        if len(token_bytes) < 16:
            raise ValueError("invalid backup token source")
        token = base64.urlsafe_b64encode(token_bytes).decode("ascii")
        token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
        connection = self._connect()
        cursor = connection.cursor()
        try:
            cursor.execute("SELECT current_user")
            role = cursor.fetchone()
            if role is None or role[0] != "hulagu_migrator":
                raise PermissionError("PostgreSQL connection is not the hulagu_migrator role")
            cursor.execute("SELECT hulagu_api.begin_backup_coordination(%s)", (token_hash,))
            row = cursor.fetchone()
            if row is None or row[0] is None:
                raise PermissionError("backup coordination was refused")
        except BaseException:
            connection.rollback()
            self._close(connection, cursor)
            raise
        self._sessions[token] = (connection, cursor, token_hash)
        return token

    def record(
        self,
        lock_token: str,
        snapshot_id: str,
        artifact_manifest: list[dict[str, object]],
    ) -> None:
        try:
            connection, cursor, token_hash = self._sessions[lock_token]
        except KeyError as exc:
            raise PermissionError("unknown backup coordination token") from exc
        del connection
        encoded_manifest = json.dumps(artifact_manifest, sort_keys=True, separators=(",", ":"))
        cursor.execute(
            "SELECT hulagu_api.record_backup_snapshot(%s,%s,%s::jsonb)",
            (token_hash, snapshot_id, encoded_manifest),
        )
        row = cursor.fetchone()
        if row is None or not isinstance(row[0], str) or len(row[0]) != 64:
            raise PermissionError("backup snapshot recording was refused")

    def release(self, lock_token: str) -> None:
        try:
            connection, cursor, token_hash = self._sessions[lock_token]
        except KeyError as exc:
            raise PermissionError("unknown backup coordination token") from exc
        cursor.execute("SELECT hulagu_api.release_backup_coordination(%s)", (token_hash,))
        row = cursor.fetchone()
        if row is None or row[0] is not True:
            raise PermissionError("backup coordination release was refused")
        connection.commit()
        self._sessions.pop(lock_token)
        self._close(connection, cursor)

    def abort(self, lock_token: str) -> None:
        session = self._sessions.pop(lock_token, None)
        if session is None:
            return
        connection, cursor, _token_hash = session
        try:
            connection.rollback()
        finally:
            self._close(connection, cursor)


_OPEN_DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_OPEN_FILE_FLAGS = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)


def _open_directory_at(parent_fd: int, name: str) -> int:
    metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if stat.S_ISLNK(metadata.st_mode):
        raise ValueError("backup source contains a symlink")
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError("backup generation component is not a directory")
    descriptor = os.open(name, _OPEN_DIRECTORY_FLAGS, dir_fd=parent_fd)
    opened = os.fstat(descriptor)
    if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
        os.close(descriptor)
        raise ValueError("backup generation changed during traversal")
    return descriptor


def _read_directory_files(directory_fd: int, prefix: str = "") -> list[tuple[str, bytes]]:
    files: list[tuple[str, bytes]] = []
    for name in sorted(os.listdir(directory_fd)):
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        relative = f"{prefix}/{name}" if prefix else name
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError("backup source contains a symlink")
        if stat.S_ISDIR(metadata.st_mode):
            child_fd = _open_directory_at(directory_fd, name)
            try:
                files.extend(_read_directory_files(child_fd, relative))
            finally:
                os.close(child_fd)
            continue
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError("backup source contains an unsupported file")
        file_fd = os.open(name, _OPEN_FILE_FLAGS, dir_fd=directory_fd)
        try:
            opened = os.fstat(file_fd)
            if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
                raise ValueError("backup file changed during traversal")
            chunks: list[bytes] = []
            while chunk := os.read(file_fd, 1024 * 1024):
                chunks.append(chunk)
            files.append((relative, b"".join(chunks)))
        finally:
            os.close(file_fd)
    return files


def _read_confined_generation(vault_root: Path, tenant: str, generation: int) -> list[tuple[str, bytes]]:
    vault_fd = os.open(vault_root, _OPEN_DIRECTORY_FLAGS)
    descriptors = [vault_fd]
    try:
        for component in ("tenants", tenant, "wiki", "generations", str(generation)):
            descriptors.append(_open_directory_at(descriptors[-1], component))
        return _read_directory_files(descriptors[-1])
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _verify_generation_manifest(files: list[tuple[str, bytes]]) -> tuple[bytes, list[tuple[str, bytes]]]:
    by_path = dict(files)
    manifest_bytes = by_path.get("manifest.json")
    if manifest_bytes is None:
        raise ValueError("pinned generation publication manifest is absent")
    try:
        manifest = json.loads(manifest_bytes)
        declared_files = manifest["files"]
    except (UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("invalid pinned generation publication manifest") from exc
    if not isinstance(manifest, dict) or not isinstance(declared_files, list) or not declared_files:
        raise ValueError("invalid pinned generation publication manifest")
    declared_paths: set[str] = set()
    pinned: list[tuple[str, bytes]] = []
    for item in declared_files:
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "bytes"}:
            raise ValueError("invalid pinned generation publication manifest")
        path = item.get("path")
        digest = item.get("sha256")
        size = item.get("bytes")
        if (
            not isinstance(path, str)
            or not path
            or Path(path).is_absolute()
            or ".." in Path(path).parts
            or path == "manifest.json"
            or path in declared_paths
            or not isinstance(digest, str)
            or len(digest) != 64
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
        ):
            raise ValueError("invalid pinned generation publication manifest")
        data = by_path.get(path)
        if data is None or len(data) != size or not hmac.compare_digest(hashlib.sha256(data).hexdigest(), digest):
            raise ValueError("pinned generation publication manifest verification failed")
        declared_paths.add(path)
        pinned.append((path, data))
    if set(by_path) != declared_paths | {"manifest.json"}:
        raise ValueError("pinned generation manifest file set mismatch")
    return manifest_bytes, [("manifest.json", manifest_bytes), *sorted(pinned)]


def _read_confined_tree(root: Path) -> list[tuple[str, bytes]]:
    metadata = os.stat(root, follow_symlinks=False)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise ValueError("backup source must be a no-follow directory")
    descriptor = os.open(root, _OPEN_DIRECTORY_FLAGS)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise ValueError("backup source changed during traversal")
        return _read_directory_files(descriptor)
    finally:
        os.close(descriptor)


def _verify_postgres_backup_files(files: list[tuple[str, bytes]]) -> dict[str, object]:
    by_path = dict(files)
    manifest_bytes = by_path.get("backup_manifest")
    if manifest_bytes is None:
        raise ValueError("PostgreSQL backup_manifest evidence is required")
    try:
        manifest = json.loads(manifest_bytes)
        declared_files = manifest["Files"]
        wal_ranges = manifest["WAL-Ranges"]
    except (UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("invalid PostgreSQL backup_manifest evidence") from exc
    if manifest.get("PostgreSQL-Backup-Manifest-Version") not in {1, 2}:
        raise ValueError("unsupported PostgreSQL backup_manifest version")
    if not isinstance(declared_files, list) or not declared_files or not isinstance(wal_ranges, list) or not wal_ranges:
        raise ValueError("incomplete PostgreSQL backup_manifest evidence")
    actual_paths = set(by_path) - {"backup_manifest"}
    declared_paths: set[str] = set()
    verified_bytes = 0
    for item in declared_files:
        if not isinstance(item, dict):
            raise TypeError("invalid PostgreSQL backup_manifest file entry")
        path = item.get("Path")
        size = item.get("Size")
        algorithm = item.get("Checksum-Algorithm")
        checksum = item.get("Checksum")
        if (
            not isinstance(path, str)
            or Path(path).is_absolute()
            or ".." in Path(path).parts
            or path in declared_paths
            or not isinstance(size, int)
            or size < 0
            or algorithm != "SHA256"
            or not isinstance(checksum, str)
            or len(checksum) != 64
        ):
            raise ValueError("invalid PostgreSQL backup_manifest file entry")
        data = by_path.get(path)
        if data is None or len(data) != size or not hmac.compare_digest(hashlib.sha256(data).hexdigest(), checksum):
            raise ValueError("PostgreSQL backup_manifest file verification failed")
        declared_paths.add(path)
        verified_bytes += size
    if declared_paths != actual_paths:
        raise ValueError("PostgreSQL backup_manifest file set mismatch")
    for wal_range in wal_ranges:
        if (
            not isinstance(wal_range, dict)
            or not isinstance(wal_range.get("Timeline"), int)
            or not isinstance(wal_range.get("Start-LSN"), str)
            or not isinstance(wal_range.get("End-LSN"), str)
        ):
            raise TypeError("invalid PostgreSQL backup_manifest WAL range")
    tree_digest_input = json.dumps(
        [
            {"path": path, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
            for path, data in files
        ],
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return {
        "status": "manifest_files_verified",
        "backup_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "snapshot_tree_sha256": hashlib.sha256(tree_digest_input).hexdigest(),
        "verified_file_count": len(declared_files),
        "verified_bytes": verified_bytes,
        "wal_range_count": len(wal_ranges),
    }


def _openssl_transform(value: bytes, passphrase: bytes, *, decrypt: bool) -> bytes:
    read_fd, write_fd = os.pipe()
    try:
        os.write(write_fd, passphrase)
        os.close(write_fd)
        write_fd = -1
        command = [
            "/usr/bin/openssl",
            "enc",
            "-aes-256-cbc",
            "-pbkdf2",
            "-iter",
            "200000",
            "-md",
            "sha256",
            "-pass",
            f"fd:{read_fd}",
        ]
        if decrypt:
            command.append("-d")
        completed = subprocess.run(  # nosec B603
            command,
            input=value,
            capture_output=True,
            check=False,
            pass_fds=(read_fd,),
        )
        if completed.returncode != 0:
            raise ValueError("backup encryption operation failed")
        return completed.stdout
    finally:
        os.close(read_fd)
        if write_fd >= 0:
            os.close(write_fd)


def _derive_openssl_passphrase(key: bytes) -> bytes:
    return hmac.new(key, b"hulagu.backup.encryption.v1", hashlib.sha256).hexdigest().encode("ascii")


def _encrypt(value: bytes, key: bytes) -> bytes:
    encryption_passphrase = _derive_openssl_passphrase(key)
    authentication_key = hmac.new(key, b"hulagu.backup.authentication.v1", hashlib.sha256).digest()
    ciphertext = _openssl_transform(value, encryption_passphrase, decrypt=False)
    tag = hmac.new(authentication_key, _ENVELOPE_PREFIX + ciphertext, hashlib.sha256).digest()
    return _ENVELOPE_PREFIX + ciphertext + tag


def decrypt_payload(value: bytes, key: bytes) -> bytes:
    if not value.startswith(_ENVELOPE_PREFIX):
        raise ValueError("invalid encrypted backup")
    packed = value[len(_ENVELOPE_PREFIX) :]
    ciphertext, tag = packed[:-32], packed[-32:]
    encryption_passphrase = _derive_openssl_passphrase(key)
    authentication_key = hmac.new(key, b"hulagu.backup.authentication.v1", hashlib.sha256).digest()
    expected = hmac.new(authentication_key, _ENVELOPE_PREFIX + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise ValueError("backup authentication failed")
    return _openssl_transform(ciphertext, encryption_passphrase, decrypt=True)


def create_backup(
    database_snapshot: Path,
    vault_root: Path,
    destination: Path,
    *,
    active_generations: dict[str, int],
    encryption_key: bytes,
    signing_key: bytes,
    created_at: str,
    coordinator: BackupCoordinator | None = None,
) -> dict[str, Any]:
    if len(encryption_key) < 16 or len(signing_key) < 16:
        raise ValueError("backup keys are too short")
    if hmac.compare_digest(encryption_key, signing_key):
        raise ValueError("backup encryption and signing require separate key families")
    if coordinator is None:
        raise ValueError("backup coordinator is required")
    lock_token = coordinator.begin()
    generation_root: Path | None = None
    try:
        database_metadata = os.stat(database_snapshot, follow_symlinks=False)
        if stat.S_ISLNK(database_metadata.st_mode) or not stat.S_ISDIR(database_metadata.st_mode):
            raise ValueError("database snapshot must be a PostgreSQL physical backup directory")
        created = datetime.fromisoformat(created_at)
        backup_id = str(uuid4())
        entries: list[dict[str, object]] = []
        artifact_generations: list[dict[str, object]] = []
        database_files = _read_confined_tree(database_snapshot)
        database_evidence = _verify_postgres_backup_files(database_files)
        payload_files: dict[str, str] = {}
        for database_relative, database_data in database_files:
            relative = f"postgres/{database_relative}"
            payload_files[relative] = base64.b64encode(database_data).decode()
            entries.append(
                {
                    "path": relative,
                    "sha256": hashlib.sha256(database_data).hexdigest(),
                    "bytes": len(database_data),
                }
            )
        for tenant, generation in sorted(active_generations.items()):
            if str(UUID(tenant)) != tenant or generation < 1:
                raise ValueError("invalid active generation authority")
            observed_generation_files = _read_confined_generation(vault_root, tenant, generation)
            publication_manifest, generation_files = _verify_generation_manifest(observed_generation_files)
            for generation_relative, data in generation_files:
                relative = f"tenants/{tenant}/wiki/generations/{generation}/{generation_relative}"
                payload_files[relative] = base64.b64encode(data).decode()
                file_entry = {"path": relative, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                entries.append(file_entry)

            artifact_generations.append(
                {
                    "tenant_id": tenant,
                    "generation": generation,
                    "digest": hashlib.sha256(publication_manifest).hexdigest(),
                }
            )
        manifest: dict[str, Any] = {
            "schema_version": "BackupManifest/v1",
            "backup_id": backup_id,
            "created_at": created.isoformat(),
            "expires_at": (created + timedelta(days=90)).isoformat(),
            "files": entries,
            "active_generations": dict(sorted(active_generations.items())),
            "artifact_generations": artifact_generations,
            "database_snapshot_id": database_evidence["snapshot_tree_sha256"],
            "database_evidence": database_evidence,
        }
        manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        payload = json.dumps(payload_files, sort_keys=True, separators=(",", ":")).encode()
        generation_root = destination / backup_id
        generation_root.mkdir(parents=True, mode=0o700)
        (generation_root / "payload.enc").write_bytes(_encrypt(payload, encryption_key))
        (generation_root / "manifest.json").write_bytes(manifest_bytes)
        (generation_root / "manifest.sig").write_text(
            hmac.new(signing_key, manifest_bytes, hashlib.sha256).hexdigest()
        )
        for path in generation_root.iterdir():
            with path.open("rb") as handle:
                os.fsync(handle.fileno())
        directory_fd = os.open(generation_root, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        coordinator.record(lock_token, str(manifest["database_snapshot_id"]), artifact_generations)
        coordinator.release(lock_token)
        return manifest
    except BaseException:
        try:
            if generation_root is not None and generation_root.exists():
                shutil.rmtree(generation_root)
                if destination.exists():
                    destination_fd = os.open(destination, _OPEN_DIRECTORY_FLAGS)
                    try:
                        os.fsync(destination_fd)
                    finally:
                        os.close(destination_fd)
        finally:
            coordinator.abort(lock_token)
        raise


def prune_expired(destination: Path, *, now: str, retention_days: int = 90) -> tuple[str, ...]:
    if retention_days != 90:
        raise ValueError("approved backup retention is exactly 90 days")
    current = datetime.fromisoformat(now)
    removed: list[str] = []
    if not destination.exists():
        return ()
    for generation in destination.iterdir():
        manifest_path = generation / "manifest.json"
        if not generation.is_dir() or not manifest_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text())
        if current > datetime.fromisoformat(str(manifest["expires_at"])):
            shutil.rmtree(generation)
            removed.append(generation.name)
    return tuple(sorted(removed))
