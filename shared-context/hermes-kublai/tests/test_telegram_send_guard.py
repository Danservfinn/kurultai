from __future__ import annotations

import importlib.util
from pathlib import Path


def load_telegram_send_module():
    module_path = Path(__file__).resolve().parents[3] / "scripts" / "telegram_send.py"
    spec = importlib.util.spec_from_file_location("telegram_send_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_send_once_uses_outbox_to_prevent_duplicate_public_sends(tmp_path, monkeypatch):
    telegram_send = load_telegram_send_module()
    db_path = tmp_path / "coordination.db"
    sent_messages: list[tuple[str, str, int | None]] = []

    def fake_send(chat_id: str, message: str, reply_to_message_id: int | None = None):
        sent_messages.append((chat_id, message, reply_to_message_id))
        return 0, {"status": "SUCCESS", "provider_message_id": "telegram-1"}

    monkeypatch.setattr(telegram_send, "send", fake_send)

    first_rc, first = telegram_send.send_once(
        chat_id="chat",
        message="one public answer",
        root_message_id="root",
        owner="kublai",
        db_path=db_path,
    )
    duplicate_rc, duplicate = telegram_send.send_once(
        chat_id="chat",
        message="duplicate public answer",
        root_message_id="root",
        owner="kublai",
        db_path=db_path,
    )

    assert first_rc == 0
    assert first["status"] == "SUCCESS"
    assert duplicate_rc == 0
    assert duplicate["status"] == "DEDUPED"
    assert sent_messages == [("chat", "one public answer", None)]
