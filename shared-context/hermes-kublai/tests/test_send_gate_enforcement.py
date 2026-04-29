from __future__ import annotations

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


def test_owner_can_reserve_public_answer_send(tmp_path):
    store, _ = load_store(tmp_path)
    lock = store.claim_response_lock("telegram", "-5287556083", "701", "kublai")

    result = store.reserve_public_answer_send(
        lock_id=lock["lock_id"],
        actor="kublai",
        text="single synthesized answer",
    )

    assert result["allowed"] is True
    assert result["outbox"]["enqueued"] is True
    why = store.explain_why("telegram", "-5287556083", "701")
    assert why["lock"]["status"] == "answering"
    assert any(e["event_type"] == "send.reserved" for e in why["events"])


def test_non_owner_public_send_is_denied(tmp_path):
    store, _ = load_store(tmp_path)
    lock = store.claim_response_lock("telegram", "-5287556083", "702", "kublai")

    result = store.reserve_public_answer_send(
        lock_id=lock["lock_id"],
        actor="hermes",
        text="wrong public answer",
    )

    assert result["allowed"] is False
    assert result["reason"] == "not_lock_owner"
    assert store.explain_why("telegram", "-5287556083", "702")["lock"]["status"] == "claimed"


def test_human_approval_required_blocks_public_send(tmp_path):
    store, _ = load_store(tmp_path)
    lock = store.claim_response_lock("telegram", "-5287556083", "703", "kublai")
    store.mark_human_approval_required(lock["lock_id"], reason="dangerous deployment", actor="kublai")

    result = store.reserve_public_answer_send(
        lock_id=lock["lock_id"],
        actor="kublai",
        text="I deployed it.",
    )

    assert result["allowed"] is False
    assert result["reason"] == "human_approval_required"


def test_required_contributor_must_be_processed_before_public_send(tmp_path):
    store, _ = load_store(tmp_path)
    lock = store.claim_response_lock(
        "telegram", "-5287556083", "704", "kublai",
        tier="tier_2_shared_expertise", required_contributors=["hermes"], support_agents=["hermes"],
    )

    missing = store.reserve_public_answer_send(lock["lock_id"], actor="kublai", text="answer without Hermes")
    assert missing["allowed"] is False
    assert missing["reason"] == "missing_required_contributors"
    assert missing["missing_contributors"] == ["hermes"]

    contrib = store.add_contribution(lock["lock_id"], "hermes", "Looks good with send gate.")
    store.process_contribution(lock["lock_id"], contrib["id"], actor="kublai", decision="accepted")
    allowed = store.reserve_public_answer_send(lock["lock_id"], actor="kublai", text="processed answer")
    assert allowed["allowed"] is True


def test_duplicate_public_send_reservation_is_deduped(tmp_path):
    store, _ = load_store(tmp_path)
    lock = store.claim_response_lock("telegram", "-5287556083", "705", "kublai")

    first = store.reserve_public_answer_send(lock["lock_id"], actor="kublai", text="first")
    second = store.reserve_public_answer_send(lock["lock_id"], actor="kublai", text="second")

    assert first["allowed"] is True
    assert first["outbox"]["enqueued"] is True
    assert second["allowed"] is False
    assert second["reason"] == "duplicate_send_reserved"
    assert second["outbox"]["text"] == "first"


def test_mark_public_answer_sent_records_message_id_and_answers_lock(tmp_path):
    store, _ = load_store(tmp_path)
    lock = store.claim_response_lock("telegram", "-5287556083", "706", "kublai")
    reserved = store.reserve_public_answer_send(lock["lock_id"], actor="kublai", text="done")

    result = store.mark_public_answer_sent(
        lock_id=lock["lock_id"],
        send_key=reserved["send_key"],
        provider_message_id="tg-999",
        actor="kublai",
    )

    assert result["status"] == "answered"
    assert result["final_answer_message_id"] == "tg-999"
    why = store.explain_why("telegram", "-5287556083", "706")
    assert any(e["event_type"] == "send.sent" for e in why["events"])
