#!/usr/bin/env python3
"""
neo4j_v2_wal.py — SQLite write-ahead log for Neo4j outage buffering.

When Neo4j is unavailable, operations are buffered to a local SQLite WAL.
On reconnect, buffered operations are replayed in order.

WAL location: ~/.openclaw/neo4j-wal.db (survives reboots, unlike /tmp)

Usage:
    from neo4j_v2_wal import WAL
    wal = WAL()
    wal.buffer("CREATE (t:Task {task_id: $id, ...})", {"id": "abc"})
    replayed = wal.replay(driver)  # returns count of replayed operations
"""

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

WAL_PATH = Path.home() / ".openclaw" / "neo4j-wal.db"


class WAL:
    """SQLite-backed write-ahead log for Neo4j outage resilience."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else WAL_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Create WAL table if not exists."""
        with sqlite3.connect(str(self.path)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS wal_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cypher TEXT NOT NULL,
                    params TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    replayed INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_wal_replayed
                ON wal_entries(replayed, id)
            """)

    def buffer(self, cypher: str, params: dict) -> int:
        """Buffer a Cypher operation for later replay.

        Returns the WAL entry ID.
        """
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(str(self.path)) as conn:
            cursor = conn.execute(
                "INSERT INTO wal_entries (cypher, params, created_at) VALUES (?, ?, ?)",
                (cypher, json.dumps(params, default=str), now),
            )
            entry_id = cursor.lastrowid
            logger.info(f"WAL buffered entry {entry_id}: {cypher[:80]}...")
            return entry_id

    def replay(self, driver, batch_size: int = 50) -> int:
        """Replay buffered operations to Neo4j.

        Replays in order (FIFO). Marks entries as replayed on success.
        Stops on first failure to preserve ordering.

        Returns count of successfully replayed entries.
        """
        replayed = 0
        with sqlite3.connect(str(self.path)) as conn:
            rows = conn.execute(
                "SELECT id, cypher, params FROM wal_entries "
                "WHERE replayed = 0 ORDER BY id LIMIT ?",
                (batch_size,),
            ).fetchall()

            if not rows:
                return 0

            logger.info(f"WAL replaying {len(rows)} buffered entries")

            with driver.session() as session:
                for row_id, cypher, params_json in rows:
                    try:
                        params = json.loads(params_json)
                        session.run(cypher, **params)
                        conn.execute(
                            "UPDATE wal_entries SET replayed = 1 WHERE id = ?",
                            (row_id,),
                        )
                        replayed += 1
                    except Exception as e:
                        logger.error(f"WAL replay failed at entry {row_id}: {e}")
                        break  # Stop to preserve ordering

        if replayed > 0:
            logger.info(f"WAL replayed {replayed}/{len(rows)} entries")
        return replayed

    def pending_count(self) -> int:
        """Count of un-replayed entries."""
        with sqlite3.connect(str(self.path)) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM wal_entries WHERE replayed = 0"
            ).fetchone()
            return row[0]

    def cleanup(self, keep_days: int = 7) -> int:
        """Remove replayed entries older than keep_days."""
        cutoff = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(str(self.path)) as conn:
            cursor = conn.execute(
                "DELETE FROM wal_entries WHERE replayed = 1 "
                "AND created_at < datetime(?, '-' || ? || ' days')",
                (cutoff, keep_days),
            )
            deleted = cursor.rowcount
            if deleted > 0:
                logger.info(f"WAL cleaned up {deleted} old entries")
            return deleted


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Neo4j WAL management")
    parser.add_argument("--status", action="store_true", help="Show WAL status")
    parser.add_argument("--replay", action="store_true", help="Replay buffered entries")
    parser.add_argument("--cleanup", type=int, metavar="DAYS", help="Clean up entries older than N days")
    args = parser.parse_args()

    wal = WAL()

    if args.status:
        pending = wal.pending_count()
        print(f"WAL path: {wal.path}")
        print(f"Pending entries: {pending}")
    elif args.replay:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from neo4j_task_tracker import get_driver, close_driver
        driver = get_driver()
        try:
            count = wal.replay(driver)
            print(f"Replayed {count} entries")
        finally:
            close_driver()
    elif args.cleanup:
        count = wal.cleanup(keep_days=args.cleanup)
        print(f"Cleaned up {count} entries")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
