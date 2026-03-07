#!/bin/bash
# Standalone brainstorm runner — decoupled from hourly_reflection.sh
# Runs every hour at :30 (offset from :00 reflections)
# Has its own 1500s timeout independent of the reflection pipeline.

SCRIPT_START=$(date +%s)
TIMEOUT_SECONDS=1500
SCRIPT_EXIT=1

SCRIPTS="/Users/kublai/.openclaw/agents/main/scripts"
LOGS_DIR="/Users/kublai/.openclaw/agents/main/logs"
PROPOSALS_DIR="/Users/kublai/.openclaw/agents/main/proposals"

mkdir -p "$PROPOSALS_DIR" "$LOGS_DIR" || { echo "[$(date)] FATAL: cannot create directories"; exit 1; }

# Timeout watchdog
timeout_watchdog() {
    sleep $TIMEOUT_SECONDS
    echo "[$(date)] TIMEOUT: Brainstorm exceeded ${TIMEOUT_SECONDS}s, forcing exit"
    kill -TERM $$ 2>/dev/null || true
}
timeout_watchdog &
WATCHDOG_PID=$!
trap "kill $WATCHDOG_PID 2>/dev/null; exit \${SCRIPT_EXIT:-1}" EXIT TERM INT

echo "[$(date)] Starting brainstorm cycle (timeout: ${TIMEOUT_SECONDS}s)"

# Run brainstorming
python3 "$SCRIPTS/kurultai_brainstorm.py" --all --proposal-output "$PROPOSALS_DIR" >> "$LOGS_DIR/kurultai-brainstorm.log" 2>&1
BRAINSTORM_EXIT=$?

# Expire stale proposals (filesystem + Neo4j)
python3 "$SCRIPTS/kurultai_review.py" --expire >> "$LOGS_DIR/kurultai-review.log" 2>&1 || true

elapsed=$(($(date +%s) - SCRIPT_START))
echo "[$(date)] Brainstorm cycle complete in ${elapsed}s (exit: $BRAINSTORM_EXIT)"

# Emit health heartbeat for watchdog monitoring
cat > "$LOGS_DIR/brainstorm-status.json" << BEOF
{"status":"$([ $BRAINSTORM_EXIT -eq 0 ] && echo complete || echo failed)","timestamp":"$(date -Iseconds)","elapsed_s":$elapsed,"exit_code":$BRAINSTORM_EXIT}
BEOF

SCRIPT_EXIT=$BRAINSTORM_EXIT
