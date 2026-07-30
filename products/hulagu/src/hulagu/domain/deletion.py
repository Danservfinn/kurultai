"""Fenced, restartable deletion domain and tombstone-key lifecycle."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

PRIVACY_NOTICE = (
    "When deletion completes, live data is erased immediately; encrypted backup copies expire within 90 days. "
    "Messages already accepted by Telegram cannot be revoked."
)


class DeletionPhase(str, Enum):
    CONFIRMED = "confirmed"
    DRAINED = "drained"
    ERASED = "erased"
    DELIVERY_PENDING = "delivery_pending"
    FINALIZED = "finalized"


@dataclass(frozen=True, slots=True)
class DeletionJob:
    deletion_id: str
    phase: DeletionPhase
    deletion_epoch: int
    expires_at: str
    delivery_outcome: str | None = None


def _xor(value: bytes, key: bytes, nonce: bytes, domain: bytes) -> bytes:
    stream = bytearray()
    counter = 0
    while len(stream) < len(value):
        stream.extend(hashlib.sha256(key + nonce + domain + counter.to_bytes(4, "big")).digest())
        counter += 1
    return bytes(byte ^ stream[index] for index, byte in enumerate(value))


class TombstoneFence:
    """Privileged encrypted subject fence with explicit overlap/re-key rules."""

    def __init__(self, keys: dict[int, bytes], active_version: int) -> None:
        if active_version not in keys or any(len(key) < 16 for key in keys.values()):
            raise ValueError("invalid tombstone keys")
        self._keys = dict(keys)
        self._active = active_version
        self._revoked: set[int] = set()

    def activate(self, version: int) -> None:
        if version not in self._keys or version in self._revoked:
            raise ValueError("unknown tombstone key")
        self._active = version

    def _subject(self, bot_id: int, actor_id: int) -> bytes:
        return f"hulagu.deletion-subject.v1\0{bot_id}\0{actor_id}".encode()

    def _seal(self, value: bytes, version: int) -> str:
        key = self._keys[version]
        nonce = os.urandom(16)
        ciphertext = _xor(value, key, nonce, b"hulagu.tombstone.v1")
        tag = hmac.new(key, b"hulagu.tombstone.v1\0" + nonce + ciphertext, hashlib.sha256).digest()
        envelope = base64.urlsafe_b64encode(version.to_bytes(4, "big") + nonce + ciphertext + tag).decode()
        return f"hts1.{envelope}"

    def _open(self, value: str) -> tuple[int, bytes]:
        if not value.startswith("hts1."):
            raise ValueError("invalid tombstone")
        try:
            packed = base64.b64decode(value.removeprefix("hts1."), altchars=b"-_", validate=True)
        except (ValueError, UnicodeEncodeError) as exc:
            raise ValueError("invalid tombstone") from exc
        if len(packed) < 53:
            raise ValueError("invalid tombstone")
        version = int.from_bytes(packed[:4], "big")
        if version in self._revoked or version not in self._keys:
            raise ValueError("unavailable tombstone key")
        nonce, ciphertext, tag = packed[4:20], packed[20:-32], packed[-32:]
        key = self._keys[version]
        expected = hmac.new(key, b"hulagu.tombstone.v1\0" + nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected):
            raise ValueError("invalid tombstone")
        return version, _xor(ciphertext, key, nonce, b"hulagu.tombstone.v1")

    def create(
        self,
        bot_id: int,
        actor_id: int,
        *,
        deletion_epoch: int,
        completed_at: datetime,
        horizon: datetime,
    ) -> dict[str, object]:
        encrypted_digest = self.protect_subject(bot_id, actor_id)
        return self.create_from_protected_digest(
            encrypted_digest,
            deletion_epoch=deletion_epoch,
            completed_at=completed_at,
            horizon=horizon,
        )

    def protect_subject(self, bot_id: int, actor_id: int) -> str:
        digest = hashlib.sha256(self._subject(bot_id, actor_id)).digest()
        return self._seal(digest, self._active)

    def create_from_protected_digest(
        self,
        encrypted_digest: str,
        *,
        deletion_epoch: int,
        completed_at: datetime,
        horizon: datetime,
    ) -> dict[str, object]:
        _version, digest = self._open(encrypted_digest)
        if len(digest) != hashlib.sha256().digest_size:
            raise ValueError("invalid protected tombstone digest")
        return {
            "schema_version": "DeletionTombstone/v1",
            "encrypted_subject_digest": encrypted_digest,
            "deletion_epoch": deletion_epoch,
            "completed_at": completed_at.isoformat(),
            "backup_expiry_horizon": horizon.isoformat(),
            "rekey_state": "current",
        }

    def matches(self, tombstone: dict[str, object], bot_id: int, actor_id: int, *, now: datetime) -> bool:
        if now >= datetime.fromisoformat(str(tombstone["backup_expiry_horizon"])):
            return False
        _version, stored = self._open(str(tombstone["encrypted_subject_digest"]))
        expected = hashlib.sha256(self._subject(bot_id, actor_id)).digest()
        return hmac.compare_digest(stored, expected)

    def rekey(self, tombstone: dict[str, object]) -> dict[str, object]:
        _version, digest = self._open(str(tombstone["encrypted_subject_digest"]))
        result = dict(tombstone)
        result["encrypted_subject_digest"] = self._seal(digest, self._active)
        result["rekey_state"] = "current"
        return result

    def revoke(
        self,
        version: int,
        *,
        tombstones: tuple[dict[str, object], ...] = (),
        now: datetime | None = None,
    ) -> None:
        for tombstone in tombstones:
            envelope_version, _digest = self._open(str(tombstone["encrypted_subject_digest"]))
            horizon = datetime.fromisoformat(str(tombstone["backup_expiry_horizon"]))
            if envelope_version == version and (now is None or now < horizon):
                raise PermissionError("applicable tombstones must re-key before revocation")
        self._revoked.add(version)

    def backup_key_state(self) -> dict[int, bytes]:
        return dict(self._keys)

    @classmethod
    def restore(cls, keys: dict[int, bytes], *, active_version: int) -> TombstoneFence:
        return cls(keys, active_version)


_DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)


def _erase_directory_contents(directory_fd: int) -> None:
    for name in sorted(os.listdir(directory_fd)):
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if stat.S_ISDIR(metadata.st_mode):
            child_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=directory_fd)
            try:
                opened = os.fstat(child_fd)
                if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
                    raise ValueError("tenant directory changed during erasure")
                _erase_directory_contents(child_fd)
            finally:
                os.close(child_fd)
            os.rmdir(name, dir_fd=directory_fd)
        elif stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            os.unlink(name, dir_fd=directory_fd)
        else:
            raise ValueError("tenant directory contains unsupported filesystem entry")
    os.fsync(directory_fd)


def erase_tenant_directory(tenants_root: Path, tenant_id: str) -> None:
    """Erase one UUID-named tenant below a trusted root without following links."""
    if str(UUID(tenant_id)) != tenant_id:
        raise ValueError("invalid tenant erasure target")
    try:
        root_metadata = os.stat(tenants_root, follow_symlinks=False)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
        raise ValueError("tenant root must be a no-follow directory")
    root_fd = os.open(tenants_root, _DIRECTORY_FLAGS)
    try:
        opened_root = os.fstat(root_fd)
        if (opened_root.st_dev, opened_root.st_ino) != (root_metadata.st_dev, root_metadata.st_ino):
            raise ValueError("tenant root changed during erasure")
        try:
            target_metadata = os.stat(tenant_id, dir_fd=root_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        if stat.S_ISLNK(target_metadata.st_mode):
            raise ValueError("tenant erasure target is a symlink")
        if not stat.S_ISDIR(target_metadata.st_mode):
            raise ValueError("tenant erasure target is not a directory")
        target_fd = os.open(tenant_id, _DIRECTORY_FLAGS, dir_fd=root_fd)
        try:
            opened_target = os.fstat(target_fd)
            if (opened_target.st_dev, opened_target.st_ino) != (
                target_metadata.st_dev,
                target_metadata.st_ino,
            ):
                raise ValueError("tenant erasure target changed during open")
            _erase_directory_contents(target_fd)
        finally:
            os.close(target_fd)
        os.rmdir(tenant_id, dir_fd=root_fd)
        os.fsync(root_fd)
        try:
            os.stat(tenant_id, dir_fd=root_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        raise RuntimeError("tenant erasure target remains after deletion")
    finally:
        os.close(root_fd)


class MemoryDeletionWorkflow:
    """Durable reference workflow used to exercise each restart boundary."""

    def __init__(self, state_path: Path, tenants_root: Path, *, tombstone_fence: TombstoneFence) -> None:
        self._state_path = state_path
        self._tenants_root = tenants_root
        self._tombstone_fence = tombstone_fence
        self._state: dict[str, Any] = {"tenants": {}, "jobs": {}, "tombstones": {}, "receipts": {}}
        if state_path.exists():
            self._state = json.loads(state_path.read_text())

    @classmethod
    def open(
        cls, state_path: Path, tenants_root: Path, *, tombstone_fence: TombstoneFence
    ) -> MemoryDeletionWorkflow:
        return cls(state_path, tenants_root, tombstone_fence=tombstone_fence)

    def _persist(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._state, sort_keys=True, separators=(",", ":")))
        os.replace(temporary, self._state_path)

    def seed_tenant(
        self,
        tenant_id: UUID,
        *,
        lifecycle_epoch: int,
        nonce: str,
        bot_id: int,
        actor_id: int,
        encrypted_route: str,
        route_generation: int,
        route_binding_digest: str,
        rows: dict[str, str],
        ordinary_outbox: tuple[str, ...],
        active_work: tuple[str, ...],
    ) -> None:
        self._state["tenants"][str(tenant_id)] = {
            "lifecycle_epoch": lifecycle_epoch,
            "nonce_hash": hashlib.sha256(nonce.encode()).hexdigest(),
            "subject_ciphertext": self._tombstone_fence.protect_subject(bot_id, actor_id),
            "encrypted_route": encrypted_route,
            "route_generation": route_generation,
            "route_binding_digest": route_binding_digest,
            "rows": rows,
            "ordinary_outbox": list(ordinary_outbox),
            "active_work": list(active_work),
            "identity_enabled": True,
            "claims_allowed": True,
        }
        self._persist()

    def confirm(self, tenant_id: UUID, *, nonce: str, expected_epoch: int, now: datetime) -> DeletionJob:
        tenant = self._state["tenants"].get(str(tenant_id))
        if (
            tenant is None
            or not tenant["identity_enabled"]
            or tenant["lifecycle_epoch"] != expected_epoch
            or not hmac.compare_digest(tenant["nonce_hash"], hashlib.sha256(nonce.encode()).hexdigest())
        ):
            raise PermissionError("invalid or consumed deletion authority")
        tenant["lifecycle_epoch"] += 1
        tenant["identity_enabled"] = False
        tenant["claims_allowed"] = False
        tenant["ordinary_outbox"] = []
        tenant["nonce_hash"] = None
        deletion_id = str(uuid4())
        self._state["jobs"][deletion_id] = {
            "deletion_id": deletion_id,
            "phase": DeletionPhase.CONFIRMED.value,
            "deletion_epoch": tenant["lifecycle_epoch"],
            "expires_at": (now + timedelta(days=30)).isoformat(),
            "target": str(tenant_id),
            "subject_ciphertext": tenant["subject_ciphertext"],
            "encrypted_route": tenant["encrypted_route"],
            "route_generation": tenant["route_generation"],
            "route_binding_digest": tenant["route_binding_digest"],
            "delivery_outcome": None,
        }
        self._persist()
        return self.job(deletion_id)

    def job(self, deletion_id: str) -> DeletionJob:
        value = self._state["jobs"][deletion_id]
        return DeletionJob(deletion_id, DeletionPhase(value["phase"]), value["deletion_epoch"], value["expires_at"], value["delivery_outcome"])

    def advance(self, deletion_id: str, *, now: datetime) -> DeletionJob:
        value = self._state["jobs"][deletion_id]
        phase = DeletionPhase(value["phase"])
        if phase is DeletionPhase.CONFIRMED:
            target = value["target"]
            if target in self._state["tenants"]:
                self._state["tenants"][target]["active_work"] = []
            value["phase"] = DeletionPhase.DRAINED.value
        elif phase is DeletionPhase.DRAINED:
            target = value["target"]
            erase_tenant_directory(self._tenants_root, target)
            self._state["tenants"].pop(target, None)
            value["target"] = None
            value["phase"] = DeletionPhase.ERASED.value
        elif phase is DeletionPhase.ERASED:
            value["phase"] = DeletionPhase.DELIVERY_PENDING.value
        elif phase is DeletionPhase.DELIVERY_PENDING:
            if value["delivery_outcome"] not in {"delivered", "delivery_unknown", "failed", "expired"}:
                raise PermissionError("delivery outcome is not terminal")
            opaque_receipt = hashlib.sha256(f"hulagu.deletion-receipt.v1\0{deletion_id}".encode()).hexdigest()
            self._state["tombstones"][deletion_id] = self._tombstone_fence.create_from_protected_digest(
                value["subject_ciphertext"],
                deletion_epoch=value["deletion_epoch"],
                completed_at=now,
                horizon=now + timedelta(days=97),
            )
            self._state["receipts"][deletion_id] = {
                "schema_version": "DeletionReceipt/v1",
                "opaque_receipt_id": opaque_receipt,
                "outcome": value["delivery_outcome"],
                "completed_at": now.isoformat(),
                "expires_at": (now + timedelta(days=365)).isoformat(),
            }
            for key in ("subject_ciphertext", "encrypted_route", "route_generation", "route_binding_digest"):
                value.pop(key, None)
            value["phase"] = DeletionPhase.FINALIZED.value
        self._persist()
        return self.job(deletion_id)

    def record_delivery(self, deletion_id: str, outcome: str, *, now: datetime) -> None:
        value = self._state["jobs"][deletion_id]
        if DeletionPhase(value["phase"]) is not DeletionPhase.DELIVERY_PENDING or now > datetime.fromisoformat(value["expires_at"]):
            raise PermissionError("invalid deletion delivery authority")
        if outcome not in {"delivered", "delivery_unknown", "failed", "expired"}:
            raise ValueError("invalid deletion delivery outcome")
        value["delivery_outcome"] = outcome
        self._persist()

    def tenant_exists(self, tenant_id: UUID) -> bool:
        return str(tenant_id) in self._state["tenants"]

    def lifecycle_epoch(self, tenant_id: UUID) -> int:
        return int(self._state["tenants"][str(tenant_id)]["lifecycle_epoch"])

    def identity_enabled(self, tenant_id: UUID) -> bool:
        return bool(self._state["tenants"].get(str(tenant_id), {}).get("identity_enabled", False))

    def claims_allowed(self, tenant_id: UUID) -> bool:
        return bool(self._state["tenants"].get(str(tenant_id), {}).get("claims_allowed", False))

    def claim_ordinary_outbox(self, tenant_id: UUID) -> tuple[str, ...]:
        tenant = self._state["tenants"].get(str(tenant_id))
        if tenant is None or not tenant["claims_allowed"]:
            return ()
        return tuple(tenant["ordinary_outbox"])

    def complete_old_work(self, tenant_id: UUID, work_id: str, *, lifecycle_epoch: int) -> bool:
        tenant = self._state["tenants"].get(str(tenant_id))
        return bool(tenant and tenant["claims_allowed"] and tenant["lifecycle_epoch"] == lifecycle_epoch and work_id in tenant["active_work"])

    def tombstone(self, deletion_id: str) -> dict[str, object]:
        return dict(self._state["tombstones"][deletion_id])

    def receipt(self, deletion_id: str) -> dict[str, object]:
        return dict(self._state["receipts"][deletion_id])

    def serialized_state_text(self) -> str:
        return json.dumps(self._state, sort_keys=True)
