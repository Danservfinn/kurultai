#!/usr/bin/env python3
"""
routing_audit_action.py — Create a kublai task when routing audit finds issues.

Called by hourly_reflection.sh before kublai-actions.
Only creates a task if there are actionable issues (not just observations).
Uses task_intake.py to avoid duplicates and respect depth limits.

Usage:
    python3 routing_audit_action.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from routing_audit import generate_audit, format_for_reflection

AUDIT_CACHE = "/Users/kublai/.openclaw/agents/main/logs/routing-audit-latest.json"


def should_create_task(report):
    """Decide whether the audit findings warrant a kublai task."""
    issues = report.get("issues", [])
    if not issues:
        return False

    # Filter out the "no routing decisions" non-issue
    real_issues = [i for i in issues if "No routing decisions logged" not in i]
    if not real_issues:
        return False

    # Only create a task if there are execution failures, stalled dispatch, or high fallback rate
    actionable_keywords = ["failed", "stalled", "backlog", "imbalance", "fallback"]
    actionable = [i for i in real_issues if any(kw in i.lower() for kw in actionable_keywords)]

    return len(actionable) > 0


def main():
    report = generate_audit(hours=1)

    # Cache the report so prepare_reflection_context.py doesn't re-run it
    try:
        with open(AUDIT_CACHE, "w") as f:
            json.dump(report, f, indent=2, default=str)
    except Exception:
        pass

    if not should_create_task(report):
        total = report.get("total_routed", 0)
        if total > 0:
            print(f"Routing audit: {total} tasks routed, no actionable issues")
        return

    # Build task body from the audit
    audit_md = format_for_reflection(report)
    issues = report.get("issues", [])
    suggestions = report.get("suggestions", [])

    body = f"""The hourly routing audit found issues that need your review.

{audit_md}

## Your Action Items

1. Review each issue above against the intended architecture:
   - task_intake.py → LLM router (task-router.py) → filesystem → task-watcher.py → agent-task-handler.py → completion
2. For each issue, decide: is this a routing problem, a dispatch problem, or an agent problem?
3. If you identify a fix (router prompt change, disambiguation rule, queue fix), implement it directly by editing the relevant file.
4. If the fix requires another agent (e.g., temujin for code changes), create a task for them.

Priority: Focus on execution failures and stalled dispatch first. Workload imbalance is secondary.
"""

    # Create task via canonical pipeline
    from task_intake import create_task

    task_id = create_task(
        title="Review routing audit findings and implement improvements",
        body=body,
        priority="normal",
        source="routing_audit",
        agent="kublai",
    )

    if task_id:
        print(f"Routing audit: created kublai task {task_id} ({len(issues)} issues)")
    else:
        print("Routing audit: task creation skipped (duplicate or depth limit)")


if __name__ == "__main__":
    main()
