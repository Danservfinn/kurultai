from __future__ import annotations

"""Tier 2 contribution bus workflow tests."""

import importlib.util
from pathlib import Path


def load_store(tmp_path):
    base = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("coordination_store", base / "coordination_store.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    store = mod.CoordinationStore(tmp_path / "coordination.db")
    store.init_schema()
    return store, mod


def _claim_tier2(store, root="500", owner="kublai"):
    return store.claim_response_lock(
        channel="telegram",
        chat_id="-5287556083",
        root_message_id=root,
        owner=owner,
        tier="tier_2_shared_expertise",
        required_contributors=["hermes"],
        support_agents=["hermes"],
        ttl_seconds=120,
    )


def test_request_contribution_event_records_correct_event(tmp_path):
    store, _ = load_store(tmp_path)
    lock = _claim_tier2(store)
    event = store.request_contribution_event(
        lock["lock_id"], "kublai", "hermes",
        "Provide system-health input",
        deadline_at="2026-04-29T14:06:02Z",
    )
    assert event["event_type"] == "contribution.requested"
    assert event["to_agent"] == "hermes"
    assert event["deadline_at"] == "2026-04-29T14:06:02Z"

    why = store.explain_why("telegram", "-5287556083", "500")
    event_types = [e["event_type"] for e in why["events"]]
    assert "contribution.requested" in event_types


def test_record_final_answer_ready_transitions_status(tmp_path):
    store, _ = load_store(tmp_path)
    lock = _claim_tier2(store)

    send_key = store.make_send_key("telegram", "-5287556083", "", "500", "kublai", "answer")
    result = store.record_final_answer_ready(
        lock["lock_id"],
        actor="kublai",
        represented_contributors=["kublai", "hermes"],
        send_key=send_key,
        timeout_disclosed=False,
    )
    assert result["status"] == "ready_to_answer"
    assert result["timeout_disclosed"] is False

    why = store.explain_why("telegram", "-5287556083", "500")
    event_types = [e["event_type"] for e in why["events"]]
    assert "final_answer.ready" in event_types


def test_final_answer_ready_with_timeout_disclosure(tmp_path):
    store, _ = load_store(tmp_path)
    lock = _claim_tier2(store)

    send_key = store.make_send_key("telegram", "-5287556083", "", "500", "kublai", "answer")
    result = store.record_final_answer_ready(
        lock["lock_id"],
        actor="kublai",
        represented_contributors=["kublai"],
        send_key=send_key,
        timeout_disclosed=True,
    )
    assert result["timeout_disclosed"] is True

    why = store.explain_why("telegram", "-5287556083", "500")
    ready_events = [e for e in why["events"] if e["event_type"] == "final_answer.ready"]
    assert len(ready_events) == 1
    assert ready_events[0]["payload"]["timeout_disclosed"] is True


def test_full_tier2_workflow_with_contribution_and_final_answer(tmp_path):
    store, _ = load_store(tmp_path)

    # Owner claims
    lock = _claim_tier2(store)
    assert lock["claimed"] is True

    # Owner requests contribution
    store.request_contribution_event(lock["lock_id"], "kublai", "hermes", "Your health/protocol view?")

    # Support agent contributes
    contribution = store.add_contribution(
        lock["lock_id"],
        contributor="hermes",
        summary="Use lock plus send gate; add stale-owner recovery.",
        stance="support_with_additions",
        key_points=["Do not expose deliberation.", "Record timeout honestly."],
        safe_public_attribution="Hermes reviewed system-health and protocol-maintenance aspects.",
    )
    assert contribution["contributor"] == "hermes"

    # Owner synthesizes and marks ready
    send_key = store.make_send_key("telegram", "-5287556083", "", "500", "kublai", "answer")
    store.record_final_answer_ready(
        lock["lock_id"], "kublai", ["kublai", "hermes"], send_key,
    )

    # Owner sends and marks lock answered
    store.enqueue_send_once(send_key, "telegram", "-5287556083", "", "One synthesized answer.")
    store.mark_send_sent(send_key, "msg_1795")
    store.finalize_lock(lock["lock_id"], status="answered", final_summary="Answer posted.", actor="kublai")

    why = store.explain_why("telegram", "-5287556083", "500")
    assert why["lock"]["status"] == "answered"
    assert len(why["contributions"]) == 1
    event_types = [e["event_type"] for e in why["events"]]
    assert "contribution.requested" in event_types
    assert "final_answer.ready" in event_types
    assert "lock_finalized" in event_types


def test_hermes_stays_silent_when_not_required_contributor(tmp_path):
    """Hermes cannot claim lock already owned by Kublai in a non-collab context."""
    store, _ = load_store(tmp_path)
    kublai_lock = store.claim_response_lock(
        "telegram", "-5287556083", "600", "kublai",
        tier="tier_1_routine",
        required_contributors=[],
    )
    hermes_attempt = store.claim_response_lock(
        "telegram", "-5287556083", "600", "hermes",
        tier="tier_1_routine",
    )
    assert kublai_lock["claimed"] is True
    assert hermes_attempt["claimed"] is False
    assert hermes_attempt["owner"] == "kublai"
