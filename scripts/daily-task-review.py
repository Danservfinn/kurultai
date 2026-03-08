#!/usr/bin/env python3
"""
Daily Task Review — Automated quality assurance for all completed tasks.

Runs daily via cron. Scans all tasks completed in the past 24 hours,
creates review tasks using /horde-review, then implementation tasks
using /horde-implement for all suggestions.

Usage:
    python3 daily-task-review.py [--hours N] [--dry-run]

Options:
    --hours N      Look back N hours (default: 24)
    --dry-run      Show what would be created without creating tasks
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kurultai_paths import AGENTS_DIR, SCRIPTS_DIR

# Agent directories to scan (Kurultai core agents)
AGENTS = ["temujin", "mongke", "chagatai", "jochi", "ogedei", "tolui", "kublai"]

# Task file patterns that indicate completion
DONE_SUFFIXES = [
    ".completed.done.md",
    ".done.md",
    ".verified.done.md",
    ".gate-passed.done.md"
]


def find_completed_tasks(hours=24):
    """Find all tasks completed in the last N hours across all agents."""
    cutoff = time.time() - (hours * 3600)
    completed = []
    
    for agent in AGENTS:
        tasks_dir = AGENTS_DIR / agent / "tasks"
        if not tasks_dir.exists():
            continue
        
        for task_file in tasks_dir.glob("*.done.md"):
            try:
                mtime = task_file.stat().st_mtime
                if mtime >= cutoff:
                    # Skip if already reviewed
                    if "_reviewed" in task_file.name:
                        continue
                    
                    # Read task to get metadata
                    content = task_file.read_text()
                    task_info = parse_task_file(task_file, content, agent)
                    completed.append(task_info)
                    
            except (OSError, IOError) as e:
                print(f"Warning: Could not read {task_file}: {e}", file=sys.stderr)
    
    return completed


def parse_task_file(path, content, agent):
    """Extract task metadata from completed task file."""
    info = {
        "agent": agent,
        "file": str(path),
        "filename": path.name,
        "title": "Unknown",
        "completed_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
    }
    
    # Try to parse frontmatter
    if content.startswith("---"):
        try:
            parts = content.split("---", 3)
            if len(parts) >= 3:
                frontmatter = parts[1].strip()
                body = parts[2].strip()
                
                # Parse key fields
                for line in frontmatter.split("\n"):
                    if ":" in line:
                        key, value = line.split(":", 1)
                        key = key.strip().lower()
                        value = value.strip()
                        
                        if key == "title" or key == "task":
                            info["title"] = value
                        elif key == "task_id":
                            info["task_id"] = value
                        elif key == "priority":
                            info["priority"] = value
                        elif key == "skill_hint":
                            info["skill_hint"] = value
                
                info["body"] = body[:500]  # First 500 chars for context
        except Exception:
            pass
    
    # Fallback: use filename as title
    if info["title"] == "Unknown":
        # Remove suffixes to get base name
        base = path.stem
        for suffix in [".completed", ".verified", ".gate-passed"]:
            base = base.replace(suffix, "")
        info["title"] = base.replace("-", " ").replace("_", " ").title()
    
    return info


def create_review_task(task_info, dry_run=False):
    """Create a horde-review task for the completed task."""
    review_title = f"Review: {task_info['title']}"
    
    review_body = f"""# Task Implementation Review

**Original Task:** {task_info['title']}
**Agent:** {task_info['agent']}
**Completed:** {task_info['completed_at']}
**Task File:** `{task_info['filename']}`

## Review Instructions

Use **/horde-review** to critically analyze the implementation of this task across all dimensions:

### Review Areas
1. **Completeness** — Were all requirements met? Any gaps?
2. **Quality** — Code quality, documentation, testing
3. **Performance** — Efficiency, scalability, resource usage
4. **Security** — Vulnerabilities, credential handling, input validation
5. **Architecture** — Design patterns, modularity, maintainability
6. **Edge Cases** — Error handling, boundary conditions
7. **Integration** — How it fits with existing systems

## Original Task Context

{task_info.get('body', 'No body available')}

## Output Required — TWO PHASES

### Phase 1: /horde-review (CRITICAL ANALYSIS)
Use /horde-review to analyze the implementation across all dimensions listed above.

### Phase 2: /horde-implement (IMPLEMENT ALL FIXES)
After /horde-review completes, IMMEDIATELY use /horde-implement to:
1. Create a detailed implementation plan for ALL identified improvements
2. Execute the plan — actually implement the fixes
3. Test the implementation
4. Document what was changed

**Do NOT just create follow-up tasks — IMPLEMENT the improvements directly.**

Only create separate follow-up tasks if:
- The fix requires human action (credentials, approvals)
- The fix is out of scope for this agent
- The fix would take more than 2 hours

## Success Criteria

- [ ] /horde-review completed with comprehensive analysis
- [ ] /horde-implement executed to fix identified issues
- [ ] Implementation tested and verified
- [ ] Any remaining follow-ups properly prioritized and assigned
"""
    
    if dry_run:
        print(f"[DRY-RUN] Would create review task:")
        print(f"  Agent: {task_info['agent']}")
        print(f"  Title: {review_title}")
        print(f"  Priority: high")
        print(f"  Skill: /horde-review")
        print()
        return {"dry_run": True, "title": review_title}
    
    # Create task via task_intake
    try:
        import subprocess
        # Use task_intake.py CLI directly
        cmd = [
            sys.executable,
            str(SCRIPTS_DIR / "task_intake.py"),
            "--title", review_title,
            "--body", review_body,
            "--agent", task_info['agent'],
            "--priority", "high",
            "--skill-hint", "/horde-review",
            "--source", "daily-task-review",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0 and "Task ID:" in result.stdout:
            # Extract task ID from output
            for line in result.stdout.split("\n"):
                if "Task ID:" in line:
                    task_id = line.split("Task ID:")[1].strip()
                    return {"success": True, "task_id": task_id, "title": review_title}
        
        return {"success": False, "error": result.stderr or "Unknown error", "title": review_title}
        
    except Exception as e:
        return {"success": False, "error": str(e), "title": review_title}


def main():
    parser = argparse.ArgumentParser(description="Daily automated task review system")
    parser.add_argument("--hours", type=int, default=24, help="Look back N hours (default: 24)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be created")
    args = parser.parse_args()
    
    print(f"=" * 70)
    print(f"DAILY TASK REVIEW — Scanning tasks from last {args.hours} hours")
    print(f"=" * 70)
    print()
    
    # Find completed tasks
    print(f"Scanning for completed tasks...")
    completed = find_completed_tasks(hours=args.hours)
    
    if not completed:
        print(f"No completed tasks found in last {args.hours} hours.")
        print(f"Done!")
        return 0
    
    print(f"Found {len(completed)} completed task(s):")
    for task in completed:
        print(f"  • [{task['agent']}] {task['title']}")
    print()
    
    # Create review tasks
    print(f"Creating review tasks...")
    print(f"-" * 70)
    
    results = {
        "created": 0,
        "failed": 0,
        "dry_run": 0
    }
    
    for task in completed:
        result = create_review_task(task, dry_run=args.dry_run)
        
        if args.dry_run:
            results["dry_run"] += 1
        elif result.get("success"):
            results["created"] += 1
            print(f"✓ Created: {result['title']} (ID: {result['task_id']})")
        else:
            results["failed"] += 1
            error = result.get('error', 'Unknown error')
            print(f"✗ Failed: {result['title']} - {error}")
    
    print()
    print(f"=" * 70)
    print(f"SUMMARY")
    print(f"=" * 70)
    
    if args.dry_run:
        print(f"Tasks that would be created: {results['dry_run']}")
    else:
        print(f"Review tasks created: {results['created']}")
        print(f"Failed: {results['failed']}")
        
        if results['failed'] > 0:
            print(f"\n⚠️  Some tasks failed to create. Check logs for details.")
    
    print()
    print(f"Next scheduled run: Tomorrow at 3:00 AM")
    print(f"=" * 70)
    
    return 0 if results['failed'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
