#!/usr/bin/env python3
"""
Test script for event/task cross-reference functionality in conversation_logger.py

Tests various message types to verify:
- Event extraction from quoted names
- Event extraction from capitalized phrases with keywords
- Task ID extraction (multiple formats)
- Bidirectional linking between conversations and events/tasks
"""

import sys
import json
from pathlib import Path

# Add parent directory to path
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from conversation_logger import ConversationLogger

def test_event_extraction():
    """Test event mention extraction from various message formats."""
    print("=" * 70)
    print("TEST 1: Event Extraction")
    print("=" * 70)

    logger = ConversationLogger()

    test_cases = [
        {
            "name": "Quoted event names",
            "message": 'Can we reschedule "Team Standup" to 3pm? Also need to discuss "Sprint Review"',
            "expected_events": ["Team Standup", "Sprint Review"]
        },
        {
            "name": "Capitalized phrases with keywords",
            "message": "Let's have a Quick Sync meeting about the project",
            "expected_events": ["Quick Sync meeting"]  # May also extract case variants
        },
        {
            "name": "Common event names",
            "message": "Are you coming to the Weekly Sync tomorrow?",
            "expected_events": ["Weekly Sync"]
        },
        {
            "name": "Mixed quoted and keyword events",
            "message": 'Join "Planning Session" for the Retro meeting',
            "expected_events": ["Planning Session"]  # "for the Retro" might be captured
        },
        {
            "name": "No events",
            "message": "Just checking in on the project status",
            "expected_events": []
        },
        {
            "name": "Multiple capitalized phrases",
            "message": "Attend the Project Review meeting and the Team Sync call",
            "expected_events": ["Project Review meeting", "Team Sync call"]
        }
    ]

    passed = 0
    failed = 0

    for test in test_cases:
        result = logger._extract_event_mentions(test["message"])
        expected = test["expected_events"]

        # Normalize for comparison (case-insensitive)
        result_lower = [r.lower() for r in result]
        expected_lower = [e.lower() for e in expected]

        if set(result_lower) == set(expected_lower):
            print(f"✓ PASS: {test['name']}")
            print(f"  Extracted: {result}")
            passed += 1
        else:
            print(f"✗ FAIL: {test['name']}")
            print(f"  Expected: {expected}")
            print(f"  Got: {result}")
            failed += 1
        print()

    print(f"\nEvent Extraction Results: {passed} passed, {failed} failed")
    return passed, failed


def test_task_extraction():
    """Test task ID extraction from various message formats."""
    print("=" * 70)
    print("TEST 2: Task ID Extraction")
    print("=" * 70)

    logger = ConversationLogger()

    test_cases = [
        {
            "name": "task-XXXX format",
            "message": "I'm working on task-1234 and task-5678",
            "expected_tasks": ["task-1234", "task-5678"]
        },
        {
            "name": "#XXXX format (4+ digits)",
            "message": "Please review #4567 and #8901",
            "expected_tasks": ["task-4567", "task-8901"]
        },
        {
            "name": "issue-XXX format",
            "message": "Bug reported in issue-123, also issue-456",
            "expected_tasks": ["task-123", "task-456"]
        },
        {
            "name": "Mixed formats",
            "message": "Check task-999, #1001, and issue-555",
            "expected_tasks": ["task-999", "task-1001", "task-555"]
        },
        {
            "name": "Deduplication",
            "message": "task-111 mentioned twice, task-111 and #111",
            "expected_tasks": ["task-111"]
        },
        {
            "name": "No task IDs",
            "message": "Just checking on the deployment status",
            "expected_tasks": []
        },
        {
            "name": "# with less than 4 digits (should not match)",
            "message": "Check #123 for details",
            "expected_tasks": []
        }
    ]

    passed = 0
    failed = 0

    for test in test_cases:
        result = logger._extract_task_ids(test["message"])
        expected = test["expected_tasks"]

        if set(result) == set(expected):
            print(f"✓ PASS: {test['name']}")
            print(f"  Extracted: {result}")
            passed += 1
        else:
            print(f"✗ FAIL: {test['name']}")
            print(f"  Expected: {expected}")
            print(f"  Got: {result}")
            failed += 1
        print()

    print(f"\nTask ID Extraction Results: {passed} passed, {failed} failed")
    return passed, failed


def test_bidirectional_linking():
    """Test bidirectional linking between conversations and events/tasks."""
    print("=" * 70)
    print("TEST 3: Bidirectional Linking")
    print("=" * 70)

    # Use a test phone number
    test_phone = "+15550199"

    logger = ConversationLogger()

    # Clear any existing test data
    try:
        import shutil
        test_profile_dir = Path.home() / ".openclaw" / "agents" / "main" / "memory" / "humans"
        test_profile_file = test_profile_dir / f"15550199.md"
        if test_profile_file.exists():
            test_profile_file.unlink()
    except:
        pass

    # Test 1: Log conversation with events
    print("\nTest 3.1: Logging conversation with events")
    print("-" * 70)

    success = logger.log_human_conversation(
        phone_number=test_phone,
        direction="inbound",
        content='Can we reschedule "Team Standup" to 3pm?',
        channel="signal"
    )

    if success:
        print("✓ Conversation logged successfully")

        # Verify conversation has related_events
        conversations = logger._load_conversation_index(test_phone)
        if conversations:
            latest_conv = conversations[-1]
            if "related_events" in latest_conv and "Team Standup" in latest_conv["related_events"]:
                print(f"✓ Event linked in conversation: {latest_conv['related_events']}")
            else:
                print(f"✗ Event not linked in conversation")

            # Verify bidirectional link in profile
            event_links = logger.get_event_links(test_phone)
            if event_links and "Team Standup" in event_links:
                print(f"✓ Bidirectional link created in profile")
                print(f"  Event links: {json.dumps(event_links, indent=2)}")
            else:
                print(f"✗ Event link not found in profile")
        else:
            print("✗ No conversations found")
    else:
        print("✗ Failed to log conversation")

    # Test 2: Log conversation with tasks
    print("\nTest 3.2: Logging conversation with tasks")
    print("-" * 70)

    success = logger.log_human_conversation(
        phone_number=test_phone,
        direction="outbound",
        content="I'm working on task-1234, please review #5678",
        channel="signal"
    )

    if success:
        print("✓ Conversation logged successfully")

        # Verify conversation has related_tasks
        conversations = logger._load_conversation_index(test_phone)
        if conversations:
            latest_conv = conversations[-1]
            if "related_tasks" in latest_conv:
                print(f"✓ Tasks linked in conversation: {latest_conv['related_tasks']}")
            else:
                print(f"✗ Tasks not linked in conversation")

            # Verify bidirectional link in profile
            task_links = logger.get_task_links(test_phone)
            if task_links:
                print(f"✓ Bidirectional link created in profile")
                print(f"  Task links: {json.dumps(task_links, indent=2)}")
            else:
                print(f"✗ task_links not found in profile")
        else:
            print("✗ No conversations found")
    else:
        print("✗ Failed to log conversation")

    # Test 3: Multiple conversations linking to same event
    print("\nTest 3.3: Multiple conversations linking to same event")
    print("-" * 70)

    logger.log_human_conversation(
        phone_number=test_phone,
        direction="inbound",
        content='Reminder about "Team Standup"',
        channel="signal"
    )

    event_links = logger.get_event_links(test_phone)
    if event_links and "Team Standup" in event_links:
        link_count = len(event_links["Team Standup"])
        if link_count >= 2:
            print(f"✓ Multiple conversations linked to same event")
            print(f"  'Team Standup' has {link_count} conversation references")
        else:
            print(f"✗ Expected 2+ links, got {link_count}")
    else:
        print(f"✗ Event link not found or insufficient references")

    # Test 4: Verify reverse lookup
    print("\nTest 3.4: Reverse lookup capability")
    print("-" * 70)

    event_links = logger.get_event_links(test_phone)
    if event_links:
        print("✓ Can lookup conversations by event:")
        for event_name, links in event_links.items():
            print(f"  Event '{event_name}': {len(links)} conversation(s)")
            for link in links:
                print(f"    - {link['conversation_date']}")

    task_links = logger.get_task_links(test_phone)
    if task_links:
        print("\n✓ Can lookup conversations by task:")
        for task_id, links in task_links.items():
            print(f"  Task '{task_id}': {len(links)} conversation(s)")
            for link in links:
                print(f"    - {link['conversation_date']}")

    print("\n" + "=" * 70)
    print("Bidirectional Linking Test Complete")
    print("=" * 70)


def test_combined_extraction():
    """Test messages with both events and tasks."""
    print("=" * 70)
    print("TEST 4: Combined Event and Task Extraction")
    print("=" * 70)

    logger = ConversationLogger()

    test_cases = [
        {
            "name": "Event and task in same message",
            "message": 'Let\'s discuss task-1234 during "Team Standup"',
            "expected_events": ["Team Standup"],
            "expected_tasks": ["task-1234"]
        },
        {
            "name": "Multiple events and tasks",
            "message": 'Work on task-555 and issue-666 before "Sprint Review" meeting',
            "expected_events": ["Sprint Review"],
            "expected_tasks": ["task-555", "task-666"]
        },
        {
            "name": "Complex message with all patterns",
            "message": 'Check task-100, task-200, and issue-300 before the "Weekly Sync" call. Also review #4000.',
            "expected_events": ["Weekly Sync"],
            "expected_tasks": ["task-100", "task-200", "task-300", "task-4000"]
        }
    ]

    passed = 0
    failed = 0

    for test in test_cases:
        events = logger._extract_event_mentions(test["message"])
        tasks = logger._extract_task_ids(test["message"])

        events_match = set([e.lower() for e in events]) == set([e.lower() for e in test["expected_events"]])
        tasks_match = set(tasks) == set(test["expected_tasks"])

        if events_match and tasks_match:
            print(f"✓ PASS: {test['name']}")
            print(f"  Events: {events}")
            print(f"  Tasks: {tasks}")
            passed += 1
        else:
            print(f"✗ FAIL: {test['name']}")
            print(f"  Expected events: {test['expected_events']}, got: {events}")
            print(f"  Expected tasks: {test['expected_tasks']}, got: {tasks}")
            failed += 1
        print()

    print(f"\nCombined Extraction Results: {passed} passed, {failed} failed")
    return passed, failed


def main():
    """Run all tests."""
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 15 + "CROSS-REFERENCE FUNCTIONALITY TESTS" + " " * 18 + "║")
    print("╚" + "═" * 68 + "╝")
    print("\n")

    total_passed = 0
    total_failed = 0

    # Run tests
    p, f = test_event_extraction()
    total_passed += p
    total_failed += f

    print("\n" * 2)

    p, f = test_task_extraction()
    total_passed += p
    total_failed += f

    print("\n" * 2)

    test_bidirectional_linking()

    print("\n" * 2)

    p, f = test_combined_extraction()
    total_passed += p
    total_failed += f

    # Summary
    print("\n")
    print("=" * 70)
    print("FINAL RESULTS")
    print("=" * 70)
    print(f"Total Passed: {total_passed}")
    print(f"Total Failed: {total_failed}")

    if total_failed == 0:
        print("\n✓ ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n✗ {total_failed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
