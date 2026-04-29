from __future__ import annotations

import importlib.util
from pathlib import Path


def load_store_module():
    module_path = Path(__file__).resolve().parents[1] / "coordination_store.py"
    spec = importlib.util.spec_from_file_location("coordination_store", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_init_creates_sqlite_wal_schema(tmp_path):
    store_mod = load_store_module()
    db_path = tmp_path / "coordination.db"

    store = store_mod.CoordinationStore(db_path)
    store.init_schema()

    assert db_path.exists()
    assert store.pragma("journal_mode").lower() == "wal"
    tables = set(store.table_names())
    assert {"response_locks", "coordination_events", "contributions", "send_outbox"} <= tables


def test_claim_response_lock_is_single_owner_and_reentrant_for_owner(tmp_path):
    store_mod = load_store_module()
    store = store_mod.CoordinationStore(tmp_path / "coordination.db")
    store.init_schema()

    first = store.claim_response_lock(
        channel="telegram",
        chat_id="-5287556083",
        root_message_id="42",
        owner="kublai",
        purpose="answer",
        tier="tier2",
        required_contributors=["hermes"],
    )
    assert first["claimed"] is True
    assert first["owner"] == "kublai"

    same_owner = store.claim_response_lock(
        channel="telegram",
        chat_id="-5287556083",
        root_message_id="42",
        owner="kublai",
        purpose="answer",
        tier="tier2",
    )
    assert same_owner["claimed"] is True
    assert same_owner["lock_id"] == first["lock_id"]

    competitor = store.claim_response_lock(
        channel="telegram",
        chat_id="-5287556083",
        root_message_id="42",
        owner="hermes",
        purpose="answer",
        tier="tier2",
    )
    assert competitor["claimed"] is False
    assert competitor["owner"] == "kublai"
    assert competitor["lock_id"] == first["lock_id"]


def test_contribution_and_finalize_are_recorded_as_events(tmp_path):
    store_mod = load_store_module()
    store = store_mod.CoordinationStore(tmp_path / "coordination.db")
    store.init_schema()
    lock = store.claim_response_lock("telegram", "chat", "root", "kublai", required_contributors=["hermes"])

    contribution = store.add_contribution(lock["lock_id"], contributor="hermes", summary="Agree; add send gate.", detail="SQLite WAL + outbox.")
    processed = store.process_contribution(lock["lock_id"], contribution["id"], actor="kublai", decision="accepted")
    store.finalize_lock(lock["lock_id"], status="ready_to_answer", final_summary="Ready after Hermes contribution")

    why = store.explain_why("telegram", "chat", "root")
    assert why["lock"]["status"] == "ready_to_answer"
    assert why["contributions"][0]["id"] == contribution["id"]
    assert processed["event_type"] == "contribution_processed"
    event_types = [event["event_type"] for event in why["events"]]
    assert "lock_claimed" in event_types
    assert "contribution_added" in event_types
    assert "contribution_processed" in event_types
    assert "lock_finalized" in event_types


def test_send_outbox_reserves_deterministic_key_once(tmp_path):
    store_mod = load_store_module()
    store = store_mod.CoordinationStore(tmp_path / "coordination.db")
    store.init_schema()
    send_key = store.make_send_key(
        channel="telegram",
        chat_id="-5287556083",
        thread_id="",
        root_message_id="42",
        owner="kublai",
        purpose="answer",
    )

    first = store.enqueue_send_once(send_key=send_key, channel="telegram", chat_id="-5287556083", thread_id="", text="one answer")
    duplicate = store.enqueue_send_once(send_key=send_key, channel="telegram", chat_id="-5287556083", thread_id="", text="duplicate")

    assert first["enqueued"] is True
    assert duplicate["enqueued"] is False
    assert duplicate["id"] == first["id"]
    assert store.get_outbox_item(send_key)["text"] == "one answer"

    sent = store.mark_send_sent(send_key, provider_message_id="1795")
    assert sent["status"] == "sent"
    assert sent["provider_message_id"] == "1795"
