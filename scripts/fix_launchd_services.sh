#!/bin/bash
# fix_launchd_services.sh — Ensure critical Kurultai launchd services are loaded and running
# Part of O003: Cron/launchd reliability investigation
#
# Checks: heartbeat-watchdog, ogedei-watchdog, task-executor, kurultai-monitor
# Actions: Bootstrap any unloaded services, log results
#
# Run: sudo ./fix_launchd_services.sh (for system-wide) or ./fix_launchd_services.sh (user agents)

set -eo pipefail

BASE="/Users/kublai/.openclaw/agents/main"
LOGDIR="$BASE/logs"
LOGFILE="$LOGDIR/launchd-service-fix.log"
TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
USER_ID=$(id -u)

# Critical services to monitor
CRITICAL_SERVICES=(
    "com.kurultai.heartbeat-watchdog"
    "com.kurultai.ogedei-watchdog"
    "com.kurultai.task-executor"
    "com.kurultai.kurultai-monitor"
    "ai.kurultai.hourly-reflection"
)

PLIST_DIR="$HOME/Library/LaunchAgents"

mkdir -p "$LOGDIR"

log() {
    echo "[$TIMESTAMP] $*" | tee -a "$LOGFILE"
}

# Check if a service is loaded
# Note: Use grep without -q to avoid SIGPIPE with pipefail
is_loaded() {
    local service="$1"
    launchctl list 2>/dev/null | grep -F "$service" > /dev/null
}

# Check if a service is running (exit code 0 or has a PID)
is_running() {
    local service="$1"
    local output
    output=$(launchctl list 2>/dev/null | grep "$service" || true)
    if [[ -z "$output" ]]; then
        return 1
    fi
    # Exit status is second field; 0 means running, - means not running
    local status
    status=$(echo "$output" | awk '{print $1}')
    # status can be "0" (running), "-" (not running), or a PID number
    [[ "$status" == "0" ]] || [[ "$status" =~ ^[0-9]+$ ]]
}

# Bootstrap a service using modern launchctl method
bootstrap_service() {
    local service="$1"
    local plist="$PLIST_DIR/$service.plist"

    if [[ ! -f "$plist" ]]; then
        log "ERROR: plist not found: $plist"
        return 1
    fi

    log "Bootstrapping $service..."

    # Validate plist syntax
    if ! plutil -lint "$plist" > /dev/null 2>&1; then
        log "ERROR: Invalid plist syntax: $plist"
        return 1
    fi

    # Bootstrap using modern method
    if launchctl bootstrap "gui/$USER_ID" "$plist" 2>&1; then
        log "SUCCESS: Bootstrapped $service"
        return 0
    else
        log "ERROR: Failed to bootstrap $service"
        return 1
    fi
}

main() {
    log "=== Launchd Service Check ==="

    fixed=0
    failed=0
    running=0

    for service in "${CRITICAL_SERVICES[@]}"; do
        if is_loaded "$service"; then
            if is_running "$service"; then
                log "OK: $service is running"
                ((running++))
            else
                log "WARNING: $service is loaded but not running (exit status != 0)"
                # Try to kickstart it
                if launchctl kickstart -k "gui/$USER_ID/$service" 2>/dev/null; then
                    log "KICKSTARTED: $service"
                    ((fixed++))
                else
                    log "ERROR: Failed to kickstart $service"
                    ((failed++))
                fi
            fi
        else
            log "MISSING: $service is not loaded"
            if bootstrap_service "$service"; then
                ((fixed++))
            else
                ((failed++))
            fi
        fi
    done

    log "=== Summary: running=$running fixed=$fixed failed=$failed ==="

    if [[ $failed -gt 0 ]]; then
        exit 1
    fi
}

main "$@"
