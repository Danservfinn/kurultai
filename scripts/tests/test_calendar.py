#!/usr/bin/env python3
"""
Test Suite for Signal Calendar System

Comprehensive tests for:
- Neo4j calendar operations
- LLM message parsing
- Date/time resolution
- Signal handler routing
- Edge cases and error handling
"""

import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_calendar import (
    init_schema,
    seed_persons,
    get_or_create_person,
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
    get_due_reminders,
    mark_reminder_sent,
    get_todays_events,
    get_daily_digest,
    check_time_conflicts,
)

from calendar_parser import (
    parse_message,
    resolve_datetime,
    Intent,
    EventExtraction,
    is_affirmative,
    is_negative,
    detect_missing_fields,
    format_followup_questions,
    parse_interrogation_response,
    _parse_duration_text,
    set_pending_interrogation,
    get_pending_interrogation,
    clear_pending_interrogation,
)


# Test helpers
LOCAL_TZ = ZoneInfo("America/New_York")
TEST_PERSON_PHONE = "+19995551234"
TEST_PERSON_NAME = "TestUser"


def print_test(name: str, passed: bool, details: str = ""):
    """Print test result."""
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"  {status}: {name}")
    if details and not passed:
        print(f"         {details}")


def cleanup_test_data():
    """Clean up test data from Neo4j."""
    from neo4j_task_tracker import neo4j_session
    with neo4j_session() as session:
        # Delete test person
        session.run("MATCH (p:Person {phone_number: $phone}) DETACH DELETE p", phone=TEST_PERSON_PHONE)
        # Delete test events (by pattern)
        session.run("MATCH (e:Event {name: 'Test Event'}) DETACH DELETE e")
        session.run("MATCH (e:Event {name: 'Team Meeting'}) DETACH DELETE e")
        session.run("MATCH (e:Event {name: 'Coffee Chat'}) DETACH DELETE e")


# =============================================================================
# Neo4j Calendar Tests
# =============================================================================

def test_neo4j_schema():
    """Test schema initialization."""
    print("\n[Neo4j Schema Tests]")

    try:
        result = init_schema()
        print_test("Schema initialization", result is True)
    except Exception as e:
        print_test("Schema initialization", False, str(e))

    try:
        result = seed_persons()
        print_test("Seed persons", result is True)
    except Exception as e:
        print_test("Seed persons", False, str(e))


def test_person_operations():
    """Test person CRUD operations."""
    print("\n[Person Operations Tests]")

    # Create test person
    person = get_or_create_person(TEST_PERSON_PHONE, TEST_PERSON_NAME)
    print_test("Create person", person is not None)
    print_test("Person has phone", person.get("phone_number") == TEST_PERSON_PHONE if person else False)

    # Cleanup
    cleanup_test_data()


def test_event_creation():
    """Test event creation and retrieval."""
    print("\n[Event Creation Tests]")

    # Create test person first
    get_or_create_person(TEST_PERSON_PHONE, TEST_PERSON_NAME)

    # Create event
    start = datetime.now(LOCAL_TZ) + timedelta(days=1)
    end = start + timedelta(hours=2)

    event = create_event(
        name="Test Event",
        start_datetime=start,
        end_datetime=end,
        creator_phone=TEST_PERSON_PHONE,
        description="A test event",
        location_name="Test Location",
        source_message="Test event tomorrow at 7pm"
    )

    print_test("Create event", event is not None)
    print_test("Event has ID", event.get("event_id") is not None if event else False)
    print_test("Event has name", event.get("name") == "Test Event" if event else False)

    # Get upcoming events
    events = get_upcoming_events(hours=48)
    test_events = [e for e in events if e.get("name") == "Test Event"]
    print_test("Get upcoming events", len(test_events) > 0)

    # Cleanup
    cleanup_test_data()


def test_rsvp_operations():
    """Test RSVP operations."""
    print("\n[RSVP Operations Tests]")

    # Setup
    get_or_create_person(TEST_PERSON_PHONE, TEST_PERSON_NAME)

    start = datetime.now(LOCAL_TZ) + timedelta(days=2)
    event = create_event(
        name="Team Meeting",
        start_datetime=start,
        creator_phone=TEST_PERSON_PHONE,
    )

    # RSVP to event
    result = rsvp_to_event(TEST_PERSON_PHONE, "Team Meeting", "going")
    print_test("RSVP to event", result is not None)

    # Get attendees
    attendees = get_event_attendees("Team Meeting")
    print_test("Get attendees", len(attendees) > 0)

    # Cleanup
    cleanup_test_data()


def test_event_search():
    """Test event search operations."""
    print("\n[Event Search Tests]")

    # Setup
    get_or_create_person(TEST_PERSON_PHONE, TEST_PERSON_NAME)
    start = datetime.now(LOCAL_TZ) + timedelta(days=3)
    create_event(
        name="Coffee Chat",
        start_datetime=start,
        creator_phone=TEST_PERSON_PHONE,
        description="Let's have coffee and chat"
    )

    # Search events
    events = search_events("coffee", limit=5)
    print_test("Search by keyword", len(events) > 0)

    # Search for person's events
    person_events = get_events_for_person(TEST_PERSON_NAME)
    print_test("Get person's events", len(person_events) > 0)

    # Cleanup
    cleanup_test_data()


def test_event_modification():
    """Test event modification and cancellation."""
    print("\n[Event Modification Tests]")

    # Setup
    get_or_create_person(TEST_PERSON_PHONE, TEST_PERSON_NAME)
    start = datetime.now(LOCAL_TZ) + timedelta(days=4)
    create_event(
        name="Test Event",
        start_datetime=start,
        creator_phone=TEST_PERSON_PHONE,
    )

    # Modify event time
    new_start = start + timedelta(hours=1)
    result = modify_event_time(TEST_PERSON_PHONE, "Test Event", new_start)
    print_test("Modify event time", result is not None)

    # Cancel event
    result = cancel_event(TEST_PERSON_PHONE, "Test Event")
    print_test("Cancel event", result is not None)
    print_test("Cancel returns status", result.get("status") == "cancelled" if result else False)

    # Verify cancelled event is NOT in upcoming events (correct behavior)
    events = get_upcoming_events(hours=168)
    cancelled_in_upcoming = [e for e in events if e.get("name") == "Test Event"]
    print_test("Cancelled event excluded from upcoming", len(cancelled_in_upcoming) == 0)

    # Cleanup
    cleanup_test_data()


def test_reminder_operations():
    """Test reminder creation and retrieval."""
    print("\n[Reminder Operations Tests]")

    # Setup
    get_or_create_person(TEST_PERSON_PHONE, TEST_PERSON_NAME)

    # Create event in 5 days
    start = datetime.now(LOCAL_TZ) + timedelta(days=5)
    create_event(
        name="Test Event",
        start_datetime=start,
        creator_phone=TEST_PERSON_PHONE,
    )

    # Create reminder 1 hour before (in the future, not due yet)
    remind_at = start - timedelta(hours=1)
    result = create_reminder(TEST_PERSON_PHONE, "Test Event", remind_at, "1 hour before")
    print_test("Create future reminder", result is not None)
    print_test("Reminder has ID", result.get("reminder_id") is not None if result else False)

    # Due reminders should NOT include future reminder
    due = get_due_reminders()
    future_due = [r for r in due if r.get("event_name") == "Test Event"]
    print_test("Future reminder not yet due", len(future_due) == 0)

    # Create an overdue reminder (in the past) to test due retrieval
    past_time = datetime.now(LOCAL_TZ) - timedelta(minutes=5)
    result2 = create_reminder(TEST_PERSON_PHONE, "Test Event", past_time, "overdue test")
    print_test("Create overdue reminder", result2 is not None)

    # Now get due reminders - should include the overdue one
    due = get_due_reminders()
    overdue_found = [r for r in due if r.get("reminder_id") == result2.get("reminder_id")]
    print_test("Get due reminders finds overdue", len(overdue_found) > 0)

    # Mark as sent
    if overdue_found:
        mark_reminder_sent(overdue_found[0]["reminder_id"])
        print_test("Mark reminder sent", True)

    # Cleanup
    cleanup_test_data()


def test_conflict_detection():
    """Test time conflict detection."""
    print("\n[Conflict Detection Tests]")

    # Setup
    get_or_create_person(TEST_PERSON_PHONE, TEST_PERSON_NAME)
    start = datetime.now(LOCAL_TZ) + timedelta(days=6, hours=10)
    end = start + timedelta(hours=2)
    create_event(
        name="Morning Meeting",
        start_datetime=start,
        end_datetime=end,
        creator_phone=TEST_PERSON_PHONE,
    )

    # Check for conflicts (overlapping time)
    proposed_start = start + timedelta(minutes=30)  # 30 min into existing event
    proposed_end = proposed_start + timedelta(hours=1)
    conflicts = check_time_conflicts(proposed_start, proposed_end)
    print_test("Detect time conflict", len(conflicts) > 0)

    # Check non-conflicting time
    free_start = start + timedelta(hours=5)
    free_end = free_start + timedelta(hours=1)
    conflicts = check_time_conflicts(free_start, free_end)
    print_test("No conflict for free slot", len(conflicts) == 0)

    # Cleanup
    cleanup_test_data()


# =============================================================================
# Parser Tests
# =============================================================================

def test_intent_classification():
    """Test LLM intent classification."""
    print("\n[Intent Classification Tests]")

    test_cases = [
        ("Dinner at Mario's Friday 7pm", Intent.EVENT_CREATE),
        ("What's happening this weekend?", Intent.EVENT_QUERY),
        ("I'm in for dinner", Intent.RSVP_YES),
        ("Can't make it", Intent.RSVP_NO),
        ("Cancel the meeting", Intent.EVENT_CANCEL),
        ("lol nice", Intent.NOT_CALENDAR),
    ]

    for message, expected_intent in test_cases:
        parsed = parse_message(message, "TestUser")
        passed = parsed.intent == expected_intent
        print_test(f"'{message[:30]}...' -> {expected_intent.value}", passed)


def test_date_resolution():
    """Test date/time resolution."""
    print("\n[Date Resolution Tests]")

    # Test "tonight"
    result = resolve_datetime("tonight")
    print_test("'tonight' resolves", result["start"] is not None)
    print_test("'tonight' is evening", result["start"].hour >= 19 if result["start"] else False)

    # Test "this weekend"
    result = resolve_datetime("this weekend")
    print_test("'this weekend' resolves", result["start"] is not None)
    print_test("'this weekend' is Sat/Sun", result["start"].weekday() >= 5 if result["start"] else False)

    # Test ambiguous
    result = resolve_datetime("sometime next week")
    print_test("'sometime next week' is ambiguous", result["is_ambiguous"])


def test_affirmative_negative():
    """Test affirmative/negative detection."""
    print("\n[Response Detection Tests]")

    affirmative_tests = ["yes", "y", "yep", "yeah", "sure", "ok"]
    for text in affirmative_tests:
        print_test(f"'{text}' is affirmative", is_affirmative(text))

    negative_tests = ["no", "n", "nope", "nah", "cancel"]
    for text in negative_tests:
        print_test(f"'{text}' is negative", is_negative(text))


# =============================================================================
# Daily Digest Tests
# =============================================================================

def test_daily_digest():
    """Test daily digest generation."""
    print("\n[Daily Digest Tests]")

    # Setup
    get_or_create_person(TEST_PERSON_PHONE, TEST_PERSON_NAME)

    # Create events for next 3 days
    for i in range(3):
        start = datetime.now(LOCAL_TZ) + timedelta(days=i+1)
        create_event(
            name=f"Day {i+1} Event",
            start_datetime=start,
            creator_phone=TEST_PERSON_PHONE,
        )

    # Get digest
    digest = get_daily_digest(days=3)
    print_test("Get daily digest", len(digest) > 0)
    print_test("Digest has 3 events", len(digest) >= 3)

    # Cleanup
    cleanup_test_data()


# =============================================================================
# Interrogation Flow Tests
# =============================================================================

def test_detect_missing_fields():
    """Test missing field detection."""
    print("\n[Missing Field Detection Tests]")

    # Fully empty event
    event = EventExtraction()
    missing = detect_missing_fields(event)
    print_test("Empty event has all fields missing", len(missing) == 8)
    print_test("name is missing", "name" in missing)
    print_test("date_text is missing", "date_text" in missing)
    print_test("duration is missing", "duration" in missing)
    print_test("location is missing", "location" in missing)

    # Partially filled event
    event = EventExtraction(name="Dinner", date_text="Friday 7pm", location="Mario's")
    missing = detect_missing_fields(event)
    print_test("Partial event: name NOT missing", "name" not in missing)
    print_test("Partial event: date_text NOT missing", "date_text" not in missing)
    print_test("Partial event: location NOT missing", "location" not in missing)
    print_test("Partial event: duration IS missing", "duration" in missing)
    print_test("Partial event: participants IS missing", "participants" in missing)

    # Fully filled event
    event = EventExtraction(
        name="Dinner", date_text="Friday 7pm", location="Mario's",
        duration_minutes=120, participants=["Danny"],
        description="Italian food", reminder_text="1 hour before",
        recurrence="no"
    )
    missing = detect_missing_fields(event)
    print_test("Full event has no missing fields", len(missing) == 0)


def test_format_followup_questions():
    """Test follow-up question formatting."""
    print("\n[Follow-up Question Formatting Tests]")

    # Event with just a name and time
    event = EventExtraction(name="Dinner", date_text="Friday 7pm")
    questions = format_followup_questions(event)
    print_test("Questions generated", len(questions) > 0)
    print_test("Contains 'Got it'", "Got it" in questions)
    print_test("Contains 'Dinner'", "Dinner" in questions)
    print_test("Asks about duration", "How long" in questions)
    print_test("Asks about location", "Where" in questions)
    print_test("Asks about participants", "coming" in questions)

    # Event with everything filled - no questions needed
    event = EventExtraction(
        name="Dinner", date_text="Friday 7pm", location="Mario's",
        duration_minutes=120, participants=["Danny"],
        description="Italian food", reminder_text="1 hour before",
        recurrence="no"
    )
    questions = format_followup_questions(event)
    print_test("No questions when all filled", questions == "")


def test_parse_duration_text():
    """Test duration text parsing."""
    print("\n[Duration Text Parsing Tests]")

    test_cases = [
        ("2 hours", 120),
        ("2h", 120),
        ("90 minutes", 90),
        ("90min", 90),
        ("1.5 hours", 90),
        ("1h30", 90),
        ("1:30", 90),
        ("3", 180),     # bare number <= 12: hours
        ("45", 45),     # bare number > 12: minutes
    ]

    for text, expected in test_cases:
        result = _parse_duration_text(text)
        print_test(f"'{text}' -> {expected} min", result == expected,
                   f"got {result}")


def test_parse_interrogation_response():
    """Test parsing user responses to interrogation questions."""
    print("\n[Interrogation Response Parsing Tests]")

    # Multi-line response matching question order
    event = EventExtraction(name="Dinner", date_text="Friday 7pm")
    missing = ["duration", "location", "participants"]
    response = "2 hours\nMario's on Main St\nDanny and Liz"

    updated = parse_interrogation_response(response, missing, event)
    print_test("Duration parsed", updated.duration_minutes == 120)
    print_test("Location parsed", updated.location == "Mario's on Main St")
    print_test("Participants parsed", len(updated.participants) == 2)
    print_test("Participant names correct",
               "Danny" in updated.participants and "Liz" in updated.participants)

    # Skip response
    event2 = EventExtraction(name="Meeting", date_text="Monday 3pm")
    updated2 = parse_interrogation_response("skip", ["duration", "location"], event2)
    print_test("Skip leaves fields empty", updated2.duration_minutes is None)
    print_test("Skip leaves location empty", updated2.location is None)

    # Partial answers with skips
    event3 = EventExtraction(name="Lunch", date_text="Tomorrow noon")
    response3 = "1 hour\nskip\nBob"
    updated3 = parse_interrogation_response(response3, ["duration", "location", "participants"], event3)
    print_test("Partial: duration filled", updated3.duration_minutes == 60)
    print_test("Partial: location skipped", updated3.location is None)
    print_test("Partial: participants filled", "Bob" in updated3.participants)


def test_interrogation_state():
    """Test interrogation state management."""
    print("\n[Interrogation State Tests]")

    phone = "+19995559999"
    event = EventExtraction(name="Test Event", date_text="Friday 7pm")
    missing = ["duration", "location"]

    # Set interrogation
    set_pending_interrogation(phone, event, missing, "TestUser")
    pending = get_pending_interrogation(phone)
    print_test("Interrogation stored", pending is not None)
    print_test("Missing fields preserved", pending.missing_fields == missing if pending else False)
    print_test("Event preserved", pending.partial_event.name == "Test Event" if pending else False)

    # Clear interrogation
    clear_pending_interrogation(phone)
    pending = get_pending_interrogation(phone)
    print_test("Interrogation cleared", pending is None)


# =============================================================================
# Main Test Runner
# =============================================================================

def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("Signal Calendar System - Test Suite")
    print("=" * 60)

    # Neo4j tests
    test_neo4j_schema()
    test_person_operations()
    test_event_creation()
    test_rsvp_operations()
    test_event_search()
    test_event_modification()
    test_reminder_operations()
    test_conflict_detection()

    # Parser tests
    test_intent_classification()
    test_date_resolution()
    test_affirmative_negative()

    # Interrogation tests
    test_detect_missing_fields()
    test_format_followup_questions()
    test_parse_duration_text()
    test_parse_interrogation_response()
    test_interrogation_state()

    # Digest tests
    test_daily_digest()

    print("\n" + "=" * 60)
    print("Test suite complete")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
