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

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")

try:
    with open(SPAWN_QUEUE, 'r') as f:
        data = json.load(f)
except:
    log("Error reading queue")
    exit(0)

spawns = data.get('spawns', [])
if not spawns:
    log("Queue is empty")
    exit(0)

log(f"Found {len(spawns)} spawn(s) to process")

# Output spawn commands for each ready spawn
for s in spawns:
    if s.get('status') == 'ready':
        agent = s.get('agent', 'unknown')
        task = s.get('task', '')
        model = s.get('model', 'qwen3.5-plus')
        label = s.get('label', 'unknown')
        
        log(f"SPAWN: {agent} ({model}) - {label}")
        print(f"SPAWN_CMD|{agent}|{model}|{label}|{task}")
        
        # Mark as processing
        s['status'] = 'processing'

# Save updated queue
with open(SPAWN_QUEUE, 'w') as f:
    json.dump({'spawns': spawns, 'updated': datetime.now().timestamp()}, f, indent=2)

log(f"Processed {sum(1 for s in spawns if s.get('status') == 'processing')} spawns")
PYTHON_SCRIPT

log "=== Cycle Complete ==="
