#!/usr/bin/env bash
# rotate_logs.sh: Rotate OpenClaw log files
# Run daily at 2 AM via cron
# Rotates logs >50M or older than 7 days, compresses rotated logs

set -euo pipefail

# Configuration
LOG_DIR="${HOME}/.openclaw/logs"
ROTATE_SIZE_MB=50  # Rotate logs larger than 50MB
RETENTION_DAYS=30  # Keep compressed logs for 30 days
TIMESTAMP=$(date +"%Y%m%d-%H%M")

# Files to always rotate regardless of size (high-volume logs)
ALWAYS_ROTATE=(
    "openclaw.log"
    "gateway.log"
    "gateway.err.log"
)

# ── Colors ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${GREEN}[rotate_logs]${NC} $*"; }
warn() { echo -e "${YELLOW}[rotate_logs]${NC} $*"; }

mkdir -p "$LOG_DIR"

# ── Rotate function ─────────────────────────────────────────────────────────
rotate_log() {
    local log_file="$1"
    local base_name=$(basename "$log_file")

    if [[ ! -f "$log_file" ]]; then
        return
    fi

    # Get file size in MB
    local size_mb=$(du -m "$log_file" | cut -f1)

    # Check if rotation is needed
    local should_rotate=false
    if [[ " ${ALWAYS_ROTATE[@]} " =~ " ${base_name} " ]]; then
        should_rotate=true
        info "Rotating ${base_name} (in always-rotate list, ${size_mb}MB)"
    elif [[ $size_mb -ge $ROTATE_SIZE_MB ]]; then
        should_rotate=true
        info "Rotating ${base_name} (size: ${size_mb}MB >= ${ROTATE_SIZE_MB}MB)"
    fi

    if [[ "$should_rotate" == true ]]; then
        local rotated="${log_file}.${TIMESTAMP}"
        mv "$log_file" "$rotated"
        gzip "$rotated"
        info "  → ${rotated}.gz ($(du -mh "${rotated}.gz" | cut -f1))"
    fi
}

# ── Rotate all .log files in main log directory ─────────────────────────────
info "Checking logs in ${LOG_DIR}..."
for log_file in "$LOG_DIR"/*.log; do
    [[ -f "$log_file" ]] || continue
    rotate_log "$log_file"
done

# Also check agents main logs
AGENT_LOG_DIR="${HOME}/.openclaw/agents/main/logs"
if [[ -d "$AGENT_LOG_DIR" ]]; then
    info "Checking logs in ${AGENT_LOG_DIR}..."
    for log_file in "$AGENT_LOG_DIR"/*.log; do
        [[ -f "$log_file" ]] || continue
        rotate_log "$log_file"
    done
fi

# ── Prune old compressed logs ────────────────────────────────────────────────
info "Pruning compressed logs older than ${RETENTION_DAYS} days..."
deleted=0
for old_gz in $(find "$LOG_DIR" "$AGENT_LOG_DIR" -name "*.log.*.gz" -type f -mtime +$RETENTION_DAYS 2>/dev/null); do
    rm -f "$old_gz"
    ((deleted++))
    info "  → Removed: $(basename "$old_gz")"
done

if [[ $deleted -eq 0 ]]; then
    info "  No old logs to prune"
else
    info "  Removed ${deleted} old compressed logs"
fi

# ── Summary ────────────────────────────────────────────────────────────────
total_logs=$(find "$LOG_DIR" "$AGENT_LOG_DIR" -name "*.log" -type f 2>/dev/null | wc -l | tr -d ' ')
total_gz=$(find "$LOG_DIR" "$AGENT_LOG_DIR" -name "*.log.*.gz" -type f 2>/dev/null | wc -l | tr -d ' ')
info "Log rotation complete: ${total_logs} active logs, ${total_gz} archived"
