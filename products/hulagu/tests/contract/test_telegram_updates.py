from __future__ import annotations

import pytest

from hulagu.telegram.adapter import FakeTelegramAdapter, TelegramContractError, normalize_update
from hulagu.telegram.sender import DeliveryState, OutboxMessage, TelegramSender


class RecordingDeliveryStore:
    def __init__(self) -> None:
        self.records: list[tuple[str, DeliveryState, int]] = []

    def record_delivery(self, delivery_id: str, state: DeliveryState, attempts: int) -> None:
        self.records.append((delivery_id, state, attempts))


def message(update_id: int = 1, *, actor: int = 42, chat: int = 42, text: str = "/start") -> dict[str, object]:
    return {"update_id": update_id, "message": {"message_id": 9, "from": {"id": actor}, "chat": {"id": chat, "type": "private"}, "text": text}}


def test_normalizes_only_schema_v1_fields_from_private_message() -> None:
    update = normalize_update(message(), pinned_bot_id=7)
    assert update.as_dict() == {"schema_version": "TelegramUpdate/v1", "bot_id": 7, "update_id": 1, "chat_id": 42, "chat_type": "private", "actor_id": 42, "message_id": 9, "callback_query_id": None}
    assert update.text == "/start"


def test_rejects_oversized_text_before_command_work() -> None:
    with pytest.raises(TelegramContractError, match="oversized"):
        normalize_update(message(text="x" * 33), pinned_bot_id=7, max_text_bytes=32)


def test_sender_marks_remote_success_local_timeout_unknown_and_caps_retry() -> None:
    adapter = FakeTelegramAdapter(bot_id=7, ambiguous_delivery_keys={"run-9:event-3"})
    recorder = RecordingDeliveryStore()
    sender = TelegramSender(adapter, max_attempts=2, recorder=recorder)
    outgoing = OutboxMessage("delivery-1", 42, "run-9:event-3", "Results ready")
    first = sender.deliver(outgoing)
    second = sender.deliver(outgoing)
    third = sender.deliver(outgoing)
    assert first.state is DeliveryState.DELIVERY_UNKNOWN
    assert second.state is DeliveryState.DELIVERY_UNKNOWN
    assert third.state is DeliveryState.FAILED
    assert sender.duplicate_risk_count == 2
    assert len(adapter.sent_messages) == 2
    assert all("[run-9:event-3]" in sent.text for sent in adapter.sent_messages)
    assert recorder.records == [
        ("delivery-1", DeliveryState.DELIVERY_UNKNOWN, 1),
        ("delivery-1", DeliveryState.DELIVERY_UNKNOWN, 2),
        ("delivery-1", DeliveryState.FAILED, 2),
    ]


def test_sender_records_delivered_terminal_state() -> None:
    adapter = FakeTelegramAdapter(bot_id=7)
    recorder = RecordingDeliveryStore()
    sender = TelegramSender(adapter, recorder=recorder)

    result = sender.deliver(OutboxMessage("delivery-2", 42, "run-10:event-1", "Ready"))

    assert result == sender.deliver(OutboxMessage("delivery-3", 42, "run-10:event-2", "Ready"))
    assert result.state is DeliveryState.DELIVERED
    assert recorder.records == [
        ("delivery-2", DeliveryState.DELIVERED, 1),
        ("delivery-3", DeliveryState.DELIVERED, 1),
    ]
