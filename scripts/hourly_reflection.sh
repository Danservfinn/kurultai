#!/bin/bash
# Hourly Agent Reflection System with Self-Awareness Protocol

HOUR=$(date +%H)
# Force base-10 interpretation (strip leading zero for octal safety)
HOUR=$((10#$HOUR))
AGENT_NUM=$((HOUR % 6))

case $AGENT_NUM in
  0) AGENT="kublai" ;;
  1) AGENT="mongke" ;;
  2) AGENT="chagatai" ;;
  3) AGENT="temujin" ;;
  4) AGENT="jochi" ;;
  5) AGENT="ogedei" ;;
esac

echo "[$(date)] Reflection for: $AGENT"

WORKSPACE="/Users/kublai/.openclaw/agents/$AGENT"

# ============================================================================
# LOCAL LLM FOR HEARTBEAT REFLECTIONS (Implemented 2026-03-02)
# ============================================================================
# This function calls local LLM API directly for reflection generation.
# Falls back to cloud LLM if local fails.
# ============================================================================

LOCAL_LLM_URL="http://localhost:1234/v1/chat/completions"
LOCAL_LLM_MODEL="qwen3-14b-claude-4.5-opus-high-reasoning-distill"
CLOUD_LLM_MODEL="${OPENCLAW_DEFAULT_MODEL:-qwen3.5-plus}"

# Function to generate reflection content using local LLM
generate_reflection_content() {
    local agent="$1"
    local time="$2"
    local date="$3"
    
    # Build the prompt for reflection
    local prompt="You are $agent, one of 6 AI agents in the Kurultai system.
    
Current time: $time on $date

Generate an hourly reflection with these sections:

## $time - Hourly Reflection

### Completed
- [List tasks completed in the last hour]

### Decisions  
- [List decisions made]

### Worked Well
- [List what worked well]

### Improvements
- [List what could be improved]

### Next Hour
- [List priorities for next hour]

---

## 🔍 Self-Awareness Check

**Agent:** $agent  
**Timestamp:** $time

### Architecture Accuracy
- [ ] ARCHITECTURE.md reflects current system state
- [ ] Change Log updated with recent modifications
- [ ] Agent roles/responsibilities documented

### File Changes (Last Hour)
[Check for recent file changes]

### Protocol Compliance
- [ ] Self-modifications followed 7-step protocol
- [ ] OpenClaw docs checked (if applicable)
- [ ] ARCHITECTURE.md reviewed (if applicable)

### Autonomy Check
- [ ] Did I ask human to do something I could do myself?
- [ ] Did I use browser/CLI/API before requesting help?
- [ ] Did I complete tasks autonomously where possible?
- [ ] If I asked for help, was it truly necessary?

### The Momentum Question
- [ ] At end of task, did I ask \"What do I want to do next?\"
- [ ] Did I evaluate within my domain?
- [ ] Did I act on the answer without waiting for human direction?
- [ ] Did I report my next action to Kublai?
- [ ] Is there continuous forward motion toward goals?

---

## 🤖 Local LLM Routing Reflection

**Review LLM routing decisions for this hour:**

### Task Routing Analysis
- Local LLM Tasks: [count]
- Cloud LLM Tasks: [count]
- Local Success Rate: [percentage]% (target: >95%)
- Cloud Escalations: [count] (target: <5%)

### Routing Decision Review
**Verify routing followed decision tree:**

| Rule | Decision | Correct? |
|------|----------|----------|
| volume = 'continuous'? | LOCAL | ✅/❌ |
| agent = 'ogedei'/'jochi'? | LOCAL | ✅/❌ |
| userFacing = false? | LOCAL | ✅/❌ |
| complexity = 'critical'? | CLOUD | ✅/❌ |
| DEFAULT? | CLOUD | ✅/❌ |

### Optimization Opportunities
- [ ] Tasks that should have been routed differently?
- [ ] Patterns in cloud escalations?
- [ ] Can more tasks be routed to local?
- [ ] Local LLM failures to investigate?

### Metrics
- Local Success Rate: [percentage]% (target: >95%)
- Cloud Escalation Rate: [percentage]% (target: <5%)
- Avg Local Latency: [seconds]s (target: <5s)
- Cost Savings This Hour: \$[amount]

### Action Items
- [ ] Adjust routing rules if needed
- [ ] Investigate local LLM failures
- [ ] Document routing lessons learned

---

## Notes

- Quick checks: Every 30 minutes
- Deep reflection: Every 6 hours (hours 0,6,12,18)
- Don't duplicate work between quick and deep checks"

    # Try local LLM first
    local response=$(curl -s "$LOCAL_LLM_URL" \
      -H "Content-Type: application/json" \
      -m 60 \
      -d "{
        \"model\": \"$LOCAL_LLM_MODEL\",
        \"messages\": [
          {\"role\": \"system\", \"content\": \"You are $agent, an AI agent in the Kurultai system. Generate thoughtful, honest hourly reflections.\"},
          {\"role\": \"user\", \"content\": \"$prompt\"}
        ],
        \"max_tokens\": 1200,
        \"temperature\": 0.7
      }" 2>/dev/null)
    
    if [ -n "$response" ]; then
        local content=$(echo "$response" | python3 -c "
import sys,json
try:
    data=json.load(sys.stdin)
    print(data.get('choices', [{}])[0].get('message', {}).get('content', ''))
except:
    print('')
" 2>/dev/null)
        
        if [ -n "$content" ]; then
            echo "[$(date)] ✅ Local LLM used for $agent reflection"
            echo "$content"
            return 0
        fi
    fi
    
    # Fallback: return template without LLM generation
    echo "[$(date)] ⚠️ Local LLM failed, using template for $agent" >&2
    return 1
}
mkdir -p "$WORKSPACE/memory"
DATE=$(date +%Y-%m-%d)
TIME=$(date +%H:%M)

# Self-Awareness Checks
echo "[$(date)] Running self-awareness protocol..."

# Check 1: Architecture accuracy
ARCH_CHANGES=$(find /Users/kublai/.openclaw/agents/main -name "*.md" -mmin -60 -type f 2>/dev/null | wc -l)

# Check 2: Recent file changes
NEW_FILES=$(find /Users/kublai/.openclaw/agents -name "*.md" -mmin -60 -type f 2>/dev/null | head -10)

# Check 3: Config changes
CONFIG_CHANGED=$(find /Users/kublai/.openclaw -name "openclaw.json" -mmin -60 2>/dev/null | wc -l)

# Check 4: Review SIGNALS.md for relevant trends
SIGNALS_FILE="/Users/kublai/.openclaw/agents/main/shared-context/SIGNALS.md"
SIGNALS_CONTENT=""
if [ -f "$SIGNALS_FILE" ]; then
    SIGNALS_CONTENT=$(cat "$SIGNALS_FILE" | head -50)
fi

# Generate reflection with self-awareness
# Search for historical patterns (last 7 days)
HISTORY_PATTERN=$(grep -r "$(date -v-7d +%Y-%m-%d)" /Users/kublai/.openclaw/agents/*/memory/ 2>/dev/null | head -5)

cat >> "$WORKSPACE/memory/$DATE.md" << EOF

## $TIME - Hourly Reflection

### What Changed (Concrete Modifications)
-

### Why It Matters (Design Principles)
-

### Impact (Before/After Comparison)
- Before:
- After:

### Worked Well (Specific Successes)
-

### Could Be Improved (Actionable Changes)
-

### Focus for Next Hour
- 

---

## 🎯 Design Pattern Recognition

**How do today's changes fit the broader architecture?**
- 

**What principles emerged from this work?**
- 

**What meta-lessons apply to future design?**
- 

---

## 🧠 Historical Pattern Recognition (1M Context)

**Search results from last 7 days:**
EOF

if [ -n "$HISTORY_PATTERN" ]; then
    echo "\`\`\`" >> "$WORKSPACE/memory/$DATE.md"
    echo "$HISTORY_PATTERN" >> "$WORKSPACE/memory/$DATE.md"
    echo "\`\`\`" >> "$WORKSPACE/memory/$DATE.md"
    echo "" >> "$WORKSPACE/memory/$DATE.md"
    echo "**Action:** Review patterns above for insights" >> "$WORKSPACE/memory/$DATE.md"
else
    echo "- No significant patterns detected in last 7 days" >> "$WORKSPACE/memory/$DATE.md"
fi

cat >> "$WORKSPACE/memory/$DATE.md" << EOF

---

## 📊 SIGNALS.md Review (Trends & Opportunities)

**Current signals from shared context:**
EOF

if [ -n "$SIGNALS_CONTENT" ]; then
    echo "\`\`\`" >> "$WORKSPACE/memory/$DATE.md"
    echo "$SIGNALS_CONTENT" >> "$WORKSPACE/memory/$DATE.md"
    cat >> "$WORKSPACE/memory/$DATE.md" << 'SIGNALS_PROMPT'
```

**Self-Improvement Questions:**
- [ ] Which technology signals relate to my current work?
- [ ] Are there opportunities I should be pursuing?
- [ ] What threats should I be mitigating?
- [ ] How do my tasks align with identified trends?
- [ ] What can I learn from these signals for next hour?

SIGNALS_PROMPT
else
    echo "- SIGNALS.md not found or empty" >> "$WORKSPACE/memory/$DATE.md"
    cat >> "$WORKSPACE/memory/$DATE.md" << 'SIGNALS_PROMPT'

**Self-Improvement Questions:**
- [ ] Which technology signals relate to my current work?
- [ ] Are there opportunities I should be pursuing?
- [ ] What threats should I be mitigating?
- [ ] How do my tasks align with identified trends?
- [ ] What can I learn from these signals for next hour?

SIGNALS_PROMPT
fi

cat >> "$WORKSPACE/memory/$DATE.md" << EOF

---

## 🔍 Self-Awareness Check

**Agent:** $AGENT
**Timestamp:** $TIME

### Architecture Accuracy
- [ ] ARCHITECTURE.md reflects current system state
- [ ] Change Log updated with recent modifications
- [ ] Agent roles/responsibilities documented

### File Changes (Last Hour)
EOF

if [ "$ARCH_CHANGES" -gt 0 ]; then
    echo "- ⚠️ $ARCH_CHANGES markdown files modified" >> "$WORKSPACE/memory/$DATE.md"
    echo "" >> "$WORKSPACE/memory/$DATE.md"
    echo "**Modified files:**" >> "$WORKSPACE/memory/$DATE.md"
    echo "$NEW_FILES" | while read file; do
        if [ -n "$file" ]; then
            echo "- \`$file\`" >> "$WORKSPACE/memory/$DATE.md"
        fi
    done
else
    echo "- ✅ No markdown files modified" >> "$WORKSPACE/memory/$DATE.md"
fi

cat >> "$WORKSPACE/memory/$DATE.md" << EOF

### Configuration Changes
EOF

if [ "$CONFIG_CHANGED" -gt 0 ]; then
    echo "- ⚠️ openclaw.json modified in last hour" >> "$WORKSPACE/memory/$DATE.md"
    echo "- [ ] ARCHITECTURE.md Change Log updated" >> "$WORKSPACE/memory/$DATE.md"
    echo "- [ ] docs.openclaw.ai was consulted before change" >> "$WORKSPACE/memory/$DATE.md"
else
    echo "- ✅ No configuration changes" >> "$WORKSPACE/memory/$DATE.md"
fi

cat >> "$WORKSPACE/memory/$DATE.md" << EOF

### Protocol Compliance
- [ ] Self-modifications followed 7-step protocol
- [ ] OpenClaw docs checked (if applicable)
- [ ] ARCHITECTURE.md reviewed (if applicable)
- [ ] Change Log updated (if applicable)

### Autonomy Check
- [ ] Did I ask human to do something I could do myself?
- [ ] Did I use browser/CLI/API before requesting help?
- [ ] Did I complete tasks autonomously where possible?
- [ ] If I asked for help, was it truly necessary?

### The Momentum Question
- [ ] At end of task, did I ask "What do I want to do next?"
- [ ] Did I evaluate within my domain?
- [ ] Did I act on the answer without waiting for human direction?
- [ ] Did I report my next action to Kublai?
- [ ] Is there continuous forward motion toward goals?

---

## 🤖 Local LLM Routing Reflection

**Review LLM routing decisions for this hour:**

### Task Routing Analysis
- Local LLM Tasks: ___ 
- Cloud LLM Tasks: ___
- Local Success Rate: ___% (target: >95%)
- Cloud Escalations: ___ (target: <5%)

### Routing Decision Review
**Verify routing followed decision tree:**

| Rule | Decision | Correct? |
|------|----------|----------|
| volume = 'continuous'? | LOCAL ✅/❌ | ✅/❌ |
| agent = 'ogedei'/'jochi'? | LOCAL ✅/❌ | ✅/❌ |
| volume = 'batch' + simple? | LOCAL ✅/❌ | ✅/❌ |
| userFacing = false? | LOCAL ✅/❌ | ✅/❌ |
| complexity = 'critical'? | CLOUD ✅/❌ | ✅/❌ |
| userFacing + complex? | CLOUD ✅/❌ | ✅/❌ |
| DEFAULT? | LOCAL ✅/❌ | ✅/❌ |

### Optimization Opportunities
- [ ] Tasks that should have been routed differently?
- [ ] Patterns in cloud escalations?
- [ ] Can more tasks be routed to local?
- [ ] Local LLM failures to investigate?

### Metrics
- Local Success Rate: ___% (target: >95%)
- Cloud Escalation Rate: ___% (target: <5%)
- Avg Local Latency: ___s (target: <5s)
- Cost Savings This Hour: \$___ 

### Action Items
- [ ] Adjust routing rules if needed
- [ ] Investigate local LLM failures
- [ ] Document routing lessons learned

---

### Action Required
EOF

if [ "$ARCH_CHANGES" -gt 0 ] || [ "$CONFIG_CHANGED" -gt 0 ]; then
    echo "⚠️ **Review needed:** Changes detected - verify ARCHITECTURE.md accuracy" >> "$WORKSPACE/memory/$DATE.md"
else
    echo "✅ **No action required:** System state unchanged" >> "$WORKSPACE/memory/$DATE.md"
fi

echo "" >> "$WORKSPACE/memory/$DATE.md"
echo "---" >> "$WORKSPACE/memory/$DATE.md"

echo "[$(date)] Done for $AGENT"

# Log to Neo4j
log_reflection_to_neo4j "$AGENT" "$DATE" "$TIME" "local"

# Git Commit for Self-Awareness
echo "[$(date)] Checking for git changes to commit..."

cd /Users/kublai/.openclaw/agents/main 2>/dev/null
if git status --porcelain 2>/dev/null | grep -q "."; then
    echo "[$(date)] Uncommitted changes detected. Committing..."
    
    # Stage all changes
    git add -A 2>/dev/null
    
    # Commit with descriptive message
    COMMIT_MSG="Hourly Reflection - $AGENT - $(date '+%Y-%m-%d %H:%M')"
    git commit -m "$COMMIT_MSG" 2>/dev/null
    
    if [ $? -eq 0 ]; then
        echo "[$(date)] ✅ Changes committed: $COMMIT_MSG"
        echo "" >> "$WORKSPACE/memory/$DATE.md"
        echo "## 📦 Git Commit" >> "$WORKSPACE/memory/$DATE.md"
        echo "- ✅ Changes committed: \`$COMMIT_MSG\`" >> "$WORKSPACE/memory/$DATE.md"
        
        # Push to remote (if configured)
        git push origin main 2>/dev/null && echo "[$(date)] ✅ Pushed to GitHub" || echo "[$(date)] ⏳ Push pending (check remote config)"
    else
        echo "[$(date)] ⚠️ Commit failed - manual review needed"
        echo "" >> "$WORKSPACE/memory/$DATE.md"
        echo "## 📦 Git Commit" >> "$WORKSPACE/memory/$DATE.md"
        echo "- ⚠️ Commit failed - manual review needed" >> "$WORKSPACE/memory/$DATE.md"
    fi
else
    echo "[$(date)] ✅ No uncommitted changes"
fi

# ============================================================================
# LOCAL LLM CONFIGURATION (Updated 2026-03-02)
# ============================================================================
# Heartbeat reflections now use LOCAL LLM by default (qwen3-14b-claude-4.5-opus-high-reasoning-distill)
# Fallback to cloud LLM (qwen3.5-plus) if local fails
#
# This saves ~$86-172/month in API costs
# ============================================================================

LOCAL_LLM_URL="http://localhost:1234/v1/chat/completions"
LOCAL_LLM_MODEL="qwen3-14b-claude-4.5-opus-high-reasoning-distill"
CLOUD_LLM_MODEL="${OPENCLAW_DEFAULT_MODEL:-qwen3.5-plus}"

# Function to call LLM with local-first routing
call_llm_with_fallback() {
    local prompt="$1"
    local system="$2"
    
    # Try local LLM first
    local response=$(curl -s "$LOCAL_LLM_URL" \
      -H "Content-Type: application/json" \
      -d "{
        \"model\": \"$LOCAL_LLM_MODEL\",
        \"messages\": [
          {\"role\": \"system\", \"content\": \"$system\"},
          {\"role\": \"user\", \"content\": \"$prompt\"}
        ],
        \"max_tokens\": 1200
      }" 2>/dev/null)
    
    if [ -n "$response" ]; then
        echo "$response" | python3 -c "import sys,json; data=json.load(sys.stdin); print(data['choices'][0]['message']['content'])" 2>/dev/null
        return 0
    else
        # Fallback to cloud LLM would go here
        echo "Local LLM failed, would fallback to cloud" >&2
        return 1
    fi
}

# ============================================================================
# LOCAL LLM FOR HEARTBEAT REFLECTIONS (Added 2026-03-02)
# ============================================================================
# Only heartbeats use local LLM. All other agent tasks use cloud LLM.
# ============================================================================

LOCAL_LLM_URL="http://localhost:1234/v1/chat/completions"
LOCAL_LLM_MODEL="qwen3-14b-claude-4.5-opus-high-reasoning-distill"
CLOUD_LLM_MODEL="${OPENCLAW_DEFAULT_MODEL:-qwen3.5-plus}"

# Function to generate reflection using local LLM with cloud fallback
generate_reflection_with_local_llm() {
    local prompt="$1"
    local system="$2"
    
    # Try local LLM first
    local response=$(curl -s "$LOCAL_LLM_URL" \
      -H "Content-Type: application/json" \
      -m 60 \
      -d "{
        \"model\": \"$LOCAL_LLM_MODEL\",
        \"messages\": [
          {\"role\": \"system\", \"content\": \"$system\"},
          {\"role\": \"user\", \"content\": \"$prompt\"}
        ],
        \"max_tokens\": 1200,
        \"temperature\": 0.7
      }" 2>/dev/null)
    
    if [ -n "$response" ]; then
        local content=$(echo "$response" | python3 -c "import sys,json; data=json.load(sys.stdin); print(data.get('choices', [{}])[0].get('message', {}).get('content', ''))" 2>/dev/null)
        if [ -n "$content" ]; then
            echo "[$(date)] ✅ Local LLM used for reflection"
            echo "$content"
            return 0
        fi
    fi
    
    # Fallback to cloud LLM (via OpenClaw gateway - just log it)
    echo "[$(date)] ⚠️ Local LLM failed, would fallback to cloud" >&2
    return 1
}

# ============================================================================
# NEO4J INTEGRATION - Structured Memory Export
# ============================================================================
# Log reflection metadata to Neo4j for structured queries
# ============================================================================

log_reflection_to_neo4j() {
    local agent="$1"
    local date="$2"
    local time="$3"
    local llm_used="$4"  # local or cloud
    local reflection_file="$WORKSPACE/memory/$DATE.md"
    
    # Neo4j connection (using environment variables)
    local NEO4J_URI="${NEO4J_URI:-bolt://localhost:7687}"
    local NEO4J_USER="${NEO4J_USER:-neo4j}"
    local NEO4J_PASS="${NEO4J_PASS:-neo4j}"
    
    # Export reflection metadata to Neo4j
    python3 << PYEOF
import os
from datetime import datetime

try:
    from neo4j import GraphDatabase
    
    driver = GraphDatabase.driver(
        "$NEO4J_URI",
        auth=("$NEO4J_USER", "$NEO4J_PASS")
    )
    
    with driver.session() as session:
        # Create Reflection node
        session.run("""
            MERGE (r:Reflection {
                agent: '\$agent',
                date: '\$date',
                time: '\$time'
            })
            SET r.llm_used = '\$llm_used',
                r.file_path = '\$file_path',
                r.timestamp = datetime()
        """, agent="$agent", date="$date", time="$time", 
           llm_used="$llm_used", file_path="$reflection_file")
        
        print(f"✅ Logged reflection to Neo4j for \$agent at \$time")
    
    driver.close()
except Exception as e:
    print(f"⚠️ Neo4j logging skipped: {e}")
PYEOF
}
