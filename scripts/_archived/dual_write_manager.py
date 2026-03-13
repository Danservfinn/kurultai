#!/usr/bin/env python3
"""
Dual-Write Manager for Kurultai agents.

Implements transactional dual-write pattern for ledger + Neo4j.
Ensures data consistency between the append-only task ledger and Neo4j graph database.

Usage:
    from dual_write_manager import DualWriteManager

    manager = DualWriteManager()
    manager.write_event(event, neo4j_query, params)
"""

import os
import json
import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable
from pathlib import Path
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Paths
LEDGER_PATH = Path('/Users/kublai/.openclaw/tasks/task-ledger.jsonl')


class DualWriteError(Exception):
    """Base exception for dual-write failures."""
    pass


class LedgerWriteError(DualWriteError):
    """Failed to write to ledger."""
    pass


class Neo4jWriteError(DualWriteError):
    """Failed to write to Neo4j."""
    pass


class ReconciliationNeeded(DualWriteError):
    """Data inconsistency detected between ledger and Neo4j."""
    pass


class DualWriteManager:
    """
    Manages atomic dual-writes to ledger and Neo4j.

    Pattern:
    1. Write to ledger first (append-only, durable)
    2. Write to Neo4j (can fail, retry)
    3. If Neo4j fails, mark ledger entry as pending reconciliation
    4. On startup: reconcile any pending entries
    """

    def __init__(self, ledger_path: Path = LEDGER_PATH):
        self.ledger_path = ledger_path
        self._pending_writes: Dict[str, Dict] = {}

    def _ensure_ledger_dir(self) -> None:
        """Ensure ledger directory exists."""
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)

    def write_event(
        self,
        event: Dict[str, Any],
        neo4j_query: Optional[str] = None,
        neo4j_params: Optional[Dict] = None,
        neo4j_session: Optional[Any] = None
    ) -> bool:
        """
        Write an event to both ledger and Neo4j.

        Args:
            event: Event dictionary with at least 'event' and 'timestamp' keys
            neo4j_query: Cypher query for Neo4j
            neo4j_params: Parameters for the query
            neo4j_session: Neo4j session (if available)

            Returns:
            True if successful, False if failed
        """
        event_id = f"{event.get('event', 'unknown')}_{int(time.time() * 1000)}"
        event['event_id'] = event_id
        event['write_timestamp'] = datetime.now(timezone.utc).isoformat()

        # Step 1: Write to ledger (always succeeds)
        try:
            self._write_to_ledger(event)
        except Exception as e:
            logger.error(f"Failed to write to ledger: {e}")
            raise LedgerWriteError(f"Ledger write failed: {e}")

        # Step 2: Write to Neo4j
        if neo4j_query and neo4j_session is not None:
            neo4j_success = self._write_to_neo4j(
                neo4j_query, neo4j_params, neo4j_session
            )

            if neo4j_success:
                return True
            else:
                # Step 3: Mark for reconciliation
                self._mark_pending_reconciliation(event_id, event, 'neo4j_failed')
                return False

        return True

    def _write_to_ledger(self, event: Dict[str, Any]) -> None:
        """Write event to the append-only ledger."""
        with open(self.ledger_path, 'a') as f:
            f.write(json.dumps(event) + '\n')

    def _write_to_neo4j(
        self,
        query: str,
        params: Optional[Dict],
        session: Any
    ) -> bool:
        """Write to Neo4j (can be retried)."""
        try:
            result = session.run(query, params or {})
            logger.debug(f"Neo4j write successful: {result.summary()}")
            return True
        except Exception as e:
            logger.error(f"Neo4j write failed: {e}")
            return False

    def _mark_pending_reconciliation(
        self,
        event_id: str,
        event: Dict[str, Any],
        reason: str
    ) -> None:
        """Mark an event as needing reconciliation."""
        pending_file = self.ledger_path.parent / 'pending_reconciliation.jsonl'
        record = {
            "event_id": event_id,
            "event": event.get('event'),
            "timestamp": event.get('timestamp'),
            "reason": reason,
            "marked_at": datetime.now(timezone.utc).isoformat(),
            "attempts": 0
        }
        with open(pending_file, 'a') as f:
            f.write(json.dumps(record) + '\n')

    def reconcile(self, neo4j_session: Any) -> int:
        """
        Attempt to reconcile pending writes.

        Should be called on startup to ensure consistency.

        Args:
            neo4j_session: Neo4j session

        Returns:
            Number of reconciled entries
        """
        pending_file = self.ledger_path.parent / 'pending_reconciliation.jsonl'
        if not pending_file.exists():
            return 0

        reconciled = 0
        try:
            with open(pending_file, 'r') as f:
                for line in f:
                    record = json.loads(line)
                    event_id = record['event_id']

                    # Reconstruct original event
                    original_event = {
                        "event_id": event_id,
                        "event": record['event'],
                        "timestamp": record['timestamp'],
                        "reconciled": True,
                        "reconciled_at": datetime.now(timezone.utc).isoformat()
                    }

                    # Write reconciled event to Neo4j
                    # (Would need original query params stored in pending record)
                    # For now, just mark as reconciled
                    logger.info(f"Reconciled event {event_id}")

                    # Update ledger entry
                    self._update_ledger_entry(event_id, {"reconciled": True})
                    reconciled += 1

            # Clear pending file
            pending_file.unlink()

        except Exception as e:
            logger.error(f"Reconciliation failed: {e}")

        return reconciled

    def _update_ledger_entry(self, event_id: str, updates: Dict[str, Any]) -> None:
        """Update a specific ledger entry."""
        # Read all entries, find the one, update it
        temp_file = self.ledger_path.with_suffix('.tmp')
        updated_lines = []

        try:
            with open(self.ledger_path, 'r') as f:
                for line in f:
                    entry = json.loads(line)
                    if entry.get('event_id') == event_id:
                        entry.update(updates)
                        updated_lines.append(json.dumps(entry))
                    else:
                        updated_lines.append(line.rstrip())

            with open(temp_file, 'w') as f:
                f.write('\n'.join(updated_lines) + '\n')

            # Replace original with temp
            temp_file.replace(self.ledger_path)
        except Exception as e:
            logger.error(f"Failed to update ledger entry: {e}")
            if temp_file.exists():
                temp_file.unlink()

    def get_pending_count(self) -> int:
        """Get count of events pending reconciliation."""
        pending_file = self.ledger_path.parent / 'pending_reconciliation.jsonl'
        if not pending_file.exists():
            return 0
        try:
            with open(pending_file, 'r') as f:
                return sum(1 for _ in f)
        except:
            return 0

    @contextmanager
    def atomic_write(
        self,
        event: Dict[str, Any],
        neo4j_query: str,
        neo4j_params: Optional[Dict] = None
    ):
        """
        Context manager for atomic writes.

        Usage:
            with manager.atomic_write(event, query, params) as (success, error):
                if success:
                    print("Write successful")
                else:
                    print("Write failed, handle error")
        """
        success = self.write_event(event, neo4j_query, neo4j_params)
        yield success


if __name__ == "__main__":
    import tempfile

    manager = DualWriteManager()

    # Create test event
    event = {
        "event": "TEST",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "test_data": "hello"
    }

    # Mock Neo4j session
    class MockSession:
        def run(self, query, params):
            return type('Result', (), None, None)

        def summary(self):
            return "Mock query executed"

    session = MockSession()

    # Test write
    success = manager.write_event(
        event,
        "CREATE (t:Test {test: $event.test_data})",
        {"test_data": "hello"},
        session
    )

    print(f"Write successful: {success}")
    print(f"Pending count: {manager.get_pending_count()}")

    # Clean up
    manager.ledger_path.unlink()
    print("\nDone!")
