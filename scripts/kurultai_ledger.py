"""
kurultai_ledger.py — Centralized task ledger I/O with file locking.

All scripts that need to read/write the task-ledger.jsonl should import
from here instead of implementing their own I/O.
"""
from __future__ import annotations

import fcntl
import json
import sys
from datetime import datetime, timedelta, timezone
from kurultai_paths import TASK_LEDGER


def append_ledger(entry: dict) -> bool:
    """Append an event to the task ledger with exclusive file locking.
    Returns True on success, False on failure."""
    try:
        TASK_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with open(TASK_LEDGER, "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(json.dumps(entry) + "\n")
                f.flush()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        return True
    except Exception as e:
        print(f"[ledger] append failed: {e}", file=sys.stderr)
        return False


def read_ledger(hours: float | None = None) -> list:
    """Read events from the task ledger with shared locking.
    Optionally filter to events within the last N hours."""
    if not TASK_LEDGER.exists():
        return []
    cutoff = None
    if hours is not None:
        cutoff = datetime.now() - timedelta(hours=hours)
    events = []
    try:
        with open(TASK_LEDGER, "r", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                        if cutoff is not None:
                            ts_str = ev.get("ts", "")
                            if ts_str:
                                try:
                                    ev_time = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                                    if ev_time.tzinfo:
                                        if ev_time < cutoff:
                                            continue
                                    else:
                                        if ev_time < cutoff.replace(tzinfo=None):
                                            continue
                                except (ValueError, TypeError):
                                    pass  # Keep events with unparseable timestamps
                        events.append(ev)
                    except json.JSONDecodeError:
                        continue
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except Exception as e:
        print(f"[ledger] read failed: {e}", file=sys.stderr)
    return events
