#!/usr/bin/env python3
"""Hermes circuit breaker.

Trips on:
  - 2 events of type 'apply_failed' within 30 min
  - 3 events of type 'rollback' within 60 min
  - 1 event of type 'denylist_violation' at apply time (indicates bug or attack)

On trip:
  - touches ~/.openclaw/flags/hermes-autonomous-disabled.flag
  - enqueues a Signal DM via hermes_notify.notify_circuit_breaker_tripped
  - writes trip_reason + tripped_at to state file

State file: ~/.openclaw/state/hermes_circuit_breaker.json
  {
    "events": [{"type": str, "ts": float, "detail": str}, ...],
    "tripped_at": iso_str | null,
    "trip_reason": str | null
  }

The rate limiter (hermes_rate_limit.py) handles smooth operation caps;
this circuit breaker handles emergency shutdown.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from json_state import locked_json_update  # type: ignore

STATE_FILE = Path.home() / ".openclaw" / "state" / "hermes_circuit_breaker.json"
DISABLE_FLAG = Path.home() / ".openclaw" / "flags" / "hermes-autonomous-disabled.flag"

_EVENT_WINDOW_SECS = 7200  # keep 2 h of events; prune older
_APPLY_FAIL_WINDOW = 1800  # 30 min
_APPLY_FAIL_THRESHOLD = 2
_ROLLBACK_WINDOW = 3600    # 60 min
_ROLLBACK_THRESHOLD = 3


def _now() -> float:
    return datetime.now(timezone.utc).timestamp()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def is_tripped() -> bool:
    """Return True if the circuit breaker has tripped (i.e., disable flag set
    by breaker)."""
    return DISABLE_FLAG.exists()


def record_event(event_type: str, detail: str = "") -> dict:
    """Record an event and trip the breaker if any threshold is exceeded.

    Returns the updated state dict (for diagnostics / logging).
    """
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    DISABLE_FLAG.parent.mkdir(parents=True, exist_ok=True)

    now = _now()

    with locked_json_update(str(STATE_FILE)) as state:
        events = state.setdefault("events", [])
        events.append({"type": event_type, "ts": now, "detail": detail})
        # Prune events older than 2 h
        events[:] = [e for e in events if now - e.get("ts", 0) < _EVENT_WINDOW_SECS]

        # Compute rolling-window counts
        last_apply_fail_window = [
            e for e in events
            if e["type"] == "apply_failed" and now - e["ts"] < _APPLY_FAIL_WINDOW
        ]
        last_rollback_window = [
            e for e in events
            if e["type"] == "rollback" and now - e["ts"] < _ROLLBACK_WINDOW
        ]
        last_denylist_window = [
            e for e in events
            if e["type"] == "denylist_violation"
            and now - e["ts"] < _APPLY_FAIL_WINDOW
        ]

        reasons: list[str] = []
        if len(last_apply_fail_window) >= _APPLY_FAIL_THRESHOLD:
            reasons.append(
                f"{len(last_apply_fail_window)} apply failures in "
                f"{_APPLY_FAIL_WINDOW // 60} min"
            )
        if len(last_rollback_window) >= _ROLLBACK_THRESHOLD:
            reasons.append(
                f"{len(last_rollback_window)} rollbacks in "
                f"{_ROLLBACK_WINDOW // 60} min"
            )
        if last_denylist_window:
            reasons.append("denylist violation at apply time")

        if reasons and not DISABLE_FLAG.exists():
            trip_reason = "; ".join(reasons)
            try:
                DISABLE_FLAG.touch()
            except OSError as e:
                # Best-effort — log and continue. Failing to touch the flag
                # does not un-trip the breaker.
                print(f"circuit_breaker: failed to touch disable flag: {e}",
                      file=sys.stderr)
            state["tripped_at"] = _now_iso()
            state["trip_reason"] = trip_reason
            # Best-effort notification
            try:
                from hermes_notify import notify_circuit_breaker_tripped
                notify_circuit_breaker_tripped(trip_reason)
            except Exception as e:
                print(f"circuit_breaker: notification enqueue failed: {e}",
                      file=sys.stderr)

        return dict(state)  # copy to return outside the lock


def reset(reason: str = "manual reset") -> None:
    """Remove the disable flag and clear event history. For operator use."""
    if DISABLE_FLAG.exists():
        try:
            DISABLE_FLAG.unlink()
        except OSError as e:
            raise RuntimeError(f"failed to remove disable flag: {e}") from e
    with locked_json_update(str(STATE_FILE)) as state:
        state["events"] = []
        state["tripped_at"] = None
        state["trip_reason"] = None
        state["last_reset_at"] = _now_iso()
        state["last_reset_reason"] = reason


def status() -> dict:
    """Return current breaker state for diagnostics."""
    if not STATE_FILE.exists():
        return {"tripped": is_tripped(), "events": []}
    with locked_json_update(str(STATE_FILE)) as state:
        return {
            "tripped": is_tripped(),
            "tripped_at": state.get("tripped_at"),
            "trip_reason": state.get("trip_reason"),
            "event_count": len(state.get("events", [])),
        }


if __name__ == "__main__":
    import json
    print(json.dumps(status(), indent=2))
