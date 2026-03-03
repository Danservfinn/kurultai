#!/bin/bash
# Spawn Consumer - Reads spawn requests and executes them via OpenClaw
# Run every 2 minutes via cron

SPAWN_QUEUE="/Users/kublai/.openclaw/agents/main/logs/spawn-queue.jsonl"
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

# Process each line in the queue
while IFS= read -r line; do
    if [ -z "$line" ]; then
        continue
    fi
    
    # Parse JSON fields
    agent=$(echo "$line" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('agent',''))" 2>/dev/null)
    task=$(echo "$line" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('task',''))" 2>/dev/null)
    model=$(echo "$line" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('model','qwen3.5-plus'))" 2>/dev/null)
    label=$(echo "$line" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('label',''))" 2>/dev/null)
    
    if [ -z "$agent" ] || [ -z "$task" ]; then
        log "Invalid spawn request: $line"
        continue
    fi
    
    log "Spawning $agent (model: $model) for: $task"
    
    # Create a temporary script that calls sessions_spawn
    # This will be picked up by the OpenClaw session
    SPawn_file="/Users/kublai/.openclaw/agents/main/spawn-requests/${label}.md"
    mkdir -p "$(dirname "$SPawn_file")"
    
    cat > "$SPawn_file" << EOF
---
agent: $agent
model: $model
label: $label
created: $(date)
status: pending
---

# Spawn Request

**Agent:** $agent  
**Model:** $model  
**Task:** $task

EOF
    
    log "Spawn request written to: $SPawn_file"
    
done < "$SPAWN_QUEUE"

# Clear the queue after processing
> "$SPAWN_QUEUE"

log "=== Cycle Complete ==="
