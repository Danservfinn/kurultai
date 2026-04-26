#!/usr/bin/env python3
"""
task-redistribute.py — Move pending tasks from overloaded agents to underutilized ones.

Usage:
    python3 scripts/task-redistribute.py [--dry-run] [--max-move N] [--auto] [--log PATH]

Options:
    --dry-run     Show what would be moved without moving
    --max-move N  Maximum tasks to move per run (default: 10, auto mode: 5)
    --auto        Only run if trigger conditions are met (for cron use)
    --log PATH    Path to log file for redistribution report (JSONL)

This utility implements overflow routing for the Kurultai agent system:
1. Check queue depth for all agents
2. Identify overloaded agents (queue > QUEUE_HIGH_THRESHOLD) and underutilized agents (queue < QUEUE_LOW_THRESHOLD)
3. For each overloaded agent, find movable tasks that match underutilized agent capabilities
4. Move tasks from overloaded to underutilized agents

Auto mode (--auto) uses should_trigger_redistribution() to decide whether to run.
"""

from __future__ import annotations

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
    should_trigger_redistribution,
    REDISTRIBUTION_TRIGGERS,
    create_task,
)
from kurultai_paths import AGENTS_DIR


# Lock file for preventing concurrent redistribution runs
REDISTRIBUTE_LOCK_FILE = "/tmp/redistribute.lock"
REDISTRIBUTE_LOG_FILE = "/Users/kublai/.openclaw/logs/redistribution.jsonl"


def acquire_lock(lock_file=REDISTRIBUTE_LOCK_FILE, timeout_s=0):
    """Acquire exclusive lock using mkdir (atomic on POSIX).

    Returns (success: bool, lock_fd or None).
    If timeout_s > 0, will wait for lock to become available.
    """
    try:
        os.makedirs(lock_file, exist_ok=False)
        # Create pid file
        with open(f"{lock_file}/pid", "w") as f:
            f.write(str(os.getpid()))
        return True, None
    except FileExistsError:
        # Lock exists - check if stale
        pid_file = f"{lock_file}/pid"
        try:
            if os.path.exists(pid_file):
                with open(pid_file) as f:
                    old_pid = int(f.read().strip())
                # Check if process still exists
                try:
                    os.kill(old_pid, 0)
                    return False, None  # Process still running
                except OSError:
                    # Stale lock - remove pid file first, then directory
                    try:
                        os.remove(f"{lock_file}/pid")
                    except FileNotFoundError:
                        pass
                    os.rmdir(lock_file)
                    return acquire_lock(lock_file, timeout_s)
        except (ValueError, FileNotFoundError):
            pass
        return False, None
    except Exception:
        return False, None


def release_lock(lock_file=REDISTRIBUTE_LOCK_FILE):
    """Release the lock by removing the lock directory."""
    try:
        if os.path.exists(lock_file):
            os.remove(f"{lock_file}/pid")
            os.rmdir(lock_file)
    except Exception:
        pass


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
        # Skip terminal-state, executing, hidden, or archived files
        # Comprehensive filter aligned with watchdog-gather.sh terminal states
        # to prevent redistribution of tasks that are no longer actionable
        TERMINAL_MARKERS = (
            '.done', '.executing', '.stale', '.failed', '.obsolete',
            '.cancelled', '.resolved', '.revision', '.no_output', '.loop',
            '.pending-gate', '.blocked', '.quarantine',
        )
        if (any(marker in fname for marker in TERMINAL_MARKERS)
            or fname.startswith('.')
            or 'archived' in fname
            or fname.endswith('.completed.md')):
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


def _count_redistribution_comments(content):
    """Count redistribution HTML comments as secondary bounce detection.

    This works regardless of frontmatter format and serves as a fallback
    safety net when redispatch_count field cannot be inserted/updated.
    """
    return len(re.findall(r'<!-- Task redistributed from ', content))


def _extract_priority(content):
    """Extract priority from either YAML frontmatter or markdown bold format.

    Handles both:
      priority: high       (YAML frontmatter)
      **Priority:** high   (markdown bold, used by watchdog/health alerts)
    """
    # Try YAML format first
    match = re.search(r'^priority:\s*(\w+)$', content, re.MULTILINE)
    if match:
        return match.group(1).lower()
    # Try markdown bold format
    match = re.search(r'^\*\*Priority:\*\*\s*(\w+)', content, re.MULTILINE)
    if match:
        return match.group(1).lower()
    return "normal"


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

    # Validate dest_agent to prevent path traversal
    if dest_agent not in VALID_AGENTS:
        return False, f"Invalid agent name: {dest_agent}"
    # Ensure resolved path is within AGENTS_DIR
    if not dest_dir.resolve().is_relative_to(AGENTS_DIR.resolve()):
        return False, f"Destination path escapes agents directory: {dest_dir}"

    if dry_run:
        return True, f"{dest_dir}/{src_path.name}"

    try:
        dest_path = dest_dir / src_path.name
        # If file exists at destination, append timestamp
        if dest_path.exists():
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            dest_path = dest_dir / f"{src_path.stem}-{timestamp}{src_path.suffix}"

        # Update agent in content — handle both YAML and markdown bold formats
        content = src_path.read_text()
        updated_content = re.sub(r'^agent: \w+$', f'agent: {dest_agent}', content, flags=re.MULTILINE)
        updated_content = re.sub(r'^\*\*Agent:\*\*\s*\w+', f'**Agent:** {dest_agent}', updated_content, flags=re.MULTILINE)

        # Increment redispatch_count to track redistribution cycles
        # This prevents infinite bouncing of tasks between agents
        redispatch_match = re.search(r'^redispatch_count:\s*(\d+)$', updated_content, re.MULTILINE)
        current_count = int(redispatch_match.group(1)) if redispatch_match else 0

        # Secondary safety: count HTML redistribution comments as fallback
        # This works even when redispatch_count field cannot be inserted
        comment_count = _count_redistribution_comments(updated_content)
        current_count = max(current_count, comment_count)

        new_count = current_count + 1

        if redispatch_match:
            # Update existing redispatch_count
            updated_content = re.sub(
                r'^redispatch_count:\s*\d+$',
                f'redispatch_count: {new_count}',
                updated_content,
                flags=re.MULTILINE
            )
        else:
            # Try YAML priority line first
            priority_sub = re.sub(
                r'^(priority:.*)$',
                f'\\1\nredispatch_count: {new_count}',
                updated_content,
                count=1,
                flags=re.MULTILINE
            )
            if priority_sub != updated_content:
                updated_content = priority_sub
            else:
                # Try markdown bold priority line as fallback
                priority_sub = re.sub(
                    r'^(\*\*Priority:\*\*.*)$',
                    f'\\1\nredispatch_count: {new_count}',
                    updated_content,
                    count=1,
                    flags=re.MULTILINE
                )
                if priority_sub != updated_content:
                    updated_content = priority_sub
                else:
                    # Last resort: append as standalone line before first blank line
                    updated_content = re.sub(
                        r'^(\s*$)',
                        f'redispatch_count: {new_count}\n',
                        updated_content,
                        count=1,
                        flags=re.MULTILINE
                    )

        # Add redistribution note with count for visibility
        redistribution_note = f"""
<!-- Task redistributed from {src_path.parent.parent.name} to {dest_agent} at {datetime.now().isoformat()} -->
<!-- Reason: Load balancing - source agent queue depth exceeded threshold -->
<!-- Redispatch count: {new_count} -->
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

    EXEMPTIONS (tasks NOT moved):
    - HIGH priority tasks: require primary agent's attention
    - ops tasks on ogedei: ogedei is PRIMARY for ops domain
    - escalation tasks: critical coordination requiring assigned agent
    - tasks at MAX_RETRY_COUNT (2): already failed max times, don't redistribute
    - tasks at MAX_REDISPATCH_COUNT (3): bounced too many times, need manual review

    IMPORTANT: The MAX_RETRY_COUNT exemption prevents routing audit issues
    where tasks appear as "routed but 0 executed". Tasks at max retries will
    be immediately marked as .failed.done.md by task-watcher's cleanup code
    without execution, causing this discrepancy.

    The MAX_REDISPATCH_COUNT exemption prevents infinite task bouncing
    when a task is genuinely difficult, blocked, or requires a different
    approach than simple load balancing. Tasks hitting this limit should
    trigger manual escalation or quarantine.

    Returns list of (task_path, task_title, dest_agent) tuples.
    """
    pending = get_pending_tasks(overloaded_agent)
    movable = []

    # Get underutilized agents as list of names and a set for O(1) lookups
    underutilized_names = [a for a, _ in underutilized_agents]
    underutilized_set = set(underutilized_names)  # Performance: O(1) lookup vs O(n)

    for fpath, title, content, domain in pending:
        if len(movable) >= max_tasks:
            break

        # EXEMPTION 1: Skip HIGH priority tasks
        # Uses _extract_priority() to handle both YAML and markdown bold formats
        task_priority = _extract_priority(content)
        if task_priority == "high":
            continue

        # EXEMPTION 2: ops tasks stay with ogedei (primary agent for ops domain)
        if domain == "ops" and overloaded_agent == "ogedei":
            continue

        # EXEMPTION 3: escalation tasks require assigned agent (critical coordination)
        if domain == "escalation":
            continue

        # EXEMPTION 4: Skip tasks that have already reached MAX_RETRY_COUNT (2)
        # These tasks have already failed the maximum number of times and
        # redistribution will only cause them to be immediately marked as
        # .failed.done.md by the task-watcher's cleanup code, wasting resources.
        retry_match = re.search(r'^retry_count:\s*(\d+)$', content, re.MULTILINE)
        retry_count = int(retry_match.group(1)) if retry_match else 0
        MAX_RETRY_COUNT = 2  # Must match task-watcher.py MAX_RETRY_COUNT
        if retry_count >= MAX_RETRY_COUNT:
            continue

        # EXEMPTION 5: Skip tasks that have been redispatched too many times
        # This prevents infinite bouncing of tasks between agents when a task
        # is genuinely difficult or blocked (not just queue imbalance).
        # A task that bounces >3 times between agents needs manual escalation.
        redispatch_match = re.search(r'^redispatch_count:\s*(\d+)$', content, re.MULTILINE)
        redispatch_count = int(redispatch_match.group(1)) if redispatch_match else 0
        # Secondary safety: count HTML redistribution comments as fallback
        # This works even when redispatch_count field insertion fails (format mismatch)
        comment_count = _count_redistribution_comments(content)
        effective_redispatch = max(redispatch_count, comment_count)
        MAX_REDISPATCH_COUNT = 3  # Max allowed agent-to-agent moves
        if effective_redispatch >= MAX_REDISPATCH_COUNT:
            # Quarantine the task — rename with .quarantine suffix to prevent
            # it from being picked up by any task scanner
            try:
                quarantine_name = fpath.stem + '.quarantine' + fpath.suffix
                quarantine_path = fpath.parent / quarantine_name
                fpath.rename(quarantine_path)
                import json as _json
                _log_entry = {
                    "event": "task_quarantined",
                    "task": str(fpath),
                    "redispatch_count": effective_redispatch,
                    "comment_count": comment_count,
                    "timestamp": datetime.now().isoformat()
                }
                log_path = Path(REDISTRIBUTE_LOG_FILE)
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with open(log_path, 'a') as _lf:
                    _lf.write(_json.dumps(_log_entry) + '\n')
                # Alert ogedei so quarantined tasks don't silently disappear
                try:
                    task_name = fpath.stem.split('.')[0]
                    create_task(
                        title=f"Quarantined task needs review: {task_name}",
                        body=(
                            f"Task `{fpath.name}` was quarantined after {effective_redispatch} "
                            f"redistribution cycles (max={MAX_REDISPATCH_COUNT}).\n\n"
                            f"**Quarantined path:** {quarantine_path}\n"
                            f"**Redistribution log:** {log_path}\n\n"
                            "Review whether to complete, reassign, cancel, or archive this task. "
                            "If the underlying alert is stale, archive it. "
                            "If it represents real work, dispatch it manually to an available agent."
                        ),
                        priority="high",
                        source="task-redistribute",
                        agent="ogedei",
                        skip_duplicate_check=False,
                    )
                except Exception:
                    pass  # Alert is best-effort; quarantine already succeeded
            except Exception:
                pass  # Best-effort quarantine
            continue

        # 1. Check domain compatibility first, prioritized by DOMAIN_AGENT_COMPATIBILITY order
        # Explicit None handling: skip to keyword fallback if domain is None
        if domain is None:
            # Unknown domain - skip to keyword-based fallback below
            domain_compatible_agents = []
        elif domain in DOMAIN_AGENT_COMPATIBILITY:
            # Get agents in domain priority order, then filter to underutilized
            priority_order = DOMAIN_AGENT_COMPATIBILITY[domain]
            domain_compatible_agents = [
                agent for agent in priority_order
                if agent in underutilized_set  # O(1) lookup
            ]
        else:
            # Unknown domain - log and fall through to keyword matching
            domain_compatible_agents = []

        if domain_compatible_agents:
            # Use the first domain-compatible underutilized agent (now in priority order!)
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
    # Include kublai as overloaded source (coordination tasks can be redistributed)
    # Include tolui as potential destination (tolui can handle implementation/ops/docs)
    overloaded = [(a, d) for a, d in depths.items() if d > QUEUE_HIGH_THRESHOLD]
    underutilized = find_underutilized_agents(exclude={'kublai'})

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
                        help="Maximum tasks to move per run (default: 10, auto mode: 5)")
    parser.add_argument("--auto", action="store_true",
                        help="Only run if trigger conditions are met (for cron use)")
    parser.add_argument("--log", type=str, default=None,
                        help="Path to log file for redistribution report (default: {})".format(REDISTRIBUTE_LOG_FILE))
    args = parser.parse_args()

    # Auto mode: use trigger check and defaults
    if args.auto:
        # Try to acquire lock - exit silently if another instance is running
        lock_acquired, _ = acquire_lock()
        if not lock_acquired:
            # Another instance is running, exit silently
            return 0

        # Check trigger conditions (lock held through entire redistribution)
        should_trigger, reason = should_trigger_redistribution()
        if not should_trigger:
            # No trigger met - release lock and exit silently
            release_lock()
            return 0

        # Auto mode defaults
        max_move = args.max_move if args.max_move != 10 else REDISTRIBUTION_TRIGGERS['max_move_per_cycle']
        log_file = args.log if args.log else REDISTRIBUTE_LOG_FILE
    else:
        max_move = args.max_move
        log_file = args.log
        lock_acquired, _ = acquire_lock()
        if not lock_acquired:
            print("ERROR: Another redistribution is already running (lock file exists)")
            print(f"Lock file: {REDISTRIBUTE_LOCK_FILE}")
            print("If this is stale, remove it manually:")
            print(f"  rm -rf {REDISTRIBUTE_LOCK_FILE}")
            return 1

    try:
        print("=" * 60)
        print("Task Redistribution Utility")
        if args.auto:
            print("AUTO MODE (triggered: {})".format(reason))
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
            max_move=max_move,
            log_file=log_file
        )

        print()
        print(f"Total tasks {'that would be ' if args.dry_run else ''}moved: {moved}")

        if report.get('message'):
            print(f"Status: {report['message']}")

        # Save report if log file specified
        if log_file:
            import json
            try:
                log_path = Path(log_file)
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with open(log_path, 'a') as f:
                    f.write(json.dumps(report) + '\n')
                print(f"Report saved to: {log_file}")
            except Exception as e:
                print(f"Failed to save report: {e}")

        return 0 if moved > 0 or not report.get('overloaded') else 1
    finally:
        release_lock()

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
