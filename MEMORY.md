# Molt Project Memory

## Kurultai Testing & Metrics Framework (Feb 7, 2026)

### Implementation Complete

Comprehensive testing framework implemented across 7 phases with 55+ test files.

**Key Components:**

1. **Interactive Testing** (`tests/interactive/`)
   - `chat_session_recorder.py` - Records and analyzes chat sessions with Kublai
   - `test_scenarios.py` - 6 predefined test scenarios (delegation, multi-agent, capability check, fallback, DAG, security)
   - `run_interactive_tests.py` - CLI tool for manual testing with validation checklists

2. **Integration Tests** (`tests/integration/`)
   - Agent messaging via OpenClaw gateway (port 18789)
   - Neo4j CRUD operations with testcontainers
   - Two-tier heartbeat system validation (infra 30s/120s, functional 90s)

3. **Concurrent & Chaos Tests**
   - Race condition prevention (10 agents, 100 tasks, zero duplicates)
   - Cascading failure recovery
   - Gateway/Neo4j partition handling

4. **Jochi's Test Orchestrator** (`tools/kurultai/test_runner_orchestrator.py`)
   - Periodic test execution (smoke: 15min, full: hourly, nightly: 2AM)
   - Result analysis with severity categorization
   - Auto-remediation for simple issues
   - Ticket creation for complex problems
   - Signal alerts for critical findings

**Configuration Files:**
- `docs/plans/TEST_EXECUTION_PROMPT.md` - Complete testing guide
- `docs/plans/JOCHI_TEST_AUTOMATION.md` - Deployment and configuration
- `tools/kurultai/test_schedule_config.json5` - Schedule and threshold configuration

**Dependencies Added:**
- pytest>=8.0.0, pytest-asyncio, pytest-benchmark, pytest-xdist, pytest-cov
- testcontainers, faker, freezegun, hypothesis
- prometheus-client

**Test Commands:**
```bash
# Run all tests
pytest tests/ -v

# Interactive scenarios
python tests/interactive/run_interactive_tests.py list

# Jochi orchestrator
python tools/kurultai/test_runner_orchestrator.py
```

---

## OpenClaw Gateway Deployment (Feb 7, 2026)

- **Port**: 18789 (bind to `lan` for internal access)
- **Health check**: `curl http://localhost:18789/health`
- **Config**: `/data/.openclaw/openclaw.json5`
- **WebSocket protocol**: Connect with `role: "operator"`, scopes for admin/approvals/pairing

---

## Two-Tier Heartbeat System (Feb 7, 2026)

### Infrastructure Heartbeat
- **Sidecar process**: `heartbeat_writer.py` writes every 30 seconds
- **Node property**: `Agent.infra_heartbeat`
- **Threshold**: 120 seconds (4 missed intervals = hard failure)

### Functional Heartbeat
- **Updated by**: `claim_task()` and `complete_task()` in OperationalMemory
- **Node property**: `Agent.last_heartbeat`
- **Threshold**: 90 seconds (soft failure)

### Standardized Thresholds
All components use consistent thresholds:
- Failover protocol: 120s infra / 90s functional
- Delegation routing: 120s
- Failover monitor: 90s

### Migration Complete
`AgentHeartbeat` node type fully migrated to `Agent` node with two heartbeat properties.

---

## kublai.kurult.ai Domain (Feb 7, 2026)

- **DNS**: Cloudflare managed (CNAME to Railway)
- **CNAME target**: `cryqc2p5.up.railway.app`
- **Status**: Certificate validation in progress
- **Action**: After cert issued, update Authentik provider external_host + brand domain
