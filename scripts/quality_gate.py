#!/usr/bin/env python3
from __future__ import annotations
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


def check_agent_credentials(agent: str) -> tuple[bool, str | None]:
    """Check if agent has valid API credentials.

    Returns (is_valid, error_message) tuple:
    - is_valid: True if credentials are valid
    - error_message: Description of issue if invalid, None if valid

    Credential model (2026-03-09):
    1. OAuth for Anthropic (no stored token) — check credentials.json
    2. Centralized vault (provider.env) for fallbacks
    3. Per-agent tokens in settings.json (legacy, being phased out)

    Prevents escalation to agents with invalid credentials (credential crisis guard).
    """
    try:
        # 1. Check OAuth status (primary auth method for Anthropic)
        _claude_creds_path = Path.home() / ".claude" / "credentials.json"
        if _claude_creds_path.exists():
            try:
                with open(_claude_creds_path, 'r') as f:
                    _creds = json.load(f)
                if _creds.get('loggedIn') and _creds.get('authMethod') == 'oauth_token':
                    # OAuth is active — credentials are valid
                    return True, None
            except (json.JSONDecodeError, IOError):
                pass  # Fall through to vault check

        # 2. Check centralized vault for fallback credentials
        _vault_path = Path.home() / ".openclaw" / "credentials" / "provider.env"
        if _vault_path.exists():
            try:
                with open(_vault_path, 'r') as f:
                    _vault_content = f.read()
                # Check for Z.AI or Alibaba fallback tokens
                _has_zai = 'ZAI_AUTH_TOKEN=' in _vault_content and 'b5b1f953' in _vault_content
                _has_alibaba = 'ALIBABA_AUTH_TOKEN=' in _vault_content and 'sk-sp-' in _vault_content
                if _has_zai or _has_alibaba:
                    return True, None  # Vault has valid fallback credentials
            except IOError:
                pass  # Fall through to legacy check

        # 3. Legacy: Check for per-agent token in settings.json
        agent_root = AGENTS_DIR / agent
        settings_path = agent_root / ".claude" / "settings.json"

        if not settings_path.exists():
            return False, f"No settings.json found for {agent}"

        with open(settings_path, 'r') as f:
            settings = json.load(f)

        # Check for ANTHROPIC_AUTH_TOKEN in env (Claude Code format)
        auth_token = None
        if 'env' in settings:
            auth_token = settings['env'].get('ANTHROPIC_AUTH_TOKEN')

        # Also check direct apiKey field
        if not auth_token:
            auth_token = settings.get('apiKey')

        if not auth_token:
            return False, f"No ANTHROPIC_AUTH_TOKEN found"

        # Validate token format - accept Anthropic, Z.AI, or Alibaba tokens
        _is_anthropic = auth_token.startswith('sk-ant-')
        _is_zai = len(auth_token.split('.')) == 2 and len(auth_token.split('.')[0]) == 32
        _is_alibaba = auth_token.startswith('sk-sp-') or auth_token.startswith('sk-')

        if not (_is_anthropic or _is_zai or _is_alibaba):
            return False, f"Invalid token: {auth_token[:10]}... (expected sk-ant-*, Z.AI, or Alibaba)"

        return True, None

    except Exception as e:
        return False, f"Credential check error: {e}"

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

        # Check for shallow implementation output (PRIORITY_FIX: workspace .md with no code)
        shallow_issue = self._check_shallow_implementation(content, output, task_file)
        if shallow_issue:
            issues.append(shallow_issue)

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

    # Skills that require actual code deliverables (not just workspace docs)
    CODE_DELIVERY_SKILLS = {
        "/horde-implement", "/implement", "/senior-frontend", "/senior-backend",
        "/senior-fullstack", "/senior-architect", "/horde-debug",
        "/systematic-debugging", "/generate-tests",
    }

    # File extensions that count as code (not just documentation)
    CODE_EXTENSIONS = {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java",
        ".cpp", ".c", ".h", ".sh", ".bash", ".zsh", ".sql", ".json",
        ".yaml", ".yml", ".toml", ".css", ".scss", ".html",
    }

    # FIX 2026-03-20: Triage/coordination tasks should not be evaluated against
    # code-delivery criteria. These tasks produce investigation reports and queue
    # mutations, not code artifacts.
    COORDINATION_KEYWORDS = {
        "triage", "stalled", "stall", "coordination", "routing", "health check",
        "queue", "backlog", "status assessment", "system-wide",
    }

    def _check_shallow_implementation(
        self, full_content: str, output: str, task_file: Path
    ) -> str | None:
        """Detect implementation tasks that produced only docs with no code changes.

        Returns an issue string if the task is a shallow implementation, None otherwise.
        """
        # FIX 2026-03-20: Skip shallow check for triage/coordination tasks
        # These are legitimately documentation-only (investigation reports, queue mutations)
        # FIX 2026-03-23: Removed the kublai-only agent guard. Any agent executing a
        # coordination/triage task should receive this exemption — not just kublai.
        # The prior guard caused other agents (jochi, ogedei) processing triage tasks
        # to still fail against code-delivery criteria, reproducing the original bug.
        content_lower = full_content.lower()
        if any(kw in content_lower for kw in self.COORDINATION_KEYWORDS):
            return None  # Coordination tasks are not code-delivery for any agent

        # Extract skill hint from frontmatter
        skill_match = re.search(r"skill[_\s]*hint?:\s*(\S+)", full_content, re.IGNORECASE)
        if not skill_match:
            return None  # No skill hint — skip this check

        skill = skill_match.group(1).strip().lower()
        # FIX 2026-03-20: "none" is an explicit opt-out from code-delivery checks
        if skill == "none" or skill == "null":
            return None
        if skill not in self.CODE_DELIVERY_SKILLS:
            return None  # Not a code-delivery skill — skip

        # Check deliverables section for actual code files
        has_code_file = False

        # Look for file paths with code extensions in output
        file_refs = re.findall(r"[\w/~.-]+\.\w{1,5}", output)
        for ref in file_refs:
            ext = os.path.splitext(ref)[1].lower()
            if ext in self.CODE_EXTENSIONS:
                has_code_file = True
                break

        # Also check for git commit indicators
        has_git_commit = bool(
            re.search(r"(?:commit|committed|pushed|git add)\b", output, re.IGNORECASE)
        )

        # Check for code blocks that contain actual code (not just markdown)
        code_blocks = re.findall(r"```(\w*)\n(.*?)```", output, re.DOTALL)
        has_substantial_code = False
        for lang, block_content in code_blocks:
            # Skip markdown/text blocks — only count code languages
            if lang.lower() in ("", "md", "markdown", "text", "txt"):
                continue
            # At least 5 lines of actual code
            code_lines = [l for l in block_content.strip().split("\n") if l.strip()]
            if len(code_lines) >= 5:
                has_substantial_code = True
                break

        # Check for workspace-only .md deliverables
        workspace_refs = re.findall(r"workspace/[\w/.-]+\.md", output)
        all_refs = re.findall(r"(?:Created|Wrote|Saved|Modified|Updated)[:\s]+([^\s\n]+)", output, re.IGNORECASE)
        all_are_docs = all_refs and all(
            os.path.splitext(r)[1].lower() in (".md", ".txt", ".rst")
            for r in all_refs
        )

        # Flag as shallow if: code-delivery skill + no code files + no git + no substantial code blocks
        if not has_code_file and not has_git_commit and not has_substantial_code:
            if workspace_refs or all_are_docs:
                return (
                    f"Shallow implementation: skill {skill} produced only documentation "
                    f"({len(workspace_refs)} workspace .md files) with no code changes or commits"
                )

        return None

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

        SAFETY CHECKS (prevents escalation loops):
        - Skip tasks ending in .done.md (already complete)
        - Skip tasks containing .resolved (already resolved)
        - Skip tasks that are themselves escalations (quality-escalate- or ESCALATE-stale-task-)
        - Check escalation depth (max 2 levels)
        - Skip recently modified files (< 5 min old)
        """
        # Extract agent and task info
        agent = task_file.parent.parent.name
        task_name = task_file.stem
        filename = task_file.name

        # SAFETY CHECK 1: Skip .done.md files (already complete)
        if filename.endswith(".done.md"):
            self._log_info(f"SKIP: {filename} - already has .done.md suffix (not escalating)")
            return

        # SAFETY CHECK 2: Skip .resolved files (already resolved)
        if ".resolved." in filename or filename.endswith(".resolved.md"):
            self._log_info(f"SKIP: {filename} - contains .resolved (not escalating)")
            return

        # SAFETY CHECK 3: Skip escalation tasks (prevent meta-escalations)
        if filename.startswith("quality-escalate-") or filename.startswith("ESCALATE-stale-task-"):
            self._log_info(f"SKIP: {filename} - is an escalation task (not escalating)")
            return

        # SAFETY CHECK 4: Escalation depth limit (max 2 levels)
        # Count how many times "escalate" appears in the filename (case-insensitive)
        escalation_count = filename.lower().count("escalate")
        if escalation_count >= 2:
            self._log_info(f"SKIP: {filename} - escalation depth {escalation_count} >= 2 (not escalating)")
            return

        # SAFETY CHECK 5: Skip recently modified files (< 5 min = 300 seconds)
        import time
        file_age = time.time() - task_file.stat().st_mtime
        if file_age < 300:
            self._log_info(f"SKIP: {filename} - modified {file_age:.0f}s ago < 300s threshold (not escalating)")
            return

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

        # SAFETY CHECK 6: Credential crisis guard — check if escalation target (ogedei) has valid credentials
        # Prevents piling up escalation tasks when target cannot execute them
        ogedei_creds_valid, creds_error = check_agent_credentials("ogedei")
        if not ogedei_creds_valid:
            self._log_info(f"SKIP_ESCALATION: ogedei has invalid credentials ({creds_error}) — NOT escalating {agent}/{task_name}")
            self._log_info("  Reason: Escalation would create a task ogedei cannot execute (credential crisis guard)")
            return

        # Write to ogedei's queue (kublai is not dispatchable)
        ogedei_tasks = AGENTS_DIR / "ogedei" / "tasks"
        ogedei_tasks.mkdir(parents=True, exist_ok=True)

        timestamp = int(datetime.now().timestamp() * 1000)
        escalation_file = ogedei_tasks / f"quality-escalate-{agent}-{task_name}-{timestamp}.md"

        try:
            escalation_file.write_text(escalation_content)
            self._log_info(f"Escalated {agent}/{task_name} to ogedei: {escalation_file.name}")
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
