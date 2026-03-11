#!/usr/bin/env python3
"""
Gate Repository - Abstraction layer for pending gate discovery.

This module provides a unified interface for finding and managing pending
completion gates, with three implementations:

1. Neo4jGateRepository: Primary, uses indexed Neo4j query (fastest)
2. CachedGateRepository: Wraps any repository with 60-second in-memory cache
3. FilesystemGateRepository: Fallback, uses filesystem glob scan

The factory function get_gate_repository() returns the appropriate
implementation based on Neo4j availability and configuration.

Architecture:
    Neo4jGateRepository (primary) → CachedGateRepository (cache layer)
                                        ↓ (fallback on error)
                                  FilesystemGateRepository

Usage:
    from gate_repository import get_gate_repository

    repo = get_gate_repository()
    pending_gates = repo.find_pending()  # List[GateTask]
    gate_status = repo.get_gate_status(task_id)  # GateState
    repo.set_gate_status(task_id, GateState.WAITING_FOLLOWUPS)

Design: ~/.openclaw/agents/ogedei/workspace/gate-repository-design.md
"""

import os
import sys
import glob
import time
import re
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kurultai_paths import AGENTS_DIR
from gate_utils import VALID_AGENTS


class GateState(Enum):
    """Gate lifecycle states stored in Neo4j gate_status."""
    NONE = "none"                      # No gate created
    WAITING_FOLLOWUPS = "waiting_followups"  # Pending gate state
    PASSED = "passed"                  # Gate passed (.gate-passed.done.md)
    BLOCKED = "blocked"                # Gate blocked (.gate-blocked.md)
    FAILED = "failed"                  # Gate failed (rare)


@dataclass
class GateTask:
    """A task in pending gate state."""
    task_id: str
    agent: str
    file_path: Path
    title: Optional[str] = None
    gate_status: GateState = GateState.WAITING_FOLLOWUPS
    modified_at: datetime = field(default_factory=datetime.now)

    def __hash__(self):
        return hash(self.task_id)

    def __eq__(self, other):
        if not isinstance(other, GateTask):
            return False
        return self.task_id == other.task_id


# =============================================================================
# Neo4j Error Handling
# =============================================================================

class Neo4jUnavailableError(Exception):
    """Raised when Neo4j is not available for query."""
    pass


# =============================================================================
# Abstract Repository Interface
# =============================================================================

class GateRepository(ABC):
    """Abstract base class for gate repositories."""

    @abstractmethod
    def find_pending(self) -> List[GateTask]:
        """Find all tasks in waiting_followups state.

        Returns:
            List of GateTask objects ordered by modified_at (oldest first).
        """
        pass

    @abstractmethod
    def get_gate_status(self, task_id: str) -> GateState:
        """Get the gate status for a specific task.

        Args:
            task_id: The task identifier

        Returns:
            GateState enum value (NONE if task not found)
        """
        pass

    @abstractmethod
    def set_gate_status(self, task_id: str, status: GateState) -> None:
        """Set the gate status for a specific task.

        Args:
            task_id: The task identifier
            status: New GateState value
        """
        pass

    @abstractmethod
    def invalidate_cache(self) -> None:
        """Invalidate any cached data. Called when gate state changes."""
        pass


# =============================================================================
# Filesystem Implementation (Fallback)
# =============================================================================

class FilesystemGateRepository(GateRepository):
    """Filesystem-based gate repository using glob scan.

    This is the fallback implementation when Neo4j is unavailable.
    It scans all agent task directories for *.pending-gate.md files.

    Performance: O(n) where n = total files across all agents.
    """

    def __init__(self):
        self._agents_dir = AGENTS_DIR

    def find_pending(self) -> List[GateTask]:
        """Scan filesystem for *.pending-gate.md files."""
        pending_gates = []

        for agent_dir in self._agents_dir.iterdir():
            if not agent_dir.is_dir() or agent_dir.name.startswith('.'):
                continue

            # Skip if not a valid agent directory
            if agent_dir.name not in VALID_AGENTS:
                continue

            tasks_dir = agent_dir / "tasks"
            if not tasks_dir.exists():
                continue

            for task_file in tasks_dir.glob("*.pending-gate.md"):
                task_id = self._extract_task_id(task_file)
                if task_id:
                    # Get file modification time
                    mtime = datetime.fromtimestamp(task_file.stat().st_mtime)

                    pending_gates.append(GateTask(
                        task_id=task_id,
                        agent=agent_dir.name,
                        file_path=task_file,
                        modified_at=mtime
                    ))

        # Sort by modification time (oldest first)
        pending_gates.sort(key=lambda g: g.modified_at)

        return pending_gates

    def get_gate_status(self, task_id: str) -> GateState:
        """Determine gate status from filesystem filename."""
        task_file = self._find_task_file(task_id)

        if not task_file:
            return GateState.NONE

        filename = task_file.name.lower()

        if 'pending-gate' in filename:
            return GateState.WAITING_FOLLOWUPS
        elif 'gate-passed' in filename and '.done.' in filename:
            return GateState.PASSED
        elif 'gate-blocked' in filename:
            return GateState.BLOCKED
        elif 'failed' in filename:
            return GateState.FAILED
        else:
            return GateState.NONE

    def set_gate_status(self, task_id: str, status: GateState) -> None:
        """Filesystem repository doesn't write state (read-only).

        The completion-gate-resolver.py handles file renaming.
        """
        pass

    def invalidate_cache(self) -> None:
        """Filesystem repository has no cache to invalidate."""
        pass

    def _extract_task_id(self, gate_file: Path) -> Optional[str]:
        """Extract task ID from a gate file."""
        try:
            with open(gate_file, 'r') as f:
                content = f.read(2000)

            # Extract from frontmatter
            match = re.search(r'task_id:\s*(\S+)', content)
            if match:
                return match.group(1)

            # Extract from filename as fallback
            # Format: priority-taskid.pending-gate.md
            stem = gate_file.stem.replace('.pending-gate', '')
            parts = stem.split('-', 1)
            if len(parts) > 1:
                return parts[1]

            return None
        except Exception:
            return None

    def _find_task_file(self, task_id: str) -> Optional[Path]:
        """Find a task file by task ID across all agent directories."""
        for agent_dir in self._agents_dir.iterdir():
            if not agent_dir.is_dir() or agent_dir.name.startswith('.'):
                continue

            if agent_dir.name not in VALID_AGENTS:
                continue

            tasks_dir = agent_dir / "tasks"
            if not tasks_dir.exists():
                continue

            # Search for any file matching the task_id
            for task_file in tasks_dir.glob(f"*{task_id}*.md"):
                return task_file

        return None


# =============================================================================
# Neo4j Implementation (Primary)
# =============================================================================

class Neo4jGateRepository(GateRepository):
    """Neo4j-based gate repository using indexed query.

    This is the PRIMARY implementation for production use.
    It uses the gate_status index on Task nodes for fast lookups.

    Performance: O(log n) indexed query, typically < 100ms.

    Requirements:
    - Neo4j available at NEO4J_URI
    - gate_status index exists on Task nodes
    - Task nodes have gate_status property
    """

    # Cypher query to find pending gates
    FIND_PENDING_QUERY = """
        MATCH (t:Task)
        WHERE t.gate_status = 'waiting_followups'
          AND t.task_id IS NOT NULL
          AND t.agent IS NOT NULL
        RETURN
            t.task_id as task_id,
            t.agent as agent,
            t.title as title,
            t.modified as modified,
            t.status as status
        ORDER BY coalesce(t.modified, t.created)
        LIMIT 1000
    """

    GET_STATUS_QUERY = """
        MATCH (t:Task {task_id: $task_id})
        RETURN coalesce(t.gate_status, 'none') as gate_status
    """

    SET_STATUS_QUERY = """
        MATCH (t:Task {task_id: $task_id})
        SET t.gate_status = $status,
            t.gate_updated = datetime()
    """

    GET_PRIORITY_QUERY = """
        MATCH (t:Task {task_id: $task_id})
        RETURN t.priority as priority
    """

    SYNC_FROM_FS_QUERY = """
        MERGE (t:Task {task_id: $task_id})
        ON CREATE SET
            t.agent = $agent,
            t.title = $title,
            t.created = datetime(),
            t.synced_from_fs = true
        SET t.gate_status = $status,
            t.modified = datetime()
    """

    def __init__(self):
        """Initialize Neo4j repository with lazy connection."""
        self._driver = None
        self._neo4j_available = None  # Cached availability check

    @property
    def driver(self):
        """Lazy-load Neo4j driver."""
        if self._driver is None:
            try:
                from neo4j_task_tracker import get_driver
                self._driver = get_driver()
            except ImportError as e:
                raise Neo4jUnavailableError(f"neo4j_task_tracker not available: {e}")
        return self._driver

    def find_pending(self) -> List[GateTask]:
        """Find pending gates using indexed Neo4j query."""
        try:
            with self.driver.session() as session:
                result = session.run(self.FIND_PENDING_QUERY)

                pending_gates = []
                for record in result:
                    task_id = record['task_id']
                    agent = record['agent']

                    # Build filesystem path for the gate file
                    gate_file = self._get_gate_file_path(task_id, agent)

                    pending_gates.append(GateTask(
                        task_id=task_id,
                        agent=agent,
                        file_path=gate_file,
                        title=record.get('title'),
                        gate_status=GateState.WAITING_FOLLOWUPS,
                        modified_at=self._parse_datetime(record.get('modified'))
                    ))

                return pending_gates

        except Exception as e:
            # Convert to Neo4jUnavailableError for fallback handling
            raise Neo4jUnavailableError(f"Neo4j query failed: {e}")

    def get_gate_status(self, task_id: str) -> GateState:
        """Get gate status from Neo4j."""
        try:
            with self.driver.session() as session:
                result = session.run(self.GET_STATUS_QUERY, task_id=task_id)
                record = result.single()

                if not record:
                    return GateState.NONE

                status_str = record['gate_status']
                try:
                    return GateState(status_str)
                except ValueError:
                    # Unknown status string - return NONE
                    return GateState.NONE

        except Exception:
            # On error, return NONE (no gate)
            return GateState.NONE

    def set_gate_status(self, task_id: str, status: GateState) -> None:
        """Set gate status in Neo4j."""
        try:
            with self.driver.session() as session:
                session.run(self.SET_STATUS_QUERY,
                           task_id=task_id,
                           status=status.value)
        except Exception as e:
            # Log but don't raise - gate operations are best-effort
            print(f"[WARN] Failed to set gate_status for {task_id}: {e}")

    def sync_gate_from_fs(self, gate_file: Path, task_id: str, agent: str) -> None:
        """Sync a gate from filesystem into Neo4j (creates/updates Task node).

        Called when a gate exists on filesystem but not in Neo4j.
        """
        try:
            # Extract title from file
            title = self._extract_title(gate_file)

            with self.driver.session() as session:
                session.run(self.SYNC_FROM_FS_QUERY,
                           task_id=task_id,
                           agent=agent,
                           title=title,
                           status=GateState.WAITING_FOLLOWUPS.value)
        except Exception as e:
            print(f"[WARN] Failed to sync gate {task_id} to Neo4j: {e}")

    def invalidate_cache(self) -> None:
        """Neo4j repository has no in-memory cache."""
        pass

    def _get_gate_file_path(self, task_id: str, agent: str) -> Path:
        """Find the actual filesystem path for a gate file.

        First queries Neo4j for task priority, then constructs path.
        Falls back to filesystem glob if Neo4j query fails.

        Supports all priority prefixes: critical-, high-, normal-, low-.
        """
        tasks_dir = AGENTS_DIR / agent / "tasks"

        # First, try filesystem glob as authoritative source
        # (file may exist before Neo4j sync)
        pattern = str(tasks_dir / f"*{task_id}*.pending-gate.md")
        matches = glob.glob(pattern)
        if matches:
            return Path(matches[0])

        # No file found on disk - construct path using Neo4j priority
        priority = self._get_task_priority(task_id)
        if priority:
            return tasks_dir / f"{priority}-{task_id}.pending-gate.md"

        # Final fallback: default to "high" prefix for backward compatibility
        return tasks_dir / f"high-{task_id}.pending-gate.md"

    def _get_task_priority(self, task_id: str) -> Optional[str]:
        """Query Neo4j for task priority.

        Returns:
            Priority string (critical, high, normal, low) or None if not found.
        """
        try:
            with self.driver.session() as session:
                result = session.run(self.GET_PRIORITY_QUERY, task_id=task_id)
                record = result.single()
                if record and record.get('priority'):
                    return record['priority']
                return None
        except Exception:
            # Neo4j unavailable or query failed
            return None

    def _extract_title(self, gate_file: Path) -> str:
        """Extract title from gate file."""
        try:
            with open(gate_file, 'r') as f:
                content = f.read(2000)
            match = re.search(r'^#\s*Task:\s*(.+)', content, re.MULTILINE)
            return match.group(1).strip() if match else task_id_from_file(gate_file)
        except Exception:
            return task_id_from_file(gate_file)

    def _parse_datetime(self, dt_any) -> datetime:
        """Parse Neo4j datetime to Python datetime."""
        if dt_any is None:
            return datetime.now()
        if isinstance(dt_any, datetime):
            return dt_any
        # Handle Neo4j DateTime object
        if hasattr(dt_any, 'iso_format'):
            return datetime.fromisoformat(dt_any.iso_format())
        return datetime.now()


def task_id_from_file(gate_file: Path) -> str:
    """Extract task ID from gate file filename as fallback title."""
    stem = gate_file.stem.replace('.pending-gate', '')
    parts = stem.split('-', 1)
    return parts[1] if len(parts) > 1 else stem


# =============================================================================
# Cached Implementation (Decorator)
# =============================================================================

class CachedGateRepository(GateRepository):
    """Caching decorator for any GateRepository implementation.

    Wraps a base repository and adds:
    - 60-second TTL cache for find_pending() results
    - Cache invalidation on gate state changes
    - Thread-safe cache updates

    Usage:
        base_repo = Neo4jGateRepository()
        cached_repo = CachedGateRepository(base_repo, ttl_seconds=60)
    """

    def __init__(self, base_repository: GateRepository, ttl_seconds: int = 60):
        """Initialize cached repository.

        Args:
            base_repository: The underlying repository to cache
            ttl_seconds: Cache time-to-live in seconds (default: 60)
        """
        self._base = base_repository
        self._ttl = ttl_seconds
        self._cache: Dict[str, Any] = {
            "data": None,
            "timestamp": 0
        }
        self._lock = threading.Lock()

    def find_pending(self) -> List[GateTask]:
        """Find pending gates with caching."""
        now = time.time()

        # Thread-safe cache check
        with self._lock:
            if (self._cache["data"] is not None and
                (now - self._cache["timestamp"]) < self._ttl):
                # Cache hit - return copy of cached data
                return list(self._cache["data"])

        # Cache miss - query base repository (outside lock)
        try:
            result = self._base.find_pending()
        except Neo4jUnavailableError:
            # Neo4j unavailable - fall back to filesystem
            print("[WARN] Neo4j unavailable, using filesystem fallback")
            fs_repo = FilesystemGateRepository()
            result = fs_repo.find_pending()

        # Thread-safe cache update
        with self._lock:
            self._cache["data"] = result
            self._cache["timestamp"] = now

        return list(result)

    def get_gate_status(self, task_id: str) -> GateState:
        """Get gate status - delegates to base (no cache for single task)."""
        return self._base.get_gate_status(task_id)

    def set_gate_status(self, task_id: str, status: GateState) -> None:
        """Set gate status and invalidate cache."""
        self._base.set_gate_status(task_id, status)
        self.invalidate_cache()

    def invalidate_cache(self) -> None:
        """Invalidate the cache immediately."""
        self._cache["data"] = None
        self._cache["timestamp"] = 0


# =============================================================================
# Factory Function
# =============================================================================

def get_gate_repository(use_cache: bool = True, ttl_seconds: int = 60) -> GateRepository:
    """Get the appropriate gate repository implementation.

    Factory function that:
    1. Tries Neo4jGateRepository (primary)
    2. Falls back to FilesystemGateRepository if Neo4j unavailable
    3. Wraps in CachedGateRepository if use_cache=True

    Args:
        use_cache: Whether to use the caching layer (default: True)
        ttl_seconds: Cache TTL in seconds (default: 60)

    Returns:
        GateRepository instance ready for use
    """
    # Try Neo4j first
    try:
        neo4j_repo = Neo4jGateRepository()
        # Test connection with a simple query
        with neo4j_repo.driver.session() as session:
            session.run("RETURN 1 as test").single()

        # Neo4j available - use it
        base_repo = neo4j_repo

    except Exception as e:
        # Neo4j unavailable - use filesystem fallback
        print(f"[INFO] Neo4j unavailable ({e}), using filesystem gate repository")
        base_repo = FilesystemGateRepository()

    # Wrap in cache if requested
    if use_cache:
        return CachedGateRepository(base_repo, ttl_seconds=ttl_seconds)

    return base_repo


# =============================================================================
# Compatibility Function for Legacy Code
# =============================================================================

def find_pending_gates() -> List[Path]:
    """Legacy compatibility function - returns list of Path objects.

    This function maintains backward compatibility with code that expects
    the old find_pending_gates() API. New code should use get_gate_repository()
    and work with GateTask objects.

    Returns:
        List of Path objects to pending gate files
    """
    repo = get_gate_repository()
    gates = repo.find_pending()
    return [gate.file_path for gate in gates]


# =============================================================================
# CLI for Testing
# =============================================================================

def main():
    """CLI for testing gate repository operations."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Gate Repository - Query and manage pending gates"
    )
    parser.add_argument("--pending", action="store_true",
                        help="List all pending gates")
    parser.add_argument("--status", metavar="TASK_ID",
                        help="Get gate status for a task")
    parser.add_argument("--no-cache", action="store_true",
                        help="Disable cache for this query")
    parser.add_argument("--bench", action="store_true",
                        help="Run performance benchmark (Neo4j vs filesystem)")
    parser.add_argument("--sync-neo4j", action="store_true",
                        help="Sync filesystem gates to Neo4j")

    args = parser.parse_args()

    repo = get_gate_repository(use_cache=not args.no_cache)

    if args.pending:
        gates = repo.find_pending()
        print(f"=== Pending Gates ({len(gates)}) ===\n")
        for gate in gates:
            age = (datetime.now() - gate.modified_at).total_seconds() / 60
            print(f"  {gate.task_id}")
            print(f"    Agent: {gate.agent}")
            print(f"    File: {gate.file_path.name}")
            print(f"    Age: {age:.1f} minutes")
            if gate.title:
                print(f"    Title: {gate.title[:60]}")
            print()

    elif args.status:
        status = repo.get_gate_status(args.status)
        print(f"Gate status for {args.status}: {status.value}")

    elif args.bench:
        import statistics

        print("=== Performance Benchmark ===\n")

        # Benchmark Neo4j query
        try:
            neo4j_repo = Neo4jGateRepository()
            neo4j_times = []
            for i in range(10):
                start = time.time()
                neo4j_repo.find_pending()
                neo4j_times.append((time.time() - start) * 1000)

            print(f"Neo4j (10 runs):")
            print(f"  Avg: {statistics.mean(neo4j_times):.2f}ms")
            print(f"  Min: {min(neo4j_times):.2f}ms")
            print(f"  Max: {max(neo4j_times):.2f}ms")
        except Exception as e:
            print(f"Neo4j benchmark failed: {e}")

        # Benchmark filesystem scan
        fs_repo = FilesystemGateRepository()
        fs_times = []
        for i in range(10):
            start = time.time()
            fs_repo.find_pending()
            fs_times.append((time.time() - start) * 1000)

        print(f"\nFilesystem (10 runs):")
        print(f"  Avg: {statistics.mean(fs_times):.2f}ms")
        print(f"  Min: {min(fs_times):.2f}ms")
        print(f"  Max: {max(fs_times):.2f}ms")

        # Calculate speedup
        if neo4j_times:
            speedup = statistics.mean(fs_times) / statistics.mean(neo4j_times)
            print(f"\nSpeedup: {speedup:.1f}x")

    elif args.sync_neo4j:
        # Sync filesystem gates to Neo4j
        fs_repo = FilesystemGateRepository()
        neo4j_repo = Neo4jGateRepository()

        gates = fs_repo.find_pending()
        print(f"Syncing {len(gates)} gates to Neo4j...")

        synced = 0
        for gate in gates:
            neo4j_repo.sync_gate_from_fs(gate.file_path, gate.task_id, gate.agent)
            synced += 1
            print(f"  Synced: {gate.task_id}")

        print(f"\nSynced {synced} gates to Neo4j")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
