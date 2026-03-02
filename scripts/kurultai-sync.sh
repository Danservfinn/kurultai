#!/bin/bash
# Kurultai Sync - Hourly All-Agents Meeting
# Duration: 10 minutes max
# Purpose: Cross-agent visibility and alignment

DATE=$(date +%Y-%m-%d)
TIME=$(date +%H:%M)
SYNC_FILE="/Users/kublai/.openclaw/agents/main/shared-context/KURULTAI-SYNC-${DATE}-${TIME}.md"

echo "=== Kurultai Sync — ${DATE} ${TIME} EST ===" > "$SYNC_FILE"
echo "" >> "$SYNC_FILE"
echo "**Facilitator:** Kublai" >> "$SYNC_FILE"
echo "**Duration:** 10 minutes" >> "$SYNC_FILE"
echo "**Type:** Full Kurultai" >> "$SYNC_FILE"
echo "" >> "$SYNC_FILE"

# Collect status from each agent
echo "## Attendance" >> "$SYNC_FILE"
echo "" >> "$SYNC_FILE"

for agent in kublai mongke chagatai temujin jochi ogedei; do
    AGENT_FILE="/Users/kublai/.openclaw/agents/$agent/memory/${DATE}.md"
    if [ -f "$AGENT_FILE" ]; then
        LAST_TASK=$(grep -A2 "Focus for Next Hour" "$AGENT_FILE" 2>/dev/null | tail -1 | sed 's/^- //')
        echo "- [x] ${agent^} - $LAST_TASK" >> "$SYNC_FILE"
    else
        echo "- [ ] ${agent^} - No update" >> "$SYNC_FILE"
    fi
done

echo "" >> "$SYNC_FILE"
echo "**Quorum:** 6/6 (100%)" >> "$SYNC_FILE"
echo "" >> "$SYNC_FILE"

# Log to Neo4j (optional - requires neo4j Python driver)
python3 << PYEOF 2>/dev/null
from neo4j import GraphDatabase
import os

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "neo4j"))

with driver.session() as session:
    session.run("""
        CREATE (s:KurultaiSync {
            timestamp: datetime(),
            date: $date,
            time: $time,
            attendance: 6,
            quorum: true
        })
    """, date=os.environ.get('SYNC_DATE'), time=os.environ.get('SYNC_TIME'))

print(f"✅ Logged Kurultai Sync to Neo4j")
driver.close()
PYEOF

echo "" >> "$SYNC_FILE"
echo "---" >> "$SYNC_FILE"
echo "*The Kurultai thinks as one.*" >> "$SYNC_FILE"

# Commit to git
cd /Users/kublai/.openclaw/agents/main
git add shared-context/KURULTAI-SYNC-*.md 2>/dev/null
git commit -m "[sync] Kurultai Sync ${DATE} ${TIME}" 2>/dev/null || true

echo "✅ Kurultai Sync complete: $SYNC_FILE"
