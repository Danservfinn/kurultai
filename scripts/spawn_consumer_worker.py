#!/usr/bin/env python3
"""
spawn_consumer_worker.py — Process spawn requests from the spawn queue.

Extracted from spawn-consumer.sh to eliminate /tmp script execution
and add input sanitization + agent name validation.

Called by spawn-consumer.sh every 2 minutes via cron.
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from json_state import locked_json_read, locked_json_update

SPAWN_QUEUE = "/Users/kublai/.openclaw/agents/main/logs/spawn-pending.json"
LOG_FILE = "/Users/kublai/.openclaw/agents/main/logs/spawn-consumer.log"
DEAD_LETTER = "/Users/kublai/.openclaw/agents/main/logs/spawn-dead-letter.json"

# Agent name allowlist — reject anything not in this set
VALID_AGENTS = {"kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei", "subagent"}


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def sanitize_text(text):
    """Remove potentially dangerous characters from task text."""
    if not isinstance(text, str):
        return ""
    # Strip shell metacharacters and control chars
    text = re.sub(r'[\x00-\x1f\x7f]', '', text)
    # Limit length
    return text[:2000]


def validate_agent(agent_name):
    """Validate agent name against allowlist."""
    return agent_name in VALID_AGENTS


def add_to_dead_letter(spawn):
    os.makedirs(os.path.dirname(DEAD_LETTER), exist_ok=True)
    dead = []
    if os.path.exists(DEAD_LETTER):
        try:
            with open(DEAD_LETTER, 'r') as f:
                dead = json.load(f).get('failed', [])
        except Exception:
            pass
    spawn['failed_at'] = datetime.now().isoformat()
    dead.append(spawn)
    with open(DEAD_LETTER, 'w') as f:
        json.dump({'failed': dead, 'updated': datetime.now().timestamp()}, f, indent=2)
    log(f"  -> Dead letter: {spawn.get('label')} (retries exhausted)")


def check_subagent_status(session_key):
    """Check if a subagent is still running."""
    if not session_key:
        return 'unknown'

    # Sanitize session_key to prevent injection
    if not re.match(r'^[\w\-\.]+$', session_key):
        return 'unknown'

    try:
        check_script = os.path.join(os.path.dirname(__file__), '_check_subagent.py')
        # Use a dedicated script instead of inline code
        result = subprocess.run(
            ['python3', '-c', f'''
import sys
sys.path.insert(0, "/opt/homebrew/lib/node_modules/openclaw")
try:
    from openclaw.tools import subagents
    result = subagents(action="list", recentMinutes=60)
    import json
    recent = result.get("recent", [])
    session_key = {json.dumps(session_key)}
    for r in recent:
        if r.get("sessionKey") == session_key:
            print(r.get("status", "unknown"))
            break
    else:
        print("not_found")
except Exception as e:
    print("error")
'''],
            capture_output=True,
            text=True,
            timeout=10
        )

        status = result.stdout.strip()
        if status in ('not_found', 'done'):
            return 'completed'
        elif status in ('failed', 'error'):
            return 'failed'
        elif status == 'running':
            return 'running'
        return 'unknown'
    except Exception as e:
        log(f"Error checking session: {e}")
        return 'unknown'


def process_queue():
    """Main queue processing logic."""
    report_only = os.getenv('REPORT_ONLY_ON_ACTIVITY', 'true') == 'true'

    data = locked_json_read(SPAWN_QUEUE, default={'spawns': []})
    spawns = data.get('spawns', [])
    if not spawns:
        if not report_only:
            log("Queue is empty")
        return

    activity_detected = False
    cutoff = datetime.now() - timedelta(minutes=30)

    # Check status of running tasks
    for s in spawns:
        if s.get('status') != 'running':
            continue
        session_key = s.get('session_key')
        label = s.get('label', 'unknown')

        if session_key:
            actual_status = check_subagent_status(session_key)
            if actual_status == 'completed':
                s['status'] = 'completed'
                s['completed_at'] = datetime.now().isoformat()
                log(f"COMPLETE: {label} (subagent done)")
                activity_detected = True
            elif actual_status == 'failed':
                s['status'] = 'failed'
                s['completed_at'] = datetime.now().isoformat()
                log(f"FAILED: {label} (subagent failed)")
                activity_detected = True
        elif not s.get('continuous'):
            last_spawned = s.get('last_spawned')
            if last_spawned:
                try:
                    spawn_time = datetime.fromisoformat(last_spawned)
                    if spawn_time < cutoff:
                        s['status'] = 'completed'
                        s['completed_at'] = datetime.now().isoformat()
                        log(f"CLEANUP: {label} marked completed (timeout)")
                        activity_detected = True
                except Exception:
                    pass

    # Process ready spawns
    ready = [s for s in spawns if s.get('status') == 'ready']

    if ready:
        log(f"Found {len(ready)} ready spawn(s)")
        activity_detected = True

    for s in ready:
        task_text = sanitize_text(s.get('task', ''))
        label = s.get('label', 'unknown')
        priority = s.get('priority', 'normal')
        source = s.get('source', 'unknown')
        agent = s.get('agent', 'subagent')

        # Validate agent name
        if not validate_agent(agent):
            log(f"REJECT: invalid agent name '{agent}' for {label}")
            s['status'] = 'failed'
            s['error'] = f"Invalid agent name: {agent}"
            continue

        if source == "agent_execution":
            model = s.get('model', 'qwen3.5-plus')
            log(f"Launching OpenClaw execution for {label} ({agent} using {model})")

            try:
                cmd = ["/opt/homebrew/bin/openclaw", "agent", "--agent", agent, "--message", task_text, "--thinking", "high"]
                env = os.environ.copy()
                env["PATH"] = "/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
                env["NODE_PATH"] = "/opt/homebrew/lib/node_modules"
                env["OPENCLAW_STATE_DIR"] = "/Users/kublai/.openclaw"
                with open(LOG_FILE, "a") as logfile:
                    subprocess.Popen(cmd, stdout=logfile, stderr=subprocess.STDOUT,
                                     cwd="/Users/kublai/.openclaw/agents/main", env=env)
                log(f"  -> PID launched for {label}")
            except Exception as e:
                log(f"Failed to launch openclaw: {e}")
                s['status'] = 'failed'
                s['error'] = str(e)
                continue

            s['status'] = 'running'
            s['last_spawned'] = datetime.now().isoformat()
            activity_detected = True
        else:
            # Use smart router to classify and route
            try:
                from task_router import classify_task, route_to_agent, route_to_subagent

                classification = classify_task(task_text)
                destination = classification['destination']

                log(f"ROUTING: {label} -> {destination} ({classification['complexity']})")

                if destination == 'subagent':
                    model = s.get('model', 'qwen3.5-plus')
                    log(f"SPAWN: subagent - {label}")
                    print(f"SPAWN_CMD|{agent}|{model}|{label}|{task_text[:500]}|run")
                    s['status'] = 'running'
                    s['last_spawned'] = datetime.now().isoformat()
                    activity_detected = True
                else:
                    route_result = route_to_agent(destination, task_text, priority)
                    if route_result.get('success'):
                        log(f"Routed to {destination}: {route_result.get('task_file')}")
                        s['status'] = 'routed'
                        s['routed_to'] = destination
                        s['routed_at'] = datetime.now().isoformat()
                        activity_detected = True
                    else:
                        log(f"Routing failed: {route_result.get('error')}")
                        s['status'] = 'failed'
                        s['error'] = route_result.get('error')

            except Exception as e:
                log(f"Routing error: {e}")
                model = s.get('model', 'qwen3.5-plus')
                log(f"FALLBACK: {label} -> subagent")
                print(f"SPAWN_CMD|{agent}|{model}|{label}|{task_text[:500]}|run")
                s['status'] = 'running'
                s['last_spawned'] = datetime.now().isoformat()
                activity_detected = True

    # Handle failed spawns (retry logic)
    failed = [s for s in spawns if s.get('status') == 'failed']
    retries_count = 0

    for s in list(failed):
        retry_count = s.get('retry_count', 0)
        max_retries = s.get('max_retries', 3)
        label = s.get('label', 'unknown')

        if retry_count < max_retries:
            s['retry_count'] = retry_count + 1
            s['status'] = 'ready'
            s['last_retry'] = datetime.now().isoformat()
            s['error'] = f"Retry {retry_count + 1}/{max_retries}"
            log(f"RETRY: {label} (attempt {retry_count + 1}/{max_retries})")
            activity_detected = True
            retries_count += 1
        else:
            add_to_dead_letter(s)
            spawns.remove(s)
            log(f"FAILED: {label} (max retries exceeded)")
            activity_detected = True

    # Cleanup: keep only running/ready
    spawns = [s for s in spawns if s.get('status') in ['ready', 'running']]

    # Move continuous tasks to registry
    continuous_tasks = [s for s in spawns if s.get('continuous') and s.get('status') == 'running']
    if continuous_tasks:
        try:
            registry_file = "/Users/kublai/.openclaw/agents/main/logs/continuous-tasks.json"
            registry_data = {'tasks': []}
            if os.path.exists(registry_file):
                with open(registry_file, 'r') as f:
                    registry_data = json.load(f)

            for ct in continuous_tasks:
                existing = [t for t in registry_data['tasks'] if t.get('label') == ct.get('label')]
                if not existing:
                    registry_data['tasks'].append({
                        'label': ct.get('label'),
                        'agent': ct.get('agent'),
                        'task': ct.get('task'),
                        'session_key': ct.get('session_key'),
                        'status': 'running',
                        'started': ct.get('last_spawned'),
                        'continuous': True
                    })
                    log(f"MOVED: {ct.get('label')} to continuous registry")
                    activity_detected = True

            with open(registry_file, 'w') as f:
                json.dump(registry_data, f, indent=2)

            spawns = [s for s in spawns if not (s.get('continuous') and s.get('status') == 'running')]
        except Exception as e:
            log(f"Error moving to continuous registry: {e}")

    # Save updated queue with locking
    with locked_json_update(SPAWN_QUEUE) as queue_data:
        queue_data['spawns'] = spawns
        queue_data['updated'] = datetime.now().timestamp()

    if activity_detected:
        log(f"=== Spawn Consumer Cycle ===")
        log(f"PROCESSED: {len(ready)} spawns, {retries_count} retries, {len(spawns)} remaining")
        log(f"=== Cycle Complete ===")
    elif not report_only:
        log(f"Cycle complete: {len(ready)} spawns, {retries_count} retries, {len(spawns)} remaining")


if __name__ == "__main__":
    process_queue()
