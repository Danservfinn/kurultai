"""Typed tenant-principal and redaction guards for Hulagu hard isolation.

The helpers in this module are source-contract runtime scaffolding: they model the
objects every adapter must require before touching tenant data.  They deliberately
avoid ambient filesystem, database, Brain, Google, Telegram, or credential access.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from pathlib import PurePosixPath

HULAGU_VAULT_ROOT = PurePosixPath("/Volumes/KurultaiVault/hulagu")
HULAGU_PRODUCT_BRAIN_ROOT = HULAGU_VAULT_ROOT / "brain"
HULAGU_TENANTS_ROOT = HULAGU_VAULT_ROOT / "tenants"
KUBLAI_BRAIN_ROOT = PurePosixPath("/Users/kublai/brain")


@dataclass(frozen=True, slots=True)
class TenantPrincipal:
    """Unforgeable-in-code principal derived from trusted server state."""

    trusted_subject: str
    tenant_uuid: str
    lifecycle_epoch: int
    tenant_namespace: str
    feature_gates: frozenset[str]
    consented: bool
    deleted: bool
    support_authority: bool = False

    @classmethod
    def derive(
        cls,
        *,
        trusted_subject: str,
        tenant_uuid: str,
        lifecycle_epoch: int,
        feature_gates: frozenset[str] = frozenset(),
        consented: bool,
        deleted: bool,
        support_authority: bool = False,
    ) -> TenantPrincipal:
        """Derive a principal from trusted identity and server-resolved tenant state."""
        if not trusted_subject.startswith(("telegram-dm:", "support-approved:")):
            raise PermissionError("trusted private-DM or approved support subject required")
        normalized_uuid = str(uuid.UUID(tenant_uuid))
        if lifecycle_epoch < 1:
            raise PermissionError("active lifecycle epoch required")
        namespace = hashlib.sha256(f"{normalized_uuid}:{lifecycle_epoch}".encode()).hexdigest()[:24]
        return cls(
            trusted_subject=trusted_subject,
            tenant_uuid=normalized_uuid,
            lifecycle_epoch=lifecycle_epoch,
            tenant_namespace=namespace,
            feature_gates=frozenset(feature_gates),
            consented=consented,
            deleted=deleted,
            support_authority=support_authority,
        )

    def assert_runtime_allowed(self, *, required_gate: str | None = None) -> None:
        if not self.consented:
            raise PermissionError("tenant consent state required")
        if self.deleted:
            raise PermissionError("deletion state blocks tenant operation")
        if required_gate is not None and required_gate not in self.feature_gates:
            raise PermissionError(f"feature gate missing: {required_gate}")

    def assert_no_caller_authority(
        self,
        *,
        caller_supplied_tenant_uuid: str | None = None,
        caller_supplied_path: str | None = None,
        caller_supplied_google_artifact_id: str | None = None,
    ) -> None:
        if caller_supplied_tenant_uuid is not None:
            try:
                supplied = str(uuid.UUID(caller_supplied_tenant_uuid))
            except ValueError as exc:
                raise PermissionError("caller-supplied tenant authority rejected") from exc
            if supplied != self.tenant_uuid:
                raise PermissionError("caller-supplied tenant authority rejected")
            raise PermissionError("caller-supplied tenant authority rejected")
        if caller_supplied_path is not None:
            raise PermissionError("caller-supplied path authority rejected")
        if caller_supplied_google_artifact_id is not None:
            raise PermissionError("caller-supplied google artifact authority rejected")

    @property
    def tenant_root(self) -> PurePosixPath:
        return HULAGU_TENANTS_ROOT / self.tenant_uuid

    @property
    def wiki_root(self) -> PurePosixPath:
        return self.tenant_root / "wiki"

    @property
    def index_root(self) -> PurePosixPath:
        return self.tenant_root / "indexes"

    @property
    def cache_root(self) -> PurePosixPath:
        return self.tenant_root / "cache" / self.tenant_namespace

    @property
    def sheets_receipt_root(self) -> PurePosixPath:
        return self.tenant_root / "receipts" / "google_sheets"


_GOOGLE_DOCS_URL = re.compile(r"https://docs\.google\.com/[^\s)]+", re.IGNORECASE)
_EMAIL = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
_TENANT_UUID = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_SHEET_OR_DRIVE_ID = re.compile(r"\b(?:sheet|drive|perm)-[A-Za-z0-9_-]+\b")
_RAW_PATH = re.compile(r"(?:/Users/kublai/brain|/Volumes/KurultaiVault/hulagu/tenants)/[^\s]+")


def validate_operator_projection(payload: dict[str, object]) -> dict[str, object]:
    """Return a schema-limited operator projection or raise on tenant/private leakage."""
    allowed = {"schema", "event_type", "count", "error_class", "latency_bucket", "gate_status"}
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"operator projection field not allowed: {sorted(unknown)}")
    text = repr(payload)
    forbidden = [_GOOGLE_DOCS_URL, _EMAIL, _TENANT_UUID, _SHEET_OR_DRIVE_ID, _RAW_PATH]
    if any(pattern.search(text) for pattern in forbidden):
        raise ValueError("operator projection contains disallowed tenant/customer identifier")
    return dict(payload)


def public_brain_gateway_may_serve(path_or_query: str) -> bool:
    """Deny public gateway exposure for Hulagu product Brain or tenant trees."""
    normalized = path_or_query.replace("file://", "")
    return "/Volumes/KurultaiVault/hulagu" not in normalized and "hulagu/tenants" not in normalized


@dataclass(frozen=True, slots=True)
class BackupManifest:
    tenant_uuid: str
    lifecycle_epoch: int
    root: PurePosixPath
    artifact_digest: str


@dataclass(frozen=True, slots=True)
class DeletionTombstone:
    tenant_uuid: str
    lifecycle_epoch: int
    reason: str


@dataclass(frozen=True, slots=True)
class SheetArtifactRecord:
    tenant_uuid: str
    lifecycle_epoch: int
    local_artifact_id: str
    spreadsheet_id: str
    drive_file_id: str


class TenantScopedStore:
    """In-memory tenant filesystem/index/cache/export/backup boundary model."""

    def __init__(self) -> None:
        self._wiki: dict[PurePosixPath, str] = {}
        self._indexes: dict[tuple[str, int], dict[str, str]] = {}
        self._cache: dict[tuple[str, int], dict[str, str]] = {}
        self._exports: dict[PurePosixPath, str] = {}
        self._tombstones: dict[str, int] = {}

    def write_wiki(
        self, principal: TenantPrincipal, relative_path: str, content: str
    ) -> PurePosixPath:
        self._assert_live_epoch(principal)
        path = self._tenant_path(principal.wiki_root, relative_path)
        self._wiki[path] = content
        return path

    def read_wiki(self, principal: TenantPrincipal, path: PurePosixPath) -> str:
        self._assert_live_epoch(principal)
        if not self._is_inside(path, principal.wiki_root):
            raise PermissionError("tenant binding mismatch")
        return self._wiki[path]

    def index_document(self, principal: TenantPrincipal, document_id: str, text: str) -> None:
        self._assert_live_epoch(principal)
        self._indexes.setdefault((principal.tenant_uuid, principal.lifecycle_epoch), {})[
            document_id
        ] = text

    def search(self, principal: TenantPrincipal, query: str) -> list[str]:
        if self._tombstones.get(principal.tenant_uuid, -1) >= principal.lifecycle_epoch:
            return []
        scoped = self._indexes.get((principal.tenant_uuid, principal.lifecycle_epoch), {})
        return [doc_id for doc_id, text in scoped.items() if query in text]

    def search_all_tenants(self, _query: str) -> list[str]:
        raise PermissionError("global customer corpus search rejected")

    def put_cache(self, principal: TenantPrincipal, key: str, value: str) -> None:
        self._assert_live_epoch(principal)
        self._cache.setdefault((principal.tenant_uuid, principal.lifecycle_epoch), {})[key] = value

    def write_export(
        self, principal: TenantPrincipal, relative_path: str, content: str
    ) -> PurePosixPath:
        self._assert_live_epoch(principal)
        sanitized = _neutralize_csv(content)
        path = self._tenant_path(principal.tenant_root / "exports", relative_path)
        self._exports[path] = sanitized
        return path

    def create_backup_manifest(
        self, principal: TenantPrincipal, *, artifact_digest: str
    ) -> BackupManifest:
        self._assert_live_epoch(principal)
        return BackupManifest(
            tenant_uuid=principal.tenant_uuid,
            lifecycle_epoch=principal.lifecycle_epoch,
            root=principal.tenant_root / "backups",
            artifact_digest=artifact_digest,
        )

    def restore_backup(self, principal: TenantPrincipal, manifest: BackupManifest) -> None:
        self._assert_live_epoch(principal)
        if manifest.tenant_uuid != principal.tenant_uuid:
            raise PermissionError("cross-tenant restore rejected")
        if manifest.lifecycle_epoch != principal.lifecycle_epoch:
            raise PermissionError("stale lifecycle epoch rejected")

    def delete_tenant(self, principal: TenantPrincipal, *, reason: str) -> DeletionTombstone:
        self._tombstones[principal.tenant_uuid] = principal.lifecycle_epoch
        for path in tuple(self._wiki):
            if self._is_inside(path, principal.tenant_root):
                del self._wiki[path]
        self._indexes.pop((principal.tenant_uuid, principal.lifecycle_epoch), None)
        self._cache.pop((principal.tenant_uuid, principal.lifecycle_epoch), None)
        for path in tuple(self._exports):
            if self._is_inside(path, principal.tenant_root):
                del self._exports[path]
        return DeletionTombstone(
            tenant_uuid=principal.tenant_uuid,
            lifecycle_epoch=principal.lifecycle_epoch,
            reason=reason,
        )

    def _assert_live_epoch(self, principal: TenantPrincipal) -> None:
        principal.assert_runtime_allowed()
        tombstone_epoch = self._tombstones.get(principal.tenant_uuid)
        if tombstone_epoch is not None and principal.lifecycle_epoch <= tombstone_epoch:
            raise PermissionError("stale lifecycle epoch rejected")

    def _tenant_path(self, root: PurePosixPath, relative_path: str) -> PurePosixPath:
        candidate = PurePosixPath(relative_path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise PermissionError("caller-supplied path rejected")
        if any(part in {"", "."} for part in candidate.parts):
            raise PermissionError("caller-supplied path rejected")
        return root / candidate

    def _is_inside(self, path: PurePosixPath, root: PurePosixPath) -> bool:
        try:
            path.relative_to(root)
        except ValueError:
            return False
        return True


class FakeTenantRepository:
    """RLS/composite-FK model for tenant-owned Google artifact tables."""

    def __init__(self, *, force_rls: bool) -> None:
        self.force_rls = force_rls
        self._records: dict[str, SheetArtifactRecord] = {}

    def insert_sheet_artifact(
        self,
        principal: TenantPrincipal,
        spreadsheet_id: str,
        drive_file_id: str,
    ) -> SheetArtifactRecord:
        self._assert_rls(principal)
        local_id = f"artifact-{len(self._records) + 1}"
        record = SheetArtifactRecord(
            tenant_uuid=principal.tenant_uuid,
            lifecycle_epoch=principal.lifecycle_epoch,
            local_artifact_id=local_id,
            spreadsheet_id=spreadsheet_id,
            drive_file_id=drive_file_id,
        )
        self._records[local_id] = record
        return record

    def get_sheet_artifact(
        self, principal: TenantPrincipal, local_artifact_id: str
    ) -> SheetArtifactRecord:
        self._assert_rls(principal)
        record = self._records[local_artifact_id]
        if record.tenant_uuid != principal.tenant_uuid:
            raise PermissionError("RLS tenant scope denied cross-tenant row")
        if record.lifecycle_epoch != principal.lifecycle_epoch:
            raise PermissionError("stale lifecycle epoch rejected")
        return record

    def _assert_rls(self, principal: TenantPrincipal) -> None:
        if not self.force_rls:
            raise PermissionError("FORCE RLS required")
        principal.assert_runtime_allowed()


def _neutralize_csv(content: str) -> str:
    cells = content.split(",")
    return ",".join(
        "'" + cell if cell.lstrip().startswith(("=", "+", "-", "@")) else cell for cell in cells
    )
