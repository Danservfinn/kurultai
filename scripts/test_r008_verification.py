#!/usr/bin/env python3
"""
Test script for R008 skill invocation verification.

Tests that _verify_task_completion correctly detects when a required skill
was not invoked in the task execution output.
"""

import sys
import os
import tempfile
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import importlib.util

# Import agent-task-handler.py (hyphenated filename)
spec = importlib.util.spec_from_file_location("agent_task_handler", "agent-task-handler.py")
handler_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handler_module)
_verify_task_completion = handler_module._verify_task_completion


def create_test_task_file(skill_hint=None, include_skill_evidence=True):
    """Create a test .executing.md file with optional skill_hint."""
    fd, path = tempfile.mkstemp(suffix='.executing.md')

    # Build frontmatter
    frontmatter = [
        "---",
        f"task_id: test-{os.urandom(4).hex()}",
        f"priority: normal",
    ]
    if skill_hint:
        frontmatter.append(f"skill_hint: {skill_hint}")
    frontmatter.extend([
        "source: test",
        "---",
        "",
        "# Test Task",
        "",
        "This is a test task to verify R008 enforcement.",
        "",
        "## Execution Output",
        "",
        "**Model:** test-model",
        "**Duration:** 10s",
        "**Status:** Completed",
        "",
        "---",
        "",
    ])

    # Add execution output (longer to pass length checks)
    # Avoid words that might match skill evidence patterns
    output = [
        "Started working on the task.",
        "Analyzed the requirements carefully.",
        "Developed the solution step by step.",
        "Verified the changes work correctly.",
        "",
        "## Resolution",
        "",
        "The task has been completed successfully.",
        "All verification tests have passed.",
        "The solution is ready for deployment.",
        "",
    ]

    # Add skill-specific evidence if requested
    if include_skill_evidence and skill_hint:
        if skill_hint == '/horde-learn':
            output.extend([
                "",
                "**Research Findings:**",
                "- Searched web for relevant sources",
                "- Found 3 key citations from authoritative sources",
                "- Analyzed research methodology",
                "- Compiled findings into summary",
            ])
        elif skill_hint == '/horde-brainstorming':
            output.extend([
                "",
                "**Brainstorming Options:**",
                "1. Approach A: Design-focused solution",
                "2. Approach B: Implementation-focused",
                "3. Approach C: Hybrid strategy",
                "Evaluated each option for feasibility.",
            ])
        else:
            output.extend([
                "",
                f"Invoked {skill_hint} skill for execution.",
                "Proceeded with skill-guided analysis.",
                "Completed the task with skill assistance.",
            ])
    else:
        # Add truly generic output to pass length check but without skill evidence
        # Use words that won't accidentally match skill evidence patterns
        output.extend([
            "",
            "The work has been finished today.",
            "All items are now in the done state.",
            "Nothing else remains at this time.",
            "The final result is ready.",
            "Line five of generic output.",
            "Line six ensures we have enough content.",
        ])

    content = "\n".join(frontmatter) + "\n".join(output) + "\n"

    with os.fdopen(fd, 'w') as f:
        f.write(content)

    return path


def test_r008_violation_detected():
    """Test that R008 violation is detected when skill not invoked."""
    print("TEST 1: R008 violation should be detected...")
    task_file = create_test_task_file(skill_hint='/horde-learn', include_skill_evidence=False)
    try:
        is_valid, reason = _verify_task_completion(task_file)
        if not is_valid and "R008_VIOLATION" in reason:
            print("  ✓ PASS: R008 violation correctly detected")
            print(f"    Reason: {reason}")
            return True
        else:
            print(f"  ✗ FAIL: Expected R008 violation but got: is_valid={is_valid}, reason={reason}")
            return False
    finally:
        os.unlink(task_file)


def test_r008_pass_with_evidence():
    """Test that task passes when skill evidence is present."""
    print("TEST 2: Task should pass with skill invocation evidence...")
    task_file = create_test_task_file(skill_hint='/horde-learn', include_skill_evidence=True)
    try:
        is_valid, reason = _verify_task_completion(task_file)
        if is_valid:
            print("  ✓ PASS: Task validated with skill evidence")
            return True
        else:
            print(f"  ✗ FAIL: Task failed unexpectedly: {reason}")
            return False
    finally:
        os.unlink(task_file)


def test_no_skill_hint_passes():
    """Test that task without skill_hint passes normally."""
    print("TEST 3: Task without skill_hint should pass...")
    task_file = create_test_task_file(skill_hint=None, include_skill_evidence=False)
    try:
        is_valid, reason = _verify_task_completion(task_file)
        if is_valid:
            print("  ✓ PASS: Task without skill_hint validated")
            return True
        else:
            print(f"  ✗ FAIL: Task failed unexpectedly: {reason}")
            return False
    finally:
        os.unlink(task_file)


def test_multiple_skills():
    """Test R008 for various skill types."""
    print("TEST 4: Testing multiple skill types...")
    skills = ['/horde-learn', '/horde-brainstorming', '/horde-implement', '/horde-review']
    results = []

    for skill in skills:
        # Should fail without evidence
        task_file = create_test_task_file(skill_hint=skill, include_skill_evidence=False)
        try:
            is_valid, reason = _verify_task_completion(task_file)
            if not is_valid and "R008_VIOLATION" in reason:
                results.append(True)
            else:
                print(f"  ✗ FAIL: {skill} - expected violation but got: {reason}")
                results.append(False)
        finally:
            os.unlink(task_file)

        # Should pass with evidence
        task_file = create_test_task_file(skill_hint=skill, include_skill_evidence=True)
        try:
            is_valid, reason = _verify_task_completion(task_file)
            if is_valid:
                results.append(True)
            else:
                print(f"  ✗ FAIL: {skill} - unexpected failure: {reason}")
                results.append(False)
        finally:
            os.unlink(task_file)

    if all(results):
        print(f"  ✓ PASS: All {len(skills)} skill types tested correctly")
        return True
    else:
        print(f"  ✗ FAIL: {results.count(False)}/{len(results)} tests failed")
        return False


def main():
    """Run all R008 verification tests."""
    print("=" * 60)
    print("R008 Skill Invocation Verification Tests")
    print("=" * 60)
    print()

    results = [
        test_r008_violation_detected(),
        test_r008_pass_with_evidence(),
        test_no_skill_hint_passes(),
        test_multiple_skills(),
    ]

    print()
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    if all(results):
        print(f"✓ ALL TESTS PASSED ({passed}/{total})")
        return 0
    else:
        print(f"✗ SOME TESTS FAILED ({passed}/{total} passed)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
