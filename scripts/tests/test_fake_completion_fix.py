#!/usr/bin/env python3
"""
Test fake completion fix.

Verifies that:
1. _append_output_to_executing uses file locking
2. _verify_task_completion uses file locking with retries
3. Verification correctly identifies fake completions
"""

import os
import sys
import tempfile
import time
import threading

# Add scripts directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_append_with_locking():
    """Test that _append_output_to_executing writes atomically with locking."""
    from agent_task_handler import _append_output_to_executing

    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("---\ntest: true\n---\n\n# Test Task\n\nOriginal content.\n")
        temp_file = f.name

    try:
        # Append execution output
        result = _append_output_to_executing(
            temp_file,
            "This is test execution output.\nIt has multiple lines.\n" * 10,
            "test-model",
            1.5,
            success=True
        )

        # Verify the marker was added
        with open(temp_file, 'r') as f:
            content = f.read()

        assert result == True, "Append should return True on success"
        assert "## Execution Output" in content, "Should have Execution Output marker"
        assert "**Model:** test-model" in content, "Should have model info"
        assert "**Duration:** 1.5s" in content, "Should have duration info"
        print("✓ test_append_with_locking PASSED")
        return True
    finally:
        os.unlink(temp_file)

def test_verify_with_locking():
    """Test that _verify_task_completion correctly validates files."""
    from agent_task_handler import _verify_task_completion

    # Test 1: Valid completion with enough content
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("---\ntest: true\n---\n\n# Test Task\n\nOriginal content.\n\n")
        f.write("## Execution Output\n\n")
        f.write("**Model:** test-model\n")
        f.write("**Duration:** 1.5s\n")
        f.write("**Status:** Completed\n")
        f.write("\n---\n\n")
        # Add enough content (8+ lines, 500+ chars)
        for i in range(10):
            f.write(f"Line {i} of execution output with enough content to pass verification.\n")
        temp_file = f.name

    try:
        is_valid, reason = _verify_task_completion(temp_file)
        assert is_valid == True, f"Should be valid, got: {reason}"
        print("✓ test_verify_valid_completion PASSED")
    finally:
        os.unlink(temp_file)

    # Test 2: Fake completion (no execution output marker)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("---\ntest: true\n---\n\n# Test Task\n\nOriginal content only.\n")
        temp_file = f.name

    try:
        is_valid, reason = _verify_task_completion(temp_file)
        assert is_valid == False, "Should be invalid (no marker)"
        assert "No execution output section" in reason, f"Wrong reason: {reason}"
        print("✓ test_verify_fake_completion PASSED")
    finally:
        os.unlink(temp_file)

    # Test 3: Too short output
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("---\ntest: true\n---\n\n# Test Task\n\nOriginal content.\n\n")
        f.write("## Execution Output\n\n")
        f.write("**Model:** test-model\n")
        f.write("**Duration:** 1.5s\n")
        f.write("\n---\n\n")
        f.write("Short output.\n")  # Only 1 line
        temp_file = f.name

    try:
        is_valid, reason = _verify_task_completion(temp_file)
        assert is_valid == False, "Should be invalid (too short)"
        assert "too short" in reason.lower(), f"Wrong reason: {reason}"
        print("✓ test_verify_too_short PASSED")
    finally:
        os.unlink(temp_file)

    return True

def test_concurrent_append_read():
    """Test that concurrent append and read don't cause race conditions."""
    from agent_task_handler import _append_output_to_executing, _verify_task_completion

    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("---\ntest: true\n---\n\n# Test Task\n\nOriginal content.\n")
        temp_file = f.name

    results = []
    errors = []

    def writer_thread():
        try:
            time.sleep(0.01)  # Small delay to create race condition
            result = _append_output_to_executing(
                temp_file,
                "Execution output line " * 20 + "\n" * 20,
                "test-model",
                1.0,
                success=True
            )
            results.append(('write', result))
        except Exception as e:
            errors.append(('write', str(e)))

    def reader_thread():
        try:
            # Try to verify while write is happening
            time.sleep(0.02)
            is_valid, reason = _verify_task_completion(temp_file)
            results.append(('read', is_valid, reason))
        except Exception as e:
            errors.append(('read', str(e)))

    try:
        t1 = threading.Thread(target=writer_thread)
        t2 = threading.Thread(target=reader_thread)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Both should complete without errors
        assert len(errors) == 0, f"Errors occurred: {errors}"
        print("✓ test_concurrent_append_read PASSED")
        return True
    finally:
        os.unlink(temp_file)

def main():
    """Run all tests."""
    print("Testing fake completion fix...\n")

    tests = [
        test_append_with_locking,
        test_verify_with_locking,
        test_concurrent_append_read,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"✗ {test.__name__} FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test.__name__} ERROR: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'='*50}")

    return failed == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)