#!/usr/bin/env python3
"""
Integration Test Suite for Conversion Tracking System

Tests the complete flow:
1. Neo4j CRUD operations
2. File-based memory sync
3. Conversion context narrative
4. Funnel analytics
5. Privacy features (deletion)
"""

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_conversion_tracker import ConversionTracker
from conversion_context_memory import ConversionContextMemory, ConversionSync


class TestColors:
    """ANSI color codes for test output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_test_header(test_name: str):
    """Print a test header with formatting"""
    print(f"\n{TestColors.BOLD}{TestColors.BLUE}{'=' * 60}{TestColors.END}")
    print(f"{TestColors.BOLD}{TestColors.BLUE}TEST: {test_name}{TestColors.END}")
    print(f"{TestColors.BOLD}{TestColors.BLUE}{'=' * 60}{TestColors.END}")


def print_test_result(test_name: str, passed: bool, details: str = ""):
    """Print test result with color coding"""
    status = f"{TestColors.GREEN}✓ PASS{TestColors.END}" if passed else f"{TestColors.RED}✗ FAIL{TestColors.END}"
    print(f"{status}: {test_name}")
    if details:
        print(f"  {details}")


def test_1_track_first_touch():
    """Test 1: Track first touch event"""
    print_test_header("Test 1: Track First Touch Event")

    tracker = ConversionTracker()
    try:
        event = tracker.track_event(
            human_id=TEST_HUMAN_ID,
            event_type="first_touch",
            metadata={"source": "twitter", "campaign": "spring_launch"},
            ip_address="192.168.1.100"
        )

        passed = event is not None and event.get("event_id") is not None
        print_test_result(
            "First touch event tracked",
            passed,
            f"Event ID: {event.get('event_id') if event else 'None'}"
        )

        return passed
    finally:
        tracker.close()


def test_2_track_pricing_views():
    """Test 2: Track multiple pricing views"""
    print_test_header("Test 2: Track Pricing Views")

    tracker = ConversionTracker()
    try:
        # Track 3 pricing views
        for i in range(3):
            tracker.track_event(
                human_id=TEST_HUMAN_ID,
                event_type="pricing_view",
                metadata={"plan": "pro", "view_number": i + 1}
            )

        context = tracker.get_conversion_context(TEST_HUMAN_ID)
        passed = context is not None and context.get("pricing_views") == 3

        print_test_result(
            "Pricing views tracked",
            passed,
            f"Count: {context.get('pricing_views') if context else 0}"
        )

        return passed
    finally:
        tracker.close()


def test_3_checkout_flow():
    """Test 3: Track checkout flow (start, abort, start, complete)"""
    print_test_header("Test 3: Checkout Flow Tracking")

    tracker = ConversionTracker()
    try:
        # Start checkout
        tracker.track_event(
            human_id=TEST_HUMAN_ID,
            event_type="checkout_start",
            metadata={"plan": "pro_annual", "mrr": 7900}
        )

        # Abort checkout
        tracker.track_event(
            human_id=TEST_HUMAN_ID,
            event_type="checkout_abort",
            metadata={"reason": "Need to think about it"}
        )

        # Start again
        tracker.track_event(
            human_id=TEST_HUMAN_ID,
            event_type="checkout_start",
            metadata={"plan": "pro_monthly", "mrr": 7900}
        )

        # Complete checkout
        tracker.track_event(
            human_id=TEST_HUMAN_ID,
            event_type="checkout_complete",
            metadata={"plan": "pro_monthly", "payment_method": "stripe"}
        )

        context = tracker.get_conversion_context(TEST_HUMAN_ID)
        passed = context is not None and context.get("checkout_attempts") >= 2

        print_test_result(
            "Checkout flow tracked",
            passed,
            f"Attempts: {context.get('checkout_attempts') if context else 0}"
        )

        return passed
    finally:
        tracker.close()


def test_4_subscription_update():
    """Test 4: Update subscription status"""
    print_test_header("Test 4: Subscription Status Update")

    tracker = ConversionTracker()
    try:
        # Update to pro_monthly
        success = tracker.update_subscription(
            human_id=TEST_HUMAN_ID,
            status="pro_monthly",
            mrr_cents=7900,
            conversion_trigger="Team needed automated task review"
        )

        context = tracker.get_conversion_context(TEST_HUMAN_ID)
        passed = (success and
                context is not None and
                context.get("subscription_status") == "pro_monthly" and
                context.get("mrr_cents") == 7900)

        print_test_result(
            "Subscription updated",
            passed,
            f"Status: {context.get('subscription_status') if context else 'None'}, "
            f"MRR: ${context.get('mrr_cents', 0) / 100 if context else 0:.0f}"
        )

        return passed
    finally:
        tracker.close()


def test_5_file_based_memory():
    """Test 5: File-based memory sync"""
    print_test_header("Test 5: File-Based Memory Sync")

    memory = ConversionContextMemory()
    try:
        # Sync from Neo4j
        sync = ConversionSync()
        success = sync.sync_to_file(TEST_HUMAN_ID)
        sync.close()

        # Read from file
        context = memory.get_conversion_context(TEST_HUMAN_ID)
        passed = success and context is not None

        print_test_result(
            "File-based memory synced",
            passed,
            f"Context found: {bool(context)}"
        )

        if context:
            print(f"  Subscription in file: {context.get('subscription_status', 'N/A')}")
            print(f"  Pricing views in file: {context.get('pricing_views', 0)}")

        return passed
    finally:
        pass


def test_6_funnel_stats():
    """Test 6: Funnel analytics aggregation"""
    print_test_header("Test 6: Funnel Analytics")

    tracker = ConversionTracker()
    try:
        stats = tracker.get_funnel_stats(days=30)

        passed = (stats is not None and
                "total_leads" in stats and
                "converted" in stats and
                "conversion_rate" in stats)

        print_test_result(
            "Funnel stats retrieved",
            passed,
            f"Leads: {stats.get('total_leads', 0)}, "
            f"Converted: {stats.get('converted', 0)}, "
            f"Rate: {stats.get('conversion_rate', 0):.1%}"
        )

        return passed
    finally:
        tracker.close()


def test_7_top_sources():
    """Test 7: Top conversion sources"""
    print_test_header("Test 7: Top Conversion Sources")

    tracker = ConversionTracker()
    try:
        sources = tracker.get_top_conversion_sources(limit=5)

        passed = sources is not None and isinstance(sources, list)

        print_test_result(
            "Top sources retrieved",
            passed,
            f"Found {len(sources) if sources else 0} sources"
        )

        if sources:
            for source in sources[:3]:
                print(f"  - {source.get('source', 'Unknown')}: "
                      f"{source.get('converted', 0)} conversions "
                      f"({source.get('conversion_rate', 0):.1%})")

        return passed
    finally:
        tracker.close()


def test_8_data_deletion():
    """Test 8: Privacy - data deletion"""
    print_test_header("Test 8: Data Deletion (Privacy)")

    tracker = ConversionTracker()
    memory = ConversionContextMemory()
    try:
        # Delete from Neo4j
        success = tracker.delete_conversion_data(TEST_HUMAN_ID)

        # Verify deletion
        context = tracker.get_conversion_context(TEST_HUMAN_ID)
        neo4j_deleted = context is None

        # Remove from file-based memory
        memory.remove_conversion_context(TEST_HUMAN_ID)
        file_context = memory.get_conversion_context(TEST_HUMAN_ID)
        file_deleted = file_context is None or file_context == {}

        passed = success and neo4j_deleted

        print_test_result(
            "Data deleted",
            passed,
            f"Neo4j: {'Deleted' if neo4j_deleted else 'Still exists'}, "
            f"File: {'Deleted' if file_deleted else 'Still exists'}"
        )

        return passed
    finally:
        tracker.close()


# Test human ID
TEST_HUMAN_ID = "+19999999999"


def run_all_tests():
    """Run all integration tests"""
    print(f"\n{TestColors.BOLD}{TestColors.YELLOW}")
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 10 + "CONVERSION TRACKING INTEGRATION TESTS" + " " * 11 + "║")
    print("╚" + "═" * 58 + "╝")
    print(f"{TestColors.END}")

    results = []

    # Run all tests
    results.append(("First Touch", test_1_track_first_touch()))
    results.append(("Pricing Views", test_2_track_pricing_views()))
    results.append(("Checkout Flow", test_3_checkout_flow()))
    results.append(("Subscription", test_4_subscription_update()))
    results.append(("File Memory", test_5_file_based_memory()))
    results.append(("Funnel Stats", test_6_funnel_stats()))
    results.append(("Top Sources", test_7_top_sources()))
    results.append(("Data Deletion", test_8_data_deletion()))

    # Print summary
    print(f"\n{TestColors.BOLD}{TestColors.BLUE}{'=' * 60}{TestColors.END}")
    print(f"{TestColors.BOLD}TEST SUMMARY{TestColors.END}")
    print(f"{TestColors.BOLD}{TestColors.BLUE}{'=' * 60}{TestColors.END}\n")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = f"{TestColors.GREEN}✓{TestColors.END}" if result else f"{TestColors.RED}✗{TestColors.END}"
        print(f"{status} {test_name}")

    print(f"\n{TestColors.BOLD}Results: {passed}/{total} tests passed ({passed/total*100:.0f}%){TestColors.END}")

    if passed == total:
        print(f"\n{TestColors.GREEN}{TestColors.BOLD}ALL TESTS PASSED!{TestColors.END}\n")
        return 0
    else:
        print(f"\n{TestColors.RED}{TestColors.BOLD}SOME TESTS FAILED!{TestColors.END}\n")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
