#!/usr/bin/env python3
"""
Curiosity Engine — Proactive knowledge gap detection and question generation.

Scans human profiles for missing data (timezone, display name, event locations)
and generates natural questions to fill those gaps. Rate-limited to avoid
annoying humans.

Usage:
    from curiosity_engine import (
        identify_knowledge_gaps, should_ask_now,
        generate_curiosity_question, send_curiosity_question,
    )
"""
from __future__ import annotations

import logging
import os
import sys
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import neo4j_session
from consent_decorator import check_consent

logger = logging.getLogger(__name__)

LOCAL_TZ = ZoneInfo("America/New_York")

# Signal configuration for sending proactive questions
SIGNAL_ACCOUNT = os.getenv("SIGNAL_ACCOUNT", "+15165643945")
SIGNAL_API_URL = os.getenv("SIGNAL_API_URL", "http://127.0.0.1:8080")


# ---------------------------------------------------------------------------
# Question templates (natural, not robotic)
# ---------------------------------------------------------------------------

QUESTION_TEMPLATES = {
    "timezone": "Hey {name}, what timezone are you in? Helps me get event times right.",
    "displayName": "By the way, what should I call you?",
    "event_location": "Quick one — where's {event_name} happening on {event_date}?",
    "re_engagement": "Hey {name}, it's been a while. Anything on your plate I can help with?",
    # --- Enriched event field questions ---
    "event_dress_code": "Quick one — is {event_name} on {event_date} casual or dressy?",
    "event_cost": "Hey {name}, is there a cost for {event_name}? Just so people know what to expect.",
    "event_what_to_bring": "Should people bring anything to {event_name}?",
    "event_indoor_outdoor": "Is {event_name} indoors or outdoors? Asking in case of weather.",
    "event_dietary": "Hey {name}, any dietary restrictions for {event_name}? I can let the group know.",
    "event_transport": "How are folks getting to {event_name}? Any parking tips?",
    "event_category": "What kind of event is {event_name}? (dinner, birthday, meeting, etc.)",
    "event_rain_plan": "Looks like rain on {event_date} — any backup plan for {event_name}?",
}

# Priority: higher = ask first
GAP_PRIORITY = {
    "timezone": 5,
    "displayName": 4,
    "event_location": 3,
    "event_rain_plan": 2.6,
    "event_dress_code": 2.5,
    "event_cost": 2.4,
    "event_what_to_bring": 2.3,
    "event_indoor_outdoor": 2.2,
    "event_dietary": 2.1,
    "event_transport": 2.0,
    "event_category": 1.8,
    "re_engagement": 1,
}

# Backoff schedule: consecutive skips/expires → days to wait
BACKOFF_SCHEDULE = {
    0: 1,   # Normal: 1 day between questions
    1: 1,   # 1 skip: still 1 day
    2: 3,   # 2 consecutive: wait 3 days
    3: 7,   # 3 consecutive: wait 7 days
    4: 14,  # 4+: wait 14 days
}


# ---------------------------------------------------------------------------
# Knowledge Gap Detection
# ---------------------------------------------------------------------------

def identify_knowledge_gaps(human_id: str) -> List[Dict]:
    """Scan a human's profile and events for gaps.

    Returns prioritized list of gaps:
    - Missing timezone (high priority — affects scheduling)
    - Missing display name (they're just a phone number)
    - Upcoming event with no location
    - No interaction in 7+ days (re-engagement)

    Each gap: {field, question, priority, reason}
    """
    gaps = []

    try:
        with neo4j_session() as session:
            # Fetch human profile
            result = session.run(
                """
                MATCH (h:Human {id: $hid})
                OPTIONAL MATCH (h)-[:IDENTIFIED_BY]->(i:Identifier {type: 'SIGNAL_PHONE'})
                RETURN h.timezone AS timezone,
                       h.displayName AS displayName,
                       h.status AS status,
                       i.value AS phone,
                       toString(h.lastProactiveAt) AS lastProactiveAt,
                       h.proactiveSkipCount AS proactiveSkipCount
                """,
                hid=human_id,
            )
            record = result.single()
            if not record:
                return []

            name = record["displayName"] or "there"
            phone = record["phone"] or ""

            # Gap: missing timezone
            if not record["timezone"]:
                gaps.append({
                    "field": "timezone",
                    "question": QUESTION_TEMPLATES["timezone"].format(name=name),
                    "priority": GAP_PRIORITY["timezone"],
                    "reason": "No timezone set — event times may be wrong",
                })

            # Gap: missing display name (only have phone)
            if not record["displayName"]:
                gaps.append({
                    "field": "displayName",
                    "question": QUESTION_TEMPLATES["displayName"],
                    "priority": GAP_PRIORITY["displayName"],
                    "reason": "Only known by phone number",
                })

            # Gap: upcoming event with no location
            event_result = session.run(
                """
                MATCH (e:Event)
                WHERE e.start_datetime > datetime()
                  AND e.start_datetime < datetime() + duration('P7D')
                  AND (e.location IS NULL OR e.location = '')
                  AND e.creator_phone IN [$phone]
                RETURN e.name AS event_name,
                       toString(e.start_datetime) AS event_date
                LIMIT 1
                """,
                phone=phone,
            )
            event_rec = event_result.single()
            if event_rec:
                gaps.append({
                    "field": "event_location",
                    "question": QUESTION_TEMPLATES["event_location"].format(
                        event_name=event_rec["event_name"],
                        event_date=event_rec["event_date"][:10] if event_rec["event_date"] else "soon",
                    ),
                    "priority": GAP_PRIORITY["event_location"],
                    "reason": f"Event '{event_rec['event_name']}' has no location",
                })

            # Gap: upcoming events missing enriched fields (within 3 days)
            enriched_events = session.run(
                """
                MATCH (e:Event)
                WHERE e.start_datetime > datetime()
                  AND e.start_datetime < datetime() + duration('P3D')
                  AND e.status = 'active'
                  AND e.creator_phone IN [$phone]
                RETURN e.name AS event_name,
                       e.event_id AS event_id,
                       toString(e.start_datetime) AS event_date,
                       e.category AS category,
                       e.dress_code AS dress_code,
                       e.cost AS cost,
                       e.what_to_bring AS what_to_bring,
                       e.indoor_outdoor AS indoor_outdoor,
                       e.dietary_notes AS dietary_notes,
                       e.transport_notes AS transport_notes,
                       e.rain_plan AS rain_plan
                ORDER BY e.start_datetime
                LIMIT 3
                """,
                phone=phone,
            )

            event_field_gaps_added = 0
            for evt in enriched_events:
                if event_field_gaps_added >= 2:
                    break
                evt_name = evt["event_name"] or "your event"
                evt_date = evt["event_date"][:10] if evt["event_date"] else "soon"

                # Calculate days until event
                try:
                    from dateutil.parser import isoparse
                    evt_dt = isoparse(evt["event_date"])
                    if evt_dt.tzinfo is None:
                        evt_dt = evt_dt.replace(tzinfo=LOCAL_TZ)
                    days_until = (evt_dt - datetime.now(LOCAL_TZ)).days
                except Exception:
                    days_until = 3

                # Prioritize by days-until-event
                # 3 days: category, indoor/outdoor, cost
                # 2 days: dress code, what to bring, transport
                # 1 day: dietary, rain plan
                field_checks = []
                if days_until >= 2:
                    if not evt["category"]:
                        field_checks.append("event_category")
                    if not evt["indoor_outdoor"]:
                        field_checks.append("event_indoor_outdoor")
                    if not evt["cost"]:
                        field_checks.append("event_cost")
                if days_until <= 2:
                    if not evt["dress_code"]:
                        field_checks.append("event_dress_code")
                    if not evt["what_to_bring"]:
                        field_checks.append("event_what_to_bring")
                    if not evt["transport_notes"]:
                        field_checks.append("event_transport")
                if days_until <= 1:
                    if not evt["dietary_notes"]:
                        field_checks.append("event_dietary")

                # Outdoor event within 2 days with no rain plan
                if evt["indoor_outdoor"] == "outdoor" and days_until <= 2 and not evt["rain_plan"]:
                    gaps.append({
                        "field": "event_rain_plan",
                        "question": QUESTION_TEMPLATES["event_rain_plan"].format(
                            event_name=evt_name, event_date=evt_date,
                        ),
                        "priority": 3.0,
                        "reason": f"Outdoor event '{evt_name}' in {days_until} days with no rain plan",
                        "context": {"event_name": evt_name, "event_id": evt.get("event_id")},
                    })
                    event_field_gaps_added += 1

                # Add at most 1 enriched-field gap per event
                for field_key in field_checks:
                    if event_field_gaps_added >= 2:
                        break
                    gaps.append({
                        "field": field_key,
                        "question": QUESTION_TEMPLATES[field_key].format(
                            name=name, event_name=evt_name, event_date=evt_date,
                        ),
                        "priority": GAP_PRIORITY.get(field_key, 2.0),
                        "reason": f"Event '{evt_name}' missing {field_key.replace('event_', '')}",
                        "context": {"event_name": evt_name, "event_id": evt.get("event_id")},
                    })
                    event_field_gaps_added += 1
                    break  # Max 1 enriched gap per event

            # Gap: no interaction in 7+ days (re-engagement)
            last_msg_result = session.run(
                """
                MATCH (m:Message {humanId: $hid, direction: 'inbound'})
                RETURN max(m.timestamp) AS lastMsg
                """,
                hid=human_id,
            )
            last_msg_rec = last_msg_result.single()
            if last_msg_rec and last_msg_rec["lastMsg"]:
                last_msg_dt = last_msg_rec["lastMsg"]
                if hasattr(last_msg_dt, 'to_native'):
                    last_msg_dt = last_msg_dt.to_native()
                if isinstance(last_msg_dt, datetime):
                    # Make timezone-aware if naive
                    if last_msg_dt.tzinfo is None:
                        last_msg_dt = last_msg_dt.replace(tzinfo=LOCAL_TZ)
                    days_ago = (datetime.now(LOCAL_TZ) - last_msg_dt).days
                    if days_ago >= 7:
                        gaps.append({
                            "field": "re_engagement",
                            "question": QUESTION_TEMPLATES["re_engagement"].format(name=name),
                            "priority": GAP_PRIORITY["re_engagement"],
                            "reason": f"No interaction in {days_ago} days",
                        })

    except Exception as e:
        logger.error(f"identify_knowledge_gaps failed for {human_id}: {e}")

    # Sort by priority descending
    gaps.sort(key=lambda g: g["priority"], reverse=True)
    return gaps


# ---------------------------------------------------------------------------
# Rate Limiting
# ---------------------------------------------------------------------------

def should_ask_now(human_id: str) -> bool:
    """Rate limiting — don't annoy the human.

    Rules:
    - Max 1 proactive question per day per human
    - Don't ask if human sent a message in the last hour
    - Don't ask if a PendingQuestion already exists (any type)
    - Don't ask if last proactive question was skipped/expired (backoff)
    - Require consent: proactive_engagement
    """
    # Check consent first
    if not check_consent(human_id, "proactive_engagement"):
        return False

    try:
        with neo4j_session() as session:
            # Check for existing pending question
            pending_result = session.run(
                """
                MATCH (pq:PendingQuestion {humanId: $hid, status: 'PENDING'})
                RETURN count(pq) AS cnt
                """,
                hid=human_id,
            )
            if pending_result.single()["cnt"] > 0:
                return False

            # Get human profile for rate limiting
            result = session.run(
                """
                MATCH (h:Human {id: $hid})
                RETURN toString(h.lastProactiveAt) AS lastProactiveAt,
                       coalesce(h.proactiveSkipCount, 0) AS skipCount
                """,
                hid=human_id,
            )
            record = result.single()
            if not record:
                return False

            skip_count = record["skipCount"]
            last_proactive = record["lastProactiveAt"]

            # Exponential backoff based on consecutive skips
            max_skip = max(BACKOFF_SCHEDULE.keys())
            wait_days = BACKOFF_SCHEDULE.get(
                min(skip_count, max_skip),
                BACKOFF_SCHEDULE[max_skip],
            )

            if last_proactive:
                try:
                    from dateutil.parser import isoparse
                    lp_dt = isoparse(last_proactive)
                    if lp_dt.tzinfo is None:
                        lp_dt = lp_dt.replace(tzinfo=LOCAL_TZ)
                    if datetime.now(LOCAL_TZ) - lp_dt < timedelta(days=wait_days):
                        return False
                except Exception:
                    pass

            # Don't ask if human sent a message in the last hour
            msg_result = session.run(
                """
                MATCH (m:Message {humanId: $hid, direction: 'inbound'})
                WHERE m.timestamp > datetime() - duration('PT1H')
                RETURN count(m) AS recent
                """,
                hid=human_id,
            )
            if msg_result.single()["recent"] > 0:
                return False

            return True

    except Exception as e:
        logger.error(f"should_ask_now failed for {human_id}: {e}")
        return False


# ---------------------------------------------------------------------------
# Question Generation & Sending
# ---------------------------------------------------------------------------

def generate_curiosity_question(human_id: str) -> Optional[Dict]:
    """Pick the highest-priority gap and generate a question.

    Returns None if should_ask_now() is False or no gaps found.
    Returns {question, field, context, priority} if there's something to ask.
    """
    if not should_ask_now(human_id):
        return None

    gaps = identify_knowledge_gaps(human_id)
    if not gaps:
        return None

    best = gaps[0]
    context = {"reason": best["reason"]}
    # Include event_name for event field questions
    if best.get("context", {}).get("event_name"):
        context["event_name"] = best["context"]["event_name"]
    if best.get("context", {}).get("event_id"):
        context["event_id"] = best["context"]["event_id"]
    return {
        "question": best["question"],
        "field": best["field"],
        "context": context,
        "priority": best["priority"],
    }


def _is_valid_signal_phone(phone: str) -> bool:
    """Reject obviously fake/test phone numbers."""
    if not phone or len(phone) < 10:
        return False
    # Remove spaces, dashes, parentheses for validation
    clean_phone = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")

    # Test prefixes and patterns used in dev/seed data
    test_patterns = [
        "+1999", "+15550", "+15551",  # Test prefixes
        "+8111",  # Suspicious long numbers starting with +81
        "+000",   # Invalid country code
    ]
    for pattern in test_patterns:
        if clean_phone.startswith(pattern):
            return False

    # Reject numbers that are too long (real E.164 numbers are max 15 digits including +)
    if len(clean_phone) > 16:
        return False

    # Reject the specific fake number from logs
    if clean_phone == "+81114726038927336915312281070740144024408":
        return False

    # Reject obviously fake patterns (all same digit, sequential)
    digits_only = clean_phone.replace("+", "")
    if len(set(digits_only)) <= 2:  # Too few unique digits
        return False

    return True


def send_curiosity_question(human_id: str) -> bool:
    """End-to-end: identify gap -> check rate limits -> create PendingQuestion -> send via Signal.

    Returns True if a question was sent.
    """
    question_data = generate_curiosity_question(human_id)
    if not question_data:
        return False

    try:
        from pending_question import create_question

        # Pre-flight: fetch human profile and phone before creating the question
        with neo4j_session() as session:
            result = session.run(
                """
                MATCH (h:Human {id: $hid})
                OPTIONAL MATCH (h)-[:IDENTIFIED_BY]->(i:Identifier {type: 'SIGNAL_PHONE'})
                RETURN h.displayName AS displayName, i.value AS phone
                """,
                hid=human_id,
            )
            record = result.single()
            if not record:
                return False

            phone = record["phone"]
            display_name = record["displayName"]

            # Skip humans without a display name (unidentified contacts)
            if not display_name:
                logger.info(f"Skipping curiosity for {human_id[:8]}: no displayName")
                return False

            # Skip fake/test phone numbers
            if not phone or not _is_valid_signal_phone(phone):
                logger.info(f"Skipping curiosity for {human_id[:8]}: invalid phone {phone}")
                return False

        # Create the PendingQuestion node
        qid = create_question(
            human_id=human_id,
            question=question_data["question"],
            field=question_data["field"],
            qtype="profile_curiosity",
            context=question_data["context"],
            ttl_minutes=60 * 24,  # 24 hours for curiosity questions
        )

        # Send via Signal JSON-RPC
        sent = _send_signal_dm(phone, question_data["question"])

        if not sent:
            # Mark question as SEND_FAILED so it doesn't sit PENDING for 24h
            with neo4j_session() as session:
                session.run(
                    """
                    MATCH (pq:PendingQuestion {id: $qid})
                    WHERE pq.status = 'PENDING'
                    SET pq.status = 'SEND_FAILED', pq.answeredAt = datetime()
                    """,
                    qid=qid,
                )
            logger.warning(f"Signal send failed for {human_id[:8]}, marked SEND_FAILED")
            return False

        # Update lastProactiveAt on success only
        with neo4j_session() as session:
            session.run(
                "MATCH (h:Human {id: $hid}) SET h.lastProactiveAt = datetime()",
                hid=human_id,
            )

        logger.info(f"Sent curiosity question to {human_id[:8]}: {question_data['field']}")
        return True

    except Exception as e:
        logger.error(f"send_curiosity_question failed for {human_id}: {e}")
        return False


def _send_signal_dm(phone: str, message: str) -> bool:
    """Send a direct message via signal-cli JSON-RPC."""
    import requests
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "send",
        "params": {
            "account": SIGNAL_ACCOUNT,
            "message": message,
            "recipients": [phone],
        },
    }
    try:
        resp = requests.post(
            f"{SIGNAL_API_URL}/api/v1/rpc",
            json=payload,
            timeout=(5, 30),
        )
        data = resp.json()
        if "error" in data:
            logger.error(f"Signal RPC error: {data['error']}")
            return False
        return True
    except Exception as e:
        logger.error(f"Signal DM send failed: {e}")
        return False


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Curiosity Engine")
    parser.add_argument("--human", help="Human UUID to check")
    parser.add_argument("--send", action="store_true", help="Actually send a question")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.human:
        gaps = identify_knowledge_gaps(args.human)
        print(f"Gaps for {args.human[:8]}:")
        for g in gaps:
            print(f"  [{g['priority']}] {g['field']}: {g['question']}")
        print(f"Should ask now: {should_ask_now(args.human)}")

        if args.send:
            sent = send_curiosity_question(args.human)
            print(f"Sent: {sent}")
    else:
        print("Usage: python3 curiosity_engine.py --human UUID [--send]")
