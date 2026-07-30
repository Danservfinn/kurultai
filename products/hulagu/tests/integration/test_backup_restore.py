from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
TENANT_A = "91000000-0000-4000-8000-000000000001"
TENANT_B = "91000000-0000-4000-8000-000000000002"


def load(name: str, path: Path) -> object:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backup = load("hulagu_backup", ROOT / "deploy" / "scripts" / "backup.py")
restore = load("hulagu_restore", ROOT / "deploy" / "scripts" / "restore_verify.py")


def test_openssl_passphrase_derivation_is_fixed_printable_and_not_line_truncatable() -> None:
    for key in (bytes(range(32)), b"\n" * 32, b"\x00" * 32, b"synthetic-key-material" * 2):
        passphrase = backup._derive_openssl_passphrase(key)
        assert len(passphrase) == 64
        assert passphrase.decode("ascii").isprintable()
        assert b"\n" not in passphrase
        assert b"\r" not in passphrase
        assert b"\x00" not in passphrase


class RecordingCoordinator:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.recorded_manifest: list[dict[str, object]] | None = None

    def begin(self) -> str:
        self.events.append("begin-read-only-drain-lock")
        return "lock-token"

    def record(self, lock_token: str, snapshot_id: str, artifact_manifest: list[dict[str, object]]) -> None:
        assert lock_token == "lock-token" and snapshot_id and artifact_manifest
        self.recorded_manifest = artifact_manifest
        self.events.append("record-snapshot-manifest")

    def release(self, lock_token: str) -> None:
        assert lock_token == "lock-token"
        self.events.append("release-after-fsync")

    def abort(self, lock_token: str) -> None:
        assert lock_token == "lock-token"
        self.events.append("abort-backup-lock")


class FailingRecordCoordinator(RecordingCoordinator):
    def record(self, lock_token: str, snapshot_id: str, artifact_manifest: list[dict[str, object]]) -> None:
        super().record(lock_token, snapshot_id, artifact_manifest)
        raise RuntimeError("synthetic record failure")


class FakeBackupCursor:
    def __init__(self, events: list[object]) -> None:
        self._events = events
        self._last_sql = ""

    def execute(self, sql: str, parameters: tuple[object, ...] = ()) -> None:
        self._last_sql = sql
        self._events.append((sql, parameters))

    def fetchone(self) -> tuple[object, ...]:
        if self._last_sql == "SELECT current_user":
            return ("hulagu_migrator",)
        if "begin_backup_coordination" in self._last_sql:
            return ("93000000-0000-4000-8000-000000000001",)
        if "record_backup_snapshot" in self._last_sql:
            return ("f" * 64,)
        if "release_backup_coordination" in self._last_sql:
            return (True,)
        raise AssertionError(self._last_sql)

    def close(self) -> None:
        self._events.append("cursor-close")


class FakeBackupConnection:
    def __init__(self, events: list[object]) -> None:
        self._events = events

    def cursor(self) -> FakeBackupCursor:
        return FakeBackupCursor(self._events)

    def commit(self) -> None:
        self._events.append("commit")

    def rollback(self) -> None:
        self._events.append("rollback")

    def close(self) -> None:
        self._events.append("connection-close")


def test_postgres_backup_coordinator_uses_one_transaction_and_frozen_0013_functions() -> None:
    events: list[object] = []
    coordinator = backup.PostgresBackupCoordinator(
        "host=/synthetic/postgres user=hulagu_migrator dbname=hulagu",
        connect=lambda _dsn: FakeBackupConnection(events),
        token_source=lambda: b"b" * 32,
    )
    token = coordinator.begin()
    generation_entries = [{"tenant_id": TENANT_A, "generation": 7, "digest": "a" * 64}]
    coordinator.record(token, "snapshot-1", generation_entries)
    coordinator.release(token)

    statements = [event[0] for event in events if isinstance(event, tuple)]
    assert statements == [
        "SELECT current_user",
        "SELECT hulagu_api.begin_backup_coordination(%s)",
        "SELECT hulagu_api.record_backup_snapshot(%s,%s,%s::jsonb)",
        "SELECT hulagu_api.release_backup_coordination(%s)",
    ]
    assert events[-3:] == ["commit", "cursor-close", "connection-close"]

    aborted_events: list[object] = []
    aborted = backup.PostgresBackupCoordinator(
        "host=/synthetic/postgres user=hulagu_migrator dbname=hulagu",
        connect=lambda _dsn: FakeBackupConnection(aborted_events),
        token_source=lambda: b"c" * 32,
    )
    aborted_token = aborted.begin()
    aborted.abort(aborted_token)
    assert aborted_events[-3:] == ["rollback", "cursor-close", "connection-close"]


def source_tree(tmp_path: Path) -> tuple[Path, Path]:
    vault = tmp_path / "vault"
    generation = vault / "tenants" / TENANT_A / "wiki" / "generations" / "7"
    generation.mkdir(parents=True)
    (generation / "index.md").write_text("synthetic tenant a")
    tenant_a_index = (generation / "index.md").read_bytes()
    (generation / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "SyntheticWikiManifest/v1",
                "tenant": "a",
                "files": [
                    {
                        "path": "index.md",
                        "sha256": hashlib.sha256(tenant_a_index).hexdigest(),
                        "bytes": len(tenant_a_index),
                    }
                ],
            },
            sort_keys=True,
        )
    )
    (vault / "tenants" / TENANT_B / "wiki" / "generations" / "8").mkdir(parents=True)
    (vault / "tenants" / TENANT_B / "wiki" / "generations" / "8" / "index.md").write_text("synthetic tenant b")
    tenant_b_generation = vault / "tenants" / TENANT_B / "wiki" / "generations" / "8"
    tenant_b_index = (tenant_b_generation / "index.md").read_bytes()
    (tenant_b_generation / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "SyntheticWikiManifest/v1",
                "tenant": "b",
                "files": [
                    {
                        "path": "index.md",
                        "sha256": hashlib.sha256(tenant_b_index).hexdigest(),
                        "bytes": len(tenant_b_index),
                    }
                ],
            },
            sort_keys=True,
        )
    )
    database = tmp_path / "postgres-backup"
    (database / "global").mkdir(parents=True)
    (database / "pg_wal").mkdir()
    database_files = {
        "global/pg_control": b"synthetic postgres control data",
        "pg_wal/000000010000000000000001": b"synthetic wal segment",
    }
    for relative, data in database_files.items():
        (database / relative).write_bytes(data)
    postgres_manifest = {
        "PostgreSQL-Backup-Manifest-Version": 2,
        "Files": [
            {
                "Path": relative,
                "Size": len(data),
                "Checksum-Algorithm": "SHA256",
                "Checksum": hashlib.sha256(data).hexdigest(),
            }
            for relative, data in sorted(database_files.items())
        ],
        "WAL-Ranges": [{"Timeline": 1, "Start-LSN": "0/0", "End-LSN": "0/1"}],
    }
    (database / "backup_manifest").write_text(json.dumps(postgres_manifest, sort_keys=True))
    return vault, database


def test_backup_refuses_to_run_without_global_coordinator(tmp_path: Path) -> None:
    vault, database = source_tree(tmp_path)
    with pytest.raises(ValueError, match="coordinator"):
        backup.create_backup(
            database,
            vault,
            tmp_path / "backups",
            active_generations={TENANT_A: 7},
            encryption_key=b"e" * 32,
            signing_key=b"s" * 32,
            created_at="2026-07-29T00:00:00+00:00",
        )


def test_backup_rejects_opaque_database_blob_without_postgres_manifest_evidence(tmp_path: Path) -> None:
    vault, _database = source_tree(tmp_path)
    database = tmp_path / "opaque-base.tar"
    database.write_bytes(b"not a verifiable physical backup")
    coordinator = RecordingCoordinator()
    with pytest.raises(ValueError, match="PostgreSQL physical backup directory"):
        backup.create_backup(
            database,
            vault,
            tmp_path / "backups",
            active_generations={TENANT_A: 7},
            encryption_key=b"e" * 32,
            signing_key=b"s" * 32,
            created_at="2026-07-29T00:00:00+00:00",
            coordinator=coordinator,
        )
    assert coordinator.events == ["begin-read-only-drain-lock", "abort-backup-lock"]


def test_backup_records_observed_postgres_manifest_evidence_without_unverified_claims(tmp_path: Path) -> None:
    vault, database = source_tree(tmp_path)
    manifest = backup.create_backup(
        database,
        vault,
        tmp_path / "backups",
        active_generations={TENANT_A: 7},
        encryption_key=b"e" * 32,
        signing_key=b"s" * 32,
        created_at="2026-07-29T00:00:00+00:00",
        coordinator=RecordingCoordinator(),
    )
    assert "wal_streamed" not in manifest
    assert manifest["database_evidence"]["status"] == "manifest_files_verified"
    assert manifest["database_evidence"]["verified_file_count"] == 2
    assert manifest["database_evidence"]["wal_range_count"] == 1
    assert len(manifest["database_evidence"]["backup_manifest_sha256"]) == 64


def test_restore_receipt_reports_only_observed_integrity_and_fails_closed_on_semantic_checks(tmp_path: Path) -> None:
    vault, database = source_tree(tmp_path)
    destination = tmp_path / "backups"
    manifest = backup.create_backup(
        database,
        vault,
        destination,
        active_generations={TENANT_A: 7, TENANT_B: 8},
        encryption_key=b"e" * 32,
        signing_key=b"s" * 32,
        created_at="2026-07-29T00:00:00+00:00",
        coordinator=RecordingCoordinator(),
    )
    encrypted_payload = (destination / manifest["backup_id"] / "payload.enc").read_bytes()
    assert encrypted_payload.startswith(b"HULAGU-BACKUP-AES256-CBC-HMAC-SHA256-V1\0")
    assert not (database / "global" / "pg_control").read_bytes() in encrypted_payload

    receipt = restore.verify_restore(
        destination / manifest["backup_id"],
        tmp_path / "isolated-restore",
        encryption_key=b"e" * 32,
        signing_key=b"s" * 32,
        expected_active_generations={TENANT_A: 7, TENANT_B: 8},
        tombstones=("tombstone-a",),
    )
    assert receipt["status"] == "INCOMPLETE_SEMANTIC_VERIFICATION"
    assert receipt["startup_authorized"] is False
    assert receipt["evidence"]["postgres_backup_manifest"] == manifest["database_evidence"]
    assert receipt["evidence"]["artifact_files"]["status"] == "verified"
    assert receipt["evidence"]["tombstone_replay"] == {"status": "not_verified", "required_count": 1}
    assert set(receipt["unverified_requirements"]) == {
        "wal_replay",
        "postgres_data_checksums",
        "rls",
        "grants",
        "tenant_isolation",
        "non_routable_runtime",
        "credential_absence",
        "tombstone_replay",
    }
    assert not {
        "verified",
        "network_mode",
        "credentials_present",
        "tenant_isolation_verified",
        "rls_grants_verified",
    } & set(receipt)
    assert not (tmp_path / "isolated-restore").exists()


def test_restore_refuses_startup_until_tombstones_are_applied(tmp_path: Path) -> None:
    gate = restore.RestoreStartupGate(required_tombstones={"tombstone-a", "tombstone-b"})
    gate.apply("tombstone-a")
    with pytest.raises(PermissionError, match="tombstone"):
        gate.enable_services()
    gate.apply("tombstone-b")
    with pytest.raises(PermissionError, match="semantic PostgreSQL"):
        gate.enable_services()


def test_backup_excludes_unpinned_and_partial_generations_and_expires_after_90_days(tmp_path: Path) -> None:
    vault, database = source_tree(tmp_path)
    partial = vault / "tenants" / TENANT_A / "wiki" / ".staging" / "9"
    partial.mkdir(parents=True)
    (partial / "secret.tmp").write_text("must not backup")
    destination = tmp_path / "backups"
    manifest = backup.create_backup(
        database,
        vault,
        destination,
        active_generations={TENANT_A: 7},
        encryption_key=b"e" * 32,
        signing_key=b"s" * 32,
        created_at="2026-01-01T00:00:00+00:00",
        coordinator=RecordingCoordinator(),
    )
    public_manifest = json.loads((destination / manifest["backup_id"] / "manifest.json").read_text())
    assert all(".staging" not in item["path"] and TENANT_B not in item["path"] for item in public_manifest["files"])
    removed = backup.prune_expired(destination, now="2026-04-02T00:00:01+00:00", retention_days=90)
    assert manifest["backup_id"] in removed
    assert not (destination / manifest["backup_id"]).exists()


def test_backup_rejects_regular_file_not_pinned_by_generation_manifest(tmp_path: Path) -> None:
    vault, database = source_tree(tmp_path)
    generation = vault / "tenants" / TENANT_A / "wiki" / "generations" / "7"
    (generation / "UNPINNED-SECRET.txt").write_text("must never enter a backup")
    coordinator = RecordingCoordinator()

    with pytest.raises(ValueError, match="manifest file set"):
        backup.create_backup(
            database,
            vault,
            tmp_path / "backups",
            active_generations={TENANT_A: 7},
            encryption_key=b"e" * 32,
            signing_key=b"s" * 32,
            created_at="2026-07-29T00:00:00+00:00",
            coordinator=coordinator,
        )

    assert coordinator.events == ["begin-read-only-drain-lock", "abort-backup-lock"]


def test_backup_removes_unrecorded_generation_when_coordinator_fails(tmp_path: Path) -> None:
    vault, database = source_tree(tmp_path)
    destination = tmp_path / "backups"
    coordinator = FailingRecordCoordinator()

    with pytest.raises(RuntimeError, match="record failure"):
        backup.create_backup(
            database,
            vault,
            destination,
            active_generations={TENANT_A: 7},
            encryption_key=b"e" * 32,
            signing_key=b"s" * 32,
            created_at="2026-07-29T00:00:00+00:00",
            coordinator=coordinator,
        )

    assert coordinator.events == [
        "begin-read-only-drain-lock",
        "record-snapshot-manifest",
        "abort-backup-lock",
    ]
    assert not destination.exists() or list(destination.iterdir()) == []


def test_backup_rejects_equal_encryption_and_signing_key_material(tmp_path: Path) -> None:
    vault, database = source_tree(tmp_path)
    coordinator = RecordingCoordinator()

    with pytest.raises(ValueError, match="separate key families"):
        backup.create_backup(
            database,
            vault,
            tmp_path / "backups",
            active_generations={TENANT_A: 7},
            encryption_key=b"same-key-material" * 2,
            signing_key=b"same-key-material" * 2,
            created_at="2026-07-29T00:00:00+00:00",
            coordinator=coordinator,
        )

    assert coordinator.events == []


def test_backup_rejects_symlink_inside_pinned_generation(tmp_path: Path) -> None:
    vault, database = source_tree(tmp_path)
    outside = tmp_path / "outside-secret"
    outside.write_text("must never be followed")
    (vault / "tenants" / TENANT_A / "wiki" / "generations" / "7" / "escape.md").symlink_to(outside)

    with pytest.raises(ValueError, match="symlink"):
        backup.create_backup(
            database,
            vault,
            tmp_path / "backups",
            active_generations={TENANT_A: 7},
            encryption_key=b"e" * 32,
            signing_key=b"s" * 32,
            created_at="2026-07-29T00:00:00+00:00",
            coordinator=RecordingCoordinator(),
        )


def test_backup_aborts_coordination_on_traversal_failure_without_release(tmp_path: Path) -> None:
    vault, database = source_tree(tmp_path)
    (vault / "tenants" / TENANT_A / "wiki" / "generations" / "7" / "escape.md").symlink_to(tmp_path)
    coordinator = RecordingCoordinator()

    with pytest.raises(ValueError, match="symlink"):
        backup.create_backup(
            database,
            vault,
            tmp_path / "backups",
            active_generations={TENANT_A: 7},
            encryption_key=b"e" * 32,
            signing_key=b"s" * 32,
            created_at="2026-07-29T00:00:00+00:00",
            coordinator=coordinator,
        )

    assert coordinator.events == ["begin-read-only-drain-lock", "abort-backup-lock"]


def test_backup_holds_global_coordination_until_encrypted_manifest_is_durable(tmp_path: Path) -> None:
    vault, database = source_tree(tmp_path)
    coordinator = RecordingCoordinator()
    backup.create_backup(
        database,
        vault,
        tmp_path / "backups",
        active_generations={TENANT_A: 7},
        encryption_key=b"e" * 32,
        signing_key=b"s" * 32,
        created_at="2026-07-29T00:00:00+00:00",
        coordinator=coordinator,
    )
    assert coordinator.events == [
        "begin-read-only-drain-lock",
        "record-snapshot-manifest",
        "release-after-fsync",
    ]
    expected_digest = hashlib.sha256(
        (vault / "tenants" / TENANT_A / "wiki" / "generations" / "7" / "manifest.json").read_bytes()
    ).hexdigest()
    assert coordinator.recorded_manifest == [
        {"tenant_id": TENANT_A, "generation": 7, "digest": expected_digest}
    ]
