#!/bin/bash
# Urgent Notification — Fast-track alert delivery via Signal
# Bypasses LLM triage for critical alerts requiring immediate attention

set -e

NOTIFY_TARGET="+19194133445"
LOG_DIR="/Users/kublai/.openclaw/logs"
URGENT_LOG="$LOG_DIR/urgent-notify.log"

mkdir -p "$LOG_DIR"

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
TIMESTAMP_READABLE=$(date '+%Y-%m-%d %H:%M:%S')

# Parse arguments
SEVERITY="${1:-INFO}"
TITLE="${2:-Alert}"
MESSAGE="${3:-}"

if [ -z "$MESSAGE" ]; then
    # Read from stdin if no message provided
    MESSAGE=$(cat)
fi

# Validate severity
case "$SEVERITY" in
    CRITICAL|HIGH|MODERATE|INFO)
        ;;
    *)
        SEVERITY="INFO"
        ;;
esac

# Add emoji based on severity
case "$SEVERITY" in
    CRITICAL)
        EMOJI="🚨"
        PRIORITY="high"
        ;;
    HIGH)
        EMOJI="⚠️"
        PRIORITY="medium"
        ;;
    MODERATE)
        EMOJI="🔶"
        PRIORITY="normal"
        ;;
    *)
        EMOJI="ℹ️"
        PRIORITY="low"
        ;;
esac

# Format message
FORMATTED_MSG="${EMOJI} [${SEVERITY}] ${TITLE}

${MESSAGE}

Timestamp: ${TIMESTAMP_READABLE}
Kurultai Watchdog"

# Log the notification
echo "[$TIMESTAMP] URGENT_NOTIFY | severity=$SEVERITY | title=$TITLE | target=$NOTIFY_TARGET" >> "$URGENT_LOG"

# Send via signal-cli (direct, fast delivery)
if command -v signal-cli >/dev/null 2>&1; then
    # Try to send immediately (timeout 10s)
    if timeout 10s signal-cli -u +19199906984 send "$NOTIFY_TARGET" "$FORMATTED_MSG" >/dev/null 2>&1; then
        echo "[$TIMESTAMP] URGENT_NOTIFY_SENT | severity=$SEVERITY" >> "$URGENT_LOG"
        echo "✅ Notification sent (Signal)"
        exit 0
    else
        echo "[$TIMESTAMP] URGENT_NOTIFY_FAILED | signal-cli timeout/error" >> "$URGENT_LOG"
        # Fallback to claude-agent dispatch
        echo "⚠️ Signal failed, using fallback dispatch..."
    fi
else
    echo "[$TIMESTAMP] URGENT_NOTIFY_NO_SIGNAL | signal-cli not found" >> "$URGENT_LOG"
    echo "⚠️ signal-cli not available, using fallback dispatch..."
fi

# Fallback: Use claude-agent dispatch (async but reliable)
ESCALATION_MSG="${EMOJI} ${TITLE}

${MESSAGE}

Timestamp: ${TIMESTAMP_READABLE}
Severity: ${SEVERITY}
This is an automated proactive alert from the Kurultai watchdog."

if [ "$PRIORITY" = "high" ] || [ "$PRIORITY" = "medium" ]; then
    # Dispatch to main for high/medium priority
    /Users/kublai/.local/bin/claude-agent \
        --message "$ESCALATION_MSG" \
        --thinking high \
        >> "$LOG_DIR/urgent-notify-fallback.log" 2>&1 &
    echo "📤 Fallback dispatch sent to main (pid=$!)"
else
    # For low priority, just log
    echo "📝 Notification logged only (low priority)"
fi

exit 0
