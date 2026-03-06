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
from pathlib import Path
from datetime import datetime, timedelta
from threading import Thread, Event, Lock
from concurrent.futures import ThreadPoolExecutor, Future

sys.path.insert(0, str(Path(__file__).parent))
from json_state import locked_json_read, locked_json_update

# Force unbuffered output for launchd (stdout goes to file)
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Configuration
AGENTS_DIR = Path("/Users/kublai/.openclaw/agents")
STATE_FILE = Path("/Users/kublai/.openclaw/agents/main/logs/task-watcher-state.json")
SPAWN_QUEUE = Path("/Users/kublai/.openclaw/agents/main/logs/spawn-pending.json")
TASK_LEDGER = Path("/Users/kublai/.openclaw/tasks/task-ledger.jsonl")
CLAUDE_AGENT = "/Users/kublai/.local/bin/claude-agent"
POLL_INTERVAL_DEFAULT = 15  # seconds
TIMEOUT_DEFAULT = 600  # 10 minutes for Claude Code execution
CLEANUP_INTERVAL = 300  # Run cleanup every 5 minutes (aligned with tick heartbeat)
DONE_FILE_MAX_AGE = 48 * 3600  # 48 hours in seconds
MAX_CONCURRENT_AGENTS = 6  # One slot per agent
VALID_AGENTS = {"kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei", "subagent"}
SPAWN_TIMEOUT_MINUTES = 30  # Mark running spawns as completed after this
STALE_EXECUTING_AGE = TIMEOUT_DEFAULT + 120  # 12 minutes: mark .executing files as failed after this
MAX_RETRY_COUNT = 2  # After this many retries, mark as .failed.done permanently

# Notification config
SEND_SIGNAL_SCRIPT = Path.home() / ".claude" / "skills" / "agent-collaboration" / "scripts" / "send_signal.sh"
NOTIFY_ON_COMPLETE = True  # Send Signal + webapp notification when tasks finish

# Global state for daemon mode
stop_event = Event()
print_lock = Lock()

# Track which agents currently have a task executing
# Maps agent_name -> Future
active_executions: dict[str, Future] = {}
active_lock = Lock()


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


def _append_ledger(entry):
    """Append an event to the unified task-ledger.jsonl."""
    try:
        TASK_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with open(TASK_LEDGER, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


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
        # Skip completed/executing tasks
        if any(x in f.name for x in ['.executing', '.completed', '.done']):
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


# Sources that are heartbeat/automated — silent unless errors
_HEARTBEAT_SOURCES = {"kublai-actions", "agent-self-wake", "agent-self-wake (rule t7)"}
# Sources that always notify on completion (kurultai results)
_KURULTAI_SOURCES = {"hourly-reflection", "kublai-reflection"}


def _notify_completion(agent, task_label, success, elapsed_s, source=""):
    """Send task completion notification via Signal and webapp.

    Notification rules:
    - Errors/failures: always notify
    - Heartbeat tasks (kublai-actions, self-wake): silent unless error
    - Kurultai reflections: always notify
    - User-initiated tasks (gateway-router, direct): always notify
    """
    source_lower = source.lower()

    if success and source_lower in _HEARTBEAT_SOURCES:
        return  # Heartbeat success — silent

    if success:
        msg = f"[OK] {agent}: {task_label} — completed ({elapsed_s}s)"
    else:
        msg = f"[ALERT] {agent}: {task_label} — FAILED ({elapsed_s}s)"

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


def execute_task(task_file, agent, task_key, timeout):
    """Execute a single task file via agent-task-handler.py.

    Runs in a thread pool worker. Updates state on completion.
    """
    task_id = _extract_task_id(task_file)
    start_time = time.time()

    # Emit EXECUTING event
    if task_id:
        _append_ledger({
            "task_id": task_id,
            "event": "EXECUTING",
            "ts": datetime.now().isoformat(),
            "agent": agent,
            "task_file": str(task_file),
        })

    cmd = [
        "python3",
        str(Path(__file__).parent / "agent-task-handler.py"),
        "--agent", agent,
        "--task-file", str(task_file),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(task_file.parent.parent.parent),
        )
        success = result.returncode == 0
        output = result.stdout[:1000] if success else (result.stderr[:1000] or result.stdout[:1000])

    except subprocess.TimeoutExpired:
        success = False
        output = f"Task timed out after {timeout}s"
    except Exception as e:
        success = False
        output = f"Execution error: {e}"

    elapsed_s = round(time.time() - start_time, 1)
    status = "✓" if success else "✗"
    log(f"  {status} {task_key}: {'Completed' if success else 'Failed'} ({elapsed_s}s)")

    # Emit COMPLETED/FAILED event
    if task_id:
        _append_ledger({
            "task_id": task_id,
            "event": "COMPLETED" if success else "FAILED",
            "ts": datetime.now().isoformat(),
            "agent": agent,
            "execution_time_s": elapsed_s,
            "output_lines": len(output.splitlines()) if output else 0,
            "error": output[:500] if not success else None,
        })

    # Notify owner
    if NOTIFY_ON_COMPLETE:
        task_label = _extract_task_label(task_file)
        task_source = _extract_task_source(task_file)
        _notify_completion(agent, task_label, success, elapsed_s, source=task_source)

    # Update state (thread-safe)
    update_state_entry(task_key, datetime.now().isoformat(), success)

    # Clear the active execution slot for this agent
    with active_lock:
        active_executions.pop(agent, None)

    return success, output


def is_new_task(task_file, agent, state):
    """Check if a task file is genuinely new (not already executed)."""
    key = f"{agent}/{task_file.name}"
    if key not in state:
        return True
    # Check if file was modified after execution (re-queued)
    try:
        exec_time = datetime.fromisoformat(state[key]['executed'])
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


def route_spawn_to_queue(agent, task_text, priority, label):
    """Route a spawn request by creating a task file in the agent's queue.

    The task file will be picked up by the next watch_cycle iteration
    (within seconds), achieving near-instant spawning.
    """
    tasks_dir = AGENTS_DIR / agent / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    safe_label = re.sub(r'[^\w\-]', '_', label)[:60]
    filename = f"{priority}-spawn-{safe_label}-{int(time.time())}.md"
    task_path = tasks_dir / filename

    content = (
        f"# Task: {label}\n\n"
        f"Source: spawn-queue (routed by task-watcher)\n"
        f"Priority: {priority}\n\n"
        f"---\n\n"
        f"{task_text}\n"
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

        # Skip if this agent already has a task running
        with active_lock:
            if agent in active_executions:
                fut = active_executions[agent]
                if not fut.done():
                    continue
                # Future completed but wasn't cleaned up yet
                active_executions.pop(agent, None)

        pending = list_pending_tasks(agent_dir)
        new_tasks = [f for f in pending if is_new_task(f, agent, state)]

        if not new_tasks:
            continue

        # Dispatch the highest-priority new task
        task_file = new_tasks[0]
        task_key = f"{agent}/{task_file.name}"

        log(f"NEW TASK: {task_key}")

        # Submit to thread pool (non-blocking)
        future = executor.submit(
            execute_task, task_file, agent, task_key, TIMEOUT_DEFAULT
        )
        with active_lock:
            active_executions[agent] = future

        dispatched += 1

    return dispatched


def cleanup_done_files():
    """Remove .done task files older than 48 hours."""
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
                if age > DONE_FILE_MAX_AGE:
                    f.unlink()
                    removed += 1
            except OSError:
                continue
    if removed > 0:
        log(f"Cleaned up {removed} done task file(s)")
    return removed


def recover_stale_executions():
    """Recover tasks stuck in .executing state (orphaned by SIGTERM/crash).

    If an .executing file is older than STALE_EXECUTING_AGE, the child process
    that was working on it is almost certainly dead. Rename it back to .md so
    the next watch_cycle retries it, or mark it failed if it's been retried
    too many times.
    """
    now = time.time()
    recovered = 0
    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir() or agent_dir.name == 'main':
            continue
        tasks_dir = agent_dir / "tasks"
        if not tasks_dir.exists():
            continue
        for f in tasks_dir.iterdir():
            if '.executing' not in f.name:
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

            # Count retries from filename (total .retry-N suffixes)
            retry_count = len(re.findall(r'\.retry-\d+', f.name))

            if retry_count >= MAX_RETRY_COUNT:
                # Permanently fail — stop retrying
                failed_path = f.parent / f.name.replace('.executing', '.failed.done')
                try:
                    os.rename(f, failed_path)
                    task_id = _extract_task_id(failed_path)
                    log(f"RECOVER: {agent}/{f.name} → failed.done (max retries reached)")
                    if task_id:
                        _append_ledger({
                            "task_id": task_id,
                            "event": "FAILED",
                            "ts": datetime.now().isoformat(),
                            "agent": agent,
                            "error": f"Max retries ({MAX_RETRY_COUNT}) exceeded, stale_age={round(age)}s",
                        })
                except OSError:
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
                    try:
                        os.rename(f, failed_path)
                        log(f"RECOVER: {agent}/{f.name} → orphan-failed (original re-created)")
                    except OSError:
                        continue
                else:
                    try:
                        os.rename(f, original_path)
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
                    except OSError:
                        continue

            recovered += 1

    if recovered > 0:
        log(f"Recovered {recovered} stale executing task(s)")
    return recovered


def daemon_loop(poll_interval):
    """Main daemon loop with concurrent execution."""
    log(f"Task Watcher starting (poll interval: {poll_interval}s, max concurrent: {MAX_CONCURRENT_AGENTS})")
    log(f"Watching: {AGENTS_DIR}")
    log(f"State file: {STATE_FILE}")

    last_cleanup = 0

    # Recover any stale .executing files on startup
    try:
        recover_stale_executions()
    except Exception as e:
        log(f"Startup recovery error: {e}")

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_AGENTS) as executor:
        while not stop_event.is_set():
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
                    recover_stale_executions()
                except Exception as e:
                    log(f"Cleanup/recovery error: {e}")
                last_cleanup = time.time()

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

    # Daemon / interactive mode
    daemon_loop(args.poll_interval)


if __name__ == "__main__":
    main()
