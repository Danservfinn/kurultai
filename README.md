# Kurultai

**Multi-agent orchestration platform with autonomous capability acquisition, graph-based operational memory, and end-to-end encrypted messaging.**

Kurultai deploys 6 specialized AI agents that collaborate through a shared Neo4j knowledge graph, communicate via Signal Protocol, and learn new capabilities on demand. The system runs on Railway with Authentik SSO and a 3D visualization dashboard.

```
               kublai.kurult.ai
                     │
            ┌────────▼────────┐
            │  Authentik SSO  │ ◄── WebAuthn / Passwordless
            │  (Caddy Proxy)  │
            └────────┬────────┘
                     │ forward_auth
    ┌────────────────▼────────────────┐
    │     Moltbot Gateway Container   │
    │  ┌──────────┐  ┌────────────┐  │
    │  │ OpenClaw  │  │ signal-cli │  │
    │  │ Gateway   │  │ (embedded) │  │
    │  │  :18789   │  │ :8081 (lo) │  │
    │  └─────┬─────┘  └─────┬──────┘  │
    │        │    spawns ▲   │         │
    │        └───────────────┘         │
    │  ┌──────────────────────────┐   │
    │  │ Heartbeat Sidecar (py)   │   │
    │  │ writes Agent.infra_hb/30s│   │
    │  └──────────────────────────┘   │
    └─────────────┬───────────────────┘
                  │
         ┌────────▼────────┐
         │  Neo4j AuraDB   │ ◄── Graph operational memory
         │  (neo4j+s://)   │
         └─────────────────┘
```

---

## Agents

| ID | Name | Role | Specialization |
|----|------|------|----------------|
| `main` | **Kublai** | Orchestrator | Delegation, personal memory, PII sanitization |
| `researcher` | **Mongke** | Research | Web search, API research, knowledge synthesis |
| `writer` | **Chagatai** | Content | Documentation, reports, communication |
| `developer` | **Temujin** | Development | Code generation, implementation, testing |
| `analyst` | **Jochi** | Analysis | AST parsing, security audit, backend monitoring |
| `ops` | **Ogedei** | Operations | Infrastructure, failover, file consistency |

All agents share operational memory through Neo4j and communicate via HMAC-SHA256 signed messages. Kublai sanitizes PII before delegating to other agents.

---

## Architecture

### Railway Services

```
┌─────────────────────────────────────────────────────────────────┐
│                        Railway Deployment                        │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  Authentik   │  │  Authentik   │  │  Authentik Proxy     │  │
│  │  Server      │  │  Worker      │  │  (Caddy) :8080       │  │
│  │  :9000       │  │  (bg tasks)  │  │  kublai.kurult.ai    │  │
│  └──────┬───────┘  └──────────────┘  └──────────┬───────────┘  │
│         │                                        │               │
│         └────────────┐      ┌────────────────────┘               │
│                      │      │ forward_auth                       │
│  ┌───────────────────▼──────▼───────────────────────────────┐   │
│  │  Moltbot (moltbot-railway-template)                       │   │
│  │  ┌─────────────┐ ┌────────────┐ ┌────────────────────┐  │   │
│  │  │ OpenClaw GW │ │ signal-cli │ │ Heartbeat Sidecar  │  │   │
│  │  │ :18789      │ │ :8081 (lo) │ │ (Python, bg)       │  │   │
│  │  └─────────────┘ └────────────┘ └────────────────────┘  │   │
│  └──────────────────────────┬───────────────────────────────┘   │
│                              │                                    │
│  ┌───────────────┐  ┌───────▼──────┐  ┌───────────────────┐    │
│  │  PostgreSQL   │  │  Neo4j 5     │  │  Steppe Dashboard │    │
│  │  (Authentik)  │  │  (Graph DB)  │  │  (Next.js)        │    │
│  └───────────────┘  └──────────────┘  └───────────────────┘    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Service Matrix

| Service | Image | Port | Health Check | Purpose |
|---------|-------|------|-------------|---------|
| `authentik-server` | `ghcr.io/goauthentik/server:2025.10.0` | 9000 | `/-/health/ready/` | SSO identity provider |
| `authentik-worker` | Same | — | — | Background tasks |
| `authentik-proxy` | Caddy 2 Alpine | 8080 | `/health` | Forward auth + reverse proxy |
| `moltbot-railway-template` | Node 22 + Java 17 + Python 3 | 18789 | `/health` | Agent gateway + Signal |
| `neo4j` | `neo4j:5-community` | 7474/7687 | `/` | Graph operational memory |
| `authentik-db` | `postgres:15-alpine` | 5432 | `pg_isready` | Authentik database |

### Data Flow

```
User Message (Signal or Web)
         │
         ▼
    Caddy Proxy ──► Authentik (auth check)
         │
         ▼
    OpenClaw Gateway ──► Kublai (main agent)
         │
    ┌────┼──────┬──────┬──────┐
    ▼    ▼      ▼      ▼      ▼
 Mongke Chagatai Temujin Jochi Ogedei
    │      │      │      │      │
    └──────┴──────┴──────┴──────┘
                  │
                  ▼
         Neo4j (shared memory)
                  │
                  ▼
         Kublai synthesizes response
                  │
                  ▼
         Response to user
```

---

## Key Features

### Two-Tier Memory

| Tier | Storage | Access | Contents |
|------|---------|--------|----------|
| **Personal** | Files (`/data/workspace/souls/{agent}/`) | Kublai only | User preferences, PII, personal history |
| **Operational** | Neo4j AuraDB | All 6 agents | Research, code patterns, tasks, capabilities |

### Task Dependency Engine

Kublai builds DAGs of tasks from rapid-fire user messages, then executes them in topological order with parallel batching.

```
User sends 3 messages in 45s
         │
    IntentWindowBuffer (collects messages)
         │
    DAGBuilder (detects dependencies via semantic similarity)
         │
    TopologicalExecutor (dispatches independent batches in parallel)
         │
    Priority overrides ("do X before Y", "focus on X")
```

### Capability Acquisition (6-Phase Pipeline)

Agents learn new capabilities through natural language: `/learn how to send SMS`

```
Classification ──► Research ──► Implementation ──► Validation ──► Registration ──► Authorization
  (Kublai)        (Mongke)      (Temujin)          (Jochi)        (Kublai)        (Kublai)
                                                  AST analysis                    CBAC grants
                                                  + sandbox
```

**Security controls:** Prompt injection filter (NFKC normalization), cost enforcer (budget pre-authorization), sandbox executor (rlimit-based), AST analyzer (tree-sitter), CBAC trust levels.

### Two-Tier Heartbeat System

```
Tier 1: Infrastructure Heartbeat
  └── Python sidecar writes Agent.infra_heartbeat every 30s
  └── Proves: gateway process is alive
  └── Timeout: 120s (4 missed beats) = hard failure

Tier 2: Functional Heartbeat
  └── Updated on claim_task() and complete_task()
  └── Proves: agent is actively working
  └── Timeout: 90s (3 missed beats) = soft failure
```

Ogedei monitors both tiers and activates as emergency router when Kublai fails 3 consecutive health checks.

### Neo4j Fallback Mode

Circuit breaker (5 failures → open) with automatic recovery:
- In-memory fallback store during outages
- Background daemon checks connectivity every 30s
- Auto-syncs fallback store to Neo4j on recovery
- <10% failure rate threshold for exiting fallback

---

## Project Structure

```
molt/
├── ARCHITECTURE.md                  # Detailed system architecture (2200+ lines)
├── railway.yml                      # Railway deployment configuration
├── openclaw_memory.py               # OperationalMemory class (Neo4j interface)
│
├── moltbot-railway-template/        # Main gateway container
│   ├── Dockerfile                   # Node 22 + Java 17 + Python 3 + OpenClaw
│   ├── entrypoint.sh               # Orchestration: migrations → Signal → heartbeat → gateway
│   ├── openclaw.json5              # Agent configuration (6 agents, Signal, auth)
│   ├── src/index.js                # Express gateway + signal-cli management
│   ├── routes/health.js            # Health check endpoints
│   └── scripts/
│       ├── heartbeat_writer.py     # Infra heartbeat sidecar
│       ├── run_migrations.py       # Neo4j schema migration runner
│       ├── model_switcher.py       # LLM model/provider switching
│       └── generate_agent_keys.sh  # HMAC key generation
│
├── src/protocols/                   # Agent coordination protocols
│   ├── delegation.py               # Task delegation with heartbeat checks
│   ├── failover.py                 # Two-tier failover detection
│   ├── security_audit.py           # Security validation
│   ├── file_consistency.py         # Cross-agent file consistency
│   └── backend_analysis.py         # Backend analysis protocol
│
├── tools/                           # Agent tooling
│   ├── failover_monitor.py         # Failover monitoring
│   ├── notion_sync.py              # Notion bidirectional sync
│   ├── memory_tools.py             # Memory utilities
│   └── kurultai/                   # Core Kurultai framework
│       ├── topological_executor.py # DAG-based task execution
│       ├── dependency_analyzer.py  # Semantic dependency detection
│       ├── intent_buffer.py        # Message batching window
│       ├── priority_override.py    # Real-time priority commands
│       ├── ogedei_file_monitor.py  # File consistency monitoring
│       ├── sandbox_executor.py     # rlimit-based code sandbox
│       ├── capability_registry.py  # Capability registration
│       ├── team_size_classifier.py # Complexity-based team sizing
│       ├── security/               # Security controls
│       │   ├── prompt_injection_filter.py
│       │   ├── cost_enforcer.py
│       │   └── pii_sanitizer.py
│       └── static_analysis/        # AST analysis
│           └── ast_parser.py
│
├── migrations/                      # Neo4j schema versions
│   ├── migration_manager.py        # Version tracking + rollback
│   ├── v1_initial_schema.py        # Agents, Research, CodePattern
│   ├── v2_kurultai_dependencies.py # Task DAG, indexes
│   └── v3_capability_acquisition.py # CBAC, LearnedCapability, 18 node types
│
├── steppe-visualization/            # Next.js 3D dashboard
│   ├── app/page.tsx                # 3D agent visualization (Three.js)
│   ├── app/control-panel/          # System monitoring dashboard
│   ├── app/mission-control/        # Goal orchestration panel
│   ├── app/api/                    # REST endpoints (agents, tasks, etc.)
│   └── app/components/
│       ├── agents/                 # Agent visualization (camps, meshes)
│       ├── scene/                  # 3D terrain, rivers, sky
│       └── ui/                     # Panels, minimap, header
│
├── authentik-server/                # Authentik SSO server Dockerfile
├── authentik-worker/                # Authentik background worker Dockerfile
├── authentik-proxy/                 # Caddy reverse proxy
│   ├── Caddyfile                   # Forward auth + route config
│   └── config/proxy-provider.yaml  # Authentik provider blueprint
│
├── tests/                           # 55+ test files
│   ├── integration/                # Failover, delegation, heartbeat
│   ├── security/                   # Injection prevention, PII
│   ├── performance/                # DAG scalability, load testing
│   ├── chaos/                      # Cascading failures, corruption
│   ├── kurultai/                   # Complexity scoring, team sizing
│   └── e2e/                        # Full user workflows
│
└── .github/workflows/
    ├── tests.yml                   # Multi-version pytest (3.11-3.13)
    ├── test-gate.yml               # Unit + integration gates (70% coverage)
    └── quality-gates.yml           # Security scanning, performance benchmarks
```

---

## Common Workflows

### Sending a Message via Signal

```
User sends Signal message to +15165643945
         │
    signal-cli daemon (localhost:8081) receives message
         │
    OpenClaw gateway routes to Kublai (main agent)
         │
    Kublai:
    ├── Reads personal context from /data/workspace/souls/main/MEMORY.md
    ├── Queries operational context from Neo4j
    ├── Sanitizes PII via PIISanitizer
    ├── Delegates to specialist agent (if needed) with HMAC signature
    │   └── Specialist writes results to Neo4j
    └── Synthesizes response → Signal reply
```

### Learning a New Capability

```
User: "/learn how to call phones"
         │
    Phase 1: Kublai classifies → type=external_api, risk=medium
         │
    Phase 2: Mongke researches Twilio API → Research nodes in Neo4j
         │
    Phase 3: Temujin generates tools/twilio_client.py + tests
         │
    Phase 4: Jochi runs AST analysis (tree-sitter) + sandbox tests
         │   ├── No eval/exec/compile detected ✓
         │   ├── No SQL injection patterns ✓
         │   └── Sandbox execution within resource limits ✓
         │
    Phase 5: Kublai creates LearnedCapability node in Neo4j
         │
    Phase 6: Kublai grants HAS_CAPABILITY to authorized agents (CBAC)
```

### Task Dependency Resolution

```
User sends 3 messages rapidly:
  1. "Research competitor pricing"
  2. "Write a pricing proposal"
  3. "Review the proposal for accuracy"
         │
    IntentWindowBuffer collects for 45s
         │
    DAGBuilder:
         │
    ┌─────────────┐      ┌──────────────┐      ┌──────────────┐
    │  Research    │─────►│   Write      │─────►│   Review     │
    │  (Mongke)   │      │  (Chagatai)  │      │   (Jochi)    │
    │  BATCH 1    │      │  BATCH 2     │      │   BATCH 3    │
    └─────────────┘      └──────────────┘      └──────────────┘
         │
    TopologicalExecutor dispatches batches sequentially
    Priority override: "do the review first" → reorders DAG
```

### Failover Sequence

```
    Heartbeat sidecar writes Agent.infra_heartbeat every 30s
         │
    Ogedei checks both heartbeat tiers:
         │
    ┌── infra_heartbeat stale > 120s? ──► HARD FAILURE (gateway dead)
    │
    └── last_heartbeat stale > 90s? ──► SOFT FAILURE (agent stuck)
         │
    Failover activated:
    ├── Ogedei becomes emergency router
    ├── Pending tasks redistributed to available agents
    └── Alert logged to Neo4j
```

### Authentication Flow

```
    Browser → https://kublai.kurult.ai/dashboard
         │
    Caddy proxy → Authentik forward_auth check
         │
    ┌── Authenticated? ──► Proxy to moltbot + X-Authentik-* headers
    │
    └── Not authenticated? ──► Redirect to /if/flow/authentication/
         │
    WebAuthn challenge (security key or biometric)
         │
    Session cookie set → Redirect back to /dashboard
```

---

## Quick Start

### Prerequisites

- [Railway CLI](https://docs.railway.app/guides/cli) installed
- Neo4j AuraDB instance (or use Railway's Neo4j service)
- Cloudflare DNS (for `kublai.kurult.ai`)

### Environment Variables

Generate secure credentials:

```bash
# Required secrets (set in Railway dashboard)
openssl rand -hex 32    # AUTHENTIK_SECRET_KEY
openssl rand -base64 24 # AUTHENTIK_BOOTSTRAP_PASSWORD
openssl rand -hex 32    # SIGNAL_LINK_TOKEN
openssl rand -base64 48 # OPENCLAW_GATEWAY_TOKEN
```

Key variables:

| Variable | Description |
|----------|-------------|
| `NEO4J_URI` | Neo4j connection string |
| `NEO4J_PASSWORD` | Neo4j password |
| `ANTHROPIC_API_KEY` | LLM API key |
| `OPENCLAW_GATEWAY_TOKEN` | Gateway authentication |
| `SIGNAL_ACCOUNT` | Signal phone number (E.164) |
| `AUTHENTIK_SECRET_KEY` | Authentik signing key |
| `AUTHENTIK_BOOTSTRAP_PASSWORD` | Initial admin password |

See `.env.example` and `ARCHITECTURE.md` for the full list of 30+ variables.

### Deploy

```bash
# 1. Clone and configure
git clone <repo-url> && cd molt
cp .env.example .env
# Edit .env with your credentials

# 2. Deploy to Railway
railway up

# 3. Run migrations
python scripts/run_migrations.py --target-version 3

# 4. Bootstrap Authentik
python authentik-proxy/bootstrap_authentik.py

# 5. Verify
curl https://kublai.kurult.ai/health
```

### Local Development

```bash
# Python dependencies
pip install -r requirements.txt

# Run tests
python -m pytest tests/ -v

# Run specific test suites
python -m pytest tests/security/ -v        # Security tests
python -m pytest tests/performance/ -v     # Performance benchmarks
python -m pytest tests/integration/ -v     # Integration tests (needs Neo4j)

# Steppe visualization dashboard
cd steppe-visualization
npm install && npm run dev
# Open http://localhost:3000
```

---

## Testing

55+ test files across 8 categories:

| Category | Directory | Tests | Description |
|----------|-----------|-------|-------------|
| Unit | `tests/` | 17 files | Core module tests |
| Integration | `tests/integration/` | 8 files | Cross-service workflows |
| Security | `tests/security/` | 2 files | Injection prevention, PII |
| Performance | `tests/performance/` | 3 files | DAG scalability, load |
| Chaos | `tests/chaos/` | 3 files | Cascading failures, corruption |
| Kurultai | `tests/kurultai/` | 5 files | Complexity scoring, team sizing |
| Concurrency | `tests/concurrency/` | 1 file | Task claim race conditions |
| E2E | `tests/e2e/` | 1 file | Full user workflows |

CI runs on Python 3.11, 3.12, and 3.13 with 70% coverage gate.

---

## API Endpoints

| Endpoint | Auth | Description |
|----------|------|-------------|
| `GET /health` | None | Service health + dependency status |
| `GET /health/neo4j` | None | Neo4j connection details |
| `GET /health/disk` | None | Volume disk usage |
| `GET /health/file-consistency` | None | File monitor status |
| `GET /api/auth/me` | Authentik | Current user info |
| `POST /api/learn` | Authentik | Learn new capability |
| `POST /agent/{id}/message` | Gateway token | Send message to agent |
| `POST /setup/api/signal-link` | X-Signal-Token | QR code device linking |

---

## Neo4j Schema

30+ node types across 3 migration versions. Key nodes:

| Node | Purpose |
|------|---------|
| `:Agent` | Agent identity + heartbeat timestamps |
| `:Task` | Task with DAG dependencies and embeddings |
| `:Research` | Research findings with vector embeddings |
| `:LearnedCapability` | Capabilities from /learn pipeline |
| `:Capability` | CBAC capability definitions |
| `:AgentKey` | HMAC-SHA256 signing keys |
| `:FileConsistencyReport` | File monitoring results |
| `:SyncEvent` | Notion sync audit trail |

Key relationships: `(Agent)-[:HAS_KEY]->(AgentKey)`, `(Agent)-[:HAS_CAPABILITY]->(Capability)`, `(Task)-[:DEPENDS_ON]->(Task)`, `(Agent)-[:LEARNED]->(LearnedCapability)`

---

## Steppe Visualization

3D dashboard built with Next.js + Three.js showing agents as camps on a steppe terrain.

- **Main view** (`/`): 3D visualization with agent camps, terrain, rivers, sky
- **Control panel** (`/control-panel`): System health, task board, activity log, memory stats
- **Mission control** (`/mission-control`): Goal orchestration panel

Tech: Next.js 16, React 19, Three.js, @react-three/fiber, Zustand, Framer Motion, shadcn/ui

---

## Security

- **Authentication**: Authentik SSO with WebAuthn (passwordless)
- **Forward Auth**: Caddy proxy validates every request against Authentik
- **Agent Signing**: HMAC-SHA256 message signatures between agents
- **PII Sanitization**: 3-layer architecture (regex, LLM review, tokenization)
- **Prompt Injection Filter**: NFKC normalization + 7 pattern categories
- **Cypher Injection Prevention**: Parameterized queries only
- **Cost Enforcement**: Pre-authorization budget control for capability learning
- **Sandbox Execution**: rlimit-based resource limits (CPU 30s, RAM 512MB)
- **Signal Security**: Localhost-only binding, allowlisted senders, E2EE

---

## Documentation

| Document | Description |
|----------|-------------|
| `ARCHITECTURE.md` | Complete system architecture (2200+ lines) |
| `docs/plans/kurultai_0.2.md` | Deployment plan with 12 phases |
| `docs/plans/2026-02-07-two-tier-heartbeat-system.md` | Heartbeat implementation plan |
| `.env.example` | Environment variable reference |

---

## License

Proprietary. Kurultai LLC.
