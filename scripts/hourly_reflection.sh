#!/bin/bash
# Concurrent Kurultai Reflection - All 6 Agents Reflect Simultaneously
# Runs every hour with all agents reflecting in parallel

set -e

echo "[$(date)] Starting Concurrent Kurultai Reflection (All 6 Agents)"
echo "================================================================"

# All 6 agents reflect concurrently
AGENTS=("kublai" "mongke" "chagatai" "temujin" "jochi" "ogedei")
HOURS=1
CHAT_HOURS=2

# Function to run reflection for a single agent (runs in background)
run_agent_reflection() {
    local AGENT="$1"
    local WORKSPACE="/Users/kublai/.openclaw/agents/$AGENT"
    local MEMORY_DIR="$WORKSPACE/memory"
    local DATE=$(date +%Y-%m-%d)
    local TIME=$(date +%H:%M)
    
    echo "[$(date)] [$AGENT] Starting reflection..."
    
    # Ensure memory directory exists
    mkdir -p "$MEMORY_DIR"
    
    # Get task metrics from Neo4j
    local task_metrics=$(python3 /Users/kublai/.openclaw/agents/main/scripts/reflection_data.py \
        --agent "$AGENT" \
        --hours "$HOURS" 2>/dev/null || echo '{"tasks":{"total":0}}')
    
    # Generate meta-reflection with chat review and heartbeat task review
    local reflection=$(python3 /Users/kublai/.openclaw/agents/main/scripts/meta_reflection.py \
        --agent "$AGENT" \
        --hours "$HOURS" \
        --chat-review \
        --chat-hours "$CHAT_HOURS" \
        --heartbeat-review 2>/dev/null || echo "# Reflection unavailable")
    
    # Write reflection to memory
    cat >> "$MEMORY_DIR/$DATE.md" << EOF

---

## $TIME - Hourly Reflection (Concurrent Kurultai)

**Agent:** $AGENT  
**Period:** Last $HOURS hour(s)  
**Chat Review:** Last $CHAT_HOURS hours

$reflection

---
EOF
    
    echo "[$(date)] [$AGENT] Reflection complete → $MEMORY_DIR/$DATE.md"
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

# List pending feedback for Kublai
echo ""
echo "Pending Feedback for Kublai:"
python3 /Users/kublai/.openclaw/agents/main/scripts/kublai_review_feedback.py --list 2>/dev/null || echo "(none)"
echo ""
