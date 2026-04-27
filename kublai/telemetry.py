"""SQLite telemetry store for Kublai task lifecycle and hot-path state.

Telemetry is intentionally separate from the markdown wiki. It owns fast,
atomic state: task claims, leases, heartbeats, rate counters, and notifications.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

DEFAULT_LEASE_TTL_MS = 1_103_329


class TelemetryError(Exception):
    """Base exception for telemetry failures."""


class NoPendingTaskError(TelemetryError):
    """Raised when no claimable task exists."""


class StaleClaimError(TelemetryError):
    """Raised when a worker tries to act with an expired or superseded claim."""


def utc_ms() -> int:
    return int(time.time() * 1000)


@dataclass(frozen=True)
class ClaimedTask:
    id: str
    claim_token: str
    lease_version: int
    expires_at: int
    payload: dict[str, Any]


class TelemetryStore:
    """Small SQLite store with fenced task claims."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=5.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode = WAL;
                PRAGMA synchronous = NORMAL;
                PRAGMA user_version = 1;

                CREATE TABLE IF NOT EXISTS schema_migrations (
                  version INTEGER PRIMARY KEY,
                  applied_at INTEGER NOT NULL,
                  description TEXT
                ) STRICT;

                CREATE TABLE IF NOT EXISTS agent_state (
                  agent TEXT PRIMARY KEY,
                  last_heartbeat INTEGER NOT NULL,
                  status TEXT NOT NULL,
                  meta TEXT CHECK(meta IS NULL OR json_valid(meta))
                ) STRICT;

                CREATE TABLE IF NOT EXISTS rate_limits (
                  agent TEXT NOT NULL,
                  operation TEXT NOT NULL,
                  window_ms INTEGER NOT NULL,
                  bucket_start_ms INTEGER NOT NULL,
                  count INTEGER NOT NULL DEFAULT 0,
                  last_hit INTEGER NOT NULL,
                  PRIMARY KEY (agent, operation, window_ms, bucket_start_ms)
                ) STRICT, WITHOUT ROWID;

                CREATE TABLE IF NOT EXISTS in_flight_tasks (
                  id TEXT PRIMARY KEY,
                  type TEXT NOT NULL,
                  description TEXT NOT NULL,
                  delegated_by TEXT NOT NULL,
                  assigned_to TEXT,
                  priority INTEGER NOT NULL,
                  status TEXT NOT NULL CHECK(status IN ('pending','in_progress','completed','failed','cancelled')),
                  claimed_by TEXT,
                  claimed_at INTEGER,
                  active_claim_token TEXT,
                  active_lease_version INTEGER,
                  completed_at INTEGER,
                  failed_at INTEGER,
                  results_json TEXT CHECK(results_json IS NULL OR json_valid(results_json)),
                  completion_summary TEXT,
                  completion_body_hash TEXT,
                  target_wiki_path TEXT,
                  wiki_path TEXT,
                  materialized_at INTEGER,
                  completion_attempt_count INTEGER NOT NULL DEFAULT 0,
                  last_error TEXT,
                  created_at INTEGER NOT NULL,
                  updated_at INTEGER NOT NULL
                ) STRICT;

                CREATE TABLE IF NOT EXISTS claim_locks (
                  task_id TEXT PRIMARY KEY REFERENCES in_flight_tasks(id) ON DELETE CASCADE,
                  claimed_by TEXT NOT NULL,
                  claim_token TEXT NOT NULL,
                  lease_version INTEGER NOT NULL,
                  claimed_at INTEGER NOT NULL,
                  expires_at INTEGER NOT NULL
                ) STRICT;

                CREATE TABLE IF NOT EXISTS notifications (
                  id TEXT PRIMARY KEY,
                  agent TEXT NOT NULL,
                  kind TEXT NOT NULL,
                  body TEXT NOT NULL,
                  read_at INTEGER,
                  created_at INTEGER NOT NULL
                ) STRICT;

                INSERT OR IGNORE INTO schema_migrations
                  VALUES (1, unixepoch() * 1000, 'initial telemetry schema');
                """
            )

    def create_task(
        self,
        task_id: str | None = None,
        *,
        type: str = "task",
        description: str,
        delegated_by: str,
        assigned_to: str | None = None,
        priority: int = 0,
        results: dict[str, Any] | None = None,
    ) -> str:
        now = utc_ms()
        task_id = task_id or f"task-{uuid.uuid4()}"
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO in_flight_tasks (
                  id, type, description, delegated_by, assigned_to, priority,
                  status, results_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
                """,
                (
                    task_id,
                    type,
                    description,
                    delegated_by,
                    assigned_to,
                    priority,
                    json.dumps(results or {}, sort_keys=True),
                    now,
                    now,
                ),
            )
        return task_id

    def claim_task(
        self,
        agent: str,
        *,
        lease_ttl_ms: int = DEFAULT_LEASE_TTL_MS,
        now_ms: int | None = None,
    ) -> ClaimedTask:
        now = now_ms or utc_ms()
        expires_at = now + lease_ttl_ms
        claim_token = str(uuid.uuid4())
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._sweep_expired_claims(conn, now)
            row = conn.execute(
                """
                SELECT * FROM in_flight_tasks
                WHERE status = 'pending'
                  AND (assigned_to IS NULL OR assigned_to = ?)
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
                """,
                (agent,),
            ).fetchone()
            if row is None:
                conn.execute("COMMIT")
                raise NoPendingTaskError("no pending task available")
            task_id = row["id"]
            inserted = conn.execute(
                """
                INSERT OR IGNORE INTO claim_locks (
                  task_id, claimed_by, claim_token, lease_version, claimed_at, expires_at
                ) VALUES (?, ?, ?, 1, ?, ?)
                """,
                (task_id, agent, claim_token, now, expires_at),
            ).rowcount
            if inserted != 1:
                conn.execute("COMMIT")
                raise NoPendingTaskError("claim lost to another worker")
            conn.execute(
                """
                UPDATE in_flight_tasks
                SET status = 'in_progress',
                    claimed_by = ?,
                    claimed_at = ?,
                    active_claim_token = ?,
                    active_lease_version = 1,
                    updated_at = ?
                WHERE id = ?
                """,
                (agent, now, claim_token, now, task_id),
            )
            conn.execute("COMMIT")
        return ClaimedTask(
            id=task_id,
            claim_token=claim_token,
            lease_version=1,
            expires_at=expires_at,
            payload=dict(row),
        )

    def renew_claim(
        self,
        task_id: str,
        agent: str,
        claim_token: str,
        *,
        lease_ttl_ms: int = DEFAULT_LEASE_TTL_MS,
        now_ms: int | None = None,
    ) -> ClaimedTask:
        now = now_ms or utc_ms()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            lock = self._valid_lock(conn, task_id, agent, claim_token, now)
            lease_version = int(lock["lease_version"]) + 1
            expires_at = now + lease_ttl_ms
            conn.execute(
                """
                UPDATE claim_locks
                SET lease_version = ?, expires_at = ?
                WHERE task_id = ?
                """,
                (lease_version, expires_at, task_id),
            )
            conn.execute(
                """
                UPDATE in_flight_tasks
                SET active_lease_version = ?, updated_at = ?
                WHERE id = ?
                """,
                (lease_version, now, task_id),
            )
            row = conn.execute("SELECT * FROM in_flight_tasks WHERE id = ?", (task_id,)).fetchone()
            conn.execute("COMMIT")
        return ClaimedTask(task_id, claim_token, lease_version, expires_at, dict(row))

    def complete_task(
        self,
        task_id: str,
        agent: str,
        claim_token: str,
        *,
        results: dict[str, Any] | None = None,
        summary: str = "",
        target_wiki_path: str | None = None,
        body_hash: str | None = None,
        now_ms: int | None = None,
    ) -> None:
        now = now_ms or utc_ms()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._valid_lock(conn, task_id, agent, claim_token, now)
            conn.execute("DELETE FROM claim_locks WHERE task_id = ?", (task_id,))
            conn.execute(
                """
                UPDATE in_flight_tasks
                SET status = 'completed',
                    completed_at = ?,
                    results_json = ?,
                    completion_summary = ?,
                    completion_body_hash = ?,
                    target_wiki_path = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    now,
                    json.dumps(results or {}, sort_keys=True),
                    summary,
                    body_hash,
                    target_wiki_path,
                    now,
                    task_id,
                ),
            )
            conn.execute("COMMIT")

    def sweep_expired_claims(self, *, now_ms: int | None = None) -> int:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            count = self._sweep_expired_claims(conn, now_ms or utc_ms())
            conn.execute("COMMIT")
        return count

    def pending_materializations(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM in_flight_tasks
                WHERE status = 'completed'
                  AND materialized_at IS NULL
                  AND target_wiki_path IS NOT NULL
                ORDER BY completed_at ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_materialized(self, task_id: str, wiki_path: str, *, now_ms: int | None = None) -> None:
        now = now_ms or utc_ms()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE in_flight_tasks
                SET wiki_path = ?, materialized_at = ?, updated_at = ?, last_error = NULL
                WHERE id = ?
                """,
                (wiki_path, now, now, task_id),
            )

    def mark_materialization_error(self, task_id: str, error: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE in_flight_tasks
                SET completion_attempt_count = completion_attempt_count + 1,
                    last_error = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (error[:1000], utc_ms(), task_id),
            )

    def heartbeat(self, agent: str, status: str = "ok", meta: dict[str, Any] | None = None) -> None:
        now = utc_ms()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_state(agent, last_heartbeat, status, meta)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(agent) DO UPDATE SET
                  last_heartbeat = excluded.last_heartbeat,
                  status = excluded.status,
                  meta = excluded.meta
                """,
                (agent, now, status, json.dumps(meta or {}, sort_keys=True)),
            )

    def increment_rate_limit(
        self,
        agent: str,
        operation: str,
        *,
        window_ms: int = 3_600_000,
        now_ms: int | None = None,
    ) -> int:
        now = now_ms or utc_ms()
        bucket = (now // window_ms) * window_ms
        with self.connect() as conn:
            row = conn.execute(
                """
                INSERT INTO rate_limits(agent, operation, window_ms, bucket_start_ms, count, last_hit)
                VALUES (?, ?, ?, ?, 1, ?)
                ON CONFLICT(agent, operation, window_ms, bucket_start_ms)
                DO UPDATE SET count = count + 1, last_hit = excluded.last_hit
                RETURNING count
                """,
                (agent, operation, window_ms, bucket, now),
            ).fetchone()
        return int(row["count"])

    def create_notification(self, agent: str, kind: str, body: str) -> str:
        notification_id = str(uuid.uuid4())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO notifications(id, agent, kind, body, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (notification_id, agent, kind, body, utc_ms()),
            )
        return notification_id

    def list_notifications(self, agent: str, *, unread_only: bool = False) -> list[dict[str, Any]]:
        clause = "AND read_at IS NULL" if unread_only else ""
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM notifications WHERE agent = ? {clause} ORDER BY created_at DESC",
                (agent,),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_notification_read(self, notification_id: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE notifications SET read_at = ? WHERE id = ?",
                (utc_ms(), notification_id),
            )

    def backup_to(self, destination: str | Path) -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as src, sqlite3.connect(destination) as dst:
            src.backup(dst)
        return destination

    def _sweep_expired_claims(self, conn: sqlite3.Connection, now: int) -> int:
        rows = conn.execute(
            "SELECT task_id FROM claim_locks WHERE expires_at <= ?",
            (now,),
        ).fetchall()
        for row in rows:
            conn.execute("DELETE FROM claim_locks WHERE task_id = ?", (row["task_id"],))
            conn.execute(
                """
                UPDATE in_flight_tasks
                SET status = 'pending',
                    active_claim_token = NULL,
                    updated_at = ?
                WHERE id = ? AND status = 'in_progress'
                """,
                (now, row["task_id"]),
            )
        return len(rows)

    def _valid_lock(
        self,
        conn: sqlite3.Connection,
        task_id: str,
        agent: str,
        claim_token: str,
        now: int,
    ) -> sqlite3.Row:
        lock = conn.execute(
            """
            SELECT * FROM claim_locks
            WHERE task_id = ? AND claimed_by = ? AND claim_token = ?
            """,
            (task_id, agent, claim_token),
        ).fetchone()
        if lock is None or int(lock["expires_at"]) <= now:
            raise StaleClaimError(f"stale claim for task {task_id}")
        return lock
