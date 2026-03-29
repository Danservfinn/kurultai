#!/usr/bin/env python3
"""
supersede_detector.py — SUPERSEDES detection for Neo4j knowledge graph.

Detects when new information supersedes old facts and maintains
the [:SUPERSEDES] audit trail. All detection runs inline in the
Python extraction pipeline (not JavaScript).

Usage:
    from supersede_detector import (
        detect_explicit_signal,
        find_conflicting_inferences,
        mark_superseded,
        get_active_facts,
        get_field_history,
        find_active_contradictions,
        process_supersedes,
    )
"""

import logging
import re
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Explicit signal detection — keyword patterns indicating corrections
# ---------------------------------------------------------------------------

EXPLICIT_SIGNALS = [
    re.compile(r'\bactually\b', re.IGNORECASE),
    re.compile(r'\bchanged to\b', re.IGNORECASE),
    re.compile(r'\bno longer\b', re.IGNORECASE),
    re.compile(r'\bcorrection:', re.IGNORECASE),
    re.compile(r'\bupdate:', re.IGNORECASE),
    re.compile(r'\bmy\s+\w+\s+is\s+now\b', re.IGNORECASE),
    re.compile(r'\bi\s+moved\s+to\b', re.IGNORECASE),
    re.compile(r'\bi\s+switched\s+to\b', re.IGNORECASE),
    re.compile(r'\bnew\s+(email|number|phone|address)\b', re.IGNORECASE),
    re.compile(r'\bfyi.{0,20}(changed|updated|new)\b', re.IGNORECASE),
    re.compile(r"\bi\s+(?:don't|do\s+not)\s+\w+\s+anymore\b", re.IGNORECASE),
    re.compile(r'\bnot\s+\w+\s+(?:any\s*more|anymore)\b', re.IGNORECASE),
]


def detect_explicit_signal(text: str) -> tuple[bool, Optional[str]]:
    """Check message text for explicit correction/update signals.

    Returns:
        (detected, matched_signal) — detected is True if any signal found,
        matched_signal is the verbatim text that triggered detection.
    """
    if not text:
        return False, None
    for pattern in EXPLICIT_SIGNALS:
        match = pattern.search(text)
        if match:
            return True, match.group(0)
    return False, None


# ---------------------------------------------------------------------------
# Core supersede operations
# ---------------------------------------------------------------------------

def mark_superseded(
    session,
    new_id: str,
    old_id: str,
    reason: str,
    confidence: float,
    signal_text: str = "",
) -> bool:
    """Atomically mark old inference as superseded and create [:SUPERSEDES].

    The [:SUPERSEDES] relationship carries audit data (review fix #13):
    - detected_at, reason, confidence, signal_text
    - old_value, new_value (captured from the inference nodes)

    Returns True if the operation was applied (old node was not already superseded).
    """
    try:
        result = session.run("""
            MATCH (newI:Inference {id: $new_id})
            MATCH (oldI:Inference {id: $old_id})
            WHERE NOT oldI.superseded
            SET oldI.superseded = true,
                oldI.supersededAt = datetime()
            MERGE (newI)-[r:SUPERSEDES]->(oldI)
            SET r.detected_at = datetime(),
                r.reason = $reason,
                r.confidence = $confidence,
                r.signal_text = $signal_text,
                r.old_value = oldI.value,
                r.new_value = newI.value
            RETURN oldI.id AS marked
        """, new_id=new_id, old_id=old_id, reason=reason,
             confidence=confidence, signal_text=signal_text)
        record = result.single()
        return record is not None
    except Exception as e:
        logger.warning(f"mark_superseded failed ({new_id} -> {old_id}): {e}")
        return False


def find_conflicting_inferences(
    session,
    human_id: str,
    field: str,
    new_value: str,
    new_timestamp: str,
) -> list[dict]:
    """Find active inferences for the same field with a different value.

    Only searches nodes with field IS NOT NULL (review fix #3: guards
    against un-backfilled nodes that lack structured field/value).

    Returns list of dicts: {id, value, ts}
    """
    if not field:
        return []
    try:
        result = session.run("""
            MATCH (i:Inference {humanId: $hid})
            WHERE NOT i.superseded
              AND i.field IS NOT NULL
              AND i.field = $field
              AND i.value <> $new_value
              AND toString(i.timestamp) < $ts
            RETURN i.id AS id, i.value AS value,
                   toString(i.timestamp) AS ts
            ORDER BY i.timestamp ASC
        """, hid=human_id, field=field, new_value=new_value, ts=new_timestamp)
        return [dict(r) for r in result]
    except Exception as e:
        logger.warning(f"find_conflicting_inferences failed: {e}")
        return []


def find_active_contradictions(session, human_id: str) -> list[dict]:
    """Find unresolved contradictions: two active inferences for same field
    with different values.

    Returns list of dicts: {field, idA, valA, idB, valB}
    """
    try:
        result = session.run("""
            MATCH (a:Inference {humanId: $hid}),
                  (b:Inference {humanId: $hid})
            WHERE NOT a.superseded AND NOT b.superseded
              AND a.field IS NOT NULL AND a.field = b.field
              AND a.value <> b.value
              AND id(a) < id(b)
            RETURN a.field AS field,
                   a.id AS idA, a.value AS valA,
                   b.id AS idB, b.value AS valB
            ORDER BY a.field
        """, hid=human_id)
        return [dict(r) for r in result]
    except Exception as e:
        logger.warning(f"find_active_contradictions failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Read queries
# ---------------------------------------------------------------------------

def get_active_facts(session, human_id: str) -> list[dict]:
    """Get all non-superseded inferences for a human."""
    try:
        result = session.run("""
            MATCH (i:Inference {humanId: $hid})
            WHERE NOT i.superseded
            RETURN i.id AS id, i.field AS field, i.value AS value,
                   i.confidence AS confidence,
                   toString(i.timestamp) AS ts
            ORDER BY i.timestamp DESC
        """, hid=human_id)
        return [dict(r) for r in result]
    except Exception as e:
        logger.warning(f"get_active_facts failed: {e}")
        return []


def get_field_history(session, human_id: str, field: str) -> list[dict]:
    """Get change history for a field, following [:SUPERSEDES] chain."""
    try:
        result = session.run("""
            MATCH (i:Inference {humanId: $hid, field: $field})
            OPTIONAL MATCH (i)<-[s:SUPERSEDES]-(newer:Inference)
            RETURN i.id AS id, i.value AS value,
                   i.superseded AS superseded,
                   toString(i.timestamp) AS ts,
                   toString(i.supersededAt) AS superseded_at,
                   s.reason AS superseded_reason,
                   s.signal_text AS signal_text,
                   newer.id AS superseded_by
            ORDER BY i.timestamp DESC
        """, hid=human_id, field=field)
        return [dict(r) for r in result]
    except Exception as e:
        logger.warning(f"get_field_history failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Pipeline integration helper
# ---------------------------------------------------------------------------

def process_supersedes(
    session,
    human_id: str,
    inference_id: str,
    field: Optional[str],
    value: Optional[str],
    message_text: str,
) -> dict:
    """Process supersede detection for a newly created inference.

    Call this AFTER creating the Inference node, BEFORE committing.

    Returns:
        {
            "superseded_count": int,
            "superseded_ids": list[str],
            "explicit_signal": bool,
            "signal_text": str | None,
        }
    """
    if not field or not value:
        return {"superseded_count": 0, "superseded_ids": [],
                "explicit_signal": False, "signal_text": None}

    detected, signal = detect_explicit_signal(message_text)
    now = datetime.now(timezone.utc).isoformat()

    conflicts = find_conflicting_inferences(
        session, human_id, field, value, now
    )

    superseded_ids = []
    for conflict in conflicts:
        reason = "explicit_signal" if detected else "implicit_same_field"
        confidence = 0.95 if detected else 0.75
        ok = mark_superseded(
            session, inference_id, conflict["id"],
            reason=reason,
            confidence=confidence,
            signal_text=signal or "",
        )
        if ok:
            superseded_ids.append(conflict["id"])

    return {
        "superseded_count": len(superseded_ids),
        "superseded_ids": superseded_ids,
        "explicit_signal": detected,
        "signal_text": signal,
    }
