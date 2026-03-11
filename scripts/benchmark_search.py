#!/usr/bin/env python3
"""
Benchmark script for conversation search performance.

Tests search performance with various query types and dataset sizes.
"""

import sys
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from conversation_search import ConversationSearch
from human_profile_memory import HumanProfileMemory


def benchmark_index_building(search: ConversationSearch) -> float:
    """Benchmark index building time."""
    print("Benchmark: Index Building")
    print("-" * 40)

    start = time.time()
    search._build_indices()
    elapsed = time.time() - start

    print(f"Index building time: {elapsed:.3f}s")
    print(f"Topic index entries: {len(search.topic_index)}")
    print(f"Date index entries: {len(search.date_index)}")
    print(f"Content index entries: {len(search.content_index)}")
    print(f"Context index entries: {len(search.context_index)}")
    print(f"Sentiment index entries: {len(search.sentiment_index)}")
    print()

    return elapsed


def benchmark_text_search(search: ConversationSearch, phone: str, query: str) -> float:
    """Benchmark full-text search."""
    print(f"Benchmark: Text Search '{query}'")
    print("-" * 40)

    start = time.time()
    results = search.search_user(phone, query, limit=50)
    elapsed = time.time() - start

    print(f"Search time: {elapsed:.3f}s")
    print(f"Results found: {len(results)}")
    print(f"Average per result: {elapsed/max(len(results), 1)*1000:.2f}ms")
    print()

    return elapsed


def benchmark_topic_search(search: ConversationSearch, phone: str, topics: list) -> float:
    """Benchmark topic-based search."""
    print(f"Benchmark: Topic Search {topics}")
    print("-" * 40)

    start = time.time()
    results = search.search_by_topics(phone, topics, limit=50)
    elapsed = time.time() - start

    print(f"Search time: {elapsed:.3f}s")
    print(f"Results found: {len(results)}")
    print(f"Average per result: {elapsed/max(len(results), 1)*1000:.2f}ms")
    print()

    return elapsed


def benchmark_date_range_search(search: ConversationSearch, phone: str) -> float:
    """Benchmark date range search."""
    print("Benchmark: Date Range Search (last 30 days)")
    print("-" * 40)

    date_to = datetime.now()
    date_from = date_to - timedelta(days=30)

    start = time.time()
    results = search.search_user(
        phone,
        "test",
        date_from=date_from,
        date_to=date_to,
        limit=100
    )
    elapsed = time.time() - start

    print(f"Search time: {elapsed:.3f}s")
    print(f"Results found: {len(results)}")
    print(f"Average per result: {elapsed/max(len(results), 1)*1000:.2f}ms")
    print()

    return elapsed


def benchmark_combined_filters(search: ConversationSearch, phone: str) -> float:
    """Benchmark combined filters."""
    print("Benchmark: Combined Filters (context + sentiment + date)")
    print("-" * 40)

    date_to = datetime.now()
    date_from = date_to - timedelta(days=30)

    start = time.time()
    results = search.search_user(
        phone,
        "meeting",
        context_filter="calendar",
        sentiment_filter="neutral",
        date_from=date_from,
        date_to=date_to,
        limit=50
    )
    elapsed = time.time() - start

    print(f"Search time: {elapsed:.3f}s")
    print(f"Results found: {len(results)}")
    print(f"Average per result: {elapsed/max(len(results), 1)*1000:.2f}ms")
    print()

    return elapsed


def benchmark_pagination(search: ConversationSearch, phone: str) -> float:
    """Benchmark pagination with large result sets."""
    print("Benchmark: Pagination (1000 results)")
    print("-" * 40)

    # First, get a large result set
    start = time.time()
    results = search.search_user(
        phone,
        "test",
        limit=1000,
        offset=0
    )
    elapsed = time.time() - start

    print(f"Search time: {elapsed:.3f}s")
    print(f"Results found: {len(results)}")

    # Test pagination
    page_times = []
    for offset in [0, 50, 100, 200, 500]:
        start = time.time()
        page = search.search_user(
            phone,
            "test",
            limit=50,
            offset=offset
        )
        page_time = time.time() - start
        page_times.append(page_time)
        print(f"  Page offset {offset}: {page_time:.3f}s ({len(page)} results)")

    print(f"Average page time: {sum(page_times)/len(page_times):.3f}s")
    print()

    return elapsed


def benchmark_large_dataset(search: ConversationSearch) -> float:
    """Benchmark search across all users."""
    print("Benchmark: Large Dataset Search (all users)")
    print("-" * 40)

    start = time.time()
    results = search.search_all(
        "meeting",
        total_limit=200
    )
    elapsed = time.time() - start

    print(f"Search time: {elapsed:.3f}s")
    print(f"Results found: {len(results)}")
    print(f"Average per result: {elapsed/max(len(results), 1)*1000:.2f}ms")
    print()

    return elapsed


def main():
    """Run all benchmarks."""
    print("=" * 60)
    print("Conversation Search Performance Benchmark")
    print("=" * 60)
    print()

    # Initialize search
    print("Initializing search engine...")
    search = ConversationSearch()

    # Get test phone number
    memory = HumanProfileMemory("main")
    phones = memory.list_profiles()

    if not phones:
        print("Error: No profiles found to benchmark")
        sys.exit(1)

    test_phone = phones[0]
    print(f"Testing with phone: {test_phone}")
    print(f"Total profiles: {len(phones)}")
    print()

    # Run benchmarks
    results = {}

    try:
        results['index_building'] = benchmark_index_building(search)
        results['text_search'] = benchmark_text_search(search, test_phone, "meeting")
        results['topic_search'] = benchmark_topic_search(search, test_phone, ["calendar"])
        results['date_range'] = benchmark_date_range_search(search, test_phone)
        results['combined_filters'] = benchmark_combined_filters(search, test_phone)
        results['pagination'] = benchmark_pagination(search, test_phone)
        results['large_dataset'] = benchmark_large_dataset(search)

        # Summary
        print("=" * 60)
        print("BENCHMARK SUMMARY")
        print("=" * 60)
        print()

        all_passed = True
        for benchmark_name, elapsed in results.items():
            status = "✓ PASS" if elapsed < 5.0 else "✗ FAIL"
            if elapsed >= 5.0:
                all_passed = False
            print(f"{benchmark_name:20s}: {elapsed:6.3f}s {status}")

        print()
        if all_passed:
            print("✓ All benchmarks PASSED (< 5s target)")
        else:
            print("✗ Some benchmarks FAILED (> 5s target)")

        print()
        print("Performance Targets:")
        print("  - Index building: < 10s")
        print("  - Text search: < 5s")
        print("  - Topic search: < 1s")
        print("  - Date range: < 2s")
        print("  - Combined filters: < 5s")
        print("  - Pagination: < 1s per page")
        print("  - Large dataset: < 10s")

        sys.exit(0 if all_passed else 1)

    except Exception as e:
        print(f"Error during benchmark: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
