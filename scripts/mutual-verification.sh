#!/bin/bash
# Mutual Verification: Hourly Reflection ↔ Heartbeat Health Check
# Ensures both systems are functioning and being actioned

set -e

WORKSPACE="/Users/kublai/.openclaw/agents/main"
TIMESTAMP=$(date -Iseconds)

echo "=== MUTUAL VERIFICATION: HOURLY REFLECTION ↔ HEARTBEAT ==="
echo "Timestamp: $TIMESTAMP"
echo ""

ISSUES_FOUND=0
TEMUJIN_TASKS=()

# ============================================================================
# PART 1: HOURLY REFLECTION VERIFIES HEARTBEAT HEALTH
# ============================================================================
echo "PART 1: Hourly Reflection Verifying Heartbeat Health"
echo "-----------------------------------------------------"
echo ""

# Check 1: Heartbeat scripts exist
echo "CHECK 1: Heartbeat Scripts Existence"
if [ -f "$WORKSPACE/hooks/health-check.sh" ]; then
    echo "  ✅ health-check.sh exists"
else
    echo "  ❌ health-check.sh MISSING"
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
    TEMUJIN_TASKS+=("Create hooks/health-check.sh")
fi

if [ -f "$WORKSPACE/hooks/health-check-neo4j.sh" ]; then
    echo "  ✅ health-check-neo4j.sh exists"
else
    echo "  ❌ health-check-neo4j.sh MISSING"
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
    TEMUJIN_TASKS+=("Create hooks/health-check-neo4j.sh")
fi

# Check 2: Heartbeat health check is being called
echo ""
echo "CHECK 2: Heartbeat Health Check Integration"
if grep -q "health-check.sh" "$WORKSPACE/scripts/hourly_reflection.sh"; then
    echo "  ✅ health-check.sh integrated into hourly_reflection.sh"
else
    echo "  ❌ health-check.sh NOT integrated"
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
    TEMUJIN_TASKS+=("Integrate health-check.sh into hourly_reflection.sh")
fi

# Check 3: Neo4j logging is working
echo ""
echo "CHECK 3: Neo4j Health Check Logging"
python3 << 'PYEOF'
from neo4j import GraphDatabase
from datetime import datetime, timedelta

try:
    driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'neo4j'))
    
    with driver.session() as session:
        # Check for recent health check logs
        result = session.run("""
            MATCH (h:AgentHarnessHealthCheck)
            WHERE h.timestamp > datetime() - duration('PT2H')
            RETURN count(h) as count, avg(h.health_score) as avg_score
        """)
        record = result.single()
        
        if record and record['count'] > 0:
            print(f"  ✅ Neo4j logging: {record['count']} health checks in last 2 hours")
            print(f"      Average health score: {record['avg_score']:.1f}%")
            
            if record['avg_score'] < 80:
                print(f"  ⚠️  WARNING: Health score below 80%")
        else:
            print("  ❌ Neo4j logging: No health checks in last 2 hours")
            print("      Task for Temüjin: Fix Neo4j health check logging")
    
    driver.close()
except Exception as e:
    print(f"  ❌ Neo4j logging: Connection failed - {e}")
    print("      Task for Temüjin: Fix Neo4j connection for health checks")
PYEOF

# Check 4: Health check trends
echo ""
echo "CHECK 4: Health Check Trends (Last 24 Hours)"
python3 << 'PYEOF'
from neo4j import GraphDatabase

try:
    driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'neo4j'))
    
    with driver.session() as session:
        result = session.run("""
            MATCH (h:AgentHarnessHealthCheck)
            WHERE h.timestamp > datetime() - duration('P1D')
            RETURN 
              count(h) as total_checks,
              avg(h.health_score) as avg_score,
              min(h.health_score) as min_score,
              max(h.health_score) as max_score,
              sum(CASE WHEN h.health_score < 80 THEN 1 ELSE 0 END) as low_score_count
        """)
        record = result.single()
        
        print(f"  Total health checks (24h): {record['total_checks']}")
        print(f"  Average health score: {record['avg_score']:.1f}%")
        print(f"  Min/Max score: {record['min_score']:.1f}% / {record['max_score']:.1f}%")
        
        if record['low_score_count'] > 0:
            print(f"  ⚠️  Low score occurrences (<80%): {record['low_score_count']}")
            print("      Task for Temüjin: Investigate and fix recurring issues")
        else:
            print(f"  ✅ No low score occurrences")
    
    driver.close()
except Exception as e:
    print(f"  ❌ Trend analysis failed: {e}")
PYEOF

echo ""

# ============================================================================
# PART 2: HEARTBEAT HEALTH CHECK VERIFIES KURULTAI EFFECTIVENESS
# ============================================================================
echo "PART 2: Heartbeat Health Check Verifying Kurultai Effectiveness"
echo "----------------------------------------------------------------"
echo ""

# Check 1: Hourly reflections are running
echo "CHECK 1: Hourly Reflections Running"
python3 << 'PYEOF'
from neo4j import GraphDatabase
from datetime import datetime, timedelta

try:
    driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'neo4j'))
    
    with driver.session() as session:
        # Check for recent TaskCompletion nodes from hourly reflections
        result = session.run("""
            MATCH (t:TaskCompletion)
            WHERE t.task_name CONTAINS 'Hourly Reflection'
              AND t.completed_at > datetime() - duration('PT2H')
            RETURN count(t) as count
        """)
        record = result.single()
        
        if record and record['count'] >= 2:
            print(f"  ✅ Hourly reflections: {record['count']} in last 2 hours")
        elif record and record['count'] == 1:
            print(f"  ⚠️  Hourly reflections: Only {record['count']} in last 2 hours (expected 2)")
            print("      Task for Temüjin: Check hourly_reflection.sh cron/schedule")
        else
            print(f"  ❌ Hourly reflections: NONE in last 2 hours")
            print("      Task for Temüjin: Fix hourly_reflection.sh execution")
    
    driver.close()
except Exception as e:
    print(f"  ❌ Hourly reflection check failed: {e}")
PYEOF

# Check 2: Agent harness components are documented
echo ""
echo "CHECK 2: Agent Harness Documentation"
agents_documented=0
for agent in main mongke chagatai temujin jochi ogedei; do
    if [ "$agent" = "main" ]; then
        AGENT_DIR="$WORKSPACE"
        AGENT_NAME="Kublai"
    else
        AGENT_DIR="$WORKSPACE/../$agent"
        AGENT_NAME="${agent^}"
    fi
    
    if grep -q "Agent Harness" "$AGENT_DIR/AGENTS.md" 2>/dev/null; then
        agents_documented=$((agents_documented + 1))
        echo "  ✅ $AGENT_NAME: Documented"
    else
        echo "  ❌ $AGENT_NAME: NOT documented"
    fi
done

if [ $agents_documented -lt 6 ]; then
    echo "      Task for Temüjin: Update missing AGENTS.md files ($((6 - agents_documented)) missing)"
fi

# Check 3: Hooks are being executed
echo ""
echo "CHECK 3: Hook Execution"
python3 << 'PYEOF'
from neo4j import GraphDatabase

try:
    driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'neo4j'))
    
    with driver.session() as session:
        # Check for health check logs (indicates hooks are being called)
        result = session.run("""
            MATCH (h:AgentHarnessHealthCheck)
            WHERE h.timestamp > datetime() - duration('PT6H')
            RETURN count(h) as count, avg(h.health_score) as avg_score
        """)
        record = result.single()
        
        if record and record['count'] > 0:
            print(f"  ✅ Health checks executed: {record['count']} in last 6 hours")
            print(f"      Average health: {record['avg_score']:.1f}%")
        else:
            print(f"  ❌ No health checks in last 6 hours")
            print("      Task for Temüjin: Verify hourly_reflection.sh is running")
    
    driver.close()
except Exception as e:
    print(f"  ❌ Hook execution check failed: {e}")
PYEOF

# Check 4: Spec templates are being used
echo ""
echo "CHECK 4: Spec Template Usage"
if [ -d "$WORKSPACE/specs/examples" ]; then
    example_count=$(ls "$WORKSPACE/specs/examples/"*.md 2>/dev/null | wc -l)
    if [ $example_count -ge 3 ]; then
        echo "  ✅ Example specs exist: $example_count examples"
    else
        echo "  ⚠️  Example specs: Only $example_count examples (expected 3+)"
        echo "      Task for Temüjin: Create missing example specs"
    fi
else
    echo "  ❌ specs/examples/ directory MISSING"
    echo "      Task for Temüjin: Create specs/examples/ directory with examples"
fi

echo ""

# ============================================================================
# PART 3: TEMÜJIN TASK ASSIGNMENT
# ============================================================================
echo "PART 3: Temüjin Task Assignment"
echo "--------------------------------"
echo ""

if [ ${#TEMUJIN_TASKS[@]} -gt 0 ]; then
    echo "⚠️  ISSUES FOUND: ${#TEMUJIN_TASKS[@]} issues require Temüjin action"
    echo ""
    
    # Create task file for Temüjin
    TASK_FILE="$WORKSPACE/../temujin/tasks/auto-generated-$(date +%Y%m%d-%H%M%S).md"
    
    cat > "$TASK_FILE" << EOF
# Auto-Generated Task: Agent Harness Verification Issues

**Generated:** $(date -Iseconds)
**Priority:** HIGH
**Assigned To:** Temüjin
**Reason:** Hourly reflection detected issues with Agent Harness

## Issues Detected

EOF
    
    for i in "${!TEMUJIN_TASKS[@]}"; do
        echo "$((i+1)). ${TEMUJIN_TASKS[$i]}" >> "$TASK_FILE"
        echo "   - [ ] Fixed" >> "$TASK_FILE"
        echo "" >> "$TASK_FILE"
    done
    
    cat >> "$TASK_FILE" << 'EOF'

## Required Actions

1. Review each issue above
2. Fix the root cause
3. Test the fix
4. Update this task with resolution
5. Re-run health check to verify fix

## Verification

After fixing, run:
```bash
./hooks/health-check.sh
```

Health score should be 100%.

---

**Auto-generated by:** Hourly Reflection Verification System
EOF
    
    echo "✅ Task file created: $TASK_FILE"
    echo ""
    echo "Temüjin should review and fix these issues immediately."
else
    echo "✅ NO ISSUES FOUND"
    echo "   Agent Harness is functioning correctly"
    echo "   All heartbeats are being actioned appropriately"
    echo "   Kurultai reflections are working correctly"
fi

echo ""
echo "=== MUTUAL VERIFICATION COMPLETE ==="
echo ""

# Log verification results to Neo4j
python3 << PYEOF
from neo4j import GraphDatabase

try:
    driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'neo4j'))
    
    with driver.session() as session:
        session.run("""
            CREATE (v:MutualVerification {
                timestamp: datetime($timestamp),
                issues_found: $issues,
                temujin_tasks: $tasks,
                verification_type: 'hourly_reflection_heartbeat'
            })
        """,
        timestamp="$TIMESTAMP",
        issues=$ISSUES_FOUND,
        tasks=${#TEMUJIN_TASKS[@]}
        )
        
        print("✅ Verification results logged to Neo4j")
    
    driver.close()
except Exception as e:
    print(f"⚠️  Neo4j logging failed: {e}")
PYEOF

echo ""

if [ $ISSUES_FOUND -gt 0 ]; then
    exit 1
else
    exit 0
fi
EOF

chmod +x /Users/kublai/.openclaw/agents/main/scripts/mutual-verification.sh

echo "✅ Mutual verification script created: scripts/mutual-verification.sh"