from __future__ import annotations

"""Tier 3 draft/review gating primitives tests."""

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


def _claim_tier3(store, root="700"):
    return store.claim_response_lock(
        channel="telegram",
        chat_id="-5287556083",
        root_message_id=root,
        owner="kublai",
        tier="tier_3_governance",
        required_contributors=["hermes"],
        support_agents=["hermes"],
        risk_level="high",
        ttl_seconds=900,
    )


def test_request_draft_review_transitions_to_reviewing(tmp_path):
    store, _ = load_store(tmp_path)
    lock = _claim_tier3(store)

    result = store.request_draft_review(
        lock["lock_id"],
        from_agent="kublai",
        to_agent="hermes",
        draft_id="draft_001",
        draft_hash="sha256:abc123",
        scope=["correctness", "protocol safety"],
        deadline_at="2026-04-29T15:00:00Z",
    )
    assert result["status"] == "reviewing"
    assert result["review_deadline_at"] == "2026-04-29T15:00:00Z"

    why = store.explain_why("telegram", "-5287556083", "700")
    event_types = [e["event_type"] for e in why["events"]]
    assert "draft.review_requested" in event_types


def test_submit_review_approve_transitions_back_to_drafting(tmp_path):
    store, _ = load_store(tmp_path)
    lock = _claim_tier3(store)
    store.request_draft_review(lock["lock_id"], "kublai", "hermes", "draft_001", "sha256:abc")

    result = store.submit_draft_review(
        lock["lock_id"],
        from_agent="hermes",
        verdict="approve_with_edits",
        blocking=False,
        suggested_changes=["Add explicit send-gate idempotency key."],
        safe_public_attribution="Hermes reviewed the draft for protocol safety.",
    )
    assert result["status"] == "drafting"
    assert result["review_event"]["verdict"] == "approve_with_edits"
    assert result["review_event"]["blocking"] is False

    why = store.explain_why("telegram", "-5287556083", "700")
    review_submitted = [e for e in why["events"] if e["event_type"] == "draft.review_submitted"]
    assert len(review_submitted) == 1
    assert review_submitted[0]["payload"]["safe_public_attribution"] == "Hermes reviewed the draft for protocol safety."


def test_submit_review_blocking_transitions_to_review_blocked(tmp_path):
    store, _ = load_store(tmp_path)
    lock = _claim_tier3(store)
    store.request_draft_review(lock["lock_id"], "kublai", "hermes", "draft_001", "sha256:abc")

    result = store.submit_draft_review(
        lock["lock_id"],
        from_agent="hermes",
        verdict="reject",
        blocking=True,
        required_changes=["Backup verified", "Rollback path tested"],
    )
    assert result["status"] == "review_blocked"
    assert result["review_event"]["blocking"] is True


def test_human_approval_required_and_granted(tmp_path):
    store, _ = load_store(tmp_path)
    lock = _claim_tier3(store)

    approval_state = store.mark_human_approval_required(
        lock["lock_id"],
        reason="deployment decision",
        blocked_actions=["deploy", "delete"],
        actor="kublai",
    )
    assert approval_state["human_approval_required"] is True
    assert approval_state["human_approval_reason"] == "deployment decision"

    approved = store.set_human_approved(lock["lock_id"], by_message_id="msg_380", actor="human")
    assert approved["human_approval_required"] is False
    assert approved["human_approved_by"] == "msg_380"

    why = store.explain_why("telegram", "-5287556083", "700")
    event_types = [e["event_type"] for e in why["events"]]
    assert "human_approval.required" in event_types
    assert "human_approval.granted" in event_types


def test_tier3_full_governance_workflow(tmp_path):
    store, _ = load_store(tmp_path)
    lock = _claim_tier3(store)

    # Request contribution from support
    store.request_contribution_event(lock["lock_id"], "kublai", "hermes", "Your health review?")
    store.add_contribution(
        lock["lock_id"], "hermes",
        summary="Deployment needs rollback verification first.",
        stance="conditional",
        blocking=True,
        objections=["Missing rollback plan"],
        safe_public_attribution="Hermes flagged missing rollback plan.",
    )

    # Owner drafts and requests review
    store.request_draft_review(lock["lock_id"], "kublai", "hermes", "draft_001", "sha256:abc",
                                scope=["correctness", "failure_modes"])

    # Reviewer approves after conditions met
    store.submit_draft_review(lock["lock_id"], "hermes", verdict="approve", blocking=False,
                               safe_public_attribution="Hermes reviewed and approved after rollback confirmed.")

    # Require human approval before deployment
    store.mark_human_approval_required(lock["lock_id"], "deployment decision", actor="kublai")
    store.set_human_approved(lock["lock_id"], "msg_390", actor="human")

    # Mark ready and finalize
    send_key = store.make_send_key("telegram", "-5287556083", "", "700", "kublai", "answer")
    store.record_final_answer_ready(lock["lock_id"], "kublai", ["kublai", "hermes"], send_key)
    store.finalize_lock(lock["lock_id"], status="answered", final_summary="Deployment approved.", actor="kublai")

    why = store.explain_why("telegram", "-5287556083", "700")
    assert why["lock"]["status"] == "answered"
    assert why["lock"]["human_approved_by"] == "msg_390"
    event_types = [e["event_type"] for e in why["events"]]
    assert "draft.review_requested" in event_types
    assert "draft.review_submitted" in event_types
    assert "human_approval.required" in event_types
    assert "human_approval.granted" in event_types
    assert "final_answer.ready" in event_types


def test_format_why_for_telegram_with_timeout(tmp_path):
    store, _ = load_store(tmp_path)
    lock = _claim_tier3(store)
    store.disclose_timeout(lock["lock_id"], missing_contributors=["hermes"], actor="kublai")

    why = store.explain_why("telegram", "-5287556083", "700")
    text = store.format_why_for_telegram(why)
    assert "provisional" in text.lower() or "timeout" in text.lower() or "did not respond" in text.lower()
    assert "hermes" in text.lower()


def test_format_why_for_telegram_human_approval_required(tmp_path):
    store, _ = load_store(tmp_path)
    lock = _claim_tier3(store)
    store.mark_human_approval_required(lock["lock_id"], "deployment decision", actor="kublai")

    why = store.explain_why("telegram", "-5287556083", "700")
    text = store.format_why_for_telegram(why)
    assert "approval" in text.lower()
    assert "blocked" in text.lower()


def test_format_why_for_telegram_no_lock_returns_helpful_message(tmp_path):
    store, _ = load_store(tmp_path)
    why = store.explain_why("telegram", "-5287556083", "nonexistent")
    text = store.format_why_for_telegram(why)
    assert "no coordination record" in text.lower()
