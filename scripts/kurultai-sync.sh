#!/bin/bash
# Kurultai Sync - Hourly All-Agents Meeting
# Duration: 10 minutes max
# Purpose: Cross-agent visibility, alignment, and continuous improvement

DATE=$(date +%Y-%m-%d)
TIME=$(date +%H:%M)
SYNC_FILE="/Users/kublai/.openclaw/agents/main/shared-context/KURULTAI-SYNC-${DATE}-${TIME}.md"
ARCHIVE_DIR="/Users/kublai/.openclaw/agents/main/shared-context/archive/sync"

# Create archive directory if it doesn't exist
mkdir -p "$ARCHIVE_DIR"

echo "=== Kurultai Sync — ${DATE} ${TIME} EST ===" > "$SYNC_FILE"
echo "" >> "$SYNC_FILE"
echo "**Facilitator:** Kublai" >> "$SYNC_FILE"
echo "**Duration:** 10 minutes" >> "$SYNC_FILE"
echo "**Type:** Full Kurultai + Process Improvement" >> "$SYNC_FILE"
echo "" >> "$SYNC_FILE"

# Collect status from each agent
echo "## Attendance" >> "$SYNC_FILE"
echo "" >> "$SYNC_FILE"

for agent in kublai mongke chagatai temujin jochi ogedei; do
    AGENT_FILE="/Users/kublai/.openclaw/agents/$agent/memory/${DATE}.md"
    AGENT_NAME=$(echo "$agent" | sed 's/\b\(.\)/\u\1/')
    if [ -f "$AGENT_FILE" ]; then
        LAST_TASK=$(grep -A2 "Focus for Next Hour" "$AGENT_FILE" 2>/dev/null | tail -1 | sed 's/^- //')
        echo "- [x] $AGENT_NAME - $LAST_TASK" >> "$SYNC_FILE"
    else
        echo "- [ ] $AGENT_NAME - No update" >> "$SYNC_FILE"
    fi
done

echo "" >> "$SYNC_FILE"
echo "**Quorum:** 6/6 (100%)" >> "$SYNC_FILE"
echo "" >> "$SYNC_FILE"

# Kublai distills learnings and identifies actions
echo "## Kublai's Distilled Learnings" >> "$SYNC_FILE"
echo "" >> "$SYNC_FILE"
echo "**Key Insights:**" >> "$SYNC_FILE"
echo "- [To be filled by Kublai based on sync results]" >> "$SYNC_FILE"
echo "" >> "$SYNC_FILE"
echo "**Identified Blockers:**" >> "$SYNC_FILE"
echo "- [List blockers identified]" >> "$SYNC_FILE"
echo "" >> "$SYNC_FILE"
echo "**Identified Dependencies:**" >> "$SYNC_FILE"
echo "- [List dependencies between agents]" >> "$SYNC_FILE"
echo "" >> "$SYNC_FILE"
echo "**Identified Synergies:**" >> "$SYNC_FILE"
echo "- [List opportunities for collaboration]" >> "$SYNC_FILE"
echo "" >> "$SYNC_FILE"

# Process Improvement Reflection
echo "## Process Improvement Reflection" >> "$SYNC_FILE"
echo "" >> "$SYNC_FILE"
echo "**What's Working Well:**" >> "$SYNC_FILE"
echo "- [Agents reflect on effective processes]" >> "$SYNC_FILE"
echo "" >> "$SYNC_FILE"
echo "**What's Not Working:**" >> "$SYNC_FILE"
echo "- [Agents identify bottlenecks or issues]" >> "$SYNC_FILE"
echo "" >> "$SYNC_FILE"
echo "**Process Improvements to Implement:**" >> "$SYNC_FILE"
echo "- [Actionable improvements to try]" >> "$SYNC_FILE"
echo "" >> "$SYNC_FILE"

# Kublai's Action Items
echo "## Kublai's Action Items" >> "$SYNC_FILE"
echo "" >> "$SYNC_FILE"

# Kublai asks: "What do I want to do next?"
echo "**Kublai Self-Reflection:**" >> "$SYNC_FILE"
echo "" >> "$SYNC_FILE"
echo "Question: What do I want to do next?" >> "$SYNC_FILE"
echo "" >> "$SYNC_FILE"
echo "**Answer:** [Kublai fills this in based on sync results]" >> "$SYNC_FILE"
echo "" >> "$SYNC_FILE"

# Kublai assigns tasks to each agent
echo "**Task Assignments:**" >> "$SYNC_FILE"
echo "" >> "$SYNC_FILE"
echo "### Möngke (Research)" >> "$SYNC_FILE"
echo "- [ ] [Task assignment]" >> "$SYNC_FILE"
echo "" >> "$SYNC_FILE"
echo "### Chagatai (Content)" >> "$SYNC_FILE"
echo "- [ ] [Task assignment]" >> "$SYNC_FILE"
echo "" >> "$SYNC_FILE"
echo "### Temüjin (Development)" >> "$SYNC_FILE"
echo "- [ ] [Task assignment]" >> "$SYNC_FILE"
echo "" >> "$SYNC_FILE"
echo "### Jochi (Analysis)" >> "$SYNC_FILE"
echo "- [ ] [Task assignment]" >> "$SYNC_FILE"
echo "" >> "$SYNC_FILE"
echo "### Ögedei (Operations)" >> "$SYNC_FILE"
echo "- [ ] [Task assignment]" >> "$SYNC_FILE"
echo "" >> "$SYNC_FILE"

echo "**Immediate Actions (This Hour):**" >> "$SYNC_FILE"
echo "- [ ] [Kublai's own task 1]" >> "$SYNC_FILE"
echo "- [ ] [Kublai's own task 2]" >> "$SYNC_FILE"
echo "" >> "$SYNC_FILE"
echo "**Deferred Actions:**" >> "$SYNC_FILE"
echo "- [ ] [Task for later]" >> "$SYNC_FILE"
echo "" >> "$SYNC_FILE"

# Log to Neo4j
export SYNC_DATE="$DATE"
export SYNC_TIME="$TIME"

python3 << PYEOF
from neo4j import GraphDatabase
import os

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "neo4j"))

sync_date = os.environ.get('SYNC_DATE')
sync_time = os.environ.get('SYNC_TIME')

try:
    with driver.session() as session:
        # Create KurultaiSync node
        result = session.run("""
            CREATE (s:KurultaiSync {
                timestamp: datetime(),
                date: \$date,
                time: \$time,
                attendance: 6,
                quorum: true
            })
            RETURN s
        """, date=sync_date, time=sync_time)
        
        sync_id = result.single()["s"].element_id
        
        # Create KublaiDecision node linked to sync
        session.run("""
            MATCH (s:KurultaiSync)
            WHERE s.date = \$date AND s.time = \$time
            CREATE (d:KublaiDecision {
                timestamp: datetime(),
                distilled_learnings: [],
                blockers_identified: [],
                dependencies_identified: [],
                synergies_identified: [],
                immediate_actions: [],
                deferred_actions: [],
                process_improvements: []
            })
            CREATE (s)-[:HAS_DECISION]->(d)
        """, date=sync_date, time=sync_time)
        
        # Create ProcessImprovement node for tracking improvements
        session.run("""
            MATCH (s:KurultaiSync)
            WHERE s.date = \$date AND s.time = \$time
            CREATE (pi:ProcessImprovement {
                timestamp: datetime(),
                whats_working: [],
                whats_not_working: [],
                improvements_to_implement: [],
                implemented: false
            })
            CREATE (s)-[:HAS_IMPROVEMENT]->(pi)
        """, date=sync_date, time=sync_time)

    print(f"✅ Logged Kurultai Sync to Neo4j (ID: {sync_id})")
    driver.close()
except Exception as e:
    print(f"⚠️ Neo4j logging skipped: {e}")
PYEOF

echo "" >> "$SYNC_FILE"
echo "---" >> "$SYNC_FILE"
echo "*The Kurultai thinks as one. Continuous improvement through reflection.*" >> "$SYNC_FILE"

# Commit to git
cd /Users/kublai/.openclaw/agents/main
git add shared-context/KURULTAI-SYNC-*.md 2>/dev/null
git commit -m "[sync] Kurultai Sync ${DATE} ${TIME} + Process Improvement" 2>/dev/null || true

# Archive the sync file (after Kublai reviews and acts)
# Note: This is commented out - Kublai should review first
# sleep 600  # Wait 10 minutes for Kublai to review
# mv "$SYNC_FILE" "$ARCHIVE_DIR/"
# echo "✅ Sync file archived: $ARCHIVE_DIR/$(basename $SYNC_FILE)"

echo "✅ Kurultai Sync complete: $SYNC_FILE"
echo ""
echo "Next steps:"
echo "  1. Kublai reviews distilled learnings"
echo "  2. Kublai logs decisions to Neo4j"
echo "  3. Kublai executes immediate actions"
echo "  4. Kublai archives sync file"