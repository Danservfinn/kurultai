#!/usr/bin/env python3
from __future__ import annotations

"""SQLite WAL coordination store for Hermes/Kublai group-chat response discipline.

This module is intentionally standalone: both agents can import it or use the
companion CLI without importing OpenClaw internals.
"""

import datetime as dt
import hashlib
import json
import secrets
import sqlite3
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parent
DEFAULT_DB = BASE / "coordination.db"
ACTIVE_LOCK_STATUSES = {"claimed", "deliberating", "ready_to_answer", "answering"}
TERMINAL_LOCK_STATUSES = {"answered", "timed_out", "cancelled", "failed", "expired"}


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def encode_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def decode_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


class CoordinationStore:
    def __init__(self, db_path: str | Path = DEFAULT_DB):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS response_locks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lock_key TEXT NOT NULL UNIQUE,
                    channel TEXT NOT NULL,
                    chat_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL DEFAULT '',
                    root_message_id TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    purpose TEXT NOT NULL DEFAULT 'answer',
                    tier TEXT NOT NULL DEFAULT 'tier1',
                    status TEXT NOT NULL DEFAULT 'claimed',
                    required_contributors_json TEXT NOT NULL DEFAULT '[]',
                    final_summary TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT,
                    owner_claim_token TEXT NOT NULL DEFAULT '',
                    owner_epoch INTEGER NOT NULL DEFAULT 1,
                    owner_heartbeat_at TEXT,
                    scope_version INTEGER NOT NULL DEFAULT 1,
                    risk_level TEXT NOT NULL DEFAULT 'low',
                    domain TEXT NOT NULL DEFAULT '',
                    request_type TEXT NOT NULL DEFAULT '',
                    ack_message_id TEXT,
                    final_answer_message_id TEXT,
                    reply_to_message_id TEXT,
                    support_agents_json TEXT NOT NULL DEFAULT '[]',
                    received_contributors_json TEXT NOT NULL DEFAULT '[]',
                    processed_contributors_json TEXT NOT NULL DEFAULT '[]'
                );

                CREATE TABLE IF NOT EXISTS coordination_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lock_id INTEGER,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(lock_id) REFERENCES response_locks(id)
                );

                CREATE TABLE IF NOT EXISTS contributions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lock_id INTEGER NOT NULL,
                    contributor TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    stance TEXT NOT NULL DEFAULT 'support',
                    key_points_json TEXT NOT NULL DEFAULT '[]',
                    objections_json TEXT NOT NULL DEFAULT '[]',
                    safe_public_attribution TEXT NOT NULL DEFAULT '',
                    blocking INTEGER NOT NULL DEFAULT 0,
                    processed_at TEXT,
                    FOREIGN KEY(lock_id) REFERENCES response_locks(id)
                );

                CREATE TABLE IF NOT EXISTS send_outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    send_key TEXT NOT NULL UNIQUE,
                    channel TEXT NOT NULL,
                    chat_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL DEFAULT '',
                    text TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    provider_message_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    sent_at TEXT,
                    payload_hash TEXT NOT NULL DEFAULT '',
                    payload_preview TEXT NOT NULL DEFAULT '',
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    message_thread_id TEXT NOT NULL DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS idx_response_locks_scope
                    ON response_locks(channel, chat_id, thread_id, root_message_id, status);
                CREATE INDEX IF NOT EXISTS idx_response_locks_expires
                    ON response_locks(expires_at, status);
                CREATE INDEX IF NOT EXISTS idx_coordination_events_lock
                    ON coordination_events(lock_id, id);
                CREATE INDEX IF NOT EXISTS idx_contributions_lock
                    ON contributions(lock_id, id);
                CREATE INDEX IF NOT EXISTS idx_send_outbox_status
                    ON send_outbox(status, id);
                """
            )
            self._migrate_schema(conn)

    def _migrate_schema(self, conn: sqlite3.Connection) -> None:
        """Additive migration for new columns on existing databases."""
        migrations = [
            ("response_locks", "owner_claim_token", "TEXT NOT NULL DEFAULT ''"),
            ("response_locks", "owner_epoch", "INTEGER NOT NULL DEFAULT 1"),
            ("response_locks", "owner_heartbeat_at", "TEXT"),
            ("response_locks", "scope_version", "INTEGER NOT NULL DEFAULT 1"),
            ("response_locks", "risk_level", "TEXT NOT NULL DEFAULT 'low'"),
            ("response_locks", "domain", "TEXT NOT NULL DEFAULT ''"),
            ("response_locks", "request_type", "TEXT NOT NULL DEFAULT ''"),
            ("response_locks", "ack_message_id", "TEXT"),
            ("response_locks", "final_answer_message_id", "TEXT"),
            ("response_locks", "reply_to_message_id", "TEXT"),
            ("response_locks", "support_agents_json", "TEXT NOT NULL DEFAULT '[]'"),
            ("response_locks", "received_contributors_json", "TEXT NOT NULL DEFAULT '[]'"),
            ("response_locks", "processed_contributors_json", "TEXT NOT NULL DEFAULT '[]'"),
            ("contributions", "stance", "TEXT NOT NULL DEFAULT 'support'"),
            ("contributions", "key_points_json", "TEXT NOT NULL DEFAULT '[]'"),
            ("contributions", "objections_json", "TEXT NOT NULL DEFAULT '[]'"),
            ("contributions", "safe_public_attribution", "TEXT NOT NULL DEFAULT ''"),
            ("contributions", "blocking", "INTEGER NOT NULL DEFAULT 0"),
            ("contributions", "processed_at", "TEXT"),
            ("send_outbox", "payload_hash", "TEXT NOT NULL DEFAULT ''"),
            ("send_outbox", "payload_preview", "TEXT NOT NULL DEFAULT ''"),
            ("send_outbox", "attempt_count", "INTEGER NOT NULL DEFAULT 0"),
            ("send_outbox", "last_error", "TEXT NOT NULL DEFAULT ''"),
            ("send_outbox", "message_thread_id", "TEXT NOT NULL DEFAULT ''"),
        ]
        for table, col, typedef in migrations:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")
            except sqlite3.OperationalError:
                pass  # Column already exists

    def pragma(self, name: str) -> str:
        with self.connect() as conn:
            row = conn.execute(f"PRAGMA {name}").fetchone()
            return str(row[0]) if row else ""

    def table_names(self) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            return [str(row["name"]) for row in rows]

    @staticmethod
    def make_lock_key(channel: str, chat_id: str, thread_id: str, root_message_id: str, purpose: str = "answer") -> str:
        parts = [channel, chat_id, thread_id or "", root_message_id, purpose]
        return "|".join(parts)

    @staticmethod
    def make_send_key(channel: str, chat_id: str, thread_id: str, root_message_id: str, owner: str, purpose: str = "answer") -> str:
        raw = "|".join([channel, chat_id, thread_id or "", root_message_id, owner, purpose])
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
        return f"{channel}:{chat_id}:{thread_id or '-'}:{root_message_id}:{owner}:{purpose}:{digest}"

    def claim_response_lock(
        self,
        channel: str,
        chat_id: str,
        root_message_id: str,
        owner: str,
        purpose: str = "answer",
        tier: str = "tier1",
        thread_id: str = "",
        required_contributors: list[str] | None = None,
        support_agents: list[str] | None = None,
        ttl_seconds: int | None = None,
        risk_level: str = "low",
        domain: str = "",
        request_type: str = "",
        reply_to_message_id: str | None = None,
    ) -> dict[str, Any]:
        self.init_schema()
        now = utc_now()
        expires_at = None
        if ttl_seconds:
            expires_at = (dt.datetime.now(dt.UTC) + dt.timedelta(seconds=ttl_seconds)).isoformat().replace("+00:00", "Z")
        lock_key = self.make_lock_key(channel, chat_id, thread_id, root_message_id, purpose)
        required = required_contributors or []
        support = support_agents or []
        claim_token = secrets.token_hex(16)
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM response_locks WHERE lock_key = ?", (lock_key,)).fetchone()
            if row and row["status"] in ACTIVE_LOCK_STATUSES and row["owner"] != owner:
                conn.execute("COMMIT")
                result = self._lock_row_to_dict(row)
                result["claimed"] = False
                return result
            if row:
                conn.execute(
                    """
                    UPDATE response_locks
                    SET owner = ?, tier = ?, required_contributors_json = ?, support_agents_json = ?,
                        updated_at = ?, expires_at = COALESCE(?, expires_at),
                        owner_claim_token = ?, owner_epoch = owner_epoch + 1,
                        owner_heartbeat_at = ?, risk_level = ?, domain = ?, request_type = ?
                    WHERE id = ?
                    """,
                    (owner, tier, encode_json(required), encode_json(support),
                     now, expires_at, claim_token, now, risk_level, domain, request_type, row["id"]),
                )
                lock_id = int(row["id"])
            else:
                cur = conn.execute(
                    """
                    INSERT INTO response_locks
                    (lock_key, channel, chat_id, thread_id, root_message_id, owner, purpose, tier, status,
                     required_contributors_json, support_agents_json, created_at, updated_at, expires_at,
                     owner_claim_token, owner_epoch, owner_heartbeat_at, scope_version,
                     risk_level, domain, request_type, reply_to_message_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'claimed', ?, ?, ?, ?, ?, ?, 1, ?, 1, ?, ?, ?, ?)
                    """,
                    (lock_key, channel, chat_id, thread_id or "", root_message_id, owner, purpose, tier,
                     encode_json(required), encode_json(support), now, now, expires_at,
                     claim_token, now, risk_level, domain, request_type, reply_to_message_id),
                )
                lock_id = int(cur.lastrowid)
            self._record_event(conn, lock_id, "lock_claimed", owner, {
                "channel": channel, "chat_id": chat_id, "root_message_id": root_message_id,
                "tier": tier, "claim_token": claim_token
            })
            conn.execute("COMMIT")
            row = conn.execute("SELECT * FROM response_locks WHERE id = ?", (lock_id,)).fetchone()
            result = self._lock_row_to_dict(row)
            result["claimed"] = True
            return result

    def get_active_lock(
        self,
        channel: str,
        chat_id: str,
        root_message_id: str,
        thread_id: str = "",
        purpose: str = "answer",
    ) -> dict[str, Any] | None:
        """Return active (non-terminal) lock for this scope, or None."""
        self.init_schema()
        lock_key = self.make_lock_key(channel, chat_id, thread_id, root_message_id, purpose)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM response_locks WHERE lock_key = ? AND status NOT IN ('answered','timed_out','cancelled','failed','expired')",
                (lock_key,),
            ).fetchone()
            return self._lock_row_to_dict(row) if row else None

    def update_heartbeat(self, lock_id: int, owner: str, claim_token: str) -> bool:
        """Update owner heartbeat only if claim_token matches current owner. Returns True if updated."""
        self.init_schema()
        now = utc_now()
        with self.connect() as conn:
            result = conn.execute(
                "UPDATE response_locks SET owner_heartbeat_at = ?, updated_at = ? WHERE id = ? AND owner = ? AND owner_claim_token = ?",
                (now, now, lock_id, owner, claim_token),
            )
            return result.rowcount > 0

    def mark_lock_status(self, lock_id: int, status: str, actor: str = "", note: str = "") -> dict[str, Any]:
        """Transition lock to any status and record an event."""
        self.init_schema()
        now = utc_now()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE response_locks SET status = ?, updated_at = ? WHERE id = ?", (status, now, lock_id))
            self._record_event(conn, lock_id, f"lock_status_changed", actor, {"new_status": status, "note": note})
            conn.execute("COMMIT")
            row = conn.execute("SELECT * FROM response_locks WHERE id = ?", (lock_id,)).fetchone()
            return self._lock_row_to_dict(row)

    def mark_transferable(self, lock_id: int, reason: str = "heartbeat_stale") -> dict[str, Any]:
        """Mark a stale-owner lock as transferable. Increments epoch to invalidate old claim token."""
        self.init_schema()
        now = utc_now()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "UPDATE response_locks SET status = 'transferable', owner_epoch = owner_epoch + 1, updated_at = ? WHERE id = ?",
                (now, lock_id),
            )
            self._record_event(conn, lock_id, "lock_transferable", "", {"reason": reason})
            conn.execute("COMMIT")
            row = conn.execute("SELECT * FROM response_locks WHERE id = ?", (lock_id,)).fetchone()
            return self._lock_row_to_dict(row)

    def sweep_expired(self, now_iso: str | None = None) -> list[dict[str, Any]]:
        """Expire all active locks past their expires_at. Returns list of expired lock dicts."""
        self.init_schema()
        now = now_iso or utc_now()
        expired = []
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT * FROM response_locks WHERE expires_at IS NOT NULL AND expires_at < ? AND status NOT IN ('answered','timed_out','cancelled','failed','expired','transferable')",
                (now,),
            ).fetchall()
            for row in rows:
                conn.execute("UPDATE response_locks SET status = 'expired', updated_at = ? WHERE id = ?", (now, row["id"]))
                self._record_event(conn, int(row["id"]), "lock_expired", "sweeper", {"expires_at": row["expires_at"]})
                expired.append(self._lock_row_to_dict(row))
            conn.execute("COMMIT")
        return expired

    def get_active_locks_for_sweep(self) -> list[dict[str, Any]]:
        """Return all non-terminal locks with heartbeat info for sweeper."""
        self.init_schema()
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM response_locks WHERE status NOT IN ('answered','timed_out','cancelled','failed','expired')",
            ).fetchall()
            return [self._lock_row_to_dict(row) for row in rows]

    def set_ack_message_id(self, lock_id: int, ack_message_id: str) -> None:
        self.init_schema()
        now = utc_now()
        with self.connect() as conn:
            conn.execute("UPDATE response_locks SET ack_message_id = ?, updated_at = ? WHERE id = ?", (ack_message_id, now, lock_id))

    def set_final_answer_message_id(self, lock_id: int, message_id: str) -> None:
        self.init_schema()
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                "UPDATE response_locks SET final_answer_message_id = ?, updated_at = ? WHERE id = ?",
                (message_id, now, lock_id),
            )

    def add_contribution(
        self,
        lock_id: int,
        contributor: str,
        summary: str,
        detail: str = "",
        stance: str = "support",
        key_points: list[str] | None = None,
        objections: list[str] | None = None,
        safe_public_attribution: str = "",
        blocking: bool = False,
    ) -> dict[str, Any]:
        self.init_schema()
        now = utc_now()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                """INSERT INTO contributions
                   (lock_id, contributor, summary, detail, created_at, stance,
                    key_points_json, objections_json, safe_public_attribution, blocking)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (lock_id, contributor, summary, detail, now, stance,
                 encode_json(key_points or []), encode_json(objections or []),
                 safe_public_attribution, int(blocking)),
            )
            contribution_id = int(cur.lastrowid)
            conn.execute(
                "UPDATE response_locks SET status = CASE WHEN status = 'claimed' THEN 'deliberating' ELSE status END, updated_at = ? WHERE id = ?",
                (now, lock_id),
            )
            self._record_event(conn, lock_id, "contribution_added", contributor, {"summary": summary, "stance": stance, "blocking": int(blocking)})
            conn.execute("COMMIT")
        return {
            "id": contribution_id, "lock_id": lock_id, "contributor": contributor,
            "summary": summary, "detail": detail, "created_at": now,
            "stance": stance, "key_points": key_points or [], "objections": objections or [],
            "safe_public_attribution": safe_public_attribution, "blocking": blocking,
        }

    def process_contribution(self, lock_id: int, contribution_id: int, actor: str, decision: str, note: str = "") -> dict[str, Any]:
        self.init_schema()
        now = utc_now()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._record_event(
                conn,
                lock_id,
                "contribution_processed",
                actor,
                {"contribution_id": contribution_id, "decision": decision, "note": note},
            )
            conn.execute("COMMIT")
        return {
            "event_type": "contribution_processed",
            "lock_id": lock_id,
            "contribution_id": contribution_id,
            "actor": actor,
            "decision": decision,
            "note": note,
            "created_at": now,
        }

    def finalize_lock(self, lock_id: int, status: str, final_summary: str = "", actor: str = "") -> dict[str, Any]:
        self.init_schema()
        now = utc_now()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE response_locks SET status = ?, final_summary = ?, updated_at = ? WHERE id = ?", (status, final_summary, now, lock_id))
            self._record_event(conn, lock_id, "lock_finalized", actor, {"status": status, "final_summary": final_summary})
            conn.execute("COMMIT")
            row = conn.execute("SELECT * FROM response_locks WHERE id = ?", (lock_id,)).fetchone()
            return self._lock_row_to_dict(row)

    def enqueue_send_once(self, send_key: str, channel: str, chat_id: str, thread_id: str, text: str) -> dict[str, Any]:
        self.init_schema()
        now = utc_now()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM send_outbox WHERE send_key = ?", (send_key,)).fetchone()
            if row:
                conn.execute("COMMIT")
                result = self._outbox_row_to_dict(row)
                result["enqueued"] = False
                return result
            cur = conn.execute(
                "INSERT INTO send_outbox (send_key, channel, chat_id, thread_id, text, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
                (send_key, channel, chat_id, thread_id or "", text, now, now),
            )
            row = conn.execute("SELECT * FROM send_outbox WHERE id = ?", (int(cur.lastrowid),)).fetchone()
            conn.execute("COMMIT")
            result = self._outbox_row_to_dict(row)
            result["enqueued"] = True
            return result

    def get_outbox_item(self, send_key: str) -> dict[str, Any] | None:
        self.init_schema()
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM send_outbox WHERE send_key = ?", (send_key,)).fetchone()
            return self._outbox_row_to_dict(row) if row else None

    def mark_send_sent(self, send_key: str, provider_message_id: str) -> dict[str, Any]:
        self.init_schema()
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                "UPDATE send_outbox SET status = 'sent', provider_message_id = ?, sent_at = ?, updated_at = ? WHERE send_key = ?",
                (provider_message_id, now, now, send_key),
            )
            row = conn.execute("SELECT * FROM send_outbox WHERE send_key = ?", (send_key,)).fetchone()
            if not row:
                raise KeyError(f"unknown send_key: {send_key}")
            return self._outbox_row_to_dict(row)

    def explain_why(self, channel: str, chat_id: str, root_message_id: str, thread_id: str = "", purpose: str = "answer") -> dict[str, Any]:
        self.init_schema()
        lock_key = self.make_lock_key(channel, chat_id, thread_id, root_message_id, purpose)
        with self.connect() as conn:
            lock_row = conn.execute("SELECT * FROM response_locks WHERE lock_key = ?", (lock_key,)).fetchone()
            if not lock_row:
                return {"lock": None, "contributions": [], "events": []}
            lock = self._lock_row_to_dict(lock_row)
            contributions = [self._contribution_row_to_dict(row) for row in conn.execute("SELECT * FROM contributions WHERE lock_id = ? ORDER BY id", (lock["lock_id"],)).fetchall()]
            events = [self._event_row_to_dict(row) for row in conn.execute("SELECT * FROM coordination_events WHERE lock_id = ? ORDER BY id", (lock["lock_id"],)).fetchall()]
            return {"lock": lock, "contributions": contributions, "events": events}

    def _record_event(self, conn: sqlite3.Connection, lock_id: int, event_type: str, actor: str, payload: dict[str, Any]) -> None:
        conn.execute(
            "INSERT INTO coordination_events (lock_id, event_type, actor, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (lock_id, event_type, actor, encode_json(payload), utc_now()),
        )

    @staticmethod
    def _lock_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        keys = row.keys()
        return {
            "lock_id": int(row["id"]),
            "lock_key": row["lock_key"],
            "channel": row["channel"],
            "chat_id": row["chat_id"],
            "thread_id": row["thread_id"],
            "root_message_id": row["root_message_id"],
            "owner": row["owner"],
            "purpose": row["purpose"],
            "tier": row["tier"],
            "status": row["status"],
            "required_contributors": decode_json(row["required_contributors_json"], []),
            "support_agents": decode_json(row["support_agents_json"], []) if "support_agents_json" in keys else [],
            "received_contributors": decode_json(row["received_contributors_json"], []) if "received_contributors_json" in keys else [],
            "processed_contributors": decode_json(row["processed_contributors_json"], []) if "processed_contributors_json" in keys else [],
            "final_summary": row["final_summary"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "expires_at": row["expires_at"],
            "owner_claim_token": row["owner_claim_token"] if "owner_claim_token" in keys else "",
            "owner_epoch": int(row["owner_epoch"]) if "owner_epoch" in keys else 1,
            "owner_heartbeat_at": row["owner_heartbeat_at"] if "owner_heartbeat_at" in keys else None,
            "scope_version": int(row["scope_version"]) if "scope_version" in keys else 1,
            "risk_level": row["risk_level"] if "risk_level" in keys else "low",
            "domain": row["domain"] if "domain" in keys else "",
            "request_type": row["request_type"] if "request_type" in keys else "",
            "ack_message_id": row["ack_message_id"] if "ack_message_id" in keys else None,
            "final_answer_message_id": row["final_answer_message_id"] if "final_answer_message_id" in keys else None,
            "reply_to_message_id": row["reply_to_message_id"] if "reply_to_message_id" in keys else None,
        }

    @staticmethod
    def _contribution_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        keys = row.keys()
        return {
            "id": int(row["id"]),
            "lock_id": int(row["lock_id"]),
            "contributor": row["contributor"],
            "summary": row["summary"],
            "detail": row["detail"],
            "created_at": row["created_at"],
            "stance": row["stance"] if "stance" in keys else "support",
            "key_points": decode_json(row["key_points_json"], []) if "key_points_json" in keys else [],
            "objections": decode_json(row["objections_json"], []) if "objections_json" in keys else [],
            "safe_public_attribution": row["safe_public_attribution"] if "safe_public_attribution" in keys else "",
            "blocking": bool(row["blocking"]) if "blocking" in keys else False,
            "processed_at": row["processed_at"] if "processed_at" in keys else None,
        }

    @staticmethod
    def _event_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {"id": int(row["id"]), "lock_id": int(row["lock_id"]) if row["lock_id"] is not None else None, "event_type": row["event_type"], "actor": row["actor"], "payload": decode_json(row["payload_json"], {}), "created_at": row["created_at"]}

    @staticmethod
    def _outbox_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {"id": int(row["id"]), "send_key": row["send_key"], "channel": row["channel"], "chat_id": row["chat_id"], "thread_id": row["thread_id"], "text": row["text"], "status": row["status"], "provider_message_id": row["provider_message_id"], "created_at": row["created_at"], "updated_at": row["updated_at"], "sent_at": row["sent_at"]}
