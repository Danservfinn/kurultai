#!/usr/bin/env python3
"""
task-redistribute.py — Move pending tasks from overloaded agents to underutilized ones.

Usage:
    python3 scripts/task-redistribute.py [--dry-run] [--max-move N]

Options:
    --dry-run     Show what would be moved without moving
    --max-move N  Maximum tasks to move per run (default: 10)

This utility implements overflow routing for the Kurultai agent system:
1. Check queue depth for all agents
2. Identify overloaded agents (queue > 20) and underutilized agents (queue < 5)
3. For each overloaded agent, find movable tasks that match underutilized agent capabilities
4. Move tasks from overloaded to underutilized agents
"""

import os
import sys
import re
import shutil
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from task_intake import (
    VALID_AGENTS,
    AGENT_CAPABILITY_MATRIX,
    get_all_agent_queue_depths,
    get_queue_depth,
    find_underutilized_agents,
    can_handle_task,
    get_capable_alternates,
    QUEUE_HIGH_THRESHOLD,
    QUEUE_LOW_THRESHOLD,
    QUEUE_CRITICAL_THRESHOLD,
    _log_routing_decision,
    DOMAIN_AGENT_COMPATIBILITY,
    classify_task_domain,
    is_domain_compatible,
)
from kurultai_paths import AGENTS_DIR


def get_pending_tasks(agent):
    """Get list of pending tasks for an agent.

    Returns list of (filepath, title, content, domain) tuples.
    """
    task_dir = AGENTS_DIR / agent / "tasks"
    if not task_dir.exists():
        return []

    pending = []
    for fpath in task_dir.iterdir():
        fname = fpath.name
        # Skip done, executing, completed, hidden, or archived files
        # Note: .completed.md is a malformed suffix (should be .completed.done.md)
        # Agents sometimes write these directly, so we must skip them during redistribution
        if ('.done' in fname or '.executing' in fname or fname.startswith('.') or
            'archived' in fname or fname.endswith('.completed.md')):
            continue
        if not fname.endswith('.md'):
            continue

        try:
            content = fpath.read_text()
            # Extract title
            title_match = re.search(r'^# Task: (.+)$', content, re.MULTILINE)
            title = title_match.group(1) if title_match else fname

            # Extract domain from frontmatter
            domain_match = re.search(r'^domain: (\w+)$', content, re.MULTILINE)
            if domain_match:
                domain = domain_match.group(1)
            else:
                # Fallback: classify from title (for tasks created before domain field existed)
                skill_hint_match = re.search(r'^skill_hint: (.+)$', content, re.MULTILINE)
                skill_hint = skill_hint_match.group(1) if skill_hint_match else None
                domain = classify_task_domain(title, skill_hint)

            pending.append((fpath, title, content, domain))
        except Exception:
            continue

    return pending


def move_task(src_path, dest_agent, dry_run=False):
    """Move a task file from one agent to another.

    Args:
        src_path: Path to the task file
        dest_agent: Target agent name
        dry_run: If True, don't actually move

    Returns:
        (success, dest_path or error_message)
    """
    src_path = Path(src_path)
    dest_dir = AGENTS_DIR / dest_agent / "tasks"

    if not dest_dir.exists():
        return False, f"Destination directory does not exist: {dest_dir}"

    if dry_run:
        return True, f"{dest_dir}/{src_path.name}"

    try:
        dest_path = dest_dir / src_path.name
        # If file exists at destination, append timestamp
        if dest_path.exists():
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            dest_path = dest_dir / f"{src_path.stem}-{timestamp}{src_path.suffix}"

        # Update agent in content
        content = src_path.read_text()
        updated_content = re.sub(r'^agent: \w+$', f'agent: {dest_agent}', content, flags=re.MULTILINE)

        # Add redistribution note
        redistribution_note = f"""
<!-- Task redistributed from {src_path.parent.parent.name} at {datetime.now().isoformat()} -->
<!-- Reason: Load balancing - source agent queue depth exceeded threshold -->
"""
        updated_content = updated_content + redistribution_note

        # Write to destination
        dest_path.write_text(updated_content)

        # Remove source
        src_path.unlink()

        return True, str(dest_path)
    except Exception as e:
        return False, str(e)


def find_movable_tasks(overloaded_agent, underutilized_agents, max_tasks=10):
    """Find tasks from overloaded agent that can be moved to underutilized agents.

    Domain compatibility is checked first (if domain field exists in frontmatter).
    Falls back to keyword-based capability matching for tasks without domain.

    Returns list of (task_path, task_title, dest_agent) tuples.
    """
    pending = get_pending_tasks(overloaded_agent)
    movable = []

    # Get underutilized agents as list of names
    underutilized_names = [a for a, _ in underutilized_agents]

    for fpath, title, content, domain in pending:
        if len(movable) >= max_tasks:
            break

        # 1. Check domain compatibility first (explicit domain field in frontmatter)
        domain_compatible_agents = [
            agent for agent in underutilized_names
            if is_domain_compatible(domain, agent)
        ]

        if domain_compatible_agents:
            # Use the first domain-compatible underutilized agent
            dest_agent = domain_compatible_agents[0]
            movable.append((fpath, title, dest_agent))
            continue

        # 2. Fallback: keyword-based capability matching (for backward compat)
        capable = get_capable_alternates(overloaded_agent, title)

        for alt_agent, _ in capable:
            if alt_agent in underutilized_names:
                movable.append((fpath, title, alt_agent))
                break

    return movable


def redistribute_tasks(dry_run=False, max_move=10, log_file=None):
    """Main redistribution logic.

    Args:
        dry_run: If True, only show what would be done
        max_move: Maximum tasks to move per agent pair
        log_file: Optional log file path

    Returns:
        (moved_count, report_dict)
    """
    depths = get_all_agent_queue_depths()

    # Find overloaded and underutilized agents
    overloaded = [(a, d) for a, d in depths.items() if d > QUEUE_HIGH_THRESHOLD and a != 'kublai']
    underutilized = find_underutilized_agents(exclude={'kublai', 'tolui'})

    report = {
        'timestamp': datetime.now().isoformat(),
        'queue_depths': depths,
        'overloaded': overloaded,
        'underutilized': underutilized,
        'moved': [],
        'skipped': []
    }

    if not overloaded:
        report['message'] = "No overloaded agents found (threshold: {})".format(QUEUE_HIGH_THRESHOLD)
        return 0, report

    if not underutilized:
        report['message'] = "No underutilized agents available to receive tasks"
        return 0, report

    total_moved = 0

    for ov_agent, ov_depth in overloaded:
        # Find tasks that can be moved
        movable = find_movable_tasks(ov_agent, underutilized, max_tasks=max_move)

        if not movable:
            report['skipped'].append({
                'agent': ov_agent,
                'reason': 'No movable tasks found (check capability matrix)'
            })
            continue

        for task_path, title, dest_agent in movable:
            success, result = move_task(task_path, dest_agent, dry_run=dry_run)

            if success:
                total_moved += 1
                move_record = {
                    'from': ov_agent,
                    'to': dest_agent,
                    'task': title[:100],
                    'path': str(task_path),
                    'dry_run': dry_run
                }
                report['moved'].append(move_record)

                # Log routing decision
                if not dry_run:
                    _log_routing_decision(
                        title=title,
                        dest=dest_agent,
                        method="redistribution",
                        overflow_reason=f"{ov_agent} queue={ov_depth} > {QUEUE_HIGH_THRESHOLD}",
                        queue_info=depths
                    )

                print(f"  {'[DRY-RUN] ' if dry_run else ''}Moved: {title[:50]}... from {ov_agent} -> {dest_agent}")
            else:
                report['skipped'].append({
                    'agent': ov_agent,
                    'task': title[:50],
                    'reason': f'Move failed: {result}'
                })

    return total_moved, report


def main():
    parser = argparse.ArgumentParser(
        description="Redistribute tasks from overloaded agents to underutilized ones"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be moved without moving")
    parser.add_argument("--max-move", type=int, default=10,
                        help="Maximum tasks to move per run (default: 10)")
    parser.add_argument("--log", type=str, default=None,
                        help="Path to log file for redistribution report")
    args = parser.parse_args()

    print("=" * 60)
    print("Task Redistribution Utility")
    print("=" * 60)
    print()

    # Show current queue depths
    depths = get_all_agent_queue_depths()
    print("Current Queue Depths:")
    for agent, depth in sorted(depths.items(), key=lambda x: -x[1]):
        status = "🔴 OVER" if depth > QUEUE_HIGH_THRESHOLD else "🟡 IDLE" if depth < QUEUE_LOW_THRESHOLD else "🟢 OK"
        print(f"  {agent:12s}: {depth:3d} {status}")
    print()

    # Run redistribution
    if args.dry_run:
        print("DRY RUN MODE - No tasks will be moved")
        print()

    moved, report = redistribute_tasks(
        dry_run=args.dry_run,
        max_move=args.max_move,
        log_file=args.log
    )

    print()
    print(f"Total tasks {'that would be ' if args.dry_run else ''}moved: {moved}")

    if report.get('message'):
        print(f"Status: {report['message']}")

    # Save report if log file specified
    if args.log:
        import json
        try:
            with open(args.log, 'w') as f:
                json.dump(report, f, indent=2)
            print(f"Report saved to: {args.log}")
        except Exception as e:
            print(f"Failed to save report: {e}")

    return 0 if moved > 0 or not report.get('overloaded') else 1


if __name__ == "__main__":
    sys.exit(main())
