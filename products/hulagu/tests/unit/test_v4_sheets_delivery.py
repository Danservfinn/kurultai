from __future__ import annotations

from pathlib import Path

import pytest

from hulagu.domain.sheets_delivery import (
    CustomerEditPolicy,
    FakeGoogleSheetsProvider,
    GoogleAccount,
    ProviderAmbiguousError,
    ProviderQuotaError,
    SheetDeliveryStatus,
    SheetRole,
    SheetsDeliveryService,
    TemplateManifest,
    TenantCandidateRow,
)
from hulagu.domain.tenant_isolation import TenantPrincipal

REPO_ROOT = Path(__file__).parents[2]
TEMPLATE_PATH = REPO_ROOT / "templates/google_sheets/job_ops_blank_template_v4.csv"
MANIFEST_PATH = REPO_ROOT / "templates/google_sheets/job_ops_blank_template_v4.manifest.json"
APPROVED_PLAN_HASH = "270cef99d010de63290e315c03ab4d21e119befd816102d67baa48a211126184"


def _principal(tenant_uuid: str = "11111111-1111-4111-8111-111111111111") -> TenantPrincipal:
    return TenantPrincipal.derive(
        trusted_subject="telegram-dm:subject-a",
        tenant_uuid=tenant_uuid,
        lifecycle_epoch=3,
        feature_gates=frozenset({"google_sheets_v4"}),
        consented=True,
        deleted=False,
    )


def test_template_manifest_is_header_only_and_exact_hash_bound() -> None:
    manifest = TemplateManifest.load(MANIFEST_PATH, template_path=TEMPLATE_PATH)

    assert (
        manifest.template_sha256
        == "bf7f0ad57a3cccf4c019c32d31961aa970d57085970f62bdfc67a5f6e59e38e5"
    )
    assert manifest.columns[0] == "candidate_id"
    assert manifest.columns[-1] == "row_version"
    assert manifest.rows == []
    assert "no live cell" in manifest.derivation_mode


def test_delivery_rejects_caller_supplied_tenant_or_sheet_authority_before_provider_calls() -> None:
    provider = FakeGoogleSheetsProvider()
    service = SheetsDeliveryService(
        provider=provider,
        manifest=TemplateManifest.load(MANIFEST_PATH, template_path=TEMPLATE_PATH),
    )
    principal = _principal()

    with pytest.raises(PermissionError, match="caller-supplied tenant authority"):
        service.create_populate_share_outbox_ready(
            principal,
            approved_plan_hash=APPROVED_PLAN_HASH,
            google_account=GoogleAccount.confirmed("Customer@Example.com", nonce="n1"),
            rows=[],
            caller_supplied_tenant_uuid="22222222-2222-4222-8222-222222222222",
        )

    with pytest.raises(PermissionError, match="caller-supplied google artifact"):
        service.create_populate_share_outbox_ready(
            principal,
            approved_plan_hash=APPROVED_PLAN_HASH,
            google_account=GoogleAccount.confirmed("Customer@Example.com", nonce="n1"),
            rows=[],
            caller_supplied_sheet_id="sheet-other",
        )

    assert provider.calls == []


def test_two_tenant_synthetic_e2e_reaches_outbox_only_after_content_acl_url_readbacks() -> None:
    provider = FakeGoogleSheetsProvider()
    service = SheetsDeliveryService(
        provider=provider,
        manifest=TemplateManifest.load(MANIFEST_PATH, template_path=TEMPLATE_PATH),
    )
    tenant_a = _principal("11111111-1111-4111-8111-111111111111")
    tenant_b = _principal("22222222-2222-4222-8222-222222222222")

    rows = [
        TenantCandidateRow(
            candidate_id="tenant-local-1",
            tenant_local_sequence=1,
            candidate_status="new",
            role_title="ML Engineer",
            company_name="Synthetic Corp",
            location_text="Remote",
            remote_policy="remote",
            employment_type="full-time",
            compensation_public_text="customer provided range",
            source_name="Synthetic Source",
            source_url="https://example.invalid/job/1",
            source_retrieved_at="2026-07-25T00:00:00Z",
            fit_score_bucket="high",
            fit_rationale_public_facts="Public facts only",
            customer_action="review",
            customer_note='literal =HYPERLINK("https://evil.invalid") text',
            last_synced_at="2026-07-25T00:01:00Z",
            row_version=1,
        )
    ]
    result = service.create_populate_share_outbox_ready(
        tenant_a,
        approved_plan_hash=APPROVED_PLAN_HASH,
        google_account=GoogleAccount.confirmed("Customer@Example.com", nonce="n1"),
        rows=rows,
        role=SheetRole.COMMENTER,
    )

    assert result.status is SheetDeliveryStatus.READY_FOR_TELEGRAM_OUTBOX
    assert result.outbox_ready is True
    assert result.spreadsheet_id is not None
    assert result.url is not None
    assert result.spreadsheet_id.startswith("sheet-")
    assert result.url.startswith("https://docs.google.invalid/spreadsheets/d/")
    assert result.row_count == 1
    assert (
        result.acl_recipient_hash
        == GoogleAccount.confirmed("customer@example.com", nonce="n1").recipient_hash
    )
    customer_note = provider.artifact_for(result.spreadsheet_id).rows[0]["customer_note"]
    assert isinstance(customer_note, str)
    assert "=HYPERLINK" not in customer_note

    with pytest.raises(PermissionError, match="tenant binding mismatch"):
        service.readback_for_principal(tenant_b, spreadsheet_id=result.spreadsheet_id)


def test_idempotent_retry_reuses_artifact_and_quota_or_ambiguous_state_never_sends_url() -> None:
    provider = FakeGoogleSheetsProvider()
    service = SheetsDeliveryService(
        provider=provider,
        manifest=TemplateManifest.load(MANIFEST_PATH, template_path=TEMPLATE_PATH),
    )
    principal = _principal()
    account = GoogleAccount.confirmed("customer@example.com", nonce="n1")

    first = service.create_populate_share_outbox_ready(
        principal,
        approved_plan_hash=APPROVED_PLAN_HASH,
        google_account=account,
        rows=[],
        idempotency_key="idem-1",
    )
    repeated = service.create_populate_share_outbox_ready(
        principal,
        approved_plan_hash=APPROVED_PLAN_HASH,
        google_account=account,
        rows=[],
        idempotency_key="idem-1",
    )
    provider.fail_next_create = ProviderAmbiguousError("network timeout after request")
    ambiguous = service.create_populate_share_outbox_ready(
        principal,
        approved_plan_hash=APPROVED_PLAN_HASH,
        google_account=account,
        rows=[],
        idempotency_key="idem-2",
    )
    provider.fail_next_create = ProviderQuotaError("quota exhausted")
    quota = service.create_populate_share_outbox_ready(
        principal,
        approved_plan_hash=APPROVED_PLAN_HASH,
        google_account=account,
        rows=[],
        idempotency_key="idem-3",
    )

    assert first.spreadsheet_id == repeated.spreadsheet_id
    assert len(provider.artifacts) == 1
    assert ambiguous.status is SheetDeliveryStatus.ERROR_RETRY_WAIT
    assert ambiguous.outbox_ready is False
    assert ambiguous.url is None
    assert quota.status is SheetDeliveryStatus.QUOTA_WAIT
    assert quota.outbox_ready is False
    assert quota.url is None


def test_duplicate_retry_with_same_key_does_not_reapply_remote_effects() -> None:
    provider = FakeGoogleSheetsProvider()
    service = SheetsDeliveryService(
        provider=provider,
        manifest=TemplateManifest.load(MANIFEST_PATH, template_path=TEMPLATE_PATH),
    )
    principal = _principal()
    account = GoogleAccount.confirmed("customer@example.com", nonce="n1")
    rows = [
        TenantCandidateRow(
            candidate_id="tenant-local-1",
            tenant_local_sequence=1,
            candidate_status="new",
            role_title="ML Engineer",
            company_name="Synthetic Corp",
            location_text="Remote",
            remote_policy="remote",
            employment_type="full-time",
            compensation_public_text="customer provided range",
            source_name="Synthetic Source",
            source_url="https://example.invalid/job/1",
            source_retrieved_at="2026-07-25T00:00:00Z",
            fit_score_bucket="high",
            fit_rationale_public_facts="Public facts only",
            customer_action="review",
            customer_note="review later",
            last_synced_at="2026-07-25T00:01:00Z",
            row_version=1,
        )
    ]

    first = service.create_populate_share_outbox_ready(
        principal,
        approved_plan_hash=APPROVED_PLAN_HASH,
        google_account=account,
        rows=rows,
        idempotency_key="idem-remote-effects",
    )
    first_calls = list(provider.calls)
    provider.fail_next_create = ProviderAmbiguousError("timeout after duplicate callback")
    repeated = service.create_populate_share_outbox_ready(
        principal,
        approved_plan_hash=APPROVED_PLAN_HASH,
        google_account=account,
        rows=[],
        idempotency_key="idem-remote-effects",
    )

    assert repeated == first
    assert provider.calls.count("create_blank_spreadsheet") == 2
    assert provider.calls.count("populate") == 1
    assert provider.calls.count("share") == 1
    assert provider.calls[: len(first_calls)] == first_calls


def test_wrong_acl_deleted_tenant_unapproved_hash_and_customer_edits_fail_closed() -> None:
    provider = FakeGoogleSheetsProvider()
    service = SheetsDeliveryService(
        provider=provider,
        manifest=TemplateManifest.load(MANIFEST_PATH, template_path=TEMPLATE_PATH),
    )
    principal = _principal()
    account = GoogleAccount.confirmed("customer@example.com", nonce="n1")

    with pytest.raises(PermissionError, match="approved v4 plan hash"):
        service.create_populate_share_outbox_ready(
            principal,
            approved_plan_hash="bad",
            google_account=account,
            rows=[],
        )

    deleted = TenantPrincipal.derive(
        trusted_subject="telegram-dm:subject-a",
        tenant_uuid="11111111-1111-4111-8111-111111111111",
        lifecycle_epoch=4,
        feature_gates=frozenset({"google_sheets_v4"}),
        consented=True,
        deleted=True,
    )
    with pytest.raises(PermissionError, match="deletion state"):
        service.create_populate_share_outbox_ready(
            deleted,
            approved_plan_hash=APPROVED_PLAN_HASH,
            google_account=account,
            rows=[],
        )

    provider.force_wrong_acl_recipient = True
    blocked = service.create_populate_share_outbox_ready(
        principal,
        approved_plan_hash=APPROVED_PLAN_HASH,
        google_account=account,
        rows=[],
        idempotency_key="wrong-acl",
    )
    assert blocked.status is SheetDeliveryStatus.ERROR_NEEDS_OPERATOR
    assert blocked.outbox_ready is False
    assert blocked.url is None

    assert CustomerEditPolicy.default().may_import_formula("=1+1") is False
    assert CustomerEditPolicy.default().may_import_comment("customer comment") is False
