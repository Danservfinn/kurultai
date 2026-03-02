#!/bin/bash
# Neo4j Reflection Logging Script

AGENT="$1"
DATE="$2"
TIME="$3"
LLM_USED="$4"

python3 << PYEOF
from neo4j import GraphDatabase
from datetime import datetime

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "neo4j"))

with driver.session() as session:
    session.run("""
        MERGE (r:Reflection {
            agent: '\$agent',
            date: '\$date',
            time: '\$time'
        })
        SET r.llm_used = '\$llm_used',
            r.timestamp = datetime()
    """, agent="$AGENT", date="$DATE", time="$TIME", llm_used="$LLM_USED")
    
    print(f"✅ Logged reflection to Neo4j for \$AGENT at \$TIME")

driver.close()
PYEOF
