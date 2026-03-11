#!/usr/bin/env python3
"""
Test pattern matching for terminal task states in ogedei-watchdog.py
Validates that files with suffixes like .revision-1.md are properly recognized as terminal states.
"""

def is_terminal_state_old(filename: str) -> bool:
    """OLD implementation - uses endswith() - BUGGY"""
    return any(filename.endswith(suffix) for suffix in (
        ".verified.done.md",
        ".verified.completed.done.md",
        ".verified.failed.done.md",
        ".resolved.md",
        ".orphan-resolved.md",
    ))

def is_terminal_state_new(filename: str) -> bool:
    """NEW implementation - uses substring matching - FIXED"""
    return any(pattern in filename for pattern in (
        ".verified.done.",
        ".verified.completed.done.",
        ".verified.failed.done.",
        ".resolved.",
        ".orphan-resolved.",
    ))

# Test cases
test_cases = [
    # (filename, expected_result, description)
    # Terminal states - should be True
    ("task.verified.done.md", True, "Basic verified done"),
    ("task.verified.completed.done.md", True, "Verified completed"),
    ("task.verified.failed.done.md", True, "Verified failed"),
    ("task.resolved.md", True, "Basic resolved"),
    ("task.orphan-resolved.md", True, "Basic orphan-resolved"),

    # Terminal states WITH suffixes - the bug cases
    ("ESCALATE-stale-task-ogedei-low-1773005550-20260308-190942.orphan-resolved.revision-1.md", True, "Orphan-resolved with revision suffix"),
    ("task.resolved.revision-2.md", True, "Resolved with revision suffix"),
    ("task.verified.done.revision-1.md", True, "Verified done with revision suffix"),
    ("task.orphan-resolved.v2.md", True, "Orphan-resolved with version suffix"),

    # Non-terminal states - should be False
    ("task.executing.md", False, "Executing task"),
    ("task.pending.md", False, "Pending task"),
    ("task.in_progress.md", False, "In progress task"),
    ("task.done.md", False, "Done without verified"),
    ("ESCALATE-stale-task-xxx.executing.md", False, "Escalation executing"),
]

def run_tests():
    """Run all test cases and report results"""
    print("=" * 70)
    print("Testing OLD implementation (endswith - BUGGY)")
    print("=" * 70)

    old_passed = 0
    old_failed = 0

    for filename, expected, description in test_cases:
        result = is_terminal_state_old(filename)
        status = "PASS" if result == expected else "FAIL"

        if result == expected:
            old_passed += 1
        else:
            old_failed += 1
            print(f"\n[FAIL] {description}")
            print(f"  File: {filename}")
            print(f"  Expected: {expected}, Got: {result}")

    print(f"\nOLD implementation: {old_passed} passed, {old_failed} failed")

    print("\n" + "=" * 70)
    print("Testing NEW implementation (substring matching - FIXED)")
    print("=" * 70)

    new_passed = 0
    new_failed = 0

    for filename, expected, description in test_cases:
        result = is_terminal_state_new(filename)
        status = "PASS" if result == expected else "FAIL"

        if result == expected:
            new_passed += 1
            print(f"[PASS] {description}")
        else:
            new_failed += 1
            print(f"\n[FAIL] {description}")
            print(f"  File: {filename}")
            print(f"  Expected: {expected}, Got: {result}")

    print(f"\nNEW implementation: {new_passed} passed, {new_failed} failed")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"OLD (buggy):  {old_passed}/{len(test_cases)} passed ({old_failed} failures)")
    print(f"NEW (fixed):  {new_passed}/{len(test_cases)} passed ({new_failed} failures)")

    if new_failed == 0:
        print("\n✓ All tests passed! Fix is correct.")
        return 0
    else:
        print(f"\n✗ {new_failed} tests failed. Fix needs adjustment.")
        return 1

if __name__ == "__main__":
    exit(run_tests())
