"""Offline isolated restore verifier; it never starts customer-facing services."""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import json
import shutil
from pathlib import Path
from typing import Any


def _backup_module() -> Any:
    path = Path(__file__).with_name("backup.py")
    spec = importlib.util.spec_from_file_location("hulagu_backup_support", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("backup support unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RestoreStartupGate:
    def __init__(self, *, required_tombstones: set[str]) -> None:
        self._required = set(required_tombstones)
        self._applied: set[str] = set()

    def apply(self, tombstone_id: str) -> None:
        if tombstone_id in self._required:
            self._applied.add(tombstone_id)

    def enable_services(self) -> bool:
        if self._applied != self._required:
            raise PermissionError("all tombstones must be applied before service startup")
        raise PermissionError("semantic PostgreSQL verification tooling is required before service startup")


def verify_restore(
    backup_root: Path,
    restore_root: Path,
    *,
    encryption_key: bytes,
    signing_key: bytes,
    expected_active_generations: dict[str, int],
    tombstones: tuple[str, ...],
) -> dict[str, object]:
    manifest_bytes = (backup_root / "manifest.json").read_bytes()
    supplied_signature = (backup_root / "manifest.sig").read_text()
    expected_signature = hmac.new(signing_key, manifest_bytes, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise ValueError("backup manifest signature mismatch")
    manifest = json.loads(manifest_bytes)
    if manifest["active_generations"] != expected_active_generations:
        raise ValueError("backup authority mismatch")
    database_evidence = manifest.get("database_evidence")
    if not isinstance(database_evidence, dict) or database_evidence.get("status") != "manifest_files_verified":
        raise ValueError("database verification evidence is absent")
    backup = _backup_module()
    payload = json.loads(backup.decrypt_payload((backup_root / "payload.enc").read_bytes(), encryption_key))
    restore_root.mkdir(parents=True, mode=0o700)
    try:
        for relative, encoded in payload.items():
            path = Path(relative)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("unsafe restore path")
            target = restore_root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(base64.b64decode(encoded))
        manifest_files = {item["path"]: item for item in manifest["files"]}
        if set(payload) != set(manifest_files):
            raise ValueError("restore file manifest mismatch")
        for relative, item in manifest_files.items():
            restored = (restore_root / relative).read_bytes()
            if len(restored) != item["bytes"] or hashlib.sha256(restored).hexdigest() != item["sha256"]:
                raise ValueError("restored file checksum mismatch")
        for tenant, generation in expected_active_generations.items():
            root = restore_root / "tenants" / tenant / "wiki" / "generations" / str(generation)
            if not root.is_dir():
                raise ValueError("active generation missing after restore")
        restored_database_evidence = backup._verify_postgres_backup_files(
            backup._read_confined_tree(restore_root / "postgres")
        )
        if restored_database_evidence != database_evidence:
            raise ValueError("restored PostgreSQL backup evidence mismatch")
        artifact_entries = [item for item in manifest_files.values() if not str(item["path"]).startswith("postgres/")]
        artifact_digest = hashlib.sha256(
            json.dumps(artifact_entries, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return {
            "schema_version": "RestoreVerification/v1",
            "status": "INCOMPLETE_SEMANTIC_VERIFICATION",
            "startup_authorized": False,
            "evidence": {
                "manifest_signature": {
                    "status": "verified",
                    "algorithm": "hmac-sha256",
                    "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                },
                "payload_authentication": {"status": "verified", "algorithm": "hmac-sha256"},
                "postgres_backup_manifest": restored_database_evidence,
                "artifact_files": {
                    "status": "verified",
                    "count": len(artifact_entries),
                    "manifest_entries_sha256": artifact_digest,
                },
                "active_generations": {
                    "status": "verified",
                    "entries": manifest["artifact_generations"],
                },
                "tombstone_replay": {"status": "not_verified", "required_count": len(tombstones)},
            },
            "unverified_requirements": [
                "wal_replay",
                "postgres_data_checksums",
                "rls",
                "grants",
                "tenant_isolation",
                "non_routable_runtime",
                "credential_absence",
                "tombstone_replay",
            ],
        }
    finally:
        shutil.rmtree(restore_root, ignore_errors=True)
