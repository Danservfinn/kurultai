from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def load_telegram_send_module():
    module_path = Path(__file__).resolve().parents[3] / "scripts" / "telegram_send.py"
    spec = importlib.util.spec_from_file_location("telegram_send_raw_bypass_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_raw_send_without_bypass_reason_is_denied_and_audited(tmp_path, monkeypatch):
    telegram_send = load_telegram_send_module()
    log_path = tmp_path / "telegram_send.log"
    monkeypatch.setattr(telegram_send, "LOG_FILE", str(log_path))

    def fail_if_network(*args, **kwargs):  # pragma: no cover - should not run
        raise AssertionError("raw Telegram network call should be blocked before token/API access")

    monkeypatch.setattr(telegram_send, "_load_token", fail_if_network)

    rc, entry = telegram_send.send("-100public", "hello")

    assert rc == 1
    assert entry["status"] == "RAW_SEND_DENIED"
    assert entry["reason"] == "missing_bypass_reason"
    logged = json.loads(log_path.read_text().strip())
    assert logged["status"] == "RAW_SEND_DENIED"
    assert logged["chat_id"] == "-100public"


def test_raw_send_with_bypass_reason_is_logged_and_allowed(tmp_path, monkeypatch):
    telegram_send = load_telegram_send_module()
    log_path = tmp_path / "telegram_send.log"
    monkeypatch.setattr(telegram_send, "LOG_FILE", str(log_path))
    monkeypatch.setattr(telegram_send, "_load_token", lambda: "TEST_TOKEN")

    calls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"ok": true, "result": {"message_id": 123}}'

    def fake_urlopen(req, timeout=15):
        calls.append((req, timeout))
        return FakeResponse()

    monkeypatch.setattr(telegram_send.urllib.request, "urlopen", fake_urlopen)

    rc, entry = telegram_send.send("-100ops", "operator notice", bypass_reason="operator-notification")

    assert rc == 0
    assert calls
    assert entry["status"] == "SUCCESS"
    assert entry["bypass_reason"] == "operator-notification"
    logged_lines = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert any(line["status"] == "RAW_SEND_BYPASS" and line["bypass_reason"] == "operator-notification" for line in logged_lines)
    assert logged_lines[-1]["status"] == "SUCCESS"


def test_send_once_calls_raw_send_with_guarded_bypass_reason(tmp_path, monkeypatch):
    telegram_send = load_telegram_send_module()
    db_path = tmp_path / "coordination.db"
    store = telegram_send.CoordinationStore(db_path)
    store.init_schema()
    store.claim_response_lock(
        channel="telegram",
        chat_id="chat",
        thread_id="",
        root_message_id="root",
        purpose="answer",
        owner="kublai",
    )

    observed = {}

    def fake_send(chat_id, message, reply_to_message_id=None, bypass_reason=None):
        observed["bypass_reason"] = bypass_reason
        return 0, {"status": "SUCCESS", "message_id": "m1"}

    monkeypatch.setattr(telegram_send, "send", fake_send)

    rc, entry = telegram_send.send_once(
        chat_id="chat",
        message="final answer",
        root_message_id="root",
        owner="kublai",
        db_path=db_path,
    )

    assert rc == 0
    assert entry["status"] == "SUCCESS"
    assert observed["bypass_reason"].startswith("coordination_send_gate_reserved:")
