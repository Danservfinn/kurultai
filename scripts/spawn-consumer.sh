#!/bin/bash
# Spawn Consumer - Reads spawn requests and executes them via OpenClaw
# Run every 2 minutes via cron

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

import os
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

# Process ready spawns (continuous tasks are in separate registry)
ready = [s for s in spawns if s.get('status') == 'ready']
activity_detected = False

if ready:
    log(f"Found {len(ready)} ready spawn(s)")
    activity_detected = True

for s in ready:
    agent = s.get('agent', 'unknown')
    task = s.get('task', '')
    model = s.get('model', 'qwen3.5-plus')
    label = s.get('label', 'unknown')
    mode = s.get('mode', 'run')
    retry_count = s.get('retry_count', 0)
    
    # Check if this is a novel execution (first time or different from last)
    is_novel = True  # Default to novel for now
    
    log(f"SPAWN: {agent} ({model}, {mode}) - {label}")
    print(f"SPAWN_CMD|{agent}|{model}|{label}|{task}|{mode}|{is_novel}")
    
    # Mark as running
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
