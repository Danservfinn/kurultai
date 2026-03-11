#!/usr/bin/env python3
"""
Task Watcher - Concurrent Task Execution + Spawn Queue Processing

Watches agent task directories for new tasks and executes them immediately
(within seconds of creation). Each agent gets its own execution slot so
all 6 agents can run Claude Code tasks in parallel.

Also processes the spawn queue (spawn-pending.json) on every cycle, routing
subagent spawn requests to agent task queues or launching Claude Code directly.
This replaces the 2-minute cron-based spawn-consumer for near-instant spawning.

Usage:
    python3 scripts/task-watcher.py [--poll-interval <seconds>] [--daemon]

Run as daemon:
    nohup python3 scripts/task-watcher.py --daemon > logs/task-watcher.log 2>&1 &

Or via launchd (recommended for macOS):
    launchctl load ~/Library/LaunchAgents/com.kurultai.task-watcher.plist
"""

import os
import re
import sys
import time
import subprocess
import signal
import json
import fcntl
from pathlib import Path
from datetime import datetime, timedelta
from threading import Thread, Event, Lock
from concurrent.futures import ThreadPoolExecutor, Future

sys.path.insert(0, str(Path(__file__).parent))
from json_state import locked_json_read, locked_json_update
from kurultai_paths import (
    AGENTS_DIR, TASK_LEDGER, SPAWN_QUEUE, WATCHER_STATE as STATE_FILE,
    VALID_AGENTS as _VALID_AGENTS, CLAUDE_AGENT as _CLAUDE_AGENT_PATH,
    agent_sessions_path as _agent_sessions_path,
    SESSION_BLOAT_THRESHOLD as _SESSION_BLOAT_THRESHOLD,
)
from kurultai_ledger import append_ledger as _kp_append_ledger
from task_verification import verify_task_completion, SLOW_SKILLS

# Circuit breaker for agent health
try:
    from circuit_breaker import AgentCircuitBreaker
    _circuit_breaker = AgentCircuitBreaker()
except Exception as e:
    log(f"Circuit breaker init failed (non-fatal): {e}")
    _circuit_breaker = None

# Neo4j sync — lazy-loaded, never blocks task execution
_neo4j_driver = None

def _get_neo4j_driver():
    """Lazy-load Neo4j driver. Returns None if unavailable."""
    global _neo4j_driver
    if _neo4j_driver is None:
        try:
            from neo4j_task_tracker import get_driver
            _neo4j_driver = get_driver()
        except Exception as e:
            log(f"Neo4j driver init failed (non-fatal): {e}")
            return None
    return _neo4j_driver


def get_pending_tasks_from_neo4j(agent: str, limit: int = 10) -> list[dict]:
    """Get pending tasks from Neo4j (single source of truth).

    Queries Neo4j for PENDING tasks assigned to this agent.
    Returns list of dicts with task_id, title, body, priority, skill_hint.

    Falls back to filesystem scan if Neo4j unavailable.
    """
    driver = _get_neo4j_driver()
    if not driver:
        return []  # Fallback handled by caller

    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (t:Task {agent: $agent, status: 'PENDING'})
                RETURN t.task_id as task_id, t.title as title, t.body as body,
                       t.priority as priority, t.skill_hint as skill_hint,
                       t.created as created, t.bucket as bucket
                ORDER BY
                    CASE t.priority WHEN 'critical' THEN 0
                                     WHEN 'high' THEN 1
                                     WHEN 'normal' THEN 2
                                     ELSE 3 END,
                    t.created ASC
                LIMIT $limit
            """, agent=agent, limit=limit)
            return [dict(r) for r in result]
    except Exception as e:
        log(f"Neo4j pending task query failed for {agent}: {e}")
        return []


def claim_task_atomic(task_id: str, agent: str) -> tuple[bool, str]:
    """Atomically claim a task using Neo4j CAS pattern.

    Returns (success, session_key) tuple.
    session_key is used to verify ownership during execution.
    """
    import time
    try:
        from neo4j_atomic_transitions import claim_task
        session_key = f"{agent}-{time.time()}"
        success, reason = claim_task(task_id, agent, session_key)
        if not success:
            # Log the specific reason for failure
            log(f"SKIP: Task {task_id} - {reason}")
        return success, session_key if success else ""
    except Exception as e:
        log(f"Atomic claim failed for {task_id}: {e}")
        return False, ""


def check_neo4j_task_status(task_id: str) -> dict | None:
    """Check task status in Neo4j (source of truth).

    Returns dict with status, retry_count, session_key or None if not found.
    """
    driver = _get_neo4j_driver()
    if not driver:
        return None

    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (t:Task {task_id: $task_id})
                RETURN t.status as status, t.retry_count as retry_count,
                       t.session_key as session_key, t.claimed_by as claimed_by
            """, task_id=task_id)
            record = result.single()
            return dict(record) if record else None
    except Exception as e:
        log(f"Neo4j status check failed for {task_id}: {e}")
        return None


def _extract_task_id(task_file) -> str | None:
    """Extract task_id from task file frontmatter.

    Returns the task_id or None if not found.
    """
    try:
        content = task_file.read_text(encoding="utf-8", errors="replace")[:2000]
        match = re.search(r'^task_id:\s*(\S+)', content, re.MULTILINE)
        return match.group(1) if match else None
    except Exception:
        return None


def _neo4j_update_status(task_id, status, agent=None, error_msg=None):
    """Fire-and-forget Neo4j status update. Never raises."""
    if not task_id:
        return
    try:
        driver = _get_neo4j_driver()
        if not driver:
            return
        with driver.session() as session:
            is_terminal = status in ('COMPLETED', 'FAILED', 'TIMEOUT', 'CANCELLED')
            session.run("""
                MATCH (t:Task {task_id: $task_id})
                SET t.status = $status,
                    t.updated = datetime(),
                    t.error = CASE WHEN $error IS NOT NULL THEN $error ELSE t.error END,
                    t.started = CASE WHEN $status = 'EXECUTING' THEN datetime() ELSE t.started END,
                    t.completed = CASE WHEN $is_terminal THEN datetime() ELSE t.completed END
            """, task_id=task_id, status=status, error=error_msg, is_terminal=is_terminal)
    except Exception as e:
        log(f"Neo4j update failed for {task_id}->{status} (non-fatal): {e}")


def _neo4j_reconcile():
    """Run Neo4j/filesystem state reconciliation. Never raises."""
    try:
        from neo4j_task_tracker import TaskTracker
        tracker = TaskTracker()
        try:
            result = tracker.sync_reconcile()
            if result.get("fixed", 0) > 0:
                log(f"NEO4J RECONCILE: fixed {result['fixed']}/{result['discrepancies']} discrepancies (skipped {result['skipped']})")
        finally:
            tracker.close()
    except Exception as e:
        log(f"Neo4j reconcile failed (non-fatal): {e}")


# Force unbuffered output for launchd (stdout goes to file)
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Configuration (paths imported from kurultai_paths above)
CLAUDE_AGENT = str(_CLAUDE_AGENT_PATH)
POLL_INTERVAL_DEFAULT = 15  # seconds
TIMEOUT_DEFAULT = 7200  # 2 hours for Claude Code execution
TIMEOUT_BY_PRIORITY = {
    'high': 7200,   # 2 hours for complex high-priority tasks
    'normal': 7200, # 2 hours
    'low': 7200,    # 2 hours
}
CLEANUP_INTERVAL = 300  # Run cleanup every 5 minutes (aligned with tick heartbeat)
DONE_FILE_MAX_AGE = 48 * 3600  # 48 hours in seconds
MAX_CONCURRENT_AGENTS = 6  # One slot per agent
VALID_AGENTS = _VALID_AGENTS | {"subagent"}
SPAWN_TIMEOUT_MINUTES = 30  # Mark running spawns as completed after this
STALE_EXECUTING_AGE = max(TIMEOUT_BY_PRIORITY.values()) + 120  # max timeout + 2min buffer: mark .executing files as failed after this
HARD_MAX_EXECUTING_AGE = 10800  # 3 hours: kill and recover regardless of PID status (prevents zombie accumulation across watcher restarts)
MAX_RETRY_COUNT = 2  # After this many retries, mark as .failed.done permanently
RATE_LIMIT_COOLDOWN = 120  # Seconds to wait before retrying a rate-limited task

# Notification config
SEND_SIGNAL_SCRIPT = Path.home() / ".claude" / "skills" / "agent-collaboration" / "scripts" / "send_signal.sh"
NOTIFY_ON_COMPLETE = True  # Send Signal + webapp notification when tasks finish
VERIFY_ON_COMPLETE = True  # Run post-completion verification

# Global state for daemon mode
stop_event = Event()
print_lock = Lock()

# Track which agents currently have a task executing
# Maps agent_name -> Future
active_executions: dict[str, Future] = {}
active_lock = Lock()


def _verify_task_completion(task_file, max_retries=3):
    """Verify task file has actual execution output before marking as complete.

    CRITICAL FIX: This function now requires the presence of an "## Execution Output"
    section to distinguish actual execution results from the original task description.

    RACE CONDITION FIX (2026-03-08): Uses file locking to prevent false positives
    when the handler is still writing output. If verification fails, retries with
    exponential backoff to handle slow writes.

    RESOLUTION CHECK (2026-03-09): Substantive completions (>=100 chars) must include
    a resolution section ("## Resolution" or similar) matching /horde-review PRIORITY_FIX.

    Checks:
    - Has "## Execution Output" section (added by _append_output_to_executing)
    - Content AFTER "## Execution Output" has substance (not just empty)
    - At least 4 non-empty lines of actual execution output
    - Resolution section present for substantive outputs (>=100 chars)

    Returns tuple: (is_valid, reason)
    """
    for attempt in range(max_retries):
        try:
            # Acquire shared lock to wait for any writer to finish
            # LOCK_SH (shared) will block if another process has LOCK_EX (exclusive)
            fd = None
            try:
                fd = os.open(task_file, os.O_RDONLY)
                fcntl.flock(fd, fcntl.LOCK_SH)  # Wait for exclusive lock to release
            except (FileNotFoundError, OSError):
                # File might have been renamed between check and open
                if attempt < max_retries - 1:
                    time.sleep(0.1 * (2 ** attempt))  # Exponential backoff
                    continue
                else:
                    return False, f"Verification error: file unavailable after {max_retries} retries"

            try:
                with open(fd, 'r', closefd=False) as f:
                    content = f.read()
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)  # Release lock
                os.close(fd)

            # CRITICAL: Check for execution output section
            # This is the separator added by _append_output_to_executing() in agent-task-handler.py
            execution_marker = '## Execution Output'

            if execution_marker not in content:
                # If content looks incomplete (too short), retry before failing
                if len(content) < 1000 and attempt < max_retries - 1:
                    time.sleep(0.1 * (2 ** attempt))
                    continue
                return False, f"No execution output section found (missing '{execution_marker}')"

            # SECURITY: Use rsplit() to find the LAST occurrence of the marker,
            # which is always the system-controlled marker. This prevents injection
            # attacks where task descriptions contain the marker.
            parts = content.rsplit(execution_marker, 1)
            if len(parts) < 2:
                return False, "Execution output section exists but has no content"

            execution_output = parts[1].strip()

            # Count actual execution output lines (non-empty, excluding known metadata patterns)
            # Only filter lines that are EXACTLY metadata format, not all bold text
            metadata_pattern = re.compile(r'^\*\*(Model|Duration|Status|Timestamp|Session|Agent|Task ID):\*\*')

            exec_lines = [l for l in execution_output.split('\n')
                          if l.strip()
                          and not metadata_pattern.match(l.strip())  # only filter known metadata
                          and not l.strip() == '---']

            # Require at least 4 lines of actual output (lowered to reduce fix-resolution churn)
            # 4 lines is enough to distinguish real completions from empty/bogus files
            # while accommodating brief fix-resolution tasks (5-7 lines is common)
            if len(exec_lines) < 4:
                # Might be incomplete write - retry if content looks truncated
                if not execution_output.endswith('```') and attempt < max_retries - 1:
                    time.sleep(0.1 * (2 ** attempt))
                    continue
                return False, f"Execution output too short ({len(exec_lines)} lines, need 4+)"

            # Also check for some substance (not just repeated markers)
            total_output_chars = sum(len(l) for l in exec_lines)
            if total_output_chars < 200:
                return False, f"Execution output too brief ({total_output_chars} chars, need 200+)"

            # RESOLUTION SECTION CHECK (2026-03-09): Match /horde-review PRIORITY_FIX
            # Substantive completions (>=100 chars) must include resolution documentation
            # This catches missing resolutions at verification time, not in later audit
            # FIXED: Case-insensitive check (2026-03-10) to match agent-task-handler.py fix
            if total_output_chars >= 100:
                output_upper = execution_output.upper()
                has_resolution = (
                    "## RESOLUTION" in output_upper
                    or "**STATUS:** RESOLVED" in output_upper
                    or "**STATUS:** COMPLETED" in output_upper
                    or execution_output.count("##") >= 3  # Has multiple sections (likely includes resolution)
                )
                if not has_resolution:
                    return False, f"Missing resolution section (add '## Resolution' or '**Status:** RESOLVED/Completed')"

            return True, "OK"

        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(0.1 * (2 ** attempt))
                continue
            return False, f"Verification error: {e}"

    # Shouldn't reach here, but handle edge case
    return False, "Verification failed: max retries exceeded"


def log(msg):
    """Thread-safe print with timestamp."""
    ts = datetime.now().isoformat()
    with print_lock:
        print(f"[{ts}] {msg}", flush=True)


def _extract_task_id(task_file):
    """Extract task_id from task file frontmatter."""
    try:
        content = task_file.read_text(encoding="utf-8", errors="replace")
        match = re.search(r'^task_id:\s*(\S+)', content, re.MULTILINE)
        return match.group(1) if match else None
    except Exception:
        return None


def _extract_skill_hint(task_file):
    """Extract skill_hint from task file frontmatter."""
    try:
        content = task_file.read_text(encoding="utf-8", errors="replace")
        match = re.search(r'^skill_hint:\s*(\S+)', content, re.MULTILINE)
        return match.group(1) if match else None
    except Exception:
        return None


def _append_ledger(entry):
    """Append an event to the unified task-ledger.jsonl (flock-safe via kurultai_paths)."""
    _kp_append_ledger(entry)


# Queue redistribution monitoring
QUEUE_CHECK_INTERVAL = 300  # Check every 5 minutes (same as cleanup)
_last_queue_check = 0


def _check_queue_redistribution():
    """Check for queue imbalance and trigger redistribution if needed.

    Runs every cleanup cycle. Logs warnings when agents are overloaded
    while others are underutilized. Auto-triggers redistribution when:
    - Any agent exceeds QUEUE_CRITICAL_THRESHOLD (30)
    - Underutilized agents (< 5) are available to receive tasks
    """
    global _last_queue_check

    import time
    current_time = time.time()
    if current_time - _last_queue_check < QUEUE_CHECK_INTERVAL:
        return
    _last_queue_check = current_time

    try:
        # Import task_intake functions for queue checking
        sys.path.insert(0, str(Path(__file__).parent))
        from task_intake import (
            get_all_agent_queue_depths,
            should_redistribute_tasks,
            QUEUE_HIGH_THRESHOLD,
            QUEUE_CRITICAL_THRESHOLD,
            QUEUE_LOW_THRESHOLD,
        )

        depths = get_all_agent_queue_depths()
        redistribution = should_redistribute_tasks()

        # Log summary
        log(f"QUEUE STATUS: " + ", ".join([f"{a}={d}" for a, d in sorted(depths.items())]))

        # Check for critical queues - auto-trigger redistribution
        critical = [(a, d) for a, d in depths.items() if d >= QUEUE_CRITICAL_THRESHOLD]
        if critical:
            for agent, depth in critical:
                log(f"QUEUE CRITICAL: {agent} has {depth} tasks (threshold: {QUEUE_CRITICAL_THRESHOLD})")

            # Auto-redistribute if we have critical queues and underutilized agents
            if redistribution:
                log(f"QUEUE AUTO-REDISTRIBUTION: Triggering redistribution for critical queues")
                _trigger_auto_redistribution()

        # Log redistribution recommendations
        if redistribution:
            for ov_agent, underutilized in redistribution:
                un_list = ", ".join([f"{a}({d})" for a, d in underutilized])
                log(f"QUEUE REDISTRIBUTION: {ov_agent}({depths[ov_agent]}) can offload to: {un_list}")

        # Check for ogedei idle warning (per success criteria)
        ogedei_depth = depths.get('ogedei', 0)
        total_pending = sum(depths.values())
        if ogedei_depth < QUEUE_LOW_THRESHOLD and total_pending > QUEUE_HIGH_THRESHOLD:
            log(f"QUEUE WARNING: ogedei underutilized ({ogedei_depth}) while total queue is {total_pending}")

            # Trigger redistribution to get ogedei working
            if ogedei_depth == 0:
                log(f"QUEUE: Triggering redistribution to activate idle ogedei")
                _trigger_auto_redistribution(max_move=5)

    except Exception as e:
        log(f"Queue check error: {e}")


def _trigger_auto_redistribution(max_move=10):
    """Trigger automatic task redistribution.

    Calls task-redistribute.py to move tasks from overloaded to underutilized agents.
    This runs in the background and doesn't block the task watcher.
    """
    try:
        script_path = Path(__file__).parent / "task-redistribute.py"
        if not script_path.exists():
            log(f"Auto-redistribution: Script not found: {script_path}")
            return

        # Run redistribution in background subprocess
        import subprocess
        log_path = Path(__file__).parent.parent / "logs" / "redistribution.log"

        proc = subprocess.Popen(
            [
                sys.executable,
                str(script_path),
                "--max-move", str(max_move),
                "--log", str(log_path.with_suffix('.json'))
            ],
            stdout=open(log_path, 'a'),
            stderr=subprocess.STDOUT,
            cwd=str(Path(__file__).parent)
        )

        log(f"Auto-redistribution: Started (PID {proc.pid}, max_move={max_move})")

    except Exception as e:
        log(f"Auto-redistribution error: {e}")


# Track last redistribution time to avoid spamming
_last_redistribution_time = 0
REDISTRIBUTION_COOLDOWN = 300  # 5 minutes between redistributions


def _check_and_fix_queue_stall():
    """Detect and fix PENDING_NO_DISPATCH stall condition.

    Stall condition: An agent has >=1 pending tasks but 0 tasks executing.
    This indicates tasks are queueing but not being picked up for execution.

    When detected, triggers redistribution to move tasks to healthier agents.

    Returns: True if stall was detected and fix triggered, False otherwise
    """
    global _last_redistribution_time

    now = time.time()

    # Cooldown: Don't redistribute too frequently
    if now - _last_redistribution_time < REDISTRIBUTION_COOLDOWN:
        return False

    try:
        stalled_agents = []

        for agent_dir in AGENTS_DIR.iterdir():
            if not agent_dir.is_dir() or agent_dir.name == 'main':
                continue

            agent = agent_dir.name
            tasks_dir = agent_dir / "tasks"

            if not tasks_dir.exists():
                continue

            # Count pending tasks (non-terminal state files)
            pending_count = 0
            for f in tasks_dir.iterdir():
                if not f.is_file() or not f.name.endswith('.md'):
                    continue
                # Skip terminal states
                if any(x in f.name for x in ['.done', '.failed', '.completed', '.resolved', '.cancelled', '.executing']):
                    continue
                pending_count += 1

            # Check for executing files
            executing_count = 0
            for f in tasks_dir.iterdir():
                if f.is_file() and f.name.endswith('.executing.md') and '.done' not in f.name:
                    # Verify PID is alive
                    pid_file = tasks_dir / f.name.replace('.executing.md', '.executing.pid')
                    if pid_file.exists():
                        try:
                            pid = int(pid_file.read_text().strip().split('\n')[0])
                            os.kill(pid, 0)  # Check if PID is alive
                            executing_count += 1
                        except (ValueError, ProcessLookupError, PermissionError, OSError):
                            pass  # Dead PID, not counted as executing

            # Stall condition: >=1 pending but 0 executing
            # Lowered from 3 to 1 because queues rarely have 3+ tasks
            # Any pending with zero executing indicates dispatch failure
            if pending_count >= 1 and executing_count == 0:
                stalled_agents.append((agent, pending_count))

        if stalled_agents:
            stall_report = ", ".join([f"{a}({c})" for a, c in stalled_agents])
            log(f"QUEUE STALL DETECTED: {stall_report} — triggering redistribution")

            _trigger_auto_redistribution(max_move=10)
            _last_redistribution_time = now
            return True

        return False

    except Exception as e:
        log(f"Queue stall check error: {e}")
        return False


def load_state():
    """Load previously seen tasks from state file."""
    return locked_json_read(str(STATE_FILE), default={})


def save_state(state):
    """Save current state to file."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with locked_json_update(str(STATE_FILE)) as data:
        data.clear()
        data.update(state)


def update_state_entry(task_key, executed_at, success):
    """Thread-safe update of a single state entry."""
    with locked_json_update(str(STATE_FILE)) as data:
        data[task_key] = {
            'executed': executed_at,
            'success': success,
        }


def list_pending_tasks(agent_dir):
    """List pending tasks for an agent, sorted by priority."""
    tasks_dir = agent_dir / "tasks"
    if not tasks_dir.exists():
        return []

    pending = []
    for f in tasks_dir.glob("*.md"):
        # Skip completed/executing/failed/resolved tasks and gate states
        # FIX 2026-03-10: Check for terminal state markers anywhere in filename
        skip_patterns = ['.executing', '.pending-gate', '.gate-blocked', '.done', '.failed', '.resolved', '.completed', '.cancelled', '.false-positive']
        # Skip any file with terminal state markers (before .md extension)
        name_without_ext = f.name[:-3] if f.name.endswith('.md') else f.name
        if any(pattern in name_without_ext for pattern in skip_patterns):
            continue
        # Skip continuous/recurring tasks (only run when explicitly triggered)
        try:
            head = f.read_text()[:500]
            if head.startswith("---") and "\ntype: continuous" in head.split("---", 2)[1]:
                continue
        except Exception:
            pass
        # Skip paused tasks (paused: true or status: paused in frontmatter)
        try:
            head = f.read_text()[:500]
            if head.startswith("---"):
                frontmatter = head.split("---", 2)[1] if "---" in head else ""
                if "\nstatus: paused" in frontmatter or "\npaused: true" in frontmatter:
                    continue
        except Exception:
            pass
        # Skip tasks in rate-limit cooldown
        cooldown = _extract_cooldown_until(f)
        if cooldown and cooldown > datetime.now():
            continue
        pending.append(f)

    # Sort by priority: high-* > normal-* > low-*
    def priority_key(path):
        name = path.name.lower()
        if name.startswith('high-'):
            return (0, path.stat().st_mtime)
        elif name.startswith('normal-'):
            return (1, path.stat().st_mtime)
        elif name.startswith('low-'):
            return (2, path.stat().st_mtime)
        return (3, path.stat().st_mtime)

    return sorted(pending, key=priority_key)


def _extract_task_label(task_file):
    """Extract task label from the first '# Task: ...' heading."""
    try:
        content = task_file.read_text(encoding="utf-8", errors="replace")[:2000]
        match = re.search(r'^#\s*Task:\s*(.+)', content, re.MULTILINE)
        return match.group(1).strip() if match else task_file.stem[:60]
    except Exception:
        return task_file.stem[:60]


def _extract_task_source(task_file):
    """Extract source: field from task frontmatter."""
    try:
        content = task_file.read_text(encoding="utf-8", errors="replace")[:2000]
        match = re.search(r'^source:\s*(.+)', content, re.MULTILINE)
        return match.group(1).strip().lower() if match else ""
    except Exception:
        return ""


def _extract_notify_metadata(task_file):
    """Extract notify_on_complete, notify_channel, notify_target from frontmatter.

    Returns dict with keys or empty dict if notify_on_complete is not set.
    """
    try:
        content = task_file.read_text(encoding="utf-8", errors="replace")[:2000]
        notify_match = re.search(r'^notify_on_complete:\s*true', content, re.MULTILINE)
        if not notify_match:
            return {}
        channel_match = re.search(r'^notify_channel:\s*(\S+)', content, re.MULTILINE)
        target_match = re.search(r'^notify_target:\s*(\S+)', content, re.MULTILINE)
        created_match = re.search(r'^created:\s*(.+)', content, re.MULTILINE)
        return {
            "notify_on_complete": True,
            "notify_channel": channel_match.group(1) if channel_match else "signal",
            "notify_target": target_match.group(1) if target_match else "+19194133445",
            "created": created_match.group(1).strip() if created_match else None,
        }
    except Exception:
        return {}


# Notification log path
NOTIFICATION_LOG = AGENTS_DIR / "main" / "logs" / "notifications.log"


def _has_been_notified(task_id):
    """Check if a task_id has already been notified (dedup guard)."""
    if not task_id or not NOTIFICATION_LOG.exists():
        return False
    try:
        content = NOTIFICATION_LOG.read_text(encoding="utf-8", errors="replace")
        return f"task_id={task_id}" in content
    except Exception:
        return False


def _log_notification(task_id, agent, task_label, result, target):
    """Append to notifications.log for dedup and audit."""
    try:
        NOTIFICATION_LOG.parent.mkdir(parents=True, exist_ok=True)
        entry = (
            f"[{datetime.now().isoformat()}] task_id={task_id} agent={agent} "
            f"result={result} target={target} label={task_label[:80]}\n"
        )
        with open(NOTIFICATION_LOG, "a") as f:
            f.write(entry)
    except Exception as e:
        log(f"  Notification log error: {e}")


def _send_task_notify(agent, task_label, task_id, success, elapsed_s, notify_meta):
    """Send per-task completion notification via Signal when notify_on_complete is set."""
    if not notify_meta.get("notify_on_complete"):
        return
    if _has_been_notified(task_id):
        log(f"  NOTIFY SKIP: {task_id} already notified")
        return

    result = "completed" if success else "failed"
    duration = f"{int(elapsed_s)}s"
    if elapsed_s >= 60:
        duration = f"{int(elapsed_s // 60)}m {int(elapsed_s % 60)}s"

    status_icon = "✅" if success else "❌"
    msg = (
        f"{status_icon} Task Complete: {task_label}\n"
        f"Agent: {agent}\n"
        f"Task ID: {task_id or 'unknown'}\n"
        f"Duration: {duration}\n"
        f"Result: {result}"
    )

    # SECURITY: Sanitize notification content before sending
    msg = sanitize_notification(msg)

    target = notify_meta.get("notify_target", "+19194133445")
    channel = notify_meta.get("notify_channel", "signal")

    def _send():
        sent = False
        if channel == "signal" and SEND_SIGNAL_SCRIPT.exists():
            try:
                r = subprocess.run(
                    ["bash", str(SEND_SIGNAL_SCRIPT), msg, "--dm", target],
                    capture_output=True, timeout=15,
                )
                sent = r.returncode == 0
                if sent:
                    log(f"  NOTIFY OK: {task_id} -> {target}")
                else:
                    log(f"  NOTIFY FAIL: {task_id} signal error: {r.stderr[:200]}")
            except Exception as e:
                log(f"  NOTIFY ERROR: {task_id}: {e}")

        _log_notification(task_id, agent, task_label, result, target)

    t = Thread(target=_send, daemon=True)
    t.start()


# Sources that are heartbeat/automated — silent unless errors
_HEARTBEAT_SOURCES = {"kublai-actions", "agent-self-wake", "agent-self-wake (rule t7)"}
# Sources that always notify on completion (kurultai results)
_KURULTAI_SOURCES = {"hourly-reflection", "kublai-reflection"}


# =============================================================================
# Notification Content Sanitization (Security)
# =============================================================================

# Patterns for sensitive data redaction in notifications
SENSITIVE_PATTERNS = [
    # API keys and tokens
    (r"api[_-]?key['\"]?\s*[:=]\s*['\"]?[\w\-]{10,}", "[API_KEY_REDACTED]"),
    (r"bearer\s+['\"]?[\w\-\.]{10,}", "[BEARER_TOKEN_REDACTED]"),
    (r"token['\"]?\s*[:=]\s*['\"]?[\w\-\.]{10,}", "[TOKEN_REDACTED]"),
    (r"secret['\"]?\s*[:=]\s*['\"]?[\w\-]{10,}", "[SECRET_REDACTED]"),
    (r"password['\"]?\s*[:=]\s*['\"]?[\w\-]{4,}", "[PASSWORD_REDACTED]"),
    # File paths (might contain usernames)
    (r"/Users/[\w]+/", "/Users/[USER]/"),
    (r"/home/[\w]+/", "/home/[USER]/"),
    # Phone numbers
    (r"\+?\d{1,3}[\s\-]?\(?\d{2,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{4}", "[PHONE_REDACTED]"),
    # Email addresses
    (r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "[EMAIL_REDACTED]"),
    # Credit card-like numbers
    (r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b", "[CARD_REDACTED]"),
]


def sanitize_notification(text: str) -> str:
    """Remove sensitive data from notification content.

    Args:
        text: Notification text to sanitize

    Returns:
        Sanitized text with sensitive patterns redacted
    """
    sanitized = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
    return sanitized


def _notify_completion(agent, task_label, success, elapsed_s, source="", result=""):
    """Send task completion notification via Signal and webapp.

    Notification rules:
    - Errors/failures: always notify
    - Heartbeat tasks (kublai-actions, self-wake): silent unless error
    - Kurultai reflections: always notify
    - User-initiated tasks (gateway-router, direct): always notify
    """
    source_lower = source.lower()

    if success:
        return  # Success notifications handled by /task-complete skill in agent-task-handler

    else:
        error_snippet = (" | " + result[:200]) if result else ""
        msg = f"[ALERT] {agent}: {task_label} — FAILED ({elapsed_s}s){error_snippet}"

    def _send():
        # 1. Signal notification
        try:
            if SEND_SIGNAL_SCRIPT.exists():
                subprocess.run(
                    ["bash", str(SEND_SIGNAL_SCRIPT), msg],
                    capture_output=True, timeout=15,
                )
        except Exception as e:
            log(f"  Signal notify error: {e}")

        # 2. Webapp notification via openclaw gateway
        try:
            subprocess.run(
                ["openclaw", "agent", "--agent", "kublai",
                 "-m", msg, "--deliver"],
                capture_output=True, timeout=30,
            )
        except Exception as e:
            log(f"  Webapp notify error: {e}")

    t = Thread(target=_send, daemon=True)
    t.start()


def _schedule_verification(task_file, agent, task_id):
    """Schedule post-completion verification + report generation in a background thread.

    Finds the .completed.done.md file (agent-task-handler renames it)
    and runs task-verifier.py against it. Then generates completion report.
    Non-blocking, fire-and-forget.
    """
    def _verify():
        try:
            # Find the completed file (task_file was the original .md path)
            tasks_dir = task_file.parent
            stem = task_file.stem.replace('.executing', '')
            # Search for .completed.done.md matching this task
            candidates = list(tasks_dir.glob(f"{stem}*.completed.done.md"))
            if not candidates:
                # Broader search by task_id prefix
                if task_id:
                    short_id = task_id[:8]
                    candidates = [f for f in tasks_dir.glob("*.completed.done.md")
                                  if short_id in f.name or
                                  abs(f.stat().st_mtime - time.time()) < 60]
            if not candidates:
                log(f"  VERIFY: no .completed.done.md found for {agent}/{task_file.name}")
                return

            completed_file = str(candidates[0])
            verifier = str(Path(__file__).parent / "task-verifier.py")
            result = subprocess.run(
                ["python3", verifier,
                 "--task-file", completed_file,
                 "--agent", agent,
                 "--json"],
                capture_output=True, text=True, timeout=120,
            )

            if result.returncode == 0:
                log(f"  VERIFY OK: {agent}/{Path(completed_file).name}")
                # Generate completion report
                _generate_completion_report(completed_file, agent, task_id)
            else:
                # Parse JSON for failure details
                detail = ""
                try:
                    data = json.loads(result.stdout)
                    failed = [d for d in data.get("details", []) if not d.get("passed")]
                    if failed:
                        detail = f" ({failed[0].get('check', '')}: {failed[0].get('detail', '')[:60]})"
                except (json.JSONDecodeError, KeyError):
                    pass
                log(f"  VERIFY FAIL: {agent}/{Path(completed_file).name}{detail}")
                # Generate failure report
                _generate_completion_report(completed_file, agent, task_id, status='failed')

        except subprocess.TimeoutExpired:
            log(f"  VERIFY TIMEOUT: {agent}/{task_file.name}")
        except Exception as e:
            log(f"  VERIFY ERROR: {agent}/{task_file.name}: {e}")

    t = Thread(target=_verify, daemon=True)
    t.start()


def _generate_completion_report(completed_file: str, agent: str, task_id: str, status: str = 'completed'):
    """Generate task completion report using kublai-task-report skill."""
    try:
        hook = str(Path(__file__).parent / "task-report-hook.py")
        result = subprocess.run(
            ["python3", hook,
             "--task-file", completed_file,
             "--agent", agent,
             "--task-id", task_id or "unknown",
             "--status", status],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            log(f"  REPORT: Generated for {agent}/{Path(completed_file).name}")
        else:
            log(f"  REPORT: Failed for {agent}/{Path(completed_file).name}: {result.stderr[:200]}")
    except subprocess.TimeoutExpired:
        log(f"  REPORT: Timeout for {agent}/{Path(completed_file).name}")
    except Exception as e:
        log(f"  REPORT: Error for {agent}/{Path(completed_file).name}: {e}")


def _schedule_task_report(task_file, agent, task_id, success, elapsed_s, output):
    """Schedule task completion report generation in a background thread.

    Non-blocking, fire-and-forget. Called for both success and failure cases.
    """
    def _report():
        try:
            hook = str(Path(__file__).parent / "task-report-hook.py")
            status = "completed" if success else "failed"
            result = subprocess.run(
                ["python3", hook,
                 "--task-file", str(task_file),
                 "--agent", agent,
                 "--status", status,
                 "--duration", str(elapsed_s),
                 "--output", output[:1000] if output else ""],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                log(f"  REPORT: Generated for {agent}/{task_file.name}")
            else:
                log(f"  REPORT: Failed for {agent}/{task_file.name}: {result.stderr[:200]}")
        except subprocess.TimeoutExpired:
            log(f"  REPORT: Timeout for {agent}/{task_file.name}")
        except Exception as e:
            log(f"  REPORT: Error for {agent}/{task_file.name}: {e}")

    t = Thread(target=_report, daemon=True)
    t.start()


SLOW_SKILLS = {
    '/horde-brainstorming': 7200,
    '/golden-horde': 7200,
    '/horde-implement': 7200,
    '/horde-review': 7200,
    '/horde-debug': 7200,
    '/horde-learn': 7200,
    '/horde-swarm': 7200,
    '/horde-test': 7200,
}


def _timeout_for_task(task_file):
    """Return timeout based on priority AND skill_hint (matches agent-task-handler logic)."""
    name = task_file.name.lower()
    priority_timeout = TIMEOUT_DEFAULT
    for prefix in ('high-', 'normal-', 'low-'):
        if name.startswith(prefix):
            priority_timeout = TIMEOUT_BY_PRIORITY.get(prefix.rstrip('-'), TIMEOUT_DEFAULT)
            break

    skill_hint = _extract_skill_hint(task_file)
    skill_timeout = SLOW_SKILLS.get(skill_hint, 0)
    return max(priority_timeout, skill_timeout)


def _extract_retry_count(task_file):
    """Extract retry_count from task file frontmatter."""
    try:
        content = task_file.read_text(encoding="utf-8", errors="replace")[:2000]
        match = re.search(r'^retry_count:\s*(\d+)', content, re.MULTILINE)
        return int(match.group(1)) if match else 0
    except Exception:
        return 0


def _is_rate_limit_failure(error_msg):
    """Detect rate limit errors in failure output."""
    if not error_msg:
        return False
    lower = error_msg.lower()
    return any(p in lower for p in [
        "rate limit", "rate_limit", "rate-limit",
        "429", "too many requests", "quota exceeded",
        "overloaded", "capacity", "throttl",
    ])


def _extract_cooldown_until(task_file):
    """Extract cooldown_until timestamp from task file frontmatter."""
    try:
        content = task_file.read_text(encoding="utf-8", errors="replace")[:2000]
        match = re.search(r'^cooldown_until:\s*(\S+)', content, re.MULTILINE)
        if match:
            return datetime.fromisoformat(match.group(1))
    except Exception:
        pass
    return None


def _append_failure_context(task_file, agent, error_msg, elapsed_s):
    """Append failure context to task file and increment retry count.

    Instead of marking as .failed.done, we append the failure reason and
    keep the file as .md so it can be re-executed. After MAX_RETRY_COUNT
    failures, the file is marked as .failed.done permanently.
    
    Returns True if permanently failed, False if will retry.
    """
    # Determine the base name and find the actual file
    base_name = task_file.name.replace('.executing.md', '.md').replace('.failed.done.md', '.md')
    task_dir = task_file.parent
    
    # Find the actual file (could be .md, .executing.md, or .failed.done.md)
    source_file = None
    for candidate_name in [base_name, base_name.replace('.md', '.executing.md'), base_name.replace('.md', '.failed.done.md')]:
        candidate = task_dir / candidate_name
        if candidate.exists():
            source_file = candidate
            break
    
    if not source_file:
        log(f"  WARNING: Cannot find task file for {agent}/{base_name}")
        return True  # Treat as permanent fail if file is missing
    
    # Extract retry count from the source file
    retry_count = _extract_retry_count(source_file)
    new_retry_count = retry_count + 1
    is_permanent = new_retry_count >= MAX_RETRY_COUNT
    
    # Detect rate limit failures and apply cooldown
    is_rate_limited = _is_rate_limit_failure(error_msg)

    if is_permanent:
        # Permanently failed - mark as .failed.done
        target_name = base_name.replace('.md', '.failed.done.md')
        failure_section = f"""
## Failure {new_retry_count} (PERMANENT - max retries reached)
- **Time:** {datetime.now().isoformat()}
- **Duration:** {elapsed_s}s
- **Error:** {error_msg[:1000]}
"""
    else:
        # Re-queue for retry - keep as .md
        target_name = base_name
        cooldown_note = ""
        if is_rate_limited:
            cooldown_note = f"\n- **Cooldown:** {RATE_LIMIT_COOLDOWN}s (rate limit backoff)"
        failure_section = f"""
## Failure {new_retry_count} (will retry)
- **Time:** {datetime.now().isoformat()}
- **Duration:** {elapsed_s}s
- **Error:** {error_msg[:1000]}
- **Retry count:** {new_retry_count}/{MAX_RETRY_COUNT}{cooldown_note}
"""
    
    target_path = task_dir / target_name
    
    try:
        # Read existing content from source file
        content = source_file.read_text(encoding="utf-8", errors="replace")
        
        # Update retry_count in frontmatter
        if 'retry_count:' in content:
            content = re.sub(r'^retry_count:\s*\d+', f'retry_count: {new_retry_count}', content, flags=re.MULTILINE)
        else:
            # Insert retry_count after priority line
            content = re.sub(r'^(priority:.*)$', f'\\1\nretry_count: {new_retry_count}', content, count=1, flags=re.MULTILINE)

        # Add/update cooldown_until for rate-limited retries
        if is_rate_limited and not is_permanent:
            cooldown_ts = (datetime.now() + timedelta(seconds=RATE_LIMIT_COOLDOWN)).isoformat()
            if 'cooldown_until:' in content:
                content = re.sub(r'^cooldown_until:\s*\S+', f'cooldown_until: {cooldown_ts}', content, flags=re.MULTILINE)
            else:
                content = re.sub(r'^(retry_count:.*)$', f'\\1\ncooldown_until: {cooldown_ts}', content, count=1, flags=re.MULTILINE)
            log(f"  RATE LIMIT COOLDOWN: {agent}/{base_name} will retry after {RATE_LIMIT_COOLDOWN}s")
        elif 'cooldown_until:' in content:
            # Clear cooldown for non-rate-limit failures
            content = re.sub(r'^cooldown_until:.*\n?', '', content, flags=re.MULTILINE)

        # Append failure context at end
        content = content.rstrip() + '\n' + failure_section
        
        # Write to target path
        target_path.write_text(content, encoding="utf-8")
        
        # Clean up old files (source file and any .executing/.pid sentinels)
        if source_file != target_path:
            source_file.unlink(missing_ok=True)
        executing_file = task_dir / base_name.replace('.md', '.executing.md')
        if executing_file.exists() and executing_file != target_path:
            executing_file.unlink(missing_ok=True)
        pid_file = task_dir / base_name.replace('.md', '.pid')
        if pid_file.exists():
            pid_file.unlink(missing_ok=True)
        # Also clean up any .failed.done.md that might exist from handler
        failed_done_file = task_dir / base_name.replace('.md', '.failed.done.md')
        if failed_done_file.exists() and failed_done_file != target_path:
            failed_done_file.unlink(missing_ok=True)
        
        if is_permanent:
            log(f"  PERMANENT FAIL: {agent}/{base_name} → {target_name} (retry {new_retry_count}/{MAX_RETRY_COUNT})")
        else:
            log(f"  REQUEUE: {agent}/{base_name} will retry (attempt {new_retry_count}/{MAX_RETRY_COUNT})")
        
        return is_permanent
            
    except Exception as e:
        log(f"  Failed to append failure context: {e}")
        return True  # Treat as permanent fail on error


def _check_and_reset_bloated_session(agent: str, task_id: str = "") -> bool:
    """Check agent session file size and reset if bloated.

    Returns True if session was reset, False otherwise.

    Threshold: SESSION_BLOAT_THRESHOLD (15KB default)
    Effect: Prevents 66% efficiency loss from 21KB stale sessions

    Called before task execution to ensure clean context.
    """
    session_path = _agent_sessions_path(agent)

    if not session_path.exists():
        return False

    try:
        size = session_path.stat().st_size
        if size > _SESSION_BLOAT_THRESHOLD:
            # Backup bloated session for debugging
            backup_path = session_path.with_suffix(f".bloated.{int(time.time())}.json")
            import shutil
            shutil.copy(session_path, backup_path)

            # Reset to empty session
            session_path.write_text("{}")

            log(f"SESSION_RESET: {agent} ({size:,}B → 2B, backup={backup_path.name})")

            # Log to ledger for tracking
            _append_ledger({
                "event": "SESSION_RESET",
                "ts": datetime.now().isoformat(),
                "agent": agent,
                "task_id": task_id,
                "size_before": size,
                "threshold": _SESSION_BLOAT_THRESHOLD,
            })

            return True
    except Exception as e:
        log(f"SESSION_CHECK_ERROR: {agent}: {e}")

    return False


def execute_task(task_file, agent, task_key, timeout):
    """Execute a single task file via agent-task-handler.py.

    Runs in a thread pool worker. Updates state on completion.

    ATOMIC CLAIM: Uses Neo4j CAS to prevent double-execution when multiple
    watchers are running. If claim fails, returns early without execution.
    """
    task_id = _extract_task_id(task_file)
    start_time = time.time()

    # ATOMIC CLAIM: Prevent double-execution across multiple watchers
    # claim_task_atomic now logs the specific failure reason
    if task_id:
        claimed, session_key = claim_task_atomic(task_id, agent)
        if not claimed:
            return  # Reason already logged by claim_task_atomic
    else:
        session_key = ""

    # Extract all file-dependent metadata NOW, before agent-task-handler
    # renames the file (.md -> .executing.md -> .completed.done.md).
    # Reading after execution silently fails because the original path is gone.
    notify_meta = _extract_notify_metadata(task_file)
    task_label = _extract_task_label(task_file)
    task_source = _extract_task_source(task_file)

    # Auto-reset bloated sessions BEFORE execution to prevent efficiency loss
    # 21KB stale session → 66% efficiency loss → 300+ min task times
    _check_and_reset_bloated_session(agent, task_id or "")

    # Emit EXECUTING event
    skill_hint = _extract_skill_hint(task_file)
    if task_id:
        _append_ledger({
            "task_id": task_id,
            "event": "EXECUTING",
            "ts": datetime.now().isoformat(),
            "agent": agent,
            "task_file": str(task_file),
            "skill_hint": skill_hint,
            "executor": "claude-code",
            "session_key": session_key,
        })
        _neo4j_update_status(task_id, "EXECUTING", agent=agent)

    cmd = [
        "python3",
        str(Path(__file__).parent / "agent-task-handler.py"),
        "--agent", agent,
        "--task-file", str(task_file),
    ]

    proc = None
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,  # New session so we can kill entire tree
            cwd=str(task_file.parent.parent.parent),
        )
        stdout, stderr = proc.communicate(timeout=timeout)
        success = proc.returncode == 0
        if success:
            output = stdout[:1000]
        else:
            # Combine stderr and stdout, filtering out known non-error messages
            combined = stderr or ""
            if stdout:
                # Filter out snapshot info messages which are not errors
                filtered_stdout = "\n".join(
                    line for line in stdout.splitlines()
                    if not any(x in line for x in [
                        "Building file manifest",
                        "Creating archive at",
                        "Snapshot created:",
                        "📸 Snapshot created:"
                    ])
                )
                if filtered_stdout.strip():
                    combined = (combined + "\n" + filtered_stdout).strip() if combined else filtered_stdout
            output = combined[:1000] if combined else f"Task failed with exit code {proc.returncode} (no output captured)"
            if not output.strip():
                output = f"Task failed with exit code {proc.returncode} (no output captured)"

    except subprocess.TimeoutExpired:
        success = False
        output = f"Task timed out after {timeout}s"
        # Kill entire process group (handler + claude + all children)
        if proc:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                time.sleep(2)
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
    except Exception as e:
        success = False
        output = f"Execution error: {e}"

    elapsed_s = round(time.time() - start_time, 1)
    status = "✓" if success else "✗"
    log(f"  {status} {task_key}: {'Completed' if success else 'Failed'} ({elapsed_s}s)")

    # CRITICAL: Double-check for fake completions
    # If handler reported success, verify the .done.md file has actual execution output
    if success:
        # Find the .done.md file that handler created
        tasks_dir = task_file.parent
        stem = task_file.stem
        done_files = list(tasks_dir.glob(f"{stem}*.done.md"))
        if done_files:
            # Check the most recent done file
            done_file = max(done_files, key=lambda f: f.stat().st_mtime)
            is_valid, reason = _verify_task_completion(str(done_file))
            if not is_valid:
                log(f"  ⚠ FAKE COMPLETION DETECTED: {reason}")
                log(f"  ⚠ Re-marking as failed (no_output)")
                success = False
                output = f"FAKE COMPLETION: {reason}"
                # Emit FAKE_COMPLETION event to ledger for tracking
                if task_id:
                    _append_ledger({
                        "task_id": task_id,
                        "event": "FAKE_COMPLETION_BLOCKED",
                        "ts": datetime.now().isoformat(),
                        "agent": agent,
                        "reason": reason,
                        "original_output_lines": len(output.splitlines()) if output else 0,
                    })

    # Emit COMPLETED/FAILED event
    if task_id:
        final_status = "COMPLETED" if success else "FAILED"
        _append_ledger({
            "task_id": task_id,
            "event": final_status,
            "ts": datetime.now().isoformat(),
            "agent": agent,
            "execution_time_s": elapsed_s,
            "output_lines": len(output.splitlines()) if output else 0,
            "error": output[:500] if not success else None,
        })
        _neo4j_update_status(task_id, final_status, agent=agent,
                             error_msg=output[:500] if not success else None)

    # After failure, append failure context and re-queue (or mark permanent after MAX_RETRY_COUNT)
    is_permanent_fail = False
    if not success:
        # RACE CONDITION FIX: Check if agent-task-handler already processed the failure
        # (file renamed to .done.md) before calling _append_failure_context
        task_dir = task_file.parent
        stem = task_file.stem.replace('.executing', '').replace('.failed', '').replace('.done', '')
        done_variants = list(task_dir.glob(f"{stem}*.done.md"))
        if done_variants:
            log(f"  Failure already processed by handler: {done_variants[0].name}")
            is_permanent_fail = True  # Handler already decided terminal state
        else:
            is_permanent_fail = _append_failure_context(task_file, agent, output, elapsed_s)

    # Notify owner (global error notifications)
    # task_label and task_source were extracted at top of execute_task()
    if NOTIFY_ON_COMPLETE:
        _notify_completion(agent, task_label, success, elapsed_s, source=task_source, result=output)

    # Per-task notify_on_complete (user-requested Signal notification)
    # notify_meta was extracted at top of execute_task(), before file rename
    if notify_meta:
        _send_task_notify(agent, task_label, task_id, success, elapsed_s, notify_meta)

    # Post-completion verification (background thread, non-blocking)
    if VERIFY_ON_COMPLETE and success:
        _schedule_verification(task_file, agent, task_id)

    # Generate completion report (background thread, non-blocking)
    _schedule_task_report(task_file, agent, task_id, success, elapsed_s, output)

    # Update state only on success or permanent failure (not on retry)
    if success or is_permanent_fail:
        update_state_entry(task_key, datetime.now().isoformat(), success)

    # Clear the active execution slot for this agent
    with active_lock:
        active_executions.pop(agent, None)

    return success, output


def is_new_task(task_file, agent, state):
    """Check if a task file is genuinely new (not already executed).

    Uses Neo4j as source of truth when available, falls back to state file.
    """
    # First check Neo4j status (single source of truth)
    task_id = _extract_task_id(task_file)
    if task_id:
        neo4j_status = check_neo4j_task_status(task_id)
        if neo4j_status:
            status = neo4j_status.get("status", "")
            status_upper = status.upper()
            if status_upper in ("COMPLETED", "FAILED", "TIMEOUT", "CANCELLED"):
                # Check retry count - allow re-execution if under limit
                retry_count = neo4j_status.get("retry_count") or 0
                if retry_count >= MAX_RETRY_COUNT:
                    return False  # Already at max retries, don't re-execute
                # Check if claimed by another process
                claimed_by = neo4j_status.get("claimed_by")
                if claimed_by and claimed_by != agent:
                    return False  # Claimed by another watcher
            elif status_upper == "EXECUTING":
                # Task is being executed - check if stale
                session_key = neo4j_status.get("session_key")
                if session_key:
                    return False  # Active execution
            # PENDING status means it's new (case-insensitive comparison)
            return status.upper() == "PENDING"

    # Fallback to state file check
    key = f"{agent}/{task_file.name}"
    if key not in state:
        return True
    entry = state[key]
    # If state records a failure but the file is still .md (not .failed.done.md),
    # the cleanup rename failed. Treat as new so it gets re-processed.
    if not entry.get('success', True):
        return True
    # Check if file was modified after execution (re-queued)
    try:
        exec_time = datetime.fromisoformat(entry['executed'])
        file_mtime = datetime.fromtimestamp(task_file.stat().st_mtime)
        return file_mtime > exec_time
    except (KeyError, ValueError, OSError):
        return False


def sanitize_text(text):
    """Remove control characters and limit length for spawn tasks."""
    if not isinstance(text, str):
        return ""
    text = re.sub(r'[\x00-\x1f\x7f]', '', text)
    return text[:2000]


def find_alternative_agent(original_agent: str, reason: str = "") -> str | None:
    """Find a healthy alternative agent when circuit breaker is open.

    Returns:
        Agent name or None if no healthy agents available
    """
    if _circuit_breaker is None:
        return None

    # Import DISPATCH_AGENTS for the list of valid agents
    try:
        from kurultai_paths import DISPATCH_AGENTS
    except ImportError:
        DISPATCH_AGENTS = ["temujin", "mongke", "chagatai", "jochi", "ogedei", "tolui"]

    for agent in DISPATCH_AGENTS:
        if agent == original_agent:
            continue
        check = _circuit_breaker.check_agent(agent)
        if check["available"]:
            return agent

    return None


def route_spawn_to_queue(agent, task_text, priority, label):
    """Route a spawn request by creating a task file in the agent's queue.

    The task file will be picked up by the next watch_cycle iteration
    (within seconds), achieving near-instant spawning.

    Checks circuit breaker before routing and diverts to healthy agent if needed.
    """
    # Check circuit breaker before routing
    if _circuit_breaker:
        circuit_state = _circuit_breaker.check_agent(agent)
        if not circuit_state["available"]:
            log(f"  CIRCUIT BREAKER: {agent} is {circuit_state['reason']}: {circuit_state.get('detail', '')}")
            alternative = find_alternative_agent(agent)
            if alternative:
                log(f"  CIRCUIT BREAKER: Diverting task from {agent} to {alternative}")
                agent = alternative
            else:
                log(f"  CIRCUIT BREAKER: No healthy agents available, using original {agent}", "WARN")

    tasks_dir = AGENTS_DIR / agent / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    safe_label = re.sub(r'[^\w\-]', '_', label)[:60]
    filename = f"{priority}-spawn-{safe_label}-{int(time.time())}.md"
    task_path = tasks_dir / filename

    # Note circuit breaker diversion in task content
    circuit_note = ""
    if _circuit_breaker:
        check = _circuit_breaker.check_agent(agent)
        if check.get("reason") in ["probation", "normal"]:
            pass  # No diversion
        else:
            circuit_note = f"\n<!-- Circuit breaker check passed for {agent} -->"

    content = (
        f"# Task: {label}\n\n"
        f"Source: spawn-queue (routed by task-watcher)\n"
        f"Priority: {priority}\n\n"
        f"---\n\n"
        f"{task_text}\n"
        f"{circuit_note}"
    )
    task_path.write_text(content)
    log(f"  SPAWN->QUEUE: {agent}/{filename}")
    return str(task_path)


def launch_spawn_direct(agent, task_text, label):
    """Launch Claude Code directly for agent_execution spawn requests.

    Non-blocking: uses Popen so the daemon continues polling.
    The spawned process runs independently.
    """
    workspace = str(AGENTS_DIR / agent)
    prompt = (
        f"You are {agent.capitalize()}, executing an assigned task.\n\n"
        f"{task_text}\n\n"
        "Execute completely. Write code, make changes, verify."
    )

    env = os.environ.copy()
    env.pop('CLAUDECODE', None)

    # Sanitize ALL inherited ANTHROPIC_* env vars to prevent credential leakage
    for key in list(env.keys()):
        if key.startswith('ANTHROPIC_'):
            del env[key]

    env['PATH'] = (
        "/Users/kublai/.local/bin:/opt/homebrew/bin:"
        "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    )

    log_file = AGENTS_DIR / "main" / "logs" / f"spawn-{agent}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    with open(log_file, "a") as logf:
        logf.write(f"\n{'='*60}\n")
        logf.write(f"[{datetime.now().isoformat()}] Spawn: {label}\n")
        logf.write(f"{'='*60}\n")
        logf.flush()

        subprocess.Popen(
            [CLAUDE_AGENT, "--workdir", workspace, "--", prompt],
            stdout=logf,
            stderr=subprocess.STDOUT,
            env=env,
        )

    log(f"  SPAWN->DIRECT: Claude Code launched for {label} ({agent})")


def process_spawn_queue():
    """Process spawn-pending.json: route ready spawns to agent queues or launch directly.

    Called every watch cycle (~15s). Replaces the 2-minute cron-based spawn-consumer
    for near-instant subagent spawning.

    Spawn sources:
    - agent_execution: Launch Claude Code directly (Popen, non-blocking)
    - agent_delegation / other: Route to agent task queue (file created in tasks/)
    """
    data = locked_json_read(str(SPAWN_QUEUE), default={'spawns': []})
    spawns = data.get('spawns', [])
    if not spawns:
        return 0

    processed = 0
    cutoff = datetime.now() - timedelta(minutes=SPAWN_TIMEOUT_MINUTES)

    # Phase 1: Check status of running spawns
    for s in spawns:
        if s.get('status') != 'running':
            continue
        last_spawned = s.get('last_spawned')
        if last_spawned and not s.get('continuous'):
            try:
                spawn_time = datetime.fromisoformat(last_spawned)
                if spawn_time < cutoff:
                    s['status'] = 'completed'
                    s['completed_at'] = datetime.now().isoformat()
                    log(f"  SPAWN TIMEOUT: {s.get('label', 'unknown')} (>{SPAWN_TIMEOUT_MINUTES}m)")
            except (ValueError, TypeError):
                pass

    # Phase 2: Process ready spawns
    ready = [s for s in spawns if s.get('status') == 'ready']
    if not ready:
        # Still save if we marked any running->completed
        if any(s.get('status') == 'completed' for s in spawns):
            _save_spawn_queue(spawns)
        return 0

    log(f"SPAWN QUEUE: {len(ready)} ready spawn(s)")

    for s in ready:
        task_text = sanitize_text(s.get('task', ''))
        label = s.get('label', 'unknown')
        priority = s.get('priority', 'normal')
        source = s.get('source', 'unknown')
        agent = s.get('agent', 'subagent')

        if agent not in VALID_AGENTS:
            log(f"  SPAWN REJECT: invalid agent '{agent}' for {label}")
            s['status'] = 'failed'
            s['error'] = f"Invalid agent: {agent}"
            continue

        try:
            if source == "agent_execution":
                launch_spawn_direct(agent, task_text, label)
                s['status'] = 'running'
                s['last_spawned'] = datetime.now().isoformat()
            else:
                # Route to agent task queue — task-watcher picks it up next cycle
                task_path = route_spawn_to_queue(agent, task_text, priority, label)
                s['status'] = 'routed'
                s['routed_to'] = agent
                s['routed_at'] = datetime.now().isoformat()
                s['task_file'] = task_path
            processed += 1
        except Exception as e:
            log(f"  SPAWN ERROR: {label}: {e}")
            s['status'] = 'failed'
            s['error'] = str(e)

    # Phase 3: Handle retries for failed spawns
    for s in list(spawns):
        if s.get('status') != 'failed':
            continue
        retry_count = s.get('retry_count', 0)
        max_retries = s.get('max_retries', 3)
        if retry_count < max_retries:
            s['retry_count'] = retry_count + 1
            s['status'] = 'ready'
            s['last_retry'] = datetime.now().isoformat()
            log(f"  SPAWN RETRY: {s.get('label')} ({retry_count + 1}/{max_retries})")

    # Phase 4: Cleanup — keep only active entries
    spawns = [s for s in spawns if s.get('status') in ('ready', 'running')]
    _save_spawn_queue(spawns)

    if processed > 0:
        log(f"SPAWN QUEUE: processed {processed} spawn(s)")
    return processed


def _save_spawn_queue(spawns):
    """Save updated spawn queue with locking."""
    with locked_json_update(str(SPAWN_QUEUE), default={'spawns': [], 'updated': 0}) as data:
        data['spawns'] = spawns
        data['updated'] = time.time()


def watch_cycle(executor):
    """Single watch cycle - check for new tasks, dispatch concurrently.

    Each agent gets at most one concurrent execution slot. If an agent
    already has a task running, new tasks for that agent wait until
    the current one finishes.
    """
    now = time.time()  # For consistent timestamping in this cycle

    # PRIORITY FIX: Check for queue stall condition BEFORE normal dispatch
    # This detects PENDING_NO_DISPATCH anomaly (agent has pending tasks but
    # zero execution) and triggers redistribution to healthier agents.
    try:
        stall_fixed = _check_and_fix_queue_stall()
        if stall_fixed:
            log("Queue stall fix triggered — redistribution in progress")
    except Exception as e:
        log(f"Queue stall check failed: {e}")

    # Process spawn queue first — routes spawns to agent task queues
    try:
        process_spawn_queue()
    except Exception as e:
        log(f"Spawn queue error: {e}")

    state = load_state()
    dispatched = 0

    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir() or agent_dir.name == 'main':
            continue

        agent = agent_dir.name

        # Skip if this agent already has a task running (in-memory tracking)
        with active_lock:
            if agent in active_executions:
                fut = active_executions[agent]
                if not fut.done():
                    continue
                # Future completed but wasn't cleaned up yet
                active_executions.pop(agent, None)

        # Check for .executing files and verify PID liveness before skipping
        # This prevents dead tasks from blocking the execution slot
        tasks_dir = agent_dir / "tasks"
        if tasks_dir.exists():
            executing_files = [
                f for f in tasks_dir.iterdir()
                if f.is_file() and f.name.endswith('.executing.md') and '.done' not in f.name
            ]
            if executing_files:
                # Verify at least one executing task has a live PID
                has_live_executing = False
                for exec_file in executing_files:
                    pid_file = exec_file.parent / exec_file.name.replace('.executing.md', '.executing.pid')
                    if pid_file.exists():
                        try:
                            pid = int(pid_file.read_text().strip().split('\n')[0])
                            os.kill(pid, 0)  # Check if PID is alive
                            has_live_executing = True
                            break
                        except (ValueError, ProcessLookupError, PermissionError, OSError):
                            # PID is dead - this executing file is stale, will be recovered below
                            pass
                if has_live_executing:
                    continue

                # If we get here, all .executing files have dead PIDs - recover them now
                # instead of waiting for recover_stale_executions() to run
                for exec_file in executing_files:
                    pid_file = exec_file.parent / exec_file.name.replace('.executing.md', '.executing.pid')
                    try:
                        age = int(now - exec_file.stat().st_mtime)
                    except OSError:
                        age = 999999

                    if age < 60:  # Grace period for very recent tasks
                        continue

                    # Recover dead-PID task immediately
                    retry_count = len(re.findall(r'\.retry-\d+', exec_file.name))
                    if retry_count >= MAX_RETRY_COUNT:
                        failed_path = exec_file.parent / exec_file.name.replace('.executing', '.failed.done')
                        success, action, detail = _safe_rename_if_not_done(exec_file, failed_path, agent)
                        if success:
                            log(f"PRE-DISPATCH RECOVER: {agent}/{exec_file.name} → failed.done (dead PID, max retries)")
                    else:
                        base_name = exec_file.name.replace('.executing.md', '.md')
                        if not base_name.endswith('.md'):
                            base_name += '.md'
                        retry_name = base_name.replace('.md', f'.retry-{retry_count + 1}.md')
                        retry_path = exec_file.parent / retry_name
                        success, action, detail = _safe_rename_if_not_done(exec_file, retry_path, agent)
                        if success:
                            log(f"PRE-DISPATCH RECOVER: {agent}/{exec_file.name} → {retry_name} (dead PID recovered)")

                    # Clean up PID file
                    if pid_file.exists():
                        try:
                            pid_file.unlink()
                        except OSError:
                            pass

        pending = list_pending_tasks(agent_dir)
        new_tasks = [f for f in pending if is_new_task(f, agent, state)]

        # Clean up orphaned permanently-failed tasks (retry_count >= MAX_RETRY)
        # that weren't properly renamed to .failed.done.md
        cleaned = []
        for f in new_tasks:
            rc = _extract_retry_count(f)
            if rc >= MAX_RETRY_COUNT:
                failed_name = f.name.replace('.md', '.failed.done.md')
                failed_path = f.parent / failed_name
                try:
                    f.rename(failed_path)
                    log(f"CLEANUP: {agent}/{f.name} → {failed_name} (retry_count={rc} >= {MAX_RETRY_COUNT})")
                except OSError as e:
                    log(f"CLEANUP FAILED: {agent}/{f.name}: {e}")
                continue
            cleaned.append(f)
        new_tasks = cleaned

        if not new_tasks:
            continue

        # Dispatch the highest-priority new task
        task_file = new_tasks[0]
        task_key = f"{agent}/{task_file.name}"

        log(f"NEW TASK: {task_key}")

        # Submit to thread pool (non-blocking)
        timeout = _timeout_for_task(task_file)
        future = executor.submit(
            execute_task, task_file, agent, task_key, timeout
        )
        with active_lock:
            active_executions[agent] = future

        dispatched += 1

    return dispatched


def cleanup_done_files():
    """Remove .done task files older than 48 hours. Self-wake tasks are removed immediately."""
    now = time.time()
    removed = 0
    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir() or agent_dir.name == 'main':
            continue
        tasks_dir = agent_dir / "tasks"
        if not tasks_dir.exists():
            continue
        for f in tasks_dir.iterdir():
            if '.done' not in f.name:
                continue
            try:
                age = now - f.stat().st_mtime
                # Self-wake tasks: delete immediately after completion
                if 'self-wake' in f.name.lower() or 'selfwake' in f.name.lower():
                    f.unlink()
                    removed += 1
                    continue
                # Regular tasks: delete after 48 hours
                if age > DONE_FILE_MAX_AGE:
                    f.unlink()
                    removed += 1
            except OSError:
                continue
    if removed > 0:
        log(f"Cleaned up {removed} done task file(s)")
    return removed


def cleanup_completed_task_files():
    """Remove .md task files for tasks that are COMPLETED in Neo4j.

    This addresses disk/Neo4j drift where task files remain on disk after
    Neo4j marks them as completed. Without cleanup, the watcher keeps
    trying to re-execute completed tasks.

    Returns:
        Number of files removed
    """
    try:
        from neo4j_atomic_transitions import get_completed_task_ids
    except ImportError:
        log("[cleanup] neo4j_atomic_transitions not available")
        return 0

    removed = 0
    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir() or agent_dir.name == 'main':
            continue
        tasks_dir = agent_dir / "tasks"
        if not tasks_dir.exists():
            continue

        # Get completed task IDs for this agent
        agent = agent_dir.name
        completed_ids = get_completed_task_ids(agent=agent, limit=500)

        if not completed_ids:
            continue

        # Convert to set for fast lookup
        completed_set = set(completed_ids)

        for f in tasks_dir.iterdir():
            if not f.name.endswith('.md'):
                continue
            # Skip already processed files
            if any(x in f.name for x in ['.done', '.executing', '.completed', '.failed']):
                continue

            # Extract task_id from file
            task_id = _extract_task_id(f)
            if not task_id:
                continue

            # Check if this task is completed in Neo4j
            if task_id in completed_set:
                try:
                    f.unlink()
                    removed += 1
                    if removed <= 10:  # Limit logging
                        log(f"[cleanup] Removed completed task file: {agent}/{f.name[:40]}")
                except OSError as e:
                    log(f"[cleanup] Failed to remove {f}: {e}")

    if removed > 0:
        log(f"[cleanup] Removed {removed} completed task file(s) (Neo4j drift cleanup)")
    return removed


def release_stale_claims():
    """Release tasks stuck in EXECUTING status for too long.

    Tasks can get stuck in EXECUTING if:
    - Watcher crashes during execution
    - Network timeout without proper cleanup
    - Process killed without shutdown handler

    This releases claims older than STALE_CLAIM_TIMEOUT_MINUTES.

    Returns:
        Number of claims released
    """
    try:
        from neo4j_atomic_transitions import release_stale_claims as _release_stale
    except ImportError:
        log("[stale_claims] neo4j_atomic_transitions not available")
        return 0

    count, task_ids = _release_stale(timeout_minutes=STALE_CLAIM_TIMEOUT_MINUTES)

    if count > 0:
        log(f"[stale_claims] Released {count} stale claim(s): {task_ids[:5]}...")

    return count


def cleanup_orphan_task_files():
    """Remove .md task files that don't exist in Neo4j at all.

    These are typically created by bugs or failed intakes that wrote the file
    but never created the Neo4j entry.

    Returns:
        Number of orphan files removed
    """
    try:
        from neo4j_atomic_transitions import get_all_tracked_task_ids
    except ImportError:
        log("[orphan_cleanup] neo4j_atomic_transitions not available")
        return 0

    # Get all task IDs from Neo4j
    tracked_ids = get_all_tracked_task_ids()

    removed = 0
    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir() or agent_dir.name == 'main':
            continue
        tasks_dir = agent_dir / "tasks"
        if not tasks_dir.exists():
            continue

        for f in tasks_dir.iterdir():
            if not f.name.endswith('.md'):
                continue
            # Skip already processed files
            if any(x in f.name for x in ['.done', '.executing', '.completed', '.failed']):
                continue

            task_id = _extract_task_id(f)
            if not task_id:
                continue

            # Check if task exists in Neo4j
            if task_id not in tracked_ids:
                try:
                    f.unlink()
                    removed += 1
                    if removed <= 10:
                        log(f"[orphan_cleanup] Removed orphan file: {agent_dir.name}/{f.name[:40]}")
                except OSError as e:
                    log(f"[orphan_cleanup] Failed to remove {f}: {e}")

    if removed > 0:
        log(f"[orphan_cleanup] Removed {removed} orphan task file(s)")
    return removed


# Configuration for stale claim timeout
STALE_CLAIM_TIMEOUT_MINUTES = 30  # Release claims older than 30 minutes

# Orphan process cleanup configuration
ORPHAN_PROCESS_MIN_AGE_SECONDS = 300  # 5 minutes - only kill orphans older than this (lowered from 1800s to fix PENDING_NO_DISPATCH stall)
ORPHAN_SIGTERM_TIMEOUT = 5  # Seconds to wait after SIGTERM before SIGKILL


def cleanup_orphan_processes():
    """Detect and kill orphaned claude-agent processes.

    An orphan process is a claude-agent process that:
    1. Is currently running (found via ps)
    2. Has no corresponding .executing.pid file
    3. Is older than ORPHAN_PROCESS_MIN_AGE_SECONDS (30 minutes)

    This handles the case where the task-watcher loses track of spawned
    processes due to crashes, restarts, or race conditions.

    Returns:
        Number of orphan processes killed
    """
    killed = 0
    now = time.time()

    # Step 1: Find all .executing.pid files and their PIDs
    tracked_pids = {}  # pid -> (agent, pid_file_path, start_time)
    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir() or agent_dir.name == 'main':
            continue
        tasks_dir = agent_dir / "tasks"
        if not tasks_dir.exists():
            continue
        agent = agent_dir.name
        for pid_file in tasks_dir.glob("*.executing.pid"):
            try:
                content = pid_file.read_text().strip()
                lines = content.split('\n', 1)
                pid = int(lines[0])
                # Try to get start time from PID file (second line)
                start_time = None
                if len(lines) > 1:
                    try:
                        start_time = float(lines[1])
                    except (ValueError, IndexError):
                        pass
                tracked_pids[pid] = (agent, str(pid_file), start_time)
            except (ValueError, OSError):
                continue

    # Step 2: Find all running claude-agent processes using ps
    # We look for processes matching "claude-agent" in their command line
    try:
        result = subprocess.run(
            ["ps", "-eo", "pid,etime,args"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            log(f"ORPHAN_CLEANUP: ps command failed: {result.stderr}")
            return 0

        for line in result.stdout.strip().split('\n')[1:]:  # Skip header
            line = line.strip()
            if not line:
                continue

            parts = line.split(None, 2)  # Split into max 3 parts
            if len(parts) < 3:
                continue

            try:
                pid = int(parts[0])
                etime = parts[1]  # Elapsed time (e.g., "30:45" or "1-02:34:56")
                args = parts[2]
            except (ValueError, IndexError):
                continue

            # Check if this is a claude-agent process
            if "claude-agent" not in args:
                continue

            # Check if this PID is tracked
            if pid in tracked_pids:
                continue  # This process has a corresponding .executing.pid file

            # Parse elapsed time to seconds
            age_seconds = _parse_ps_elapsed_time(etime)
            if age_seconds is None:
                # If we can't parse the time, be conservative and skip
                log(f"ORPHAN_CLEANUP: Could not parse elapsed time '{etime}' for PID {pid}")
                continue

            # Check if process is old enough to be considered an orphan
            if age_seconds < ORPHAN_PROCESS_MIN_AGE_SECONDS:
                age_str = _format_age(age_seconds)
                log(f"ORPHAN_CLEANUP: Skipping PID {pid} - too young ({age_str} < {ORPHAN_PROCESS_MIN_AGE_SECONDS}s)")
                continue

            # This is an orphan - kill it
            age_str = _format_age(age_seconds)
            log(f"ORPHAN_CLEANUP: Found orphan PID {pid} (age: {age_str}, cmd: {args[:80]}...)")

            # Try SIGTERM first
            try:
                os.kill(pid, signal.SIGTERM)
                log(f"ORPHAN_CLEANUP: Sent SIGTERM to PID {pid}")
            except ProcessLookupError:
                log(f"ORPHAN_CLEANUP: PID {pid} already gone")
                continue
            except PermissionError:
                log(f"ORPHAN_CLEANUP: No permission to kill PID {pid}")
                continue
            except OSError as e:
                log(f"ORPHAN_CLEANUP: Error sending SIGTERM to PID {pid}: {e}")
                continue

            # Wait for graceful shutdown
            time.sleep(ORPHAN_SIGTERM_TIMEOUT)

            # Check if process is still alive
            try:
                os.kill(pid, 0)  # Signal 0 = liveness check
                # Process still alive - send SIGKILL
                try:
                    os.kill(pid, signal.SIGKILL)
                    log(f"ORPHAN_CLEANUP: Sent SIGKILL to PID {pid} (SIGTERM timeout)")
                except (ProcessLookupError, PermissionError, OSError) as e:
                    log(f"ORPHAN_CLEANUP: SIGKILL failed for PID {pid}: {e}")
            except ProcessLookupError:
                # Process exited after SIGTERM - good
                log(f"ORPHAN_CLEANUP: PID {pid} terminated gracefully after SIGTERM")

            killed += 1

    except subprocess.TimeoutExpired:
        log("ORPHAN_CLEANUP: ps command timed out")
    except Exception as e:
        log(f"ORPHAN_CLEANUP: Error finding processes: {e}")

    if killed > 0:
        log(f"ORPHAN_CLEANUP: Killed {killed} orphan process(es)")

    return killed


def _parse_ps_elapsed_time(etime: str) -> int | None:
    """Parse ps elapsed time format to seconds.

    Formats handled:
    - "SS" or "SS.cc" - seconds
    - "MM:SS" or "MM:SS.cc" - minutes:seconds
    - "HH:MM:SS" or "HH:MM:SS.cc" - hours:minutes:seconds
    - "DD-HH:MM:SS" or "DD-HH:MM:SS.cc" - days-hours:minutes:seconds

    Returns:
        Total seconds as int, or None if parsing fails
    """
    try:
        # Remove fractional seconds if present
        if '.' in etime:
            etime = etime.split('.')[0]

        # Check for days component
        days = 0
        if '-' in etime:
            day_part, etime = etime.split('-', 1)
            days = int(day_part)

        parts = etime.split(':')

        if len(parts) == 1:
            # Just seconds
            seconds = int(parts[0])
            minutes = 0
            hours = 0
        elif len(parts) == 2:
            # MM:SS
            seconds = int(parts[1])
            minutes = int(parts[0])
            hours = 0
        elif len(parts) == 3:
            # HH:MM:SS
            seconds = int(parts[2])
            minutes = int(parts[1])
            hours = int(parts[0])
        else:
            return None

        total = (days * 86400) + (hours * 3600) + (minutes * 60) + seconds
        return total
    except (ValueError, IndexError):
        return None


def _format_age(seconds: int) -> str:
    """Format age in seconds to human-readable string."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"


def recover_stuck_failed_tasks():
    """Rename permanently-failed tasks that are stuck as .md back to .failed.done.md.

    Bug: When a task hits MAX_RETRY_COUNT, _append_failure_context is supposed to
    rename it to .failed.done.md. But a race with agent-task-handler's
    mark_task_completed('failed') can leave the file as .md with retry_count >= MAX
    and a state entry showing success=False. The watcher's is_new_task() then skips
    them forever (mtime <= exec_time), blocking the agent's execution slot from
    picking up genuinely new tasks.

    Fix: Scan for .md files that are in state as permanently failed, and rename them
    to .failed.done.md so they stop blocking the pending-task scan.
    """
    state = load_state()
    recovered = 0

    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir() or agent_dir.name == 'main':
            continue
        agent = agent_dir.name
        tasks_dir = agent_dir / "tasks"
        if not tasks_dir.exists():
            continue

        for f in tasks_dir.glob("*.md"):
            if any(x in f.name for x in ['.executing', '.done']):
                continue
            key = f"{agent}/{f.name}"
            entry = state.get(key)
            if not entry:
                continue
            # Task is in state as failed
            if entry.get('success', True):
                continue
            # Check retry_count in file
            retry_count = _extract_retry_count(f)
            if retry_count < MAX_RETRY_COUNT:
                continue
            # This task is permanently failed but stuck as .md — rename it
            failed_name = f.name.replace('.md', '.failed.done.md')
            failed_path = f.parent / failed_name
            try:
                f.rename(failed_path)
                recovered += 1
                log(f"  STUCK-FAIL RECOVERY: {key} → {failed_name} (retry_count={retry_count}, was stuck as .md)")
            except OSError as e:
                log(f"  STUCK-FAIL RECOVERY ERROR: {key}: {e}")

    if recovered > 0:
        log(f"Recovered {recovered} stuck-failed task(s)")
    return recovered


def recover_completed_md_files():
    """Rename .completed.md files to .completed.done.md for proper cleanup.

    Bug: Agent completion summaries are written as .completed.md instead of
    .completed.done.md. This prevents task-watcher from processing them correctly
    and they never get cleaned up.

    Fix: Rename all .completed.md files to .completed.done.md so they're recognized
    as terminal state files and cleaned up after 48 hours.
    """
    recovered = 0
    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir() or agent_dir.name == 'main':
            continue
        tasks_dir = agent_dir / "tasks"
        if not tasks_dir.exists():
            continue
        agent = agent_dir.name
        for f in tasks_dir.iterdir():
            if not f.name.endswith('.completed.md') or f.name.endswith('.done.md'):
                continue
            # Rename .completed.md to .completed.done.md
            new_name = f.name.replace('.completed.md', '.completed.done.md')
            new_path = f.parent / new_name
            try:
                f.rename(new_path)
                recovered += 1
                log(f"  COMPLETED-MD RECOVERY: {agent}/{f.name} → {new_name}")
                # Emit ledger event for tracking this bug occurrence
                try:
                    task_id = _extract_task_id(new_path)
                    _append_ledger({
                        "event": "COMPLETED_MD_SUFFIX_BUG",
                        "ts": datetime.now().isoformat(),
                        "agent": agent,
                        "task_file": str(new_path),
                        "task_id": task_id,
                        "original_suffix": ".completed.md",
                        "fixed_suffix": ".completed.done.md",
                        "severity": "medium"
                    })
                except Exception:
                    pass  # Don't block recovery on ledger failure
            except OSError as e:
                log(f"  COMPLETED-MD RECOVERY ERROR: {agent}/{f.name}: {e}")

    if recovered > 0:
        log(f"Recovered {recovered} .completed.md file(s)")
    return recovered


def _already_completed(executing_file):
    """Check if a .completed.done.md, .failed.done.md, or .no_output.done.md already exists for this task.

    Prevents the rename race condition where recover_stale_executions() tries to
    recover a task that mark_task_completed() already finished. Returns True if
    the task is already done and the .executing.md file should just be cleaned up.
    """
    stem = executing_file.name.replace('.executing.md', '')
    # Strip retry suffixes to get the base stem
    stem_base = re.sub(r'\.retry-\d+', '', stem)
    parent = executing_file.parent
    for done_file in parent.iterdir():
        if not done_file.name.endswith('.done.md'):
            continue
        # Check for all terminal states: .completed.done.md, .failed.done.md, .no_output.done.md,
        # .dup-orphan.done.md, .deadpid-orphan.done.md (duplicate recovery)
        # .no_output.done.md added 2026-03-09 to prevent false-positive escalations
        done_stem = None
        if '.completed.done.md' in done_file.name:
            done_stem = done_file.name.split('.completed.done.md')[0]
        elif '.failed.done.md' in done_file.name:
            done_stem = done_file.name.split('.failed.done.md')[0]
        elif '.no_output.done.md' in done_file.name:
            done_stem = done_file.name.split('.no_output.done.md')[0]
        elif '.dup-orphan.done.md' in done_file.name:
            done_stem = done_file.name.split('.dup-orphan.done.md')[0]
        elif '.deadpid-orphan.done.md' in done_file.name:
            done_stem = done_file.name.split('.deadpid-orphan.done.md')[0]

        if done_stem is None:
            continue
        done_stem_base = re.sub(r'\.retry-\d+', '', done_stem)
        if done_stem_base == stem_base:
            return True
    return False


def _cleanup_escalation_marker(executing_file):
    """Remove .stuck-escalated marker if it exists.

    Called when a task is recovered/completed to clean up the escalation
    marker created by Phase 1.75 stuck task detection.
    """
    escalation_marker = executing_file.parent / f"{executing_file.name}.stuck-escalated"
    if escalation_marker.exists():
        try:
            escalation_marker.unlink()
        except OSError:
            pass


def _safe_rename_if_not_done(executing_file, target_path, agent="unknown"):
    """Atomic rename with race guard for completion.

    Checks if task is already completed BEFORE renaming, then does atomic rename.
    Returns (success: bool, action: str, error: str).

    This prevents the race condition where:
    1. recover_stale_executions() checks _already_completed() -> False
    2. mark_task_completed() renames .executing.md -> .completed.done.md
    3. recover_stale_executions() tries to rename same file -> FileNotFoundError or corrupts state

    The fix: check again inside a file lock before the actual rename.
    """
    # Quick check without lock (fast path for common case)
    if _already_completed(executing_file):
        return False, "skip", "already_completed"

    # Acquire lock for this specific task's stem
    stem = executing_file.stem.replace('.executing', '')
    stem_base = re.sub(r'\.retry-\d+', '', stem)
    lock_path = executing_file.parent / f".{stem_base}.rename-lock"

    lock_fd = None
    try:
        # Open lock file with exclusive creation (O_CREAT | O_EXCL)
        # This fails if lock already exists, meaning another process is handling this task
        lock_fd = os.open(lock_path, os.O_CREAT | O_OEXCL | os.O_WRONLY)
    except (FileExistsError, PermissionError):
        # Another process has the lock - they're handling it
        return False, "skip", "concurrent_operation"

    try:
        # RECHECK completion after acquiring lock
        # This is the critical fix - prevents TOCTOU race
        if _already_completed(executing_file):
            return False, "skip", "already_completed_locked"

        # Verify source file still exists (might have been renamed during lock wait)
        if not executing_file.exists():
            return False, "skip", "source_gone"

        # Do the atomic rename
        os.rename(executing_file, target_path)
        return True, "renamed", "ok"

    except FileNotFoundError:
        # File was renamed between lock acquire and our rename
        return False, "skip", "race_renamed"
    except OSError as e:
        return False, "error", str(e)
    finally:
        # Always release lock
        try:
            os.close(lock_fd)
            lock_path.unlink(missing_ok=True)
        except (OSError, AttributeError):
            pass


# O_EXCL constant for file locking
O_OEXCL = os.O_EXCL if hasattr(os, 'O_EXCL') else 0x800


def recover_stale_executions():
    """Recover tasks stuck in .executing state (orphaned by SIGTERM/crash).

    If an .executing file is older than STALE_EXECUTING_AGE, the child process
    that was working on it is almost certainly dead. Rename it back to .md so
    the next watch_cycle retries it, or mark it failed if it's been retried
    too many times.

    Also detects DUPLICATE .executing files per agent (caused by race conditions
    when multiple watcher instances run). When an agent has >1 executing file,
    only the newest is kept; older ones are recovered immediately.
    """
    now = time.time()
    recovered = 0

    # Phase 1: Detect and recover duplicate .executing files per agent.
    # Each agent should have at most 1 executing task. Extra ones are orphans
    # from a double-dispatch race condition and block the agent indefinitely.
    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir() or agent_dir.name == 'main':
            continue
        tasks_dir = agent_dir / "tasks"
        if not tasks_dir.exists():
            continue
        agent = agent_dir.name
        executing_files = []
        for f in tasks_dir.iterdir():
            # Only match .executing.md files, NOT .executing.pid sentinels
            # Also skip files with completion markers (false positives)
            if f.is_file() and f.name.endswith('.executing.md'):
                # Skip completed task patterns
                if any(f.name.endswith(pattern) for pattern in [
                    ".verified.done.md.executing.md",
                    ".completed.done.md.executing.md",
                    ".no_output.done.md.executing.md",
                    ".failed.done.md.executing.md",
                    ".done.md.executing.md",
                    ".failed.md.executing.md",
                    ".completed.md.executing.md",
                ]):
                    continue
                try:
                    mtime = f.stat().st_mtime
                    executing_files.append((mtime, f))
                except OSError:
                    continue
        if len(executing_files) > 1:
            # Sort newest first — keep the newest, recover all older ones
            recovered = 0  # Reset per-agent counter
            executing_files.sort(key=lambda x: x[0], reverse=True)
            for mtime, f in executing_files[1:]:
                age = now - mtime
                # Check if this specific execution has a live PID
                pid_file = f.parent / f.name.replace('.executing.md', '.executing.pid')
                pid_alive = False
                if pid_file.exists():
                    try:
                        handler_pid = int(pid_file.read_text().strip())
                        os.kill(handler_pid, 0)
                        pid_alive = True
                    except (ValueError, ProcessLookupError, PermissionError, OSError):
                        pass
                if pid_alive:
                    continue  # This one is legitimately running, skip

                # Race guard: handler may have already completed this task
                if _already_completed(f):
                    log(f"DEDUP SKIP: {agent}/{f.name} — already completed by handler, cleaning up")
                    try:
                        f.unlink()
                        pid_file_cleanup = f.parent / f.name.replace('.executing.md', '.executing.pid')
                        if pid_file_cleanup.exists():
                            pid_file_cleanup.unlink()
                    except OSError:
                        pass
                    continue

                retry_count = len(re.findall(r'\.retry-\d+', f.name))
                if retry_count >= MAX_RETRY_COUNT:
                    failed_path = f.parent / f.name.replace('.executing', '.failed.done')
                    success, action, detail = _safe_rename_if_not_done(f, failed_path, agent)
                    if success:
                        task_id = _extract_task_id(failed_path)
                        log(f"DEDUP RECOVER: {agent}/{f.name} → failed.done (duplicate executing, max retries)")
                        if task_id:
                            _append_ledger({"task_id": task_id, "event": "FAILED",
                                "ts": datetime.now().isoformat(), "agent": agent,
                                "error": f"Duplicate executing file recovered (age={round(age)}s, retries={retry_count})"})
                            _neo4j_update_status(task_id, "FAILED", agent=agent,
                                error_msg="Duplicate executing file — double-dispatch race")
                    elif action == "skip" and detail in ("already_completed", "already_completed_locked", "source_gone"):
                        log(f"DEDUP SKIP: {agent}/{f.name} — {detail}")
                    else:
                        log(f"DEDUP ERROR: {agent}/{f.name} — {action} - {detail}")
                    continue
                else:
                    base_name = f.name.replace('.executing.md', '.md').replace('.executing', '')
                    if not base_name.endswith('.md'):
                        base_name += '.md'
                    retry_name = base_name.replace('.md', f'.retry-{retry_count + 1}.md')
                    original_path = f.parent / retry_name
                    if original_path.exists():
                        dup_path = f.parent / f.name.replace('.executing', '.dup-orphan.done')
                        success, action, detail = _safe_rename_if_not_done(f, dup_path, agent)
                        if success:
                            log(f"DEDUP RECOVER: {agent}/{f.name} → dup-orphan.done (retry target exists)")
                        elif action == "skip" and detail in ("already_completed", "already_completed_locked", "source_gone"):
                            log(f"DEDUP SKIP: {agent}/{f.name} — {detail}")
                        else:
                            log(f"DEDUP ERROR: {agent}/{f.name} — {action} - {detail}")
                    else:
                        success, action, detail = _safe_rename_if_not_done(f, original_path, agent)
                        if success:
                            log(f"DEDUP RECOVER: {agent}/{f.name} → {retry_name} (duplicate executing, retry {retry_count + 1})")
                            task_id = _extract_task_id(original_path)
                            if task_id:
                                _append_ledger({"task_id": task_id, "event": "RECOVERED",
                                    "ts": datetime.now().isoformat(), "agent": agent,
                                    "stale_age_s": round(age), "retry": retry_count + 1,
                                    "reason": "duplicate_executing"})
                        elif action == "skip" and detail in ("already_completed", "already_completed_locked", "source_gone"):
                            log(f"DEDUP SKIP: {agent}/{f.name} — {detail}")
                        else:
                            log(f"DEDUP ERROR: {agent}/{f.name} — {action} - {detail}")
                    continue
                # Clean up PID file if it exists
                try:
                    if pid_file.exists():
                        pid_file.unlink()
                except OSError:
                    pass
                recovered += 1
            if recovered > 0:
                log(f"DEDUP: {agent} had {len(executing_files)} executing files, recovered {recovered} duplicate(s)")

    # Phase 1.5: Dead PID fast recovery
    # If the handler PID is confirmed dead and the task is older than a short
    # grace period, recover immediately instead of waiting STALE_EXECUTING_AGE
    # (~2h). This closes the throughput gap where a crashed task blocks an
    # agent's execution slot for hours.
    DEAD_PID_GRACE_SECS = 120  # 2 minutes grace to avoid race with startup
    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir() or agent_dir.name == 'main':
            continue
        tasks_dir = agent_dir / "tasks"
        if not tasks_dir.exists():
            continue
        agent = agent_dir.name
        for f in tasks_dir.iterdir():
            if not f.name.endswith('.executing.md') or '.done' in f.name:
                continue
            try:
                age = now - f.stat().st_mtime
            except OSError:
                continue
            if age < DEAD_PID_GRACE_SECS:
                continue  # Too young — PID may still be starting up
            if age >= STALE_EXECUTING_AGE:
                continue  # Will be handled by Phase 2 below

            # Skip if in-memory future is still running (current watcher session)
            with active_lock:
                if agent in active_executions and not active_executions[agent].done():
                    continue

            # Check PID liveness
            pid_file = f.parent / f.name.replace('.executing.md', '.executing.pid')
            if not pid_file.exists():
                # No PID file = orphan from crash before PID was written
                pid_alive = False
            else:
                try:
                    handler_pid = int(pid_file.read_text().strip().split('\n')[0])
                    os.kill(handler_pid, 0)
                    pid_alive = True
                except (ValueError, ProcessLookupError, PermissionError, OSError):
                    pid_alive = False

            if pid_alive:
                continue  # Process is running fine, let it work

            # PID is dead — fast-recover this task

            # Race guard: handler may have already completed this task
            if _already_completed(f):
                log(f"DEAD_PID SKIP: {agent}/{f.name} — already completed by handler, cleaning up")
                try:
                    f.unlink()
                    if pid_file.exists():
                        pid_file.unlink()
                except OSError:
                    pass
                continue

            retry_count = len(re.findall(r'\.retry-\d+', f.name))
            actual_age = f"{age/60:.1f}m" if age < 3600 else f"{age/3600:.1f}h"
            task_id = _extract_task_id(f)

            if retry_count >= MAX_RETRY_COUNT:
                failed_path = f.parent / f.name.replace('.executing', '.failed.done')
                success, action, detail = _safe_rename_if_not_done(f, failed_path, agent)
                if success:
                    log(f"DEAD_PID RECOVER: {agent}/{f.name} → failed.done (PID dead after {actual_age}, max retries={retry_count})")
                    if task_id:
                        _append_ledger({"task_id": task_id, "event": "FAILED",
                            "ts": datetime.now().isoformat(), "agent": agent,
                            "error": f"Handler PID dead after {actual_age}, max retries exhausted"})
                        _neo4j_update_status(task_id, "FAILED", agent=agent,
                            error_msg=f"Handler PID dead after {actual_age}")
                elif action == "skip" and detail in ("already_completed", "already_completed_locked", "source_gone"):
                    log(f"DEAD_PID SKIP: {agent}/{f.name} — {detail}")
                else:
                    log(f"DEAD_PID ERROR: {agent}/{f.name} — {action} - {detail}")
                continue
            else:
                base_name = f.name.replace('.executing.md', '.md').replace('.executing', '')
                if not base_name.endswith('.md'):
                    base_name += '.md'
                retry_name = base_name.replace('.md', f'.retry-{retry_count + 1}.md')
                original_path = f.parent / retry_name
                if original_path.exists():
                    dup_path = f.parent / f.name.replace('.executing', '.deadpid-orphan.done')
                    success, action, detail = _safe_rename_if_not_done(f, dup_path, agent)
                    if success:
                        log(f"DEAD_PID RECOVER: {agent}/{f.name} → deadpid-orphan.done (retry target exists)")
                    elif action == "skip" and detail in ("already_completed", "already_completed_locked", "source_gone"):
                        log(f"DEAD_PID SKIP: {agent}/{f.name} — {detail}")
                    else:
                        log(f"DEAD_PID ERROR: {agent}/{f.name} — {action} - {detail}")
                    continue
                else:
                    success, action, detail = _safe_rename_if_not_done(f, original_path, agent)
                    if success:
                        log(f"DEAD_PID RECOVER: {agent}/{f.name} → {retry_name} (PID dead after {actual_age}, retry {retry_count + 1})")
                        if task_id:
                            _append_ledger({"task_id": task_id, "event": "RECOVERED",
                                "ts": datetime.now().isoformat(), "agent": agent,
                                "stale_age_s": round(age), "retry": retry_count + 1,
                                "reason": "dead_pid_fast_recovery"})
                            _neo4j_update_status(task_id, "PENDING", agent=agent)
                    elif action == "skip" and detail in ("already_completed", "already_completed_locked", "source_gone"):
                        log(f"DEAD_PID SKIP: {agent}/{f.name} — {detail}")
                    else:
                        log(f"DEAD_PID ERROR: {agent}/{f.name} — {action} - {detail}")
                    continue
            # Clean up PID file
            try:
                if pid_file.exists():
                    pid_file.unlink()
            except OSError:
                pass
            recovered += 1
            log(f"DEAD_PID: {agent} slot unblocked — next watch_cycle can dispatch new task")

    # Phase 1.75: Stuck-but-alive task escalation (2026-03-11)
    # Detects tasks >15 minutes old where PID is alive but task may be hung
    # (e.g., agent stuck waiting for input, network limbo, etc.)
    # Escalates to kublai for manual intervention instead of waiting 2+ hours
    STUCK_ESCALATION_AGE = 900  # 15 minutes — faster than STALE_EXECUTING_AGE (2h)
    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir() or agent_dir.name == 'main':
            continue
        tasks_dir = agent_dir / "tasks"
        if not tasks_dir.exists():
            continue
        agent = agent_dir.name
        for f in tasks_dir.iterdir():
            if not f.name.endswith('.executing.md') or '.done' in f.name:
                continue
            try:
                age = now - f.stat().st_mtime
            except OSError:
                continue
            # Only check tasks in the stuck window: 15min to STALE_EXECUTING_AGE
            if age < STUCK_ESCALATION_AGE:
                continue
            if age >= STALE_EXECUTING_AGE:
                continue  # Will be handled by Phase 2 below

            # Skip if we've already escalated this task
            escalation_marker = f.parent / f"{f.name}.stuck-escalated"
            if escalation_marker.exists():
                continue

            # Check if in-memory future is still running
            with active_lock:
                if agent in active_executions and not active_executions[agent].done():
                    # Task is actively running in current watcher session
                    continue

            # Check PID liveness
            pid_file = f.parent / f.name.replace('.executing.md', '.executing.pid')
            pid_alive = False
            handler_pid = None
            if pid_file.exists():
                try:
                    pid_content = pid_file.read_text().strip().split('\n')
                    handler_pid = int(pid_content[0])
                    os.kill(handler_pid, 0)
                    pid_alive = True
                except (ValueError, ProcessLookupError, PermissionError, OSError):
                    pid_alive = False

            # Even if PID is alive, task may be stuck — escalate for review
            task_id = _extract_task_id(f)
            actual_age = f"{age/60:.1f}m" if age < 3600 else f"{age/3600:.1f}h"
            pid_status = f"PID {handler_pid} alive" if pid_alive else "PID dead"

            # Create escalation task for kublai
            escalation_path = tasks_dir / f"stuck-{agent}-{int(now)}.md"
            escalation_content = f"""---
priority: high
agent: kublai
escalated_from: {agent}
escalation_type: stuck_task_alive
original_task: {task_id or 'unknown'}
stuck_age: {actual_age}
pid_status: {pid_status}
---

# Stuck Task Escalation: {agent}

**Task:** `{task_id or f.name}`
**Age:** {actual_age}
**Status:** {pid_status}

The task has been in EXECUTING state for {actual_age} but may be stuck:
- PID is {'alive (agent process running)' if pid_alive else 'dead (agent process crashed)'}
- Task file: `{f.name}`
- Agent: {agent}

## Action Required
1. Check if the agent session is responsive
2. Review task file for progress indicators
3. Either:
   - Allow more time if task is genuinely long-running
   - Kill and retry if agent is hung
   - Mark as failed if unrecoverable

## Files
- Task: `~/.openclaw/agents/{agent}/tasks/{f.name}`
- PID file: `{pid_file}`
"""
            try:
                escalation_path.write_text(escalation_content)
                # Create marker to prevent duplicate escalations
                escalation_marker.touch()
                log(f"STUCK ESCALATE: {agent}/{f.name} → kublai (age={actual_age}, {pid_status})")
            except OSError as e:
                log(f"STUCK ERROR: Failed to create escalation for {agent}/{f.name}: {e}")

    # Phase 2: Standard age-based stale recovery
    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir() or agent_dir.name == 'main':
            continue
        tasks_dir = agent_dir / "tasks"
        if not tasks_dir.exists():
            continue
        for f in tasks_dir.iterdir():
            # Only match .executing.md files, NOT .executing.pid sentinels
            if not f.name.endswith('.executing.md') or '.done' in f.name:
                continue
            try:
                age = now - f.stat().st_mtime
            except OSError:
                continue
            if age < STALE_EXECUTING_AGE:
                continue

            agent = agent_dir.name

            # Check if this agent currently has an active execution
            with active_lock:
                if agent in active_executions and not active_executions[agent].done():
                    continue  # Still running, don't touch

            # Check if handler process is still alive via PID sentinel file
            pid_file = f.parent / f.name.replace('.executing.md', '.executing.pid')

            # Calculate age from PID file start timestamp (not file mtime, which gets reset on retries)
            pid_start_ts = None
            if pid_file.exists():
                try:
                    pid_content = pid_file.read_text().strip()
                    lines = pid_content.split('\n', 1)
                    handler_pid = int(lines[0])
                    if len(lines) > 1:
                        pid_start_ts = float(lines[1])
                        # Recalculate age based on process start time, not file mtime
                        age = now - pid_start_ts
                except (ValueError, IndexError):
                    handler_pid = None

            force_kill = age >= HARD_MAX_EXECUTING_AGE
            if pid_file.exists() and handler_pid:
                try:
                    os.kill(handler_pid, 0)  # Signal 0 = liveness check
                    if not force_kill:
                        actual_age = f"{age/60:.1f}m" if age < 3600 else f"{age/3600:.1f}h"
                        log(f"RECOVER SKIP: {agent}/{f.name} — handler PID {handler_pid} still alive (age: {actual_age})")
                        continue
                    # Hard ceiling exceeded — kill the zombie process tree
                    actual_age = f"{age/3600:.1f}h" if age >= 3600 else f"{age/60:.1f}m"
                    log(f"HARD KILL: {agent}/{f.name} — PID {handler_pid} alive but age {actual_age} exceeds {HARD_MAX_EXECUTING_AGE/3600:.0f}h ceiling")
                    try:
                        os.killpg(os.getpgid(handler_pid), signal.SIGTERM)
                        time.sleep(2)
                        os.killpg(os.getpgid(handler_pid), signal.SIGKILL)
                    except (ProcessLookupError, PermissionError, OSError):
                        try:
                            os.kill(handler_pid, signal.SIGKILL)
                        except (ProcessLookupError, PermissionError):
                            pass
                except (ProcessLookupError, PermissionError):
                    # Process dead — safe to recover
                    pass
                try:
                    pid_file.unlink()
                except OSError:
                    pass

            # Race guard: handler may have already completed this task
            if _already_completed(f):
                log(f"RECOVER SKIP: {agent}/{f.name} — already completed by handler, cleaning up")
                _cleanup_escalation_marker(f)
                try:
                    f.unlink()
                except OSError:
                    pass
                continue

            # Count retries from filename (total .retry-N suffixes)
            retry_count = len(re.findall(r'\.retry-\d+', f.name))

            if retry_count >= MAX_RETRY_COUNT:
                # Permanently fail — stop retrying
                failed_path = f.parent / f.name.replace('.executing', '.failed.done')
                success, action, detail = _safe_rename_if_not_done(f, failed_path, agent)
                if success:
                    _cleanup_escalation_marker(f)
                    task_id = _extract_task_id(failed_path)
                    log(f"RECOVER: {agent}/{f.name} → failed.done (max retries reached)")
                    if task_id:
                        error_msg = f"Max retries ({MAX_RETRY_COUNT}) exceeded, stale_age={round(age)}s"
                        _append_ledger({
                            "task_id": task_id,
                            "event": "FAILED",
                            "ts": datetime.now().isoformat(),
                            "agent": agent,
                            "error": error_msg,
                        })
                        _neo4j_update_status(task_id, "FAILED", agent=agent, error_msg=error_msg)
                elif action == "skip" and detail in ("already_completed", "already_completed_locked", "source_gone"):
                    # Handler already completed this task — clean up and continue
                    log(f"RECOVER SKIP: {agent}/{f.name} — {detail}")
                else:
                    log(f"RECOVER ERROR: {agent}/{f.name} — {action} - {detail}")
                    continue
            else:
                # Rename back to .md for retry (strip .executing, add retry counter)
                base_name = f.name.replace('.executing.md', '.md').replace('.executing', '')
                if not base_name.endswith('.md'):
                    base_name += '.md'
                # Insert retry counter before .md
                retry_name = base_name.replace('.md', f'.retry-{retry_count + 1}.md')
                original_path = f.parent / retry_name

                if original_path.exists():
                    failed_path = f.parent / f.name.replace('.executing', '.orphan-failed.done')
                    success, action, detail = _safe_rename_if_not_done(f, failed_path, agent)
                    if success:
                        log(f"RECOVER: {agent}/{f.name} → orphan-failed (original re-created)")
                    elif action == "skip" and detail in ("already_completed", "already_completed_locked", "source_gone"):
                        log(f"RECOVER SKIP: {agent}/{f.name} — {detail}")
                    else:
                        log(f"RECOVER ERROR: {agent}/{f.name} — {action} - {detail}")
                    continue
                else:
                    success, action, detail = _safe_rename_if_not_done(f, original_path, agent)
                    if success:
                        _cleanup_escalation_marker(f)
                        log(f"RECOVER: {agent}/{f.name} → {retry_name} (retry {retry_count + 1}/{MAX_RETRY_COUNT})")
                        task_id = _extract_task_id(original_path)
                        if task_id:
                            _append_ledger({
                                "task_id": task_id,
                                "event": "RECOVERED",
                                "ts": datetime.now().isoformat(),
                                "agent": agent,
                                "stale_age_s": round(age),
                                "retry": retry_count + 1,
                            })
                    elif action == "skip" and detail in ("already_completed", "already_completed_locked", "source_gone"):
                        log(f"RECOVER SKIP: {agent}/{f.name} — {detail}")
                    else:
                        log(f"RECOVER ERROR: {agent}/{f.name} — {action} - {detail}")
                    continue

            recovered += 1

    if recovered > 0:
        log(f"Recovered {recovered} stale executing task(s)")
    return recovered


# ==========================================================
# REVISION LOOP DETECTOR
# ==========================================================

_last_revision_check = 0
_REVISION_CHECK_INTERVAL = 600  # 10 minutes
_MAX_REVISION_DEPTH = 3  # After .revision-3, force escalation or fail

def detect_revision_loops():
    """Detect and break revision death spirals.

    When a task produces insufficient output, quality gates create
    .revision-N.md files. If these revisions also produce short output,
    we get an endless loop that blocks the agent's queue.

    This function:
    1. Finds tasks with deep revision chains (>= _MAX_REVISION_DEPTH)
    2. Checks if the latest revision also has .no_output or .failed markers
    3. Either escalates to kublai or marks as permanently failed

    FIX 2026-03-09: Count ALL .revision- occurrences in filename, not just
    those matching strict pattern. This catches death spirals like:
    task.revision-1.failed.revision-1.failed.revision-1.failed...

    Returns count of tasks broken out of revision loops.
    """
    global _last_revision_check

    now = time.time()
    if now - _last_revision_check < _REVISION_CHECK_INTERVAL:
        return 0

    _last_revision_check = now
    broken_loops = 0

    # Pattern to find ALL .revision-N occurrences in filename
    revision_counter = re.compile(r'\.revision-(\d+)')
    # Pattern to extract base task name (strip all .revision-N.* suffixes)
    base_extractor = re.compile(r'^(.+?)(\.revision-\d+)+$')

    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir() or agent_dir.name == 'main':
            continue

        tasks_dir = agent_dir / "tasks"
        if not tasks_dir.exists():
            continue

        agent = agent_dir.name

        # Scan ALL .md files, count .revision-N occurrences
        for f in tasks_dir.iterdir():
            if not f.is_file() or not f.name.endswith('.md'):
                continue

            # Skip already-done files
            if '.done.' in f.name or f.name.endswith('.done.md'):
                continue

            # Count ALL .revision-N occurrences in filename
            all_matches = revision_counter.findall(f.name)
            revision_count = len(all_matches)

            if revision_count >= _MAX_REVISION_DEPTH:
                # Check if this is a failing revision
                is_failing_revision = (
                    '.no_output.' in f.name or
                    '.failed.' in f.name or
                    '.unverified.' in f.name
                )

                if is_failing_revision:
                    # Extract base task name by stripping ALL .revision-N.* suffixes
                    base_match = base_extractor.match(f.name)
                    if base_match:
                        base = base_match.group(1)
                    else:
                        base = f.name  # Fallback

                    # Break the loop - escalate to kublai
                    escalation_path = tasks_dir / f"{base}.revision-loop-escalated.md"

                    if not escalation_path.exists():
                        try:
                            # Create escalation task for kublai
                            escalation_content = f"""---
priority: high
created: {datetime.now().isoformat()}
source: revision-loop-detector
parent_task: {agent}/{base}
escalation_type: revision_death_spiral
agent: temujin
---

# Revision Loop Escalation: {agent}/{base}

This task has been through {revision_count} revision attempts without producing valid output.

**Latest status:** {f.name}

**Root cause:** The task keeps producing output that fails quality verification (too short or insufficient substance), creating a death spiral.

**Action needed:**
1. Review the original task requirements
2. Either: simplify the task scope OR mark as failed with clear reason
3. Do NOT create another revision - break the loop

**Detected by:** Fixed loop detector 2026-03-09 (counts all .revision- occurrences)
"""
                            escalation_path.write_text(escalation_content)

                            # Move the revision file to completed state to stop the loop
                            failed_path = f.parent / f.name.replace('.executing.md', '.loop-escalated.done').replace('.md', '.loop-escalated.done')
                            if not failed_path.name.endswith('.done'):
                                failed_path = f.parent / f"{f.name}.loop-escalated.done"

                            try:
                                f.rename(failed_path)
                            except OSError:
                                pass  # File may have been processed already

                            log(f"[REVISION_LOOP] Escalated {agent}/{base} after {revision_count} revisions")
                            broken_loops += 1

                            # Log to ledger
                            task_id = _extract_task_id(escalation_path)
                            if task_id:
                                _append_ledger({
                                    "task_id": task_id,
                                    "event": "REVISION_LOOP_ESCALATED",
                                    "ts": datetime.now().isoformat(),
                                    "agent": agent,
                                    "base_task": base,
                                    "revision_depth": revision_count,
                                    "latest_file": f.name
                                })

                        except Exception as e:
                            log(f"[REVISION_LOOP] Failed to escalate {agent}/{base}: {e}")

    return broken_loops


# ==========================================================
# COMPLETION GATE RESOLUTION
# ==========================================================

# Gate resolution removed - handled by cron job (completion-gate-resolver)
# Fix for dual-trigger race condition (2026-03-08)


_DAEMON_LOCK_FILE = AGENTS_DIR / "main" / "logs" / "task-watcher.lock"


def _acquire_daemon_lock():
    """Acquire exclusive file lock to prevent multiple task-watcher instances.

    Returns the open file descriptor (must be kept alive) or None if another
    instance is already running.

    Uses open("a+") to avoid truncation race: two processes opening with "w"
    simultaneously both truncate the file before either acquires the lock,
    which can cause flock to operate on different file descriptions on some
    OS/filesystem combinations.  With "a+" the file is never truncated until
    AFTER the lock is held.
    """
    _DAEMON_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = open(_DAEMON_LOCK_FILE, "a+")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        # Another instance holds the lock — check if it's still alive
        lock_fd.seek(0)
        existing_content = lock_fd.read().strip().split("\n")
        lock_fd.close()
        existing_pid = None
        try:
            existing_pid = int(existing_content[0])
        except (ValueError, IndexError):
            pass
        if existing_pid:
            try:
                os.kill(existing_pid, 0)  # Liveness check
                log(f"ABORT: Another task-watcher already running (PID {existing_pid})")
                return None
            except (ProcessLookupError, PermissionError):
                # Stale lock — previous holder is dead, force-acquire
                log(f"STALE LOCK: PID {existing_pid} is dead, force-acquiring lock")
                lock_fd = open(_DAEMON_LOCK_FILE, "a+")
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    log("ABORT: Lock contention during stale recovery")
                    lock_fd.close()
                    return None
        else:
            log("ABORT: Another task-watcher already running (unknown PID)")
            return None

    # Lock acquired — truncate and write our PID
    lock_fd.seek(0)
    lock_fd.truncate()
    lock_fd.write(f"{os.getpid()}\n{datetime.now().isoformat()}\n")
    lock_fd.flush()
    return lock_fd


def daemon_loop(poll_interval):
    """Main daemon loop with concurrent execution."""
    log(f"Task Watcher starting (poll interval: {poll_interval}s, max concurrent: {MAX_CONCURRENT_AGENTS})")
    log(f"Watching: {AGENTS_DIR}")
    log(f"State file: {STATE_FILE}")

    last_cleanup = 0
    cycle_count = 0

    # Recover any stale .executing files on startup
    try:
        recover_stale_executions()
    except Exception as e:
        log(f"Startup recovery error: {e}")

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_AGENTS) as executor:
        while not stop_event.is_set():
            cycle_count += 1

            try:
                dispatched = watch_cycle(executor)
                if dispatched > 0:
                    log(f"Dispatched {dispatched} task(s)")
            except Exception as e:
                log(f"Error in watch cycle: {e}")

            # Periodic cleanup and recovery
            if time.time() - last_cleanup > CLEANUP_INTERVAL:
                try:
                    cleanup_done_files()
                    recover_stuck_failed_tasks()
                    recover_completed_md_files()
                    recover_stale_executions()
                    # NEW: Neo4j/disk drift cleanup
                    cleanup_completed_task_files()
                    cleanup_orphan_task_files()
                    release_stale_claims()
                    # NEW: Orphan process cleanup (kills untracked claude-agent processes)
                    cleanup_orphan_processes()
                except Exception as e:
                    log(f"Cleanup/recovery error: {e}")
                # Neo4j/filesystem state reconciliation (every cleanup cycle)
                try:
                    _neo4j_reconcile()
                except Exception as e:
                    log(f"Neo4j reconcile error (non-fatal): {e}")
                # Queue redistribution check
                try:
                    _check_queue_redistribution()
                except Exception as e:
                    log(f"Queue redistribution check error (non-fatal): {e}")
                last_cleanup = time.time()

            # Gate resolution is handled by cron job (completion-gate-resolver)
            # Removed dual-trigger to prevent race conditions (fix-2026-03-08)
            # Cron runs every 5 minutes with proper file locking

            # Check for revision loops (runs every 10 min)
            try:
                loops_broken = detect_revision_loops()
                if loops_broken > 0:
                    log(f"[REVISION_LOOP] Broke {loops_broken} revision loop(s)")
            except Exception as e:
                log(f"Revision loop check error (non-fatal): {e}")

            # Sleep in small increments to respond to stop_event quickly
            for _ in range(poll_interval):
                if stop_event.is_set():
                    break
                time.sleep(1)

        # Wait for in-flight tasks to finish on shutdown
        with active_lock:
            pending_futures = list(active_executions.values())
        if pending_futures:
            log(f"Waiting for {len(pending_futures)} in-flight task(s) to finish...")
            for fut in pending_futures:
                try:
                    fut.result(timeout=30)
                except Exception:
                    pass

    log("Task Watcher stopped")


def signal_handler(sig, frame):
    """Handle shutdown signals."""
    log(f"Received signal {sig}, shutting down...")
    stop_event.set()


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Watch for new tasks and execute immediately')
    parser.add_argument('--poll-interval', type=int, default=POLL_INTERVAL_DEFAULT,
                        help=f'Poll interval in seconds (default: {POLL_INTERVAL_DEFAULT})')
    parser.add_argument('--daemon', action='store_true', help='Run as daemon')
    parser.add_argument('--once', action='store_true', help='Run single cycle and exit')
    args = parser.parse_args()

    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if args.once:
        # Single cycle mode — still uses thread pool but waits for completion
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_AGENTS) as executor:
            dispatched = watch_cycle(executor)
            # Wait for all dispatched tasks
            with active_lock:
                futures = list(active_executions.values())
            for fut in futures:
                try:
                    fut.result(timeout=TIMEOUT_DEFAULT + 30)
                except Exception:
                    pass
            print(f"\nDispatched {dispatched} tasks")
        sys.exit(0)

    # Daemon / interactive mode — acquire exclusive lock first
    lock_fd = _acquire_daemon_lock()
    if lock_fd is None:
        sys.exit(1)
    try:
        daemon_loop(args.poll_interval)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()


if __name__ == "__main__":
    main()
