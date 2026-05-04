import json
import os
import sys
import threading
import uuid
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
KUBLAI_REPO = Path.home() / "kurultai/kublai-repo"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(KUBLAI_REPO))


def _with_brain_service(tmp_path, monkeypatch):
    from kublai.brain_service import BrainService
    import task_intake

    socket_path = Path("/tmp") / f"task-intake-{os.getpid()}-{uuid.uuid4().hex[:8]}.sock"
    service = BrainService(tmp_path / "brain", tmp_path / "telemetry.db", tmp_path / "index.db")
    server = service.serve_socket(socket_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    monkeypatch.setenv("BRAIN_SERVICE_SOCKET", str(socket_path))
    monkeypatch.setenv("KUBLAI_TASK_OPTIMIZER", "0")
    monkeypatch.setattr(task_intake, "agent_tasks_dir", lambda agent: tmp_path / "agents" / agent / "tasks")
    monkeypatch.setattr(task_intake, "should_suppress_alert", lambda *_args, **_kwargs: (False, ""))
    monkeypatch.setattr(task_intake, "record_alert_created", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(task_intake, "get_queue_depth", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(task_intake, "should_redistribute_tasks", lambda *_args, **_kwargs: [])

    import brain_service_client

    def _brain_call(method, params=None):
        resp = brain_service_client.brain_rpc(method, params, socket_path=str(socket_path))
        if not resp.get("ok", False):
            error = resp.get("error") or "BrainServiceError"
            message = resp.get("message") or "(no message)"
            raise brain_service_client.BrainServiceError(f"{method}: {error}: {message}")
        return resp.get("result")

    monkeypatch.setattr(brain_service_client, "brain_call", _brain_call)
    return task_intake, service, server, socket_path


def test_create_task_via_brain_service_is_claimable(tmp_path, monkeypatch):
    task_intake, service, server, socket_path = _with_brain_service(tmp_path, monkeypatch)

    try:
        task_id = task_intake.create_task(
            title="Brain-service intake regression",
            body="Verify intake writes to the same store the executor claims.",
            priority="normal",
            source="unit-test",
            agent="temujin",
            skip_duplicate_check=True,
            notify_target="test-only",
        )
        claimed = service.telemetry.claim_task("temujin", now_ms=1_000)
        assert claimed.id == task_id
        assert claimed.payload["title"] == "Brain-service intake regression"
    finally:
        server.shutdown()
        server.server_close()
        try:
            socket_path.unlink()
        except FileNotFoundError:
            pass


def test_kublai_handoff_routes_to_ogedei_with_owner_metadata(tmp_path, monkeypatch):
    task_intake, service, server, socket_path = _with_brain_service(tmp_path, monkeypatch)

    try:
        task_id = task_intake.create_task(
            title="Process Kurultai handoff: evidence operator",
            body=(
                "Lock 14: Kublai should synthesize.\n"
                "root message id: synthetic-20260504T0903Z-integrate-research-agent"
            ),
            priority="high",
            source="coordination-handoff",
            agent="kublai",
            skip_duplicate_check=True,
            notify_target="test-only",
        )
        assert task_id
        claimed = service.telemetry.claim_task("ogedei", now_ms=1_000)
        assert claimed.id == task_id
        assert claimed.payload["assigned_to"] == "ogedei"
        assert "KUBLAI DISPATCH PROXY" in claimed.payload["prompt"]
        metadata = json.loads(claimed.payload["results_json"])["intake_metadata"]
        assert metadata["logical_owner"] == "kublai"
        assert metadata["public_synthesizer"] == "kublai"
        assert metadata["requires_owner_synthesis"] is True
        assert metadata["fallback_requires_transfer"] is True
        assert metadata["owner_response_timeout_s"] == 900
        assert metadata["lock_id"] == "14"
        assert metadata["root_message_id"] == "synthetic-20260504T0903Z-integrate-research-agent"
        assert metadata["dispatch_proxy"]["dispatch_proxy"] == "ogedei"
    finally:
        server.shutdown()
        server.server_close()
        try:
            socket_path.unlink()
        except FileNotFoundError:
            pass
