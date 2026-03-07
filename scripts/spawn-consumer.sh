#!/bin/bash
# Spawn Consumer - Reads spawn requests and executes them via OpenClaw
# Run every 2 minutes via cron
#
# SECURITY: No longer writes Python to /tmp. Uses spawn_consumer_worker.py directly.

# Set up PATH for cron environment
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export NODE_PATH="/opt/homebrew/lib/node_modules"

SPAWN_QUEUE="/Users/kublai/.openclaw/agents/main/logs/spawn-pending.json"
LOG_FILE="/Users/kublai/.openclaw/agents/main/logs/spawn-consumer.log"
SCRIPTS_DIR="/Users/kublai/.openclaw/agents/main/scripts"

mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Silent mode: Only report when something meaningful happens
export REPORT_ONLY_ON_ACTIVITY="${REPORT_ONLY_ON_ACTIVITY:-true}"

if [ "$REPORT_ONLY_ON_ACTIVITY" != "true" ]; then
    log "=== Spawn Consumer Cycle ==="
fi

if [ ! -f "$SPAWN_QUEUE" ]; then
    if [ "$REPORT_ONLY_ON_ACTIVITY" != "true" ]; then
        log "No spawn queue found"
    fi
    exit 0
fi

# Execute the proper Python worker (no /tmp scripts)
python3 "$SCRIPTS_DIR/spawn_consumer_worker.py"
