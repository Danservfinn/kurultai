from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from hulagu.domain.deletion import TombstoneFence

NOW = datetime(2026, 7, 29, tzinfo=UTC)


def test_tombstone_match_survives_active_key_rotation_restore_and_rekey() -> None:
    original = TombstoneFence({1: b"old-key-material" * 2, 2: b"new-key-material" * 2}, active_version=1)
    tombstone = original.create(777, 888, deletion_epoch=4, completed_at=NOW, horizon=NOW + timedelta(days=97))
    restored = TombstoneFence.restore(original.backup_key_state(), active_version=2)
    assert restored.matches(tombstone, 777, 888, now=NOW)
    rekeyed = restored.rekey(tombstone)
    restored.revoke(1)
    assert rekeyed["rekey_state"] == "current"
    assert restored.matches(rekeyed, 777, 888, now=NOW)


def test_old_subject_key_cannot_be_revoked_while_applicable_tombstone_needs_it() -> None:
    fence = TombstoneFence({1: b"old-key-material" * 2, 2: b"new-key-material" * 2}, active_version=1)
    tombstone = fence.create(777, 888, deletion_epoch=4, completed_at=NOW, horizon=NOW + timedelta(days=97))
    fence.activate(2)
    with pytest.raises(PermissionError, match="re-key"):
        fence.revoke(1, tombstones=(tombstone,), now=NOW)
