# Kurultai v0.2 Full Build Prompt

> **Usage**: Copy this entire prompt into a Claude Code session with the molt repository as the working directory. The agent will execute all phases sequentially, create missing files, modify existing ones, deploy to Railway, and verify the system end-to-end.

---

## System Context

You are building **Kurultai v0.2**, a multi-agent orchestration platform with 6 specialized AI agents, Neo4j graph memory, Signal messaging, Authentik SSO, and a Next.js web dashboard. The system runs on Railway.

**Working directory**: The `molt` repository root.

## Required Reference Documents

Before starting ANY phase, read these documents in full. They are your source of truth:

```
# PRIMARY — The deployment plan (3,818 lines). Contains every task, code snippet, and exit criteria.
docs/plans/kurultai_0.2.md

# SECONDARY — Architecture reference (2,172 lines). System design, moltbot.json config, Neo4j schema, API endpoints.
ARCHITECTURE.md
```

**Read both documents fully before writing any code.** Cross-reference between them when the plan says "see ARCHITECTURE.md" or vice versa.

## Existing Codebase (DO NOT recreate — read and extend)

These files already exist. Read each one before modifying or building on top of it:

### Core Python Modules (read for patterns and interfaces)
```
# Migration system — follow this pattern for v3 migration
migrations/migration_manager.py          # MigrationManager class with register_migration(), migrate()
migrations/v1_initial_schema.py          # V1 schema — UP_CYPHER/DOWN_CYPHER class pattern
migrations/v2_kurultai_dependencies.py   # V2 schema — DAG fields, vector indexes

# Task Dependency Engine — already implemented
tools/kurultai/types.py                  # Message, Dependency, DeliverableType, Task dataclasses
tools/kurultai/intent_buffer.py          # IntentWindowBuffer (45s window)
tools/kurultai/dependency_analyzer.py    # DAGBuilder with semantic similarity
tools/kurultai/topological_executor.py   # TopologicalExecutor for task dispatch
tools/kurultai/priority_override.py      # PriorityCommandHandler

# Complexity Scoring System — partially implemented
tools/kurultai/team_size_classifier.py   # TeamSizeClassifier (561 lines, weights normalized)
tools/kurultai/complexity_config.py      # Centralized config (112 lines)
tools/kurultai/complexity_models.py      # Canonical TestCase at line 96 (209 lines)
tools/kurultai/complexity_auth.py        # RBAC ComplexityAuthenticator (83 lines) — NO HMAC yet
tools/kurultai/drift_detector.py         # PSI drift detection, epsilon smoothing (276 lines)

# Delegation & Security
src/protocols/delegation.py              # DelegationProtocol — MODIFY for security fixes

# File Consistency
tools/file_consistency.py                # FileConsistencyChecker (881 lines) — USE as base

# Notion
tools/notion_sync.py                     # Existing Notion integration — reference for patterns
```

### Node.js Gateway (read before modifying)
```
moltbot-railway-template/Dockerfile      # Existing: node:20-slim + signal-cli + Express
moltbot-railway-template/package.json    # Dependencies: express, cors, helmet, winston
moltbot-railway-template/src/index.js    # Gateway entry point with signal-cli spawn
moltbot-railway-template/src/config/     # Signal channel configuration
```

### Infrastructure (read before deploying)
```
.env.example                             # All env vars documented with generation commands
authentik-server/Dockerfile              # Existing Authentik server image
authentik-proxy/Caddyfile                # Existing Caddy proxy config
signal-cli-daemon/Dockerfile             # Reference for signal-cli setup
requirements.txt                         # Python deps — ADD sentence-transformers
```

### Web Dashboard (read before auth integration)
```
steppe-visualization/app/layout.tsx      # Next.js app layout
steppe-visualization/app/page.tsx        # Main page
steppe-visualization/app/lib/            # Utility functions — ADD auth.ts here
steppe-visualization/app/components/     # UI components
```

## Build Execution Plan

Execute the following phases **in order**. Each phase has exit criteria — verify ALL exit criteria pass before moving to the next phase. If a criterion fails, fix it before proceeding.

### PHASE -1: Wipe and Rebuild
**Read**: `docs/plans/kurultai_0.2.md` Phase -1 (starts at "Phase -1: Wipe and Rebuild")

1. Create backup of current Railway state and .env
2. Preserve .signal-data/ (registration data), src/, tools/, tests/ — NOTE: signal-cli-daemon/ and signal-proxy/ are DEPRECATED directories from a previous architecture. They may be kept for reference but are NOT deployed as Railway services.
3. Delete Railway services (authentik-*, moltbot-*)
4. Clean local build artifacts (__pycache__, .pytest_cache, .hypothesis, dist/, build/)
5. Clean Docker volumes

**Exit criteria**: Backup exists, Signal dirs preserved, Railway services deleted, local clean.

### PHASE 0: Environment & Security Setup
**Read**: `docs/plans/kurultai_0.2.md` Phase 0

1. Generate credentials (AUTHENTIK_SECRET_KEY, AUTHENTIK_BOOTSTRAP_PASSWORD, SIGNAL_LINK_TOKEN)
2. Create Railway project or link to existing (project ID: `26201f75-3375-46ce-98c7-9d1dde5f9569`)
3. Set ALL environment variables per Task 0.3 — **including**:
   - NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DATABASE
   - KURLTAI_ENABLED, KURLTAI_MAX_PARALLEL_TASKS
   - AUTHENTIK_SECRET_KEY, AUTHENTIK_BOOTSTRAP_PASSWORD, AUTHENTIK_EXTERNAL_HOST
   - SIGNAL_LINK_TOKEN
   - OPENCLAW_GATEWAY_URL, OPENCLAW_GATEWAY_TOKEN
   - **ANTHROPIC_API_KEY** (REQUIRED for agent functionality)
   - **OPENCLAW_STATE_DIR="/data/.clawdbot"**, **OPENCLAW_WORKSPACE_DIR="/data/workspace"**
   - **PHONE_HASH_SALT**, **EMBEDDING_ENCRYPTION_KEY**
4. Apply security fixes to `src/protocols/delegation.py` (subprocess list args, E.164 validation)
5. Create `tools/kurultai/security/pii_sanitizer.py` per Task 0.5

**Exit criteria**: Railway project exists, ALL env vars set (verify with `railway variables --json`), PII sanitizer created, security fixes applied.

### PHASE 1: Neo4j & Foundation
**Read**: `docs/plans/kurultai_0.2.md` Phase 1

1. Create Neo4j AuraDB Free instance (kurultai-prod, us-east-1)
2. Create `migrations/v3_capability_acquisition.py` following the V1/V2 pattern (UP_CYPHER/DOWN_CYPHER class with register() classmethod). Schema additions per Task 1.3.
3. Create `scripts/run_migrations.py` per Task 1.2
4. Run migrations to v3: `python scripts/run_migrations.py --target-version 3`
5. Verify schema: run Cypher queries to confirm all node types, relationships, constraints, and indexes exist
6. Generate HMAC keys for all 6 agents per Task 1.4 (store as AgentKey nodes in Neo4j)
7. Populate agent profiles per Task 1.5.1

**Exit criteria**: Neo4j connected, migrations v1-v3 applied, 6 agents have AgentKey nodes, schema verified.

### PHASE 1.5: Task Dependency Engine
**Read**: `docs/plans/kurultai_0.2.md` Phase 1.5

The core engine (intent_buffer, dependency_analyzer, topological_executor, priority_override) already exists in `tools/kurultai/`. This phase adds security:

1. Create `tools/kurultai/security/` directory
2. Create `tools/kurultai/security/rate_limiter.py` — 1000 req/hour, 100 req/batch per sender
3. Create `tools/kurultai/security/task_validator.py` — input validation for deliverable types, priority weights
4. Create `tools/kurultai/security/audit_logger.py` — audit logging for task operations
5. Add `sentence-transformers>=2.2.0` to `requirements.txt`
6. Wire OperationalMemory bridge to Neo4j per Task 1.5.2 (embedding model: `sentence-transformers/all-MiniLM-L6-v2`, 384 dims, thresholds: 0.75 high / 0.55 medium)

**Exit criteria**: Security modules created, rate limiter tested, audit logger writes to structlog, requirements.txt updated.

### PHASE 2: Capability Acquisition System
**Read**: `docs/plans/kurultai_0.2.md` Phase 2

1. Create `tools/kurultai/security/prompt_injection_filter.py` (~150 lines) — NFKC normalization, pattern-based filtering
2. Create `tools/kurultai/security/cost_enforcer.py` (~200 lines) — budget pre-authorization
3. Create `tools/kurultai/security/static_analysis.py` (~250 lines) — dangerous pattern detection
4. Create `tools/kurultai/sandbox_executor.py` (~400 lines) — subprocess sandbox with resource limits
5. Create `tools/kurultai/horde_learn_adapter.py` (~500 lines) — horde-learn 6-phase pipeline integration
6. Create `tools/kurultai/capability_registry.py` (~350 lines) — Neo4j-backed capability storage with CBAC
7. Create `tools/kurultai/static_analysis/ast_parser.py` (~300 lines) — tree-sitter based AST analysis

**Exit criteria**: All modules created, prompt injection filter catches test patterns, sandbox executes safely, capability can be registered in Neo4j.

### PHASE 3: Railway Deployment
**Read**: `docs/plans/kurultai_0.2.md` Phase 3 + ARCHITECTURE.md moltbot.json section

1. Modify `moltbot-railway-template/Dockerfile` per Task 3.4:
   - Keep node:20-slim base with signal-cli
   - Add Python 3.11+, supervisord, dumb-init
   - Add agent workspace directories (`/data/workspace/souls/{main,researcher,writer,developer,analyst,ops}`)
   - Configure supervisord for Node.js gateway + Python OperationalMemory bridge
   - **Note**: The Dockerfile MUST include the `agentToAgent` binding in moltbot.json config (see ARCHITECTURE.md)
2. Add missing npm dependencies: `http-proxy-middleware`, `express-rate-limit`
3. Create `moltbot-railway-template/supervisord.conf`
4. Create `moltbot-railway-template/routes/health.js` — /health, /health/neo4j, /health/disk endpoints
5. Create `moltbot-railway-template/routes/auth.js` — /api/auth/me reading Authentik X-Authentik-* headers
6. Deploy Railway services:
   - `railway up` for authentik-server (from authentik-server/Dockerfile)
   - `railway up` for authentik-worker (from authentik-worker/Dockerfile)
   - `railway up` for authentik-proxy (from authentik-proxy/Caddyfile)
   - `railway up` for moltbot-railway-template
7. Attach PostgreSQL to authentik-server
8. Create persistent volume at `/data` for moltbot-railway-template
9. Create persistent volume for Signal data

**Exit criteria**: All 4 Railway services running, health checks passing, `curl https://kublai.kurult.ai/health` returns 200.

### PHASE 4: Signal Integration
**Read**: `docs/plans/kurultai_0.2.md` Phase 4

Signal runs INSIDE moltbot as a child process (OpenClaw auto-spawn pattern). signal-cli-daemon and signal-proxy are NOT separate Railway services.

1. Verify signal-cli embedded in moltbot Dockerfile
2. Restore Signal registration data from `.signal-data/signal-data.tar.gz` into the container
3. Configure moltbot.json channels.signal per ARCHITECTURE.md (account, allowFrom, groupAllowFrom)
4. Verify Signal connectivity: send test message from admin phone, confirm bot receives and responds
5. Create Railway volume for Signal data persistence (`/data/.signal` mapped to Railway persistent volume)

**Exit criteria**: Signal messages sent to bot phone number get responses, Signal data persists across container restarts.

### PHASE 4.5: Notion Integration
**Read**: `docs/plans/kurultai_0.2.md` Phase 4.5

1. Reference existing `tools/notion_sync.py` for patterns
2. Create `tools/kurultai/notion_client.py` — NotionTaskClient for Notion API
3. Create `tools/kurultai/notion_sync_handler.py` — bidirectional sync with field mapping
4. Create `tools/kurultai/notion_polling.py` — Ogedei's continuous polling engine
5. Create `tools/kurultai/reconciliation.py` — conflict resolution with Neo4j as source of truth
6. Create `tests/integration/test_notion_sync.py`

**Exit criteria**: Notion tasks sync to Neo4j, Neo4j task updates sync back to Notion, conflicts resolve correctly.

### PHASE 5: Authentik Web App Integration
**Read**: `docs/plans/kurultai_0.2.md` Phase 5

1. Configure Authentik admin at `https://kublai.kurult.ai/if/admin/`
2. Create Authentik application and proxy provider for the web dashboard
3. Set up WebAuthn/FIDO2 authentication flow
4. Create `steppe-visualization/app/lib/auth.ts` — read X-Authentik-* headers
5. Modify `steppe-visualization/app/middleware.ts` — add Authentik header checking
6. Create `moltbot-railway-template/routes/auth.js` — /api/auth/me endpoint

**Exit criteria**: Navigating to `https://kublai.kurult.ai` redirects to Authentik login, after auth user sees dashboard, X-Authentik-Username header is present.

### PHASE 6: Monitoring & Health Checks
**Read**: `docs/plans/kurultai_0.2.md` Phase 6

1. Create `moltbot-railway-template/middleware/logger.js` — Pino structured logging
2. Enhance health check endpoints with Neo4j connectivity check, disk space check
3. Configure log rotation and Railway log drain
4. Set up alerting thresholds

**Exit criteria**: Structured JSON logs visible in Railway, health endpoints return detailed status, Neo4j health check works.

### PHASE 6.5: File Consistency Monitoring
**Read**: `docs/plans/kurultai_0.2.md` Phase 6.5

1. Read existing `tools/file_consistency.py` (881 lines) — USE as base
2. Create `tools/kurultai/ogedei_file_monitor.py` — Ogedei's workspace monitoring agent
3. Integrate with health check endpoint (/health/files)

**Exit criteria**: File changes detected, conflicts flagged, health endpoint reports file consistency status.

### PHASE 7: Testing & Validation
**Read**: `docs/plans/kurultai_0.2.md` Phase 7

Run the FULL test suite to validate everything works end-to-end:

```bash
# 1. Python unit tests
python -m pytest tests/ -v --tb=short

# 2. Neo4j schema validation
python scripts/run_migrations.py --target-version 3 --dry-run

# 3. API endpoint tests
curl -f https://kublai.kurult.ai/health
curl -f https://kublai.kurult.ai/health/neo4j
curl -f https://kublai.kurult.ai/api/auth/me -H "Cookie: <authentik_session>"

# 4. Signal conversation test (REQUIRED — proves end-to-end messaging works)
#    From admin phone, send Signal message: "Hello, are you online?"
#    EXPECTED: Bot responds within 60 seconds with a coherent greeting
#    Then send: "What can you help me with?"
#    EXPECTED: Bot describes its capabilities (multi-agent, research, writing, etc.)
#    Then send: "@researcher Summarize what Neo4j is in one sentence"
#    EXPECTED: Kublai delegates to Möngke, response mentions graph database
#    FAILURE CRITERIA: No response after 120s, garbled output, or delegation doesn't reach Möngke

# 5. Web UI conversation test (REQUIRED — proves authenticated chat works)
#    a. Open https://kublai.kurult.ai in browser
#    b. EXPECTED: Redirect to Authentik login page
#    c. Authenticate with WebAuthn or password
#    d. EXPECTED: Dashboard loads, chat interface is visible
#    e. Type in chat: "Hello Kublai, who are your team members?"
#    f. EXPECTED: Response names the 6 agents (Möngke, Chagatai, Temüjin, Jochi, Ögedei)
#    g. Type: "@developer Write a Python hello world function"
#    h. EXPECTED: Temüjin is delegated to, returns a Python function
#    FAILURE CRITERIA: Auth loop, blank dashboard, no chat response, delegation fails

# 6. Cross-channel verification (REQUIRED — proves both channels use same agent state)
#    Send via Signal: "Remember that my favorite color is blue"
#    Then in web UI: "What is my favorite color?"
#    EXPECTED: Agent recalls "blue" from operational memory (Neo4j)
#    This confirms both channels share the same Neo4j-backed memory

# 7. Load test (optional)
python -m pytest tests/performance/test_load.py -v
```

### FINAL VERIFICATION CHECKLIST

After all phases complete, verify each of these manually:

- [ ] `https://kublai.kurult.ai/health` returns `{"status": "healthy"}`
- [ ] `https://kublai.kurult.ai/health/neo4j` returns connected status
- [ ] Authentik login works with WebAuthn at `https://kublai.kurult.ai/if/flow/default-authentication-flow/`
- [ ] Web dashboard loads after authentication
- [ ] **WEB UI CONVERSATION**: Send "Hello Kublai" in web UI chat → get coherent response within 30s
- [ ] **WEB UI DELEGATION**: Send "@developer Write a hello world" in web UI → Temüjin responds with code
- [ ] **SIGNAL CONVERSATION**: Send "Hello" to bot via Signal from admin phone → get response within 60s
- [ ] **SIGNAL DELEGATION**: Send "@researcher What is Neo4j?" via Signal → Möngke responds with description
- [ ] **CROSS-CHANNEL MEMORY**: Store a fact via Signal, retrieve it via web UI (confirms shared Neo4j memory)
- [ ] Neo4j has all 6 agent nodes, AgentKey nodes, and correct schema
- [ ] All Python tests pass: `python -m pytest tests/ -v`
- [ ] Railway logs show structured JSON logging
- [ ] Signal data persists after container restart (check with `railway restart`)
- [ ] PII sanitizer redacts phone numbers in delegated messages

## Critical Constraints

1. **Signal data is SACRED** — never delete `.signal-data/` or the `/data/.signal` volume. Re-linking requires physical access to the phone.
2. **Environment variables** — verify ALL with `railway variables --json` after setting. Railway's table display truncates values.
3. **HMAC middleware is DEFERRED to v0.3** — generate the keys now (AgentKey nodes) but don't implement signing/verification middleware.
4. **Rate limits**: 1000/hour, 100/batch (NOT 100/50).
5. **moltbot.json must include `agentToAgent`** config for inter-agent messaging.
6. **Port 18789** is the OpenClaw internal gateway port. Port 8080 is the Express health check / Railway port. **Port 8081** is the embedded signal-cli HTTP daemon (localhost only).
7. **Railway strips Docker CMD** — use `ENTRYPOINT []` + `CMD [...]` format.
8. **`railway up` uploads entire cwd** — use a temp directory with just the Dockerfile + required files for minimal deploys.
9. **Complexity scoring Appendix H** — `threshold_calibrator.py` and `test_case_registry.py` DO NOT EXIST yet. Mark them as Phase 4 pending items, don't block deployment on them.
10. **`complexity_validation_framework.py` is 2,250 lines** — decomposition is a separate task, don't attempt during this build.

## Error Recovery

If a phase fails:
- **Neo4j connection fails**: Check NEO4J_URI uses `neo4j+s://` (not `bolt://`) for AuraDB
- **Railway deploy fails**: Check Dockerfile builds locally first with `docker build -t test .`
- **Signal doesn't respond**: Check signal-cli process is running inside container with `railway logs`
- **Authentik redirect loop**: Verify AUTHENTIK_EXTERNAL_HOST matches the custom domain exactly
- **Health check 502**: Service is still starting — wait 60s for signal-cli startup timeout
- **Agent delegation fails**: Verify moltbot.json has `agentToAgent.enabled: true` and all 6 agents in `allow` array
