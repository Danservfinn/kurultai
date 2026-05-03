import threading

import pytest

from kublai.telemetry import NoPendingTaskError, StaleClaimError, TelemetryStore


def test_claim_race_has_single_winner(tmp_path):
    store = TelemetryStore(tmp_path / "telemetry.db")
    store.create_task("task-1", description="race", delegated_by="kublai")
    winners = []
    errors = []

    def worker(i):
        try:
            winners.append(store.claim_task(f"agent-{i}", lease_ttl_ms=10_000))
        except NoPendingTaskError as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(100)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(winners) == 1
    assert len(errors) == 99


def test_fencing_rejects_stale_worker_after_lease_expiry(tmp_path):
    store = TelemetryStore(tmp_path / "telemetry.db")
    store.create_task("task-1", description="fenced", delegated_by="kublai")

    first = store.claim_task("agent-a", lease_ttl_ms=100, now_ms=1_000)
    assert store.sweep_expired_claims(now_ms=1_101) == 1
    second = store.claim_task("agent-b", lease_ttl_ms=100, now_ms=1_102)

    with pytest.raises(StaleClaimError):
        store.complete_task(
            first.id,
            "agent-a",
            first.claim_token,
            summary="stale",
            now_ms=1_103,
        )

    store.complete_task(
        second.id,
        "agent-b",
        second.claim_token,
        summary="fresh",
        now_ms=1_104,
    )


def test_renew_claim_extends_lease_and_increments_version(tmp_path):
    store = TelemetryStore(tmp_path / "telemetry.db")
    store.create_task("task-1", description="renew", delegated_by="kublai")
    claim = store.claim_task("agent-a", lease_ttl_ms=300, now_ms=1_000)

    for i in range(1, 6):
        claim = store.renew_claim(
            claim.id,
            "agent-a",
            claim.claim_token,
            lease_ttl_ms=300,
            now_ms=1_000 + i * 100,
        )
        assert claim.lease_version == i + 1
        assert claim.expires_at == 1_000 + i * 100 + 300


def test_online_backup_restores_task_state(tmp_path):
    store = TelemetryStore(tmp_path / "telemetry.db")
    store.create_task("task-1", description="backup", delegated_by="kublai")
    backup = store.backup_to(tmp_path / "backup.db")

    restored = TelemetryStore(backup)
    with restored.connect() as conn:
        row = conn.execute("SELECT id, status FROM in_flight_tasks").fetchone()
    assert dict(row) == {"id": "task-1", "status": "pending"}


def test_dashboard_statuses_normalize_to_claimable_lowercase(tmp_path):
    store = TelemetryStore(tmp_path / "telemetry.db")
    created = store.create_task_full(
        task_id="task-dashboard",
        title="Dashboard task",
        prompt="do work",
        assigned_to="temujin",
        status="PENDING",
    )
    assert created == {"task_id": "task-dashboard"}

    with store.connect() as conn:
        row = conn.execute("SELECT status FROM in_flight_tasks WHERE id = ?", ("task-dashboard",)).fetchone()
    assert row["status"] == "pending"

    claim = store.claim_task("temujin", lease_ttl_ms=300, now_ms=1_000)
    assert claim.id == "task-dashboard"


def test_retry_resets_to_claimable_lowercase_pending(tmp_path):
    store = TelemetryStore(tmp_path / "telemetry.db")
    store.create_task("task-retry", description="retry", delegated_by="kublai")
    claim = store.claim_task("temujin", lease_ttl_ms=300, now_ms=1_000)
    store.complete_task(claim.id, "temujin", claim.claim_token, summary="done", now_ms=1_010)

    result = store.retry_task(task_id="task-retry", agent="temujin")
    assert result["task_id"] == "task-retry"
    with store.connect() as conn:
        row = conn.execute("SELECT status FROM in_flight_tasks WHERE id = ?", ("task-retry",)).fetchone()
    assert row["status"] == "pending"
