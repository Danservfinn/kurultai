#!/usr/bin/env python3
"""
Task Verifier — Post-completion verification for Kurultai agent tasks.

Checks that completed tasks actually delivered their promised outcomes.
Runs AFTER a task is marked .completed.done.md by agent-task-handler.py.

Verification rules by task type:
  - deploy: curl URLs (expect 200), check files exist
  - code:   workspace output exists (>200 chars), run test commands, check files
  - research: output files exist with >500 chars of substantive content
  - content: files exist with expected structure (headings, prose)

Usage:
    python3 task-verifier.py --task-file path/to/.completed.done.md --agent temujin
    python3 task-verifier.py --batch  # verify all recent completions
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kurultai_paths import AGENTS_DIR, TASK_LEDGER, LOGS_DIR
from kurultai_ledger import append_ledger as _kp_append_ledger

VERIFICATION_LOG = LOGS_DIR / "verification.jsonl"

# Agent-based default task type
AGENT_DEFAULT_TYPE = {
    "temujin": "code",
    "mongke": "research",
    "chagatai": "content",
    "jochi": "code",
    "ogedei": "code",
    "kublai": "content",
}

# Body signal patterns for task type classification
TASK_TYPE_SIGNALS = {
    "deploy": [
        r"deploy\b", r"curl\s+https?://", r"returns?\s+200",
        r"railway\s+deploy", r"launchctl", r"docker\s+",
        r"live\s+url", r"port\s+\d{4,5}",
    ],
    "code": [
        r"implement\b", r"build\b", r"fix\b", r"bug\b",
        r"create\s+(script|file|function)", r"run\s+tests?\b",
        r"npm\s+test", r"pytest\b", r"\.py\b", r"\.ts\b",
    ],
    "research": [
        r"research\b", r"investigate\b", r"discover\b",
        r"analyze\b", r"study\b", r"findings?\b", r"report\b",
    ],
    "content": [
        r"write\b.*doc", r"blog\s+post", r"changelog\b",
        r"readme\b", r"documentation\b", r"article\b",
    ],
}

# Sources that skip verification entirely (routine housekeeping)
SKIP_VERIFICATION_SOURCES = {
    "agent-self-wake",
    "kublai-actions",
    "agent-self-wake (rule t7)",
}

# Whitelisted test command prefixes (security: never run arbitrary shell)
ALLOWED_TEST_COMMANDS = [
    "npm test", "npm run test", "npx jest", "npx vitest",
    "pytest", "python3 -m pytest", "python -m pytest",
    "make test", "bun test",
]

# URL allowlist patterns for SSRF prevention
ALLOWED_URL_PATTERNS = [
    r"^https?://.*\.kurult\.ai",
    r"^https?://.*\.parsethe\.media",
    r"^https?://.*\.up\.railway\.app",
    r"^https?://localhost:\d+",
    r"^https?://127\.0\.0\.1:\d+",
]

# Path allowlist for file checks (prevent traversal)
ALLOWED_PATH_PREFIXES = [
    "/Users/kublai/",
    "/tmp/",
    "/var/tmp/",
]


class Confidence(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    SKIP = "skip"


@dataclass
class CheckResult:
    check: str
    target: str
    passed: bool
    detail: str


@dataclass
class VerificationResult:
    task_id: str
    agent: str
    task_type: str
    passed: bool
    confidence: str
    checks_run: int = 0
    checks_passed: int = 0
    checks_failed: int = 0
    checks_skipped: int = 0
    details: list = field(default_factory=list)
    elapsed_s: float = 0.0
    timestamp: str = ""


def _extract_frontmatter(content):
    """Extract frontmatter fields from task markdown."""
    fm = {}
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().splitlines():
                if ":" in line:
                    key, _, val = line.partition(":")
                    fm[key.strip()] = val.strip()
    return fm


def _extract_body(content):
    """Extract body (after frontmatter) from task markdown."""
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return content.strip()


def classify_task_type(agent, task_content):
    """Classify task type from agent defaults + body signal matching."""
    body = _extract_body(task_content).lower()

    # Deploy signals take priority
    for pattern in TASK_TYPE_SIGNALS["deploy"]:
        if re.search(pattern, body, re.IGNORECASE):
            return "deploy"

    # Count signal matches for each type
    scores = {}
    for task_type, patterns in TASK_TYPE_SIGNALS.items():
        if task_type == "deploy":
            continue
        scores[task_type] = sum(1 for p in patterns if re.search(p, body, re.IGNORECASE))

    best = max(scores, key=scores.get) if scores else None
    if best and scores[best] >= 2:
        return best

    return AGENT_DEFAULT_TYPE.get(agent, "code")


def _is_safe_url(url):
    """Check URL against allowlist to prevent SSRF."""
    for pattern in ALLOWED_URL_PATTERNS:
        if re.match(pattern, url):
            return True
    return False


def _is_safe_path(path):
    """Check path against allowlist to prevent traversal."""
    resolved = os.path.realpath(path)
    return any(resolved.startswith(prefix) for prefix in ALLOWED_PATH_PREFIXES)


def _is_safe_command(cmd):
    """Check command against whitelist of test runners."""
    return any(cmd.strip().startswith(prefix) for prefix in ALLOWED_TEST_COMMANDS)


def extract_verification_targets(task_content, workspace_content, task_type):
    """Extract verification targets from task and workspace content."""
    targets = {
        "urls": [],
        "files": [],
        "commands": [],
        "min_output_chars": 500 if task_type in ("research", "content") else 200,
    }

    combined = task_content + "\n" + (workspace_content or "")

    # Look for explicit verification/success criteria section first
    verification_section = ""
    for heading in [r"##\s+(?:Verification|Success Criteria|Deliverables)",
                    r"##\s+(?:Expected Output|Output)"]:
        match = re.search(heading, combined, re.IGNORECASE)
        if match:
            # Grab text until next heading or end
            section_start = match.end()
            next_heading = re.search(r"\n##\s", combined[section_start:])
            if next_heading:
                verification_section = combined[section_start:section_start + next_heading.start()]
            else:
                verification_section = combined[section_start:]
            break

    # Prefer targets from verification section; fall back to full body
    search_text = verification_section if verification_section else combined

    # Extract URLs from curl commands
    for match in re.finditer(r"curl\s+(?:-[sSkLfv]+\s+)*(?:\")?'?(https?://[^\s\"')\]]+)", search_text):
        url = match.group(1).rstrip(".,;:")
        if _is_safe_url(url):
            targets["urls"].append(url)

    # Extract URLs from "Live URL:", "URL:", "Deploy URL:" patterns
    for match in re.finditer(
        r"(?:live|frontend|deploy|api|base)\s*url[:\s]+(https?://[^\s\"')\]]+)",
        search_text, re.IGNORECASE
    ):
        url = match.group(1).rstrip(".,;:")
        if _is_safe_url(url):
            targets["urls"].append(url)

    # Extract file paths (absolute paths)
    for match in re.finditer(r"(?:^|\s)(/(?:Users|home|tmp|var/tmp)/[^\s\"')\]]+\.\w+)", search_text):
        path = match.group(1).rstrip(".,;:")
        if _is_safe_path(path):
            targets["files"].append(path)

    # Extract test commands from code blocks
    for match in re.finditer(r"```(?:bash|sh|shell)?\n([^\n]+)\n", search_text):
        cmd = match.group(1).strip()
        if _is_safe_command(cmd):
            targets["commands"].append(cmd)

    # Deduplicate
    targets["urls"] = list(dict.fromkeys(targets["urls"]))
    targets["files"] = list(dict.fromkeys(targets["files"]))
    targets["commands"] = list(dict.fromkeys(targets["commands"]))

    return targets


def run_url_check(url, timeout=10, retries=2):
    """Check URL reachability. Returns CheckResult."""
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, method="HEAD")
            req.add_header("User-Agent", "Kurultai-TaskVerifier/1.0")
            start = time.time()
            resp = urllib.request.urlopen(req, timeout=timeout)
            elapsed = round(time.time() - start, 2)
            code = resp.getcode()
            if code and 200 <= code < 400:
                return CheckResult("url_reachable", url, True, f"HTTP {code} in {elapsed}s")
            return CheckResult("url_reachable", url, False, f"HTTP {code}")
        except urllib.error.HTTPError as e:
            if attempt < retries and e.code >= 500:
                time.sleep(3)
                continue
            return CheckResult("url_reachable", url, False, f"HTTP {e.code}: {e.reason}")
        except Exception as e:
            if attempt < retries:
                time.sleep(3)
                continue
            return CheckResult("url_reachable", url, False, f"Error: {type(e).__name__}: {e}")


def run_file_check(filepath):
    """Check file existence and minimum content. Returns CheckResult."""
    if not _is_safe_path(filepath):
        return CheckResult("file_exists", filepath, False, "Path outside allowed directories")
    if not os.path.exists(filepath):
        return CheckResult("file_exists", filepath, False, "File not found")
    try:
        size = os.path.getsize(filepath)
        return CheckResult("file_exists", filepath, True, f"Exists ({size} bytes)")
    except OSError as e:
        return CheckResult("file_exists", filepath, False, f"Error: {e}")


def run_content_check(filepath, min_chars=500):
    """Check file has substantive content above threshold. Returns CheckResult."""
    if not os.path.exists(filepath):
        return CheckResult("content_substantive", filepath, False, "File not found")
    try:
        content = Path(filepath).read_text(encoding="utf-8", errors="replace")
        # Strip markdown headers, whitespace, frontmatter
        stripped = re.sub(r"^---.*?---\s*", "", content, flags=re.DOTALL)
        stripped = re.sub(r"^#+\s+.*$", "", stripped, flags=re.MULTILINE)
        stripped = stripped.strip()
        char_count = len(stripped)
        if char_count >= min_chars:
            return CheckResult("content_substantive", filepath, True,
                               f"{char_count} chars of substantive content")
        return CheckResult("content_substantive", filepath, False,
                           f"Only {char_count} chars (need {min_chars})")
    except Exception as e:
        return CheckResult("content_substantive", filepath, False, f"Error: {e}")


def run_command_check(cmd, timeout=60, cwd=None):
    """Run whitelisted test command. Returns CheckResult."""
    if not _is_safe_command(cmd):
        return CheckResult("command_run", cmd, False, "Command not in whitelist")
    try:
        # Split command safely - no shell=True
        parts = cmd.split()
        result = subprocess.run(
            parts, capture_output=True, text=True, timeout=timeout, cwd=cwd,
        )
        if result.returncode == 0:
            return CheckResult("command_run", cmd, True, f"Exit 0 ({len(result.stdout)} bytes output)")
        return CheckResult("command_run", cmd, False,
                           f"Exit {result.returncode}: {result.stderr[:200]}")
    except subprocess.TimeoutExpired:
        return CheckResult("command_run", cmd, False, f"Timed out after {timeout}s")
    except Exception as e:
        return CheckResult("command_run", cmd, False, f"Error: {e}")


def run_structure_check(filepath):
    """Check file has expected document structure (headings, paragraphs). Returns CheckResult."""
    if not os.path.exists(filepath):
        return CheckResult("structure", filepath, False, "File not found")
    try:
        content = Path(filepath).read_text(encoding="utf-8", errors="replace")
        heading_count = len(re.findall(r"^#+\s+", content, re.MULTILINE))
        # Count paragraphs (3+ consecutive lines of non-empty prose)
        paragraphs = re.findall(r"(?:^[A-Za-z].+\n){3,}", content, re.MULTILINE)
        if heading_count >= 1 and len(paragraphs) >= 1:
            return CheckResult("structure", filepath, True,
                               f"{heading_count} headings, {len(paragraphs)} paragraphs")
        return CheckResult("structure", filepath, False,
                           f"Weak structure: {heading_count} headings, {len(paragraphs)} paragraphs")
    except Exception as e:
        return CheckResult("structure", filepath, False, f"Error: {e}")


def _find_workspace_result(agent, task_file):
    """Find the most recent workspace result file for a completed task.

    Looks for task-{timestamp}.md in the agent's workspace, matching
    the task completion time window.
    """
    workspace_dir = AGENTS_DIR / agent / "workspace"
    if not workspace_dir.exists():
        return None

    # Get task file mtime as reference
    try:
        task_mtime = os.path.getmtime(task_file)
    except OSError:
        return None

    # Find workspace results within 2 minutes of task completion
    candidates = []
    for f in workspace_dir.glob("task-*.md"):
        try:
            f_mtime = f.stat().st_mtime
            if abs(f_mtime - task_mtime) < 120:
                candidates.append((f, abs(f_mtime - task_mtime)))
        except OSError:
            continue

    if candidates:
        candidates.sort(key=lambda x: x[1])
        return str(candidates[0][0])

    # Fallback: most recent workspace result
    results = sorted(workspace_dir.glob("task-*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
    return str(results[0]) if results else None


def verify_task(task_file, agent=None):
    """Run verification on a completed task file.

    Returns VerificationResult with pass/fail and check details.
    """
    start = time.time()

    # Read task content
    task_path = Path(task_file)
    if not task_path.exists():
        return VerificationResult(
            task_id="", agent=agent or "", task_type="unknown",
            passed=False, confidence=Confidence.SKIP.value,
            timestamp=datetime.now().isoformat(),
        )

    task_content = task_path.read_text(encoding="utf-8", errors="replace")
    fm = _extract_frontmatter(task_content)

    task_id = fm.get("task_id", "")
    if not agent:
        agent = fm.get("agent", "unknown")
    source = fm.get("source", "")

    # Skip verification for housekeeping sources
    if source in SKIP_VERIFICATION_SOURCES:
        return VerificationResult(
            task_id=task_id, agent=agent, task_type="housekeeping",
            passed=True, confidence=Confidence.SKIP.value,
            timestamp=datetime.now().isoformat(),
        )

    # Classify task type
    task_type = classify_task_type(agent, task_content)

    # Find workspace result
    workspace_file = _find_workspace_result(agent, task_file)
    workspace_content = ""
    if workspace_file and os.path.exists(workspace_file):
        workspace_content = Path(workspace_file).read_text(encoding="utf-8", errors="replace")

    # Extract verification targets
    targets = extract_verification_targets(task_content, workspace_content, task_type)

    # Determine confidence based on target availability
    has_specific_targets = bool(targets["urls"] or targets["files"] or targets["commands"])
    has_verification_section = bool(
        re.search(r"##\s+(?:Verification|Success Criteria)", task_content, re.IGNORECASE)
    )

    if has_verification_section:
        confidence = Confidence.HIGH
    elif has_specific_targets:
        confidence = Confidence.MEDIUM
    else:
        confidence = Confidence.LOW

    # Run checks
    checks = []

    # Type-specific checks
    if task_type == "deploy":
        # Deploy delay: wait for deployment to be live
        if targets["urls"]:
            time.sleep(5)
        for url in targets["urls"][:5]:
            checks.append(run_url_check(url))
        for fp in targets["files"][:10]:
            checks.append(run_file_check(fp))
        # Workspace output check (lenient for deploy)
        if workspace_file:
            checks.append(run_content_check(workspace_file, min_chars=100))

    elif task_type == "code":
        # Workspace output
        if workspace_file:
            checks.append(run_content_check(workspace_file, min_chars=200))
        # Test commands (max 2)
        for cmd in targets["commands"][:2]:
            checks.append(run_command_check(cmd))
        # File existence
        for fp in targets["files"][:10]:
            checks.append(run_file_check(fp))

    elif task_type == "research":
        # Workspace output with substantive content
        if workspace_file:
            checks.append(run_content_check(workspace_file, min_chars=500))
        # Deliverable files
        for fp in targets["files"][:5]:
            checks.append(run_file_check(fp))
            checks.append(run_content_check(fp, min_chars=500))

    elif task_type == "content":
        # Workspace output
        if workspace_file:
            checks.append(run_content_check(workspace_file, min_chars=500))
            checks.append(run_structure_check(workspace_file))
        # Deliverable files
        for fp in targets["files"][:5]:
            checks.append(run_file_check(fp))

    # Fallback: if no specific checks ran, verify workspace output exists at all
    if not checks:
        if workspace_file:
            checks.append(run_content_check(workspace_file, min_chars=100))
        else:
            checks.append(CheckResult("workspace_exists", "workspace/", False, "No workspace result found"))

    # Tally results
    passed_checks = [c for c in checks if c.passed]
    failed_checks = [c for c in checks if not c.passed]

    # Overall pass/fail
    if not checks:
        overall_passed = True  # Nothing to verify
    elif confidence == Confidence.LOW:
        # Low confidence: pass if workspace output exists
        overall_passed = len(failed_checks) == 0 or (len(passed_checks) > 0)
    else:
        # Medium/High confidence: fail if any critical check fails
        overall_passed = len(failed_checks) == 0

    elapsed = round(time.time() - start, 2)

    return VerificationResult(
        task_id=task_id,
        agent=agent,
        task_type=task_type,
        passed=overall_passed,
        confidence=confidence.value,
        checks_run=len(checks),
        checks_passed=len(passed_checks),
        checks_failed=len(failed_checks),
        details=[asdict(c) for c in checks],
        elapsed_s=elapsed,
        timestamp=datetime.now().isoformat(),
    )


def apply_verification_result(task_file, result):
    """Rename task file based on verification result.

    .completed.done.md -> .verified.done.md   (passed, confidence HIGH/MEDIUM)
    .completed.done.md -> .unverified.done.md (failed, confidence HIGH/MEDIUM)
    .completed.done.md -> unchanged           (confidence LOW/SKIP)
    """
    if result.confidence in (Confidence.LOW.value, Confidence.SKIP.value):
        return task_file  # No rename for low confidence

    task_path = Path(task_file)
    if not task_path.exists():
        return task_file

    if result.passed:
        new_name = task_path.name.replace(".completed.done", ".verified.done")
    else:
        new_name = task_path.name.replace(".completed.done", ".unverified.done")

    if new_name == task_path.name:
        return task_file  # Name didn't change (not a .completed.done file)

    new_path = task_path.parent / new_name
    try:
        os.rename(task_path, new_path)
        return str(new_path)
    except OSError:
        return task_file


def log_verification(result):
    """Append verification result to verification log."""
    VERIFICATION_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "task_id": result.task_id,
        "agent": result.agent,
        "task_type": result.task_type,
        "passed": result.passed,
        "confidence": result.confidence,
        "checks_run": result.checks_run,
        "checks_passed": result.checks_passed,
        "checks_failed": result.checks_failed,
        "details": result.details,
        "elapsed_s": result.elapsed_s,
        "ts": result.timestamp,
    }
    try:
        with open(VERIFICATION_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def log_to_ledger(result):
    """Append verification event to task ledger."""
    event = "VERIFIED" if result.passed else "VERIFICATION_FAILED"
    entry = {
        "task_id": result.task_id,
        "event": event,
        "ts": result.timestamp,
        "agent": result.agent,
        "task_type": result.task_type,
        "checks_run": result.checks_run,
        "checks_passed": result.checks_passed,
        "checks_failed": result.checks_failed,
        "confidence": result.confidence,
        "verification_time_s": result.elapsed_s,
    }
    if not result.passed:
        entry["failed_checks"] = [d for d in result.details if not d["passed"]]
    _kp_append_ledger(entry)


def update_neo4j(result):
    """Update Neo4j task node with verification status. Non-fatal on failure."""
    if not result.task_id:
        return
    try:
        from neo4j_task_tracker import neo4j_session
        with neo4j_session() as session:
            session.run("""
                MATCH (t:Task {task_id: $task_id})
                SET t.verified = $passed,
                    t.verification_type = $task_type,
                    t.verification_checks = $checks_run,
                    t.verification_passed_count = $checks_passed,
                    t.verification_confidence = $confidence,
                    t.verification_ts = datetime()
            """,
                task_id=result.task_id,
                passed=result.passed,
                task_type=result.task_type,
                checks_run=result.checks_run,
                checks_passed=result.checks_passed,
                confidence=result.confidence,
            )
    except Exception:
        pass


def format_notification(result):
    """Format notification message for kublai."""
    if result.confidence == Confidence.SKIP.value:
        return None

    if result.passed:
        if result.confidence == Confidence.LOW.value:
            return None  # Don't notify for low-confidence passes
        return (
            f"[VERIFIED] {result.agent}: task {result.task_id[:11]} "
            f"— {result.checks_passed}/{result.checks_run} checks passed "
            f"({result.task_type}, {result.confidence} confidence)"
        )
    else:
        failed = [d for d in result.details if not d["passed"]]
        fail_summary = "; ".join(
            f"{d['check']}: {d['target'][:40]} -> {d['detail'][:60]}"
            for d in failed[:3]
        )
        return (
            f"[VERIFY-FAIL] {result.agent}: task {result.task_id[:11]} "
            f"— {result.checks_failed}/{result.checks_run} checks failed "
            f"({fail_summary})"
        )


def send_notification(msg):
    """Send notification via openclaw gateway."""
    if not msg:
        return
    try:
        subprocess.run(
            ["openclaw", "agent", "--agent", "kublai", "-m", msg, "--deliver"],
            capture_output=True, timeout=30,
        )
    except Exception:
        pass


def verify_and_report(task_file, agent=None, rename=True, notify=True):
    """Full verification pipeline: verify, log, rename, notify.

    Returns VerificationResult.
    """
    result = verify_task(task_file, agent)

    # Log
    log_verification(result)
    if result.task_id:
        log_to_ledger(result)
        update_neo4j(result)

    # Rename
    if rename and result.confidence not in (Confidence.LOW.value, Confidence.SKIP.value):
        apply_verification_result(task_file, result)

    # Notify
    if notify:
        msg = format_notification(result)
        send_notification(msg)

    return result


def batch_verify(hours=2):
    """Verify all recent .completed.done.md files from the last N hours."""
    cutoff = time.time() - (hours * 3600)
    results = []

    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir() or agent_dir.name == "main":
            continue
        tasks_dir = agent_dir / "tasks"
        if not tasks_dir.exists():
            continue

        for f in tasks_dir.glob("*.completed.done.md"):
            try:
                if f.stat().st_mtime < cutoff:
                    continue
            except OSError:
                continue

            agent = agent_dir.name
            print(f"Verifying: {agent}/{f.name}")
            result = verify_and_report(str(f), agent, rename=True, notify=False)
            status = "PASS" if result.passed else "FAIL"
            print(f"  [{status}] {result.task_type} ({result.confidence}): "
                  f"{result.checks_passed}/{result.checks_run} checks passed")
            results.append(result)

    return results


def main():
    parser = argparse.ArgumentParser(description="Verify completed Kurultai tasks")
    parser.add_argument("--task-file", help="Path to .completed.done.md file")
    parser.add_argument("--agent", help="Agent name (auto-detected from frontmatter if omitted)")
    parser.add_argument("--batch", action="store_true", help="Verify all recent completions")
    parser.add_argument("--hours", type=int, default=2, help="Hours lookback for --batch (default: 2)")
    parser.add_argument("--no-rename", action="store_true", help="Skip file rename")
    parser.add_argument("--no-notify", action="store_true", help="Skip notification")
    parser.add_argument("--json", action="store_true", help="Output JSON result")
    args = parser.parse_args()

    if args.batch:
        results = batch_verify(args.hours)
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        print(f"\nBatch: {passed}/{total} tasks verified successfully")
        sys.exit(0 if passed == total else 1)

    if not args.task_file:
        parser.error("--task-file is required (or use --batch)")

    result = verify_and_report(
        args.task_file,
        agent=args.agent,
        rename=not args.no_rename,
        notify=not args.no_notify,
    )

    if args.json:
        print(json.dumps(asdict(result), indent=2))
    else:
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.agent}/{result.task_type} ({result.confidence} confidence)")
        print(f"  Checks: {result.checks_passed}/{result.checks_run} passed, "
              f"{result.checks_failed} failed")
        for d in result.details:
            icon = "+" if d["passed"] else "-"
            print(f"  [{icon}] {d['check']}: {d['target'][:50]} — {d['detail']}")

    sys.exit(0 if result.passed else 1)


if __name__ == "__main__":
    main()
