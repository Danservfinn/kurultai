#!/bin/bash
# Cleanup working-memory — delete directories older than 30 days

WORKING_MEMORY="/Users/kublai/.openclaw/agents/shared-context/working-memory"

find "$WORKING_MEMORY" -type d -name "task-*" -mtime +30 -exec rm -rf {} + 2>/dev/null

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Cleaned up working-memory (30+ day old task dirs)"

# === Log Rotation (added 2026-03-12) ===

FREED_BYTES=0

rotate_logs() {
    local DIR="$1"
    local LABEL="$2"

    if [ ! -d "$DIR" ]; then
        echo "  [$LABEL] Directory not found, skipping: $DIR"
        return
    fi

    # 1. Delete .jsonl files older than 30 days
    local jsonl_size
    jsonl_size=$(find "$DIR" -maxdepth 1 -name "*.jsonl" -mtime +30 -exec stat -f%z {} + 2>/dev/null | paste -sd+ - | bc 2>/dev/null || echo 0)
    local jsonl_count
    jsonl_count=$(find "$DIR" -maxdepth 1 -name "*.jsonl" -mtime +30 2>/dev/null | wc -l | tr -d ' ')
    find "$DIR" -maxdepth 1 -name "*.jsonl" -mtime +30 -delete 2>/dev/null
    echo "  [$LABEL] Deleted $jsonl_count .jsonl files older than 30 days (${jsonl_size:-0} bytes)"
    FREED_BYTES=$((FREED_BYTES + ${jsonl_size:-0}))

    # 2. Compress .log files older than 7 days
    local log_count=0
    while IFS= read -r -d '' logfile; do
        gzip -f "$logfile" 2>/dev/null && log_count=$((log_count + 1))
    done < <(find "$DIR" -maxdepth 1 -name "*.log" -mtime +7 -print0 2>/dev/null)
    echo "  [$LABEL] Compressed $log_count .log files older than 7 days"

    # 3. Delete .log.gz files older than 30 days
    local gz_size
    gz_size=$(find "$DIR" -maxdepth 1 -name "*.log.gz" -mtime +30 -exec stat -f%z {} + 2>/dev/null | paste -sd+ - | bc 2>/dev/null || echo 0)
    local gz_count
    gz_count=$(find "$DIR" -maxdepth 1 -name "*.log.gz" -mtime +30 2>/dev/null | wc -l | tr -d ' ')
    find "$DIR" -maxdepth 1 -name "*.log.gz" -mtime +30 -delete 2>/dev/null
    echo "  [$LABEL] Deleted $gz_count .log.gz files older than 30 days (${gz_size:-0} bytes)"
    FREED_BYTES=$((FREED_BYTES + ${gz_size:-0}))
}

# Rotate logs in both directories
rotate_logs "/Users/kublai/.openclaw/logs" "openclaw/logs"
rotate_logs "/Users/kublai/.openclaw/agents/main/logs" "agents/main/logs"

# 5. Trim ticks.jsonl to last 1000 lines if it exists
TICKS_FILE="/Users/kublai/.openclaw/agents/main/logs/ticks.jsonl"
if [ -f "$TICKS_FILE" ]; then
    TICKS_LINES=$(wc -l < "$TICKS_FILE" | tr -d ' ')
    if [ "$TICKS_LINES" -gt 1000 ]; then
        TICKS_SIZE_BEFORE=$(stat -f%z "$TICKS_FILE" 2>/dev/null || echo 0)
        tail -n 1000 "$TICKS_FILE" > "${TICKS_FILE}.tmp" && mv "${TICKS_FILE}.tmp" "$TICKS_FILE"
        TICKS_SIZE_AFTER=$(stat -f%z "$TICKS_FILE" 2>/dev/null || echo 0)
        TICKS_FREED=$((TICKS_SIZE_BEFORE - TICKS_SIZE_AFTER))
        FREED_BYTES=$((FREED_BYTES + TICKS_FREED))
        echo "  [ticks.jsonl] Trimmed from $TICKS_LINES to 1000 lines (freed $TICKS_FREED bytes)"
    else
        echo "  [ticks.jsonl] OK ($TICKS_LINES lines, under 1000 threshold)"
    fi
fi

# 6. Report total space freed
if [ "$FREED_BYTES" -gt 1048576 ]; then
    FREED_MB=$(echo "scale=2; $FREED_BYTES / 1048576" | bc)
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Log rotation complete — freed ${FREED_MB} MB"
elif [ "$FREED_BYTES" -gt 1024 ]; then
    FREED_KB=$(echo "scale=2; $FREED_BYTES / 1024" | bc)
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Log rotation complete — freed ${FREED_KB} KB"
else
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Log rotation complete — freed ${FREED_BYTES} bytes"
fi

# === Orphan Cron Run Cleanup (added 2026-03-12) ===
ORPHAN_SCRIPT="/Users/kublai/.openclaw/agents/main/scripts/cleanup-orphan-cron-runs.sh"
if [ -x "$ORPHAN_SCRIPT" ]; then
    echo ""
    bash "$ORPHAN_SCRIPT"
else
    echo "  [orphan-cron-runs] Script not found or not executable: $ORPHAN_SCRIPT"
fi
