#!/bin/bash
# Neo4j Reflection Logging Script

AGENT="$1"
DATE="$2"
TIME="$3"
LLM_USED="$4"
SCRIPTS_DIR="$(dirname "$0")"

python3 - "$AGENT" "$DATE" "$TIME" "$LLM_USED" << 'PYEOF'
import sys
sys.path.insert(0, '$SCRIPTS_DIR')
from neo4j_task_tracker import get_driver, close_driver

agent = sys.argv[1]
date = sys.argv[2]
time = sys.argv[3]
llm_used = sys.argv[4]

driver = get_driver()

with driver.session() as session:
    session.run("""
        MERGE (r:Reflection {
            agent: $agent,
            date: $date,
            time: $time
        })
        SET r.llm_used = $llm_used,
            r.timestamp = datetime()
    """, agent=agent, date=date, time=time, llm_used=llm_used)

    print(f"✅ Logged reflection to Neo4j for {agent} at {time}")

close_driver()
PYEOF
