#!/bin/bash
# Agent Harness Health Check
# Validates that Agent Harness is functioning properly

set -e

WORKSPACE="/Users/kublai/.openclaw/agents/main"

echo "=== AGENT HARNESS HEALTH CHECK ==="
echo "Timestamp: $(date)"
echo ""

ERRORS=0
WARNINGS=0

# ============================================================================
# CHECK 1: Hooks Exist and Are Executable
# ============================================================================
echo "CHECK 1: Hook Scripts"
echo "--------------------"

for hook in pre-commit.sh pre-deploy.sh post-task.sh; do
    if [ -f "$WORKSPACE/hooks/$hook" ]; then
        if [ -x "$WORKSPACE/hooks/$hook" ]; then
            echo "  ✅ $hook: Exists and executable"
        else
            echo "  ⚠️  $hook: Exists but NOT executable"
            chmod +x "$WORKSPACE/hooks/$hook"
            echo "      Fixed: Made executable"
            WARNINGS=$((WARNINGS + 1))
        fi
    else
        echo "  ❌ $hook: MISSING"
        ERRORS=$((ERRORS + 1))
    fi
done

echo ""

# ============================================================================
# CHECK 2: Hooks Integrated into hourly_reflection.sh
# ============================================================================
echo "CHECK 2: Hook Integration"
echo "-------------------------"

REFLECTION_SCRIPT="$WORKSPACE/scripts/hourly_reflection.sh"

if grep -q "hooks/pre-commit" "$REFLECTION_SCRIPT"; then
    echo "  ✅ pre-commit.sh: Integrated"
else
    echo "  ❌ pre-commit.sh: NOT integrated"
    ERRORS=$((ERRORS + 1))
fi

if grep -q "hooks/post-task" "$REFLECTION_SCRIPT"; then
    echo "  ✅ post-task.sh: Integrated"
else
    echo "  ❌ post-task.sh: NOT integrated"
    ERRORS=$((ERRORS + 1))
fi

echo ""

# ============================================================================
# CHECK 3: Spec Templates Exist
# ============================================================================
echo "CHECK 3: Spec Templates"
echo "-----------------------"

for template in task-spec-template.md feature-spec-template.md bug-fix-spec-template.md; do
    if [ -f "$WORKSPACE/specs/$template" ]; then
        echo "  ✅ $template: Exists"
    else
        echo "  ❌ $template: MISSING"
        ERRORS=$((ERRORS + 1))
    fi
done

echo ""

# ============================================================================
# CHECK 4: Example Specs Exist
# ============================================================================
echo "CHECK 4: Example Specs"
echo "----------------------"

for example in task-example.md feature-example.md bug-fix-example.md; do
    if [ -f "$WORKSPACE/specs/examples/$example" ]; then
        echo "  ✅ $example: Exists"
    else
        echo "  ❌ $example: MISSING"
        ERRORS=$((ERRORS + 1))
    fi
done

echo ""

# ============================================================================
# CHECK 5: Agents' AGENTS.md Updated
# ============================================================================
echo "CHECK 5: Agent Documentation"
echo "----------------------------"

for agent in main mongke chagatai temujin jochi ogedei; do
    if [ "$agent" = "main" ]; then
        AGENT_NAME="Kublai"
        AGENT_DIR="$WORKSPACE"
    else
        AGENT_NAME="${agent^}"
        AGENT_DIR="$WORKSPACE/../$agent"
    fi
    
    if grep -q "Agent Harness" "$AGENT_DIR/AGENTS.md" 2>/dev/null; then
        echo "  ✅ $AGENT_NAME: Documented"
    else
        echo "  ⚠️  $AGENT_NAME: NOT documented"
        WARNINGS=$((WARNINGS + 1))
    fi
done

echo ""

# ============================================================================
# CHECK 6: Neo4j Logging
# ============================================================================
echo "CHECK 6: Neo4j Logging"
echo "----------------------"

python3 << 'PYEOF'
from neo4j import GraphDatabase
from datetime import datetime, timedelta

try:
    driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'neo4j'))
    
    with driver.session() as session:
        # Check for recent TaskCompletion nodes
        result = session.run("""
            MATCH (t:TaskCompletion)
            WHERE t.completed_at > datetime() - duration('PT1H')
            RETURN count(t) as count, max(t.completed_at) as last
        """)
        record = result.single()
        
        if record and record['count'] > 0:
            last_log = record['last'].strftime('%H:%M:%S')
            print(f"  ✅ Neo4j logging: {record['count']} tasks in last hour")
            print(f"      Last log: {last_log}")
        else:
            print("  ⚠️  Neo4j logging: No recent TaskCompletion nodes")
            print("      This may be OK if no tasks completed recently")
    
    driver.close()
except Exception as e:
    print(f"  ❌ Neo4j logging: {e}")
PYEOF

echo ""

# ============================================================================
# CHECK 7: Hooks README
# ============================================================================
echo "CHECK 7: Documentation"
echo "----------------------"

if [ -f "$WORKSPACE/hooks/README.md" ]; then
    echo "  ✅ hooks/README.md: Exists"
else
    echo "  ❌ hooks/README.md: MISSING"
    ERRORS=$((ERRORS + 1))
fi

echo ""

# ============================================================================
# SUMMARY
# ============================================================================
echo "=== SUMMARY ==="
echo ""
echo "Errors: $ERRORS"
echo "Warnings: $WARNINGS"
echo ""

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo "✅ AGENT HARNESS: HEALTHY"
    HEALTH_STATUS="HEALTHY"
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo "⚠️  AGENT HARNESS: HEALTHY (with warnings)"
    HEALTH_STATUS="HEALTHY_WARNINGS"
    exit 0
else
    echo "❌ AGENT HARNESS: UNHEALTHY"
    echo ""
    echo "Critical issues found. Please fix:"
    echo "  - Missing hook scripts"
    echo "  - Hooks not integrated"
    echo "  - Missing spec templates"
    echo "  - Missing documentation"
    HEALTH_STATUS="UNHEALTHY"
    exit 1
fi
EOF

# Log to Neo4j
if [ -f "$WORKSPACE/hooks/health-check-neo4j.sh" ]; then
    bash "$WORKSPACE/hooks/health-check-neo4j.sh"
fi
EOF

chmod +x /Users/kublai/.openclaw/agents/main/hooks/health-check.sh

echo "✅ Health check script created: hooks/health-check.sh"
echo ""
echo "Usage:"
echo "  ./hooks/health-check.sh"
echo ""
echo "This will be run automatically on every hourly reflection."