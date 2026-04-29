from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path


def load_modules(tmp_path):
    base = Path(__file__).resolve().parents[1]
    store_spec = importlib.util.spec_from_file_location("coordination_store", base / "coordination_store.py")
    store_mod = importlib.util.module_from_spec(store_spec)
    store_spec.loader.exec_module(store_mod)

    sweeper_spec = importlib.util.spec_from_file_location("lock_sweeper", base / "lock_sweeper.py")
    sweeper_mod = importlib.util.module_from_spec(sweeper_spec)
    sweeper_spec.loader.exec_module(sweeper_mod)
    # Point sweeper at test db
    sweeper_mod.DEFAULT_DB = tmp_path / "coordination.db"

    store = store_mod.CoordinationStore(tmp_path / "coordination.db")
    store.init_schema()
    return store, sweeper_mod


def _claim(store, root_message_id: str, owner: str = "kublai", tier: str = "tier2", ttl_seconds: int | None = None):
    return store.claim_response_lock(
        channel="telegram",
        chat_id="-5287556083",
        root_message_id=root_message_id,
        owner=owner,
        tier=tier,
        ttl_seconds=ttl_seconds,
    )


def test_expired_lock_is_marked_expired(tmp_path):
    store, sweeper_mod = load_modules(tmp_path)
    lock = _claim(store, "100", ttl_seconds=60)
    assert lock["claimed"] is True

    past = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=120)).isoformat().replace("+00:00", "Z")
    result = sweeper_mod.sweep(store, dt.datetime.fromisoformat(past.replace("Z", "+00:00")))

    assert result["expired"] == 1
    assert lock["lock_id"] in result["expired_lock_ids"]

    active = store.get_active_lock("telegram", "-5287556083", "100")
    assert active is None


def test_fresh_lock_is_not_swept(tmp_path):
    store, sweeper_mod = load_modules(tmp_path)
    lock = _claim(store, "200", ttl_seconds=300)
    assert lock["claimed"] is True

    now = dt.datetime.now(dt.timezone.utc)
    result = sweeper_mod.sweep(store, now)

    assert result["expired"] == 0
    assert result["transferred"] == 0


def test_stale_heartbeat_lock_is_marked_transferable(tmp_path):
    store, sweeper_mod = load_modules(tmp_path)
    lock = _claim(store, "300", tier="tier2", ttl_seconds=3600)

    past = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=120)).isoformat().replace("+00:00", "Z")
    result = sweeper_mod.sweep(store, dt.datetime.fromisoformat(past.replace("Z", "+00:00")))

    assert result["transferred"] == 1
    assert lock["lock_id"] in result["transferred_lock_ids"]


def test_tier1_stale_heartbeat_shorter_ttl(tmp_path):
    store, sweeper_mod = load_modules(tmp_path)
    lock = _claim(store, "400", tier="tier1", ttl_seconds=3600)

    past_35s = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=35)).isoformat().replace("+00:00", "Z")
    result = sweeper_mod.sweep(store, dt.datetime.fromisoformat(past_35s.replace("Z", "+00:00")))

    assert result["transferred"] == 1


def test_answered_lock_not_swept(tmp_path):
    store, sweeper_mod = load_modules(tmp_path)
    lock = _claim(store, "500", ttl_seconds=60)
    store.finalize_lock(lock["lock_id"], status="answered", final_summary="done")

    past = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=120)).isoformat().replace("+00:00", "Z")
    result = sweeper_mod.sweep(store, dt.datetime.fromisoformat(past.replace("Z", "+00:00")))

    assert lock["lock_id"] not in result["expired_lock_ids"]
    assert lock["lock_id"] not in result["transferred_lock_ids"]


def test_is_heartbeat_stale_returns_false_for_fresh_lock(tmp_path):
    store, sweeper_mod = load_modules(tmp_path)
    lock = _claim(store, "600", tier="tier2")
    now = dt.datetime.now(dt.timezone.utc)
    assert sweeper_mod.is_heartbeat_stale(lock, now) is False


def test_is_heartbeat_stale_returns_true_for_old_heartbeat(tmp_path):
    store, sweeper_mod = load_modules(tmp_path)
    lock = _claim(store, "700", tier="tier2")
    future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=120)
    assert sweeper_mod.is_heartbeat_stale(lock, future) is True


def test_sweep_no_locks_returns_zeros(tmp_path):
    store, sweeper_mod = load_modules(tmp_path)
    result = sweeper_mod.sweep(store)
    assert result["expired"] == 0
    assert result["transferred"] == 0
