#!/bin/bash
# Heartbeat Watchdog Script
# Runs every 5 minutes to execute pending agent tasks
#
# Two dispatch mechanisms (belt and suspenders):
# 1. auto_dispatch.py — Primary: scans queues, cleans stale tasks, dispatches via openclaw agent
# 2. heartbeat-task-executor.py — Fallback: simpler executor for anything auto-dispatch missed

export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export NODE_PATH="/opt/homebrew/lib/node_modules"
export OPENCLAW_STATE_DIR="/Users/kublai/.openclaw"

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPTS_DIR/../logs/heartbeat-watchdog.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=== Heartbeat Watchdog Cycle ==="

# Primary: Auto-dispatch (scans queues, cleans stale .executing, dispatches to idle agents)
python3 "$SCRIPTS_DIR/auto_dispatch.py" 2>&1 | tee -a "$LOG_FILE"

# Fallback: Legacy executor (catches anything auto-dispatch didn't handle)
python3 "$SCRIPTS_DIR/heartbeat-task-executor.py" --max-tasks 1 2>&1 | tee -a "$LOG_FILE"

log "=== Cycle Complete ==="
