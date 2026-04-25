#!/usr/bin/env python3
"""
Ollama GPU Lock Manager — flock-based resource coordination for local LLM.

Prevents concurrent Ollama calls from tick, tock, and research scripts.
Uses kernel-managed flock(2) — no stale lock problem, auto-releases on death.

Priority levels:
  HIGH   — block up to 300s (watchdog alerts)
  NORMAL — block up to 90s, then skip (tick/tock routine)
  LOW    — non-blocking, skip immediately + yield near tick boundaries (research)

Usage (Python):
    from ollama_lock import OllamaLock, Priority, LockBusy

    try:
        with OllamaLock(Priority.LOW, label="mongke-research"):
            resp = requests.post("http://localhost:11434/api/chat", ...)
    except LockBusy:
        print("GPU busy, skipping")

Usage (CLI):
    python3 ollama_lock.py status
    python3 ollama_lock.py acquire NORMAL "tick-triage" -- curl ...
"""
from __future__ import annotations

import enum
import fcntl
import json
import os
import sys
import time

LOCK_FILE = "/tmp/ollama-gpu.lock"
SIDECAR_FILE = "/tmp/ollama-gpu.lock.pid"


class Priority(enum.IntEnum):
    HIGH = 3
    NORMAL = 2
    LOW = 1


# Timeout per priority level (seconds)
TIMEOUTS = {
    Priority.HIGH: 300,
    Priority.NORMAL: 90,
    Priority.LOW: 0,  # non-blocking
}


class LockBusy(Exception):
    """Raised when the GPU lock cannot be acquired (LOW priority or timeout)."""
    pass


def seconds_until_next_tick(interval=300):
    """Return seconds until the next 5-minute boundary."""
    return interval - (time.time() % interval)


def yield_for_tick(margin=15, wait=20):
    """If a tick is due within `margin` seconds, sleep `wait` seconds to let it run.

    Call this before each Ollama request in long-running LOW-priority jobs
    (e.g., mongke-research) to avoid blocking the watchdog tick.
    """
    remaining = seconds_until_next_tick()
    if remaining < margin:
        time.sleep(wait)


class OllamaLock:
    """Context manager for exclusive Ollama GPU access.

    Args:
        priority: HIGH, NORMAL, or LOW
        label: Human-readable identifier for diagnostics (e.g., "tick-triage")
        yield_for_ticks: If True (default for LOW), call yield_for_tick() on enter
    """

    def __init__(self, priority: Priority = Priority.NORMAL, label: str = "",
                 yield_for_ticks: bool = None):
        self.priority = priority
        self.label = label
        self.yield_for_ticks = yield_for_ticks if yield_for_ticks is not None else (priority == Priority.LOW)
        self._fd = None

    def __enter__(self):
        if self.yield_for_ticks:
            yield_for_tick()

        self._fd = open(LOCK_FILE, "w")
        timeout = TIMEOUTS[self.priority]

        if self.priority == Priority.LOW:
            # Non-blocking: try once, skip if busy
            try:
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (BlockingIOError, OSError):
                self._fd.close()
                self._fd = None
                raise LockBusy(f"GPU busy, skipping {self.label or 'LOW priority call'}")
        else:
            # Blocking with timeout via alarm signal
            acquired = self._acquire_with_timeout(timeout)
            if not acquired:
                self._fd.close()
                self._fd = None
                raise LockBusy(
                    f"GPU lock timeout after {timeout}s for {self.label or self.priority.name}"
                )

        self._write_sidecar()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._remove_sidecar()
        if self._fd:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            self._fd.close()
            self._fd = None
        return False  # don't suppress exceptions

    def _acquire_with_timeout(self, timeout: int) -> bool:
        """Attempt flock with timeout using non-blocking poll.

        Works in any thread (no SIGALRM dependency).
        """
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    return False
                time.sleep(0.5)

    def _write_sidecar(self):
        """Write diagnostic sidecar with holder info."""
        try:
            info = {
                "pid": os.getpid(),
                "priority": self.priority.name,
                "label": self.label,
                "acquired_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "epoch": int(time.time()),
            }
            with open(SIDECAR_FILE, "w") as f:
                json.dump(info, f)
        except OSError:
            pass  # non-critical

    def _remove_sidecar(self):
        """Remove diagnostic sidecar."""
        try:
            os.unlink(SIDECAR_FILE)
        except OSError:
            pass


def lock_status() -> dict:
    """Return current lock status for diagnostics."""
    result = {"locked": False, "holder": None}

    # Try non-blocking acquire to check if locked
    try:
        fd = open(LOCK_FILE, "w")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
            result["locked"] = False
        except (BlockingIOError, OSError):
            result["locked"] = True
        fd.close()
    except OSError:
        pass

    # Read sidecar if it exists
    try:
        with open(SIDECAR_FILE) as f:
            result["holder"] = json.load(f)
    except (OSError, json.JSONDecodeError):
        pass

    return result


# ============================================================
# CLI
# ============================================================

def _cli_status():
    status = lock_status()
    if status["locked"]:
        holder = status.get("holder", {})
        pid = holder.get("pid", "?")
        label = holder.get("label", "?")
        prio = holder.get("priority", "?")
        since = holder.get("acquired_at", "?")
        age = int(time.time()) - holder.get("epoch", int(time.time()))
        print(f"LOCKED by pid={pid} priority={prio} label={label} since={since} ({age}s ago)")
    else:
        print("UNLOCKED — GPU is available")


def _cli_acquire(args):
    """Acquire lock, run command, release. For bash integration."""
    if len(args) < 2:
        print("Usage: ollama_lock.py acquire PRIORITY label -- command...", file=sys.stderr)
        sys.exit(1)

    priority_name = args[0].upper()
    try:
        priority = Priority[priority_name]
    except KeyError:
        print(f"Unknown priority: {priority_name}. Use HIGH, NORMAL, or LOW", file=sys.stderr)
        sys.exit(1)

    label = args[1] if len(args) > 1 else ""

    # Find command after "--"
    cmd_args = []
    for i, a in enumerate(args):
        if a == "--":
            cmd_args = args[i + 1:]
            break

    if not cmd_args:
        print("No command specified after '--'", file=sys.stderr)
        sys.exit(1)

    try:
        with OllamaLock(priority, label=label):
            import subprocess
            result = subprocess.run(cmd_args, capture_output=False)
            sys.exit(result.returncode)
    except LockBusy:
        print(f"LOCK_BUSY: GPU unavailable for {priority_name}/{label}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: ollama_lock.py {status|acquire PRIORITY LABEL -- cmd...}")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "status":
        _cli_status()
    elif cmd == "acquire":
        _cli_acquire(sys.argv[2:])
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)
