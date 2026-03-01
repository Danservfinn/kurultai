#!/bin/bash
# Hourly Agent Reflection System with Self-Awareness Protocol

HOUR=$(date +%H)
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
