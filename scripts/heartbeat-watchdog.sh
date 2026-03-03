#!/bin/bash
# Heartbeat Daemon Watchdog
# Run via cron: */5 * * * * /Users/kublai/.openclaw/agents/main/scripts/heartbeat-watchdog.sh

LOG_FILE="/Users/kublai/.openclaw/agents/main/logs/watchdog.log"
DAEMON_NAME="heartbeat_master.py"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=== Watchdog Check ==="

# Check for heartbeat daemon process
PIDS=$(pgrep -f "$DAEMON_NAME")

if [ -z "$PIDS" ]; then
    log "❌ Heartbeat daemon NOT RUNNING - restarting..."
    
    # Restart the daemon
    cd /Users/kublai/.openclaw/agents/main
    nohup python3 -m openclaw daemon > /dev/null 2>&1 &
    
    # Wait and verify
    sleep 5
    NEW_PIDS=$(pgrep -f "$DAEMON_NAME")
    if [ -n "$NEW_PIDS" ]; then
        log "✅ Heartbeat daemon restarted (PIDs: $NEW_PIDS)"
    else
        log "❌ Failed to restart heartbeat daemon"
        # Alert Kublai
        echo "Heartbeat daemon failed to restart" >&2
    fi
else
    log "✅ Heartbeat daemon running (PIDs: $PIDS)"
    
    # Check CPU/memory health
    for pid in $PIDS; do
        cpu=$(ps -p $pid -o %cpu= 2>/dev/null || echo "0")
        mem=$(ps -p $pid -o %mem= 2>/dev/null || echo "0")
        
        # Flag if CPU > 80% or MEM > 50%
        if (( $(echo "$cpu > 80" | bc -l) )); then
            log "⚠️ PID $pid high CPU: $cpu%"
        fi
        if (( $(echo "$mem > 50" | bc -l) )); then
            log "⚠️ PID $pid high MEM: $mem%"
        fi
    done
fi

log "=== Watchdog Done ==="