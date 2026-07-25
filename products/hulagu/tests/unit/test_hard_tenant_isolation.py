from __future__ import annotations

from pathlib import PurePosixPath

import pytest

from hulagu.domain.tenant_isolation import (
    HULAGU_PRODUCT_BRAIN_ROOT,
    KUBLAI_BRAIN_ROOT,
    FakeTenantRepository,
    TenantPrincipal,
    TenantScopedStore,
    public_brain_gateway_may_serve,
    validate_operator_projection,
)


def _principal(tenant_uuid: str, *, epoch: int = 1, deleted: bool = False) -> TenantPrincipal:
    return TenantPrincipal.derive(
        trusted_subject=f"telegram-dm:{tenant_uuid}",
        tenant_uuid=tenant_uuid,
        lifecycle_epoch=epoch,
        feature_gates=frozenset({"google_sheets_v4"}),
        consented=True,
        deleted=deleted,
    )


def test_tenant_roots_indexes_caches_exports_and_backups_are_per_tenant_only() -> None:
    tenant_a = _principal("11111111-1111-4111-8111-111111111111")
    tenant_b = _principal("22222222-2222-4222-8222-222222222222")
    store = TenantScopedStore()

    store.write_wiki(tenant_a, "profile.md", "synthetic tenant A only")
    store.index_document(tenant_a, "doc-a", "synthetic skill python")
    store.put_cache(tenant_a, "search-plan", "cache-a")
    export = store.write_export(tenant_a, "job_ops.csv", "candidate_id,role\nlocal-1,ML Engineer\n")
    backup = store.create_backup_manifest(tenant_a, artifact_digest="digest-a")

    assert export == tenant_a.tenant_root / "exports" / "job_ops.csv"
    assert backup.tenant_uuid == tenant_a.tenant_uuid
    assert backup.root == tenant_a.tenant_root / "backups"
    assert store.search(tenant_a, "python") == ["doc-a"]
    assert store.search(tenant_b, "python") == []

    with pytest.raises(PermissionError, match="tenant binding mismatch"):
        store.read_wiki(tenant_b, tenant_a.wiki_root / "profile.md")
    with pytest.raises(PermissionError, match="global customer corpus"):
        store.search_all_tenants("python")
    with pytest.raises(PermissionError, match="cross-tenant restore"):
        store.restore_backup(tenant_b, backup)
    with pytest.raises(PermissionError, match="caller-supplied path"):
        store.write_wiki(tenant_a, "../escape.md", "bad")


def test_repository_rls_scope_and_deleted_lifecycle_fail_closed() -> None:
    tenant_a = _principal("11111111-1111-4111-8111-111111111111", epoch=4)
    tenant_b = _principal("22222222-2222-8222-8222-222222222222", epoch=4)
    deleted_a = _principal("11111111-1111-4111-8111-111111111111", epoch=5, deleted=True)
    repo = FakeTenantRepository(force_rls=True)

    artifact = repo.insert_sheet_artifact(
        tenant_a, spreadsheet_id="sheet-a", drive_file_id="drive-a"
    )

    assert repo.get_sheet_artifact(tenant_a, artifact.local_artifact_id).spreadsheet_id == "sheet-a"
    with pytest.raises(PermissionError, match="RLS tenant scope"):
        repo.get_sheet_artifact(tenant_b, artifact.local_artifact_id)
    with pytest.raises(PermissionError, match="FORCE RLS"):
        FakeTenantRepository(force_rls=False).insert_sheet_artifact(tenant_a, "sheet-x", "drive-x")
    with pytest.raises(PermissionError, match="deletion state"):
        repo.insert_sheet_artifact(
            deleted_a, spreadsheet_id="sheet-deleted", drive_file_id="drive-deleted"
        )


def test_operator_projection_and_public_gateway_deny_private_hulagu_identifiers() -> None:
    safe = validate_operator_projection(
        {
            "schema": "hulagu.operator_projection.v1",
            "event_type": "delivery_ready_count",
            "count": 2,
            "error_class": "none",
            "latency_bucket": "lt_1s",
            "gate_status": "synthetic_green",
        }
    )

    assert safe["count"] == 2
    assert public_brain_gateway_may_serve(str(KUBLAI_BRAIN_ROOT / "public-safe.md")) is True
    assert public_brain_gateway_may_serve(str(HULAGU_PRODUCT_BRAIN_ROOT / "runbook.md")) is False
    assert (
        public_brain_gateway_may_serve("file:///Volumes/KurultaiVault/hulagu/tenants/x/wiki/a.md")
        is False
    )

    leaked_projections: list[dict[str, object]] = [
        {
            "schema": "hulagu.operator_projection.v1",
            "event_type": "x",
            "count": 1,
            "gate_status": "sheet-abc",
        },
        {
            "schema": "hulagu.operator_projection.v1",
            "event_type": "x",
            "count": 1,
            "gate_status": "customer@example.com",
        },
        {
            "schema": "hulagu.operator_projection.v1",
            "event_type": "x",
            "count": 1,
            "gate_status": "https://docs.google.com/spreadsheets/d/sheet",
        },
        {
            "schema": "hulagu.operator_projection.v1",
            "event_type": "x",
            "count": 1,
            "gate_status": str(
                PurePosixPath("/Volumes/KurultaiVault/hulagu/tenants/tenant-a/wiki")
            ),
        },
        {"schema": "hulagu.operator_projection.v1", "free_text": "not allowed"},
    ]
    for leaked in leaked_projections:
        with pytest.raises(ValueError):
            validate_operator_projection(leaked)


def test_deletion_tombstone_prevents_stale_worker_recreation() -> None:
    tenant = _principal("11111111-1111-4111-8111-111111111111", epoch=7)
    stale = _principal("11111111-1111-4111-8111-111111111111", epoch=6)
    store = TenantScopedStore()

    store.write_wiki(tenant, "profile.md", "synthetic content")
    tombstone = store.delete_tenant(tenant, reason="customer_request")

    assert tombstone.tenant_uuid == tenant.tenant_uuid
    assert store.search(tenant, "synthetic") == []
    with pytest.raises(PermissionError, match="stale lifecycle epoch"):
        store.write_wiki(stale, "profile.md", "recreate")
