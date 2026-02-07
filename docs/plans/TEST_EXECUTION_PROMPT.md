# Kurultai Testing & Metrics Framework - Execution Prompt

> **Generated:** 2026-02-07
> **Framework Version:** 1.0
> **Phases:** 7 | **Tasks:** 23 | **Test Files:** 55+

---

## Executive Summary

Execute the comprehensive Kurultai v0.2 multi-agent testing framework to validate:
- Agent communication via OpenClaw gateway (port 18789)
- Neo4j-backed operational memory operations
- Two-tier heartbeat system (infra + functional)
- Delegation protocol with complexity-based routing
- Concurrent access patterns and race condition prevention
- End-to-end workflow validation
- Performance benchmarks and regression detection

---

## Prerequisites

### Environment Setup

```bash
# Verify Python version
python --version  # Should be 3.13+

# Install all test dependencies
pip install -r requirements.txt

# Verify Neo4j is accessible (if running integration tests with real DB)
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="password"

# Verify OpenClaw gateway is running (for agent messaging tests)
curl -f http://localhost:18789/health
```

### Service Status Checklist

- [ ] Neo4j database running (bolt://localhost:7687)
- [ ] OpenClaw gateway running (localhost:18789)
- [ ] All 6 agents registered (kublai, mongke, chagatai, temujin, jochi, ogedei)
- [ ] Environment variables loaded (.env file sourced)

---

## Phase 0: Test Infrastructure Validation

**Goal:** Verify test fixtures and mock agents are functional.

```bash
# Run fixture imports
python -c "
from tests.fixtures.integration_harness import KurultaiTestHarness
from tests.fixtures.mock_agents import MockAgentFactory
from tests.fixtures.test_data import TestDataGenerator

# Test mock agent factory
kublai = MockAgentFactory.create_kublai()
print(f'✓ Created mock Kublai: {kublai.agent_id}, role: {kublai.role}')

# Test data generator
task = TestDataGenerator.simple_task()
print(f'✓ Generated test task: {task[\"id\"]}')

# Test harness
harness = KurultaiTestHarness(gateway_port=18789)
print(f'✓ Created harness with gateway port: {harness.gateway_port}')
"

# Expected output:
# ✓ Created mock Kublai: kublai, role: orchestrator
# ✓ Generated test task: stub-id
# ✓ Created harness with gateway port: 18789
```

**Exit Criteria:**
- All imports successful
- Mock agent factory creates all 6 agent types
- Test data generator produces valid tasks
- Harness initializes without errors

---

## Phase 1: Interactive Workflow Observation Tests

**Goal:** Execute manual chat-based scenarios to observe real workflow processes.

```bash
# List all available test scenarios
python tests/interactive/run_interactive_tests.py list

# Expected output: 6 scenarios
# 0. Simple Delegation to Researcher
# 1. Multi-Agent Collaboration
# 2. Delegation with Capability Check
# 3. Fallback on Specialist Unavailable
# 4. Complex DAG Task Coordination
# 5. Security Audit Task
```

### Manual Test Execution

For each scenario, follow this workflow:

```bash
# Example: Run scenario 0 (Simple Delegation to Researcher)
python tests/interactive/run_interactive_tests.py run 0
```

**Manual Testing Workflow:**

1. **Scenario Setup:**
   - Read the user message from the scenario
   - Connect to Kublai via OpenClaw WebSocket (ws://localhost:18789)
   - Use the chat session recorder to track the interaction

2. **Send Message:**
   ```
   ws.send(JSON.stringify({
     type: "req",
     id: uuidv4(),
     method: "chat.send",
     params: {
       sessionKey: "main",
       message: "<user_message_from_scenario>",
       deliver: false,
       idempotencyKey: uuidv4()
     }
   }))
   ```

3. **Record Observations:**
   - Which agents participated?
   - What was the total duration?
   - Did workflow steps match expected steps?
   - Were all success criteria met?

4. **Save Session:**
   - Sessions auto-save to `tests/interactive/sessions/<scenario_name>_<timestamp>.json`
   - Checklists save to `tests/interactive/checklists/<scenario_name>_<timestamp>_checklist.json`

**Scenarios to Execute:**

| Scenario | Agents Expected | Duration Range | Success Criteria |
|----------|----------------|----------------|------------------|
| Simple Delegation | kublai, mongke | 5-45s | Research sources mentioned, Mongke attribution visible |
| Multi-Agent Collab | kublai, mongke, temujin, chagatai, jochi | 30-180s | FastAPI code + docs + security analysis provided |
| Capability Check | kublai, jochi | 10-60s | Neo4j-specific analysis, actionable recommendations |
| Fallback | kublai, chagatai | 5-30s | Poem generated, completes without error |
| DAG Coordination | kublai, temujin, mongke, chagatai, jochi | 60-300s | Database schema + API + tests + docs |
| Security Audit | kublai, temujin | 15-90s | OWASP Top 10 mentioned, remediation provided |

**Exit Criteria:**
- At least 3 scenarios executed manually
- Session recordings saved with timestamps
- Validation checklists completed
- Architecture validation identifies workflow patterns

---

## Phase 2: Unit & Integration Tests

**Goal:** Verify component-level functionality with real services.

```bash
# Run all integration tests (without container dependencies)
pytest tests/integration/ -v -m "not testcontainers" --tb=short

# Run with coverage
pytest tests/integration/ -v --cov=src --cov-report=html --cov-report=term

# Run specific test suites
pytest tests/integration/test_agent_messaging.py -v
pytest tests/integration/test_neo4j_operations.py -v
pytest tests/integration/test_heartbeat_system.py -v
```

### Critical Tests

**Agent Messaging (test_agent_messaging.py):**
- `test_kublai_to_specialist_message_delivery` - Verify port 18789 routing
- `test_concurrent_delegation_message_ordering` - No message loss under load

**Neo4j Operations (test_neo4j_operations.py):**
- `test_task_lifecycle_crud` - Create, read, update, delete tasks
- `test_concurrent_task_claims_no_race` - Exactly one claim succeeds

**Heartbeat System (test_heartbeat_system.py):**
- `test_infra_heartbeat_sidecar_writes_every_30s` - Infra heartbeat updates
- `test_functional_heartbeat_on_claim_task` - Last heartbeat updates on claim
- `test_failover_check_uses_both_heartbeats` - 120s infra / 90s functional thresholds
- `test_agentheartbeat_migration_complete` - No AgentHeartbeat node references

**Exit Criteria:**
- All integration tests pass
- Neo4j CRUD operations verified
- Heartbeat thresholds standardized across codebase
- Concurrent access patterns validated

---

## Phase 3: Concurrent & Chaos Testing

**Goal:** Validate system behavior under concurrent load and failure conditions.

```bash
# Run concurrent access tests
pytest tests/concurrency/ -v -s

# Run chaos tests
pytest tests/chaos/ -v --tb=short

# Run with multiple workers (pytest-xdist)
pytest tests/concurrency/ tests/chaos/ -v -n auto
```

### Key Tests

**Concurrent Claims (test_concurrent_claims.py):**
- `test_ten_agents_hundred_tasks_no_duplicate_claims` - 100 tasks, 10 agents, zero duplicates

**Cascading Failures (test_cascading_failures.py):**
- `test_agent_failure_cascade` - Multiple simultaneous agent failures
- `test_neo4j_partitions_with_active_tasks` - Neo4j unavailable during processing
- `test_gateway_failure_recovery` - OpenClaw gateway crash recovery

**Exit Criteria:**
- No duplicate task claims under concurrent load
- No deadlocks detected
- System recovers from cascading failures
- Recovery time within acceptable thresholds (< 30s for gateway, < 60s for Neo4j)

---

## Phase 4: End-to-End Workflow Tests

**Goal:** Validate complete user journeys from Signal message to response.

```bash
# Run E2E tests
pytest tests/e2e/ -v --tb=long

# Run specific E2E workflows
pytest tests/e2e/test_user_workflows.py::TestUserWorkflows::test_complete_user_request_via_signal -v
pytest tests/e2e/test_capability_acquisition.py -v
pytest tests/e2e/test_failure_recovery_workflows.py -v
```

### E2E Test Scenarios

**Complete User Request:**
1. Simulate Signal message from user
2. Kublai receives and delegates to specialist
3. Specialist processes and returns result
4. Kublai synthesizes and sends response
5. Verify response received within SLA (< 60s for simple tasks)

**Capability Acquisition:**
1. Send `/learn` command to register new capability
2. Verify Capability node created in Neo4j
3. Test routing uses learned capability
4. Verify CBAC enforcement

**Failure Recovery:**
1. Trigger specialist failure mid-task
2. Verify task reassignment without data loss
3. Trigger Neo4j unavailability
4. Verify fallback mode activation
5. Verify data sync on recovery

**Exit Criteria:**
- E2E Signal request completes in < 60s
- Multi-agent collaboration produces synthesized results
- Capability acquisition creates Neo4j nodes
- Failure recovery meets SLA requirements

---

## Phase 5: Metrics & Observability Validation

**Goal:** Verify metrics collection and dashboard visualization.

```bash
# Start Prometheus (if not running)
docker run -d -p 9090:9090 prom/prometheus

# Start Grafana (if not running)
docker run -d -p 3000:3000 grafana/grafana

# Verify metrics endpoint
curl http://localhost:18789/metrics

# Expected metrics:
# kurultai_classification_confidence_bucket
# kurultai_delegation_latency_seconds_bucket
# kurultai_agent_active_seconds_total
```

### Dashboard Verification

**Grafana Setup:**

```bash
# Import dashboards from monitoring/dashboards/
curl -X POST http://localhost:3000/api/dashboards/import \
  -H "Content-Type: application/json" \
  -u admin:admin \
  -d @monitoring/dashboards/complexity-scoring.json

curl -X POST http://localhost:3000/api/dashboards/import \
  -H "Content-Type: application/json" \
  -u admin:admin \
  -d @monitoring/dashboards/delegation-latency.json

curl -X POST http://localhost:3000/api/dashboards/import \
  -H "Content-Type: application/json" \
  -u admin:admin \
  -d @monitoring/dashboards/agent-utilization.json
```

**Metrics to Verify:**

| Metric | Type | Healthy Threshold |
|--------|------|-------------------|
| `kurultai_classification_confidence` | Histogram | avg > 0.7 |
| `kurultai_delegation_latency_seconds` | Histogram | p95 < 2.5s |
| `kurultai_routing_accuracy` | Gauge | > 85% |
| `kurultai_agent_active_seconds` | Counter | 20-80% utilization |

**Exit Criteria:**
- All metrics exposed at `/metrics` endpoint
- Classification confidence tracking working
- Delegation latency breakdown by component
- Agent utilization tracking per agent
- Grafana dashboards imported and visualizing data

---

## Phase 6: Performance Benchmarking

**Goal:** Establish performance baselines and detect regressions.

```bash
# Run performance benchmarks
pytest tests/performance/test_benchmarks.py --benchmark-only --benchmark-json=output.json

# Compare against baseline (if exists)
python scripts/check_benchmark_regression.py output.json

# Expected baseline targets:
# - Task creation latency p50 < 100ms
# - DAG topological sort (1000 nodes) < 1s
# - Vector similarity search (1000 queries) < 500ms
```

### Benchmark Targets

| Operation | Target (p50) | Target (p95) |
|-----------|--------------|--------------|
| Task creation | < 100ms | < 200ms |
| DAG topological sort (100 nodes) | < 100ms | < 200ms |
| DAG topological sort (1000 nodes) | < 500ms | < 1000ms |
| Vector similarity (100 queries) | < 50ms | < 100ms |
| Vector similarity (1000 queries) | < 250ms | < 500ms |

**Exit Criteria:**
- All benchmarks meet target thresholds
- Benchmark JSON output generated
- No regressions detected vs baseline

---

## Phase 7: CI/CD Pipeline Validation

**Goal:** Verify automated test gates work correctly.

```bash
# Simulate CI/CD pipeline execution locally
# Unit tests
pytest tests/unit/ -v --cov=src --cov-report=xml

# Integration tests
pytest tests/integration/ -v --maxfail=3

# Performance regression
pytest tests/performance/test_benchmarks.py --benchmark-json=output.json
python scripts/check_benchmark_regression.py output.json

# E2E tests
pytest tests/e2e/ -v --maxfail=1
```

### Test Gate Configuration

The `.github/workflows/test-gate.yml` pipeline includes:

1. **unit-tests** - Fast unit tests with 80% coverage gate
2. **integration-tests** - Service integration tests (max 3 failures allowed)
3. **performance-regression** - Benchmark comparison vs baseline
4. **e2e-tests** - End-to-end workflow validation (max 1 failure allowed)
5. **chaos-tests** - Failure scenario validation
6. **security-scan** - Dependency vulnerability scan

**Exit Criteria:**
- All test gate jobs pass sequentially
- Coverage threshold enforced (80% minimum)
- Performance regression detected and reported
- Security scan produces report

---

## Test Execution Summary Checklist

After executing all phases, verify:

- [ ] Phase 0: Test fixtures functional
- [ ] Phase 1: At least 3 interactive scenarios completed
- [ ] Phase 2: Integration tests passing
- [ ] Phase 3: Concurrent access validated
- [ ] Phase 4: E2E workflows complete
- [ ] Phase 5: Metrics collection working
- [ ] Phase 6: Performance benchmarks meet targets
- [ ] Phase 7: CI/CD pipeline functional

### Test Results Summary Template

```markdown
## Test Execution Results - [DATE]

### Phase 0: Test Infrastructure
- Status: ✅ PASS / ❌ FAIL
- Details: [notes]

### Phase 1: Interactive Workflows
- Scenarios Completed: X/6
- Pass Rate: X%
- Findings: [notes]

### Phase 2: Integration Tests
- Tests Run: X
- Passed: X
- Failed: X
- Coverage: X%

### Phase 3: Concurrent & Chaos
- Concurrency Tests: X/X passed
- Chaos Tests: X/X passed
- Recovery Times: [notes]

### Phase 4: E2E Workflows
- Workflows Tested: X
- Passed: X
- Failed: X
- Avg Duration: [notes]

### Phase 5: Metrics & Observability
- Metrics Exposed: X/Y
- Dashboards Active: X/3
- Critical Findings: [notes]

### Phase 6: Performance Benchmarks
- Targets Met: X/Y
- Regressions: X
- Baseline Established: Yes/No

### Phase 7: CI/CD Pipeline
- Pipeline Status: ✅ PASS / ❌ FAIL
- Failed Jobs: [list]
```

---

## Troubleshooting

### Common Issues

**Neo4j Connection Failed:**
```bash
# Check Neo4j is running
cypher-shell -u neo4j -p password "RETURN 1"

# Verify connection string in .env
grep NEO4J_URI .env
```

**OpenClaw Gateway Unreachable:**
```bash
# Check gateway status
curl http://localhost:18789/health

# Restart gateway if needed
# (depends on your deployment method)
```

**Import Errors:**
```bash
# Ensure all dependencies installed
pip install -r requirements.txt

# Verify Python path
python -c "import sys; print(sys.path)"
```

**Race Condition Failures:**
```bash
# Run with verbose output to diagnose
pytest tests/concurrency/test_concurrent_claims.py -v -s
```

---

## Next Steps After Testing

1. **Fix Failing Tests:** Address any test failures discovered during execution
2. **Update Baselines:** If this is first run, save benchmark outputs as baselines
3. **Configure CI/CD:** Push `.github/workflows/test-gate.yml` to repository
4. **Schedule Regular Runs:** Set up nightly test execution for regression detection
5. **Document Findings:** Record any architecture discoveries or issues found

---

## Appendix: Test File Reference

### Interactive Tests
- `tests/interactive/chat_session_recorder.py` - Session recording and validation
- `tests/interactive/test_scenarios.py` - 6 predefined test scenarios
- `tests/interactive/run_interactive_tests.py` - CLI test runner

### Integration Tests
- `tests/integration/test_agent_messaging.py` - OpenClaw gateway tests
- `tests/integration/test_neo4j_operations.py` - Neo4j CRUD tests
- `tests/integration/test_heartbeat_system.py` - Two-tier heartbeat tests

### Concurrent & Chaos Tests
- `tests/concurrency/test_concurrent_claims.py` - Race condition tests
- `tests/chaos/test_cascading_failures.py` - Multi-component failures

### E2E Tests
- `tests/e2e/test_user_workflows.py` - Complete user journey tests
- `tests/e2e/test_capability_acquisition.py` - `/learn` command tests
- `tests/e2e/test_failure_recovery_workflows.py` - Failure scenario tests

### Performance Tests
- `tests/performance/test_benchmarks.py` - pytest-benchmark tests

### Fixtures
- `tests/fixtures/integration_harness.py` - KurultaiTestHarness
- `tests/fixtures/mock_agents.py` - MockAgentFactory
- `tests/fixtures/test_data.py` - TestDataGenerator with faker

### Monitoring
- `tools/monitoring_extensions.py` - Metrics instrumentation
- `monitoring/dashboards/*.json` - Grafana dashboard configs

---

**END OF TEST EXECUTION PROMPT**
