#!/usr/bin/env python3
"""File-backed rate limiter for Hermes autonomous fixes.

Caps:
  - Per scope ('content' | 'code'): 3 fixes per rolling hour
  - Total: 10 fixes per rolling day

State file: ~/.openclaw/state/hermes_rate_limits.json
  { "content": [ts_float, ts_float, ...], "code": [ts_float, ...] }

Uses json_state.locked_json_update for atomic read-modify-write.

Usage:
    from hermes_rate_limit import allowed, record
    ok, reason = allowed('content')
    if not ok:
        return {'outcome': 'RATE_LIMITED', 'reason': reason}
    # ... apply the fix ...
    record('content')
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from json_state import locked_json_update  # type: ignore

STATE_FILE = Path.home() / ".openclaw" / "state" / "hermes_rate_limits.json"
PER_SCOPE_HOURLY_MAX = 3
DAILY_TOTAL_MAX = 10
_VALID_SCOPES = ("content", "code", "task_action")


def _now() -> float:
    return datetime.now(timezone.utc).timestamp()


def _prune(ts_list, cutoff_floor: float):
    """Keep only timestamps newer than cutoff_floor."""
    return [t for t in ts_list if t >= cutoff_floor]


def allowed(scope: str) -> tuple[bool, str]:
    """Return (allowed, reason). Does NOT record — caller calls record() on success."""
    if scope not in _VALID_SCOPES:
        return False, f"unknown scope: {scope}"

    now = _now()
    hour_cutoff = now - 3600
    day_cutoff = now - 86400

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with locked_json_update(str(STATE_FILE)) as state:
        content = _prune(state.get("content", []), day_cutoff)
        code = _prune(state.get("code", []), day_cutoff)
        task_action = _prune(state.get("task_action", []), day_cutoff)
        state["content"] = content
        state["code"] = code
        state["task_action"] = task_action
        total_today = len(content) + len(code) + len(task_action)
        if total_today >= DAILY_TOTAL_MAX:
            return False, f"daily cap: {total_today}/{DAILY_TOTAL_MAX}"

        scope_ts = state.get(scope, [])
        scope_hour_count = sum(1 for t in scope_ts if t >= hour_cutoff)
        if scope_hour_count >= PER_SCOPE_HOURLY_MAX:
            return False, (
                f"scope {scope} hourly cap: "
                f"{scope_hour_count}/{PER_SCOPE_HOURLY_MAX}"
            )
    return True, ""


def record(scope: str) -> None:
    """Record a fix in the rate-limit state.

    Prefer consume_slot() for new code — it's race-free. This function
    remains for backward compatibility with callers that need to record
    a slot AFTER verifying the fix landed (e.g., rollback-to-un-record
    is not a pattern we support, so record-after is safer only when the
    caller is single-threaded).
    """
    if scope not in _VALID_SCOPES:
        raise ValueError(f"unknown scope: {scope}")

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with locked_json_update(str(STATE_FILE)) as state:
        state.setdefault(scope, []).append(_now())


def consume_slot(scope: str) -> tuple[bool, str]:
    """Atomically check-and-record a rate-limit slot.

    Race-free replacement for the allowed() + record() pattern. Two
    concurrent callers cannot both see 'allowed' at cap-minus-one and
    both proceed, because the cap check and the record happen inside
    the same locked_json_update block.

    Returns (ok, reason). On (True, ''), the slot has been consumed and
    the caller should proceed with their fix. On (False, reason), no
    slot was consumed — caller must NOT apply a fix and should log the
    reason / move the job to the rate-limited bucket.

    Failures leave state unchanged (transactional semantics via
    locked_json_update's release-on-exception).
    """
    if scope not in _VALID_SCOPES:
        return False, f"unknown scope: {scope}"

    now = _now()
    hour_cutoff = now - 3600
    day_cutoff = now - 86400

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with locked_json_update(str(STATE_FILE)) as state:
        # Prune stale entries
        content = _prune(state.get("content", []), day_cutoff)
        code = _prune(state.get("code", []), day_cutoff)
        state["content"] = content
        state["code"] = code

        # Check caps
        total_today = len(content) + len(code)
        if total_today >= DAILY_TOTAL_MAX:
            return False, f"daily cap: {total_today}/{DAILY_TOTAL_MAX}"

        scope_ts = state.get(scope, [])
        scope_hour_count = sum(1 for t in scope_ts if t >= hour_cutoff)
        if scope_hour_count >= PER_SCOPE_HOURLY_MAX:
            return False, (
                f"scope {scope} hourly cap: "
                f"{scope_hour_count}/{PER_SCOPE_HOURLY_MAX}"
            )

        # Atomically record within the same lock
        state.setdefault(scope, []).append(now)

    return True, ""


def current_counts() -> dict:
    """Return current hourly/daily counts for diagnostics."""
    now = _now()
    hour_cutoff = now - 3600
    day_cutoff = now - 86400
    if not STATE_FILE.exists():
        return {"content_hour": 0, "code_hour": 0,
                "task_action_hour": 0, "total_day": 0}
    with locked_json_update(str(STATE_FILE)) as state:
        content = _prune(state.get("content", []), day_cutoff)
        code = _prune(state.get("code", []), day_cutoff)
        task_action = _prune(state.get("task_action", []), day_cutoff)
        state["content"] = content
        state["code"] = code
        state["task_action"] = task_action
        return {
            "content_hour": sum(1 for t in content if t >= hour_cutoff),
            "code_hour": sum(1 for t in code if t >= hour_cutoff),
            "task_action_hour": sum(1 for t in task_action if t >= hour_cutoff),
            "total_day": len(content) + len(code) + len(task_action),
            "caps": {
                "per_scope_hour": PER_SCOPE_HOURLY_MAX,
                "daily_total": DAILY_TOTAL_MAX,
            },
        }


if __name__ == "__main__":
    import json
    print(json.dumps(current_counts(), indent=2))
