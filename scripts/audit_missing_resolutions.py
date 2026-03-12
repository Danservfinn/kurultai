#!/usr/bin/env python3
"""
Audit task completion reports for missing resolution sections.

Jochi's quality assurance script - scans completed task reports and flags
those missing acceptable resolution headers.

ACCEPTED RESOLUTION PATTERNS (must match task_verification.py):
- ## Resolution (explicit, preferred for manual updates)
- ## What Was Done (auto-generated report standard)
- ## Summary (alternative summary)
- ## Changes Made (change-focused)
- ## Files (Created|Modified) (file-centric)
- ## Acceptance Criteria (verification-focused)
- ## Deliverables (output-focused, auto-generated)

This script is run by watchdog-gather.sh to monitor task completion quality.
If compliance < 90%, system status is marked as degraded.

Usage:
    python scripts/audit_missing_resolutions.py [--agent AGENT] [--recent HOURS]
"""

import argparse
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path


REPORTS_DIR = Path("/Users/kublai/.openclaw/agents/main/reports/completed")
AUDIT_LOG = Path("/Users/kublai/.openclaw/agents/main/logs/missing-resolutions-audit.jsonl")


def parse_report(filepath: Path) -> dict:
    """Extract metadata and check for resolution section."""
    content = filepath.read_text()

    # Extract task ID from filename or content
    task_id = filepath.stem

    # Parse frontmatter-like header
    agent = "unknown"
    status = "unknown"
    completed = None
    priority = "unknown"

    for line in content.split("\n")[:50]:
        if line.startswith("**Agent:**"):
            agent = line.split("**Agent:**")[1].strip().lower()
        elif line.startswith("**Status:**"):
            status = line.split("**Status:**")[1].strip()
        elif line.startswith("**Completed:**"):
            try:
                completed = datetime.strptime(line.split("**Completed:**")[1].strip(), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass
        elif line.startswith("**Priority:**"):
            priority = line.split("**Priority:**")[1].strip().lower()

    # Check for resolution section (matches accepted patterns from task_verification.py
    # and auto-generated reports from task_report_hook.py)
    #
    # Auto-generated reports use "## What Was Done" as their execution summary.
    # For manual updates, agents should add explicit resolution headers.
    resolution_patterns = [
        r"^## Resolution\s*$",           # Explicit resolution (preferred)
        r"^## What Was Done\s*$",         # Auto-generated report standard
        r"^## Summary\s*$",               # Alternative summary header
        r"^## Changes Made\s*$",          # Change-focused summary
        r"^## Files (Created|Modified)\s*$",  # File-centric summary
        r"^## Acceptance Criteria\s*$",   # Verification-focused
        r"^## Deliverables\s*$",          # Output-focused (auto-generated)
    ]
    has_resolution = any(re.search(p, content, re.MULTILINE) for p in resolution_patterns)

    # Check if file was updated by an agent (has "*Updated by" in footer)
    was_updated = bool(re.search(r"\*Updated by \w+ at", content))

    return {
        "task_id": task_id,
        "agent": agent,
        "status": status,
        "priority": priority,
        "completed": completed.isoformat() if completed else None,
        "has_resolution": has_resolution,
        "was_updated": was_updated,
        "file": str(filepath.name),
    }


def main():
    parser = argparse.ArgumentParser(description="Audit task reports for missing resolution sections")
    parser.add_argument("--agent", help="Filter by agent (e.g., temujin, mongke)")
    parser.add_argument("--recent", type=int, default=24, help="Only scan reports from last N hours")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    args = parser.parse_args()

    cutoff = datetime.now() - timedelta(hours=args.recent)
    reports = list(REPORTS_DIR.glob("*.md"))

    results = []
    missing_resolutions = []

    for report_path in reports:
        if report_path.name.startswith("."):
            continue

        data = parse_report(report_path)

        # Filter by agent if specified
        if args.agent and data["agent"] != args.agent.lower():
            continue

        # Filter by recency
        if data["completed"]:
            completed_dt = datetime.fromisoformat(data["completed"])
            if completed_dt < cutoff:
                continue

        results.append(data)

        # Flag missing resolution - only for reports that SHOULD have one
        # Pattern: fix-, implement-, or task was manually updated by an agent
        should_have_resolution = (
            data["status"] == "✅ Completed" and (
                data["task_id"].startswith("fix-") or
                data["task_id"].startswith("implement-") or
                data["task_id"].startswith("high-") or
                data["task_id"].startswith("normal-") or
                data["task_id"].startswith("low-") or
                data["was_updated"]  # Agent manually updated the report
            )
        )

        if should_have_resolution and not data["has_resolution"]:
            missing_resolutions.append(data)

    # Summary stats
    total = len(results)
    with_resolution = sum(1 for r in results if r["has_resolution"])
    without_resolution = total - with_resolution
    completion_rate = (with_resolution / total * 100) if total > 0 else 0

    # Prepare output
    output = {
        "timestamp": datetime.now().isoformat(),
        "scan_period_hours": args.recent,
        "total_completed": total,
        "with_resolution": with_resolution,
        "without_resolution": without_resolution,
        "completion_rate_percent": round(completion_rate, 1),
        "missing": missing_resolutions,
    }

    # Write to audit log
    with open(AUDIT_LOG, "a") as f:
        f.write(json.dumps(output) + "\n")

    if args.json:
        print(json.dumps(output, indent=2))
    else:
        print(f"\n=== Task Resolution Audit (last {args.recent}h) ===\n")
        print(f"Total completed reports: {total}")
        print(f"With resolution section: {with_resolution}")
        print(f"Missing resolution: {without_resolution}")
        print(f"Resolution compliance: {completion_rate:.1f}%\n")

        if missing_resolutions:
            print(f"⚠️  Reports missing resolution section:\n")
            for m in missing_resolutions[:10]:
                updated_mark = " (was updated)" if m["was_updated"] else ""
                print(f"  - [{m['agent']}] {m['task_id']}{updated_mark}")
            if len(missing_resolutions) > 10:
                print(f"  ... and {len(missing_resolutions) - 10} more")
            print(f"\n💡 Agents should add '## Resolution' section after the footer")
        else:
            print("✅ All reports have resolution sections!")

    # Exit with error code if compliance < 90%
    if completion_rate < 90:
        return 1
    return 0


if __name__ == "__main__":
    exit(main())
