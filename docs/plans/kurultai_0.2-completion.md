# Completion Prompt: Kurultai v0.2 Deployment

## Context

This is a completion prompt for the Kurultai v0.2 Railway deployment plan.

**Original Plan**: `docs/plans/kurultai_0.2.md`

**Audit Summary**:
- **Status**: 9 of 11 phases complete (82%)
- **Complete**: Phases 0, 1, 1.5, 2, 3, 4, 4.5, 5, 6, 6.5
- **Partial**: Phase -1 (Wipe and Rebuild - procedures documented but NOT executed), Phase 7 (Testing - tests exist but not verified)
- **Missing**: None - all code is implemented

The system has significant code coverage but requires integration fixes before deployment (see kurultai_v0.2_gap_remediation.md). All Dockerfiles, configurations, security controls, and integrations are complete.

## Completed Work (For Reference)

### ✅ Phase 0: Environment & Security Setup
- Secure credentials generated (AUTHENTIK_SECRET_KEY, SIGNAL_LINK_TOKEN, etc.)
- Environment variables documented in `.env.example`

### ✅ Phase 1: Neo4j & Foundation
- Migrations v1/v2/v3 implemented
- `openclaw_memory.py` with circuit breaker and fallback mode
- All Neo4j schema v0.2 node types, constraints, indexes defined

### ✅ Phase 1.5: Task Dependency Engine
- `tools/kurultai/intent_buffer.py` - 45-second message batching
- `tools/kurultai/dependency_analyzer.py` - semantic similarity detection
- `tools/kurultai/topological_executor.py` - DAG execution with agent routing

### ✅ Phase 2: Capability Acquisition System
- `tools/kurultai/security/prompt_injection_filter.py` - 7 injection patterns + NFKC normalization
- `tools/kurultai/security/cost_enforcer.py` - budget enforcement with reservations
- `tools/kurultai/sandbox_executor.py` - subprocess sandbox with resource limits
- `tools/kurultai/static_analysis/ast_parser.py` - AST-based vulnerability detection
- `tools/kurultai/capability_registry.py` - CBAC implementation
- `tools/kurultai/horde_learn_adapter.py` - 6-phase learning pipeline

### ✅ Phase 3: Railway Deployment
- `authentik-server/Dockerfile` - ENTRYPOINT [] + CMD ["dumb-init", "--", "ak", "server"]
- `authentik-worker/Dockerfile` - worker configuration
- `authentik-proxy/Dockerfile` - Caddy 2 Alpine
- `moltbot-railway-template/Dockerfile` - Node 20 + Java 17 + signal-cli v0.13.12

### ✅ Phase 4: Signal Integration (Preserved)
- `moltbot-railway-template/src/index.js` - legacy Signal-CLI process management (gateway now handled by OpenClaw)
- signal-cli bound to `127.0.0.1:8081` (localhost only)
- Health checks and graceful shutdown implemented

### ✅ Phase 4.5: Notion Integration
- `tools/notion_sync.py` - complete sync handler with reconciliation
- Status/priority mappings, agent routing, audit trail

### ✅ Phase 5: Authentik Web App Integration
- `authentik-proxy/Caddyfile` - forward_auth configuration
- Bypass routes: `/setup/api/signal-link`, `/ws/*`, `/outpost.goauthentik.io/*`, `/flows/*`, `/health`
- X-Authentik-* headers passed through

### ✅ Phase 6: Monitoring & Health Checks
- Health endpoints: `/health`, `/health/neo4j`, `/health/disk`, `/health/file-consistency`
- Structured logging (Winston with daily rotation) in moltbot gateway
- Log rotation configured (winston-daily-rotate-file)

### ✅ Phase 6.5: File Consistency Monitoring
- `tools/kurultai/ogedei_file_monitor.py` - periodic scans (5-minute interval)
- `tools/file_consistency.py` - hash-based change detection
- Neo4j persistence (FileConsistencyReport, FileConflict nodes)

## Remaining Work

### Phase -1: Wipe and Rebuild (OPTIONAL - Only if fresh deployment needed)

**Status**: Procedures documented, NOT executed

**If you need a clean slate**, execute:
```bash
# Creates backup and deletes all Railway services
./scripts/wipe_and_rebuild.sh
```

### Phase 1 Task 1.4: Generate Agent Keys

**Status**: Schema exists, keys NOT generated

**Implementation**:
```bash
# Run migrations to create AgentKey nodes
python scripts/run_migrations.py --target-version 3

# Generate HMAC-SHA256 keys for all 6 agents
./scripts/generate_agent_keys.sh
```

**Prerequisites**:
- Neo4j database running and accessible
- Environment variables set: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`
- Agent nodes exist in Neo4j (created by migration v3)

**Exit Criteria**:
- [ ] All 6 agents have AgentKey nodes in Neo4j
- [ ] Keys have 90-day expiration
- [ ] `is_active: true` flag set

### Phase 7: Testing & Validation

**Status**: Tests exist, NOT verified as passing

**Test Suite Locations**:
- `tests/chaos/test_failure_scenarios.py`
- `tests/performance/test_dag_scalability.py`
- `tests/security/test_injection_prevention.py`
- `tests/security/test_pii_sanitization.py`
- `tests/integration/test_delegation_workflow.py`
- `tests/integration/test_notion_sync.py`

**End-to-End Tests to Run**:

```bash
# Test 1: Unauthenticated redirect to login
curl -I https://kublai.kurult.ai/dashboard
# Expected: 302 redirect to /if/flow/authentication/

# Test 2: Health check without auth
curl https://kublai.kurult.ai/health
# Expected: 200 with healthy status

# Test 3: Signal link requires token
curl -X POST https://kublai.kurult.ai/setup/api/signal-link \
  -H "Content-Type: application/json" \
  -d '{"phoneNumber": "+1234567890"}'
# Expected: 401 Unauthorized

# Test 4: Neo4j schema validation
# Run in Neo4j Browser:
SHOW INDEXES;
SHOW CONSTRAINTS;
MATCH (a:Agent)-[:HAS_KEY]->(k:AgentKey) RETURN count(*) as key_count;
# Expected: 6 AgentKey nodes

# Test 5: File consistency monitor
curl https://kublai.kurult.ai/health/file-consistency
# Expected: 200 with monitor_running: true
```

**Unit Tests**:
```bash
# Run test suite (unit + integration)
./scripts/run_phase7_tests.sh

# Run with coverage
./scripts/run_phase7_tests.sh --cov
pytest tests/ --cov=src --cov-report=html
open htmlcov/index.html

# Run end-to-end tests against deployed URL
./scripts/run_phase7_tests.sh --e2e --url https://kublai.kurult.ai
```

**Exit Criteria**:
- [ ] All end-to-end tests pass
- [ ] Unit tests pass with >80% coverage
- [ ] Neo4j schema validated
- [ ] Health endpoints return 200
- [ ] Signal linking flow works

### Optional: Kublai Web UI Verification

**Status**: Not verified

**Location**: `steppe-visualization/`

**Verification Steps**:
1. Check `steppe-visualization/app/middleware.ts` reads X-Authentik-* headers
2. Check `steppe-visualization/app/lib/auth.ts` has `requireAuth()` function
3. Verify `/dashboard` route redirects unauthenticated requests

---

## Implementation Instructions

### Phase-by-Phase Completion

**Priority Order**:
1. **Phase 1 Task 1.4** - Generate Agent Keys (required for HMAC authentication)
2. **Phase 7** - Run tests and validation
3. **Phase -1** - Only if fresh deployment needed

### Subagent Dispatch Strategy

**Sequential Requirements**:
- Phase 1 Task 1.4 must be complete before testing (tests need agent keys)
- Phase 7 tests can run in parallel once agent keys exist

**Parallel Opportunities**:
- Within Phase 7, all test suites can run in parallel:
  - Unit tests (pytest)
  - Integration tests (notion sync, delegation)
  - End-to-end tests (curl commands)

### Verification Requirements

Each completed task must have:
- [ ] Implementation matches plan specifications
- [ ] Tests written and passing
- [ ] Integration points verified
- [ ] Documentation updated

## Known Blockers

**Note:** See `docs/plans/kurultai_v0.2_gap_remediation.md` for 14 critical blockers identified post-OpenClaw migration.

---

## Final Deliverables

1. Agent keys generated and stored in Neo4j
2. Test suite passes (unit + integration + e2e)
3. Health endpoints verified
4. Signal linking flow tested
5. Summary of changes

---

**Begin with**: Generate agent keys (Phase 1 Task 1.4), then run Phase 7 tests.

**Deployment Command** (when ready):
```bash
railway up
```
