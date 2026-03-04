#!/bin/bash
# Gathers all gateway health metrics in one shot for the watchdog agent
LOG="$HOME/.openclaw/agents/main/logs/watchdog.log"
TS=$(date '+%Y-%m-%d %H:%M:%S')

# Gateway PIDs
PIDS=$(pgrep -f "openclaw" 2>/dev/null | head -5 | tr '\n' ',')
PIDS=${PIDS%,}

# Process stats
if [ -n "$PIDS" ]; then
    FIRST_PID=$(echo "$PIDS" | cut -d',' -f1)
    CPU=$(ps -p "$FIRST_PID" -o %cpu= 2>/dev/null | tr -d ' ')
    MEM=$(ps -p "$FIRST_PID" -o %mem= 2>/dev/null | tr -d ' ')
    RSS=$(ps -p "$FIRST_PID" -o rss= 2>/dev/null | tr -d ' ')
else
    CPU=0; MEM=0; RSS=0
fi

# Health endpoint
HTTP=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:18789/health 2>/dev/null || echo "000")

# Recent errors
ERRORS=$(tail -200 ~/.openclaw/logs/openclaw.log 2>/dev/null | grep -c "ERROR\|FATAL\|CRASH" || echo "0")

# Determine status
STATUS="healthy"
ACTION="none"
REASON="all checks passed"

if [ -z "$PIDS" ] && [ "$HTTP" = "000" ]; then
    STATUS="down"
    ACTION="restart"
    REASON="no PID and endpoint unreachable"
    launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway 2>/dev/null
    sleep 5
    NEW_PID=$(pgrep -f "openclaw" | head -1)
    if [ -n "$NEW_PID" ]; then
        REASON="restarted successfully (new PID: $NEW_PID)"
    else
        ACTION="alert"
        REASON="restart failed"
    fi
elif [ "$HTTP" != "200" ] && [ "$HTTP" != "000" ]; then
    STATUS="degraded"
    ACTION="warn"
    REASON="endpoint returned $HTTP"
elif [ -n "$CPU" ] && [ "$(echo "$CPU > 80" | bc -l 2>/dev/null)" = "1" ]; then
    STATUS="degraded"
    ACTION="warn"
    REASON="high CPU ${CPU}%"
fi

# Log one line
echo "[$TS] WATCHDOG | status=$STATUS | pid=$PIDS | cpu=${CPU}% | mem=${MEM}% | rss=${RSS}KB | endpoint=$HTTP | errors=$ERRORS | action=$ACTION | reason=$REASON" >> "$LOG"

# Output for the agent
echo "status=$STATUS pid=$PIDS cpu=${CPU}% mem=${MEM}% endpoint=$HTTP errors=$ERRORS action=$ACTION reason=$REASON"
