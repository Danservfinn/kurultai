#!/bin/bash
# Spawn Consumer - Reads spawn requests and executes them via OpenClaw
# Run every 2 minutes via cron

SPAWN_QUEUE="/Users/kublai/.openclaw/agents/main/logs/spawn-pending.json"
LOG_FILE="/Users/kublai/.openclaw/agents/main/logs/spawn-consumer.log"

mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=== Spawn Consumer Cycle ==="

if [ ! -f "$SPAWN_QUEUE" ]; then
    log "No spawn queue found"
    exit 0
fi

# Read JSON and process spawns
python3 << 'PYTHON_SCRIPT'
import json
import os
from datetime import datetime

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

try:
    with open(SPAWN_QUEUE, 'r') as f:
        data = json.load(f)
except Exception as e:
    log(f"Error reading queue: {e}")
    exit(0)

spawns = data.get('spawns', [])
if not spawns:
    log("Queue is empty")
    exit(0)

# Process ready spawns
ready = [s for s in spawns if s.get('status') == 'ready']
log(f"Found {len(ready)} ready spawn(s)")

for s in ready:
    agent = s.get('agent', 'unknown')
    task = s.get('task', '')
    model = s.get('model', 'qwen3.5-plus')
    label = s.get('label', 'unknown')
    mode = s.get('mode', 'run')
    continuous = s.get('continuous', False)
    retry_count = s.get('retry_count', 0)
    
    # Check if continuous task already running
    if continuous and s.get('session_key'):
        log(f"SKIP: {label} (continuous task already running)")
        continue
    
    log(f"SPAWN: {agent} ({model}, {mode}) - {label}")
    print(f"SPAWN_CMD|{agent}|{model}|{label}|{task}|{mode}|{continuous}")
    
    # Mark as running
    s['status'] = 'running'
    s['last_spawned'] = datetime.now().isoformat()

# Handle failed spawns (retry logic)
failed = [s for s in spawns if s.get('status') == 'failed']
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
    else:
        # Dead letter
        add_to_dead_letter(s)
        spawns.remove(s)
        log(f"FAILED: {label} (max retries exceeded)")

# Cleanup completed spawns older than 1 hour
cutoff = datetime.now().timestamp() - 3600
spawns = [s for s in spawns if 
          s.get('status') not in ['completed', 'failed'] or
          s.get('completed_at') is None or
          datetime.fromisoformat(s.get('completed_at', '2000-01-01')).timestamp() > cutoff]

# Save updated queue
save_queue({'spawns': spawns, 'updated': datetime.now().timestamp()})

log(f"Processed {len(ready)} spawns, {len(failed)} retries, {len(spawns)} remaining in queue")
PYTHON_SCRIPT

log "=== Cycle Complete ==="
