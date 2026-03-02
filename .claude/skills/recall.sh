#!/bin/bash
# /recall Skill - Load context before working
# Integrates Neo4j (structured) + QMD (unstructured)

MODE="${1:-hybrid}"
QUERY="${2:-}"

echo "=== RECALL MODE: $MODE ==="
echo ""

case "$MODE" in
  neo4j)
    echo "Querying Neo4j for structured data..."
    python3 << 'PYEOF'
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "neo4j"))

with driver.session() as session:
    result = session.run("""
        MATCH (r:Reflection)
        WHERE r.timestamp > datetime() - duration('P1D')
        RETURN r.agent, r.time, r.llm_used
        ORDER BY r.timestamp DESC
        LIMIT 10
    """)
    
    for record in result:
        print(f"{record['r.agent']} at {record['r.time']} - LLM: {record['r.llm_used']}")

driver.close()
PYEOF
    ;;
    
  qmd)
    echo "Querying QMD for unstructured data..."
    if command -v qmd &> /dev/null; then
        qmd search "$QUERY" -c agent_memories -n 10
    else
        echo "⚠️ QMD not installed. Install with: brew install qmd"
    fi
    ;;
    
  hybrid|*)
    echo "=== NEO4J (Structured) ==="
    python3 << 'PYEOF'
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "neo4j"))

with driver.session() as session:
    result = session.run("""
        MATCH (r:Reflection)
        WHERE r.timestamp > datetime() - duration('P1D')
        RETURN r.agent, r.time, r.llm_used
        ORDER BY r.timestamp DESC
        LIMIT 5
    """)
    
    for record in result:
        print(f"{record['r.agent']} at {record['r.time']} - LLM: {record['r.llm_used']}")

driver.close()
PYEOF
    
    echo ""
    echo "=== QMD (Unstructured) ==="
    if command -v qmd &> /dev/null; then
        qmd search "$QUERY" -c agent_memories -n 5
    else
        echo "⚠️ QMD not installed"
    fi
    ;;
esac
