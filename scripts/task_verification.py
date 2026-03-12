#!/usr/bin/env python3
"""
task_verification.py - Shared task verification utilities.

Consolidates duplicate code between task-watcher.py and agent-task-handler.py.
"""

import os
import time
import fcntl
import re


SLOW_SKILLS = {
    '/horde-brainstorming': 7200,
    '/golden-horde': 7200,
    '/horde-implement': 7200,
    '/horde-review': 7200,
    '/horde-debug': 7200,
    '/horde-learn': 7200,
    '/horde-swarm': 7200,
    '/horde-test': 7200,
}


def verify_task_completion(task_file: str, max_retries: int = 3) -> tuple[bool, str]:
    """Verify task file has actual execution output before marking as complete.

    CRITICAL FIX: This function requires the presence of an "## Execution Output"
    section to distinguish actual execution results from the original task description.

    RACE CONDITION FIX (2026-03-08): Uses file locking to prevent false positives
    when the handler is still writing output. If verification fails, retries with
    exponential backoff to handle slow writes.

    RESOLUTION CHECK (2026-03-09): Substantive completions (>=100 chars) must include
    a resolution section ("## Resolution" or similar) matching /horde-review PRIORITY_FIX.

    Checks:
    - Has "## Execution Output" section (added by _append_output_to_executing)
    - Content AFTER "## Execution Output" has substance (not just empty)
    - At least 4 non-empty lines of actual execution output
    - Resolution section present for substantive outputs (>=100 chars)

    Returns tuple: (is_valid, reason)
    """
    for attempt in range(max_retries):
        try:
            # Acquire shared lock to wait for any writer to finish
            # LOCK_SH (shared) will block if another process has LOCK_EX (exclusive)
            fd = None
            try:
                fd = os.open(task_file, os.O_RDONLY)
                fcntl.flock(fd, fcntl.LOCK_SH)  # Wait for exclusive lock to release
            except (FileNotFoundError, OSError):
                # File might have been renamed between check and open
                if attempt < max_retries - 1:
                    time.sleep(0.1 * (2 ** attempt))  # Exponential backoff
                    continue
                else:
                    return False, f"Verification error: file unavailable after {max_retries} retries"

            try:
                with open(fd, 'r', closefd=False) as f:
                    content = f.read()

                if not content:
                    return False, "Empty task file"

                # Check for execution marker
                exec_marker = "## Execution Output"
                if exec_marker not in content:
                    # Check for alternative markers
                    alt_markers = ["## Result", "## Summary", "## Implementation"]
                    has_marker = any(m in content for m in alt_markers)
                    if not has_marker:
                        return False, "No execution output section found"

                # Find the output section
                output_section = content
                for marker in [exec_marker, "## Result", "## Summary", "## Implementation"]:
                    if marker in content:
                        output_section = content.split(marker, 1)[-1]
                        break

                # Check for substance
                output_lines = [l.strip() for l in output_section.split('\n') if l.strip()]
                if len(output_lines) < 4:
                    return False, f"Execution output too short ({len(output_lines)} lines, need 4+)"

                # Check for resolution section on substantive outputs
                # Matches audit_missing_resolutions.py patterns including auto-generated reports
                if len(output_section) >= 100:
                    resolution_patterns = [
                        r"## Resolution",              # Explicit resolution (preferred)
                        r"## What Was Done",           # Auto-generated report standard
                        r"## Summary",                 # Alternative summary header
                        r"## Changes Made",            # Change-focused summary
                        r"## Files (Created|Modified)",# File-centric summary
                        r"## Acceptance Criteria",     # Verification-focused
                        r"## Deliverables",            # Output-focused (auto-generated)
                    ]
                    has_resolution = any(
                        re.search(p, output_section, re.IGNORECASE)
                        for p in resolution_patterns
                    )
                    if not has_resolution:
                        # Allow if has code blocks or file references
                        has_code = "```" in output_section or ".py" in output_section
                        if not has_code:
                            return False, "Substantive output missing resolution section"

                return True, "Valid execution output"

            finally:
                if fd is not None:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_UN)
                        os.close(fd)
                    except:
                        pass

        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(0.1 * (2 ** attempt))
                continue
            return False, f"Verification error: {e}"

    return False, "Max retries exceeded"
