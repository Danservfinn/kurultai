#!/bin/bash
# Agent Harness Health Check - Neo4j Logging
# Logs health check results to Neo4j for tracking over time
# Auto-restarts Neo4j if down

set -e

WORKSPACE="/Users/kublai/.openclaw/agents/main"
TIMESTAMP=$(date -Iseconds)

echo "=== NEO4J HEALTH CHECK & AUTO-RESTART ==="
echo ""

# Check if Neo4j is running, restart if not
if ! curl -s http://localhost:7474 > /dev/null 2>&1; then
    echo "⚠️  Neo4j is DOWN - attempting restart..."
    brew services restart neo4j > /dev/null 2>&1 || {
        echo "❌ Failed to restart Neo4j via brew services"
        exit 1
    }
    # Wait for Neo4j to start
    echo "⏳ Waiting for Neo4j to start..."
    for i in {1..30}; do
        if curl -s http://localhost:7474 > /dev/null 2>&1; then
            echo "✅ Neo4j is UP"
            break
        fi
        sleep 1
    done
    # Verify Bolt connection
    if ! curl -s http://localhost:7474 > /dev/null 2>&1; then
        echo "❌ Neo4j failed to start after 30 seconds"
        exit 1
    fi
else
    echo "✅ Neo4j is UP"
fi

echo ""
echo "=== LOGGING HEALTH CHECK TO NEO4J ==="
echo ""

python3 << PYEOF
from neo4j import GraphDatabase
from datetime import datetime
import os

WORKSPACE = "$WORKSPACE"
TIMESTAMP = "$TIMESTAMP"

# Run health checks
checks = {
    'hooks_executable': 0,
    'hooks_total': 0,
    'hooks_integrated': 0,
    'specs_exist': 0,
    'specs_total': 0,
    'examples_exist': 0,
    'examples_total': 0,
    'agents_documented': 0,
    'agents_total': 0,
    'readme_exists': 0,
    'neo4j_logging': 0
}

# Check 1: Hooks executable
for hook in ['pre-commit.sh', 'pre-deploy.sh', 'post-task.sh']:
    checks['hooks_total'] += 1
    hook_path = f"{WORKSPACE}/hooks/{hook}"
    if os.path.isfile(hook_path) and os.access(hook_path, os.X_OK):
        checks['hooks_executable'] += 1

# Check 2: Hooks integrated
reflection_script = f"{WORKSPACE}/scripts/hourly_reflection.sh"
if os.path.isfile(reflection_script):
    with open(reflection_script, 'r') as f:
        content = f.read()
        if 'hooks/pre-commit' in content:
            checks['hooks_integrated'] += 1
        if 'hooks/post-task' in content:
            checks['hooks_integrated'] += 1

# Check 3: Spec templates
for template in ['task-spec-template.md', 'feature-spec-template.md', 'bug-fix-spec-template.md']:
    checks['specs_total'] += 1
    template_path = f"{WORKSPACE}/specs/{template}"
    if os.path.isfile(template_path):
        checks['specs_exist'] += 1

# Check 4: Example specs
for example in ['task-example.md', 'feature-example.md', 'bug-fix-example.md']:
    checks['examples_total'] += 1
    example_path = f"{WORKSPACE}/specs/examples/{example}"
    if os.path.isfile(example_path):
        checks['examples_exist'] += 1

# Check 5: Agents documented
agents = ['main', 'mongke', 'chagatai', 'temujin', 'jochi', 'ogedei']
checks['agents_total'] = len(agents)
for agent in agents:
    agent_dir = f"{WORKSPACE}/../{agent}" if agent != 'main' else WORKSPACE
    agents_file = f"{agent_dir}/AGENTS.md"
    if os.path.isfile(agents_file):
        with open(agents_file, 'r') as f:
            if 'Agent Harness' in f.read():
                checks['agents_documented'] += 1

# Check 6: README exists
readme_path = f"{WORKSPACE}/hooks/README.md"
if os.path.isfile(readme_path):
    checks['readme_exists'] = 1

# Check 7: Neo4j logging working
# Load credentials from centralized env file
_neo4j_env = os.path.expanduser("~/.openclaw/credentials/neo4j.env")
_neo4j_user = "neo4j"
_neo4j_password = "neo4j"  # fallback
if os.path.exists(_neo4j_env):
    with open(_neo4j_env) as f:
        for line in f:
            if line.startswith("NEO4J_USER="):
                _neo4j_user = line.strip().split("=", 1)[1]
            elif line.startswith("NEO4J_PASSWORD="):
                _neo4j_password = line.strip().split("=", 1)[1]

try:
    driver = GraphDatabase.driver('bolt://localhost:7687', auth=(_neo4j_user, _neo4j_password))
    with driver.session() as session:
        result = session.run("""
            MATCH (t:TaskCompletion)
            WHERE t.completed_at > datetime() - duration('PT1H')
            RETURN count(t) as count
        """)
        record = result.single()
        if record and record['count'] > 0:
            checks['neo4j_logging'] = 1
    driver.close()
except:
    checks['neo4j_logging'] = 0

# Calculate health score
total_checks = (
    checks['hooks_total'] +  # 3
    2 +  # hooks integrated (2 checks)
    checks['specs_total'] +  # 3
    checks['examples_total'] +  # 3
    checks['agents_total'] +  # 6
    1 +  # readme
    1  # neo4j logging
)

passed_checks = (
    checks['hooks_executable'] +
    checks['hooks_integrated'] +
    checks['specs_exist'] +
    checks['examples_exist'] +
    checks['agents_documented'] +
    checks['readme_exists'] +
    checks['neo4j_logging']
)

health_score = (passed_checks / total_checks) * 100

# Log to Neo4j (using credentials loaded above)
driver = GraphDatabase.driver('bolt://localhost:7687', auth=(_neo4j_user, _neo4j_password))

with driver.session() as session:
    session.run("""
        CREATE (h:AgentHarnessHealthCheck {
            timestamp: datetime($timestamp),
            health_score: $health_score,
            passed_checks: $passed_checks,
            total_checks: $total_checks,
            hooks_executable: $hooks_executable,
            hooks_total: $hooks_total,
            hooks_integrated: $hooks_integrated,
            specs_exist: $specs_exist,
            specs_total: $specs_total,
            examples_exist: $examples_exist,
            examples_total: $examples_total,
            agents_documented: $agents_documented,
            agents_total: $agents_total,
            readme_exists: $readme_exists,
            neo4j_logging: $neo4j_logging
        })
    """,
    timestamp=TIMESTAMP,
    health_score=health_score,
    passed_checks=passed_checks,
    total_checks=total_checks,
    **checks
    )
    
    print(f"✅ Health check logged to Neo4j")
    print(f"   Health Score: {health_score:.1f}%")
    print(f"   Passed: {passed_checks}/{total_checks}")

driver.close()
PYEOF

echo ""
echo "=== HEALTH CHECK COMPLETE ==="
EOF

chmod +x /Users/kublai/.openclaw/agents/main/hooks/health-check-neo4j.sh

echo "✅ Neo4j logging script created: hooks/health-check-neo4j.sh"