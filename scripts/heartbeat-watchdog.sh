#!/bin/bash
# Heartbeat Daemon Watchdog
# Run via cron: */5 * * * * /Users/kublai/.openclaw/agents/main/scripts/heartbeat-watchdog.sh

LOG_FILE="/Users/kublai/.openclaw/agents/main/logs/watchdog.log"
DAEMON_NAME="openclaw-gateway"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=== Watchdog Check ==="

# Check for gateway process (heartbeat is built into gateway)
PIDS=$(pgrep -f "$DAEMON_NAME")

if [ -z "$PIDS" ]; then
    log "❌ Gateway NOT RUNNING - restarting..."
    
    # Restart the gateway via launchctl
    launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway 2>/dev/null || \
    launchctl kickstart -k gui/$(id -u)/com.openclaw.gateway 2>/dev/null || \
    log "⚠️ launchctl kickstart failed, trying direct start..."
    
    # Wait and verify
    sleep 5
    NEW_PIDS=$(pgrep -f "$DAEMON_NAME")
    if [ -n "$NEW_PIDS" ]; then
        log "✅ Gateway restarted (PIDs: $NEW_PIDS)"
    else
        log "❌ Failed to restart gateway"
        # Alert Kublai
        echo "Gateway failed to restart" >&2
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