#!/usr/bin/env python3
"""
Subprocess Health Check — Detect and clear orphaned agent subprocesses.

Scans all agent task queues for .executing.md tasks and verifies:
1. The .executing.pid file exists and contains a valid PID
2. The PID is actually running (not zombie/stopped)
3. The PID belongs to an agent process (claude-agent or Python)

If any check fails, the stale .executing state is cleared and the orphaned
subprocess is killed if it exists.

Called from watchdog-gather.sh on every tick (5 minutes).

Output format (stdout, one line per issue):
    SUBPROCESS_ISSUE: <agent> orphaned task "<task_title>" - <reason>

Exit codes:
    0 = no issues found
    1 = one or more issues resolved
"""

import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kurultai_paths import AGENTS_DIR

AGENTS = ["temujin", "mongke", "chagatai", "jochi", "ogedei", "kublai", "tolui"]
MAX_EXECUTING_AGE_SECS = 7200  # 2 hours - after this, force clear regardless


def read_pid(pid_file):
    """Read PID from file, return None if invalid."""
    try:
        content = pid_file.read_text().strip()
        if content.isdigit():
            return int(content)
    except Exception:
        pass
    return None


def is_process_running(pid):
    """Check if PID is running and not in stopped state.

    Returns:
        "running" - process is active
        "stopped" - process exists but in T (stopped) state
        "dead" - no such process
    """
    try:
        # Get process status
        result = os.forkpty if hasattr(os, 'forkpty') else (None, None)
        # Simpler approach: use ps via subprocess
        import subprocess
        output = subprocess.check_output(
            ["ps", "-o", "stat=", "-p", str(pid)],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        if not output:
            return "dead"
        # Check for T (stopped) state
        if "T" in output:
            return "stopped"
        return "running"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "dead"


def is_agent_process(pid):
    """Check if PID belongs to an agent process (claude-agent or Python)."""
    try:
        import subprocess
        output = subprocess.check_output(
            ["ps", "-o", "command=", "-p", str(pid)],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        # Check if it's an agent-related process
        return any(keyword in output for keyword in
                   ["claude-agent", "claude", "python", "Python",
                    "task-watcher", "agent-task-handler"])
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def extract_task_title(task_path):
    """Extract task title from task file."""
    try:
        content = task_path.read_text(encoding="utf-", errors="replace")[:1000]
        match = re.search(r'^#\s+Task:\s*(.+)', content, re.MULTILINE)
        if match:
            return match.group(1).strip()
    except Exception:
        pass
    return task_path.stem


def clear_executing_state(task_path, pid_file, reason):
    """Clear stuck .executing state."""
    title = extract_task_title(task_path)

    # Backup the task file
    backup_path = task_path.with_suffix(f".executing.stale-{int(time.time())}.bak")
    try:
        task_path.rename(backup_path)
    except Exception:
        pass

    # Remove PID file
    try:
        pid_file.unlink()
    except Exception:
        pass

    print(f"SUBPROCESS_ISSUE: {task_path.parent.parent.name} cleared '{title}' - {reason}")
    return True


def check_agent_subprocess(agent):
    """Check an agent's executing task for subprocess health issues."""
    tasks_dir = AGENTS_DIR / agent / "tasks"
    if not tasks_dir.exists():
        return []

    issues = []
    executing_files = list(tasks_dir.glob("*.executing.md"))

    for task_file in executing_files:
        pid_file = task_file.with_suffix(".md.executing.pid")
        now = time.time()

        # Check task age
        try:
            task_age = now - task_file.stat().st_mtime
        except Exception:
            task_age = 0

        # Check PID file
        pid = read_pid(pid_file) if pid_file.exists() else None

        if pid is None:
            # No PID file - stale state
            clear_executing_state(task_file, pid_file, "no PID file")
            issues.append("no_pid")
            continue

        # Check if process exists
        proc_status = is_process_running(pid)

        if proc_status == "dead":
            # PID doesn't exist - orphaned state
            clear_executing_state(task_file, pid_file, f"PID {pid} not found")
            issues.append("dead_pid")
            continue

        if proc_status == "stopped":
            # Process is stopped (T state) - kill and clear
            try:
                os.kill(pid, 9)  # SIGKILL
            except Exception:
                pass
            clear_executing_state(task_file, pid_file, f"PID {pid} was stopped")
            issues.append("stopped_pid")
            continue

        # Process is running - check if it's actually an agent process
        if not is_agent_process(pid):
            clear_executing_state(task_file, pid_file, f"PID {pid} not an agent process")
            issues.append("wrong_process")
            continue

        # Task is too old - force clear
        if task_age > MAX_EXECUTING_AGE_SECS:
            try:
                os.kill(pid, 9)
            except Exception:
                pass
            clear_executing_state(task_file, pid_file, f"stale for {int(task_age/60)}min")
            issues.append("stale_task")

    return issues


def recover_and_cleanup_backup_files(recover_age_seconds=86400, cleanup_age_seconds=604800):
    """Recover recent .bak files as re-queued tasks, clean up old ones.

    When a task gets stuck in .executing state, subprocess_health_check creates
    a .bak file. This function:
    1. Re-queues recent .bak files (less than recover_age_seconds) by removing
       the .executing. suffix so task-watcher can pick them up again
    2. Deletes very old .bak files (older than cleanup_age_seconds)

    Args:
        recover_age_seconds: Age threshold for re-queuing (default 24h)
        cleanup_age_seconds: Age threshold for deletion (default 7 days)

    Returns:
        (recovered_count, cleaned_count)
    """
    recovered = 0
    cleaned = 0
    now = time.time()

    for agent in AGENTS:
        tasks_dir = AGENTS_DIR / agent / "tasks"
        if not tasks_dir.exists():
            continue

        for bak_file in tasks_dir.glob("*.bak"):
            try:
                file_age = now - bak_file.stat().st_mtime

                # Re-queue recent backups: remove the .executing.stale-XXX.bak suffix
                # to restore the original .md filename
                if file_age < recover_age_seconds:
                    # Parse filename using regex to handle edge cases:
                    # - "task-123.executing.stale-1234567890.bak" -> "task-123.md"
                    # - "task-123.executing.executing.stale-1234567890.bak" -> "task-123.md" (double suffix)
                    stem = bak_file.stem  # removes .bak
                    # Use regex to strip .executing(.executing)*.stale-TIMESTAMP suffix
                    original_stem = re.sub(r'\.executing(\.executing)*\.stale-\d+$', '', stem)
                    recovered_path = bak_file.parent / f"{original_stem}.md"

                    # Only recover if we got a valid name and recovered file doesn't exist
                    if original_stem != stem and not recovered_path.exists():
                        bak_file.rename(recovered_path)
                        recovered += 1
                        print(f"SUBPROCESS_RECOVER: {agent} re-queued '{recovered_path.name}' ({int(file_age/3600)}h old)")
                    elif recovered_path.exists():
                        # Original exists, just delete the backup
                        bak_file.unlink()
                        print(f"SUBPROCESS_CLEANUP: {agent} removed duplicate backup {bak_file.name} (original exists)")
                    else:
                        # Not a stale backup pattern, just clean up
                        bak_file.unlink()
                        cleaned += 1
                        print(f"SUBPROCESS_CLEANUP: {agent} removed old backup {bak_file.name} ({int(file_age/86400)}d old)")

                # Clean up very old backups
                elif file_age > cleanup_age_seconds:
                    bak_file.unlink()
                    cleaned += 1
                    print(f"SUBPROCESS_CLEANUP: {agent} removed old backup {bak_file.name} ({int(file_age/86400)}d old)")

            except Exception as e:
                # Log but don't fail
                print(f"SUBPROCESS_ERROR: {agent} failed to process {bak_file.name}: {e}")

    return recovered, cleaned


def cleanup_old_backup_files(max_age_seconds=604800):
    """Clean up old .bak files from stale task cleanup.

    DEPRECATED: Use recover_and_cleanup_backup_files() instead.
    Kept for compatibility.

    Args:
        max_age_seconds: Maximum age in seconds (default 7 days)

    Returns:
        Number of files cleaned up
    """
    _, cleaned = recover_and_cleanup_backup_files(cleanup_age_seconds=max_age_seconds)
    return cleaned


def main():
    """Check all agents for subprocess health issues."""
    total_issues = 0

    for agent in AGENTS:
        issues = check_agent_subprocess(agent)
        total_issues += len(issues)

    # Recover and cleanup backup files (run after health checks)
    recovered, cleaned = recover_and_cleanup_backup_files()

    sys.exit(1 if total_issues > 0 else 0)


if __name__ == "__main__":
    main()
