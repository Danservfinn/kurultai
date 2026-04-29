#!/usr/bin/env python3
from __future__ import annotations

"""Stale-lock sweeper and heartbeat checker for the coordination store.

Run this on a cron (every minute) or call sweep() from any agent.
Marks expired locks and transfers locks whose owners have stopped heartbeating.
"""

import datetime as dt
import sys
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from coordination_store import CoordinationStore, DEFAULT_DB, utc_now

HEARTBEAT_TTL_SECONDS_BY_TIER: dict[str, int] = {
    "tier1": 30,
    "tier1_routine": 30,
    "tier_1_routine": 30,
    "tier2": 60,
    "tier2_shared_expertise": 60,
    "tier_2_shared_expertise": 60,
    "tier3": 120,
    "tier3_governance": 120,
    "tier_3_governance": 120,
    "transferable": 0,
}

DEFAULT_HEARTBEAT_TTL = 60


def _parse_iso(ts: str | None) -> dt.datetime | None:
    if not ts:
        return None
    try:
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def is_heartbeat_stale(lock: dict[str, Any], now: dt.datetime | None = None) -> bool:
    """Return True if the owner's heartbeat has not been updated within the tier TTL."""
    if now is None:
        now = dt.datetime.now(dt.timezone.utc)

    heartbeat_at = _parse_iso(lock.get("owner_heartbeat_at"))
    if heartbeat_at is None:
        created_at = _parse_iso(lock.get("created_at"))
        if created_at is None:
            return False
        heartbeat_at = created_at

    tier = lock.get("tier", "tier2")
    ttl = HEARTBEAT_TTL_SECONDS_BY_TIER.get(tier, DEFAULT_HEARTBEAT_TTL)
    age = (now - heartbeat_at).total_seconds()
    return age > ttl


def sweep(
    store: CoordinationStore | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Run one sweep cycle.

    1. Expire all active locks past expires_at.
    2. Mark transferable any locks whose owners have stale heartbeats.

    Returns a summary dict with counts.
    """
    if store is None:
        store = CoordinationStore(DEFAULT_DB)

    if now is None:
        now = dt.datetime.now(dt.timezone.utc)

    now_iso = now.isoformat().replace("+00:00", "Z")

    expired = store.sweep_expired(now_iso)
    transferred: list[dict[str, Any]] = []

    active_locks = store.get_active_locks_for_sweep()
    for lock in active_locks:
        if lock["status"] == "transferable":
            continue
        if is_heartbeat_stale(lock, now):
            result = store.mark_transferable(lock["lock_id"], reason="heartbeat_stale")
            transferred.append(result)

    return {
        "expired": len(expired),
        "transferred": len(transferred),
        "expired_lock_ids": [l["lock_id"] for l in expired],
        "transferred_lock_ids": [l["lock_id"] for l in transferred],
        "swept_at": now_iso,
    }


if __name__ == "__main__":
    import json
    result = sweep()
    print(json.dumps(result))
