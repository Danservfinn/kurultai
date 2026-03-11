#!/bin/bash
# Standalone kurultai-reflect runner — fires at :30 via separate launchd job
# Extracted from hourly_reflection.sh Phase 3b to relieve timing budget pressure

SCRIPT_START=$(date +%s)
TIMEOUT_SECONDS=720   # 12 minute ceiling for the entire script (increased from 300s)
LOGS_DIR="/Users/kublai/.openclaw/agents/main/logs"
AGENTS=("kublai" "mongke" "chagatai" "temujin" "jochi" "ogedei")
CLAUDE_AGENT_BIN="/Users/kublai/.local/bin/claude-agent"

# Use gtimeout (GNU coreutils on macOS) or fallback to built-in timeout
TIMEOUT_CMD=$(command -v gtimeout 2>/dev/null || command -v timeout 2>/dev/null || echo "")
# Per-agent timeout: 240s (increased from 180s to allow full kurultai-reflect execution)
PER_AGENT_TIMEOUT=240

_exit_code=0
_failed_count=0

# ============================================================
# AUTH HEALTH CHECK: Skip reflection when authentication unavailable
# Prevents wasted reflection runs when claude session expires
# ============================================================
check_auth_status() {
    # Quick check if claude-agent binary exists and is executable
    if [ ! -x "$CLAUDE_AGENT_BIN" ]; then
        echo "[$(date)] AUTH CHECK FAILED: claude-agent not found or not executable"
        return 1
    fi

    # Try a minimal API call to verify authentication
    local output
    output=$("$CLAUDE_AGENT_BIN" -p "Say 'auth_ok'" 2>&1)
    local rc=$?

    if [ $rc -ne 0 ]; then
        echo "[$(date)] AUTH CHECK FAILED: claude-agent returned exit code $rc"
        echo "[$(date)] Output: $output"
        return 1
    fi

    if echo "$output" | grep -qi "not logged in"; then
        echo "[$(date)] AUTH CHECK FAILED: Not logged in"
        return 1
    fi

    echo "[$(date)] AUTH CHECK PASSED: claude-agent authenticated"
    return 0
}

# Call auth check at start
if ! check_auth_status; then
    echo "[$(date)] Skipping reflection - authentication unavailable"
    exit 0
fi

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
        "$TIMEOUT_CMD" --foreground --kill-after=10s $PER_AGENT_TIMEOUT "$CLAUDE_AGENT_BIN" --model opus \
            -p "Run the kurultai-reflect skill for agent: ${agent}. Window: last 2 hours. Execute all 7 phases completely. Read SKILL.md at ~/.openclaw/agents/main/skills/kurultai-reflect/SKILL.md first." \
            >> "$LOG_FILE" 2>&1 &
    else
        # Fallback: run without timeout (watchdog will still kill after 12min)
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
