#!/bin/bash
# ollama-lock.sh — Bash wrapper for Ollama GPU lock
#
# Source this file, then use the wrapper functions:
#   source /path/to/ollama-lock.sh
#   ollama_with_lock NORMAL "tick-triage" python3 -c "..."
#   ollama_high "watchdog-alert" curl -s http://localhost:11434/...
#   ollama_normal "tock-assess" python3 -c "..."
#   ollama_low "research" python3 -c "..."
#
# Exit codes:
#   0 = command succeeded
#   2 = GPU busy (lock not acquired) — not an error, caller should skip
#   other = command's own exit code

OLLAMA_LOCK_FILE="/tmp/ollama-gpu.lock"
OLLAMA_LOCK_SIDECAR="/tmp/ollama-gpu.lock.pid"
OLLAMA_LOCK_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/ollama_lock.py"

# ollama_with_lock PRIORITY LABEL command [args...]
#   PRIORITY: HIGH (wait 300s), NORMAL (wait 90s), LOW (skip if busy)
#   LABEL: human-readable identifier for diagnostics
ollama_with_lock() {
    local priority="${1:?Usage: ollama_with_lock PRIORITY LABEL cmd...}"
    local label="${2:-unnamed}"
    shift 2

    python3 "$OLLAMA_LOCK_SCRIPT" acquire "$priority" "$label" -- "$@"
    return $?
}

# Convenience aliases
ollama_high()   { ollama_with_lock HIGH   "$@"; }
ollama_normal() { ollama_with_lock NORMAL "$@"; }
ollama_low()    { ollama_with_lock LOW    "$@"; }

# Check if GPU is currently locked
ollama_lock_status() {
    python3 "$OLLAMA_LOCK_SCRIPT" status
}
