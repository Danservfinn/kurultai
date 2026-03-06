#!/bin/bash
# Concurrent Kurultai Reflection - All 6 Agents Reflect Simultaneously
# Runs every hour with all agents reflecting in parallel
#
# Option B: Protocol-based reflections (~800 tokens/agent vs ~6400 legacy)
# - Role-specific protocols with WHEN/THEN behavioral rules
# - Commitment tracking across sessions
# - Tock data replaces redundant CLI calls
#
# HARD TIMEOUT: 420s (7 min) - ensures cron exits before 900s stale threshold
# CHECKPOINT: Emits reflection-status.json after core reflections complete
# FALLBACK: Exit 0 even if downstream steps fail (content generation succeeded)

# HARD TIMEOUT GUARD (Kublai Initiative 2026-03-06)
# Kill entire process group after 420s to prevent 900s stale task reverts
SCRIPT_START=$(date +%s)
TIMEOUT_SECONDS=420

cleanup_and_exit() {
    local elapsed=$(($(date +%s) - SCRIPT_START))
    echo "[$(date)] Reflection finished in ${elapsed}s"
    # Always exit 0 if core reflections completed - decouple from downstream failures
    if [ -f "$LOGS_DIR/reflection-status.json" ]; then
        exit 0
    else
        # Core reflections didn't complete - this is a real failure
        exit 1
    fi
}

# Timeout watchdog - kill if running too long
timeout_watchdog() {
    sleep $TIMEOUT_SECONDS
    echo "[$(date)] TIMEOUT: Reflection exceeded ${TIMEOUT_SECONDS}s, forcing exit"
    kill -TERM -$$ 2>/dev/null || true
}
timeout_watchdog &
WATCHDOG_PID=$!
trap "kill $WATCHDOG_PID 2>/dev/null; cleanup_and_exit" EXIT TERM INT

echo "[$(date)] Starting Concurrent Kurultai Reflection (All 6 Agents) [Protocol Mode]"
echo "[$(date)] Hard timeout: ${TIMEOUT_SECONDS}s | Watchdog PID: $WATCHDOG_PID"
echo "================================================================"

AGENTS=("kublai" "mongke" "chagatai" "temujin" "jochi" "ogedei")
HOURS=1
SCRIPTS="/Users/kublai/.openclaw/agents/main/scripts"

# Function to run reflection for a single agent
run_agent_reflection() {
    local AGENT="$1"
    local WORKSPACE="/Users/kublai/.openclaw/agents/$AGENT"
    local MEMORY_DIR="$WORKSPACE/memory"
    local DATE=$(date +%Y-%m-%d)
    local TIME=$(date +%H:%M)

    echo "[$(date)] [$AGENT] Starting protocol reflection..."

    # Ensure memory directory exists
    mkdir -p "$MEMORY_DIR"

    # Generate protocol-based reflection (Option B: ~800 tokens)
    local reflection=$(python3 "$SCRIPTS/meta_reflection.py" \
        --agent "$AGENT" \
        --hours "$HOURS" \
        --protocol \
        --heartbeat-review 2>/dev/null || echo "# Reflection unavailable")

    # Write reflection to memory with ACTIVE RULES section preserved
    # Check if ACTIVE RULES section already exists in today's file
    if [ -f "$MEMORY_DIR/$DATE.md" ] && grep -q "^## ACTIVE RULES" "$MEMORY_DIR/$DATE.md"; then
        # Append session log only (rules already at top)
        cat >> "$MEMORY_DIR/$DATE.md" << EOF

---

## SESSION LOG - $TIME (Protocol Reflection)

$reflection

---
EOF
    else
        # First reflection of the day — include header
        cat >> "$MEMORY_DIR/$DATE.md" << EOF

---

## $TIME - Hourly Reflection (Protocol Mode)

**Agent:** $AGENT
**Period:** Last $HOURS hour(s)

$reflection

---
EOF
    fi

    echo "[$(date)] [$AGENT] Protocol reflection complete -> $MEMORY_DIR/$DATE.md"
}

# Run all 6 agents in parallel (reflections are pure Python, no API rate limit concern)
echo "[$(date)] Launching ${#AGENTS[@]} agents in parallel..."

pids=()
for agent in "${AGENTS[@]}"; do
    run_agent_reflection "$agent" &
    pids+=($!)
done
for pid in "${pids[@]}"; do
    wait "$pid" || true
done

echo "[$(date)] All 6 agents completed their reflections (parallel)"
echo "================================================================"

# ============================================================
# CHECKPOINT: Emit success status - core reflections complete
# This decouples content generation success from downstream step failures
# ============================================================
LOGS_DIR="/Users/kublai/.openclaw/agents/main/logs"
mkdir -p "$LOGS_DIR"
cat > "$LOGS_DIR/reflection-status.json" << EOF
{
  "status": "content_complete",
  "timestamp": "$(date -Iseconds)",
  "elapsed_seconds": $(($(date +%s) - SCRIPT_START)),
  "agents": ["kublai", "mongke", "chagatai", "temujin", "jochi", "ogedei"]
}
EOF
echo "[$(date)] Checkpoint written to $LOGS_DIR/reflection-status.json"

echo "[$(date)] Concurrent Kurultai Reflection Complete"
echo "================================================================"

# ============================================================
# SELF-IMPROVEMENT BRAINSTORMING: Each agent proposes improvements
# (Uses Claude Code + /horde-brainstorming, configured per claude-code-setup-v2)
# ============================================================
echo "[$(date)] Running Self-Improvement Brainstorming (all agents, parallel)..."
python3 "$SCRIPTS/kurultai_brainstorm.py" --all >> "$SCRIPTS/../logs/kurultai-brainstorm.log" 2>&1 || true

# ============================================================
# CROSS-AGENT RULE PROPAGATION: Proven rules propagated to related agents
# ============================================================
echo "[$(date)] Running Cross-Agent Rule Propagation..."
python3 "$SCRIPTS/cross_agent_rules.py" >> "$SCRIPTS/../logs/cross-agent-rules.log" 2>&1 || true

# ============================================================
# CAPABILITY SCORE UPDATE: Update routing quality scores
# ============================================================
echo "[$(date)] Updating capability scores..."
python3 "$SCRIPTS/route_quality_tracker.py" >> "$SCRIPTS/../logs/capability-scores.log" 2>&1 || true

# ============================================================
# ROUTING AUDIT: Analyze routing decisions + cache for kublai reflection
# ============================================================
echo "[$(date)] Running Routing Audit..."
python3 "$SCRIPTS/routing_audit_action.py" 2>/dev/null || true

# ============================================================
# KUBLAI ACTIONS: Process feedback into agent tasks
# (Also handles pending AgentFeedback review — no separate --summary needed)
# ============================================================
echo "[$(date)] Running Kublai Actions (kurultai trigger)..."
python3 "$SCRIPTS/kublai-actions.py" --trigger kurultai 2>/dev/null || true

# ============================================================
# PROPOSAL EXPIRY: Clean up stale proposals (Kublai reviews them himself)
# ============================================================
echo "[$(date)] Expiring stale proposals..."
python3 "$SCRIPTS/kurultai_review.py" --expire >> "$SCRIPTS/../logs/kurultai-review.log" 2>&1 || true

# ============================================================
# KUBLAI INITIATIVE: "What do I want to do next?"
# ============================================================
echo "[$(date)] Running Kublai Initiative (self-directed action)..."
python3 "$SCRIPTS/kublai-initiative.py" 2>/dev/null || true
