#!/usr/bin/env python3
"""count_errors.py — Timestamp-accurate error counting for openclaw.log

Replaces the line-count-based `tail -N | grep` approach in watchdog-gather.sh
with actual time-window filtering using the JSON "time" field.

Usage:
    python3 count_errors.py [log_file]

Output (single line, space-separated):
    <errors_5m> <errors_1h> <fatal_5m>

Reads from end of file efficiently (last 2MB chunk) to avoid scanning
the entire log on every tick.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

LOG_FILE = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    "~/.openclaw/logs/openclaw.log"
)

# Noise patterns — messages matching any of these are not counted as real errors.
# Kept in sync with watchdog-gather.sh NOISE_FILTER.
NOISE_PATTERNS = [
    "gateway-like services",
    "Cleanup hint",
    "Recommendation: run",
    "isolate ports",
    "com.kurultai.task-watcher",
    "signal daemon exited",
    "Service unit not found",
    "Service not installed",
    "File logs:",
    "message failed: Unknown target",
    "ENOENT",           # covers ENOENT.*skills and similar
    "command not found: timeout",
    "(user, plist:",         # launchctl service listing logged at ERROR level
    "RPC probe:",            # gateway RPC retry chatter
    "RPC target:",           # gateway RPC target logging
    "is already in use",     # port conflict noise (e.g. Tolui gateway)
    "Gateway target:",       # gateway connection target logging
    "Source: cli",           # informational source line logged at ERROR
    "Multiple listeners",    # multi-gateway detection (informational)
    "gateway closed",        # abnormal closure during reconnect
    "Embedded agent failed", # fallback behavior, not actionable
    "Gateway agent failed",  # fallback to embedded, not actionable
    "Unknown agent id",      # agent not yet registered, transient
    "Config: /Users/",       # config path logging at ERROR level
    "Gateway already running",  # startup conflict (retry chatter)
    "Gateway failed to start",  # startup lock timeout (retries)
    "Gateway service appears",  # "appears loaded" informational
    "Tip: openclaw",            # help text logged at ERROR level
    "Or: launchctl",            # help text logged at ERROR level
    "- pid ",                   # process listing logged at ERROR level
    '"subsystem":"diagnostic"',  # diagnostic subsystem chatter
    '"subsystem":"gateway',      # gateway subsystem (e.g. signal channel)
]


def is_noise(message: str) -> bool:
    """Check if a log message matches known noise patterns."""
    for pattern in NOISE_PATTERNS:
        if pattern in message:
            return True
    return False


def count_errors(log_path: str) -> tuple[int, int, int]:
    """Count errors in the last 5 minutes and 1 hour from log timestamps.

    Returns: (errors_5m, errors_1h, fatal_5m)
    """
    if not os.path.isfile(log_path):
        return 0, 0, 0

    now = datetime.now(timezone.utc)
    cutoff_5m = now - timedelta(minutes=5)
    cutoff_1h = now - timedelta(hours=1)

    errors_5m = 0
    errors_1h = 0
    fatal_5m = 0

    # Read last 2MB from end of file — covers well over 1 hour of logs
    # even at high throughput (13MB covers many hours)
    file_size = os.path.getsize(log_path)
    chunk_size = min(file_size, 2 * 1024 * 1024)

    with open(log_path, "rb") as f:
        f.seek(file_size - chunk_size)
        raw = f.read().decode("utf-8", errors="replace")

    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue

        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue

        meta = entry.get("_meta", {})
        level = meta.get("logLevelName", "")

        # Only count ERROR, FATAL, CRASH
        if level not in ("ERROR", "FATAL", "CRASH"):
            continue

        # Extract message text — field "1" or "0" holds the log message
        msg = entry.get("1", "") or entry.get("0", "")
        if isinstance(msg, dict):
            msg = json.dumps(msg)
        msg = str(msg)

        if is_noise(msg):
            continue

        # Parse timestamp (ISO 8601 with timezone offset)
        ts_str = entry.get("time", "")
        if not ts_str:
            # Fallback: try _meta.date (UTC)
            ts_str = meta.get("date", "")
        if not ts_str:
            continue

        try:
            ts = datetime.fromisoformat(ts_str)
            # Normalize to UTC for comparison
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            else:
                ts = ts.astimezone(timezone.utc)
        except (ValueError, TypeError):
            continue

        # Skip entries older than 1 hour
        if ts < cutoff_1h:
            continue

        errors_1h += 1
        if ts >= cutoff_5m:
            errors_5m += 1
            if level in ("FATAL", "CRASH"):
                fatal_5m += 1

    return errors_5m, errors_1h, fatal_5m


if __name__ == "__main__":
    e5, e1h, f5 = count_errors(LOG_FILE)
    print(f"{e5} {e1h} {f5}")
