"""Lightweight health helpers for Phase 1 fixtures."""

from __future__ import annotations

from pathlib import Path

from .telemetry import TelemetryStore


def health_snapshot(telemetry: TelemetryStore, wiki_root: str | Path) -> dict:
    wiki_root = Path(wiki_root)
    with telemetry.connect() as conn:
        tasks = conn.execute("SELECT status, count(*) AS n FROM in_flight_tasks GROUP BY status").fetchall()
        agents = conn.execute("SELECT count(*) AS n FROM agent_state").fetchone()["n"]
        materialization_errors = conn.execute(
            """
            SELECT count(*) AS n FROM in_flight_tasks
            WHERE materialized_at IS NULL
              AND completion_attempt_count > 0
            """
        ).fetchone()["n"]
        materialization_alerts = conn.execute(
            """
            SELECT count(*) AS n FROM in_flight_tasks
            WHERE materialized_at IS NULL
              AND completion_attempt_count >= 3
            """
        ).fetchone()["n"]
    return {
        "ok": materialization_alerts == 0,
        "wiki_root_exists": wiki_root.exists(),
        "agent_count": agents,
        "tasks": {row["status"]: row["n"] for row in tasks},
        "materialization_errors": materialization_errors,
        "materialization_alerts": materialization_alerts,
    }
