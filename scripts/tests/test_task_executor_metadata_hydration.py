import json
import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))


def test_hydrate_task_payload_lifts_intake_metadata_and_normalizes_strings():
    from task_executor import _hydrate_task_payload

    task = _hydrate_task_payload(
        {
            "id": "task-1",
            "description": "Do the thing",
            "source": None,
            "title": None,
            "skill_hint": None,
            "results_json": json.dumps(
                {
                    "intake_metadata": {
                        "notify_target": "+19194133445",
                        "origin_type": "agent",
                        "origin_initiator": "kublai",
                        "origin_message_id": "council-7",
                    }
                }
            ),
        }
    )

    assert task["notify_target"] == "+19194133445"
    assert task["origin_type"] == "agent"
    assert task["origin_initiator"] == "kublai"
    assert task["origin_message_id"] == "council-7"
    assert task["source"] == ""
    assert task["title"] == ""
    assert task["skill_hint"] == ""
    assert task["prompt"] == "Do the thing"


def test_notification_allows_nonhuman_origin_with_explicit_target(monkeypatch):
    from task_executor import Executor

    sent = {}

    class Queue:
        def enqueue(self, *args):
            sent["queued"] = args

    def fake_send(target, message, quote_ts=None, quote_author=None):
        sent["target"] = target
        sent["message"] = message
        sent["quote_ts"] = quote_ts
        sent["quote_author"] = quote_author
        return 0, "ok"

    import signal_send

    monkeypatch.setattr(signal_send, "send", fake_send)
    executor = object.__new__(Executor)
    executor._nqueue = Queue()

    import asyncio

    asyncio.run(
        executor._send_notification(
            "jochi",
            {
                "task_id": "task-1",
                "title": "Council advisor brief",
                "notify_target": "+19194133445",
                "origin_type": "agent",
                "origin_initiator": "kublai",
                "origin_message_id": "council-7",
            },
            "## Resolution\n\nDone.",
        )
    )

    assert sent["target"] == "+19194133445"
    assert "Council advisor brief" in sent["message"]
    assert sent["quote_ts"] == "council-7"
    assert sent["quote_author"] == "kublai"
    assert "queued" not in sent
