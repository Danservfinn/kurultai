#!/usr/bin/env python3
from __future__ import annotations
"""
alert_deduplication.py — Alert deduplication with exponential backoff.

Extracted from task_intake.py for maintainability.

Usage:
    from alert_deduplication import should_suppress_alert, record_alert_created
"""

import os
import re
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kurultai_paths import LOGS_DIR


# =============================================================================
# Topic Key Extraction (shared with has_pending_task in task_intake)
# =============================================================================

def _extract_topic_keys(title):
    """Extract normalized topic keywords from a task title for fuzzy dedup."""
    # Lowercase, strip common verbs/prepositions
    noise = {'investigate', 'fix', 'debug', 'check', 'add', 'implement',
             'update', 'create', 'review', 'the', 'and', 'for', 'all',
             'across', 'from', 'with', 'when', 'not', 'is', 'are', 'to',
             'a', 'an', 'of', 'in', 'on', 'by', 'be', 'that', 'this'}
    words = re.sub(r'[^a-z0-9\s]', '', title.lower()).split()
    return frozenset(w for w in words if w not in noise and len(w) > 2)


# =============================================================================
# Alert Deduplication with Exponential Backoff
# =============================================================================

# Alert patterns that should trigger deduplication
ALERT_PATTERNS = [
    "system health alert",
    "health check",
    "watchdog alert",
    "stall alert",
    "queue imbalance",
    "throughput escalation",
    "routing audit",  # PRIORITY_FIX: deduplicate routing_audit tasks (2026-03-11)
]

# Deduplication state file
_ALERT_DEDUP_PATH = LOGS_DIR / "alert-dedup.json"

# Backoff intervals: 1st alert=0min, 2nd=10min, 3rd=30min, 4th+=60min
_BACKOFF_INTERVALS = [0, 5, 15, 30]  # Tightened: 0/5/15/30 (was 0/10/30/60)


def _get_alert_dedup_state() -> dict:
    """Load alert dedup state, returning empty dict if not exists."""
    if not _ALERT_DEDUP_PATH.exists():
        return {}
    try:
        with open(_ALERT_DEDUP_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_alert_dedup_state(state: dict):
    """Persist alert dedup state."""
    try:
        os.makedirs(os.path.dirname(_ALERT_DEDUP_PATH), exist_ok=True)
        with open(_ALERT_DEDUP_PATH, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass  # Never let dedup break task creation


def _cleanup_old_alerts(state: dict, cutoff_hours: int = 24):
    """Remove alert entries older than cutoff_hours."""
    cutoff = datetime.now() - timedelta(hours=cutoff_hours)
    cutoff_iso = cutoff.isoformat()
    to_delete = []
    for key, entry in state.items():
        if entry.get("last_seen", "") < cutoff_iso:
            to_delete.append(key)
    for key in to_delete:
        del state[key]
    return state


def _normalize_alert_key(agent: str, title: str, source: str) -> str:
    """Create a normalized key for alert deduplication.
    Groups similar alerts by agent + normalized source + topic keywords."""
    title_lower = title.lower()
    # Extract alert type from source or title
    for pattern in ALERT_PATTERNS:
        if pattern in title_lower or pattern in source.lower():
            # Use the pattern as part of the key
            return f"{agent}:{pattern}"
    # If no pattern matches, use extracted keywords
    topic_keys = _extract_topic_keys(title)
    if topic_keys:
        keyword_key = "-".join(sorted(topic_keys)[:3])  # First 3 keywords
        return f"{agent}:alert:{keyword_key}"
    return f"{agent}:unknown"


def normalize_task_filename(filename: str) -> str:
    """Normalize task filename to standard format.

    Standard formats:
    - {task_id}.md (pending)
    - {task_id}.executing.md (in progress)
    - {task_id}.done.md (completed)
    - {task_id}.failed.md (failed)

    Non-standard patterns to clean up:
    - .completed.revision-1.md -> .done.md
    - .resolved.md -> .done.md
    - .false-positive.md -> remove or keep .done.md
    """
    # Remove revision suffixes
    filename = re.sub(r'\.revision-\d+', '', filename)

    # Standardize status suffixes
    filename = re.sub(r'\.completed', '.done', filename)
    filename = re.sub(r'\.resolved', '.done', filename)
    filename = re.sub(r'\.false-positive', '', filename)  # Remove, will keep .done.md

    return filename


def should_suppress_alert(agent: str, title: str, source: str) -> tuple[bool, str]:
    """Check if an alert should be suppressed due to recent similar alerts.

    Returns:
        (should_suppress, reason) tuple

    Implements exponential backoff:
    - 1st alert: always allow (0min cooldown)
    - 2nd alert: suppress if <10min since last
    - 3rd alert: suppress if <30min since last
    - 4th+ alert: suppress if <60min since last
    """
    # Only apply to alert-type tasks
    title_lower = title.lower()
    source_lower = source.lower()
    is_alert = any(pattern in title_lower or pattern in source_lower
                  for pattern in ALERT_PATTERNS)

    if not is_alert:
        return False, ""

    state = _get_alert_dedup_state()
    state = _cleanup_old_alerts(state)

    key = _normalize_alert_key(agent, title, source)
    entry = state.get(key, {})

    if not entry:
        # First alert of this type
        return False, ""

    # Get backoff interval based on strike count
    strikes = entry.get("strikes", 0)
    interval_idx = min(strikes, len(_BACKOFF_INTERVALS) - 1)
    cooldown_minutes = _BACKOFF_INTERVALS[interval_idx]

    if cooldown_minutes == 0:
        return False, ""

    # Check if enough time has passed
    last_seen = datetime.fromisoformat(entry["last_seen"])
    elapsed = (datetime.now() - last_seen).total_seconds() / 60

    if elapsed < cooldown_minutes:
        reason = f"ALERT_DEDUP: {key} suppressed ({elapsed:.0f}min < {cooldown_minutes}min cooldown, strike={strikes})"
        print(reason)
        return True, reason

    return False, ""


def record_alert_created(agent: str, title: str, source: str, task_id: str = None):
    """Record that an alert was created, incrementing strike count."""
    # Only record alert-type tasks
    title_lower = title.lower()
    source_lower = source.lower()
    is_alert = any(pattern in title_lower or pattern in source_lower
                  for pattern in ALERT_PATTERNS)

    if not is_alert:
        return

    state = _get_alert_dedup_state()
    state = _cleanup_old_alerts(state)

    key = _normalize_alert_key(agent, title, source)
    entry = state.get(key, {})

    entry["strikes"] = entry.get("strikes", 0) + 1
    entry["last_seen"] = datetime.now().isoformat()
    entry["last_title"] = title[:100]
    entry["last_source"] = source
    if task_id:
        entry["last_task_id"] = task_id

    state[key] = entry
    _save_alert_dedup_state(state)


def auto_cancel_stale_alerts(max_age_hours: int = 24,
                              patterns: list[str] | None = None) -> int:
    """Cancel PENDING system-alert tasks older than max_age_hours.

    System-generated alerts (health checks, watchdog, routing audit) that sit
    PENDING for too long are stale — the condition either resolved itself or
    was handled by a newer alert. Auto-cancel them to keep the queue clean.

    Returns:
        Number of tasks cancelled.
    """
    from kurultai_paths import LOGS_DIR
    from neo4j_v2_core import TaskStore
    import logging

    logger = logging.getLogger(__name__)

    if patterns is None:
        patterns = list(ALERT_PATTERNS)

    cancelled = 0
    try:
        store = TaskStore()
        with store._driver.session() as sess:
            # Find PENDING system alert tasks older than threshold
            result = sess.run("""
                MATCH (t:Task {status: 'PENDING'})
                WHERE t.created_at < datetime() - duration({hours: $max_hours})
                  AND any(pattern IN $patterns WHERE
                      toLower(t.title) CONTAINS pattern OR
                      toLower(t.source) CONTAINS pattern)
                RETURN t.task_id AS tid, t.title AS title
            """, max_hours=max_age_hours, patterns=patterns)

            for record in result:
                tid = record["tid"]
                title = record["title"] or ""
                try:
                    with store._driver.session() as inner:
                        inner.run("""
                            MATCH (t:Task {task_id: $tid, status: 'PENDING'})
                            SET t.status = 'CANCELLED',
                                t.updated_at = datetime(),
                                t.cancel_reason = 'stale_alert_auto_cancel'
                        """, tid=tid)
                    cancelled += 1
                    logger.info(f"STALE_CANCEL: {tid} — '{title[:60]}'")
                except Exception as e:
                    logger.warning(f"Failed to cancel stale alert {tid}: {e}")

        store.close()
    except Exception as e:
        logger.warning(f"auto_cancel_stale_alerts failed: {e}")

    return cancelled
