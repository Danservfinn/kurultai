from __future__ import annotations

"""Extra regression tests: cancel/scope, stale owner transfer, timeout disclosure, sweeper."""

import datetime as dt
import importlib.util
from pathlib import Path


def load_store(tmp_path, name="coordination.db"):
    base = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("coordination_store", base / "coordination_store.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    store = mod.CoordinationStore(tmp_path / name)
    store.init_schema()
    return store, mod


def load_sweeper():
    base = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("lock_sweeper", base / "lock_sweeper.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _claim(store, root, owner="kublai", tier="tier_2_shared_expertise", ttl=300):
    return store.claim_response_lock(
        channel="telegram", chat_id="-5287556083",
        root_message_id=root, owner=owner, tier=tier, ttl_seconds=ttl,
    )


# ── Follow-up cancellation / scope version ───────────────────────────────────

def test_cancel_lock_sets_cancelled_status(tmp_path):
    store, _ = load_store(tmp_path)
    lock = _claim(store, "c01")
    cancelled = store.cancel_lock(lock["lock_id"], actor="human", cancel_message_id="msg_377", reason="human_cancel")
    assert cancelled["status"] == "cancelled"


def test_cancelled_lock_is_not_active(tmp_path):
    store, _ = load_store(tmp_path)
    lock = _claim(store, "c02")
    store.cancel_lock(lock["lock_id"], actor="human")
    active = store.get_active_lock("telegram", "-5287556083", "c02")
    assert active is None


def test_cancel_records_cancel_event_with_message_id(tmp_path):
    store, _ = load_store(tmp_path)
    lock = _claim(store, "c03")
    store.cancel_lock(lock["lock_id"], actor="human", cancel_message_id="msg_099")
    why = store.explain_why("telegram", "-5287556083", "c03")
    cancel_events = [e for e in why["events"] if e["event_type"] == "lock.cancelled"]
    assert len(cancel_events) == 1
    assert cancel_events[0]["payload"]["cancel_message_id"] == "msg_099"
    assert cancel_events[0]["payload"]["terminal"] is True


def test_increment_scope_version_invalidates_send_key(tmp_path):
    """Scope increment means old send_key (with scope v1) is no longer valid for new draft."""
    store, _ = load_store(tmp_path)
    lock = _claim(store, "s01")
    assert lock["scope_version"] == 1

    updated = store.increment_scope_version(lock["lock_id"], reason="Danny changed scope", actor="kublai")
    assert updated["scope_version"] == 2

    # Old send key was based on scope v1; new send key should use v2 suffix
    old_key = store.make_send_key("telegram", "-5287556083", "", "s01", "kublai", "answer")
    new_key = store.make_send_key("telegram", "-5287556083", "", "s01", "kublai", "answer:v2")
    assert old_key != new_key


def test_scope_change_records_event(tmp_path):
    store, _ = load_store(tmp_path)
    lock = _claim(store, "s02")
    store.increment_scope_version(lock["lock_id"], reason="scope_change", actor="kublai")
    why = store.explain_why("telegram", "-5287556083", "s02")
    scope_events = [e for e in why["events"] if e["event_type"] == "lock.scope_changed"]
    assert len(scope_events) == 1
    assert scope_events[0]["payload"]["new_scope_version"] == 2


def test_double_scope_increment(tmp_path):
    store, _ = load_store(tmp_path)
    lock = _claim(store, "s03")
    store.increment_scope_version(lock["lock_id"], reason="first change")
    updated = store.increment_scope_version(lock["lock_id"], reason="second change")
    assert updated["scope_version"] == 3


# ── Stale owner transfer ──────────────────────────────────────────────────────

def test_stale_owner_lock_can_be_reclaimed_by_new_owner(tmp_path):
    """After mark_transferable, a different agent can re-claim."""
    store, _ = load_store(tmp_path)
    lock = _claim(store, "t01", owner="kublai", tier="tier_2_shared_expertise", ttl=3600)
    assert lock["owner"] == "kublai"

    store.mark_transferable(lock["lock_id"], reason="heartbeat_stale")

    hermes_lock = store.claim_response_lock(
        channel="telegram", chat_id="-5287556083", root_message_id="t01",
        owner="hermes", tier="tier_2_shared_expertise",
    )
    assert hermes_lock["claimed"] is True
    assert hermes_lock["owner"] == "hermes"


def test_transferred_lock_epoch_incremented(tmp_path):
    """mark_transferable bumps epoch to invalidate old claim token."""
    store, _ = load_store(tmp_path)
    lock = _claim(store, "t02", owner="kublai")
    original_epoch = lock["owner_epoch"]

    store.mark_transferable(lock["lock_id"])
    hermes_lock = store.claim_response_lock(
        "telegram", "-5287556083", "t02", "hermes",
    )
    assert hermes_lock["owner_epoch"] > original_epoch


def test_stale_lock_sweeper_marks_transferable_and_new_owner_reclaims(tmp_path):
    sweeper = load_sweeper()
    store, _ = load_store(tmp_path)

    lock = _claim(store, "t03", owner="kublai", tier="tier_2_shared_expertise", ttl=3600)
    future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=120)
    result = sweeper.sweep(store, future)
    assert lock["lock_id"] in result["transferred_lock_ids"]

    hermes_lock = store.claim_response_lock(
        "telegram", "-5287556083", "t03", "hermes",
    )
    assert hermes_lock["claimed"] is True
    assert hermes_lock["owner"] == "hermes"


def test_old_claim_token_rejected_after_transfer(tmp_path):
    """Heartbeat with old token should be rejected after a transfer."""
    store, _ = load_store(tmp_path)
    lock = _claim(store, "t04", owner="kublai")
    old_token = lock["owner_claim_token"]

    store.mark_transferable(lock["lock_id"])
    hermes_lock = store.claim_response_lock("telegram", "-5287556083", "t04", "hermes")

    updated = store.update_heartbeat(hermes_lock["lock_id"], "kublai", old_token)
    assert updated is False


# ── Timeout disclosure ────────────────────────────────────────────────────────

def test_disclose_timeout_marks_timed_out_and_records_event(tmp_path):
    store, _ = load_store(tmp_path)
    lock = _claim(store, "d01")
    result = store.disclose_timeout(lock["lock_id"], missing_contributors=["hermes"], actor="kublai")
    assert result["status"] == "timed_out"
    assert result["timeout_disclosed"] is True

    why = store.explain_why("telegram", "-5287556083", "d01")
    timeout_events = [e for e in why["events"] if e["event_type"] == "collaboration.timed_out"]
    assert len(timeout_events) == 1
    assert "hermes" in timeout_events[0]["payload"]["missing_contributors"]


def test_timed_out_lock_is_not_active(tmp_path):
    store, _ = load_store(tmp_path)
    lock = _claim(store, "d02")
    store.disclose_timeout(lock["lock_id"], missing_contributors=["hermes"])
    active = store.get_active_lock("telegram", "-5287556083", "d02")
    assert active is None


def test_format_why_includes_timeout_disclosure(tmp_path):
    store, _ = load_store(tmp_path)
    lock = _claim(store, "d03")
    store.disclose_timeout(lock["lock_id"], missing_contributors=["hermes"], actor="kublai")
    why = store.explain_why("telegram", "-5287556083", "d03")
    text = store.format_why_for_telegram(why)
    assert any(w in text.lower() for w in ("provisional", "timeout", "did not respond", "timed out"))


# ── Sweeper — additional scenarios ───────────────────────────────────────────

def test_sweeper_does_not_expire_lock_without_expires_at(tmp_path):
    sweeper = load_sweeper()
    store, _ = load_store(tmp_path)
    # Claim with no TTL (no expires_at set)
    lock = store.claim_response_lock(
        channel="telegram", chat_id="-5287556083",
        root_message_id="sw01", owner="kublai",
    )
    assert lock["expires_at"] is None

    future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=24)
    result = sweeper.sweep(store, future)
    assert lock["lock_id"] not in result["expired_lock_ids"]


def test_sweeper_handles_mix_of_expired_and_fresh_locks(tmp_path):
    sweeper = load_sweeper()
    store, _ = load_store(tmp_path)

    expired_lock = _claim(store, "sw02", ttl=30)
    fresh_lock = _claim(store, "sw03", ttl=3600)
    answered_lock = _claim(store, "sw04", ttl=30)
    store.finalize_lock(answered_lock["lock_id"], status="answered")

    future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=120)
    result = sweeper.sweep(store, future)

    assert expired_lock["lock_id"] in result["expired_lock_ids"]
    assert fresh_lock["lock_id"] not in result["expired_lock_ids"]
    assert answered_lock["lock_id"] not in result["expired_lock_ids"]


def test_sweeper_returns_swept_at_timestamp(tmp_path):
    sweeper = load_sweeper()
    store, _ = load_store(tmp_path)
    result = sweeper.sweep(store)
    assert "swept_at" in result
    assert result["swept_at"].endswith("Z")


# ── Inbound adapter smoke test ────────────────────────────────────────────────

def test_inbound_adapter_returns_claim_and_answer_for_kublai_message(tmp_path):
    import sys
    base = Path(__file__).resolve().parents[1]
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))
    import importlib
    adapter_spec = importlib.util.spec_from_file_location("inbound_adapter", base / "inbound_adapter.py")
    adapter = importlib.util.module_from_spec(adapter_spec)
    adapter_spec.loader.exec_module(adapter)

    store, _ = load_store(tmp_path)
    update = {
        "message": {
            "message_id": 42,
            "chat": {"id": -5287556083},
            "from": {"id": 111, "username": "danny", "is_bot": False},
            "text": "Kublai, why did that route to Mongke?",
            "date": 1714400000,
        }
    }
    result = adapter.process_inbound_update(update, "kublai", store)
    assert result["action"] == "claim_and_answer"
    assert result["lock"] is not None
    assert result["lock"]["owner"] == "kublai"


def test_inbound_adapter_returns_stay_silent_for_wrong_agent(tmp_path):
    import sys
    base = Path(__file__).resolve().parents[1]
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))
    import importlib
    adapter_spec = importlib.util.spec_from_file_location("inbound_adapter2", base / "inbound_adapter.py")
    adapter = importlib.util.module_from_spec(adapter_spec)
    adapter_spec.loader.exec_module(adapter)

    store, _ = load_store(tmp_path, "coordination2.db")
    update = {
        "message": {
            "message_id": 43,
            "chat": {"id": -5287556083},
            "from": {"id": 111, "username": "danny", "is_bot": False},
            "text": "Kublai, why did that route to Mongke?",
            "date": 1714400000,
        }
    }
    # Hermes processes a message addressed to Kublai
    result = adapter.process_inbound_update(update, "hermes", store)
    assert result["action"] == "stay_silent"


def test_inbound_adapter_observe_for_casual_message(tmp_path):
    import sys
    base = Path(__file__).resolve().parents[1]
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))
    import importlib
    adapter_spec = importlib.util.spec_from_file_location("inbound_adapter3", base / "inbound_adapter.py")
    adapter = importlib.util.module_from_spec(adapter_spec)
    adapter_spec.loader.exec_module(adapter)

    store, _ = load_store(tmp_path, "coordination3.db")
    update = {
        "message": {
            "message_id": 50,
            "chat": {"id": -5287556083},
            "from": {"id": 111, "username": "danny", "is_bot": False},
            "text": "Thanks, looks good!",
            "date": 1714400001,
        }
    }
    result = adapter.process_inbound_update(update, "kublai", store)
    assert result["action"] == "observe"
