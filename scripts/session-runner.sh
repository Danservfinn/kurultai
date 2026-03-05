#!/bin/bash
# Session Runner - Dispatches tasks to idle Kurultai agents
# Usage: ./session-runner.sh [agent]
# If no agent specified, checks all agents for pending tasks

set -e

AGENTS_DIR="/Users/kublai/.openclaw/agents"
LOG_FILE="/Users/kublai/.openclaw/agents/main/logs/session-runner.log"

log() {
    echo "[$(date -Iseconds)] $1" >> "$LOG_FILE"
}

dispatch_task() {
    local agent=$1
    local task_dir="$AGENTS_DIR/$agent/tasks"
    
    # Find oldest pending task (not .executing, .completed, or .done)
    local pending_task=$(find "$task_dir" -name "*.md" ! -name "*.executing*" ! -name "*.completed*" ! -name "*.done*" 2>/dev/null | sort | head -1)
    
    if [ -z "$pending_task" ]; then
        log "No pending tasks for $agent"
        return 1
    fi
    
    local task_name=$(basename "$pending_task")
    log "Dispatching task for $agent: $task_name"
    
    # Mark as executing
    mv "$pending_task" "${pending_task}.executing"
    
    # TODO: Actually invoke the agent via openclaw sessions_spawn
    # For now, just log the dispatch
    log "Task dispatched: $task_name for $agent"
    
    return 0
}

# Main
if [ -n "$1" ]; then
    dispatch_task "$1"
else
    # Check all agents in priority order
    for agent in temujin mongke chagatai jochi ogedei; do
        dispatch_task "$agent" && break
    done
fi
