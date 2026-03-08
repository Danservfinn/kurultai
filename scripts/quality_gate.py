#!/usr/bin/env python3
"""
Completion Quality Gate — Post-completion quality verification.

Checks task completions against quality thresholds:
- Low content: < 500 chars
- Weak structure: < 3 headings
- Missing resolution: No resolution section

Provides auto-retry with feedback and escalation to Kublai.
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).parent))
from kurultai_paths import AGENTS_DIR, LOGS_DIR

# Quality thresholds
QUALITY_THRESHOLDS = {
    "min_chars": 500,
    "min_headings": 3,
    "min_code_blocks": 0,  # Optional
    "must_have_resolution": True,
    "max_retries": 2,
}

# Quality feedback log
QUALITY_LOG = LOGS_DIR / "quality-gate-log.jsonl"


class QualityResult:
    """Result of quality verification."""

    def __init__(
        self,
        passed: bool,
        action: Literal["pass", "retry", "escalate"] = "pass",
        issues: list | None = None,
        reason: str = "",
        retry_count: int = 0,
    ):
        self.passed = passed
        self.action = action
        self.issues = issues or []
        self.reason = reason
        self.retry_count = retry_count

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "action": self.action,
            "issues": self.issues,
            "reason": self.reason,
            "retry_count": self.retry_count,
        }


class CompletionQualityGate:
    """Post-completion quality verification with auto-retry."""

    def __init__(self, thresholds: dict | None = None):
        self.thresholds = thresholds or QUALITY_THRESHOLDS.copy()

    def verify_completion(self, task_file: Path) -> QualityResult:
        """Verify task completion meets quality standards.

        Args:
            task_file: Path to the .done.md completion file

        Returns:
            QualityResult with action (pass|retry|escalate)
        """
        if not task_file.exists():
            return QualityResult(passed=False, action="pass", issues=["File not found"])

        try:
            content = task_file.read_text()
        except Exception as e:
            return QualityResult(passed=False, action="escalate", issues=[f"Cannot read file: {e}"])

        # Extract the task output (remove frontmatter if present)
        output = self.extract_output(content)

        # Check quality metrics
        char_count = len(output.strip())
        headings = len(re.findall(r"^#+\s", output, re.MULTILINE))
        code_blocks = len(re.findall(r"```", output)) // 2
        has_resolution = (
            "## Resolution" in output
            or "**Status:**" in output
            or "## Result" in output
            or "## Summary" in output
        )

        issues = []

        if char_count < self.thresholds["min_chars"]:
            issues.append(
                f"Low content: {char_count} chars (need {self.thresholds['min_chars']})"
            )

        if headings < self.thresholds["min_headings"]:
            issues.append(
                f"Weak structure: {headings} headings (need {self.thresholds['min_headings']})"
            )

        if (
            self.thresholds["must_have_resolution"]
            and not has_resolution
            and char_count >= 100  # Only require resolution for substantive content
        ):
            issues.append("Missing resolution section")

        # Check if it's a trivial completion (e.g., just "OK" or similar)
        if char_count < 50:
            issues.append(f"Trivial completion: only {char_count} chars")

        # If no issues, pass
        if not issues:
            return QualityResult(passed=True, action="pass")

        # Check retry count
        retry_count = self.get_retry_count(task_file)

        if retry_count >= self.thresholds["max_retries"]:
            # Max retries reached, escalate
            self._log_quality_event(task_file, issues, "escalate", retry_count)
            return QualityResult(
                passed=False,
                action="escalate",
                issues=issues,
                reason=f"Max retries ({retry_count}) reached",
                retry_count=retry_count,
            )

        # Mark for revision
        self.mark_for_revision(task_file, issues, retry_count + 1)
        self._log_quality_event(task_file, issues, "retry", retry_count + 1)

        return QualityResult(
            passed=False,
            action="retry",
            issues=issues,
            reason=f"Retry #{retry_count + 1}",
            retry_count=retry_count + 1,
        )

    def extract_output(self, content: str) -> str:
        """Extract the task output from completion file.

        Removes YAML frontmatter and extracts the actual output.
        """
        lines = content.split("\n")

        # Check for YAML frontmatter
        if lines and lines[0].strip() == "---":
            # Find end of frontmatter
            for i, line in enumerate(lines[1:], 1):
                if line.strip() == "---":
                    return "\n".join(lines[i + 1 :])
            # No closing ---, return everything after first line
            return "\n".join(lines[1:])

        return content

    def get_retry_count(self, task_file: Path) -> int:
        """Check how many times this task has been retried.

        Looks for .revision-1.md, .revision-2.md patterns.
        """
        stem = task_file.stem
        # Extract base name (remove .done, .completed, etc.)
        base = stem
        for suffix in [".done", ".completed", ".verified", ".unverified", ".no_output"]:
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break

        # Look for existing revision files
        parent = task_file.parent
        revision_pattern = re.compile(rf"^{re.escape(base)}\.revision-(\d+)\.md$")

        max_retry = 0
        for f in parent.iterdir():
            m = revision_pattern.match(f.name)
            if m:
                max_retry = max(max_retry, int(m.group(1)))

        return max_retry

    def mark_for_revision(self, task_file: Path, issues: list, retry_num: int):
        """Mark task for re-execution with quality feedback.

        Renames .done.md to .revision-N.md and appends feedback.
        """
        stem = task_file.stem
        # Extract base name
        base = stem
        for suffix in [".done", ".completed", ".verified", ".unverified", ".no_output"]:
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break

        # New revision file name
        revision_name = f"{base}.revision-{retry_num}.md"
        revision_path = task_file.parent / revision_name

        # Read original content
        try:
            content = task_file.read_text()
        except Exception as e:
            # Can't read, create minimal revision file
            content = f"# Task: {base}\n\n(Original file could not be read)"

        # Append quality feedback
        feedback = "\n\n---\n## Quality Feedback (Auto-Generated)\n\n"
        feedback += f"This task requires revision (attempt {retry_num}/{self.thresholds['max_retries']}):\n\n"
        for issue in issues:
            feedback += f"- {issue}\n"
        feedback += "\nPlease address these issues and complete the task properly.\n"

        # Write revision file
        try:
            revision_path.write_text(content + feedback)

            # Remove the original .done file
            task_file.unlink()
        except Exception as e:
            # Log error but don't crash
            self._log_error(f"Failed to mark {task_file.name} for revision: {e}")

    def escalate_to_kublai(self, task_file: Path, issues: list):
        """Create escalation task for Kublai review.

        Creates a new high-priority task in kublai's queue.
        """
        # Extract agent and task info
        agent = task_file.parent.parent.name
        task_name = task_file.stem

        # Create escalation task
        escalation_content = f"""---
priority: high
created: {datetime.now().isoformat()}
source: quality-gate
parent_task: {agent}/{task_name}
escalation_type: quality_failure
---

# Quality Escalation: {agent}/{task_name}

This task has failed quality verification {self.thresholds['max_retries']} times.

## Issues
"""
        for issue in issues:
            escalation_content += f"- {issue}\n"

        escalation_content += f"""

## Task Location
Original file: `{task_file}`

## Action Required
Review the task output and determine:
1. Is the task fundamentally flawed? → Reassign with better requirements
2. Is the agent struggling? → Consider different routing
3. Is the quality gate too strict? → Adjust thresholds

Generated by quality-gate.py at {datetime.now().isoformat()}
"""

        # Write to kublai's queue
        kublai_tasks = AGENTS_DIR / "kublai" / "tasks"
        kublai_tasks.mkdir(parents=True, exist_ok=True)

        timestamp = int(datetime.now().timestamp() * 1000)
        escalation_file = kublai_tasks / f"quality-escalate-{agent}-{task_name}-{timestamp}.md"

        try:
            escalation_file.write_text(escalation_content)
            self._log_info(f"Escalated {agent}/{task_name} to kublai: {escalation_file.name}")
        except Exception as e:
            self._log_error(f"Failed to create escalation task: {e}")

    def _log_quality_event(self, task_file: Path, issues: list, action: str, retry: int):
        """Log quality event for analytics."""
        event = {
            "ts": datetime.now().isoformat(),
            "task": str(task_file),
            "agent": task_file.parent.parent.name,
            "action": action,
            "retry": retry,
            "issues": issues,
        }

        try:
            QUALITY_LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(QUALITY_LOG, "a") as f:
                f.write(json.dumps(event) + "\n")
        except Exception:
            pass  # Non-critical

    def _log_info(self, msg: str):
        """Log info message."""
        print(f"[quality-gate] INFO: {msg}")

    def _log_error(self, msg: str):
        """Log error message."""
        print(f"[quality-gate] ERROR: {msg}", file=os.sys.stderr)


def verify_completion_file(task_file: str | Path) -> dict:
    """Convenience function to verify a single completion file.

    Returns:
        dict with keys: passed, action, issues, reason, retry_count
    """
    gate = CompletionQualityGate()
    result = gate.verify_completion(Path(task_file))
    return result.to_dict()


def main():
    """CLI for quality gate verification."""
    import argparse

    parser = argparse.ArgumentParser(description="Verify task completion quality")
    parser.add_argument("file", help="Path to .done.md completion file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    gate = CompletionQualityGate()
    result = gate.verify_completion(Path(args.file))

    if args.verbose or not result.passed:
        print(f"Quality Check: {'PASS' if result.passed else 'FAIL'}")
        print(f"Action: {result.action}")
        if result.issues:
            print("Issues:")
            for issue in result.issues:
                print(f"  - {issue}")
        if result.reason:
            print(f"Reason: {result.reason}")
        if result.retry_count > 0:
            print(f"Retry attempt: {result.retry_count}")

    return 0 if result.passed else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
