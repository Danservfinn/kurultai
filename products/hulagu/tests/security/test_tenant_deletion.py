from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from hulagu.domain.deletion import PRIVACY_NOTICE, DeletionPhase, MemoryDeletionWorkflow, TombstoneFence

TENANT = UUID("90000000-0000-4000-8000-000000000001")
NOW = datetime(2026, 7, 29, tzinfo=UTC)


def tombstone_fence() -> TombstoneFence:
    return TombstoneFence({1: b"synthetic-tombstone-key-material"}, active_version=1)


def test_privacy_notice_states_live_backup_and_remote_message_limits() -> None:
    assert "live data is erased immediately" in PRIVACY_NOTICE
    assert "backup copies expire within 90 days" in PRIVACY_NOTICE
    assert "already accepted by Telegram cannot be revoked" in PRIVACY_NOTICE


def seeded(tmp_path: Path) -> MemoryDeletionWorkflow:
    tenant_root = tmp_path / "tenants" / str(TENANT)
    (tenant_root / "wiki" / "generations" / "1").mkdir(parents=True)
    (tenant_root / "wiki" / "generations" / "1" / "index.md").write_text("synthetic")
    workflow = MemoryDeletionWorkflow(
        tmp_path / "state.json",
        tmp_path / "tenants",
        tombstone_fence=tombstone_fence(),
    )
    workflow.seed_tenant(
        TENANT,
        lifecycle_epoch=7,
        nonce="single-use",
        bot_id=777,
        actor_id=888,
        encrypted_route="ciphertext-only",
        route_generation=3,
        route_binding_digest="b" * 64,
        rows={"profile": "synthetic", "cv": "raw", "export": "archive", "identity": "binding"},
        ordinary_outbox=("ordinary-1",),
        active_work=("job-1",),
    )
    return workflow


def test_confirmation_only_fences_and_never_performs_one_step_deletion(tmp_path: Path) -> None:
    workflow = seeded(tmp_path)
    job = workflow.confirm(TENANT, nonce="single-use", expected_epoch=7, now=NOW)
    assert job.phase is DeletionPhase.CONFIRMED
    assert workflow.tenant_exists(TENANT)
    assert workflow.lifecycle_epoch(TENANT) == 8
    assert not workflow.identity_enabled(TENANT)
    assert not workflow.claims_allowed(TENANT)
    assert workflow.claim_ordinary_outbox(TENANT) == ()
    with pytest.raises(PermissionError):
        workflow.confirm(TENANT, nonce="single-use", expected_epoch=7, now=NOW)


def test_each_numbered_boundary_survives_real_store_restart_without_reenabling_authority(tmp_path: Path) -> None:
    workflow = seeded(tmp_path)
    job = workflow.confirm(TENANT, nonce="single-use", expected_epoch=7, now=NOW)
    expected = [DeletionPhase.CONFIRMED, DeletionPhase.DRAINED, DeletionPhase.ERASED, DeletionPhase.DELIVERY_PENDING]
    for phase in expected:
        restarted = MemoryDeletionWorkflow.open(
            tmp_path / "state.json",
            tmp_path / "tenants",
            tombstone_fence=tombstone_fence(),
        )
        assert restarted.job(job.deletion_id).phase is phase
        assert not restarted.identity_enabled(TENANT)
        assert not restarted.claims_allowed(TENANT)
        assert restarted.claim_ordinary_outbox(TENANT) == ()
        if phase is not expected[-1]:
            restarted.advance(job.deletion_id, now=NOW)
    restarted = MemoryDeletionWorkflow.open(
        tmp_path / "state.json",
        tmp_path / "tenants",
        tombstone_fence=tombstone_fence(),
    )
    restarted.record_delivery(job.deletion_id, "delivered", now=NOW)
    restarted.advance(job.deletion_id, now=NOW)
    assert restarted.job(job.deletion_id).phase is DeletionPhase.FINALIZED


def test_erasure_removes_all_tenant_content_and_late_epoch_work_cannot_commit(tmp_path: Path) -> None:
    workflow = seeded(tmp_path)
    job = workflow.confirm(TENANT, nonce="single-use", expected_epoch=7, now=NOW)
    assert not workflow.complete_old_work(TENANT, "job-1", lifecycle_epoch=7)
    workflow.advance(job.deletion_id, now=NOW)
    workflow.advance(job.deletion_id, now=NOW)
    assert not workflow.tenant_exists(TENANT)
    assert not (tmp_path / "tenants" / str(TENANT)).exists()
    assert str(TENANT) not in workflow.serialized_state_text()


def test_symlink_swap_cannot_advance_erasure_or_drop_durable_target(tmp_path: Path) -> None:
    workflow = seeded(tmp_path)
    job = workflow.confirm(TENANT, nonce="single-use", expected_epoch=7, now=NOW)
    workflow.advance(job.deletion_id, now=NOW)
    tenant_root = tmp_path / "tenants" / str(TENANT)
    moved_root = tmp_path / "moved-tenant"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "retain.txt").write_text("outside bytes")
    tenant_root.rename(moved_root)
    tenant_root.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        workflow.advance(job.deletion_id, now=NOW)

    assert workflow.job(job.deletion_id).phase is DeletionPhase.DRAINED
    assert workflow.tenant_exists(TENANT)
    assert tenant_root.is_symlink()
    assert (outside / "retain.txt").read_text() == "outside bytes"
    assert str(TENANT) in workflow.serialized_state_text()


def test_final_tombstone_and_receipt_are_exactly_minimized_and_use_backup_horizon(tmp_path: Path) -> None:
    workflow = seeded(tmp_path)
    job = workflow.confirm(TENANT, nonce="single-use", expected_epoch=7, now=NOW)
    workflow.advance(job.deletion_id, now=NOW)
    workflow.advance(job.deletion_id, now=NOW)
    workflow.advance(job.deletion_id, now=NOW)
    workflow.record_delivery(job.deletion_id, "delivery_unknown", now=NOW)
    workflow.advance(job.deletion_id, now=NOW)
    tombstone = workflow.tombstone(job.deletion_id)
    receipt = workflow.receipt(job.deletion_id)
    assert set(tombstone) == {"schema_version", "encrypted_subject_digest", "deletion_epoch", "completed_at", "backup_expiry_horizon", "rekey_state"}
    assert set(receipt) == {"schema_version", "opaque_receipt_id", "outcome", "completed_at", "expires_at"}
    forbidden = (str(TENANT), "ciphertext-only", "synthetic", "raw", "binding")
    rendered = repr((tombstone, receipt))
    assert not any(value in rendered for value in forbidden)
    assert tombstone["backup_expiry_horizon"] == (NOW + timedelta(days=97)).isoformat()


def test_workflow_tombstone_uses_encrypted_fence_and_matches_subject_without_reversible_digest(tmp_path: Path) -> None:
    fence = TombstoneFence({1: b"tombstone-encryption-key-material"}, active_version=1)
    workflow = MemoryDeletionWorkflow(tmp_path / "state.json", tmp_path / "tenants", tombstone_fence=fence)
    workflow.seed_tenant(
        TENANT,
        lifecycle_epoch=7,
        nonce="single-use",
        bot_id=777,
        actor_id=888,
        encrypted_route="ciphertext-only",
        route_generation=3,
        route_binding_digest="b" * 64,
        rows={},
        ordinary_outbox=(),
        active_work=(),
    )
    job = workflow.confirm(TENANT, nonce="single-use", expected_epoch=7, now=NOW)
    workflow.advance(job.deletion_id, now=NOW)
    workflow.advance(job.deletion_id, now=NOW)
    workflow.advance(job.deletion_id, now=NOW)
    workflow.record_delivery(job.deletion_id, "delivered", now=NOW)
    workflow.advance(job.deletion_id, now=NOW)

    tombstone = workflow.tombstone(job.deletion_id)
    assert set(tombstone) == {
        "schema_version",
        "encrypted_subject_digest",
        "deletion_epoch",
        "completed_at",
        "backup_expiry_horizon",
        "rekey_state",
    }
    assert fence.matches(tombstone, 777, 888, now=NOW)
