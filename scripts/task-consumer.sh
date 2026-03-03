#!/bin/bash
# Task Consumer: Executes LLM-generated tasks from temujin/tasks/
# Run via cron: */15 * * * * /Users/kublai/.openclaw/agents/main/scripts/task-consumer.sh

set -e

TASKS_DIR="/Users/kublai/.openclaw/agents/main/agent/temujin/tasks"
LOG_FILE="/Users/kublai/.openclaw/agents/main/logs/task-consumer.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=== Task Consumer Starting ==="

# Check for new task files
shopt -s nullglob
tasks=("$TASKS_DIR"/llm-review-*.md)

if [ ${#tasks[@]} -eq 0 ]; then
    log "No tasks found. Exiting."
    exit 0
fi

log "Found ${#tasks[@]} task(s)"

for task_file in "${tasks[@]}"; do
    task_name=$(basename "$task_file")
    log "Processing: $task_name"
    
    # Check if already processed
    if [[ "$task_name" == *.processed.md ]]; then
        log "  Skipping already processed: $task_name"
        continue
    fi
    
    # Parse task content
    code_needed=$(grep -i "code_needed:" "$task_file" | head -1 | cut -d: -f2 | tr -d ' ' || echo "false")
    
    log "  code_needed: $code_needed"
    
    if [ "$code_needed" = "true" ]; then
        # Extract task description
        task_desc=$(grep -A5 "task:" "$task_file" | head -6 || echo "No description")
        
        log "  Executing task via sessions_spawn..."
        
        # Spawn ACP session to execute
        # Note: This calls the OpenClaw API indirectly via subprocess
        # In practice, you'd use the OpenClaw CLI or API
        timeout 300 openclaw spawn --agent temujin --task "$task_desc" --runtime acp --mode run
        
        if [ $? -eq 0 ]; then
            log "  Task completed successfully"
            mv "$task_file" "$task_file.processed"
        else
            log "  Task failed - leaving for retry"
        fi
    else
        log "  No code needed - marking processed"
        mv "$task_file" "$task_file.processed"
    fi
done

log "=== Task Consumer Done ==="