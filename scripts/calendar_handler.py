#!/usr/bin/env python3
"""
Calendar Handler - Signal message intake and routing for calendar system

Receives messages from signal-cli, parses them with calendar_parser,
and executes calendar operations via neo4j_calendar.
"""

import os
import sys
import json
import subprocess
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from calendar_parser import (
    parse_message,
    resolve_datetime,
    ResolvedEvent,
    format_confirmed_event,
    format_needs_confirmation,
    format_clarification_needed,
    format_conflict,
    get_pending_confirmation,
    set_pending_confirmation,
    clear_pending_confirmation,
    get_pending_interrogation,
    set_pending_interrogation,
    clear_pending_interrogation,
    detect_missing_fields,
    format_followup_questions,
    parse_interrogation_response,
    is_affirmative,
    is_negative,
    Intent,
    DEFAULT_DURATION,
)

from profile_handler import apply_profile_hints, get_context_for_conversation, format_context_for_agent

from neo4j_calendar import (
    create_event,
    get_upcoming_events,
    get_events_for_person,
    search_events,
    get_event_attendees,
    rsvp_to_event,
    add_person_to_event,
    remove_person_from_event,
    cancel_event,
    modify_event_time,
    create_reminder,
    get_todays_events,
    get_daily_digest,
    check_time_conflicts,
    get_or_create_person,
    # Notification rules (advanced)
    create_notification_rule,
    get_event_notification_rules,
    update_notification_rule,
    delete_notification_rule,
    create_notification_instances_from_rules,
    apply_notification_preset,
)

# Signal configuration
SIGNAL_ACCOUNT = os.getenv("SIGNAL_ACCOUNT", "+15165643945")
GROUP_ID = os.getenv("SIGNAL_GROUP_ID", "BROemHVncLgSz8tReUKBz6V3BeDhDB0EXaJd+sRp6oA=")


# =============================================================================
# Message Buffer (rolling context)
# =============================================================================

class MessageBuffer:
    """Rolling buffer for recent messages in a group."""

    def __init__(self, max_size: int = 20):
        self.messages: List[Dict] = []
        self.max_size = max_size

    def add(self, sender: str, text: str, timestamp: datetime):
        """Add a message to the buffer."""
        self.messages.append({
            "sender": sender,
            "text": text,
            "timestamp": timestamp
        })
        if len(self.messages) > self.max_size:
            self.messages.pop(0)

    def recent(self, minutes: int = 30, limit: int = 5) -> List[Dict]:
        """Get recent messages from the last N minutes."""
        cutoff = datetime.now() - timedelta(minutes=minutes)
        recent = [m for m in self.messages if m["timestamp"] > cutoff]
        return recent[-limit:]


# Global buffer per group
_buffers: Dict[str, MessageBuffer] = {}


def get_buffer(group_id: str) -> MessageBuffer:
    """Get or create message buffer for a group."""
    if group_id not in _buffers:
        _buffers[group_id] = MessageBuffer()
    return _buffers[group_id]


# =============================================================================
# Signal I/O
# =============================================================================

def send_signal_message(recipient: str, message: str, is_group: bool = True):
    """Send a message via signal-cli."""
    cmd = [
        "signal-cli",
        "-a", SIGNAL_ACCOUNT,
        "send",
        "-m", message,
    ]

    if is_group:
        cmd.extend(["-g", recipient])
    else:
        cmd.append(recipient)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            print(f"Signal send error: {result.stderr}")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("Signal send timeout")
        return False
    except Exception as e:
        print(f"Signal send exception: {e}")
        return False


def send_group_message(message: str):
    """Send a message to the group."""
    return send_signal_message(GROUP_ID, message, is_group=True)


def send_dm(phone: str, message: str):
    """Send a direct message."""
    return send_signal_message(phone, message, is_group=False)


# =============================================================================
# Intent Handlers
# =============================================================================

def handle_event_create(
    parsed: Any,
    sender_phone: str,
    sender_name: str,
    group_id: str
) -> Optional[str]:
    """Handle event creation intent.

    When key fields are missing, enters an interrogation flow to gather
    complete event details before creating.
    """
    event_data = parsed.event

    # Resolve date/time (may be None if no date provided)
    resolved = resolve_datetime(
        event_data.date_text,
        event_name=event_data.name
    )

    if resolved["start"] is None or resolved["is_ambiguous"]:
        # Date is unclear — always interrogate
        missing = detect_missing_fields(event_data)
        if "date_text" not in missing:
            missing.insert(0, "date_text")
        questions = format_followup_questions(event_data, resolved)
        set_pending_interrogation(
            sender_phone, event_data, missing, sender_name, resolved
        )
        return questions or format_clarification_needed(parsed, resolved)

    # Check which fields are missing (excluding date since we resolved it)
    missing = detect_missing_fields(event_data)
    # Remove date_text from missing since we have it
    missing = [f for f in missing if f != "date_text"]

    # If key fields are missing, interrogate before creating
    # Key fields: duration, location, participants (always ask)
    # Optional fields: description, reminder_text, recurrence (ask if nothing else missing)
    key_missing = [f for f in missing if f in ("duration", "location", "participants")]

    if key_missing:
        questions = format_followup_questions(event_data, resolved)
        set_pending_interrogation(
            sender_phone, event_data, missing, sender_name, resolved
        )
        return questions

    # All key fields present — build and create/confirm event
    return _finalize_event_create(
        event_data, resolved, parsed, sender_phone, sender_name
    )


def _finalize_event_create(
    event_data: Any,
    resolved: Dict[str, Any],
    parsed: Any,
    sender_phone: str,
    sender_name: str,
) -> str:
    """Finalize event creation after all fields are gathered."""
    # Calculate end time from duration or default
    if event_data.duration_minutes:
        end_dt = resolved["start"] + timedelta(minutes=event_data.duration_minutes)
    else:
        end_dt = resolved["end"]  # Uses DEFAULT_DURATION from parser

    event = ResolvedEvent(
        name=event_data.name or "Unnamed Event",
        start_datetime=resolved["start"],
        end_datetime=end_dt,
        location=event_data.location,
        participants=[sender_name] + (event_data.participants or []),
        created_by=sender_name,
        source_message=parsed.raw_message if parsed else "",
        confidence=parsed.confidence if parsed else 0.8,
        description=event_data.description,
        recurrence=event_data.recurrence,
    )

    # Check conflicts
    conflicts = check_time_conflicts(event.start_datetime, event.end_datetime)

    if conflicts:
        set_pending_confirmation(sender_phone, event)
        return format_conflict(event, conflicts)

    # High-confidence auto-confirm, otherwise ask
    if (parsed and parsed.confidence >= 0.8 and not getattr(parsed, 'ambiguities', [])):
        create_event(
            name=event.name,
            start_datetime=event.start_datetime,
            end_datetime=event.end_datetime,
            creator_phone=sender_phone,
            description=event.description,
            location_name=event.location,
            source_message=event.source_message,
        )
        return format_confirmed_event(event)

    set_pending_confirmation(sender_phone, event)
    return format_needs_confirmation(event)


def _handle_interrogation_response(
    message: str,
    interrogation: Any,
    sender_phone: str,
    sender_name: str,
    group_id: str,
) -> Optional[str]:
    """Handle user's response to interrogation follow-up questions.

    Parses their answers, updates the event, then moves to confirmation.
    """
    # If user wants to cancel
    if is_negative(message):
        clear_pending_interrogation(sender_phone)
        return "[Calendar] OK, cancelled."

    # Parse the response to fill in missing fields
    event_data = interrogation.partial_event
    updated = parse_interrogation_response(
        message, interrogation.missing_fields, event_data
    )

    # Re-resolve date/time if it was updated
    resolved = interrogation.resolved_time
    if updated.date_text and (not resolved or resolved.get("start") is None):
        resolved = resolve_datetime(updated.date_text, event_name=updated.name)

    # If we still don't have a date, ask again
    if not resolved or resolved.get("start") is None:
        clear_pending_interrogation(sender_phone)
        return "[Calendar] I still need a date/time. When is this happening?\n(e.g. 'Friday at 7pm', 'tomorrow at noon')"

    clear_pending_interrogation(sender_phone)

    # Build the finalized event and move to confirmation
    if updated.duration_minutes:
        end_dt = resolved["start"] + timedelta(minutes=updated.duration_minutes)
    else:
        end_dt = resolved["end"]

    event = ResolvedEvent(
        name=updated.name or "Unnamed Event",
        start_datetime=resolved["start"],
        end_datetime=end_dt,
        location=updated.location,
        participants=[sender_name] + (updated.participants or []),
        created_by=sender_name,
        source_message=f"(gathered via follow-up questions)",
        confidence=0.9,
        description=updated.description,
        recurrence=updated.recurrence,
    )

    # Show full summary and ask for confirmation
    set_pending_confirmation(sender_phone, event)
    return _format_complete_summary(event, updated)


def _format_complete_summary(event: ResolvedEvent, event_data: Any = None) -> str:
    """Format a complete event summary for final confirmation."""
    lines = [
        "[Calendar] Here's what I've got:",
        f"  Event: {event.name}",
        f"  When: {event.start_datetime.strftime('%A, %B %d at %I:%M %p')}",
    ]

    duration_hours = (event.end_datetime - event.start_datetime).total_seconds() / 3600
    if duration_hours == int(duration_hours):
        lines.append(f"  Duration: {int(duration_hours)} hours")
    else:
        lines.append(f"  Duration: {duration_hours:.1f} hours")

    if event.location:
        lines.append(f"  Where: {event.location}")

    if event.participants:
        lines.append(f"  Who: {', '.join(event.participants)}")

    if event.description:
        lines.append(f"  Notes: {event.description}")

    if event_data and getattr(event_data, 'reminder_text', None):
        reminder = event_data.reminder_text
        if reminder.lower() not in ("no", "none", "skip"):
            lines.append(f"  Reminder: {reminder}")

    if event.recurrence:
        if event.recurrence.lower() not in ("no", "none", "skip"):
            lines.append(f"  Recurring: {event.recurrence}")

    lines.append("Does that look right? Reply 'yes' to confirm or 'no' to cancel.")
    return "\n".join(lines)


def handle_event_query(parsed: Any, sender_phone: str, group_id: str) -> Optional[str]:
    """Handle event query intent."""
    query_data = parsed.query

    if query_data and query_data.time_range:
        time_range = query_data.time_range.lower()

        if "weekend" in time_range:
            # Get weekend events
            events = get_upcoming_events(hours=48)
            # Filter to Saturday-Sunday
            weekend_events = []
            for e in events:
                dt = e.get("start_datetime")
                if dt and dt.weekday() >= 5:  # Saturday=5, Sunday=6
                    weekend_events.append(e)
            return format_events_list(weekend_events, "This weekend")

        elif "today" in time_range:
            events = get_todays_events()
            return format_events_list(events, "Today")

        elif "week" in time_range or "coming" in time_range:
            events = get_upcoming_events(hours=168)
            return format_events_list(events, "Coming up this week")

    # Default: show upcoming events
    events = get_upcoming_events(hours=72)
    return format_events_list(events, "Upcoming events")


def format_events_list(events: List[Dict], title: str) -> str:
    """Format a list of events for display."""
    if not events:
        return f"[Calendar] No events {title.lower()}"

    lines = [f"[Calendar] {title}:"]
    for e in events:
        dt = e.get("start_datetime")
        if dt:
            date_str = dt.strftime("%a %I:%M %p")
        else:
            date_str = "TBD"

        name = e.get("name", "Unnamed")
        location = e.get("location", {})
        loc_name = location.get("name") if location else None
        attendees = e.get("attendees", [])

        line = f"  {date_str} - {name}"
        if loc_name:
            line += f" at {loc_name}"
        if attendees:
            line += f" ({', '.join(attendees[:3])}"
            if len(attendees) > 3:
                line += f" +{len(attendees) - 3}"
            line += ")"
        lines.append(line)

    return "\n".join(lines)


def handle_rsvp(
    intent: Intent,
    parsed: Any,
    sender_phone: str,
    sender_name: str,
    group_id: str
) -> Optional[str]:
    """Handle RSVP intents."""
    event_query = parsed.event.reference_event if parsed.event else None

    if not event_query:
        # Try to find most recent event
        recent = get_upcoming_events(hours=24)
        if recent:
            event_query = recent[0].get("name", "")
        else:
            return "[Calendar] Which event? Please specify the event name."

    # Map intent to RSVP status
    rsvp_map = {
        Intent.RSVP_YES: "going",
        Intent.RSVP_NO: "declined",
        Intent.RSVP_MAYBE: "maybe",
    }
    rsvp_status = rsvp_map.get(intent, "going")

    result = rsvp_to_event(sender_phone, event_query, rsvp_status)

    if result:
        # Get attendee count
        attendees = get_event_attendees(event_query)
        going = [a for a in attendees if a.get("rsvp") == "going"]

        response = f"[Calendar] Marked you as '{rsvp_status}' for: {result['event_name']}"
        if going:
            response += f"\n  Attending: {', '.join([a['person'] for a in going[:5]])}"
        return response

    return f"[Calendar] Could not find event '{event_query}'"


def handle_add_person(
    sender_phone: str,
    sender_name: str,
    target_name: str,
    event_query: str,
    group_id: str
) -> Optional[str]:
    """Handle adding a person to an event."""
    result = add_person_to_event(sender_phone, target_name, event_query)

    if result:
        return f"[Calendar] Added {result['added']} to: {result['event_name']}"

    return f"[Calendar] Could not add {target_name} - make sure they're in the group"


def handle_cancel(
    sender_phone: str,
    parsed: Any,
    group_id: str
) -> Optional[str]:
    """Handle event cancellation."""
    event_query = parsed.event.reference_event if parsed.event else None

    if not event_query:
        return "[Calendar] Which event to cancel? Please specify."

    result = cancel_event(sender_phone, event_query)

    if result:
        return f"[Calendar] Cancelled: {result['event_name']} ({result['starts'].strftime('%a %I:%M %p')})"

    return "[Calendar] Could not cancel - only the creator can cancel an event"


def handle_remind(
    sender_phone: str,
    parsed: Any,
    group_id: str
) -> Optional[str]:
    """Handle reminder creation."""
    event_query = parsed.event.reference_event if parsed.event else None

    if not event_query:
        return "[Calendar] Which event should I remind you about?"

    # Parse offset from date_text
    offset_text = parsed.event.date_text if parsed.event else "1 hour before"

    # Simple offset parsing
    offset_map = {
        "1 hour": timedelta(hours=1),
        "2 hour": timedelta(hours=2),
        "3 hour": timedelta(hours=3),
        "1 day": timedelta(days=1),
        "morning": timedelta(hours=-8),  # 8 AM on the day
    }

    offset = timedelta(hours=1)  # Default
    for key, val in offset_map.items():
        if key in offset_text.lower():
            offset = val
            break

    # Find event to get start time
    events = search_events(event_query, limit=1)
    if not events:
        return f"[Calendar] Could not find event '{event_query}'"

    event = events[0]
    start_time = event.get("start_datetime")

    if offset < timedelta(0):
        # "Morning of" - set to 8 AM on the day
        remind_at = start_time.replace(hour=8, minute=0)
        offset_desc = "morning of"
    else:
        remind_at = start_time - offset
        offset_desc = offset_text

    result = create_reminder(sender_phone, event_query, remind_at, offset_desc)

    if result:
        return f"[Calendar] Reminder set: {result['event_name']}\n  I'll ping you at {remind_at.strftime('%I:%M %p')}"

    return "[Calendar] Could not create reminder"


def handle_notification_rule(
    sender_phone: str,
    message: str,
    group_id: str
) -> Optional[str]:
    """Handle advanced notification rule creation.

    Supports patterns like:
    - "notify me 15 min before dinner"
    - "set escalating reminders for the meeting"
    - "remind me with travel presets for the trip"
    - "add 3 notifications before the deadline"
    """
    # Find event from message
    event_query = None
    for word in message.split():
        if word[0].isupper():
            event_query = word
            break

    if not event_query:
        # Try most recent event
        recent = get_upcoming_events(hours=24)
        if recent:
            event_query = recent[0].get("name", "")
        else:
            return "[Calendar] Which event? Please specify the event name."

    # Find event to get event_id
    events = search_events(event_query, limit=1)
    if not events:
        return f"[Calendar] Could not find event '{event_query}'"

    event = events[0]
    event_id = event.get("event_id", "")

    # Detect preset type from keywords
    message_lower = message.lower()
    if "travel" in message_lower or "trip" in message_lower:
        preset = "travel"
    elif "deadline" in message_lower or "due" in message_lower:
        preset = "deadline"
    elif "escalat" in message_lower:
        preset = "deadline"  # Escalating = deadline preset
    elif "meeting" in message_lower:
        preset = "meeting"
    else:
        preset = "meeting"  # Default

    # Apply preset
    result = apply_notification_preset(event_id, sender_phone, preset)

    if result and "rules" in result:
        rules_count = len(result.get("rules", []))
        notifs_count = len(result.get("notifications", []))
        return f"[Calendar] Added {rules_count} notification rule(s) ({notifs_count} alerts) for {event_query} using {preset} template"

    return "[Calendar] Could not create notification rules"


def handle_person_query(person_name: str) -> Optional[str]:
    """Handle 'what is X going to?' queries."""
    events = get_events_for_person(person_name)

    if not events:
        return f"[Calendar] {person_name} has no upcoming events"

    lines = [f"[Calendar] {person_name} is going to:"]
    for e in events:
        dt = e.get("start_datetime")
        date_str = dt.strftime("%a %I:%M %p") if dt else "TBD"
        name = e.get("name", "Unnamed")
        lines.append(f"  {date_str} - {name}")

    return "\n".join(lines)


# =============================================================================
# Main Handler
# =============================================================================

def handle_message(
    raw_msg: Dict[str, Any]
) -> Optional[str]:
    """
    Main entry point for processing Signal messages.

    Args:
        raw_msg: Dict with keys: message, sender, sender_name, group_id, timestamp

    Returns:
        Response message or None if no response needed
    """
    message = raw_msg.get("message", "")
    sender_phone = raw_msg.get("sender", "")
    sender_name = raw_msg.get("sender_name", sender_phone)
    group_id = raw_msg.get("group_id", GROUP_ID)
    timestamp = raw_msg.get("timestamp", datetime.now())

    # Add to message buffer
    buffer = get_buffer(group_id)
    buffer.add(sender_name, message, timestamp)

    # Ensure sender exists in Neo4j
    get_or_create_person(sender_phone, sender_name)

    # Load sender's profile context for this conversation
    sender_context = {}
    try:
        context_map = get_context_for_conversation([sender_phone])
        sender_context = context_map.get(sender_phone, {})
    except Exception:
        pass

    # Attach context to raw_msg for downstream handlers
    raw_msg["_sender_context"] = sender_context
    raw_msg["_context_block"] = format_context_for_agent(sender_context)

    # Use preferred name if available
    if sender_context.get("name"):
        sender_name = sender_context["name"]

    # Extract and apply any chat preference hints from the message
    try:
        preference_response = apply_profile_hints(sender_phone, message)
    except Exception:
        preference_response = None

    # Track interaction timestamp (lightweight — fire and forget)
    try:
        from neo4j_human_profile import HumanProfileStore
        import json as _json
        _store = HumanProfileStore()
        _profile = _store.get_profile_by_phone(sender_phone)
        if _profile:
            _pc = _profile.get("personal_context", {})
            if not isinstance(_pc, dict):
                _pc = {}
            _pc["interaction_count"] = (_pc.get("interaction_count") or 0) + 1
            _pc["last_interaction"] = datetime.now().isoformat()
            if not _pc.get("first_interaction"):
                _pc["first_interaction"] = datetime.now().isoformat()
            _store.update_field(sender_phone, "personal_context", _pc)
        _store.close()
    except Exception:
        pass  # Never block message processing for tracking

    # Check for pending interrogation first (follow-up questions)
    interrogation = get_pending_interrogation(sender_phone)
    if interrogation:
        return _handle_interrogation_response(
            message, interrogation, sender_phone, sender_name, group_id
        )

    # Check for pending confirmation
    pending = get_pending_confirmation(sender_phone)
    if pending:
        if is_affirmative(message):
            # Confirm and create
            event = pending.resolved_event
            create_event(
                name=event.name,
                start_datetime=event.start_datetime,
                end_datetime=event.end_datetime,
                creator_phone=sender_phone,
                description=event.description,
                location_name=event.location,
                source_message=event.source_message,
            )
            clear_pending_confirmation(sender_phone)
            return format_confirmed_event(event)

        elif is_negative(message):
            clear_pending_confirmation(sender_phone)
            return "[Calendar] OK, cancelled."

        # Otherwise, treat as new message (pending will expire)

    # Parse the message
    recent_context = buffer.recent(minutes=30, limit=5)
    parsed = parse_message(message, sender_name, recent_context)

    # Route by intent
    if parsed.intent == Intent.NOT_CALENDAR:
        return None

    elif parsed.intent == Intent.EVENT_QUERY:
        return handle_event_query(parsed, sender_phone, group_id)

    elif parsed.intent == Intent.EVENT_CREATE:
        return handle_event_create(parsed, sender_phone, sender_name, group_id)

    elif parsed.intent in [Intent.RSVP_YES, Intent.RSVP_NO, Intent.RSVP_MAYBE]:
        return handle_rsvp(parsed.intent, parsed, sender_phone, sender_name, group_id)

    elif parsed.intent == Intent.EVENT_CANCEL:
        return handle_cancel(sender_phone, parsed, group_id)

    elif parsed.intent == Intent.EVENT_REMIND:
        return handle_remind(sender_phone, parsed, group_id)

    # Check for advanced notification rule patterns
    if any(kw in message.lower() for kw in ["notify me", "set reminder", "add notification", "set alert"]):
        return handle_notification_rule(sender_phone, message, group_id)

    # Check for "add X to Y" pattern
    if "add" in message.lower() and "to" in message.lower():
        # Extract names (simple pattern matching)
        parts = message.lower().split("add")
        if len(parts) > 1:
            rest = parts[1].split("to")
            if len(rest) > 1:
                target_name = rest[0].strip().title()
                event_query = rest[1].strip()
                return handle_add_person(sender_phone, sender_name, target_name, event_query, group_id)

    # Check for person query pattern "what is X going to"
    if "going to" in message.lower() or "what is" in message.lower():
        # Extract person name
        for word in message.split():
            if word[0].isupper() and word.lower() not in ["what", "is", "going", "to"]:
                return handle_person_query(word.rstrip("?,."))

    # Check for "who is coming to [event]" pattern
    if "who" in message.lower() and ("coming" in message.lower() or "going" in message.lower()):
        # Extract event name after "to" or "at"
        msg_lower = message.lower()
        for prefix in ["coming to ", "going to ", "coming ", "rsvp'd for ", "rsvp for "]:
            if prefix in msg_lower:
                event_query = msg_lower.split(prefix, 1)[1].strip().rstrip("?!.")
                return handle_who_is_coming(event_query)

    # If no calendar intent but we detected preference hints, acknowledge them
    if preference_response:
        return preference_response

    return None


def handle_who_is_coming(event_query: str) -> Optional[str]:
    """Handle 'who is coming to [event]' queries."""
    attendees = get_event_attendees(event_query)

    if not attendees:
        return f"[Calendar] No attendees found for '{event_query}'"

    going = [a for a in attendees if a.get("rsvp") == "going"]
    maybe = [a for a in attendees if a.get("rsvp") == "maybe"]
    declined = [a for a in attendees if a.get("rsvp") == "declined"]

    lines = [f"[Calendar] Attendees for '{event_query}':"]

    if going:
        lines.append(f"  Going: {', '.join([a['person'] for a in going])}")
    if maybe:
        lines.append(f"  Maybe: {', '.join([a['person'] for a in maybe])}")
    if declined:
        lines.append(f"  Declined: {', '.join([a['person'] for a in declined])}")

    return "\n".join(lines)


# =============================================================================
# CLI Interface (for testing)
# =============================================================================

if __name__ == "__main__":
    print("Calendar Handler - Test Mode")
    print("Enter messages to process (or 'quit' to exit)\n")

    while True:
        try:
            line = input("> ").strip()
            if line.lower() in ("quit", "exit"):
                break

            # Simulate a message
            raw_msg = {
                "message": line,
                "sender": "+19194133445",
                "sender_name": "Danny",
                "group_id": GROUP_ID,
                "timestamp": datetime.now(),
            }

            response = handle_message(raw_msg)
            if response:
                print(f"\n{response}\n")

        except EOFError:
            break
        except Exception as e:
            print(f"Error: {e}")
