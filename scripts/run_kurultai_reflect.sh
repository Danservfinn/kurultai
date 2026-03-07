#!/bin/bash
# Standalone kurultai-reflect runner — fires at :30 via separate launchd job
# Extracted from hourly_reflection.sh Phase 3b to relieve timing budget pressure

SCRIPT_START=$(date +%s)
TIMEOUT_SECONDS=300   # 5 minute ceiling for the entire script
LOGS_DIR="/Users/kublai/.openclaw/agents/main/logs"
AGENTS=("kublai" "mongke" "chagatai" "temujin" "jochi" "ogedei")
CLAUDE_AGENT_BIN="/Users/kublai/.local/bin/claude-agent"

# Use gtimeout (GNU coreutils on macOS) or fallback to built-in timeout
TIMEOUT_CMD=$(command -v gtimeout 2>/dev/null || command -v timeout 2>/dev/null || echo "")

_exit_code=0
_failed_count=0

# Timeout watchdog
(sleep $TIMEOUT_SECONDS && kill -TERM -$$ 2>/dev/null) &
WATCHDOG_PID=$!
trap 'kill $WATCHDOG_PID 2>/dev/null; exit $_exit_code' EXIT TERM INT

echo "[$(date)] Starting kurultai-reflect for all agents (parallel, timeout=${TIMEOUT_SECONDS}s)"

reflect_pids=()
for agent in "${AGENTS[@]}"; do
    LOG_FILE="$LOGS_DIR/kurultai-reflect-${agent}.log"
    if [ -f "$LOG_FILE" ]; then
        tail -500 "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
    fi
    echo "--- $(date) ---" >> "$LOG_FILE"
    if [ -n "$TIMEOUT_CMD" ]; then
        # Use gtimeout/timeout if available
        "$TIMEOUT_CMD" --foreground --kill-after=10s 180 "$CLAUDE_AGENT_BIN" --model opus \
            -p "Run the kurultai-reflect skill for agent: ${agent}. Window: last 2 hours. Execute all 7 phases completely. Read SKILL.md at ~/.openclaw/agents/main/skills/kurultai-reflect/SKILL.md first." \
            >> "$LOG_FILE" 2>&1 &
    else
        # Fallback: run without timeout (watchdog will still kill after 5min)
        "$CLAUDE_AGENT_BIN" --model opus \
            -p "Run the kurultai-reflect skill for agent: ${agent}. Window: last 2 hours. Execute all 7 phases completely. Read SKILL.md at ~/.openclaw/agents/main/skills/kurultai-reflect/SKILL.md first." \
            >> "$LOG_FILE" 2>&1 &
    fi
    reflect_pids+=($!)
    sleep 2   # stagger launches to avoid thundering herd
done

for i in "${!reflect_pids[@]}"; do
    pid="${reflect_pids[$i]}"
    agent="${AGENTS[$i]}"
    wait "$pid"
    rc=$?
    log_bytes=$(($(wc -c < "$LOGS_DIR/kurultai-reflect-${agent}.log" 2>/dev/null || echo 0)))
    if [ $rc -eq 124 ]; then
        echo "[$(date)] [$agent] TIMEOUT (exit 124, ${log_bytes} bytes)"
    elif [ $rc -ne 0 ]; then
        echo "[$(date)] [$agent] FAILED (exit $rc, ${log_bytes} bytes)"
        _failed_count=$((_failed_count + 1))
    else
        echo "[$(date)] [$agent] OK (${log_bytes} bytes)"
    fi
done

if [ "$_failed_count" -eq "${#AGENTS[@]}" ]; then
    echo "[$(date)] ALL agents failed — exiting 1"
    _exit_code=1
fi

elapsed=$(($(date +%s) - SCRIPT_START))
echo "[$(date)] kurultai-reflect complete in ${elapsed}s"
