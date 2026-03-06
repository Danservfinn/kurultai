#!/bin/bash
# Auto-Dispatch — Cron wrapper for auto_dispatch.py
# Runs every 5 minutes to dispatch queued tasks to idle agents.
#
# Cron entry:
#   */5 * * * * /Users/kublai/.openclaw/agents/main/scripts/auto-dispatch.sh >> /Users/kublai/.openclaw/agents/main/logs/auto-dispatch-cron.log 2>&1

# Set up PATH for cron environment
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export NODE_PATH="/opt/homebrew/lib/node_modules"
export OPENCLAW_STATE_DIR="/Users/kublai/.openclaw"
export HOME="/Users/kublai"

SCRIPTS_DIR="/Users/kublai/.openclaw/agents/main/scripts"
LOG_FILE="/Users/kublai/.openclaw/agents/main/logs/auto-dispatch-cron.log"

mkdir -p "$(dirname "$LOG_FILE")"

# Run the Python dispatcher
python3 "$SCRIPTS_DIR/auto_dispatch.py" "$@"
