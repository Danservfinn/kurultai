#!/usr/bin/env python3
from __future__ import annotations
"""
Fix Missing Resolutions — Auto-remediate tasks missing resolution sections.

Scans agent task directories for .no_output, .unverified, and .done.md files
missing resolution sections, then creates follow-up tasks for the owning agent.

This addresses the /horde-review PRIORITY_FIX:
"Ensure agents include resolution sections in task outputs"

Usage:
    python3 fix-missing-resolutions.py --agent mongke --dry-run
    python3 fix-missing-resolutions.py --agent mongke --execute
    python3 fix-missing-resolutions.py --all-agents --execute

Run periodically (e.g., via tock) to clean up incomplete completions.
"""

import argparse
import json
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kurultai_paths import AGENTS_DIR
from gate_utils import validate_task_id, sanitize_task_id_for_glob

# Resolution section patterns (matches quality_gate.py)
RESOLUTION_PATTERNS = [
    r"## Resolution",
    r"\*\*Status:\*\*",
    r"## Result",
    r"## Summary",
]

RESOLUTION_REGEX = re.compile("|".join(RESOLUTION_PATTERNS), re.IGNORECASE)

# Quality thresholds (from quality_gate.py)
MIN_CONTENT_CHARS = 100  # Only require resolution for substantive content

# Incomplete file patterns to check
INCOMPLETE_PATTERNS = [
    ".no_output",
    ".unverified",
    ".unverified.unverified",
]


def has_resolution_section(content: str) -> bool:
    """Check if content has a resolution section."""
    # Extract output after frontmatter
    lines = content.split("\n")

    # Skip YAML frontmatter
    start_idx = 0
    if lines and lines[0].strip() == "---":
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                start_idx = i + 1
                break

    output = "\n".join(lines[start_idx:])
    output_stripped = output.strip()

    # Empty content requires resolution (to explain why)
    if len(output_stripped) == 0:
        return False

    # Check for resolution patterns
    return bool(RESOLUTION_REGEX.search(output))


def extract_task_metadata(file_path: Path) -> dict:
    """Extract task metadata from frontmatter."""
    try:
        with open(file_path, "r") as f:
            content = f.read()

        # Parse YAML frontmatter
        if not content.startswith("---"):
            return {}

        end_idx = content.find("---", 3)
        if end_idx == -1:
            return {}

        frontmatter_str = content[3:end_idx]
        metadata = {}

        for line in frontmatter_str.split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                metadata[key.strip()] = value.strip()

        return metadata
    except Exception:
        return {}


def find_incomplete_tasks(agent: str) -> list[dict]:
    """Find tasks missing resolution sections."""
    agent_tasks_dir = AGENTS_DIR / agent / "tasks"
    if not agent_tasks_dir.exists():
        return []

    incomplete = []

    # Check all .md files
    for file_path in agent_tasks_dir.glob("*.md"):
        # Skip executing files
        if file_path.name.endswith(".executing.md"):
            continue

        # Skip failed tasks — they crashed, so missing resolution is expected
        # Creating fix-resolution tasks for crashes causes cascading failures
        if ".failed." in file_path.name:
            continue

        # Skip existing fix-resolution tasks (prevent cascade loops)
        if "fix-resolution" in file_path.name:
            continue

        # FIX 2026-03-23: Skip .no_output tasks — these represent zero-execution
        # failures (R008_VIOLATION, credential failures, session startup stalls).
        # Adding a fix-resolution task to a zero-execution task fabricates evidence
        # of completion that never occurred; these tasks need re-dispatch, not docs.
        # Root cause of the 1773979337 cascade: .no_output files were treated the
        # same as .done files, causing fabricated "resolution" sections to be accepted
        # by the quality gate with no actual investigation performed.
        if ".no_output" in file_path.name:
            continue

        # Check for incomplete patterns (excluding .no_output — handled above)
        is_incomplete_type = any(
            file_path.name.endswith(pattern) for pattern in INCOMPLETE_PATTERNS
            if pattern != ".no_output"
        )

        # Also check .done.md files for missing resolutions
        is_done_file = file_path.name.endswith(".done.md")

        if not is_incomplete_type and not is_done_file:
            continue

        try:
            content = file_path.read_text()

            if not has_resolution_section(content):
                metadata = extract_task_metadata(file_path)

                # FIX 2026-03-23: Skip tasks that explicitly opt out of the completion gate.
                # Tasks with completion_gate_optout: true (e.g., triage/coordination tasks
                # created by kublai-actions.py) should never trigger fix-up tasks — they
                # opted out precisely because they produce coordination artifacts, not code.
                # Without this check, the optout flag is written but never respected here,
                # causing the same cascade it was meant to prevent.
                optout = metadata.get("completion_gate_optout", "").strip().lower()
                if optout in ("true", "1", "yes"):
                    continue

                incomplete.append({
                    "path": str(file_path),
                    "filename": file_path.name,
                    "task_id": metadata.get("task_id", file_path.stem),
                    "title": metadata.get("title", "Unknown"),
                    "priority": metadata.get("priority", "normal"),
                    "original_agent": agent,
                    "missing_since": datetime.fromtimestamp(
                        file_path.stat().st_mtime
                    ).isoformat(),
                })
        except Exception as e:
            print(f"[WARN] Failed to read {file_path}: {e}")

    return incomplete


def create_fixup_task(incomplete_task: dict, dry_run: bool = False) -> str | None:
    """Create a follow-up task to add the missing resolution section.

    CASCADE PREVENTION (2026-03-12): Limits fix-resolution tasks per parent to 2.
    Previous cascade: 30 fix-resolution tasks spawned from single parent 1773227787
    across 6 agents, all failing and creating more fix attempts.
    """
    agent = incomplete_task["original_agent"]
    task_id = incomplete_task["task_id"]

    # CASCADE BREAKER: Check how many fix-resolution tasks already exist for this parent
    # FIX 2026-03-23: Sanitize task_id before using in glob pattern. Unsanitized IDs
    # containing glob metacharacters (*, ?, [, ]) caused the cascade breaker to fail
    # silently — confirmed root cause of 16-task cascade for a single parent task.
    # sanitize_task_id_for_glob() strips *, ?, [, ] before the glob call.
    agent_tasks_dir = AGENTS_DIR / agent / "tasks"
    safe_task_id_for_glob = sanitize_task_id_for_glob(task_id)
    existing_fixes = list(agent_tasks_dir.glob(f"*fix-resolution-*{safe_task_id_for_glob}*"))
    if len(existing_fixes) >= 2:
        print(f"  SKIP: {task_id} already has {len(existing_fixes)} fix-resolution tasks (max 2)")
        return None

    # New fixup task ID
    fixup_id = f"fix-resolution-{task_id}-{uuid.uuid4().hex[:8]}"
    priority = incomplete_task.get("priority", "normal")
    title = incomplete_task.get("title", task_id)

    # Build task frontmatter
    frontmatter_lines = [
        "---",
        f"agent: {agent}",
        f"priority: {priority}",
        f"created: {datetime.now().isoformat()}",
        f"source: fix-missing-resolutions",
        f"task_id: {fixup_id}",
        f"parent_task: {task_id}",
        f"bucket: TODAY",
        f"domain: completion",
        f"timeout: 1800",
        f"skill_hint: null",
        "---",
    ]

    # Build task body
    body_lines = [
        f"# Task: Add Resolution Section to {title}",
        "",
        "This is a **quality fix-up task** for a previously completed task",
        f"that is missing its resolution section.",
        "",
        f"## Original Task",
        "",
        f"**ID:** `{task_id}`",
        f"**File:** `{incomplete_task['filename']}`",
        f"**Missing since:** {incomplete_task['missing_since']}",
        "",
        "## What to Do",
        "",
        "1. Read the original task file to understand what was done",
        "2. Add a proper **## Resolution** section that summarizes:",
        "   - What was actually implemented/completed",
        "   - The final outcome or result",
        "   - Any known limitations or next steps",
        "3. Use one of these formats (any will work):",
        "   - `## Resolution`",
        "   - `## Result`",
        "   - `## Summary`",
        "   - `**Status:** <status>`",
        "",
        "## Example Resolution Section",
        "",
        "```markdown",
        "## Resolution",
        "",
        "Implemented feature X with the following changes:",
        "- Added function Y to handle Z",
        "- Updated configuration",
        "",
        "Status: Complete and ready for production.",
        "```",
        "",
        f"---\n_Generated by fix-missing-resolutions.py at {datetime.now().isoformat()}_",
    ]

    task_content = "\n".join(frontmatter_lines) + "\n" + "\n".join(body_lines) + "\n"

    # Write task file
    task_filename = f"{priority}-{fixup_id}.md"
    task_path = AGENTS_DIR / agent / "tasks" / task_filename

    if dry_run:
        print(f"  Would create: {task_path}")
        return None

    try:
        task_path.parent.mkdir(parents=True, exist_ok=True)
        with open(task_path, "w") as f:
            f.write(task_content)
        print(f"  Created: {task_path}")
        return str(task_path)
    except Exception as e:
        print(f"  ERROR creating task: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Fix tasks missing resolution sections",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--agent",
        choices=["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei"],
        help="Specific agent to scan",
    )
    parser.add_argument(
        "--all-agents",
        action="store_true",
        help="Scan all agents",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without creating tasks",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually create fix-up tasks (required for changes)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    args = parser.parse_args()

    if args.all_agents:
        agents = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei"]
    elif args.agent:
        agents = [args.agent]
    else:
        # Default to mongke since all 6 issues are from mongke
        agents = ["mongke"]

    # Scan agents
    all_incomplete = []
    for agent in agents:
        print(f"\n=== Scanning {agent} ===")
        incomplete = find_incomplete_tasks(agent)
        print(f"Found {len(incomplete)} tasks missing resolution section")
        all_incomplete.extend(incomplete)

    if not all_incomplete:
        print("\n✓ No tasks missing resolution sections")
        return 0

    print(f"\n=== Total: {len(all_incomplete)} tasks need fixing ===")

    # Show what we found
    for task in all_incomplete:
        print(f"  - {task['filename']}: {task['title']}")

    # Create fix-up tasks
    if args.dry_run:
        print("\n=== Dry run - no tasks created ===")
        for task in all_incomplete:
            create_fixup_task(task, dry_run=True)
        return 0

    if args.execute:
        print("\n=== Creating fix-up tasks ===")
        created = []
        for task in all_incomplete:
            result = create_fixup_task(task, dry_run=False)
            if result:
                created.append(result)

        print(f"\n✓ Created {len(created)} fix-up tasks")

        # Save scan report
        report_path = (
            AGENTS_DIR / "main" / "logs" / "fix-missing-resolutions-report.json"
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w") as f:
            json.dump(
                {
                    "timestamp": datetime.now().isoformat(),
                    "scanned_agents": agents,
                    "found": len(all_incomplete),
                    "created": len(created),
                    "tasks": all_incomplete,
                    "created_tasks": created,
                },
                f,
                indent=2,
            )
        print(f"Report saved to: {report_path}")
        return 0

    # Default: show JSON output
    if args.json:
        print(json.dumps(all_incomplete, indent=2))
    else:
        print("\nUse --dry-run to preview, --execute to create fix-up tasks")

    return 1


if __name__ == "__main__":
    sys.exit(main())
