#!/bin/bash
# Spawn Executor - Reads pending spawn requests and executes sessions_spawn
# Run every 2 minutes via cron
# This script outputs spawn commands for Kublai to execute

SPAWN_DIR="/Users/kublai/.openclaw/agents/main/spawn-requests"
LOG_FILE="/Users/kublai/.openclaw/agents/main/logs/spawn-executor.log"

mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=== Spawn Executor Cycle ==="

if [ ! -d "$SPAWN_DIR" ]; then
    log "No spawn requests directory found"
    exit 0
fi

# Find pending spawn requests
shopt -s nullglob
pending=("$SPAWN_DIR"/*.md)

if [ ${#pending[@]} -eq 0 ]; then
    log "No pending spawn requests"
    exit 0
fi

log "Found ${#pending[@]} pending spawn request(s)"

for request_file in "${pending[@]}"; do
    # Skip if already processed
    if [[ "$request_file" == *.processed.md ]] || [[ "$request_file" == *.executing.md ]]; then
        continue
    fi
    
    # Parse YAML frontmatter
    agent=$(grep "^agent:" "$request_file" | cut -d: -f2 | tr -d ' ')
    model=$(grep "^model:" "$request_file" | cut -d: -d: -f2 | tr -d ' ')
    label=$(grep "^label:" "$request_file" | cut -d: -f2 | tr -d ' ')
    task=$(grep "^# Task:" "$request_file" | sed 's/^# Task: //')
    
    if [ -z "$agent" ] || [ -z "$task" ]; then
        log "Invalid request file: $request_file"
        continue
    fi
    
    log "Spawning: $agent ($model) - $task"
    
    # Mark as executing
    mv "$request_file" "${request_file%.md}.executing.md"
    
    # Output the spawn command for Kublai to execute
    # This gets picked up by the cron job which calls sessions_spawn
    echo "SPAWN_REQUEST:agent=$agent,model=$model,label=$label,task=$task"
    
done

log "=== Cycle Complete ==="
