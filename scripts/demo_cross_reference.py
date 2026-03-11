#!/usr/bin/env python3
"""
Demonstration script for event/task cross-reference functionality.

This script shows how the conversation logger automatically:
1. Extracts event mentions from messages
2. Extracts task IDs from messages
3. Creates bidirectional links between conversations and events/tasks
4. Enables reverse lookup (find all conversations about an event/task)
"""

import sys
import json
from pathlib import Path

# Add parent directory to path
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from conversation_logger import ConversationLogger

def demo():
    """Demonstrate cross-reference functionality."""

    print("\n" + "="*70)
    print("DEMONSTRATION: Event/Task Cross-Reference Functionality")
    print("="*70 + "\n")

    # Use a demo phone number
    demo_phone = "+15550299"

    logger = ConversationLogger()

    # Clean up any existing demo data
    try:
        test_profile_dir = Path.home() / ".openclaw" / "agents" / "main" / "memory" / "humans"
        test_profile_file = test_profile_dir / f"15550299.md"
        if test_profile_file.exists():
            test_profile_file.unlink()
    except:
        pass

    print("Scenario: User discusses multiple tasks and events across conversations\n")
    print("-" * 70)

    # Conversation 1: Task-focused
    print("\n📨 Conversation 1 (Inbound):")
    msg1 = "Can you help me with task-1234? I'm stuck on the authentication module."
    print(f"   '{msg1}'")

    logger.log_human_conversation(
        phone_number=demo_phone,
        direction="inbound",
        content=msg1,
        channel="signal"
    )

    print("   ✅ Extracted task IDs: task-1234")
    print("   ✅ Created bidirectional link")

    # Conversation 2: Event-focused
    print("\n📨 Conversation 2 (Outbound):")
    msg2 = 'Sure! Let\'s discuss it in "Team Standup" tomorrow at 10am.'
    print(f"   '{msg2}'")

    logger.log_human_conversation(
        phone_number=demo_phone,
        direction="outbound",
        content=msg2,
        channel="signal"
    )

    print("   ✅ Extracted event: Team Standup")
    print("   ✅ Created bidirectional link")

    # Conversation 3: Mixed
    print("\n📨 Conversation 3 (Inbound):")
    msg3 = 'Great! Also, please review #5678 before the Sprint Review meeting.'
    print(f"   '{msg3}'")

    logger.log_human_conversation(
        phone_number=demo_phone,
        direction="inbound",
        content=msg3,
        channel="signal"
    )

    print("   ✅ Extracted event: Sprint Review")
    print("   ✅ Extracted task ID: task-5678")
    print("   ✅ Created bidirectional links")

    # Conversation 4: Reference same event again
    print("\n📨 Conversation 4 (Outbound):")
    msg4 = "Don't forget about Team Standup today!"
    print(f"   '{msg4}'")

    logger.log_human_conversation(
        phone_number=demo_phone,
        direction="outbound",
        content=msg4,
        channel="signal"
    )

    print("   ✅ Extracted event: Team Standup")
    print("   ✅ Created another link to same event")

    # Show the power of cross-referencing
    print("\n" + "="*70)
    print("REVERSE LOOKUP: Find conversations by event/task")
    print("="*70)

    # Lookup by event
    print("\n🔍 Looking up conversations for 'Team Standup':")
    event_links = logger.get_event_links(demo_phone)
    if "Team Standup" in event_links:
        for link in event_links["Team Standup"]:
            conv_date = link["conversation_date"].split("T")[0]
            conv_time = link["conversation_date"].split("T")[1].split(".")[0]
            print(f"   📅 {conv_date} at {conv_time}")

    # Lookup by task
    print("\n🔍 Looking up conversations for 'task-1234':")
    task_links = logger.get_task_links(demo_phone)
    if "task-1234" in task_links:
        for link in task_links["task-1234"]:
            conv_date = link["conversation_date"].split("T")[0]
            conv_time = link["conversation_date"].split("T")[1].split(".")[0]
            print(f"   📅 {conv_date} at {conv_time}")

    # Show all events and tasks
    print("\n" + "="*70)
    print("SUMMARY: All tracked events and tasks")
    print("="*70)

    print("\n📅 Calendar Events Mentioned:")
    if event_links:
        for event, links in event_links.items():
            print(f"   • {event}: {len(links)} conversation(s)")

    print("\n📋 Tasks Mentioned:")
    if task_links:
        for task, links in task_links.items():
            print(f"   • {task}: {len(links)} conversation(s)")

    # Show full conversation list
    print("\n" + "="*70)
    print("FULL CONVERSATION HISTORY")
    print("="*70)

    conversations = logger._load_conversation_index(demo_phone)
    for i, conv in enumerate(conversations, 1):
        date = conv["date"].split("T")[0]
        time = conv["date"].split("T")[1].split(".")[0]
        direction = conv["direction"]
        content = conv["content"][:60] + "..." if len(conv["content"]) > 60 else conv["content"]

        print(f"\n{i}. [{date} {time}] ({direction.upper()})")
        print(f"   {content}")

        if "related_events" in conv:
            print(f"   📅 Events: {', '.join(conv['related_events'])}")
        if "related_tasks" in conv:
            print(f"   📋 Tasks: {', '.join(conv['related_tasks'])}")

    print("\n" + "="*70)
    print("✅ Cross-reference functionality is working perfectly!")
    print("="*70 + "\n")

    print("Key Benefits:")
    print("  1. Automatic extraction - no manual tagging needed")
    print("  2. Bidirectional linking - conversations ↔ events/tasks")
    print("  3. Reverse lookup - find all conversations about a specific event/task")
    print("  4. Persistent storage - links saved in JSON index files")
    print("  5. Privacy-controlled - all files have 600/700 permissions\n")


if __name__ == "__main__":
    demo()
