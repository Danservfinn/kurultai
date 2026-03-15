#!/bin/bash
# Neo4j Schema Overhaul — Full Test Suite
# Runs all new and existing tests with summary
set -o pipefail

PASS=0; FAIL=0; SKIP=0; TOTAL=0

run_test() {
    local name="$1"; shift
    TOTAL=$((TOTAL + 1))
    echo ""
    echo "=== [$TOTAL] $name ==="
    if "$@" 2>&1; then
        echo "  -> PASS"
        PASS=$((PASS + 1))
    else
        local exit_code=$?
        if [ $exit_code -eq 0 ]; then
            echo "  -> PASS"
            PASS=$((PASS + 1))
        else
            echo "  -> FAIL (exit $exit_code)"
            FAIL=$((FAIL + 1))
        fi
    fi
}

echo "Neo4j Schema Overhaul — Full Test Suite"
echo "========================================"
echo "Started: $(date)"

# Phase 1 tests
run_test "V1 Deprecation" python3 ~/.openclaw/agents/main/scripts/tests/test_v1_deprecation.py
run_test "Migration Dry Run" python3 ~/.openclaw/agents/main/scripts/neo4j_migrate_v1_status.py --dry-run

# Phase 2 tests
run_test "CAS Fencing" python3 ~/.openclaw/agents/main/scripts/tests/test_cas_fencing.py
run_test "Orphan Lifecycle" python3 ~/.openclaw/agents/main/scripts/tests/test_orphan_lifecycle.py
run_test "SPAWNED Depth" python3 ~/.openclaw/agents/main/scripts/tests/test_spawned_depth.py

# Phase 3 tests
run_test "Schema Indexes" python3 ~/.openclaw/agents/main/scripts/tests/test_schema_indexes.py

# Phase 4 tests
run_test "Archival" python3 ~/.openclaw/agents/main/scripts/tests/test_archival.py
run_test "Archival Dry Run" python3 ~/.openclaw/agents/main/scripts/neo4j_archive_tasks.py --dry-run

# Built-in self-tests
run_test "V2 Core Self-Test" python3 ~/.openclaw/agents/main/scripts/neo4j_v2_core.py --test
run_test "V2 Schema Self-Test" python3 ~/.openclaw/agents/main/scripts/neo4j_v2_schema.py --test

# Existing regression tests
if [ -f ~/.openclaw/agents/main/tests/test_neo4j_first_flow.sh ]; then
    run_test "Neo4j First Flow" bash ~/.openclaw/agents/main/tests/test_neo4j_first_flow.sh
fi

if [ -f ~/.openclaw/apps/the-kurultai/server.test.js ]; then
    run_test "Server Routes" node ~/.openclaw/apps/the-kurultai/server.test.js
fi

if [ -f ~/.openclaw/apps/the-kurultai/utils.test.js ]; then
    run_test "Server Utils" node ~/.openclaw/apps/the-kurultai/utils.test.js
fi

# Server integration (requires running server)
run_test "Server Endpoint Tests" node ~/.openclaw/apps/the-kurultai/tests/test_schema_overhaul.js

# Stress tests (last — they take longest)
run_test "Connection Pool Stress" python3 ~/.openclaw/agents/main/scripts/tests/test_connection_pool.py

echo ""
echo "========================================"
echo "Finished: $(date)"
echo "TOTAL: $TOTAL | PASS: $PASS | FAIL: $FAIL"
echo "========================================"
[ $FAIL -eq 0 ] && echo "ALL TESTS PASSED" || echo "SOME TESTS FAILED"
exit $FAIL
