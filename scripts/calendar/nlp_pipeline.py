"""
Signal Calendar - NLP Pipeline

Parses natural language messages into structured calendar intents.
Uses Claude Code sessions for classification + entity extraction,
dateparser for deterministic datetime resolution.

Based on: signal-calendar-nlp-pipeline-design.md
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
from zoneinfo import ZoneInfo

import dateparser
from pydantic import BaseModel, Field

# Import Claude Code LLM client (replaces direct OpenRouter API)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))  # parent scripts dir
from calendar_llm_client import parse_with_claude_code, is_claude_code_available

# Configuration
LOCAL_TZ = ZoneInfo("America/New_York")
DEFAULT_DURATION = timedelta(hours=2)


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


class EventExtraction(BaseModel):
    name: Optional[str] = None
    date_text: Optional[str] = None
    location: Optional[str] = None
    duration_minutes: Optional[int] = None
    participants: list[str] = Field(default_factory=list)
    reference_event: Optional[str] = None


class QueryExtraction(BaseModel):
    time_range: Optional[str] = None
    filter: Optional[str] = None


class ParsedMessage(BaseModel):
    intent: Intent
    confidence: float = Field(ge=0.0, le=1.0)
    event: Optional[EventExtraction] = None
    query: Optional[QueryExtraction] = None
    ambiguities: list[str] = Field(default_factory=list)
    sender: str = ""
    raw_message: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)


class ResolvedEvent(BaseModel):
    name: str
    start_datetime: datetime
    end_datetime: datetime
    location: Optional[str] = None
    participants: list[str] = Field(default_factory=list)
    created_by: str = ""
    source_message: str = ""
    confidence: float = 1.0


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
    "reference_event": "string or null"
  },
  "query": {
    "time_range": "string or null",
    "filter": "string or null"
  },
  "ambiguities": ["string"]
}

Rules:
- "I'm in" / "count me in" with no context = not_calendar (need reference event)
- "I'm in" following an event creation = event_rsvp_yes referencing that event
- If the message contains multiple events, return the primary one and note others in ambiguities
- confidence < 0.6 = flag for confirmation
- Default duration is null (caller will apply 2-hour default)
- Participants are first names only as mentioned in the message
- For RSVP/modify/cancel, reference_event should match the most recent relevant event name
- "my place" = sender's location
- Bare hours (1-6) default to PM for social events
- Morning keywords (breakfast, brunch, hike, run) keep AM times"""


class MessageBuffer:
    """Rolling buffer of recent messages for context."""

    def __init__(self, max_size: int = 20):
        self.messages: list[dict] = []
        self.max_size = max_size

    def add(self, sender: str, text: str, timestamp: datetime = None):
        if timestamp is None:
            timestamp = datetime.now()
        self.messages.append({"sender": sender, "text": text, "ts": timestamp})
        if len(self.messages) > self.max_size:
            self.messages.pop(0)

    def recent(self, minutes: int = 30, limit: int = 5) -> list[dict]:
        cutoff = datetime.now() - timedelta(minutes=minutes)
        recent = [m for m in self.messages if m["ts"] > cutoff]
        return recent[-limit:]

    def get_last_event_create(self) -> Optional[str]:
        """Get the most recent event creation for RSVP context."""
        for m in reversed(self.messages):
            # Simple heuristic: look for event-like patterns
            if any(kw in m["text"].lower() for kw in ["dinner", "lunch", "brunch", "hike", "game", "party", "at "]):
                if any(kw in m["text"].lower() for kw in ["tomorrow", "today", "friday", "saturday", "sunday", "monday", "at "]):
                    return m["text"]
        return None


# Global message buffers per group
_message_buffers: dict[str, MessageBuffer] = {}


def get_buffer(group_id: str) -> MessageBuffer:
    """Get or create message buffer for a group."""
    if group_id not in _message_buffers:
        _message_buffers[group_id] = MessageBuffer()
    return _message_buffers[group_id]


def parse_message_with_llm(
    message: str,
    sender: str,
    recent_context: list[dict] = None,
) -> ParsedMessage:
    """
    Use Claude Code to classify intent and extract entities.
    Falls back to rule-based if Claude Code is unavailable.
    """
    # Check if Claude Code is available
    if not is_claude_code_available():
        return _rule_based_parse(message, sender)

    try:
        # Use Claude Code for classification
        result = parse_with_claude_code(
            message=message,
            sender=sender,
            recent_context=recent_context,
            timeout=30,
        )

        # Parse event extraction if present
        event = None
        if result.get("event"):
            event_data = result["event"]
            event = EventExtraction(
                name=event_data.get("name"),
                date_text=event_data.get("date_text"),
                location=event_data.get("location"),
                duration_minutes=event_data.get("duration_minutes"),
                participants=event_data.get("participants", []),
                reference_event=event_data.get("reference_event"),
            )

        # Parse query extraction if present
        query = None
        if result.get("query"):
            query_data = result["query"]
            query = QueryExtraction(
                time_range=query_data.get("time_range"),
                filter=query_data.get("filter"),
            )

        return ParsedMessage(
            intent=Intent(result.get("intent", "not_calendar")),
            confidence=result.get("confidence", 0.5),
            event=event,
            query=query,
            ambiguities=result.get("ambiguities", []),
            sender=sender,
            raw_message=message,
        )

    except Exception as e:
        print(f"Claude Code parse error: {e}")
        return _rule_based_parse(message, sender)


def _rule_based_parse(message: str, sender: str) -> ParsedMessage:
    """Fallback rule-based parsing when LLM is unavailable."""
    msg_lower = message.lower()

    # RSVP patterns
    if any(x in msg_lower for x in ["i'm in", "im in", "count me in", "i am in"]):
        return ParsedMessage(
            intent=Intent.RSVP_YES,
            confidence=0.7,
            sender=sender,
            raw_message=message,
        )

    if any(x in msg_lower for x in ["i'm out", "im out", "can't make it", "cant make it"]):
        return ParsedMessage(
            intent=Intent.RSVP_NO,
            confidence=0.7,
            sender=sender,
            raw_message=message,
        )

    # Query patterns
    if any(x in msg_lower for x in ["what's happening", "whats happening", "what am i doing", "what's going on"]):
        return ParsedMessage(
            intent=Intent.EVENT_QUERY,
            confidence=0.8,
            query=QueryExtraction(time_range="upcoming"),
            sender=sender,
            raw_message=message,
        )

    # Cancel patterns
    if any(x in msg_lower for x in ["cancel", "scratch", "call off"]):
        return ParsedMessage(
            intent=Intent.EVENT_CANCEL,
            confidence=0.7,
            event=EventExtraction(reference_event=_extract_event_name(message)),
            sender=sender,
            raw_message=message,
        )

    # Create patterns - look for date/time indicators
    date_indicators = [
        r"\btomorrow\b", r"\btoday\b", r"\btonight\b",
        r"\bmonday\b", r"\btuesday\b", r"\bwednesday\b",
        r"\bthursday\b", r"\bfriday\b", r"\bsaturday\b", r"\bsunday\b",
        r"\d{1,2}:\d{2}", r"\bat \d\b", r"\d{1,2}(am|pm)",
        r"\bnext week\b", r"\bthis week\b", r"\bweekend\b",
    ]

    has_date = any(re.search(pattern, msg_lower) for pattern in date_indicators)

    if has_date:
        # Try to extract event name and date
        event_name = _extract_event_name(message)
        date_text = _extract_date_text(message)
        location = _extract_location(message)

        return ParsedMessage(
            intent=Intent.EVENT_CREATE,
            confidence=0.6,
            event=EventExtraction(
                name=event_name,
                date_text=date_text,
                location=location,
            ),
            sender=sender,
            raw_message=message,
        )

    return ParsedMessage(
        intent=Intent.NOT_CALENDAR,
        confidence=0.8,
        sender=sender,
        raw_message=message,
    )


def _extract_event_name(message: str) -> Optional[str]:
    """Extract potential event name from message."""
    # Simple patterns
    patterns = [
        r"(?:dinner|lunch|brunch|breakfast|coffee|drinks)\s+(?:at|@)\s+([\w\s']+)",
        r"([\w\s]+)(?:\s+(?:at|@)\s+|$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return None


def _extract_date_text(message: str) -> Optional[str]:
    """Extract date/time portion from message."""
    # Look for date/time patterns
    patterns = [
        r"(tomorrow|today|tonight|this weekend|next week)",
        r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)(?:\s+at\s+\d[^,]*)?",
        r"(\d{1,2}:\d{2}(?:\s*(?:am|pm))?)",
        r"at\s+(\d{1,2}(?::\d{2})?(?:\s*(?:am|pm))?)",
    ]

    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return None


def _extract_location(message: str) -> Optional[str]:
    """Extract location from message."""
    patterns = [
        r"(?:at|@)\s+([\w\s']+?)(?:\s+(?:on|this|next|tomorrow|today|\d{1,2}))",
        r"(?:at|@)\s+([\w\s']+)$",
        r"my place",
    ]

    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            loc = match.group(0) if pattern == r"my place" else match.group(1)
            return loc.strip()

    return None


def resolve_datetime(
    date_text: str,
    reference_time: datetime = None,
    event_name: str = "",
) -> dict:
    """
    Resolve date text to absolute datetime using dateparser + custom rules.
    Returns dict with start, end, is_ambiguous, interpretation, alternatives.
    """
    if reference_time is None:
        reference_time = datetime.now(LOCAL_TZ)

    date_text = date_text.strip()
    date_lower = date_text.lower()

    # Special patterns
    if date_lower == "tonight":
        tonight = reference_time.replace(hour=19, minute=0, second=0, microsecond=0)
        return {
            "start": tonight,
            "end": tonight + DEFAULT_DURATION,
            "is_ambiguous": False,
            "interpretation": "Tonight at 7:00 PM",
            "alternatives": [],
        }

    if "weekend" in date_lower:
        sat = _next_weekday(reference_time, 5)  # Saturday
        return {
            "start": sat.replace(hour=10, minute=0),
            "end": (sat + timedelta(days=1)).replace(hour=18, minute=0),
            "is_ambiguous": "next" in date_lower,  # "next weekend" is ambiguous
            "interpretation": f"This weekend: {sat.strftime('%b %d')} - {(sat + timedelta(days=1)).strftime('%b %d')}",
            "alternatives": [],
        }

    if date_lower == "next week":
        return {
            "start": None,
            "end": None,
            "is_ambiguous": True,
            "interpretation": "'next week' is vague - which day?",
            "alternatives": [],
        }

    # Use dateparser
    settings = {
        'PREFER_DATES_FROM': 'future',
        'PREFER_DAY_OF_MONTH': 'first',
        'RELATIVE_BASE': reference_time.replace(tzinfo=None),
        'RETURN_AS_TIMEZONE_AWARE': False,
        'TIMEZONE': str(LOCAL_TZ),
    }

    parsed = dateparser.parse(date_text, settings=settings)

    if parsed is None:
        return {
            "start": None,
            "end": None,
            "is_ambiguous": True,
            "interpretation": f"Could not parse: '{date_text}'",
            "alternatives": [],
        }

    # Localize
    start = parsed.replace(tzinfo=LOCAL_TZ)

    # Apply AM/PM heuristic
    start = _apply_ampm_heuristic(start, date_text, event_name)

    # Detect ambiguity
    ambiguous = _detect_ambiguity(date_text, start, reference_time)

    return {
        "start": start,
        "end": start + DEFAULT_DURATION,
        "is_ambiguous": ambiguous,
        "interpretation": f"{start.strftime('%A, %B %d at %I:%M %p')}",
        "alternatives": [],
    }


def _next_weekday(date: datetime, weekday: int) -> datetime:
    """Get next occurrence of weekday (0=Monday, 6=Sunday)."""
    days_ahead = weekday - date.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return date + timedelta(days=days_ahead)


def _apply_ampm_heuristic(dt: datetime, date_text: str, event_name: str) -> datetime:
    """Apply AM/PM heuristics for bare hour numbers."""
    # Check if time was explicitly specified with am/pm
    has_ampm = re.search(r'\d\s*(am|pm)', date_text, re.IGNORECASE)
    if has_ampm:
        return dt

    # Check if hour looks like it was parsed without am/pm context
    hour = dt.hour

    # Morning events keep AM
    morning_keywords = {"breakfast", "brunch", "coffee", "run", "hike", "yoga", "morning"}
    name_lower = (event_name or "").lower()

    if any(kw in name_lower for kw in morning_keywords):
        if hour >= 12:
            # Likely mis-parsed, reset to AM
            return dt.replace(hour=hour - 12 if hour > 12 else 9)
        return dt

    # Social events: bare hours 1-6 default to PM
    if 1 <= hour <= 6 and not has_ampm:
        return dt.replace(hour=hour + 12)

    # 7-11: default PM for social unless morning keyword
    if 7 <= hour <= 11 and not has_ampm:
        if not any(kw in name_lower for kw in morning_keywords):
            return dt.replace(hour=hour + 12)

    return dt


def _detect_ambiguity(date_text: str, parsed: datetime, reference: datetime) -> bool:
    """Detect if date/time is ambiguous."""
    date_lower = date_text.lower()

    # These are always ambiguous
    ambiguous_terms = ["next week", "sometime", "soon", "later"]
    if any(term in date_lower for term in ambiguous_terms):
        return True

    # Bare day names without "this" or "next" could be ambiguous
    day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    if any(day == date_lower.strip() for day in day_names):
        return True

    return False


def generate_event_name(event: EventExtraction, sender: str = "") -> str:
    """Generate event name from extraction."""
    if event.name and event.name.lower() not in ("something", "thing", "stuff", "it"):
        return event.name

    if event.location:
        if event.location.lower() == "my place" and sender:
            return f"At {sender}'s place"
        return f"At {event.location}"

    return "Unnamed Event"


def is_affirmative(text: str) -> bool:
    """Check if text is an affirmative response."""
    affirmatives = ["yes", "y", "yep", "yeah", "sure", "ok", "okay", "do it", "confirm"]
    return text.lower().strip().rstrip(".!?") in affirmatives


def is_negative(text: str) -> bool:
    """Check if text is a negative response."""
    negatives = ["no", "n", "nope", "nah", "cancel", "skip", "pass"]
    return text.lower().strip().rstrip(".!?") in negatives
