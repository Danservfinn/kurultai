#!/usr/bin/env python3
"""
notification_queue.py — SQLite-backed persistent notification queue.

Dequeue AFTER send (not before) to prevent message loss on crash.
Uses WAL mode for concurrent read/write safety.

Usage:
    from notification_queue import NotificationQueue
    q = NotificationQueue()
    q.enqueue(task_id="abc", agent="temujin", notify_target="+1...", message="Done")
    item = q.peek()
    # ... send notification ...
    q.mark_sent(item["id"])
"""

import os
import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = Path.home() / ".openclaw" / "notifications" / "queue.db"
MAX_ATTEMPTS = 5


class NotificationQueue:
    """Persistent notification queue with retry support."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self._init_db()

    def _init_db(self):
        """Create queue table if not exists, set permissions."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""CREATE TABLE IF NOT EXISTS queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                agent TEXT NOT NULL,
                notify_target TEXT NOT NULL,
                message TEXT NOT NULL,
                attempts INTEGER DEFAULT 0,
                last_error TEXT DEFAULT NULL,
                created_at TEXT NOT NULL,
                sent_at TEXT DEFAULT NULL,
                status TEXT DEFAULT 'pending'
            )""")
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_queue_status
                ON queue(status, created_at)""")
        # Restrict file permissions
        try:
            os.chmod(self.db_path, 0o600)
        except OSError:
            pass

    def enqueue(self, task_id: str, agent: str, notify_target: str,
                message: str) -> int:
        """Add notification to queue. Returns queue entry ID."""
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute(
                "INSERT INTO queue (task_id, agent, notify_target, message, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (task_id, agent, notify_target, message, now),
            )
            entry_id = cursor.lastrowid
            logger.info(f"Notification queued #{entry_id} for task {task_id}")
            return entry_id

    def peek(self) -> Optional[dict]:
        """Get the oldest pending notification without removing it."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM queue WHERE status = 'pending' "
                f"AND attempts < {MAX_ATTEMPTS} "
                "ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None

    def mark_sent(self, entry_id: int):
        """Mark notification as successfully sent."""
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "UPDATE queue SET status = 'sent', sent_at = ? WHERE id = ?",
                (now, entry_id),
            )
            logger.info(f"Notification #{entry_id} sent")

    def increment_attempts(self, entry_id: int, error: str = ""):
        """Increment attempt count. Moves to 'failed' if max exceeded."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "UPDATE queue SET attempts = attempts + 1, last_error = ?, "
                "status = CASE WHEN attempts + 1 >= ? THEN 'failed' ELSE 'pending' END "
                "WHERE id = ?",
                (error[:500], MAX_ATTEMPTS, entry_id),
            )

    def pending_count(self) -> int:
        """Count of unsent pending notifications."""
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM queue WHERE status = 'pending'"
            ).fetchone()
            return row[0]

    def failed_count(self) -> int:
        """Count of failed notifications (exceeded max attempts)."""
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM queue WHERE status = 'failed'"
            ).fetchone()
            return row[0]

    def cleanup(self, keep_days: int = 7) -> int:
        """Remove sent notifications older than keep_days."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute(
                "DELETE FROM queue WHERE status = 'sent' "
                "AND sent_at < datetime('now', '-' || ? || ' days')",
                (keep_days,),
            )
            deleted = cursor.rowcount
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old notifications")
            return deleted


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Notification queue management")
    parser.add_argument("--status", action="store_true", help="Show queue status")
    parser.add_argument("--cleanup", type=int, metavar="DAYS",
                        help="Clean up sent entries older than N days")
    args = parser.parse_args()

    q = NotificationQueue()

    if args.status:
        print(f"DB path: {q.db_path}")
        print(f"Pending: {q.pending_count()}")
        print(f"Failed: {q.failed_count()}")
    elif args.cleanup:
        count = q.cleanup(keep_days=args.cleanup)
        print(f"Cleaned up {count} entries")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
