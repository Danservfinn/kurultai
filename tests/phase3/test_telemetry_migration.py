import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest

from kublai.brain_service import BrainService
from kublai.brain_service_client import call
from kublai.telemetry import NoPendingTaskError, StaleClaimError, TelemetryStore
from openclaw_memory import NoPendingTaskError as LegacyNoPendingTaskError
from openclaw_memory import OperationalMemory


NODE_BIN = shutil.which("node") or "/opt/homebrew/bin/node"


def test_operational_memory_telemetry_mode_keeps_core_signatures(tmp_path, monkeypatch):
    monkeypatch.setenv("KUBLAI_TELEMETRY_PRIMARY", "1")
    monkeypatch.setenv("KUBLAI_TELEMETRY_DB", str(tmp_path / "telemetry.db"))

    memory = OperationalMemory(password=None)
    task_id = memory.create_task(
        "analysis",
        "migrate telemetry",
        delegated_by="kublai",
        assigned_to="temujin",
        priority="high",
    )

    claimed = memory.claim_task("temujin")
    assert claimed["id"] == task_id
    assert claimed["priority"] == "high"
    assert claimed["claim_token"]

    notification_id = memory.create_notification("kublai", "task_completed", "done", task_id=task_id)
    assert memory.get_notifications("kublai", unread_only=True)[0]["id"] == notification_id
    assert memory.mark_notification_read(notification_id) is True
    assert memory.mark_notification_read("missing-notification") is False
    assert memory.get_notifications("kublai", unread_only=True) == []

    assert memory.complete_task(task_id, {"ok": True}) is True
    assert memory.update_agent_heartbeat("temujin", "active") is True
    assert memory.get_agent_status("temujin")["status"] == "active"


def test_operational_memory_telemetry_claim_race_has_single_winner(tmp_path, monkeypatch):
    monkeypatch.setenv("KUBLAI_TELEMETRY_PRIMARY", "1")
    monkeypatch.setenv("KUBLAI_TELEMETRY_DB", str(tmp_path / "telemetry.db"))
    memory = OperationalMemory(password=None)
    memory.create_task("analysis", "race", delegated_by="kublai", assigned_to="any")

    winners = []
    errors = []

    def worker(i):
        try:
            winners.append(memory.claim_task(f"agent-{i}"))
        except LegacyNoPendingTaskError as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(100)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(winners) == 1
    assert len(errors) == 99


def test_telemetry_lease_fencing_and_renewal(tmp_path):
    store = TelemetryStore(tmp_path / "telemetry.db")
    store.create_task("task-1", description="fenced", delegated_by="kublai")
    first = store.claim_task("agent-a", lease_ttl_ms=90, now_ms=1_000)

    renewed = first
    for i in range(1, 6):
        renewed = store.renew_claim(
            renewed.id,
            "agent-a",
            renewed.claim_token,
            lease_ttl_ms=90,
            now_ms=1_000 + i * 30,
        )
        assert renewed.lease_version == i + 1

    assert store.sweep_expired_claims(now_ms=1_000 + 6 * 90) == 1
    second = store.claim_task("agent-b", lease_ttl_ms=90, now_ms=1_000 + 6 * 90 + 1)
    with pytest.raises(StaleClaimError):
        store.complete_task(first.id, "agent-a", first.claim_token, summary="stale", now_ms=1_000 + 6 * 90 + 2)
    store.complete_task(second.id, "agent-b", second.claim_token, summary="fresh", now_ms=1_000 + 6 * 90 + 3)


def test_telemetry_mid_claim_process_death_releases_task(tmp_path):
    db_path = tmp_path / "telemetry.db"
    store = TelemetryStore(db_path)
    store.create_task("task-1", description="kill", delegated_by="kublai")

    script = f"""
import os, signal
from kublai.telemetry import TelemetryStore
store = TelemetryStore({str(db_path)!r})
store.claim_task("agent-a", lease_ttl_ms=50, now_ms=1000)
os.kill(os.getpid(), signal.SIGKILL)
"""
    result = subprocess.run([sys.executable, "-c", script], env={**os.environ, "PYTHONPATH": "."})
    assert result.returncode != 0

    recovered = TelemetryStore(db_path)
    assert recovered.sweep_expired_claims(now_ms=1_051) == 1
    assert recovered.claim_task("agent-b", lease_ttl_ms=50, now_ms=1_052).id == "task-1"


def test_heartbeat_and_rate_limit_under_load(tmp_path):
    store = TelemetryStore(tmp_path / "telemetry.db")
    agents = ["kublai", "temujin", "jochi", "mongke", "ogedei", "chagatai"]
    start = int(time.time() * 1000)
    for tick in range(120):
        for agent in agents:
            store.heartbeat(agent, status="active", meta={"tick": tick})
    with store.connect() as conn:
        assert conn.execute("SELECT count(*) FROM agent_state").fetchone()[0] == len(agents)

    for i in range(500):
        assert store.increment_rate_limit("temujin", "api", window_ms=60_000, now_ms=start + i) == i + 1
    with store.connect() as conn:
        row = conn.execute("SELECT count, bucket_start_ms FROM rate_limits").fetchone()
    assert row["count"] == 500
    assert row["bucket_start_ms"] == (start // 60_000) * 60_000


def test_single_host_atomicity_stress_has_no_sqlite_busy(tmp_path):
    store = TelemetryStore(tmp_path / "telemetry.db")
    busy_errors = []

    for round_id in range(20):
        store.create_task(f"task-{round_id}", description="stress", delegated_by="kublai")
        winners = []

        def worker(i):
            try:
                winners.append(store.claim_task(f"agent-{i}", lease_ttl_ms=10_000))
            except NoPendingTaskError:
                pass
            except Exception as exc:  # pragma: no cover - assertion reports the concrete leak
                busy_errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(100)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert len(winners) == 1

    assert busy_errors == []


def test_wiki_write_failure_injection_recovers_without_duplicate_page(tmp_path, monkeypatch):
    service = BrainService(tmp_path / "brain", tmp_path / "telemetry.db", tmp_path / "brain-index.db")
    service.telemetry.create_task("task-1", description="recover", delegated_by="kublai")
    claim = service.telemetry.claim_task("temujin", now_ms=1_000)
    service.telemetry.complete_task(
        claim.id,
        "temujin",
        claim.claim_token,
        summary="recover me",
        target_wiki_path="operations/tasks/2026/04/task-task-1.md",
        now_ms=1_100,
    )

    original = service.knowledge.record_completed_task
    failures = {"count": 0}

    def fail_once(**kwargs):
        failures["count"] += 1
        if failures["count"] == 1:
            raise OSError("injected wiki write failure")
        return original(**kwargs)

    monkeypatch.setattr(service.knowledge, "record_completed_task", fail_once)

    assert service.sweep() == 0
    with service.telemetry.connect() as conn:
        row = conn.execute(
            "SELECT completion_attempt_count, last_error, materialized_at FROM in_flight_tasks WHERE id = ?",
            ("task-1",),
        ).fetchone()
    assert row["completion_attempt_count"] == 1
    assert "injected wiki write failure" in row["last_error"]
    assert row["materialized_at"] is None

    assert service.sweep() == 1
    assert service.sweep() == 0
    task_pages = list((tmp_path / "brain" / "operations/tasks").rglob("*.md"))
    assert len(task_pages) == 1


def test_disk_full_injection_surfaces_materialization_alert(tmp_path, monkeypatch):
    service = BrainService(tmp_path / "brain", tmp_path / "telemetry.db", tmp_path / "brain-index.db")
    service.telemetry.create_task("task-1", description="disk full", delegated_by="kublai")
    claim = service.telemetry.claim_task("temujin", now_ms=1_000)
    service.telemetry.complete_task(
        claim.id,
        "temujin",
        claim.claim_token,
        summary="cannot write",
        target_wiki_path="operations/tasks/2026/04/task-task-1.md",
        now_ms=1_100,
    )

    def disk_full(*_args, **_kwargs):
        raise OSError("No space left on device")

    monkeypatch.setattr(service.knowledge, "atomic_write", disk_full)

    for _ in range(3):
        assert service.sweep() == 0

    health = service.health()
    assert health["ok"] is False
    assert health["materialization_errors"] == 1
    assert health["materialization_alerts"] == 1


def test_js_clients_use_local_unix_socket_for_telemetry_and_knowledge(tmp_path):
    service = BrainService(tmp_path / "brain", tmp_path / "telemetry.db", tmp_path / "brain-index.db")
    service.knowledge.record_reflection(agent="kublai", reflection_id="reflection-1", body="socket lookup")
    service.reindex()

    socket_path = Path("/tmp") / f"bs-phase3-{os.getpid()}-{uuid.uuid4().hex[:8]}.sock"
    server = service.serve_socket(socket_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert call(
            socket_path,
            "telemetry.create_task",
            {"task_id": "task-1", "description": "rpc", "delegated_by": "kublai"},
        ) == {"ok": True, "result": "task-1"}

        node_script = f"""
        const telemetry = require('./kublai/telemetry-client');
        const knowledge = require('./kublai/knowledge-client');
        process.env.BRAIN_SERVICE_SOCKET = {json.dumps(str(socket_path))};

        async function main() {{
          const samples = [];
          for (let i = 0; i < 20; i++) {{
            const started = process.hrtime.bigint();
            await telemetry.heartbeat({{agent: 'temujin', status: 'active'}});
            samples.push(Number(process.hrtime.bigint() - started) / 1e6);
          }}
          const claimed = await telemetry.claimTask({{agent: 'temujin'}});
          const found = await knowledge.get({{node_type: 'reflection', typed_id: 'reflection-1'}});
          samples.sort((a, b) => a - b);
          const p99 = samples[samples.length - 1];
          console.log(JSON.stringify({{
            claimed: claimed.id,
            hasToken: !!claimed.claim_token,
            reflection: found && found.typed_id,
            p99
          }}));
        }}

        main().catch(error => {{
          console.error(error.stack || error.message);
          process.exit(1);
        }});
        """
        result = subprocess.run(
            [NODE_BIN, "-e", node_script],
            cwd=".",
            text=True,
            capture_output=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        assert payload["claimed"] == "task-1"
        assert payload["hasToken"] is True
        assert payload["reflection"] == "reflection-1"
        assert payload["p99"] < 50
    finally:
        server.shutdown()
        server.server_close()
        if socket_path.exists():
            socket_path.unlink()
