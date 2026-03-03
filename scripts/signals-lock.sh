#!/bin/bash
# Signals.md Locking Wrapper
# Usage: ./signals-lock.sh "message to append"
# Uses flock to prevent race conditions

SIGNALS_FILE="/Users/kublai/.openclaw/agents/shared-context/SIGNALS.md"
LOCK_FILE="$SIGNALS_FILE.lock"

append_to_signals() {
    local message="$1"
    local agent="${2:-kublai}"
    
    (
        flock -n 9 || { echo "Failed to acquire lock"; exit 1; }
        
        echo "" >> "$SIGNALS_FILE"
        echo "## $(date '+%Y-%m-%d %H:%M:%S') - $agent" >> "$SIGNALS_FILE"
        echo "$message" >> "$SIGNALS_FILE"
        
        flock -u 9
    ) 9>"$LOCK_FILE"
}

# If called directly with argument
if [ -n "$1" ]; then
    append_to_signals "$1" "${2:-kublai}"
fi