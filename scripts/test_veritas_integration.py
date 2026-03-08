#!/usr/bin/env python3
"""
Test Veritas Integration - Test suite for Squad Chat, Crash Recovery, Enforcement Gates.

Usage:
    python3 test_veritas_integration.py --verbose
    python3 test_veritas_integration.py --test squad-chat
"""

import argparse
import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Add main scripts directory to path
MAIN_SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(MAIN_SCRIPTS_DIR))

# Change to main scripts directory for imports to work
import os
os.chdir(MAIN_SCRIPTS_DIR)


def test_squad_chat_basic():
    """Test basic squad chat client functionality."""
    print("Testing: Squad Chat basic client...")

    try:
        from squad_chat_client import SquadChatClient
        from squad_chat_events import Events, format_event_message

        # Test event formatting
        event_msg = format_event_message(Events.TASK_STARTED, {"task_id": "test-123"})
        assert "test-123" in event_msg or "test" in event_msg, f"Event message missing task_id: {event_msg}"

        print("  [PASS] Squad Chat client imports and event formatting work")
        return True
    except Exception as e:
        print(f"  [FAIL] Squad Chat basic test failed: {e}")
        return False


def test_checkpoint_save_resume():
    """Test checkpoint save and resume."""
    print("Testing: Checkpoint save/resume...")

    try:
        from checkpoint_manager import CheckpointManager

        manager = CheckpointManager()

        # Test save
        test_task_id = f"test-task-{int(datetime.now().timestamp())}"
        test_state = {
            "stage": "testing",
            "output_so_far": "This is test output with ANTHROPIC_API_KEY=sk-test-secret",
            "timestamp": datetime.now().isoformat()
        }

        checkpoint_id = manager.save_checkpoint(test_task_id, "temujin", test_state)
        assert checkpoint_id, "Failed to save checkpoint"
        print(f"  [INFO] Saved checkpoint: {checkpoint_id}")

        # Test load
        loaded = manager.load_checkpoint(test_task_id)
        assert loaded, "Failed to load checkpoint"
        assert loaded.task_id == test_task_id, f"Task ID mismatch: {loaded.task_id}"
        print(f"  [INFO] Loaded checkpoint: {loaded.id}")

        # Test clear
        assert manager.clear_checkpoint(test_task_id), "Failed to clear checkpoint"
        assert not manager.load_checkpoint(test_task_id), "Checkpoint still exists after clear"

        print("  [PASS] Checkpoint save/resume/clear works")
        return True
    except Exception as e:
        print(f"  [FAIL] Checkpoint test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_checkpoint_sanitization():
    """Verify secrets are sanitized in checkpoints."""
    print("Testing: Checkpoint secret sanitization...")

    try:
        from checkpoint_manager import CheckpointManager

        manager = CheckpointManager()

        test_task_id = f"test-sanitize-{int(datetime.now().timestamp())}"
        test_state = {
            "output": "ANTHROPIC_API_KEY=sk-ant-api03-secret-key-here\nOPENAI_API_KEY=sk-openai-secret",
            "config": {
                "password": "super_secret_password_123",
                "token": "bearer_token_xyz"
            }
        }

        checkpoint_id = manager.save_checkpoint(test_task_id, "temujin", test_state)
        assert checkpoint_id, "Failed to save checkpoint"

        loaded = manager.load_checkpoint(test_task_id)
        assert loaded, "Failed to load checkpoint"

        # Check that secrets are sanitized
        state_json = json.dumps(loaded.state)
        assert "sk-ant-api03-secret" not in state_json, "ANTHROPIC_API_KEY not sanitized"
        assert "sk-openai-secret" not in state_json, "OPENAI_API_KEY not sanitized"
        assert "super_secret_password" not in state_json, "password not sanitized"
        assert "bearer_token_xyz" not in state_json, "token not sanitized"

        # Check that *** markers are present
        assert "***" in state_json, "Sanitization markers not present"

        manager.clear_checkpoint(test_task_id)

        print("  [PASS] Checkpoint secret sanitization works")
        return True
    except Exception as e:
        print(f"  [FAIL] Sanitization test failed: {e}")
        return False


def test_enforcement_gates():
    """Test all 6 enforcement gates."""
    print("Testing: Enforcement Gates...")

    try:
        from enforcement_gates import EnforcementGates, GateResult

        gates = EnforcementGates()

        # Test status
        status = gates.get_status()
        assert "reviewGate" in status, "reviewGate missing from status"
        assert "closingComments" in status, "closingComments missing from status"
        assert "autoTelemetry" in status, "autoTelemetry missing from status"
        assert "autoTimeTracking" in status, "autoTimeTracking missing from status"
        assert "orchestratorDelegation" in status, "orchestratorDelegation missing from status"
        assert "squadChat" in status, "squadChat missing from status"
        print("  [INFO] All 6 gates present in status")

        # Test enable/disable
        assert gates.enable_gate("reviewGate"), "Failed to enable reviewGate"
        assert gates.disable_gate("reviewGate"), "Failed to disable reviewGate"
        assert gates.enable_gate("reviewGate"), "Failed to re-enable reviewGate"
        print("  [INFO] Gate enable/disable works")

        # Test individual gate checks
        context = {
            "task_content": "---\ntitle: Test task\n---\nThis is a test task.",
            "agent": "temujin",
            "skill_hint": "/systematic-debugging"
        }

        results = gates.check_all("test-task-123", context)

        # Count results
        passed = len([r for r in results if r.result == GateResult.PASS])
        warned = len([r for r in results if r.result == GateResult.WARN])
        skipped = len([r for r in results if r.result == GateResult.SKIP])

        print(f"  [INFO] Gate results: {passed} passed, {warned} warned, {skipped} skipped")

        print("  [PASS] Enforcement gates work")
        return True
    except Exception as e:
        print(f"  [FAIL] Enforcement gates test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests(verbose=False):
    """Run all integration tests."""
    print("=" * 60)
    print("Veritas Integration Test Suite")
    print("=" * 60)

    results = {
        "squad_chat_basic": test_squad_chat_basic(),
        "checkpoint_save_resume": test_checkpoint_save_resume(),
        "checkpoint_sanitization": test_checkpoint_sanitization(),
        "enforcement_gates": test_enforcement_gates(),
    }

    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)

    passed = 0
    failed = 0
    for name, result in results.items():
        status = "PASS" if result else "FAIL"
        if result:
            passed += 1
        else:
            failed += 1
        print(f"  [{status:4}] {name}")

    print(f"\nTotal: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


def main():
    parser = argparse.ArgumentParser(description="Veritas Integration Tests")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--test", "-t", choices=[
        "squad-chat", "checkpoint", "sanitization", "gates", "all"
    ], default="all", help="Run specific test")
    args = parser.parse_args()

    if args.test == "squad-chat":
        success = test_squad_chat_basic()
    elif args.test == "checkpoint":
        success = test_checkpoint_save_resume()
    elif args.test == "sanitization":
        success = test_checkpoint_sanitization()
    elif args.test == "gates":
        success = test_enforcement_gates()
    else:
        success = run_all_tests(args.verbose)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
