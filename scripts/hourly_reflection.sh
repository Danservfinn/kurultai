#!/bin/bash
# Concurrent Kurultai Reflection - All 6 Agents Reflect Simultaneously
# Runs every hour with all agents reflecting in parallel
#
# Option B: Protocol-based reflections (~800 tokens/agent vs ~6400 legacy)
# - Role-specific protocols with WHEN/THEN behavioral rules
# - Commitment tracking across sessions
# - Tock data replaces redundant CLI calls

set -e

echo "[$(date)] Starting Concurrent Kurultai Reflection (All 6 Agents) [Protocol Mode]"
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

# Run all 6 agents sequentially in a cascade
echo "[$(date)] Launching ${#AGENTS[@]} agents sequentially (cascade)..."

for agent in "${AGENTS[@]}"; do
    run_agent_reflection "$agent"
    # Small pause between agents to prevent API rate limits
    sleep 5
done

echo "[$(date)] All 6 agents completed their reflections sequentially"
echo "================================================================"

# Generate Kublai summary
echo "[$(date)] Generating Kublai review summary..."
python3 /Users/kublai/.openclaw/agents/main/scripts/kublai_review_feedback.py --summary 2>/dev/null || true

echo "[$(date)] Concurrent Kurultai Reflection Complete"
echo "================================================================"

# ============================================================
# KUBLAI ACTIONS: Process feedback into agent tasks
# ============================================================
echo "[$(date)] Running Kublai Actions (kurultai trigger)..."
python3 /Users/kublai/.openclaw/agents/main/scripts/kublai-actions.py --trigger kurultai 2>/dev/null || true

# List pending feedback for Kublai
echo ""
echo "Pending Feedback for Kublai:"
python3 /Users/kublai/.openclaw/agents/main/scripts/kublai_review_feedback.py --list 2>/dev/null || echo "(none)"
echo ""
