#!/bin/bash
# Neo4j Reflection Logging Script

AGENT="$1"
DATE="$2"
TIME="$3"
LLM_USED="$4"

python3 - "$AGENT" "$DATE" "$TIME" "$LLM_USED" << 'PYEOF'
import sys
from neo4j import GraphDatabase

agent = sys.argv[1]
date = sys.argv[2]
time = sys.argv[3]
llm_used = sys.argv[4]

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "neo4j"))

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

driver.close()
PYEOF
