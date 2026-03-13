#!/bin/bash
# Cleanup Orphaned Claude Code Sessions
#
# This script identifies and optionally terminates orphaned Claude Code processes
# that are consuming memory without active use.
#
# An orphan is defined as a process that is BOTH:
# 1. Running for more than 2 hours OR has no session file modified recently
# 2. Not associated with a recently active session
#
# Usage:
#   ./cleanup-orphan-claude.sh [--older-minutes N]  # Dry run - shows what would be cleaned
#   ./cleanup-orphan-claude.sh --run               # Actually terminate orphans

set -euo pipefail

LOG_FILE="/Users/kublai/.openclaw/logs/cleanup-orphan-claude.log"
RUN_ACTUAL=false
OLDER_MINUTES=120  # Default: processes older than 2 hours

for arg in "$@"; do
    case "$arg" in
        --run)
            RUN_ACTUAL=true
            ;;
        --older-minutes=*)
            OLDER_MINUTES="${arg#*=}"
            ;;
    esac
done

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=== Claude Cleanup Scan Started ==="
log "Threshold: Processes older than ${OLDER_MINUTES} minutes OR no session activity in 60 minutes"

# Find all Claude Code processes (matches both .claude/claude and .local/bin/claude)
CLAUDE_PROCS=$(ps aux | grep -E '(\.claude/claude|\.local/bin/claude|node .*claude)' | grep -v grep || true)

if [[ -z "$CLAUDE_PROCS" ]]; then
    log "No Claude Code processes found"
    exit 0
fi

# Count and list processes
CLAUDE_COUNT=$(echo "$CLAUDE_PROCS" | wc -l | tr -d ' ')
TOTAL_MEM=$(echo "$CLAUDE_PROCS" | awk '{sum+=$4} END {print sum}')

log "Found $CLAUDE_COUNT Claude Code process(es) using ${TOTAL_MEM}% RAM"

# Check each process for recent activity
ORPHANS=()
ACTIVE=()

while read -r line; do
    PID=$(echo "$line" | awk '{print $2}')
    MEM=$(echo "$line" | awk '{print $4}')
    RSS=$(echo "$line" | awk '{print $6}')
    STARTED=$(echo "$line" | awk '{print $9}')
    CMD=$(echo "$line" | awk '{for(i=11;i<=NF;i++)printf "%s ", $i; print ""}' | head -c 200)

    # Check if process has been running longer than threshold
    # On macOS, ps shows time like "12:09PM" or "2:30:15" or "1:00.00"
    PROC_AGE_MINUTES=0
    if [[ "$STARTED" =~ ([0-9]+):([0-9]{2})(AM|PM) ]]; then
        # Format: HH:MMAM/PM - process started today
        CURRENT_HOUR=$(date +%H)
        CURRENT_MIN=$(date +%M)
        START_HOUR="${BASH_REMATCH[1]}"
        START_MIN="${BASH_REMATCH[2]}"
        START_AMPM="${BASH_REMATCH[3]}"

        # Force base 10 interpretation to avoid octal issues with "08", "09"
        START_HOUR=$((10#$START_HOUR))
        START_MIN=$((10#$START_MIN))

        # Convert to 24-hour
        if [[ "$START_AMPM" == "PM" && "$START_HOUR" != "12" ]]; then
            START_HOUR=$((START_HOUR + 12))
        elif [[ "$START_AMPM" == "AM" && "$START_HOUR" == "12" ]]; then
            START_HOUR=0
        fi

        PROC_AGE_MINUTES=$(( (CURRENT_HOUR * 60 + CURRENT_MIN) - (START_HOUR * 60 + START_MIN) ))
        if [[ $PROC_AGE_MINUTES -lt 0 ]]; then
            PROC_AGE_MINUTES=$((PROC_AGE_MINUTES + 1440))  # Handle day wraparound
        fi
    elif [[ "$STARTED" =~ ([0-9]+):([0-9]+):([0-9]+) ]]; then
        # Format: H:MM:SS - process started more than a day ago
        HOURS="${BASH_REMATCH[1]}"
        PROC_AGE_MINUTES=$((10#$HOURS * 60))
    elif [[ "$STARTED" =~ ([0-9]+):([0-9]{2}\.[0-9]{2}) ]]; then
        # Format: MM:SS.CC - process started today (less than an hour)
        MINUTES="${BASH_REMATCH[1]}"
        PROC_AGE_MINUTES=$((10#$MINUTES))
    fi

    # Check for recent session activity
    # Look for session directories that have been modified recently
    STALE=true
    SESSION_DIRS="$HOME/.openclaw/agents/*/sessions"
    RECENT_SESSION=$(find $SESSION_DIRS -type f -mmin -60 2>/dev/null | head -1)
    if [[ -n "$RECENT_SESSION" ]]; then
        # There's a recent session somewhere - be conservative
        # Only consider processes truly old as orphans
        if [[ $PROC_AGE_MINUTES -lt $OLDER_MINUTES ]]; then
            STALE=false
        fi
    fi

    if $STALE && [[ $PROC_AGE_MINUTES -ge $OLDER_MINUTES ]]; then
        ORPHANS+=("$PID|$MEM|$RSS|$PROC_AGE_MINUTES|$STARTED")
        log "Orphan candidate: PID=$PID MEM=${MEM}% RSS=${RSS}KB AGE=${PROC_AGE_MINUTES}min STARTED=$STARTED"
        log "  CMD: $CMD"
    else
        ACTIVE+=("$PID|$PROC_AGE_MINUTES")
    fi
done <<< "$CLAUDE_PROCS"

if [[ ${#ORPHANS[@]} -eq 0 ]]; then
    log "No orphaned processes found"
    if [[ ${#ACTIVE[@]} -gt 0 ]]; then
        log "Active processes: ${#ACTIVE[@]}"
    fi
    exit 0
fi

ORPHAN_MEM=$(IFS=$'\n'; echo "${ORPHANS[*]}" | awk -F'|' '{sum+=$2} END {print sum}')
log "Found ${#ORPHANS[@]} orphaned process(es) using ${ORPHAN_MEM}% RAM"

if $RUN_ACTUAL; then
    for orphan in "${ORPHANS[@]}"; do
        PID=$(echo "$orphan" | cut -d'|' -f1)
        log "Terminating orphaned PID $PID..."
        if kill "$PID" 2>/dev/null; then
            log "  Terminated PID $PID"
            sleep 0.5
            if kill -0 "$PID" 2>/dev/null; then
                log "  Still running, sending SIGKILL..."
                kill -9 "$PID" 2>/dev/null || log "  Failed to force kill $PID"
            fi
        else
            log "  Failed to terminate $PID (may have already exited)"
        fi
    done
    log "Cleanup complete: terminated ${#ORPHANS[@]} process(es)"
else
    log "DRY RUN: Would terminate ${#ORPHANS[@]} process(es)"
    log "Run with --run to actually terminate"
fi

log "=== Claude Cleanup Scan Complete ==="
