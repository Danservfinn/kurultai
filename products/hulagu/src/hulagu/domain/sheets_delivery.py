"""Pure v4 Google Sheets delivery state machine with a fake provider.

This is intentionally a no-credentials/no-network adapter boundary.  Tests use the
fake provider to prove tenant binding, idempotency, readback gates, ACL gates,
redaction, and failure semantics before any real Google implementation exists.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from hulagu.domain.tenant_isolation import TenantPrincipal, validate_operator_projection

APPROVED_V4_PLAN_HASH = "270cef99d010de63290e315c03ab4d21e119befd816102d67baa48a211126184"


class SheetDeliveryStatus(StrEnum):
    SHEETS_DISABLED = "sheets_disabled"
    ACCOUNT_REQUIRED = "account_required"
    CREATE_REQUESTED = "create_requested"
    CREATE_IN_FLIGHT = "create_in_flight"
    CREATED_READBACK_PENDING = "created_readback_pending"
    POPULATE_REQUESTED = "populate_requested"
    POPULATE_IN_FLIGHT = "populate_in_flight"
    CONTENT_READBACK_PENDING = "content_readback_pending"
    SHARE_REQUESTED = "share_requested"
    SHARE_IN_FLIGHT = "share_in_flight"
    ACL_READBACK_PENDING = "acl_readback_pending"
    URL_READBACK_PENDING = "url_readback_pending"
    READY_FOR_TELEGRAM_OUTBOX = "ready_for_telegram_outbox"
    TELEGRAM_OUTBOX_QUEUED = "telegram_outbox_queued"
    REVOKE_REQUESTED = "revoke_requested"
    REVOKED = "revoked"
    DELETE_REQUESTED = "delete_requested"
    DELETED_CONFIRMED = "deleted_confirmed"
    ERROR_RETRY_WAIT = "error_retry_wait"
    ERROR_NEEDS_OPERATOR = "error_needs_operator"
    QUOTA_WAIT = "quota_wait"


class SheetRole(StrEnum):
    READER = "reader"
    COMMENTER = "commenter"
    WRITER = "writer"


class ProviderAmbiguousError(RuntimeError):
    pass


class ProviderQuotaError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GoogleAccount:
    normalized: str
    recipient_hash: str
    is_confirmed: bool

    @classmethod
    def confirmed(cls, address: str, *, nonce: str) -> GoogleAccount:
        normalized = address.strip().casefold()
        if not re.fullmatch(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", normalized):
            raise ValueError("confirmed Google account must be a valid email")
        digest = hashlib.sha256(f"{normalized}:{nonce}".encode()).hexdigest()
        return cls(normalized=normalized, recipient_hash=digest, is_confirmed=True)


@dataclass(frozen=True, slots=True)
class TenantCandidateRow:
    candidate_id: str
    tenant_local_sequence: int
    candidate_status: str
    role_title: str
    company_name: str
    location_text: str
    remote_policy: str
    employment_type: str
    compensation_public_text: str
    source_name: str
    source_url: str
    source_retrieved_at: str
    fit_score_bucket: str
    fit_rationale_public_facts: str
    customer_action: str
    customer_note: str
    last_synced_at: str
    row_version: int

    def to_sheet_row(self) -> dict[str, str | int]:
        row = asdict(self)
        return {
            key: _neutralize_formula(value) if isinstance(value, str) else value
            for key, value in row.items()
        }


@dataclass(frozen=True, slots=True)
class TemplateManifest:
    template_sha256: str
    columns: tuple[str, ...]
    derivation_mode: str
    rows: list[dict[str, str]]

    @classmethod
    def load(cls, manifest_path: Path, *, template_path: Path) -> TemplateManifest:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        template_bytes = template_path.read_bytes()
        template_sha = hashlib.sha256(template_bytes).hexdigest()
        expected = raw["template_sha256"]
        if template_sha != expected:
            raise ValueError("template sha256 mismatch")
        rows = list(csv.DictReader(template_bytes.decode("utf-8").splitlines()))
        columns = tuple(raw["sheet_contract"]["blank_template_columns"])
        header = tuple(template_bytes.decode("utf-8").splitlines()[0].split(","))
        if rows:
            raise ValueError("template must be header-only")
        if header != columns:
            raise ValueError("template header does not match manifest columns")
        derivation = raw["derivation_mode"]
        if "no live cell" not in derivation or "ACL" not in derivation:
            raise ValueError("manifest must record no-live-copy derivation")
        return cls(
            template_sha256=template_sha,
            columns=columns,
            derivation_mode=derivation,
            rows=rows,
        )


@dataclass(slots=True)
class FakeSheetArtifact:
    tenant_uuid: str
    lifecycle_epoch: int
    idempotency_key: str
    spreadsheet_id: str
    drive_file_id: str
    title_digest: str
    url: str
    rows: list[dict[str, str | int]] = field(default_factory=list)
    row_digest: str | None = None
    permission_id: str | None = None
    recipient_hash: str | None = None
    role: SheetRole | None = None
    revoked: bool = False
    deleted: bool = False


@dataclass(frozen=True, slots=True)
class SheetDeliveryReceipt:
    status: SheetDeliveryStatus
    outbox_ready: bool
    spreadsheet_id: str | None = None
    drive_file_id: str | None = None
    url: str | None = None
    row_count: int = 0
    row_digest: str | None = None
    acl_recipient_hash: str | None = None
    role: SheetRole | None = None
    audit_projection: dict[str, object] = field(default_factory=dict)
    error_class: str | None = None


class FakeGoogleSheetsProvider:
    """In-memory provider that records calls and simulates readbacks."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.artifacts: dict[str, FakeSheetArtifact] = {}
        self._by_idempotency: dict[tuple[str, int, str], str] = {}
        self.fail_next_create: Exception | None = None
        self.force_wrong_acl_recipient = False

    def create_blank_spreadsheet(
        self,
        principal: TenantPrincipal,
        *,
        idempotency_key: str,
        title_digest: str,
    ) -> FakeSheetArtifact:
        self.calls.append("create_blank_spreadsheet")
        if self.fail_next_create is not None:
            exc = self.fail_next_create
            self.fail_next_create = None
            raise exc
        lookup = (principal.tenant_uuid, principal.lifecycle_epoch, idempotency_key)
        if lookup in self._by_idempotency:
            return self.artifacts[self._by_idempotency[lookup]]
        number = len(self.artifacts) + 1
        spreadsheet_id = f"sheet-{number:04d}"
        artifact = FakeSheetArtifact(
            tenant_uuid=principal.tenant_uuid,
            lifecycle_epoch=principal.lifecycle_epoch,
            idempotency_key=idempotency_key,
            spreadsheet_id=spreadsheet_id,
            drive_file_id=f"drive-{number:04d}",
            title_digest=title_digest,
            url=f"https://docs.google.invalid/spreadsheets/d/{spreadsheet_id}",
        )
        self.artifacts[spreadsheet_id] = artifact
        self._by_idempotency[lookup] = spreadsheet_id
        return artifact

    def populate(self, artifact: FakeSheetArtifact, rows: list[dict[str, str | int]]) -> None:
        self.calls.append("populate")
        artifact.rows = rows
        artifact.row_digest = _digest(rows)

    def share(self, artifact: FakeSheetArtifact, *, recipient_hash: str, role: SheetRole) -> None:
        self.calls.append("share")
        artifact.permission_id = f"perm-{artifact.spreadsheet_id}"
        artifact.recipient_hash = (
            "wrong-recipient" if self.force_wrong_acl_recipient else recipient_hash
        )
        artifact.role = role

    def readback(self, spreadsheet_id: str) -> FakeSheetArtifact:
        self.calls.append("readback")
        return self.artifacts[spreadsheet_id]

    def artifact_for(self, spreadsheet_id: str) -> FakeSheetArtifact:
        return self.artifacts[spreadsheet_id]

    def lookup_by_idempotency(
        self,
        principal: TenantPrincipal,
        *,
        idempotency_key: str,
    ) -> FakeSheetArtifact | None:
        spreadsheet_id = self._by_idempotency.get(
            (principal.tenant_uuid, principal.lifecycle_epoch, idempotency_key)
        )
        if spreadsheet_id is None:
            return None
        return self.artifacts[spreadsheet_id]

    def revoke(self, principal: TenantPrincipal, *, spreadsheet_id: str) -> SheetDeliveryReceipt:
        artifact = self._artifact_for_principal(principal, spreadsheet_id)
        artifact.revoked = True
        return SheetDeliveryReceipt(status=SheetDeliveryStatus.REVOKED, outbox_ready=False)

    def delete(self, principal: TenantPrincipal, *, spreadsheet_id: str) -> SheetDeliveryReceipt:
        artifact = self._artifact_for_principal(principal, spreadsheet_id)
        artifact.deleted = True
        return SheetDeliveryReceipt(
            status=SheetDeliveryStatus.DELETED_CONFIRMED, outbox_ready=False
        )

    def _artifact_for_principal(
        self,
        principal: TenantPrincipal,
        spreadsheet_id: str,
    ) -> FakeSheetArtifact:
        artifact = self.artifacts[spreadsheet_id]
        if artifact.tenant_uuid != principal.tenant_uuid:
            raise PermissionError("tenant binding mismatch")
        if artifact.lifecycle_epoch != principal.lifecycle_epoch:
            raise PermissionError("lifecycle epoch mismatch")
        return artifact


@dataclass(frozen=True, slots=True)
class CustomerEditPolicy:
    import_formulas_enabled: bool = False
    import_comments_enabled: bool = False

    @classmethod
    def default(cls) -> CustomerEditPolicy:
        return cls()

    def may_import_formula(self, value: str) -> bool:
        return self.import_formulas_enabled and not value.lstrip().startswith(("=", "+", "-", "@"))

    def may_import_comment(self, _value: str) -> bool:
        return self.import_comments_enabled


@dataclass(slots=True)
class SheetsDeliveryService:
    provider: FakeGoogleSheetsProvider
    manifest: TemplateManifest

    def create_populate_share_outbox_ready(
        self,
        principal: TenantPrincipal,
        *,
        approved_plan_hash: str,
        google_account: GoogleAccount | None,
        rows: list[TenantCandidateRow],
        role: SheetRole = SheetRole.COMMENTER,
        idempotency_key: str = "default-idempotency-key",
        caller_supplied_tenant_uuid: str | None = None,
        caller_supplied_sheet_id: str | None = None,
    ) -> SheetDeliveryReceipt:
        if approved_plan_hash != APPROVED_V4_PLAN_HASH:
            raise PermissionError("approved v4 plan hash required")
        principal.assert_no_caller_authority(
            caller_supplied_tenant_uuid=caller_supplied_tenant_uuid,
            caller_supplied_google_artifact_id=caller_supplied_sheet_id,
        )
        principal.assert_runtime_allowed(required_gate="google_sheets_v4")
        if google_account is None or not google_account.is_confirmed:
            return SheetDeliveryReceipt(
                status=SheetDeliveryStatus.ACCOUNT_REQUIRED, outbox_ready=False
            )
        title_digest = hashlib.sha256(
            f"{principal.tenant_namespace}:{principal.lifecycle_epoch}:job-ops".encode()
        ).hexdigest()
        sheet_rows = [row.to_sheet_row() for row in rows]
        try:
            artifact = self.provider.create_blank_spreadsheet(
                principal,
                idempotency_key=idempotency_key,
                title_digest=title_digest,
            )
        except ProviderQuotaError as exc:
            return self._blocked(SheetDeliveryStatus.QUOTA_WAIT, exc)
        except ProviderAmbiguousError as exc:
            existing = self.provider.lookup_by_idempotency(
                principal,
                idempotency_key=idempotency_key,
            )
            if existing is not None:
                ready = self._ready_receipt_if_artifact_ready(
                    existing,
                    google_account=google_account,
                    role=role,
                )
                if ready is not None:
                    return ready
            return self._blocked(SheetDeliveryStatus.ERROR_RETRY_WAIT, exc)
        ready = self._ready_receipt_if_artifact_ready(
            artifact,
            google_account=google_account,
            role=role,
        )
        if ready is not None:
            return ready
        self.provider.populate(artifact, sheet_rows)
        content = self.readback_for_principal(principal, spreadsheet_id=artifact.spreadsheet_id)
        expected_row_digest = _digest(sheet_rows)
        if content.row_digest != expected_row_digest or len(content.rows) != len(rows):
            return self._blocked(
                SheetDeliveryStatus.ERROR_NEEDS_OPERATOR, RuntimeError("content mismatch")
            )
        self.provider.share(artifact, recipient_hash=google_account.recipient_hash, role=role)
        acl = self.readback_for_principal(principal, spreadsheet_id=artifact.spreadsheet_id)
        if acl.recipient_hash != google_account.recipient_hash or acl.role is not role:
            return self._blocked(
                SheetDeliveryStatus.ERROR_NEEDS_OPERATOR, RuntimeError("ACL mismatch")
            )
        url_readback = self.readback_for_principal(
            principal, spreadsheet_id=artifact.spreadsheet_id
        )
        if not url_readback.url.endswith(url_readback.spreadsheet_id):
            return self._blocked(
                SheetDeliveryStatus.ERROR_NEEDS_OPERATOR, RuntimeError("URL mismatch")
            )
        projection = validate_operator_projection(
            {
                "schema": "hulagu.operator_projection.v1",
                "event_type": "sheets_delivery_ready",
                "count": len(rows),
                "gate_status": "synthetic_ready",
            }
        )
        return SheetDeliveryReceipt(
            status=SheetDeliveryStatus.READY_FOR_TELEGRAM_OUTBOX,
            outbox_ready=True,
            spreadsheet_id=url_readback.spreadsheet_id,
            drive_file_id=url_readback.drive_file_id,
            url=url_readback.url,
            row_count=len(rows),
            row_digest=url_readback.row_digest,
            acl_recipient_hash=url_readback.recipient_hash,
            role=url_readback.role,
            audit_projection=projection,
        )

    def _ready_receipt_if_artifact_ready(
        self,
        artifact: FakeSheetArtifact,
        *,
        google_account: GoogleAccount,
        role: SheetRole,
    ) -> SheetDeliveryReceipt | None:
        if artifact.row_digest is None:
            return None
        if artifact.recipient_hash != google_account.recipient_hash or artifact.role is not role:
            return None
        if not artifact.url.endswith(artifact.spreadsheet_id):
            return None
        projection = validate_operator_projection(
            {
                "schema": "hulagu.operator_projection.v1",
                "event_type": "sheets_delivery_ready",
                "count": len(artifact.rows),
                "gate_status": "synthetic_ready",
            }
        )
        return SheetDeliveryReceipt(
            status=SheetDeliveryStatus.READY_FOR_TELEGRAM_OUTBOX,
            outbox_ready=True,
            spreadsheet_id=artifact.spreadsheet_id,
            drive_file_id=artifact.drive_file_id,
            url=artifact.url,
            row_count=len(artifact.rows),
            row_digest=artifact.row_digest,
            acl_recipient_hash=artifact.recipient_hash,
            role=artifact.role,
            audit_projection=projection,
        )

    def readback_for_principal(
        self,
        principal: TenantPrincipal,
        *,
        spreadsheet_id: str,
    ) -> FakeSheetArtifact:
        artifact = self.provider.readback(spreadsheet_id)
        if artifact.tenant_uuid != principal.tenant_uuid:
            raise PermissionError("tenant binding mismatch")
        if artifact.lifecycle_epoch != principal.lifecycle_epoch:
            raise PermissionError("lifecycle epoch mismatch")
        return artifact

    def _blocked(self, status: SheetDeliveryStatus, exc: Exception) -> SheetDeliveryReceipt:
        return SheetDeliveryReceipt(
            status=status,
            outbox_ready=False,
            error_class=exc.__class__.__name__,
        )


def _neutralize_formula(value: str) -> str:
    stripped = value.lstrip()
    if stripped.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value.replace("=HYPERLINK", "'HYPERLINK")


def _digest(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
