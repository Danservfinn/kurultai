import asyncio
import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))


class FakeCoordinationStore:
    def __init__(self, lock, contributions):
        self.lock = dict(lock)
        self.contributions = [dict(c) for c in contributions]
        self.events = []
        self.processed = []
        self.finalized = []
        self.reserved = []
        self.sent = []

    def snapshot_lock(self, lock_id):
        assert int(lock_id) == int(self.lock["lock_id"])
        return {
            "lock": dict(self.lock),
            "contributions": [dict(c) for c in self.contributions],
            "events": list(self.events),
        }

    def process_contribution(self, lock_id, contribution_id, actor, decision, note=""):
        self.processed.append((lock_id, contribution_id, actor, decision, note))
        for contribution in self.contributions:
            if int(contribution["id"]) == int(contribution_id):
                contribution["processed_at"] = "now"
        self.events.append(
            {
                "event_type": "contribution_processed",
                "actor": actor,
                "payload": {"contribution_id": contribution_id, "decision": decision, "note": note},
            }
        )
        return {"ok": True}

    def finalize_lock(self, lock_id, status, final_summary="", actor=""):
        self.finalized.append((lock_id, status, final_summary, actor))
        self.lock["status"] = status
        self.lock["final_summary"] = final_summary
        return dict(self.lock)

    def reserve_public_answer_send(self, lock_id, actor, text, purpose="answer"):
        self.reserved.append((lock_id, actor, text, purpose))
        return {"allowed": True, "send_key": "send-1", "outbox": {"channel": "telegram", "chat_id": "[REDACTED]", "thread_id": "", "text": text}}

    def mark_public_answer_sent(self, lock_id, send_key, provider_message_id, actor, final_summary=""):
        self.sent.append((lock_id, send_key, provider_message_id, actor, final_summary))
        self.lock["status"] = "answered"
        self.lock["final_answer_message_id"] = provider_message_id
        return dict(self.lock)

    def record_bridge_blocker(self, lock_id, actor, reason, details=None):
        self.events.append({"event_type": "coordination.bridge_blocked", "actor": actor, "payload": {"reason": reason, **(details or {})}})
        return {"ok": True, "reason": reason}


def _task(**overrides):
    base = {
        "task_id": "critical-1",
        "source": "coordination-handoff",
        "assigned_to": "ogedei",
        "intake_metadata": {
            "lock_id": "14",
            "logical_owner": "kublai",
            "requires_owner_synthesis": True,
            "fallback_requires_transfer": True,
        },
    }
    base.update(overrides)
    return base


def test_coordination_bridge_processes_finalizes_reserves_and_marks_sent(monkeypatch):
    from task_executor import _run_coordination_completion_bridge

    store = FakeCoordinationStore(
        {
            "lock_id": 14,
            "owner": "kublai",
            "status": "deliberating",
            "purpose": "answer",
            "required_contributors": ["kublai", "hermes"],
        },
        [
            {"id": 1, "contributor": "kublai", "summary": "Kublai synthesis", "detail": "Use this as the public plan.", "processed_at": None},
            {"id": 2, "contributor": "hermes", "summary": "Hermes checks", "detail": "Guardrails included.", "processed_at": None},
        ],
    )
    sent = {}

    def fake_send(outbox):
        sent["outbox"] = outbox
        return "telegram-message-1"

    result = _run_coordination_completion_bridge(_task(), "executor output", store_factory=lambda: store, send_func=fake_send)

    assert result["status"] == "sent"
    assert store.processed == [
        (14, 1, "kublai", "accepted", "executor-side completion bridge"),
        (14, 2, "kublai", "accepted", "executor-side completion bridge"),
    ]
    assert store.finalized and store.finalized[0][1] == "ready_to_answer"
    assert store.reserved and store.reserved[0][1] == "kublai"
    assert sent["outbox"]["text"].startswith("Kublai synthesis")
    assert store.sent[0][2] == "telegram-message-1"


def test_coordination_bridge_blocks_when_kublai_synthesis_missing():
    from task_executor import _run_coordination_completion_bridge

    store = FakeCoordinationStore(
        {
            "lock_id": 14,
            "owner": "kublai",
            "status": "deliberating",
            "purpose": "answer",
            "required_contributors": ["kublai", "hermes"],
        },
        [
            {"id": 2, "contributor": "hermes", "summary": "Hermes checks", "detail": "Not owner synthesis.", "processed_at": None},
        ],
    )

    result = _run_coordination_completion_bridge(_task(), "executor output", store_factory=lambda: store, send_func=lambda _: "should-not-send")

    assert result["status"] == "blocked"
    assert result["reason"] == "missing_owner_synthesis"
    assert store.reserved == []
    assert store.sent == []
    assert any(e["event_type"] == "coordination.bridge_blocked" for e in store.events)


def test_coordination_bridge_is_idempotent_after_prior_send():
    from task_executor import _run_coordination_completion_bridge

    store = FakeCoordinationStore(
        {
            "lock_id": 14,
            "owner": "kublai",
            "status": "answered",
            "purpose": "answer",
            "required_contributors": ["kublai"],
            "final_answer_message_id": "already-sent",
        },
        [
            {"id": 1, "contributor": "kublai", "summary": "Kublai synthesis", "detail": "Done.", "processed_at": "now"},
        ],
    )

    result = _run_coordination_completion_bridge(_task(), "executor output", store_factory=lambda: store, send_func=lambda _: "duplicate")

    assert result["status"] == "skipped"
    assert result["reason"] == "already_answered"
    assert store.reserved == []
    assert store.sent == []


def test_coordination_handoff_post_completion_does_not_schedule_generic_notification(monkeypatch, tmp_path):
    import task_executor
    from task_executor import Executor, RunResult

    scheduled = []

    def fake_create_task(coro):
        scheduled.append(coro)
        coro.close()
        raise AssertionError("coordination handoffs must not use generic completion notifications")

    monkeypatch.setattr(task_executor, "AGENTS_DIR", tmp_path)
    monkeypatch.setattr(asyncio, "create_task", fake_create_task)
    executor = object.__new__(Executor)
    task = _task(
        notify_target="tg:[REDACTED]",
        origin_type="human",
        title="Kublai-owned handoff",
    )
    run_result = RunResult(
        success=True,
        content="Kublai proxy output",
        return_code=0,
        duration_s=1.0,
        model="test-model",
        stall_detected=False,
    )

    asyncio.run(executor._post_completion(task, run_result))

    result_file = tmp_path / "ogedei" / "workspace" / "critical-1.result.md"
    assert result_file.exists()
    assert scheduled == []
