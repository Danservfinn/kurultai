#!/usr/bin/env python3
"""
Subprocess Audit for Tick/Tock Heartbeats

Audits active claude-agent processes and correlates them with executing tasks.
This script is called by watchdog-gather.sh (tick - 5min) and tock-gather.sh (tock - 30min).

Architecture:
    task-watcher.py → agent-task-handler.py → claude-agent --workdir ~/.openclaw/agents/{agent}/

Each executing task has:
    - .executing.md file (task content + execution state)
    - .executing.pid file (handler PID + start timestamp for liveness tracking)

PID Sentinel Format:
    Line 1: <pid>
    Line 2: <start_timestamp_unix>

Anomaly Types:
    - orphaned_executing: .executing.md exists but PID is dead
    - missing_pid_file: .executing.md exists but no .executing.pid sentinel
    - zombie_process: claude-agent/agent-task-handler running but no matching .executing.md
    - stale_execution: PID alive but age > STALE_EXECUTING_AGE (2h)

Output Format (JSON):
    {
      "timestamp": "2026-03-08T13:40:00Z",
      "executing_tasks": [...],
      "anomalies": [...],
      "summary": {"total": N, "alive": N, "dead": N, "orphaned": N, ...}
    }
"""

import os
import sys
import json
import time
import signal
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict

# Configuration
AGENTS_DIR = Path.home() / ".openclaw" / "agents"
VALID_AGENTS = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei", "tolui"]
STALE_EXECUTING_AGE_SECONDS = 7200  # 2 hours

# Process patterns for detection
HANDLER_PATTERN = "agent-task-handler"
CLAUDE_PATTERN = "claude"


@dataclass
class ExecutingTask:
    """Represents an executing task found in agent task directories."""
    agent: str
    task_id: str
    task_file: str  # Full path to .executing.md
    pid: Optional[int]
    alive: bool
    age_seconds: float
    start_timestamp: Optional[float]
    process_type: Optional[str]  # 'handler' or 'claude' or None


@dataclass
class Anomaly:
    """Represents an anomaly detected during audit."""
    type: str  # orphaned_executing, missing_pid_file, zombie_process, stale_execution
    agent: Optional[str]
    task_id: Optional[str]
    pid: Optional[int]
    details: str
    action: str  # recovery_needed, investigate, cleanup_safe


@dataclass
class AuditResult:
    """Complete audit result."""
    timestamp: str
    executing_tasks: List[Dict[str, Any]]
    anomalies: List[Dict[str, Any]]
    summary: Dict[str, int]


def is_pid_alive(pid: int) -> bool:
    """Check if a process is alive using os.kill(pid, 0)."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError, ValueError):
        return False


def get_process_info(pid: int) -> Optional[Dict[str, Any]]:
    """Get process info via ps command."""
    try:
        import subprocess
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "pid,ppid,command"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            if len(lines) >= 2:
                parts = lines[1].split(None, 2)
                if len(parts) >= 3:
                    return {
                        "pid": int(parts[0]),
                        "ppid": int(parts[1]),
                        "command": parts[2][:200]  # Truncate long commands
                    }
    except Exception:
        pass
    return None


def detect_process_type(pid: int) -> Optional[str]:
    """Detect if PID is a handler, claude process, or other."""
    info = get_process_info(pid)
    if not info:
        return None
    cmd = info.get("command", "").lower()
    if HANDLER_PATTERN in cmd:
        return "handler"
    elif CLAUDE_PATTERN in cmd:
        return "claude"
    return "other"


def read_pid_sentinel(pid_file: Path) -> Tuple[Optional[int], Optional[float]]:
    """Read PID sentinel file. Returns (pid, start_timestamp)."""
    try:
        content = pid_file.read_text().strip().split("\n")
        pid = int(content[0]) if content[0].isdigit() else None
        start_ts = float(content[1]) if len(content) > 1 and content[1] else None
        return pid, start_ts
    except Exception:
        return None, None


def find_executing_tasks() -> List[ExecutingTask]:
    """Scan all agent task directories for .executing.md files."""
    executing_tasks = []

    for agent in VALID_AGENTS:
        task_dir = AGENTS_DIR / agent / "tasks"
        if not task_dir.exists():
            continue

        # Find all .executing.md files
        for executing_file in task_dir.glob("*.executing.md"):
            # Extract task_id from filename
            filename = executing_file.name

            # Skip .no_output.executing.md variations by getting the core task name
            # Pattern: priority-taskid.executing.md or priority-taskid.no_output.executing.md
            task_id = filename.replace(".executing.md", "").replace(".no_output", "")

            # Look for corresponding .executing.pid file
            # The PID file might be for the base task name
            pid_file = task_dir / f"{filename.replace('.no_output.executing.md', '.executing.pid').replace('.executing.md', '.executing.pid')}"

            # Actually, the PID file name matches exactly
            pid_file_exact = task_dir / filename.replace(".md", ".pid")

            # Check multiple possible PID file patterns
            possible_pid_files = [
                pid_file_exact,  # exact match
                task_dir / filename.replace(".no_output.executing.md", ".executing.pid"),
                task_dir / filename.replace(".executing.md", ".executing.pid"),
            ]

            pid = None
            start_ts = None
            pid_file_found = None

            for pf in possible_pid_files:
                if pf.exists():
                    pid, start_ts = read_pid_sentinel(pf)
                    pid_file_found = pf
                    break

            # Calculate age
            now = time.time()
            age_seconds = (now - start_ts) if start_ts else 0

            # Check if alive
            alive = False
            process_type = None
            if pid is not None:
                alive = is_pid_alive(pid)
                if alive:
                    process_type = detect_process_type(pid)

            executing_tasks.append(ExecutingTask(
                agent=agent,
                task_id=task_id,
                task_file=str(executing_file),
                pid=pid,
                alive=alive,
                age_seconds=age_seconds,
                start_timestamp=start_ts,
                process_type=process_type
            ))

    return executing_tasks


def find_running_handler_processes() -> Dict[int, Dict[str, Any]]:
    """Find all running agent-task-handler processes."""
    handlers = {}
    try:
        import subprocess
        result = subprocess.run(
            ["pgrep", "-f", HANDLER_PATTERN],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.strip().split("\n"):
            if line.isdigit():
                pid = int(line)
                info = get_process_info(pid)
                if info:
                    handlers[pid] = info
    except Exception:
        pass
    return handlers


def find_running_claude_processes() -> Dict[int, Dict[str, Any]]:
    """Find all running claude processes."""
    processes = {}
    try:
        import subprocess
        result = subprocess.run(
            ["pgrep", "-f", f"claude.*--workdir.*openclaw"],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.strip().split("\n"):
            if line.isdigit():
                pid = int(line)
                info = get_process_info(pid)
                if info:
                    processes[pid] = info
    except Exception:
        pass
    return processes


def detect_anomalies(
    executing_tasks: List[ExecutingTask],
    running_handlers: Dict[int, Dict[str, Any]],
    running_claude: Dict[int, Dict[str, Any]]
) -> List[Anomaly]:
    """Detect anomalies in the task execution state."""
    anomalies = []

    # Build set of PIDs from executing tasks
    executing_pids = {t.pid for t in executing_tasks if t.pid is not None}

    # 1. Orphaned executing files: .executing.md exists but PID is dead
    for task in executing_tasks:
        if task.pid is not None and not task.alive:
            anomalies.append(Anomaly(
                type="orphaned_executing",
                agent=task.agent,
                task_id=task.task_id,
                pid=task.pid,
                details=f"Executing file exists but PID {task.pid} is dead (age: {task.age_seconds:.0f}s)",
                action="recovery_needed"
            ))

        # 2. Missing PID files: .executing.md exists but no PID sentinel
        if task.pid is None:
            anomalies.append(Anomaly(
                type="missing_pid_file",
                agent=task.agent,
                task_id=task.task_id,
                pid=None,
                details=f"Executing file exists but no PID sentinel found",
                action="investigate"
            ))

        # 3. Stale executions: PID alive but age > STALE_EXECUTING_AGE
        if task.alive and task.age_seconds > STALE_EXECUTING_AGE_SECONDS:
            anomalies.append(Anomaly(
                type="stale_execution",
                agent=task.agent,
                task_id=task.task_id,
                pid=task.pid,
                details=f"Process alive but execution age {task.age_seconds/3600:.1f}h exceeds threshold {STALE_EXECUTING_AGE_SECONDS/3600:.1f}h",
                action="recovery_needed"
            ))

    # 4. Zombie processes: handler running but no matching .executing.md
    for pid, info in running_handlers.items():
        if pid not in executing_pids:
            # Check if this is an agent-task-handler for one of our agents
            cmd = info.get("command", "")
            matched_agent = None
            for agent in VALID_AGENTS:
                if f"/{agent}/" in cmd or f"--agent {agent}" in cmd:
                    matched_agent = agent
                    break

            if matched_agent:
                anomalies.append(Anomaly(
                    type="zombie_process",
                    agent=matched_agent,
                    task_id=None,
                    pid=pid,
                    details=f"Handler process running but no .executing.md file found",
                    action="investigate"
                ))

    return anomalies


def run_audit() -> AuditResult:
    """Run the complete subprocess audit."""
    timestamp = datetime.now(timezone.utc).isoformat()

    # Find all executing tasks
    executing_tasks = find_executing_tasks()

    # Find running processes
    running_handlers = find_running_handler_processes()
    running_claude = find_running_claude_processes()

    # Detect anomalies
    anomalies = detect_anomalies(executing_tasks, running_handlers, running_claude)

    # Build summary
    summary = {
        "total_executing": len(executing_tasks),
        "alive": sum(1 for t in executing_tasks if t.alive),
        "dead": sum(1 for t in executing_tasks if t.pid is not None and not t.alive),
        "missing_pid": sum(1 for t in executing_tasks if t.pid is None),
        "stale": sum(1 for t in executing_tasks if t.alive and t.age_seconds > STALE_EXECUTING_AGE_SECONDS),
        "running_handlers": len(running_handlers),
        "running_claude": len(running_claude),
        "anomaly_count": len(anomalies)
    }

    return AuditResult(
        timestamp=timestamp,
        executing_tasks=[asdict(t) for t in executing_tasks],
        anomalies=[asdict(a) for a in anomalies],
        summary=summary
    )


def main():
    """Main entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="Audit claude-agent subprocess state")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--summary-only", action="store_true", help="Only output summary")
    args = parser.parse_args()

    result = run_audit()

    if args.summary_only:
        # Compact summary for log files
        s = result.summary
        print(f"SUBPROCESS_AUDIT: total={s['total_executing']} alive={s['alive']} dead={s['dead']} "
              f"stale={s['stale']} anomalies={s['anomaly_count']} handlers={s['running_handlers']} "
              f"claude={s['running_claude']}")
        if result.anomalies:
            for a in result.anomalies:
                print(f"  ANOMALY: {a['type']} agent={a['agent']} task={a['task_id']} action={a['action']}")
    elif args.json:
        print(json.dumps(asdict(result), indent=2))
    else:
        # Human-readable format
        print(f"Subprocess Audit: {result.timestamp}")
        print(f"\nSummary:")
        s = result.summary
        print(f"  Executing tasks: {s['total_executing']} (alive: {s['alive']}, dead: {s['dead']}, stale: {s['stale']})")
        print(f"  Running handlers: {s['running_handlers']}")
        print(f"  Running claude: {s['running_claude']}")
        print(f"  Anomalies: {s['anomaly_count']}")

        if result.executing_tasks:
            print(f"\nExecuting Tasks:")
            for t in result.executing_tasks:
                status = "ALIVE" if t['alive'] else "DEAD" if t['pid'] else "NO_PID"
                age_m = t['age_seconds'] / 60
                print(f"  [{t['agent']}] {t['task_id'][:40]}... pid={t['pid']} status={status} age={age_m:.1f}m")

        if result.anomalies:
            print(f"\nAnomalies:")
            for a in result.anomalies:
                print(f"  [{a['type']}] {a['agent']}/{a['task_id']}: {a['details']}")
                print(f"    → Action: {a['action']}")


if __name__ == "__main__":
    main()
