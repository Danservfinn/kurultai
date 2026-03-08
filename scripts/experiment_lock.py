#!/usr/bin/env python3
"""
Experiment Lock - Concurrent experiment coordination for Kurultai

Prevents multiple agents from modifying the same files simultaneously.
Uses file-based locks with metadata for tracking.

Usage:
    from experiment_lock import ExperimentLock

    lock = ExperimentLock('temujin', ['scripts/router_scorer.py'])
    if lock.acquire('exp-20260308-001'):
        try:
            # Run experiment...
            pass
        finally:
            lock.release()
    else:
        print("Files are locked by another experiment")
"""

import os
import sys
import json
import time
import fcntl
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


LOCK_DIR = Path("/tmp/kurultai-experiment-locks")


@dataclass
class LockInfo:
    """Information about an active lock."""
    experiment_id: str
    agent: str
    target_paths: list[str]
    acquired_at: datetime
    pid: int

    def to_dict(self) -> dict:
        return {
            "experiment_id": self.experiment_id,
            "agent": self.agent,
            "target_paths": self.target_paths,
            "acquired_at": self.acquired_at.isoformat(),
            "pid": self.pid,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LockInfo":
        return cls(
            experiment_id=data["experiment_id"],
            agent=data["agent"],
            target_paths=data["target_paths"],
            acquired_at=datetime.fromisoformat(data["acquired_at"]),
            pid=data["pid"],
        )


class ExperimentLock:
    """
    File-based lock for coordinating concurrent experiments.

    Features:
    - Path-level locking (one experiment per path)
    - Agent-level lock files
    - Stale lock detection (process died without releasing)
    - Atomic acquire/release operations
    """

    def __init__(self, agent: str, target_paths: list[str]):
        """
        Initialize lock for an agent and target paths.

        Args:
            agent: Agent name (temujin, ogedei, etc.)
            target_paths: List of file/directory paths to lock
        """
        self.agent = agent
        self.target_paths = [str(p) for p in target_paths]
        self.lock_file = LOCK_DIR / f"{agent}.lock"
        self._lock_handle: Optional[int] = None
        self._experiment_id: Optional[str] = None

        # Ensure lock directory exists
        LOCK_DIR.mkdir(parents=True, exist_ok=True)

    def _normalize_path(self, path: str) -> str:
        """Normalize path for consistent comparison."""
        return os.path.normpath(os.path.expanduser(path))

    def _read_lock_info(self, lock_path: Path) -> Optional[LockInfo]:
        """Read lock info from file."""
        if not lock_path.exists():
            return None

        try:
            with open(lock_path) as f:
                data = json.load(f)
            return LockInfo.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            return None

    def _write_lock_info(self, lock_path: Path, info: LockInfo) -> bool:
        """Write lock info to file atomically."""
        try:
            # Write to temp file, then rename for atomicity
            temp_path = lock_path.with_suffix(".tmp")
            with open(temp_path, "w") as f:
                json.dump(info.to_dict(), f, indent=2)
            temp_path.rename(lock_path)
            return True
        except (IOError, OSError) as e:
            print(f"Warning: Could not write lock file: {e}", file=sys.stderr)
            return False

    def _is_process_alive(self, pid: int) -> bool:
        """Check if a process is still running."""
        try:
            os.kill(pid, 0)  # Signal 0 = check if process exists
            return True
        except OSError:
            return False

    def _path_locked_by_other(self, path: str, exclude_experiment: Optional[str] = None) -> Optional[LockInfo]:
        """
        Check if a path is locked by another experiment.

        Args:
            path: Path to check
            exclude_experiment: Experiment ID to exclude from check

        Returns:
            LockInfo if locked by another, None otherwise
        """
        normalized = self._normalize_path(path)

        # Check all lock files in the directory
        for lock_file in LOCK_DIR.glob("*.lock"):
            info = self._read_lock_info(lock_file)
            if not info:
                continue

            # Skip our own experiment
            if exclude_experiment and info.experiment_id == exclude_experiment:
                continue

            # Check if process is still alive (stale lock detection)
            if not self._is_process_alive(info.pid):
                # Clean up stale lock
                try:
                    lock_file.unlink()
                except OSError:
                    pass
                continue

            # Check if any locked path conflicts
            for locked_path in info.target_paths:
                locked_normalized = self._normalize_path(locked_path)

                # Check for exact match or parent directory match
                if normalized == locked_normalized:
                    return info
                if normalized.startswith(locked_normalized + "/"):
                    return info
                if locked_normalized.startswith(normalized + "/"):
                    return info

        return None

    def acquire(self, experiment_id: str, timeout_seconds: int = 0) -> bool:
        """
        Acquire lock on target paths.

        Args:
            experiment_id: Unique experiment identifier
            timeout_seconds: Max time to wait for lock (0 = no wait)

        Returns:
            True if lock acquired, False if any path is locked
        """
        start_time = time.time()

        while True:
            # Check if any target path is already locked
            for path in self.target_paths:
                existing_lock = self._path_locked_by_other(path, experiment_id)
                if existing_lock:
                    if timeout_seconds == 0:
                        return False

                    elapsed = time.time() - start_time
                    if elapsed >= timeout_seconds:
                        return False

                    # Wait and retry
                    time.sleep(0.5)
                    continue

            # All paths available - acquire lock
            lock_info = LockInfo(
                experiment_id=experiment_id,
                agent=self.agent,
                target_paths=self.target_paths,
                acquired_at=datetime.now(),
                pid=os.getpid(),
            )

            if self._write_lock_info(self.lock_file, lock_info):
                self._experiment_id = experiment_id
                return True

            # Write failed - retry if timeout allows
            if timeout_seconds == 0:
                return False

            elapsed = time.time() - start_time
            if elapsed >= timeout_seconds:
                return False

            time.sleep(0.5)

    def release(self) -> bool:
        """
        Release the lock.

        Returns:
            True if lock released, False if not held
        """
        if not self.lock_file.exists():
            return True  # Already released

        # Verify we own the lock
        info = self._read_lock_info(self.lock_file)
        if not info:
            return True

        if info.pid != os.getpid():
            return False  # Don't own the lock

        try:
            self.lock_file.unlink()
            self._experiment_id = None
            return True
        except OSError as e:
            print(f"Warning: Could not release lock: {e}", file=sys.stderr)
            return False

    def is_locked(self, path: str) -> bool:
        """
        Check if a specific path is locked.

        Args:
            path: Path to check

        Returns:
            True if path is locked by any experiment
        """
        return self._path_locked_by_other(path) is not None

    def get_lock_info(self, path: str) -> Optional[LockInfo]:
        """
        Get information about who holds a lock on a path.

        Args:
            path: Path to check

        Returns:
            LockInfo if locked, None otherwise
        """
        return self._path_locked_by_other(path)

    def __enter__(self):
        """Context manager entry - requires acquire() to be called first."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - always releases lock."""
        self.release()
        return False


def list_all_locks() -> list[LockInfo]:
    """
    List all active experiment locks.

    Returns:
        List of LockInfo objects for all active locks
    """
    locks = []

    if not LOCK_DIR.exists():
        return locks

    for lock_file in LOCK_DIR.glob("*.lock"):
        info = LockInfo.__new__(LockInfo)
        info = None

        try:
            with open(lock_file) as f:
                data = json.load(f)
            info = LockInfo.from_dict(data)

            # Check if process is alive
            if not os.path.exists(f"/proc/{info.pid}"):
                # Stale lock - clean up
                lock_file.unlink()
                continue

            locks.append(info)
        except (json.JSONDecodeError, KeyError, OSError):
            continue

    return locks


def clear_stale_locks() -> int:
    """
    Clear all stale locks from dead processes.

    Returns:
        Number of stale locks cleared
    """
    cleared = 0

    if not LOCK_DIR.exists():
        return 0

    for lock_file in LOCK_DIR.glob("*.lock"):
        try:
            with open(lock_file) as f:
                data = json.load(f)
            pid = data.get("pid")

            # Check if process exists
            try:
                os.kill(pid, 0)
            except OSError:
                # Process dead - remove lock
                lock_file.unlink()
                cleared += 1
        except (json.JSONDecodeError, KeyError, OSError):
            continue

    return cleared


def main():
    """CLI interface for experiment lock management."""
    import argparse

    parser = argparse.ArgumentParser(description="Experiment Lock CLI")
    parser.add_argument("command", choices=["list", "clear", "check", "test"])
    parser.add_argument("--agent", default="temujin", help="Agent name")
    parser.add_argument("--path", help="Path to check")
    parser.add_argument("--files", nargs="+", help="Files to lock")
    parser.add_argument("--experiment-id", default="test-exp", help="Experiment ID")

    args = parser.parse_args()

    if args.command == "list":
        locks = list_all_locks()
        if not locks:
            print("No active locks")
        for lock in locks:
            print(f"{lock.experiment_id}\t{lock.agent}\tPID:{lock.pid}")
            for path in lock.target_paths:
                print(f"  - {path}")

    elif args.command == "clear":
        cleared = clear_stale_locks()
        print(f"Cleared {cleared} stale locks")

    elif args.command == "check":
        if not args.path:
            print("Error: --path required for check", file=sys.stderr)
            sys.exit(1)
        lock = ExperimentLock(args.agent, [args.path])
        info = lock.get_lock_info(args.path)
        if info:
            print(f"Locked by: {info.experiment_id} ({info.agent})")
        else:
            print("Not locked")

    elif args.command == "test":
        # Test the lock system
        files = args.files or ["scripts/test.py"]

        print(f"Creating first lock for {args.agent}...")
        lock1 = ExperimentLock(args.agent, files)
        success1 = lock1.acquire(args.experiment_id)
        print(f"Lock 1 acquired: {success1}")

        print(f"Creating second lock for {args.agent}...")
        lock2 = ExperimentLock(args.agent, files)
        success2 = lock2.acquire("exp-002")
        print(f"Lock 2 acquired (should fail): {success2}")

        print("Releasing lock 1...")
        lock1.release()

        print("Retrying lock 2...")
        success2_retry = lock2.acquire("exp-002")
        print(f"Lock 2 acquired (should succeed): {success2_retry}")

        lock2.release()
        print("Test complete - both locks released")


if __name__ == "__main__":
    main()
