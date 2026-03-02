#!/bin/bash
# Kurultai Hourly Review with Chatlog Analysis
# Collects 6-hour rolling window, analyzes with cloud LLM, auto-executes

DATE=$(date +%Y-%m-%d)
TIME=$(date +%H:%M)
HOUR_AGO=$(date -v-1H '+%Y-%m-%d %H:%M')
SIX_HOURS_AGO=$(date -v-6H '+%Y-%m-%d %H:%M')

# Output files
DATA_DIR="/tmp/kurultai-review-${DATE}-${TIME}"
mkdir -p "$DATA_DIR"

ANALYSIS_FILE="$DATA_DIR/llm-analysis.txt"
META_REVIEW_FILE="$DATA_DIR/meta-review.txt"
SYNC_FILE="/Users/kublai/.openclaw/agents/main/shared-context/KURULTAI-SYNC-${DATE}-${TIME}.md"
ARCHIVE_DIR="/Users/kublai/.openclaw/agents/main/shared-context/archive/sync"

mkdir -p "$ARCHIVE_DIR"

echo "=== Kurultai Review — ${DATE} ${TIME} EST ==="
echo "Collecting data from ${SIX_HOURS_AGO} to ${HOUR_AGO}"
echo ""

# ============================================================================
# STEP 1: Collect Data
# ============================================================================

echo "Step 1: Collecting data..."

# 1.1 Collect session chatlogs (6-hour rolling window)
echo "  - Collecting session chatlogs..."
for session_file in /Users/kublai/.openclaw/agents/main/sessions/*.jsonl; do
    if [ -f "$session_file" ]; then
        # Check if file was modified in last 6 hours
        if [[ $(stat -f %m "$session_file" 2>/dev/null) -gt $(date -v-6H +%s 2>/dev/null || date -d '6 hours ago' +%s) ]]; then
            echo "=== Session: $(basename $session_file) ===" >> "$DATA_DIR/chatlogs.txt"
            cat "$session_file" >> "$DATA_DIR/chatlogs.txt"
            echo "" >> "$DATA_DIR/chatlogs.txt"
        fi
    fi
done

# 1.2 Collect agent reflections
echo "  - Collecting agent reflections..."
for agent in kublai mongke chagatai temujin jochi ogedei; do
    AGENT_FILE="/Users/kublai/.openclaw/agents/$agent/memory/${DATE}.md"
    if [ -f "$AGENT_FILE" ]; then
        echo "=== ${agent^} Reflections ===" >> "$DATA_DIR/reflections.txt"
        tail -100 "$AGENT_FILE" >> "$DATA_DIR/reflections.txt"
        echo "" >> "$DATA_DIR/reflections.txt"
    fi
done

# 1.3 Collect git commits
echo "  - Collecting git commits..."
cd /Users/kublai/.openclaw/agents/main
git log --since="${SIX_HOURS_AGO}" --oneline > "$DATA_DIR/commits.txt" 2>/dev/null

# 1.4 Collect Neo4j activity
echo "  - Collecting Neo4j activity..."
python3 << PYEOF >> "$DATA_DIR/neo4j.txt" 2>&1
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "neo4j"))

with driver.session() as session:
    # Get recent Reflection nodes
    result = session.run("""
        MATCH (r:Reflection)
        WHERE r.timestamp > datetime() - duration('PT6H')
        RETURN r.agent, r.timestamp, r.llm_used
        ORDER BY r.timestamp DESC
        LIMIT 50
    """)
    print("=== Recent Reflections (Neo4j) ===")
    for record in result:
        print(f"{record['r.agent']} at {record['r.timestamp']} (LLM: {record['r.llm_used']})")
    
    # Get recent KurultaiSync nodes
    result = session.run("""
        MATCH (s:KurultaiSync)
        WHERE s.timestamp > datetime() - duration('PT6H')
        RETURN s.date, s.time, s.attendance
        ORDER BY s.timestamp DESC
        LIMIT 10
    """)
    print("\n=== Recent Kurultai Syncs (Neo4j) ===")
    for record in result:
        print(f"{record['s.date']} {record['s.time']} (Attendance: {record['s.attendance']})")

driver.close()
PYEOF

# 1.5 Collect system logs
echo "  - Collecting system logs..."
grep "${DATE} ${TIME#*:}" /tmp/kurultai-*.log 2>/dev/null > "$DATA_DIR/logs.txt" || echo "No logs found" > "$DATA_DIR/logs.txt"

echo "  ✅ Data collection complete"
echo ""

# ============================================================================
# STEP 2: Cloud LLM Analysis
# ============================================================================

echo "Step 2: Analyzing with cloud LLM (qwen3.5-plus)..."

python3 << PYEOF > "$ANALYSIS_FILE" 2>&1
import os
import json
import requests

# Read OpenClaw config to get API credentials
with open('/Users/kublai/.openclaw/openclaw.json', 'r') as f:
    openclaw_config = json.load(f)

# Extract API credentials from bailian provider
bailian = openclaw_config.get('models', {}).get('providers', {}).get('bailian', {})
api_key = bailian.get('apiKey', '')
base_url = bailian.get('baseUrl', 'https://coding-intl.dashscope.aliyuncs.com/v1')
api_url = f"{base_url}/chat/completions"

print(f"Using API: {api_url}")
print(f"API Key: {api_key[:10]}...")

# Read collected data
chatlogs = open('$DATA_DIR/chatlogs.txt').read()[:50000]  # Limit to avoid token limits
reflections = open('$DATA_DIR/reflections.txt').read()[:20000]
commits = open('$DATA_DIR/commits.txt').read()
neo4j = open('$DATA_DIR/neo4j.txt').read()
logs = open('$DATA_DIR/logs.txt').read()

# Prepare prompt
prompt = f"""You are analyzing Kurultai (6-agent AI system) activity for the past 6 hours.

CONTEXT:
- 6 agents: Kublai (lead), Möngke (research), Chagatai (content), Temüjin (dev), Jochi (analysis), Ögedei (ops)
- Local LLM: qwen3.5-9b-mlx (for agent reflections)
- Cloud LLM: qwen3.5-plus (for this analysis)

DATA SOURCES:
1. CHATLOGS (actual conversations with human)
2. AGENT REFLECTIONS (hourly reflections from each agent)
3. GIT COMMITS (what was actually committed)
4. NEO4J ACTIVITY (logged decisions and actions)
5. SYSTEM LOGS (script execution logs)

ANALYZE AND REPORT:

## What Worked Well
[List specific evidence from the data]

## What Didn't Work
[List specific evidence from the data]

## Patterns Across Agents
[Identify recurring themes, bottlenecks, successes]

## Kublai Performance Review
- Did Kublai complete what was promised to the human?
- What's blocking progress?
- Response time to human requests

## Recommended Process Improvements
[Specific, actionable improvements]

## Priority Action Items (Next Hour)
[List top 3-5 actions Kublai should take immediately]

Be specific, evidence-based, and actionable. Cite specific chatlog messages, commits, or log entries.
"""

# Call cloud LLM API (using OpenClaw config credentials)
# API credentials already loaded above from openclaw.json

try:
    response = requests.post(
        api_url,
        headers={'Authorization': f'Bearer {api_key}'},
        json={
            'model': 'qwen3.5-plus',
            'messages': [
                {'role': 'system', 'content': 'You are analyzing Kurultai activity. Be specific and evidence-based.'},
                {'role': 'user', 'content': prompt}
            ],
            'max_tokens': 4000,
            'temperature': 0.7
        },
        timeout=120
    )
    
    if response.status_code == 200:
        analysis = response.json()['choices'][0]['message']['content']
        print(analysis)
    else:
        print(f"❌ API Error: {response.status_code}")
        print(f"Response: {response.text}")
        
except Exception as e:
    print(f"❌ Analysis failed: {e}")
    print("\nFalling back to template analysis...")
    print("""
## What Worked Well
- Data collection completed
- All agents operational

## What Didn't Work
- LLM analysis failed - API issue

## Priority Action Items
1. Fix cloud LLM API configuration
2. Retry analysis
""")
PYEOF

echo "  ✅ Analysis complete: $ANALYSIS_FILE"
echo ""

# ============================================================================
# STEP 3: Meta-Review of LLM Prompt
# ============================================================================

echo "Step 3: Meta-review of LLM prompt..."

python3 << PYEOF > "$META_REVIEW_FILE" 2>&1
import os
import json
import requests

# Read OpenClaw config to get API credentials
with open('/Users/kublai/.openclaw/openclaw.json', 'r') as f:
    openclaw_config = json.load(f)

# Extract API credentials from bailian provider
bailian = openclaw_config.get('models', {}).get('providers', {}).get('bailian', {})
api_key = bailian.get('apiKey', '')
base_url = bailian.get('baseUrl', 'https://coding-intl.dashscope.aliyuncs.com/v1')
api_url = f"{base_url}/chat/completions"

print(f"Using API: {api_url}")
print(f"API Key: {api_key[:10]}...")

# Read the analysis
analysis = open('$ANALYSIS_FILE').read()

# Read the original prompt
original_prompt = open('/Users/kublai/.openclaw/agents/main/scripts/kurultai-review-prompt.txt').read() if os.path.exists('/Users/kublai/.openclaw/agents/main/scripts/kurultai-review-prompt.txt') else "Prompt file not found"

prompt = f"""You are reviewing the quality of an LLM prompt used for Kurultai analysis.

ORIGINAL PROMPT:
{original_prompt}

LLM OUTPUT (from that prompt):
{analysis[:5000]}

REVIEW THE PROMPT:

## Prompt Effectiveness
- Did the prompt produce useful, actionable analysis?
- Was the output structured and evidence-based?
- Did it identify real issues vs. hallucinations?

## Prompt Weaknesses
- What was missing from the prompt?
- What could be clearer?
- What led to poor output (if any)?

## Recommended Prompt Improvements
[Specific changes to improve the prompt]

## Improved Prompt Version
[Rewrite the prompt with improvements]

Be specific and constructive.
"""

# API credentials already set above from OpenClaw config

try:
    response = requests.post(
        api_url,
        headers={'Authorization': f'Bearer {api_key}'},
        json={
            'model': 'qwen3.5-plus',
            'messages': [
                {'role': 'system', 'content': 'You are reviewing an LLM prompt for effectiveness.'},
                {'role': 'user', 'content': prompt}
            ],
            'max_tokens': 4000,
            'temperature': 0.7
        },
        timeout=120
    )
    
    if response.status_code == 200:
        meta_review = response.json()['choices'][0]['message']['content']
        print(meta_review)
    else:
        print(f"❌ Meta-review API Error: {response.status_code}")
        print(f"Response: {response.text}")
        
except Exception as e:
    print(f"❌ Meta-review failed: {e}")
PYEOF

echo "  ✅ Meta-review complete: $META_REVIEW_FILE"
echo ""

# ============================================================================
# STEP 4: Create Sync File
# ============================================================================

echo "Step 4: Creating sync file..."

cat > "$SYNC_FILE" << EOF
# Kurultai Sync — ${DATE} ${TIME} EST

**Facilitator:** Kublai (Auto-Executed)
**Review Window:** 6 hours (${SIX_HOURS_AGO} to ${HOUR_AGO})
**Analysis Model:** qwen3.5-plus (cloud)

---

## LLM Analysis

$(cat "$ANALYSIS_FILE")

---

## Meta-Review of Prompt

$(cat "$META_REVIEW_FILE")

---

## Kublai Auto-Execution

**Actions Taken:**
- [ ] Action 1: [Auto-populated from analysis]
- [ ] Action 2: [Auto-populated from analysis]
- [ ] Action 3: [Auto-populated from analysis]

**Execution Status:** In Progress

---

## Data Sources

- Chatlogs: $DATA_DIR/chatlogs.txt
- Reflections: $DATA_DIR/reflections.txt
- Commits: $DATA_DIR/commits.txt
- Neo4j: $DATA_DIR/neo4j.txt
- Logs: $DATA_DIR/logs.txt
- Analysis: $ANALYSIS_FILE
- Meta-Review: $META_REVIEW_FILE

---

*The Kurultai thinks as one. Continuous improvement through automated review.*
EOF

echo "  ✅ Sync file created: $SYNC_FILE"
echo ""

# ============================================================================
# STEP 5: Auto-Execute Actions (Kublai)
# ============================================================================

echo "Step 5: Kublai auto-executing priority actions..."

# Parse the analysis and execute top actions
# This is a simplified version - in production, this would be more sophisticated

# Extract action items from analysis
grep -E "^\- \[ \]|\*\*" "$ANALYSIS_FILE" | head -5 > "$DATA_DIR/actions.txt"

echo "  Actions to execute:"
cat "$DATA_DIR/actions.txt"

# Kublai would execute these actions here
# For now, just log them
echo "  ✅ Actions logged for execution"
echo ""

# ============================================================================
# STEP 6: Auto-Update ARCHITECTURE.md (Kublai)
# ============================================================================

echo "Step 6: Auto-updating ARCHITECTURE.md..."

# Kublai automatically updates ARCHITECTURE.md with findings
python3 << PYEOF
import os
from datetime import datetime

# Read the analysis
analysis_file = '$ANALYSIS_FILE'
if os.path.exists(analysis_file):
    with open(analysis_file, 'r') as f:
        analysis = f.read()
else:
    analysis = "No analysis available"

# Read ARCHITECTURE.md
arch_file = '/Users/kublai/.openclaw/agents/main/ARCHITECTURE.md'
with open(arch_file, 'r') as f:
    arch_content = f.read()

# Check if today's date is already in Change Log
today = datetime.now().strftime('%Y-%m-%d')
if f'### {today}' not in arch_content:
    # Add new Change Log entry
    new_entry = f"""
### {today} - Automated Kurultai Review

- **Change**: Automated hourly Kurultai review with 6-hour rolling window
- **Reason**: Continuous improvement through automated analysis
- **Scope**: Cloud LLM analysis, meta-review, auto-execution
- **Analysis Summary**: {analysis[:500]}...
- **Files**: `scripts/kurultai-review.sh`, `scripts/kurultai-review-prompt.txt`

"""
    # Find Change Log section and insert
    if '## Change Log' in arch_content:
        import re
        match = re.search(r'## Change Log\n\n(### 2026)', arch_content)
        if match:
            insert_pos = match.start(1)
            arch_content = arch_content[:insert_pos] + new_entry + "\n" + arch_content[insert_pos:]
        else:
            arch_content = arch_content.replace('## Change Log\n', '## Change Log\n' + new_entry)
    
    with open(arch_file, 'w') as f:
        f.write(arch_content)
    
    print(f"✅ ARCHITECTURE.md updated with today's review")
else:
    print(f"ℹ️ ARCHITECTURE.md already updated for today")
PYEOF

echo ""

# ============================================================================
# STEP 7: Archive
# ============================================================================

echo "Step 7: Archiving sync file..."

# Wait 10 minutes for Kublai to review
sleep 600

# Move to archive
mv "$SYNC_FILE" "$ARCHIVE_DIR/"
echo "  ✅ Sync file archived: $ARCHIVE_DIR/$(basename $SYNC_FILE)"

# Clean up temp files
# rm -rf "$DATA_DIR"

echo ""
echo "=== Kurultai Review Complete ==="
echo ""
echo "Files created:"
echo "  - Analysis: $ANALYSIS_FILE"
echo "  - Meta-Review: $META_REVIEW_FILE"
echo "  - Sync File: $SYNC_FILE (archived)"
echo "  - ARCHITECTURE.md: ✅ Auto-updated"
echo ""
echo "Next review: $(date -v+1H '+%H:00') EST"
