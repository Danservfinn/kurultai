#!/bin/bash
# Heartbeat Watchdog Script
# Runs every 5 minutes to execute pending agent tasks

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPTS_DIR/../logs/heartbeat-watchdog.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=== Heartbeat Watchdog Cycle ==="

# Execute pending tasks for all agents
python3 "$SCRIPTS_DIR/heartbeat-task-executor.py" --max-tasks 1 2>&1 | tee -a "$LOG_FILE"

log "=== Cycle Complete ==="
