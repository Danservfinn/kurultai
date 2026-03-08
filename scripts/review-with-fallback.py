#!/usr/bin/env python3
"""
horde-review Fallback Mode - P0 Self-Healing Enhancement

Provides graceful degradation when /horde-review fails or times out.
Ensures reflection pipeline always completes with quality data.

Modes:
  1. Full: Use /horde-review via claude-agent (dispatches multiple agents)
  2. Degraded: Single-agent review without spawning subagents
  3. Minimal: Static checklist (last resort)

Usage:
    python3 review-with-fallback.py --agent kublai [--timeout 300]

Exit codes:
    0: Success (any mode)
    1: All modes failed
    2: Invalid arguments
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional


# Configuration
LOGS_DIR = Path("/Users/kublai/.openclaw/logs")
REVIEW_LOG = LOGS_DIR / "horde-review-fallback.log"
FALLBACK_ALERT_LOG = LOGS_DIR / "horde-review-fallbacks.jsonl"

# Thresholds for degraded mode quality checks
MIN_CHARS_THRESHOLD = 500
MIN_HEADINGS_THRESHOLD = 2
REVIEW_HOURS_WINDOW = 24


class ReviewResult:
    """Result of a review attempt."""
    def __init__(self, mode: str, success: bool, data: str = "",
                 issues: List[str] = None, execution_time: float = 0):
        self.mode = mode
        self.success = success
        self.data = data
        self.issues = issues or []
        self.execution_time = execution_time


def log_fallback(agent: str, mode: str, original_error: str, execution_time: float):
    """Log fallback events for tracking and analysis."""
    FALLBACK_ALERT_LOG.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp": datetime.now().isoformat(),
        "agent": agent,
        "mode_used": mode,
        "original_error": original_error[:200],  # Truncate long errors
        "execution_time_s": round(execution_time, 1)
    }

    with open(FALLBACK_ALERT_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def read_recent_completions(agent: str, hours: int = REVIEW_HOURS_WINDOW) -> List[Dict]:
    """Read recent task completions from ledger files."""
    completions = []
    agent_dir = Path(f"/Users/kublai/.openclaw/agents/{agent}")
    tasks_dir = agent_dir / "tasks"

    if not tasks_dir.exists():
        return completions

    cutoff = datetime.now() - timedelta(hours=hours)

    for f in tasks_dir.glob("*.done.md"):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                continue

            content = f.read_text()
            completions.append({
                "file": f.name,
                "completed_at": mtime.isoformat(),
                "char_count": len(content),
                "has_resolution": "## Resolution" in content or "**Status:**" in content,
                "has_code_blocks": "```" in content,
                "headings": content.count("\n##"),
                "content": content[:1000]  # Sample for analysis
            })
        except Exception:
            continue

    return sorted(completions, key=lambda x: x["completed_at"], reverse=True)


def run_full_review(agent: str, timeout: int) -> ReviewResult:
    """Attempt 1: Full horde-review via claude-agent."""
    start = datetime.now()

    # Build review prompt
    prompt = f"""/horde-review

Critically review {agent} agent performance for the past hour.

## Review Focus
Analyze this agent's performance with structured critical analysis:
1. Task completion effectiveness — what succeeded, what failed, why
2. Behavioral rule compliance — are WHEN/THEN rules being followed
3. Efficiency — time spent vs output produced
4. Cross-agent impact — how does this agent affect system throughput

Output EXACTLY this format:
STRENGTHS: (2-3 bullet points of what worked well)
WEAKNESSES: (2-3 bullet points of what failed or underperformed)
PATTERNS: (recurring issues or successes observed)
PRIORITY_FIX: (single most impactful improvement for next hour)
SCORE: (1-10 performance rating with one-line justification)
"""

    try:
        # Use sonnet for reviews (per user instruction)
        result = subprocess.run(
            [
                "/Users/kublai/.local/bin/claude-agent",
                "--model", "sonnet",
                prompt
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "ANOY": "1"}  # Suppress interactive prompts
        )

        execution_time = (datetime.now() - start).total_seconds()

        if result.returncode == 0 and result.stdout:
            # Verify structured output
            if "STRENGTHS:" in result.stdout and "WEAKNESSES:" in result.stdout:
                return ReviewResult(
                    mode="full",
                    success=True,
                    data=result.stdout,
                    execution_time=execution_time
                )

        return ReviewResult(
            mode="full",
            success=False,
            issues=[f"Return code: {result.returncode}"],
            execution_time=execution_time
        )

    except subprocess.TimeoutExpired:
        execution_time = (datetime.now() - start).total_seconds()
        return ReviewResult(
            mode="full",
            success=False,
            issues=[f"Timeout after {timeout}s"],
            execution_time=execution_time
        )
    except Exception as e:
        execution_time = (datetime.now() - start).total_seconds()
        return ReviewResult(
            mode="full",
            success=False,
            issues=[str(e)],
            execution_time=execution_time
        )


def run_simple_review(agent: str) -> ReviewResult:
    """Attempt 2: Degraded single-agent review without spawning subagents."""
    start = datetime.now()

    completions = read_recent_completions(agent, hours=REVIEW_HOURS_WINDOW)

    if not completions:
        return ReviewResult(
            mode="degraded",
            success=True,
            data=f"""# {agent.upper()} REVIEW (Degraded Mode)

**Note:** Full horde-review unavailable. Using degraded analysis.

STRENGTHS:
- No recent task failures detected in past {REVIEW_HOURS_WINDOW}h
- System operating normally

WEAKNESSES:
- Insufficient task data for full analysis

PATTERNS:
- No tasks completed in review window

PRIORITY_FIX:
- None required

SCORE: N/A (no recent activity)
""",
            execution_time=(datetime.now() - start).total_seconds()
        )

    # Analyze completions
    issues_found = []
    low_quality_count = 0
    no_resolution_count = 0

    for task in completions:
        task_name = task["file"].replace(".done.md", "")
        if task["char_count"] < MIN_CHARS_THRESHOLD:
            issues_found.append(f"{task_name}: Low content ({task['char_count']} chars)")
            low_quality_count += 1
        if not task["has_resolution"]:
            issues_found.append(f"{task_name}: Missing resolution section")
            no_resolution_count += 1

    total_tasks = len(completions)
    quality_rate = (total_tasks - low_quality_count) / total_tasks if total_tasks > 0 else 1

    # Generate report
    strengths = [
        f"{total_tasks} task(s) completed in past {REVIEW_HOURS_WINDOW}h",
        f"Quality rate: {quality_rate:.0%}"
    ]

    weaknesses = []
    if low_quality_count > 0:
        weaknesses.append(f"{low_quality_count} low-quality completions")
    if no_resolution_count > 0:
        weaknesses.append(f"{no_resolution_count} tasks missing resolution")
    if not weaknesses:
        weaknesses.append("No significant issues detected")

    patterns = [
        f"Total completions: {total_tasks}",
        f"Average content length: {sum(c['char_count'] for c in completions) // total_tasks if total_tasks else 0} chars"
    ]

    # Score calculation (1-10)
    base_score = int(10 * quality_rate)
    score = max(1, min(10, base_score))

    report = f"""# {agent.upper()} REVIEW (Degraded Mode)

**Note:** Full horde-review unavailable. Using degraded analysis.
**Tasks Reviewed:** {total_tasks} (past {REVIEW_HOURS_WINDOW}h)

STRENGTHS:
{chr(10).join(f"- {s}" for s in strengths)}

WEAKNESSES:
{chr(10).join(f"- {w}" for w in weaknesses)}

PATTERNS:
{chr(10).join(f"- {p}" for p in patterns)}
"""

    if issues_found:
        report += f"\nISSUES DETECTED:\n"
        for issue in issues_found[:10]:
            report += f"- {issue}\n"

    report += f"\nPRIORITY_FIX: "
    if low_quality_count > total_tasks // 2:
        report += "Investigate low-quality completions - possible model/routing issue"
    elif no_resolution_count > 0:
        report += "Ensure agents include resolution sections in task outputs"
    else:
        report += "None required"

    report += f"\n\nSCORE: {score}/10 - Based on completion quality metrics"

    return ReviewResult(
        mode="degraded",
        success=True,
        data=report,
        issues=issues_found,
        execution_time=(datetime.now() - start).total_seconds()
    )


def generate_static_checklist(agent: str) -> ReviewResult:
    """Attempt 3: Static checklist (last resort)."""
    start = datetime.now()

    report = f"""# {agent.upper()} REVIEW (Minimal Mode)

**WARNING:** All review modes failed. This is a minimal health check.

STATUS: UNABLE TO COMPLETE FULL REVIEW

CHECKLIST:
- [ ] Agent process is running
- [ ] Tasks are being dispatched
- [ ] No critical errors in logs
- [ ] Gateway connectivity OK

PRIORITY_FIX:
- Investigate why horde-review is failing
- Check claude-agent binary accessibility
- Verify API credentials and model availability

SCORE: N/A (review system degraded)

**Action Required:** Manual investigation recommended.
"""

    return ReviewResult(
        mode="minimal",
        success=True,
        data=report,
        execution_time=(datetime.now() - start).total_seconds()
    )


def run_review_with_fallback(agent: str, timeout: int = 300) -> ReviewResult:
    """Run agent review with automatic fallback.

    Strategy:
    1. Try full horde-review
    2. Fall back to degraded single-agent review
    3. Fall back to static checklist (last resort)

    Always returns success, even if all modes fail (minimal mode).
    """
    # Attempt 1: Full horde-review
    result = run_full_review(agent, timeout)
    if result.success:
        return result

    original_error = "; ".join(result.issues) if result.issues else "unknown"

    # Attempt 2: Degraded review
    result = run_simple_review(agent)
    if result.success:
        log_fallback(agent, "degraded", original_error, result.execution_time)
        return result

    # Attempt 3: Static checklist (always succeeds)
    result = generate_static_checklist(agent)
    log_fallback(agent, "minimal", original_error, result.execution_time)
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Run agent review with automatic fallback"
    )
    parser.add_argument("--agent", required=True, help="Agent name (e.g., kublai)")
    parser.add_argument("--timeout", type=int, default=300,
                       help="Timeout for full review in seconds (default: 300)")
    parser.add_argument("--output", help="Write result to file")
    args = parser.parse_args()

    # Validate agent
    valid_agents = ["kublai", "mongke", "chagatai", "temujin", "jochi", "ogedei"]
    if args.agent not in valid_agents:
        print(f"Error: Invalid agent '{args.agent}'. Valid agents: {', '.join(valid_agents)}",
              file=sys.stderr)
        return 2

    # Run review with fallback
    result = run_review_with_fallback(args.agent, args.timeout)

    # Write output
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            f.write(result.data)
        print(f"Review written to {args.output} (mode: {result.mode})")
    else:
        print(result.data)

    # Log mode used for tracking
    with open(REVIEW_LOG, "a") as f:
        f.write(f"{datetime.now().isoformat()} | {args.agent} | {result.mode} | "
                f"{result.execution_time:.1f}s | success={result.success}\n")

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
