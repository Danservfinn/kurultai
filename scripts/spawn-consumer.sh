#!/bin/bash
# Spawn Consumer - Reads spawn requests and executes them via OpenClaw
# Run every 2 minutes via cron

# Set up PATH for cron environment
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export NODE_PATH="/opt/homebrew/lib/node_modules"

SPAWN_QUEUE="/Users/kublai/.openclaw/agents/main/logs/spawn-pending.json"
LOG_FILE="/Users/kublai/.openclaw/agents/main/logs/spawn-consumer.log"

mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Silent mode: Only report when something meaningful happens
# Set REPORT_ONLY_ON_ACTIVITY=true to suppress empty cycle reports
export REPORT_ONLY_ON_ACTIVITY="${REPORT_ONLY_ON_ACTIVITY:-true}"

# Only log header if not in silent mode or if there's activity
if [ "$REPORT_ONLY_ON_ACTIVITY" != "true" ]; then
    log "=== Spawn Consumer Cycle ==="
fi

if [ ! -f "$SPAWN_QUEUE" ]; then
    if [ "$REPORT_ONLY_ON_ACTIVITY" != "true" ]; then
        log "No spawn queue found"
    fi
    exit 0
fi

# Write python script to a file
cat > /tmp/spawn_consumer_python.py << 'PYTHON_SCRIPT'
import json
import os
from datetime import datetime
import subprocess

SPAWN_QUEUE = "/Users/kublai/.openclaw/agents/main/logs/spawn-pending.json"
LOG_FILE = "/Users/kublai/.openclaw/agents/main/logs/spawn-consumer.log"
DEAD_LETTER = "/Users/kublai/.openclaw/agents/main/logs/spawn-dead-letter.json"

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")

def save_queue(data):
    with open(SPAWN_QUEUE, 'w') as f:
        json.dump(data, f, indent=2)

def add_to_dead_letter(spawn):
    os.makedirs(os.path.dirname(DEAD_LETTER), exist_ok=True)
    dead = []
    if os.path.exists(DEAD_LETTER):
        try:
            with open(DEAD_LETTER, 'r') as f:
                dead = json.load(f).get('failed', [])
        except:
            pass
    spawn['failed_at'] = datetime.now().isoformat()
    dead.append(spawn)
    with open(DEAD_LETTER, 'w') as f:
        json.dump({'failed': dead, 'updated': datetime.now().timestamp()}, f, indent=2)
    log(f"  → Dead letter: {spawn.get('label')} (retries exhausted)")

report_only = os.getenv('REPORT_ONLY_ON_ACTIVITY', 'true') == 'true'

try:
    with open(SPAWN_QUEUE, 'r') as f:
        data = json.load(f)
except Exception as e:
    log(f"Error reading queue: {e}")
    exit(0)

spawns = data.get('spawns', [])
if not spawns:
    if not report_only:
        log("Queue is empty")
    exit(0)

# Check subagent status via OpenClaw subagents tool
def check_subagent_status(session_key):
    """Check if a subagent is still running"""
    if not session_key:
        return 'unknown'
    
    try:
        result = subprocess.run(
            ['python3', '-c', '''
import sys
sys.path.insert(0, "/opt/homebrew/lib/node_modules/openclaw")
try:
    from openclaw.tools import subagents
    result = subagents(action="list", recentMinutes=60)
    import json
    recent = result.get("recent", [])
    for r in recent:
        if r.get("sessionKey") == "''' + session_key + '''":
            print(r.get("status", "unknown"))
            break
    else:
        print("not_found")
except Exception as e:
    print("error:" + str(e))
'''],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        status = result.stdout.strip()
        if status == 'not_found' or status == 'done':
            return 'completed'
        elif status in ['failed', 'error']:
            return 'failed'
        elif status == 'running':
            return 'running'
        else:
            return 'unknown'
    except Exception as e:
        log(f"Error checking session: {e}")
        return 'unknown'

# Check status of running tasks and update completed ones
from datetime import timedelta
cutoff = datetime.now() - timedelta(minutes=30)

for s in spawns:
    if s.get('status') == 'running':
        session_key = s.get('session_key')
        label = s.get('label', 'unknown')
        
        # Check actual subagent status if we have session_key
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
            # else: still running, keep as-is
        
        # Fallback: timeout-based cleanup for tasks without session tracking
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
                except:
                    pass

# Process ready spawns with smart routing
ready = [s for s in spawns if s.get('status') == 'ready']
activity_detected = False

if ready:
    log(f"Found {len(ready)} ready spawn(s)")
    activity_detected = True

for s in ready:
    task_text = s.get('task', '')
    label = s.get('label', 'unknown')
    priority = s.get('priority', 'normal')
    source = s.get('source', 'unknown')
    
    # Bypass smart router for execution tasks that are already designated
    if source == "agent_execution":
        agent = s.get('agent', 'subagent')
        model = s.get('model', 'qwen3.5-plus')
        mode = s.get('mode', 'run')
        log(f"🚀 Launching OpenClaw execution for {label} ({agent} using {model})")
        
        # Execute directly via subprocess
        try:
            cmd = ["/opt/homebrew/bin/openclaw", "execute", task_text, f"--agent={agent}", f"--model={model}", f"--label={label}"]
            with open(LOG_FILE, "a") as logfile:
                subprocess.Popen(cmd, stdout=logfile, stderr=subprocess.STDOUT)
        except Exception as e:
            log(f"Failed to launch openclaw: {e}")
            
        s['status'] = 'running'
        s['last_spawned'] = datetime.now().isoformat()
        activity_detected = True
    else:
        # Use smart router to classify and route
        try:
            # Import smart router classification
            import sys
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from task_router import classify_task, route_to_agent, route_to_subagent
            
            classification = classify_task(task_text)
            destination = classification['destination']
            
            log(f"ROUTING: {label} → {destination} ({classification['complexity']})")
            
            if destination == 'subagent':
                # Direct subagent spawn (simple tasks)
                agent = s.get('agent', 'subagent')
                model = s.get('model', 'qwen3.5-plus')
                mode = s.get('mode', 'run')
                
                log(f"SPAWN: subagent - {label}")
                print(f"SPAWN_CMD|{agent}|{model}|{label}|{task_text}|{mode}")
                s['status'] = 'running'
                s['last_spawned'] = datetime.now().isoformat()
                activity_detected = True
            else:
                # Route to full agent queue
                route_result = route_to_agent(destination, task_text, priority)
                if route_result.get('success'):
                    log(f"✓ Routed to {destination}: {route_result.get('task_file')}")
                    s['status'] = 'routed'
                    s['routed_to'] = destination
                    s['routed_at'] = datetime.now().isoformat()
                    activity_detected = True
                else:
                    log(f"✗ Routing failed: {route_result.get('error')}")
                    s['status'] = 'failed'
                    s['error'] = route_result.get('error')
            
        except Exception as e:
            log(f"✗ Routing error: {e}")
            # Fallback to direct subagent spawn
            agent = s.get('agent', 'subagent')
            model = s.get('model', 'qwen3.5-plus')
            mode = s.get('mode', 'run')
            log(f"FALLBACK: {label} → subagent")
            print(f"SPAWN_CMD|{agent}|{model}|{label}|{task_text}|{mode}")
            s['status'] = 'running'
            s['last_spawned'] = datetime.now().isoformat()
            activity_detected = True

# Handle failed spawns (retry logic)
failed = [s for s in spawns if s.get('status') == 'failed']
retries_count = 0

for s in failed:
    retry_count = s.get('retry_count', 0)
    max_retries = s.get('max_retries', 3)
    label = s.get('label', 'unknown')
    
    if retry_count < max_retries:
        # Retry
        s['retry_count'] = retry_count + 1
        s['status'] = 'ready'
        s['last_retry'] = datetime.now().isoformat()
        s['error'] = f"Retry {retry_count + 1}/{max_retries}"
        log(f"RETRY: {label} (attempt {retry_count + 1}/{max_retries})")
        activity_detected = True
        retries_count += 1
    else:
        # Dead letter
        add_to_dead_letter(s)
        spawns.remove(s)
        log(f"FAILED: {label} (max retries exceeded)")
        activity_detected = True

# Immediate cleanup of completed/failed tasks (keep only running/ready)
spawns = [s for s in spawns if s.get('status') in ['ready', 'running']]

# Move continuous tasks to separate registry
continuous_tasks = [s for s in spawns if s.get('continuous') and s.get('status') == 'running']
if continuous_tasks:
    try:
        registry_file = "/Users/kublai/.openclaw/agents/main/logs/continuous-tasks.json"
        registry_data = {'tasks': []}
        if os.path.exists(registry_file):
            with open(registry_file, 'r') as f:
                registry_data = json.load(f)
        
        for ct in continuous_tasks:
            # Check if already in registry
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
        
        # Remove continuous tasks from main queue
        spawns = [s for s in spawns if not (s.get('continuous') and s.get('status') == 'running')]
    except Exception as e:
        log(f"Error moving to continuous registry: {e}")

# Save updated queue
save_queue({'spawns': spawns, 'updated': datetime.now().timestamp()})

# Only report if there was meaningful activity
if activity_detected:
    log(f"=== Spawn Consumer Cycle ===")
    log(f"PROCESSED: {len(ready)} spawns, {retries_count} retries, {len(spawns)} remaining")
    log(f"=== Cycle Complete ===")
elif not report_only:
    log(f"Cycle complete: {len(ready)} spawns, {retries_count} retries, {len(spawns)} remaining")
PYTHON_SCRIPT
python3 /tmp/spawn_consumer_python.py