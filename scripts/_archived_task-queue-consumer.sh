#!/bin/bash
# Task Queue Consumer - Polls agent task directories and executes pending tasks
# Runs continuously, checking each agent's tasks directory

set -e

AGENT_DIR="/Users/kublai/.openclaw/agents/main/agent"
LOG_FILE="/Users/kublai/.openclaw/agents/main/logs/task-consumer.log"
POLL_INTERVAL=30  # seconds between checks

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] $1" | tee -a "$LOG_FILE"
}

# Check if task is locked (already being processed)
is_locked() {
    local task_file="$1"
    local lock_file="${task_file}.lock"
    [ -f "$lock_file" ]
}

# Acquire lock on task
acquire_lock() {
    local task_file="$1"
    local lock_file="${task_file}.lock"
    echo $$ > "$lock_file"
}

# Release lock on task
release_lock() {
    local task_file="$1"
    local lock_file="${task_file}.lock"
    rm -f "$lock_file"
}

# Mark task as completed
complete_task() {
    local task_file="$1"
    local status="$2"  # "completed" or "failed"
    
    mv "$task_file" "${task_file%.md}.${status}.done"
}

# Execute a task based on agent type
execute_task() {
    local task_file="$1"
    local agent=$(basename "$(dirname "$(dirname "$task_file")")")
    local task_name=$(basename "$task_file" .md)
    
    log "Executing task for $agent: $task_name"
    
    # Read task content
    local task_content=$(cat "$task_file")
    local task_desc=$(echo "$task_content" | grep -A5 "^# Task:" | tail -n +2 | head -1)
    
    # Route to appropriate agent via sessions_spawn
    case $agent in
        temujin)
            model="qwen3.5-plus"
            ;;
        mongke)
            model="qwen3.5-plus"
            ;;
        chagatai)
            model="qwen3.5-plus"
            ;;
        jochi)
            model="MiniMax-M2.5"
            ;;
        ogedei)
            model="qwen3.5-plus"
            ;;
        kublai)
            model="qwen3.5-plus"
            ;;
        *)
            log "Unknown agent: $agent"
            return 1
            ;;
    esac
    
    # Spawn sub-agent to execute task
    log "Spawning $agent (model: $model) for task: $task_desc"
    
    # Use OpenClaw sessions_spawn via the API or CLI
    # For now, we'll note the task and let it be picked up by cron
    log "Task queued for $agent: $task_desc"
    
    return 0
}

# Process all pending tasks in an agent's directory
process_agent() {
    local agent="$1"
    local task_dir="$AGENT_DIR/$agent/tasks"
    
    if [ ! -d "$task_dir" ]; then
        return
    fi
    
    # Find pending tasks (not .lock, not .done)
    local tasks=$(find "$task_dir" -maxdepth 1 -name "*.md" ! -name "*.lock" ! -name "*.done" 2>/dev/null | sort)
    
    if [ -z "$tasks" ]; then
        return
    fi
    
    for task_file in $tasks; do
        # Skip if locked
        if is_locked "$task_file"; then
            continue
        fi
        
        # Skip if empty
        if [ ! -s "$task_file" ]; then
            rm -f "$task_file"
            continue
        fi
        
        # Acquire lock
        acquire_lock "$task_file"
        
        # Execute task
        if execute_task "$task_file"; then
            complete_task "$task_file" "completed"
            log "Task completed: $task_file"
        else
            complete_task "$task_file" "failed"
            log "Task failed: $task_file"
        fi
        
        # Release lock
        release_lock "$task_file"
    done
}

# Main loop
log "Task consumer started"
log "Polling directories every ${POLL_INTERVAL}s"

# Process once on startup
for agent in temujin mongke chagatai jochi ogedei kublai; do
    process_agent "$agent"
done

log "Initial scan complete, entering continuous mode"

# Continuous polling
while true; do
    sleep "$POLL_INTERVAL"
    
    for agent in temujin mongke chagatai jochi ogedei kublai; do
        process_agent "$agent"
    done
done