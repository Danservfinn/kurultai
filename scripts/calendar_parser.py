#!/usr/bin/env python3
"""
Calendar Parser - LLM classification + date/time resolution for Signal calendar

Uses Claude Code sessions for intent classification + entity extraction,
then dateparser for deterministic datetime resolution.

Replaces previous direct OpenRouter API calls with local Claude Code sessions.
"""

import os
import sys
import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field

import dateparser

# Import Claude Code LLM client (replaces direct OpenRouter API)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from calendar_llm_client import parse_with_claude_code, is_claude_code_available

LOCAL_TZ = ZoneInfo("America/New_York")
DEFAULT_DURATION = timedelta(hours=2)


# =============================================================================
# Intent Types
# =============================================================================

class Intent(str, Enum):
    EVENT_CREATE = "event_create"
    EVENT_QUERY = "event_query"
    RSVP_YES = "event_rsvp_yes"
    RSVP_NO = "event_rsvp_no"
    RSVP_MAYBE = "event_rsvp_maybe"
    EVENT_MODIFY = "event_modify"
    EVENT_CANCEL = "event_cancel"
    EVENT_REMIND = "event_remind"
    NOT_CALENDAR = "not_calendar"


# =============================================================================
# Pydantic Models
# =============================================================================

class EventExtraction(BaseModel):
    name: Optional[str] = None
    date_text: Optional[str] = None
    location: Optional[str] = None
    duration_minutes: Optional[int] = None
    participants: List[str] = Field(default_factory=list)
    reference_event: Optional[str] = None
    description: Optional[str] = None
    reminder_text: Optional[str] = None
    recurrence: Optional[str] = None
    # --- Enriched fields ---
    cost: Optional[str] = None
    dress_code: Optional[str] = None
    what_to_bring: Optional[str] = None
    category: Optional[str] = None
    vibe: Optional[str] = None
    indoor_outdoor: Optional[str] = None
    event_url: Optional[str] = None
    ticket_url: Optional[str] = None
    dietary_notes: Optional[str] = None


class QueryExtraction(BaseModel):
    time_range: Optional[str] = None
    filter: Optional[str] = None


class ParsedMessage(BaseModel):
    intent: Intent
    confidence: float = Field(ge=0.0, le=1.0)
    event: Optional[EventExtraction] = None
    query: Optional[QueryExtraction] = None
    ambiguities: List[str] = Field(default_factory=list)
    sender: str = ""
    raw_message: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(LOCAL_TZ))


class ResolvedEvent(BaseModel):
    name: str
    start_datetime: datetime
    end_datetime: datetime
    location: Optional[str] = None
    participants: List[str] = Field(default_factory=list)
    reminders: List[datetime] = Field(default_factory=list)
    created_by: str = ""
    source_message: str = ""
    confidence: float = 1.0
    description: Optional[str] = None
    recurrence: Optional[str] = None


# =============================================================================
# LLM System Prompt
# =============================================================================

SYSTEM_PROMPT = """You are a calendar assistant parsing messages from a group chat.

Given a message and recent chat context, respond with JSON only. No explanation.

Schema:
{
  "intent": "event_create" | "event_query" | "event_rsvp_yes" | "event_rsvp_no" |
            "event_rsvp_maybe" | "event_modify" | "event_cancel" | "event_remind" |
            "not_calendar",
  "confidence": 0.0-1.0,
  "event": {
    "name": "string or null",
    "date_text": "string or null",
    "location": "string or null",
    "duration_minutes": int or null,
    "participants": ["string"] or [],
    "reference_event": "string or null",
    "cost": "string or null (ticket price, 'free', '$20')",
    "dress_code": "string or null (casual, smart casual, formal, costume)",
    "what_to_bring": "string or null",
    "category": "dinner|birthday|meeting|concert|hike|game_night|wedding|workout|travel|holiday|other or null",
    "vibe": "casual|formal|chill|high_energy|intimate or null",
    "indoor_outdoor": "indoor|outdoor|both or null",
    "event_url": "URL or null",
    "ticket_url": "URL or null",
    "dietary_notes": "string or null"
  },
  "query": {
    "time_range": "string or null",
    "filter": "string or null"
  },
  "ambiguities": ["string"]
}

Rules:
- "I'm in" / "count me in" ALONE with no event mentioned = not_calendar (need reference event)
- "I'm in for [event]" with explicit event name = event_rsvp_yes with reference_event set
- "I'm in" following an event creation = event_rsvp_yes referencing that event
- "Can't make it", "not going", "decline", "skip", "no", "nope", "nah" = event_rsvp_no
- "Maybe", "not sure", "might" = event_rsvp_maybe
- If the message contains multiple events, return the primary one and note others in ambiguities
- confidence < 0.6 = flag for confirmation
- Default duration is null (caller will apply 2-hour default)
- Participants are first names only as mentioned in the message
- For RSVP/modify/cancel, reference_event should match the most recent relevant event name
- Infer category from context: "birthday dinner" → category=birthday, "standup" → category=meeting
- Infer vibe from category if not explicit: meeting→formal, hike→casual, concert→high_energy
- Extract URLs mentioned in the message
- "bring X" → what_to_bring
- "$20" or "free" or "tickets" → cost
- "casual" / "dress up" / "black tie" → dress_code
"""


# =============================================================================
# LLM Classification (via Claude Code sessions)
# =============================================================================

def parse_message(
    message: str,
    sender: str,
    recent_context: List[Dict] = None,
) -> ParsedMessage:
    """
    Single LLM call: classify intent + extract entities.
    Uses Claude Code sessions instead of direct OpenRouter API.

    Args:
        message: The message text to parse
        sender: Name or phone of sender
        recent_context: List of recent messages for context (last 5)

    Returns:
        ParsedMessage with intent, confidence, and extracted entities
    """
    try:
        # Use Claude Code for LLM classification
        result = parse_with_claude_code(
            message=message,
            sender=sender,
            recent_context=recent_context,
            timeout=90,  # 90s timeout to allow for Claude Code startup + API call
        )

        event_data = result.get("event")
        event = EventExtraction(**event_data) if event_data else None

        query_data = result.get("query")
        query = QueryExtraction(**query_data) if query_data else None

        parsed = ParsedMessage(
            intent=Intent(result.get("intent", "not_calendar")),
            confidence=float(result.get("confidence", 0.5)),
            event=event,
            query=query,
            ambiguities=result.get("ambiguities", []),
            sender=sender,
            raw_message=message,
        )
        return parsed

    except Exception as e:
        # LLM failed - use rule-based fallback parser
        return _rule_based_parse(message, sender)


# =============================================================================
# Rule-Based Fallback Parser (when LLM is unavailable)
# =============================================================================

# Common patterns for rule-based parsing
_EVENT_PATTERNS = [
    # "Dinner at Mario's Friday 7pm" -> event name + location + time
    re.compile(r"(.+?)\s+(?:at|@)\s+(.+?)\s+(?:on\s+)?(.+)", re.IGNORECASE),
    # "Meeting tomorrow at 3pm"
    re.compile(r"(.+?)\s+(?:on\s+|this\s+|next\s+)?(.+?)(?:\s+at\s+(.+))?$", re.IGNORECASE),
    # "Friday 7pm dinner"
    re.compile(r"(.+?)\s+(.+)$", re.IGNORECASE),
]

_RSVP_YES_PATTERNS = [
    re.compile(r"^\s*(yes|yeah|yep|sure|ok|going)\s*$", re.IGNORECASE),
    re.compile(r"(I'm\s+in|count\s+me\s+in)", re.IGNORECASE),
]

_RSVP_NO_PATTERNS = [
    re.compile(r"^\s*(no|nope|nah|not\s+going|decline|skip)\s*$", re.IGNORECASE),
    re.compile(r"can't\s+make\s+it", re.IGNORECASE),
    re.compile(r"can['']t\s+make\s+it", re.IGNORECASE),
]

_RSVP_MAYBE_PATTERNS = [
    re.compile(r"^(maybe|perhaps|might|possibly|not\s+sure)$", re.IGNORECASE),
]

_QUERY_PATTERNS = [
    re.compile(r"(what|what's|whats)\s+(?:is\s+)?(?:happening|going\s+on|up|coming)", re.IGNORECASE),
    re.compile(r"(show|list|get)\s+(?:me\s+)?(?:the\s+)?(?:events|calendar|schedule)", re.IGNORECASE),
    re.compile(r"(this\s+weekend|today|tomorrow|this\s+week|next\s+week)", re.IGNORECASE),
    re.compile(r"who\s+(?:is\s+)?(?:coming|going|attending|rsvp'd)", re.IGNORECASE),
]

_CANCEL_PATTERNS = [
    re.compile(r"(cancel|delete|remove|call\s+off)\s+(?:the\s+)?(.+)", re.IGNORECASE),
]

_REMIND_PATTERNS = [
    re.compile(r"(remind|reminder|ping)\s+(?:me\s+)?(?:about\s+)?(.+)", re.IGNORECASE),
]

_ADD_PERSON_PATTERNS = [
    re.compile(r"add\s+(.+?)\s+(?:to\s+)?(.+)", re.IGNORECASE),
    re.compile(r"\+@?(\w+)", re.IGNORECASE),
]

_DATE_KEYWORDS = [
    "today", "tonight", "tomorrow", "this weekend", "next week",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "mon", "tue", "wed", "thu", "fri", "sat", "sun",
    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
]

_TIME_PATTERN = re.compile(r"(\d{1,2}):?(\d{2})?\s*(am|pm)?", re.IGNORECASE)


def _rule_based_parse(message: str, sender: str) -> ParsedMessage:
    """
    Rule-based parser for when LLM is unavailable.
    Handles common calendar patterns without API calls.
    """
    msg_lower = message.lower().strip()

    # Check for RSVP patterns first (simple yes/no)
    for pattern in _RSVP_YES_PATTERNS:
        match = pattern.match(message)
        if match:
            ref_event = match.group(2) if match.lastindex and match.lastindex >= 2 else None
            return ParsedMessage(
                intent=Intent.RSVP_YES,
                confidence=0.7,
                event=EventExtraction(reference_event=ref_event),
                sender=sender,
                raw_message=message,
            )

    # Check for RSVP no
    for pattern in _RSVP_NO_PATTERNS:
        if pattern.match(message):
            return ParsedMessage(
                intent=Intent.RSVP_NO,
                confidence=0.7,
                sender=sender,
                raw_message=message,
            )

    # Check for RSVP maybe
    for pattern in _RSVP_MAYBE_PATTERNS:
        if pattern.match(message):
            return ParsedMessage(
                intent=Intent.RSVP_MAYBE,
                confidence=0.7,
                sender=sender,
                raw_message=message,
            )

    # Check for query patterns
    for pattern in _QUERY_PATTERNS:
        if pattern.search(message):
            # Extract time range from query
            time_range = None
            if "this weekend" in msg_lower:
                time_range = "this weekend"
            elif "today" in msg_lower:
                time_range = "today"
            elif "tomorrow" in msg_lower:
                time_range = "tomorrow"
            elif "week" in msg_lower:
                time_range = "this week"

            return ParsedMessage(
                intent=Intent.EVENT_QUERY,
                confidence=0.75,
                query=QueryExtraction(time_range=time_range),
                sender=sender,
                raw_message=message,
            )

    # Check for cancel patterns
    for pattern in _CANCEL_PATTERNS:
        match = pattern.match(message)
        if match:
            ref_event = match.group(2) if match.lastindex >= 2 else None
            return ParsedMessage(
                intent=Intent.EVENT_CANCEL,
                confidence=0.75,
                event=EventExtraction(reference_event=ref_event),
                sender=sender,
                raw_message=message,
            )

    # Check for remind patterns
    for pattern in _REMIND_PATTERNS:
        match = pattern.match(message)
        if match:
            ref_event = match.group(2) if match.lastindex >= 2 else None
            return ParsedMessage(
                intent=Intent.EVENT_REMIND,
                confidence=0.7,
                event=EventExtraction(reference_event=ref_event, date_text="1 hour before"),
                sender=sender,
                raw_message=message,
            )

    # Check for event creation patterns
    # Look for date/time keywords
    has_date = any(kw in msg_lower for kw in _DATE_KEYWORDS)
    has_time = _TIME_PATTERN.search(message) is not None

    if has_date or has_time:
        # Try to extract event name and date/time
        event_name = _extract_event_name(message)
        date_text = _extract_date_text(message)
        location = _extract_location(message)

        if event_name:
            return ParsedMessage(
                intent=Intent.EVENT_CREATE,
                confidence=0.65,  # Lower confidence for rule-based
                event=EventExtraction(
                    name=event_name,
                    date_text=date_text,
                    location=location,
                ),
                sender=sender,
                raw_message=message,
            )

    # Default: not calendar
    return ParsedMessage(
        intent=Intent.NOT_CALENDAR,
        confidence=0.5,
        sender=sender,
        raw_message=message,
    )


def _extract_event_name(message: str) -> Optional[str]:
    """Extract event name from message."""
    # Remove common time/date patterns
    cleaned = message

    # Remove time patterns like "7pm", "7:30pm", "at 7"
    cleaned = _TIME_PATTERN.sub("", cleaned)

    # Remove date keywords
    for kw in _DATE_KEYWORDS:
        cleaned = re.sub(rf'\b{kw}\b', '', cleaned, flags=re.IGNORECASE)

    # Remove prepositions and connecting words
    for word in [" at ", " on ", " for ", " this ", " next ", " with ", " in "]:
        cleaned = cleaned.replace(word, " ")

    # Clean up and return
    cleaned = cleaned.strip().strip(",.!?")
    return cleaned if len(cleaned) > 1 else None


def _extract_date_text(message: str) -> str:
    """Extract date/time portion from message."""
    # Find date keywords
    msg_lower = message.lower()
    for kw in _DATE_KEYWORDS:
        if kw in msg_lower:
            return kw

    # Find time patterns
    time_match = _TIME_PATTERN.search(message)
    if time_match:
        return time_match.group(0)

    return ""


def _extract_location(message: str) -> Optional[str]:
    """Extract location from 'at location' pattern."""
    match = re.search(r"\bat\s+([^,]+?)(?:\s+(?:on|at|this|next)\s+|\s*$)", message, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


# =============================================================================
# Date/Time Resolution
# =============================================================================

def _is_weekend_reference(text: str) -> bool:
    """Check if text refers to 'this weekend'."""
    return "weekend" in text.lower()


def _next_weekday(dt: datetime, weekday: int) -> datetime:
    """Get the next occurrence of a weekday (0=Monday, 6=Sunday)."""
    days_ahead = weekday - dt.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return dt + timedelta(days=days_ahead)


def _detect_ambiguity(date_text: str, parsed: datetime, reference: datetime) -> bool:
    """Detect if the date resolution is ambiguous."""
    text_lower = date_text.lower().strip()

    # Known ambiguous patterns
    ambiguous_patterns = [
        "next week", "sometime", "later", "soon", "whenever",
        "one day", "some day", "maybe", "perhaps"
    ]

    return any(p in text_lower for p in ambiguous_patterns)


def _generate_alternatives(date_text: str, primary: datetime) -> List[datetime]:
    """Generate alternative interpretations for ambiguous dates."""
    # For now, just return empty - could be enhanced
    return []


def apply_ampm_heuristic(hour: int, event_name: str = "") -> int:
    """For bare hour numbers, infer AM/PM from event context."""
    morning_events = {"breakfast", "brunch", "coffee", "run", "hike", "yoga", "morning"}
    name_lower = (event_name or "").lower()

    if any(kw in name_lower for kw in morning_events):
        return hour  # Keep as AM

    # Social default: bare hours 1-6 are PM
    if 1 <= hour <= 6:
        return hour + 12

    # 7-11: default PM for social, unless morning keyword
    if 7 <= hour <= 11:
        return hour

    return hour


def resolve_datetime(
    date_text: str,
    reference_time: datetime = None,
    event_name: str = None
) -> Dict[str, Any]:
    """
    Resolve a date string to an absolute datetime.

    Args:
        date_text: The raw date text from LLM extraction
        reference_time: The reference time for resolution (default: now)
        event_name: Event name for AM/PM heuristics

    Returns:
        Dict with start, end, is_ambiguous, interpretation, alternatives
    """
    if reference_time is None:
        reference_time = datetime.now(LOCAL_TZ)

    if not date_text:
        return {
            "start": None,
            "end": None,
            "is_ambiguous": True,
            "interpretation": "No date specified",
            "alternatives": []
        }

    # Special pattern: "this weekend"
    if _is_weekend_reference(date_text):
        sat = _next_weekday(reference_time, 5)  # Saturday
        sun = sat + timedelta(days=1)
        return {
            "start": sat.replace(hour=10, minute=0, tzinfo=LOCAL_TZ),
            "end": sun.replace(hour=18, minute=0, tzinfo=LOCAL_TZ),
            "is_ambiguous": False,
            "interpretation": f"This weekend: {sat.strftime('%b %d')} - {sun.strftime('%b %d')}",
            "alternatives": []
        }

    # Special pattern: "tonight"
    if date_text.strip().lower() == "tonight":
        tonight = reference_time.replace(hour=19, minute=0, second=0, tzinfo=LOCAL_TZ)
        return {
            "start": tonight,
            "end": tonight + DEFAULT_DURATION,
            "is_ambiguous": False,
            "interpretation": "Tonight at 7:00 PM",
            "alternatives": []
        }

    # Use dateparser for everything else
    settings = {
        'PREFER_DATES_FROM': 'future',
        'PREFER_DAY_OF_MONTH': 'first',
        'RELATIVE_BASE': reference_time.replace(tzinfo=None),
        'RETURN_AS_TIMEZONE_AWARE': False,
        'TIMEZONE': 'America/New_York',
    }

    parsed = dateparser.parse(date_text, settings=settings)

    if parsed is None:
        return {
            "start": None,
            "end": None,
            "is_ambiguous": True,
            "interpretation": f"Could not parse: '{date_text}'",
            "alternatives": []
        }

    # Localize the result
    start = parsed.replace(tzinfo=LOCAL_TZ)

    # Apply AM/PM heuristic if hour was bare
    if parsed.hour and 1 <= parsed.hour <= 12:
        new_hour = apply_ampm_heuristic(parsed.hour, event_name)
        start = start.replace(hour=new_hour)

    # Detect ambiguity
    ambiguous = _detect_ambiguity(date_text, start, reference_time)

    return {
        "start": start,
        "end": start + DEFAULT_DURATION,
        "is_ambiguous": ambiguous,
        "interpretation": f"{start.strftime('%A, %B %d at %I:%M %p %Z')}",
        "alternatives": _generate_alternatives(date_text, start) if ambiguous else []
    }


# =============================================================================
# Confirmation Message Generation
# =============================================================================

def format_confirmed_event(event: ResolvedEvent, enriched: Dict[str, Any] = None) -> str:
    """Format a confirmed event message."""
    lines = [
        "[Calendar] Got it!",
        f"  {event.name}",
        f"  {event.start_datetime.strftime('%A, %B %d at %I:%M %p')}",
    ]
    if event.location:
        lines.append(f"  Location: {event.location}")
    duration_hours = (event.end_datetime - event.start_datetime).total_seconds() / 3600
    lines.append(f"  Duration: {int(duration_hours)} hours")
    # Show enriched fields if provided
    if enriched:
        if enriched.get("category"):
            lines.append(f"  Type: {enriched['category']}")
        if enriched.get("dress_code"):
            lines.append(f"  Dress: {enriched['dress_code']}")
        if enriched.get("cost"):
            lines.append(f"  Cost: {enriched['cost']}")
        if enriched.get("what_to_bring"):
            lines.append(f"  Bring: {enriched['what_to_bring']}")
        if enriched.get("indoor_outdoor"):
            lines.append(f"  Setting: {enriched['indoor_outdoor']}")
        if enriched.get("vibe"):
            lines.append(f"  Vibe: {enriched['vibe']}")
    lines.append("React with thumbs up to join, thumbs down to skip.")
    return "\n".join(lines)


def format_needs_confirmation(event: ResolvedEvent) -> str:
    """Format a message asking for confirmation."""
    lines = [
        "[Calendar] I think you want to create:",
        f"  {event.name}",
        f"  {event.start_datetime.strftime('%A, %B %d at %I:%M %p')}",
    ]
    if event.location:
        lines.append(f"  Location: {event.location}")
    lines.append("Does that look right? Reply 'yes' to confirm or correct me.")
    return "\n".join(lines)


def format_clarification_needed(parsed: ParsedMessage, resolved: Dict) -> str:
    """Format a message asking for clarification."""
    lines = ["[Calendar] Not sure I caught that."]
    if resolved.get("interpretation"):
        lines.append(f"  You mentioned: {resolved['interpretation']}")
    if parsed.ambiguities:
        lines.append(f"  Issues: {', '.join(parsed.ambiguities)}")
    lines.append("Try something like: 'Dinner at Mario's, Friday at 7pm'")
    return "\n".join(lines)


def format_conflict(event: ResolvedEvent, conflicts: List[Dict]) -> str:
    """Format a conflict warning message."""
    lines = ["[Calendar] Heads up -- you already have:"]
    for c in conflicts:
        lines.append(f"  {c['event_name']} ({c['starts'].strftime('%I:%M %p')})")
    lines.append("Create anyway? Reply 'yes' to confirm.")
    return "\n".join(lines)


# =============================================================================
# Missing Field Detection & Interrogation
# =============================================================================

# Fields to check, in order of importance
INTERROGATION_FIELDS = [
    "date_text",      # When?
    "name",           # What event?
    "duration",       # How long?
    "location",       # Where?
    "participants",   # Who else?
    "category",       # What kind of event?
    "indoor_outdoor", # Indoor or outdoor?
    "cost",           # Any cost?
    "what_to_bring",  # Anything to bring?
    "description",    # Any details?
    "reminder_text",  # Want a reminder?
    "recurrence",     # Is this recurring?
]

# Questions mapped to each missing field
FIELD_QUESTIONS = {
    "name": "What should I call this event?",
    "date_text": "When is this happening?",
    "duration": "How long will it be? (default: 2 hours)",
    "location": "Where is it?",
    "participants": "Anyone else coming?",
    "category": "What kind of event is this? (dinner, birthday, meeting, concert, hike, etc.)",
    "indoor_outdoor": "Indoor or outdoor?",
    "cost": "Any cost? (e.g. '$20', 'free', 'BYOB')",
    "what_to_bring": "Should people bring anything?",
    "description": "Any details to add? (optional, reply 'skip')",
    "reminder_text": "Want a reminder? When? (e.g. '1 hour before', or 'no')",
    "recurrence": "Is this recurring? (e.g. 'weekly', 'monthly', or 'no')",
}


def detect_missing_fields(event: EventExtraction) -> List[str]:
    """Detect which important fields are missing from a parsed event."""
    missing = []

    if not event.name:
        missing.append("name")
    if not event.date_text:
        missing.append("date_text")
    if event.duration_minutes is None:
        missing.append("duration")
    if not event.location:
        missing.append("location")
    if not event.participants:
        missing.append("participants")
    if not event.description:
        missing.append("description")
    if not event.reminder_text:
        missing.append("reminder_text")
    if not event.recurrence:
        missing.append("recurrence")
    # Enriched fields (only asked if not already provided)
    if not event.category:
        missing.append("category")
    if not event.indoor_outdoor:
        missing.append("indoor_outdoor")
    if not event.cost:
        missing.append("cost")
    if not event.what_to_bring:
        missing.append("what_to_bring")

    return missing


def format_followup_questions(
    event: EventExtraction,
    resolved_time: Optional[Dict[str, Any]] = None,
) -> str:
    """Format a friendly message asking follow-up questions for missing fields.

    Returns the interrogation message with what we know and what we need.
    """
    missing = detect_missing_fields(event)

    # Build "here's what I got" summary
    known_parts = []
    if event.name:
        known_parts.append(event.name)
    if event.date_text:
        if resolved_time and resolved_time.get("interpretation"):
            known_parts.append(resolved_time["interpretation"])
        else:
            known_parts.append(event.date_text)
    if event.location:
        known_parts.append(f"at {event.location}")

    if known_parts:
        summary = f"[Calendar] Got it! {' — '.join(known_parts)}."
    else:
        summary = "[Calendar] Let me help you create an event."

    # Only ask about genuinely missing fields (skip name/date if we have them)
    questions_to_ask = []
    for field in INTERROGATION_FIELDS:
        if field in missing:
            questions_to_ask.append(f"- {FIELD_QUESTIONS[field]}")

    if not questions_to_ask:
        return ""  # Nothing missing

    lines = [summary, "A few quick questions:"] + questions_to_ask
    lines.append("(Reply with answers, or 'skip' for any you want to leave blank)")

    return "\n".join(lines)


def parse_interrogation_response(
    response: str,
    missing_fields: List[str],
    event: EventExtraction,
) -> EventExtraction:
    """Parse a user's freeform reply to interrogation questions.

    Updates the event extraction with any answered fields.
    """
    text = response.strip()
    text_lower = text.lower()

    # If user says just "skip" or "done", return event as-is
    if text_lower in ("skip", "done", "no", "nah", "none"):
        return event

    # Split response into lines for multi-answer parsing
    lines = [l.strip().lstrip("-•* ") for l in text.split("\n") if l.strip()]

    # Track which fields we've filled by matching lines to questions in order
    field_idx = 0
    remaining_fields = list(missing_fields)

    for line in lines:
        line_lower = line.lower().strip()

        # Skip empty or "skip" lines
        if not line_lower or line_lower in ("skip", "n/a", "na", "-", "none"):
            if remaining_fields:
                remaining_fields.pop(0)
            continue

        if not remaining_fields:
            break

        field = remaining_fields.pop(0)
        _apply_field_answer(event, field, line)

    # If single-line response with multiple fields still missing, try heuristic parsing
    if len(lines) == 1 and len(missing_fields) > 1:
        _parse_single_line_response(event, text, missing_fields)

    return event


def _apply_field_answer(event: EventExtraction, field: str, answer: str):
    """Apply a single answer to the appropriate field on the event."""
    answer_clean = answer.strip()
    answer_lower = answer_clean.lower()

    # Skip negative/empty answers
    if answer_lower in ("skip", "no", "none", "n/a", "na", "nope", "nah", ""):
        return

    if field == "name":
        event.name = answer_clean
    elif field == "date_text":
        event.date_text = answer_clean
    elif field == "duration":
        event.duration_minutes = _parse_duration_text(answer_clean)
    elif field == "location":
        event.location = answer_clean
    elif field == "participants":
        # Split by commas or "and"
        names = re.split(r'[,&]|\band\b', answer_clean)
        event.participants = [n.strip() for n in names if n.strip()]
    elif field == "description":
        event.description = answer_clean
    elif field == "reminder_text":
        event.reminder_text = answer_clean
    elif field == "recurrence":
        event.recurrence = answer_clean
    elif field == "category":
        event.category = answer_clean
    elif field == "indoor_outdoor":
        event.indoor_outdoor = answer_clean.lower()
    elif field == "cost":
        event.cost = answer_clean
    elif field == "what_to_bring":
        event.what_to_bring = answer_clean


def _parse_duration_text(text: str) -> Optional[int]:
    """Parse duration text like '2 hours', '90 minutes', '1.5h' into minutes."""
    text_lower = text.lower().strip()

    # "2 hours", "2h", "2 hr"
    match = re.match(r'(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)\b', text_lower)
    if match:
        return int(float(match.group(1)) * 60)

    # "90 minutes", "90min", "90m"
    match = re.match(r'(\d+)\s*(?:minutes?|mins?|m)\b', text_lower)
    if match:
        return int(match.group(1))

    # "1:30" or "1h30" or "1h30m"
    match = re.match(r'(\d+)[h:](\d+)', text_lower)
    if match:
        return int(match.group(1)) * 60 + int(match.group(2))

    # Bare number: assume hours if <= 12, minutes if > 12
    match = re.match(r'^(\d+)$', text_lower)
    if match:
        val = int(match.group(1))
        return val * 60 if val <= 12 else val

    return None


def _parse_single_line_response(
    event: EventExtraction,
    text: str,
    missing_fields: List[str],
):
    """Try to extract multiple field answers from a single line response."""
    # Look for location patterns: "at X" or "@ X"
    if "location" in missing_fields and not event.location:
        loc_match = re.search(r'(?:at|@)\s+([^,]+?)(?:\s*[,.]|$)', text, re.IGNORECASE)
        if loc_match:
            event.location = loc_match.group(1).strip()

    # Look for duration patterns
    if "duration" in missing_fields and event.duration_minutes is None:
        dur_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h|minutes?|mins?|m)\b', text, re.IGNORECASE)
        if dur_match:
            event.duration_minutes = _parse_duration_text(dur_match.group(0))

    # Look for participant names (capitalized words not matching other patterns)
    if "participants" in missing_fields and not event.participants:
        # Simple heuristic: comma-separated capitalized names
        name_match = re.search(r'(?:with|invite|bring)\s+(.+?)(?:\s*[.]|$)', text, re.IGNORECASE)
        if name_match:
            names = re.split(r'[,&]|\band\b', name_match.group(1))
            event.participants = [n.strip() for n in names if n.strip()]


# =============================================================================
# Pending Confirmation State
# =============================================================================

class PendingConfirmation(BaseModel):
    user_phone: str
    resolved_event: ResolvedEvent
    created_at: datetime
    expires_at: datetime  # 10 minute timeout


class PendingInterrogation(BaseModel):
    user_phone: str
    partial_event: EventExtraction
    resolved_time: Optional[Dict[str, Any]] = None
    missing_fields: List[str]
    sender_name: str
    created_at: datetime
    expires_at: datetime  # 10 minute timeout


_pending_confirmations: Dict[str, PendingConfirmation] = {}
_pending_interrogations: Dict[str, PendingInterrogation] = {}


def get_pending_confirmation(user_phone: str) -> Optional[PendingConfirmation]:
    """Get pending confirmation for a user, or None if expired/missing."""
    pending = _pending_confirmations.get(user_phone)
    if pending and datetime.now(LOCAL_TZ) > pending.expires_at:
        del _pending_confirmations[user_phone]
        return None
    return pending


def set_pending_confirmation(user_phone: str, event: ResolvedEvent):
    """Set a pending confirmation with 10-minute expiry."""
    _pending_confirmations[user_phone] = PendingConfirmation(
        user_phone=user_phone,
        resolved_event=event,
        created_at=datetime.now(LOCAL_TZ),
        expires_at=datetime.now(LOCAL_TZ) + timedelta(minutes=10)
    )


def clear_pending_confirmation(user_phone: str):
    """Clear a pending confirmation."""
    _pending_confirmations.pop(user_phone, None)


def get_pending_interrogation(user_phone: str) -> Optional[PendingInterrogation]:
    """Get pending interrogation for a user, or None if expired/missing."""
    pending = _pending_interrogations.get(user_phone)
    if pending and datetime.now(LOCAL_TZ) > pending.expires_at:
        del _pending_interrogations[user_phone]
        return None
    return pending


def set_pending_interrogation(
    user_phone: str,
    event: EventExtraction,
    missing_fields: List[str],
    sender_name: str,
    resolved_time: Optional[Dict[str, Any]] = None,
):
    """Set a pending interrogation with 10-minute expiry."""
    _pending_interrogations[user_phone] = PendingInterrogation(
        user_phone=user_phone,
        partial_event=event,
        resolved_time=resolved_time,
        missing_fields=missing_fields,
        sender_name=sender_name,
        created_at=datetime.now(LOCAL_TZ),
        expires_at=datetime.now(LOCAL_TZ) + timedelta(minutes=10),
    )


def clear_pending_interrogation(user_phone: str):
    """Clear a pending interrogation."""
    _pending_interrogations.pop(user_phone, None)


def is_affirmative(text: str) -> bool:
    """Check if text is an affirmative response."""
    affirmative = {"yes", "y", "yep", "yeah", "sure", "ok", "okay", "do it", "confirm"}
    return text.lower().strip() in affirmative


def is_negative(text: str) -> bool:
    """Check if text is a negative response."""
    negative = {"no", "n", "nope", "nah", "cancel", "nevermind", "skip"}
    return text.lower().strip() in negative


# =============================================================================
# Test Functions
# =============================================================================

if __name__ == "__main__":
    print("Testing calendar parser...")

    # Test 1: Standard event creation
    print("\n1. Standard event creation:")
    parsed = parse_message("Dinner at Mario's Friday at 7pm", "Danny")
    print(f"   Intent: {parsed.intent}")
    print(f"   Confidence: {parsed.confidence}")
    print(f"   Event name: {parsed.event.name if parsed.event else 'N/A'}")
    print(f"   Date text: {parsed.event.date_text if parsed.event else 'N/A'}")

    # Test 2: Event query
    print("\n2. Event query:")
    parsed = parse_message("What's happening this weekend?", "Liz")
    print(f"   Intent: {parsed.intent}")
    print(f"   Query time_range: {parsed.query.time_range if parsed.query else 'N/A'}")

    # Test 3: RSVP
    print("\n3. RSVP yes:")
    parsed = parse_message("I'm in for dinner", "Danny")
    print(f"   Intent: {parsed.intent}")
    print(f"   Reference event: {parsed.event.reference_event if parsed.event else 'N/A'}")

    # Test 4: Not calendar
    print("\n4. Not calendar:")
    parsed = parse_message("lol nice photo", "Liz")
    print(f"   Intent: {parsed.intent}")

    # Test 5: Date resolution
    print("\n5. Date resolution:")
    resolved = resolve_datetime("Friday at 7pm")
    print(f"   Start: {resolved['start']}")
    print(f"   Interpretation: {resolved['interpretation']}")

    print("\nParser tests complete")
