#!/bin/bash
# Task Consumer: Executes tasks from all agent task queues
# Run via cron: */5 * * * * /Users/kublai/.openclaw/agents/main/scripts/task-consumer.sh
# Or run continuously: nohup task-consumer.sh &

set -e

AGENT_DIR="/Users/kublai/.openclaw/agents"
LOG_FILE="/Users/kublai/.openclaw/agents/main/logs/task-consumer.log"
POLL_INTERVAL=30

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Get model for agent
get_model() {
    local agent="$1"
    case $agent in
        temujin|mongke|chagatai|ogedei|kublai) echo "qwen3.5-plus" ;;
        jochi) echo "MiniMax-M2.5" ;;
        *) echo "qwen3.5-plus" ;;
    esac
}

# Extract task description from file
get_task_desc() {
    local task_file="$1"
    # Get content after "# Task:" until next "---"
    sed -n '/^# Task:/,/^---/p' "$task_file" | sed '1d;$d' | tr '\n' ' ' | sed 's/^ *//;s/ *$//'
}

# Process tasks for a single agent
process_agent() {
    local agent="$1"
    local task_dir="$AGENT_DIR/$agent/tasks"
    
    if [ ! -d "$task_dir" ]; then
        return
    fi
    
    # Find pending tasks (high-*, normal-*, low-*.md, not .done, not .executing)
    shopt -s nullglob
    local tasks=()
    for f in "$task_dir"/high-*.md "$task_dir"/normal-*.md "$task_dir"/low-*.md; do
        # Skip files that are .done or .executing
        if [[ "$f" != *.done.md ]] && [[ "$f" != *.executing.md ]]; then
            tasks+=("$f")
        fi
    done
    
    if [ ${#tasks[@]} -eq 0 ]; then
        return
    fi
    
    log "=== $agent: Found ${#tasks[@]} task(s) ==="
    
    for task_file in "${tasks[@]}"; do
        # Skip if already processed
        if [[ "$task_file" == *.executing.md ]] || [[ "$task_file" == *.done.md ]]; then
            continue
        fi
        
        local task_name=$(basename "$task_file" .md)
        local model=$(get_model "$agent")
        
        log "Processing: $task_name (model: $model)"
        
        # Extract task description
        local task_desc=$(get_task_desc "$task_file")
        
        if [ -z "$task_desc" ]; then
            task_desc="$task_name"
        fi
        
        log "  Task: $task_desc"
        
        # Mark as executing
        local executing_file="${task_file%.md}.executing.md"
        mv "$task_file" "$executing_file"
        
        # Execute task with agent-task-handler.py
        log "  Executing with $agent-task-handler.py..."
        python3 /Users/kublai/.openclaw/agents/main/scripts/agent-task-handler.py \
            --agent "$agent" \
            --task-file "$executing_file" \
            2>&1 | while read line; do log "    $line"; done
        
        # Check if execution was successful
        if [ $? -eq 0 ]; then
            # Move to completed
            mv "$executing_file" "${executing_file%.md}.completed.done.md"
            log "  ✓ Task completed"
        else
            # Move back to pending for retry
            mv "$executing_file" "$task_file"
            log "  ✗ Task failed - returned to queue"
        fi
    done
}

# Process all agents
process_all() {
    log "=== Task Consumer Cycle ==="
    
    for agent in temujin mongke chagatai jochi ogedei kublai; do
        process_agent "$agent"
    done
    
    log "=== Cycle Complete ==="
}

# If run with --continuous flag, loop forever
if [ "$1" = "--continuous" ]; then
    log "Starting continuous task consumer (poll every ${POLL_INTERVAL}s)"
    while true; do
        process_all
        sleep "$POLL_INTERVAL"
    done
else
    # Single pass
    process_all
fi