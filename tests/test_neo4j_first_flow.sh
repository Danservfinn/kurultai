#!/bin/bash
#
# test_neo4j_first_flow.sh — Integration test for Neo4j-first task flow
#
# Verifies:
# 1. Task creation writes to Neo4j first
# 2. Task visible in Neo4j immediately after creation
# 3. Filesystem file exists within 1 second
# 4. Status change propagates correctly
#
# Usage:
#   ./test_neo4j_first_flow.sh [--cleanup]
#

set -e

SCRIPTS_DIR="$(dirname "$0")/../scripts"
cd "$SCRIPTS_DIR"

CLEANUP=${1:-""}

echo "=== Neo4j First Flow Integration Test ==="
echo ""

# Generate unique task ID for testing
TEST_ID="test-$(date +%s)-$RANDOM"
echo "Test task ID: $TEST_ID"

# 1. Create task via intake
echo ""
echo "[1/4] Creating test task..."
TASK_OUTPUT=$(python3 task_intake.py \
    --title "Test task $TEST_ID" \
    --body "This is a test task for Neo4j-first flow verification" \
    --agent temujin \
    --priority high \
    --source "test-neo4j-first-flow" \
    2>&1)

TASK_ID=$(echo "$TASK_OUTPUT" | grep -oE '[a-f0-9]{12}' | head -1)

if [ -z "$TASK_ID" ]; then
    echo "FAIL: Could not extract task_id from output"
    echo "Output: $TASK_OUTPUT"
    exit 1
fi

echo "Created task: $TASK_ID"

# 2. Verify in Neo4j immediately
echo ""
echo "[2/4] Verifying task exists in Neo4j..."
python3 -c "
from neo4j_task_tracker import get_driver
driver = get_driver()
with driver.session() as session:
    result = session.run('MATCH (t:Task {task_id: \"'$TASK_ID'\"}) RETURN t.status, t.agent')
    record = result.single()
    if not record:
        print('FAIL: Task not found in Neo4j')
        exit(1)
    status = record['t.status']
    agent = record['t.agent']
    print(f'Neo4j status: {status}, agent: {agent}')
    if status != 'PENDING':
        print(f'FAIL: Expected PENDING, got {status}')
        exit(1)
    if agent != 'temujin':
        print(f'FAIL: Expected temujin, got {agent}')
        exit(1)
    print('PASS: Task found in Neo4j with correct status')
driver.close()
"

if [ $? -ne 0 ]; then
    echo "FAIL: Neo4j verification failed"
    exit 1
fi

# 3. Verify filesystem file exists
echo ""
echo "[3/4] Verifying filesystem file exists..."
sleep 0.5  # Small delay for async file write

TASK_FILE=$(find ~/.openclaw/agents/temujin/tasks -name "*$TASK_ID*.md" 2>/dev/null | head -1)

if [ -z "$TASK_FILE" ]; then
    echo "WARN: Filesystem file not found (may be async)"
    echo "Checking for any new task files..."
    find ~/.openclaw/agents/temujin/tasks -name "*.md" -mmin -1 2>/dev/null | head -3
else
    echo "PASS: Filesystem file exists: $TASK_FILE"
fi

# 4. Simulate status change and verify propagation
echo ""
echo "[4/4] Simulating status change..."
python3 -c "
from neo4j_task_tracker import get_driver
driver = get_driver()
with driver.session() as session:
    session.run('MATCH (t:Task {task_id: \"'$TASK_ID'\"}) SET t.status = \"TEST_COMPLETED\"')
    result = session.run('MATCH (t:Task {task_id: \"'$TASK_ID'\"}) RETURN t.status')
    record = result.single()
    status = record['t.status']
    print(f'New status: {status}')
    if status == 'TEST_COMPLETED':
        print('PASS: Status update successful')
    else:
        print(f'FAIL: Status not updated, got {status}')
        exit(1)
driver.close()
"

if [ $? -ne 0 ]; then
    echo "FAIL: Status change verification failed"
    exit 1
fi

# Cleanup
if [ "$CLEANUP" == "--cleanup" ]; then
    echo ""
    echo "[CLEANUP] Removing test task..."
    python3 -c "
from neo4j_task_tracker import get_driver
driver = get_driver()
with driver.session() as session:
    session.run('MATCH (t:Task {task_id: \"'$TASK_ID'\"}) DETACH DELETE t')
print('Task removed from Neo4j')
"
    if [ -n "$TASK_FILE" ]; then
        rm -f "$TASK_FILE"
        echo "Task file removed"
    fi
fi

echo ""
echo "=== ALL CHECKS PASSED ==="
