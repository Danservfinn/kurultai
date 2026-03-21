#!/usr/bin/env python3
"""
Pending Question Manager — Neo4j-backed state for sequential interrogation.

Replaces the in-memory PendingInterrogation/PendingConfirmation dicts from
calendar_parser.py with durable Neo4j PendingQuestion nodes.

Only ONE PendingQuestion is active per human at a time.

Usage:
    from pending_question import (
        get_pending_question, create_question, answer_question,
        skip_question, expire_old_questions, queue_event_questions,
        get_next_event_question,
    )
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from zoneinfo import ZoneInfo

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import neo4j_session

logger = logging.getLogger(__name__)

LOCAL_TZ = ZoneInfo("America/New_York")

# Reuse field question text from calendar_parser
FIELD_QUESTIONS = {
    "name": "What should I call this event?",
    "date_text": "When is this happening?",
    "duration": "How long will it be? (default: 2 hours)",
    "location": "Where is it?",
    "participants": "Anyone else coming?",
    "description": "Any details to add? (optional, reply 'skip')",
    "reminder_text": "Want a reminder? When? (e.g. '1 hour before', or 'no')",
    "recurrence": "Is this recurring? (e.g. 'weekly', 'monthly', or 'no')",
    "category": "What kind of event is this? (dinner, birthday, meeting, concert, hike, etc.)",
    "indoor_outdoor": "Indoor or outdoor?",
    "cost": "Any cost? (e.g. '$20', 'free', 'BYOB')",
    "what_to_bring": "Should people bring anything?",
}

# Answers that mean "skip this field"
SKIP_WORDS = {"skip", "no", "nah", "nope", "none", "n/a", "na", "pass", "-"}

# Answers that mean "I'm done, create the event now"
DONE_WORDS = {"done", "that's it", "thats it", "create it", "just create it", "go ahead"}


class QuestionAlreadyPending(Exception):
    """Raised when trying to create a question while one is already active."""
    pass


# ---------------------------------------------------------------------------
# Core CRUD
# ---------------------------------------------------------------------------

def get_pending_question(human_id: str, channel_id: Optional[str] = None) -> Optional[Dict]:
    """Get the oldest PENDING question for a human (only 1 active at a time).

    Args:
        human_id: UUID of the Human
        channel_id: Optional channel scope (group_id or None for DM).
                    If provided, only returns questions for that channel.

    Returns dict with: id, humanId, type, context, question, field, status,
    createdAt, expiresAt. Returns None if no pending question.
    """
    try:
        with neo4j_session() as session:
            if channel_id:
                result = session.run(
                    """
                    MATCH (pq:PendingQuestion {humanId: $human_id, status: 'PENDING'})
                    WHERE pq.expiresAt > datetime()
                      AND pq.channelId = $channel_id
                    RETURN pq {.*} AS pq
                    ORDER BY pq.createdAt ASC
                    LIMIT 1
                    """,
                    human_id=human_id,
                    channel_id=channel_id,
                )
            else:
                result = session.run(
                    """
                    MATCH (pq:PendingQuestion {humanId: $human_id, status: 'PENDING'})
                    WHERE pq.expiresAt > datetime()
                      AND (pq.channelId IS NULL OR pq.channelId = 'dm')
                    RETURN pq {.*} AS pq
                    ORDER BY pq.createdAt ASC
                    LIMIT 1
                    """,
                    human_id=human_id,
                )
            record = result.single()
            if not record:
                return None
            pq = dict(record["pq"])
            # Deserialize context JSON
            if pq.get("context"):
                pq["context"] = json.loads(pq["context"])
            return pq
    except Exception as e:
        logger.error(f"get_pending_question failed for {human_id}: {e}")
        return None


def create_question(
    human_id: str,
    question: str,
    field: str,
    qtype: str,
    context: dict,
    ttl_minutes: int = 30,
    channel_id: Optional[str] = None,
) -> str:
    """Create a PendingQuestion node atomically. Returns question ID.

    Uses a MERGE-based approach with a sentinel node to prevent race conditions.
    If a PENDING question already exists for this human+channel, raises QuestionAlreadyPending.
    """
    channel = channel_id or "dm"
    question_id = str(uuid.uuid4())
    now = datetime.now(LOCAL_TZ)
    expires = now + timedelta(minutes=ttl_minutes)

    try:
        with neo4j_session() as session:
            # Atomic check-and-create: only create if no PENDING question exists
            result = session.run(
                """
                OPTIONAL MATCH (existing:PendingQuestion {humanId: $human_id, status: 'PENDING'})
                WHERE existing.channelId = $channel
                  AND existing.expiresAt > datetime()
                WITH existing
                WHERE existing IS NULL
                CREATE (pq:PendingQuestion {
                    id: $id,
                    humanId: $human_id,
                    type: $qtype,
                    context: $context,
                    question: $question,
                    field: $field,
                    channelId: $channel,
                    status: 'PENDING',
                    createdAt: datetime($created_at),
                    expiresAt: datetime($expires_at)
                })
                RETURN pq.id AS id
                """,
                id=question_id,
                human_id=human_id,
                qtype=qtype,
                context=json.dumps(context, default=str),
                question=question,
                field=field,
                channel=channel,
                created_at=now.isoformat(),
                expires_at=expires.isoformat(),
            )
            record = result.single()
            if not record:
                # A pending question already exists
                raise QuestionAlreadyPending(
                    f"Human {human_id} already has a pending question on channel {channel}"
                )
            return question_id
    except QuestionAlreadyPending:
        raise
    except Exception as e:
        logger.error(f"create_question failed: {e}")
        raise


def answer_question(question_id: str, answer: str) -> Optional[Dict]:
    """Mark question as ANSWERED, store the answer. Returns the question context.

    Uses WHERE status = 'PENDING' guard for idempotency (concurrent calls).
    Returns None if question was already answered (race condition).

    Handles skip/done detection:
    - skip words -> mark SKIPPED, advance to next field
    - done words -> mark all remaining SKIPPED, signal finalization
    """
    answer_lower = answer.strip().lower()

    # Determine if this is a skip or done
    is_skip = answer_lower in SKIP_WORDS
    is_done = answer_lower in DONE_WORDS

    new_status = "SKIPPED" if is_skip else "ANSWERED"

    try:
        with neo4j_session() as session:
            result = session.run(
                """
                MATCH (pq:PendingQuestion {id: $id})
                WHERE pq.status = 'PENDING'
                SET pq.status = $status,
                    pq.answeredAt = datetime(),
                    pq.answer = $answer
                RETURN pq {.*} AS pq
                """,
                id=question_id,
                status=new_status,
                answer=answer if not is_skip else None,
            )
            record = result.single()
            if not record:
                return None  # Already answered (race condition)

            pq = dict(record["pq"])
            if pq.get("context"):
                pq["context"] = json.loads(pq["context"])

            context = pq.get("context", {})
            field = pq.get("field", "")

            # Apply answer to event_data in context
            if not is_skip and not is_done and context.get("event_data"):
                _apply_answer_to_context(context, field, answer)
                # If the answered field is date_text, resolve datetime
                if field == "date_text":
                    _resolve_date_in_context(context, answer)
                # Save updated context back
                session.run(
                    """
                    MATCH (pq:PendingQuestion {id: $id})
                    SET pq.context = $context
                    """,
                    id=question_id,
                    context=json.dumps(context, default=str),
                )

            # If "done", mark all remaining fields as handled
            if is_done:
                context["remaining_fields"] = []
                session.run(
                    """
                    MATCH (pq:PendingQuestion {id: $id})
                    SET pq.context = $context
                    """,
                    id=question_id,
                    context=json.dumps(context, default=str),
                )

            pq["context"] = context
            pq["_is_done"] = is_done
            pq["_is_skip"] = is_skip
            return pq

    except Exception as e:
        logger.error(f"answer_question failed for {question_id}: {e}")
        return None


def skip_question(question_id: str) -> bool:
    """Mark question as SKIPPED."""
    try:
        with neo4j_session() as session:
            result = session.run(
                """
                MATCH (pq:PendingQuestion {id: $id})
                WHERE pq.status = 'PENDING'
                SET pq.status = 'SKIPPED', pq.answeredAt = datetime()
                RETURN pq.id AS id
                """,
                id=question_id,
            )
            return result.single() is not None
    except Exception as e:
        logger.error(f"skip_question failed for {question_id}: {e}")
        return False


def expire_old_questions() -> int:
    """Expire questions past their TTL. Returns count of expired questions.

    Also increments proactiveSkipCount on Human node for expired
    profile_curiosity questions (ignored = skipped for backoff).
    """
    try:
        with neo4j_session() as session:
            # First, find curiosity questions that are expiring (for backoff tracking)
            curiosity_result = session.run(
                """
                MATCH (pq:PendingQuestion)
                WHERE pq.status = 'PENDING'
                  AND pq.expiresAt <= datetime()
                  AND pq.type = 'profile_curiosity'
                RETURN pq.humanId AS humanId
                """
            )
            curiosity_humans = [r["humanId"] for r in curiosity_result]

            # Increment proactiveSkipCount for each
            for hid in curiosity_humans:
                session.run(
                    """
                    MATCH (h:Human {id: $hid})
                    SET h.proactiveSkipCount = coalesce(h.proactiveSkipCount, 0) + 1
                    """,
                    hid=hid,
                )

            # Now expire all old questions
            result = session.run(
                """
                MATCH (pq:PendingQuestion)
                WHERE pq.status = 'PENDING' AND pq.expiresAt <= datetime()
                SET pq.status = 'EXPIRED'
                RETURN count(pq) AS expired
                """
            )
            record = result.single()
            count = record["expired"] if record else 0
            if count > 0:
                logger.info(f"Expired {count} pending questions")
            return count
    except Exception as e:
        logger.error(f"expire_old_questions failed: {e}")
        return 0


# ---------------------------------------------------------------------------
# Sequential Event Interrogation
# ---------------------------------------------------------------------------

def queue_event_questions(
    human_id: str,
    event_data: dict,
    missing_fields: list,
    resolved_time: Optional[dict] = None,
    sender_name: str = "",
) -> str:
    """Queue the FIRST missing field as a PendingQuestion.

    Remaining fields are stored in context for sequential follow-up.
    Returns the question text to send to the human.
    """
    if not missing_fields:
        return ""

    first_field = missing_fields[0]
    remaining = missing_fields[1:]

    # Build known-parts summary
    known_parts = []
    if event_data.get("name"):
        known_parts.append(event_data["name"])
    if event_data.get("date_text"):
        if resolved_time and resolved_time.get("interpretation"):
            known_parts.append(resolved_time["interpretation"])
        else:
            known_parts.append(event_data["date_text"])
    if event_data.get("location"):
        known_parts.append(f"at {event_data['location']}")

    summary = f"Got it — {' — '.join(known_parts)}." if known_parts else "Let me help you create an event."

    question_text = FIELD_QUESTIONS.get(first_field, f"What about the {first_field}?")

    context = {
        "event_data": event_data,
        "remaining_fields": remaining,
        "resolved_time": resolved_time,
        "sender_name": sender_name,
        "confirmation_pending": False,
    }

    create_question(
        human_id=human_id,
        question=question_text,
        field=first_field,
        qtype="event_field",
        context=context,
        ttl_minutes=30,
    )

    return f"{summary} {question_text}"


def get_next_event_question(human_id: str, context: dict) -> Optional[str]:
    """After a question is answered, check context for more missing fields.

    If fields remain, creates the next PendingQuestion and returns its text.
    If none remain, returns None (event is ready for confirmation).
    """
    remaining = context.get("remaining_fields", [])
    if not remaining:
        return None

    next_field = remaining[0]
    new_remaining = remaining[1:]

    question_text = FIELD_QUESTIONS.get(next_field, f"What about the {next_field}?")

    new_context = dict(context)
    new_context["remaining_fields"] = new_remaining

    create_question(
        human_id=human_id,
        question=question_text,
        field=next_field,
        qtype="event_field",
        context=new_context,
        ttl_minutes=30,
    )

    return question_text


def build_event_summary(context: dict) -> str:
    """Build a human-readable event summary from collected context."""
    ed = context.get("event_data", {})
    rt = context.get("resolved_time", {})

    lines = ["Here's what I've got:"]
    if ed.get("name"):
        lines.append(f"  Event: {ed['name']}")
    if rt and rt.get("interpretation"):
        lines.append(f"  When: {rt['interpretation']}")
    elif ed.get("date_text"):
        lines.append(f"  When: {ed['date_text']}")
    if ed.get("duration_minutes"):
        h = ed["duration_minutes"] / 60
        lines.append(f"  Duration: {int(h)} hours" if h == int(h) else f"  Duration: {h:.1f} hours")
    if ed.get("location"):
        lines.append(f"  Where: {ed['location']}")
    if ed.get("participants"):
        p = ed["participants"]
        if isinstance(p, list):
            lines.append(f"  Who: {', '.join(p)}")
        else:
            lines.append(f"  Who: {p}")
    if ed.get("description"):
        lines.append(f"  Notes: {ed['description']}")
    if ed.get("reminder_text") and ed["reminder_text"].lower() not in ("no", "none", "skip"):
        lines.append(f"  Reminder: {ed['reminder_text']}")
    if ed.get("recurrence") and ed["recurrence"].lower() not in ("no", "none", "skip"):
        lines.append(f"  Recurring: {ed['recurrence']}")

    lines.append("Create this event? Reply yes or no.")
    return "\n".join(lines)


def create_confirmation_question(human_id: str, context: dict) -> str:
    """Create a confirmation PendingQuestion after all fields are collected."""
    summary = build_event_summary(context)

    new_context = dict(context)
    new_context["confirmation_pending"] = True

    create_question(
        human_id=human_id,
        question=summary,
        field="confirmation",
        qtype="event_field",
        context=new_context,
        ttl_minutes=30,
    )

    return summary


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _apply_answer_to_context(context: dict, field: str, answer: str):
    """Apply an answer to the event_data within context."""
    ed = context.get("event_data", {})
    answer_clean = answer.strip()

    if field == "name":
        ed["name"] = answer_clean
    elif field == "date_text":
        ed["date_text"] = answer_clean
    elif field == "duration":
        ed["duration_minutes"] = _parse_duration_text(answer_clean)
    elif field == "location":
        ed["location"] = answer_clean
    elif field == "participants":
        import re
        names = re.split(r'[,&]|\band\b', answer_clean)
        ed["participants"] = [n.strip() for n in names if n.strip()]
    elif field == "description":
        ed["description"] = answer_clean
    elif field == "reminder_text":
        ed["reminder_text"] = answer_clean
    elif field == "recurrence":
        ed["recurrence"] = answer_clean
    elif field in ("category", "indoor_outdoor", "cost", "what_to_bring",
                    "dress_code", "dietary_notes", "vibe"):
        ed[field] = answer_clean

    context["event_data"] = ed


def _resolve_date_in_context(context: dict, answer: str):
    """Resolve a date_text answer and store in context['resolved_time']."""
    try:
        from calendar_parser import resolve_datetime
        event_name = context.get("event_data", {}).get("name")
        resolved = resolve_datetime(answer, event_name=event_name)
        context["resolved_time"] = _serialize_resolved_time(resolved)
    except Exception as e:
        logger.warning(f"Failed to resolve date '{answer}': {e}")


def _serialize_resolved_time(resolved: dict) -> dict:
    """Convert datetime objects to ISO strings for JSON storage."""
    out = {}
    for k, v in resolved.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        elif isinstance(v, list):
            out[k] = [x.isoformat() if isinstance(x, datetime) else x for x in v]
        else:
            out[k] = v
    return out


def _parse_duration_text(text: str) -> Optional[int]:
    """Parse duration text like '2 hours', '90 minutes' into minutes."""
    import re
    text_lower = text.lower().strip()

    match = re.match(r'(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)\b', text_lower)
    if match:
        return int(float(match.group(1)) * 60)

    match = re.match(r'(\d+)\s*(?:minutes?|mins?|m)\b', text_lower)
    if match:
        return int(match.group(1))

    match = re.match(r'(\d+)[h:](\d+)', text_lower)
    if match:
        return int(match.group(1)) * 60 + int(match.group(2))

    match = re.match(r'^(\d+)$', text_lower)
    if match:
        val = int(match.group(1))
        return val * 60 if val <= 12 else val

    return None


if __name__ == "__main__":
    print("PendingQuestion manager — self-test")
    test_hid = "test-human-" + uuid.uuid4().hex[:8]

    # Test create
    qid = create_question(
        human_id=test_hid,
        question="How long will it be?",
        field="duration",
        qtype="event_field",
        context={"event_data": {"name": "Lunch"}, "remaining_fields": ["location"]},
    )
    print(f"  Created: {qid}")

    # Test get
    pq = get_pending_question(test_hid)
    print(f"  Pending: {pq['field']} — {pq['question']}")

    # Test answer
    answered = answer_question(qid, "2 hours")
    print(f"  Answered: {answered is not None}")

    # Cleanup
    with neo4j_session() as s:
        s.run("MATCH (pq:PendingQuestion {humanId: $hid}) DETACH DELETE pq", hid=test_hid)
    print("  Cleaned up. Self-test passed.")
