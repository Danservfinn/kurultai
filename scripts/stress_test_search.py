#!/usr/bin/env python3
"""
Stress test for conversation search with synthetic data.

Creates a large dataset to verify search performance scales well.
"""

import sys
import os
import time
import random
from datetime import datetime, timedelta
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from conversation_search import ConversationSearch
from human_profile_memory import HumanProfileMemory


def generate_synthetic_conversations(phone: str, count: int = 1000):
    """Generate synthetic conversations for stress testing."""
    print(f"Generating {count} synthetic conversations for {phone}...")

    memory = HumanProfileMemory("main")
    profile = memory.read_profile(phone)

    if not profile:
        print(f"Error: Profile {phone} not found")
        return

    topics = [
        "calendar", "task", "code", "business", "general",
        "meeting", "deploy", "bug", "feature", "review",
        "standup", "planning", "release", "hotfix", "testing"
    ]

    contexts = ["calendar", "task", "code", "business", "general"]
    sentiments = ["positive", "negative", "neutral"]

    base_date = datetime.now() - timedelta(days=365)

    synthetic_conversations = []

    for i in range(count):
        # Generate random date within last year
        days_ago = random.randint(0, 365)
        conv_date = base_date + timedelta(days=days_ago)

        # Generate random content
        topic_words = [
            "meeting", "deploy", "code", "review", "bug", "feature",
            "standup", "planning", "release", "hotfix", "testing",
            "authentication", "database", "api", "frontend", "backend"
        ]

        content_words = random.sample(topic_words, random.randint(3, 8))
        content = f"Discussion about {' '.join(content_words)} and related topics."

        conversation = {
            "date": conv_date.isoformat(),
            "content": content,
            "topics": random.sample(topics, random.randint(1, 3)),
            "context": random.choice(contexts),
            "sentiment": random.choice(sentiments),
            "action_items": [
                f"Action item {j}" for j in range(random.randint(0, 3))
            ],
            "direction": random.choice(["inbound", "outbound"]),
            "channel": "signal"
        }

        synthetic_conversations.append(conversation)

    # Add to profile
    profile["conversations"].extend(synthetic_conversations)
    memory.write_profile(phone, profile)

    print(f"Generated {len(synthetic_conversations)} conversations")
    print(f"Total conversations in profile: {len(profile['conversations'])}")


def stress_test_search_performance(phone: str, conversation_count: int):
    """Stress test search with various query types."""
    print("\n" + "=" * 60)
    print(f"STRESS TEST: {conversation_count} conversations")
    print("=" * 60 + "\n")

    search = ConversationSearch()

    # Rebuild indices with new data
    print("Rebuilding indices...")
    start = time.time()
    search._build_indices()
    index_time = time.time() - start
    print(f"Index building: {index_time:.3f}s")
    print()

    results = {}

    # Test 1: Simple text search
    print("Test 1: Simple text search")
    start = time.time()
    search_results = search.search_user(phone, "meeting", limit=100)
    elapsed = time.time() - start
    results['simple_search'] = elapsed
    status = "✓ PASS" if elapsed < 5.0 else "✗ FAIL"
    print(f"  Time: {elapsed:.3f}s {status} ({len(search_results)} results)")
    print()

    # Test 2: Topic-based search
    print("Test 2: Topic-based search")
    start = time.time()
    search_results = search.search_by_topics(phone, ["calendar"], limit=100)
    elapsed = time.time() - start
    results['topic_search'] = elapsed
    status = "✓ PASS" if elapsed < 1.0 else "✗ FAIL"
    print(f"  Time: {elapsed:.3f}s {status} ({len(search_results)} results)")
    print()

    # Test 3: Date range search
    print("Test 3: Date range search (last 30 days)")
    date_to = datetime.now()
    date_from = date_to - timedelta(days=30)
    start = time.time()
    search_results = search.search_user(
        phone, "test", date_from=date_from, date_to=date_to, limit=100
    )
    elapsed = time.time() - start
    results['date_search'] = elapsed
    status = "✓ PASS" if elapsed < 2.0 else "✗ FAIL"
    print(f"  Time: {elapsed:.3f}s {status} ({len(search_results)} results)")
    print()

    # Test 4: Combined filters
    print("Test 4: Combined filters (context + sentiment + date)")
    start = time.time()
    search_results = search.search_user(
        phone,
        "meeting",
        context_filter="calendar",
        sentiment_filter="neutral",
        date_from=date_from,
        date_to=date_to,
        limit=100
    )
    elapsed = time.time() - start
    results['combined_filters'] = elapsed
    status = "✓ PASS" if elapsed < 5.0 else "✗ FAIL"
    print(f"  Time: {elapsed:.3f}s {status} ({len(search_results)} results)")
    print()

    # Test 5: Large result set with pagination
    print("Test 5: Large result set (1000 results)")
    start = time.time()
    search_results = search.search_user(phone, "test", limit=1000)
    elapsed = time.time() - start
    results['large_result'] = elapsed
    status = "✓ PASS" if elapsed < 5.0 else "✗ FAIL"
    print(f"  Time: {elapsed:.3f}s {status} ({len(search_results)} results)")
    print()

    # Test 6: Pagination performance
    print("Test 6: Pagination performance (10 pages)")
    page_times = []
    for i in range(10):
        offset = i * 50
        start = time.time()
        page = search.search_user(phone, "test", limit=50, offset=offset)
        page_time = time.time() - start
        page_times.append(page_time)

    avg_page_time = sum(page_times) / len(page_times)
    results['pagination'] = avg_page_time
    status = "✓ PASS" if avg_page_time < 1.0 else "✗ FAIL"
    print(f"  Avg: {avg_page_time:.3f}s {status}")
    print(f"  Min: {min(page_times):.3f}s")
    print(f"  Max: {max(page_times):.3f}s")
    print()

    # Summary
    print("=" * 60)
    print("STRESS TEST SUMMARY")
    print("=" * 60)
    print()

    all_passed = True
    for test_name, elapsed in results.items():
        target = 5.0
        if test_name in ['topic_search', 'pagination']:
            target = 1.0
        elif test_name == 'date_search':
            target = 2.0

        status = "✓ PASS" if elapsed < target else "✗ FAIL"
        if elapsed >= target:
            all_passed = False
        print(f"{test_name:20s}: {elapsed:6.3f}s {status} (target: {target}s)")

    print()
    if all_passed:
        print("✓ All stress tests PASSED")
    else:
        print("✗ Some stress tests FAILED")

    return all_passed


def main():
    """Run stress tests with increasing dataset sizes."""
    print("=" * 60)
    print("Conversation Search Stress Test")
    print("=" * 60)
    print()

    memory = HumanProfileMemory("main")
    phones = memory.list_profiles()

    if not phones:
        print("Error: No profiles found")
        sys.exit(1)

    test_phone = phones[0]

    # Test with different dataset sizes
    test_sizes = [100, 500, 1000, 2000]

    all_results = {}

    for size in test_sizes:
        print(f"\n{'=' * 60}")
        print(f"Testing with {size} conversations")
        print(f"{'=' * 60}\n")

        # Generate synthetic data
        generate_synthetic_conversations(test_phone, size)

        # Run stress test
        passed = stress_test_search_performance(test_phone, size)
        all_results[size] = passed

        # Clean up for next test (remove synthetic data)
        print("Cleaning up synthetic data...")
        profile = memory.read_profile(test_phone)
        # Keep only original conversations (first 100)
        if len(profile.get("conversations", [])) > 100:
            profile["conversations"] = profile["conversations"][:100]
            memory.write_profile(test_phone, profile)
        print("Cleanup complete\n")

    # Final summary
    print("\n" + "=" * 60)
    print("FINAL STRESS TEST SUMMARY")
    print("=" * 60)
    print()

    for size, passed in all_results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{size:6d} conversations: {status}")

    print()
    if all(all_results.values()):
        print("✓ All stress tests PASSED across all dataset sizes")
        sys.exit(0)
    else:
        print("✗ Some stress tests FAILED at larger dataset sizes")
        sys.exit(1)


if __name__ == "__main__":
    main()
