# Kurultai v0.2 Architecture

**Version**: v0.2
**Date**: 2026-02-07
**Platform**: Railway (container hosting)
**Domain**: `kublai.kurult.ai`
**Owner**: Kurultai LLC

---

## Overview

Kurultai v0.2 is a multi-agent orchestration platform with autonomous capability acquisition, Neo4j-backed operational memory, and Authentik SSO authentication. The system consists of 4 Railway services + PostgreSQL + Neo4j AuraDB, with Signal messaging embedded inside the moltbot gateway via OpenClaw's auto-spawn channel pattern.

> **Note**: Service name `moltbot-railway-template` is the canonical Railway service name (referred to as "moltbot" for brevity throughout this document).

### Key Features

| Feature | Description |
|---------|-------------|
| **Multi-Agent Orchestration** | 6 specialized agents (Kublai, Möngke, Chagatai, Temüjin, Jochi, Ögedei) working collaboratively |
| **Capability Acquisition** | Agents learn new capabilities via `/learn` command using horde-learn 6-phase pipeline |
| **Task Dependency Engine** | DAG-based task batching with topological execution and priority overrides |
| **Neo4j Memory** | Shared graph-based operational memory across all agents |
| **Authentik SSO** | WebAuthn-based single sign-on for web interface |
| **Signal Integration** | End-to-end encrypted messaging via Signal Protocol |
| **Notion Integration** | Bidirectional sync between Notion task databases and Neo4j task graph |
| **File Consistency Monitoring** | Ogedei-driven workspace file monitoring with conflict detection |
| **CBAC** | Capability-Based Access Control for learned skills |
| **Two-Tier Heartbeat** | Infrastructure + functional heartbeat for failover detection (zero cost) |
| **Automated Testing** | Comprehensive test framework with Jochi-powered continuous validation |

### What's New in v0.2

- **Autonomous Learning**: Agents can learn new capabilities through natural language requests
- **HMAC-SHA256 Authentication**: Cryptographic message signing between agents
- **AST-Based Security**: Tree-sitter static analysis for generated code
- **Two-Tier Memory**: Personal (files) + Operational (Neo4j graph)
- **Forward Auth**: Caddy proxy with Authentik integration
- **Prompt Injection Defense**: Pattern-based filtering with NFKC Unicode normalization
- **Task Dependency Engine**: Intent window buffering, DAG building, topological execution
- **Notion Integration**: Bidirectional sync with polling engine and reconciliation
- **File Consistency Monitoring**: Hash-based change detection across agent workspaces
- **Neo4j Fallback Mode**: Circuit breaker with in-memory fallback store and automatic recovery
- **Two-Tier Heartbeat**: Infrastructure sidecar (30s writes) + functional heartbeat (on task claim/complete) for reliable failover detection

### Scope

This document covers **Core Infrastructure + Foundation Features**: Neo4j-backed operational memory, SSO authentication, Signal messaging, capability acquisition pipeline, Task Dependency Engine, Notion Integration, File Consistency Monitoring, and operational monitoring. Features deferred to v0.3 are documented in [Scope Boundary](#scope-boundary--deferred-to-v03).

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Railway Deployment                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────┐    ┌────────────────┐    ┌────────────────┐            │
│  │   Authentik    │    │   Authentik    │    │  Authentik     │            │
│  │    Server      │    │    Worker      │    │  Proxy (Caddy) │            │
│  │  :9000 (int)   │    │  (background)  │    │   :8080 (pub)  │            │
│  └────────┬───────┘    └────────────────┘    └────────┬───────┘            │
│           │                                        │                       │
│           └────────────────────────────────────────┼───────────────────────┘
│                                                    │ forward_auth
│  ┌─────────────────────────────────────┐           │                       │
│  │  Moltbot (moltbot-railway-template) │           │                       │
│  │  ┌─────────────┐  ┌──────────────┐ │           │                       │
│  │  │  Node.js    │  │  signal-cli   │ │           │                       │
│  │  │  Gateway    │  │  (embedded)   │ │           │                       │
│  │  │  :8080 (int)│  │  :8081 (lo)   │ │           │                       │
│  │  └──────┬──────┘  └──────┬───────┘ │           │                       │
│  │         │     spawns ▲    │          │           │                       │
│  │         └─────────────────┘          │           │                       │
│  │  ┌──────────────────────────────┐   │           │                       │
│  │  │  Heartbeat Sidecar (Python)  │   │           │                       │
│  │  │  writes Agent.infra_heartbeat│   │           │                       │
│  │  │  every 30s to Neo4j          │   │           │                       │
│  │  └──────────────────────────────┘   │           │                       │
│  │                                      │◀──── Neo4j AuraDB (neo4j+s://)   │
│  └──────────────┬──────────────────────┘           │                       │
│                 │                                    │                       │
│                 │   ┌────────────────┐               │                       │
│                 └──▶│  Kublai Web UI │◀──────────────┘                       │
│                     │  (Next.js)      │  Authenticated requests               │
│                     │  /dashboard     │                                       │
│                     └────────────────┘                                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

External DNS: kublai.kurult.ai → authentik-proxy.railway.app
Total Services: 4 Railway services + PostgreSQL + Neo4j AuraDB
Railway Services: authentik-server, authentik-worker, authentik-proxy, moltbot-railway-template
External Dependency: Neo4j AuraDB (neo4j+s://)

Signal Architecture: signal-cli runs INSIDE moltbot as a child process (OpenClaw auto-spawn
pattern). The Node.js gateway spawns signal-cli on 127.0.0.1:8081 at startup. No separate
signal-cli-daemon or signal-proxy Railway services are needed.
```

---

## Deployment Phases

The v0.2 deployment follows a phased approach (detailed in `docs/plans/kurultai_0.2.md`):

| Phase | Name | Description |
|-------|------|-------------|
| Phase -1 | Wipe and Rebuild | Clean slate teardown of previous deployment |
| Phase 0 | Environment & Security Setup | Credentials, env vars, security controls |
| Phase 1 | Neo4j & Foundation | AuraDB setup, migrations v1/v2/v3, agent keys |
| **Phase 1.5** | **Task Dependency Engine** | Intent window buffering, DAG builder, topological executor |
| Phase 2 | Capability Acquisition System | 6-phase horde-learn pipeline, CBAC |
| Phase 3 | Railway Deployment | Dockerfiles, service creation, container deployment |
| Phase 4 | Signal Integration | Embedded signal-cli in moltbot, device linking, allowlists |
| **Phase 4.5** | **Notion Integration** | Bidirectional sync, polling engine, reconciliation |
| Phase 5 | Authentik Web App Integration | SSO, WebAuthn, forward auth proxy |
| Phase 6 | Monitoring & Health Checks | Structured logging, health endpoints, log rotation |
| **Phase 6.5** | **File Consistency Monitoring** | Ogedei file monitor, conflict detection, resolution |
| Phase 7 | Testing & Validation | End-to-end tests, schema validation, load testing (depends on Phase 6.5) |

**Appendices**: A (Environment Variables), B (Railway Service Config), C (Troubleshooting), D (Rollback Procedures), E (Security Infrastructure Reference), F (Fallback Mode Procedures), G (Scope Boundary Declaration), H (Complexity Scoring & Team Sizing System - see kurultai_0.2.md)

---

## Railway Project Structure

### Project Details

| Property | Value |
|----------|-------|
| Project Name | `kurultai` |
| Project ID | `26201f75-3375-46ce-98c7-9d1dde5f9569` |
| Environment | `production` |
| Region | US East (default) |

### Services

#### 1. authentik-server

| Property | Value |
|----------|-------|
| Image | `ghcr.io/goauthentik/server:2025.10.0` |
| Port (Internal) | 9000 |
| Purpose | SSO identity provider and admin UI |
| Dependencies | PostgreSQL (Railway internal) |

#### 2. authentik-worker

| Property | Value |
|----------|-------|
| Image | `ghcr.io/goauthentik/server:2025.10.0` |
| Purpose | Background task processing for Authentik |
| Dependencies | PostgreSQL, authentik-server |

#### 3. authentik-proxy

| Property | Value |
|----------|-------|
| Image | Caddy 2 Alpine with custom Caddyfile |
| Port (External) | 8080 |
| Custom Domain | `kublai.kurult.ai` |
| Purpose | Forward auth proxy with bypass routes |

#### 4. moltbot-railway-template

| Property | Value |
|----------|-------|
| Base Image | Node 20 slim + Java 17 JRE + signal-cli v0.13.12 |
| Port (Internal) | 8080 (Express gateway), 8081 (signal-cli, localhost only) |
| Volume | `/data` (persistent) |
| Purpose | Main application gateway with embedded Signal integration |
| Dependencies | Neo4j AuraDB |
| Signal Integration | Embedded via OpenClaw auto-spawn pattern (child process) |

> **Deprecated services**: `signal-cli-daemon/` and `signal-proxy/` directories exist in the repo
> from an earlier architecture iteration but are **not deployed** in v0.2. Signal runs inside
> moltbot as a child process per the OpenClaw channel specification.

### Railway Service Configuration Matrix

| Service | Build | Health Check | Public Domain | Internal URL |
|---------|-------|--------------|---------------|--------------|
| authentik-server | Dockerfile | `/-/health/ready/` | No | `authentik-server.railway.internal:9000` |
| authentik-worker | Dockerfile | None | No | N/A |
| authentik-proxy | Dockerfile | `/health` | Yes (`kublai.kurult.ai`) | `authentik-proxy.railway.internal:8080` |
| moltbot-railway-template | Dockerfile | `/health` | Via proxy | `moltbot-railway-template.railway.internal:8080` |

> **Port Note**: The OpenClaw internal gateway listens on port 18789 (configured in moltbot.json
> gateway.port). The Express.js health check server runs on port 8080 (Railway's expected port).
> The Caddy proxy (authentik-proxy) handles external HTTPS on port 443/8080.

---

## Agent Architecture

### 6 Specialized Agents

| Agent ID | Name | Specialization | Primary Capabilities |
|----------|------|----------------|---------------------|
| `main` | **Kublai** | Orchestration, user interface | Delegation, personal memory, PII sanitization |
| `researcher` | **Möngke** | Research, documentation | Web search, API research, knowledge synthesis |
| `writer` | **Chagatai** | Content creation | Documentation, reports, communication |
| `developer` | **Temüjin** | Software development | Code generation, implementation, testing |
| `analyst` | **Jochi** | Code analysis, security | AST parsing, security audit, backend monitoring |
| `ops` | **Ögedei** | Operations / Emergency Router / File Consistency Manager / Project Manager | Infrastructure, monitoring, maintenance, heartbeat-based failover. Activates as emergency router when Kublai fails 3 consecutive health checks. Monitors `Agent.infra_heartbeat` and `Agent.last_heartbeat` for two-tier failover detection. |

> **Model Configuration**: All agents use the primary model specified in `moltbot.json` under `agents.defaults.model.primary`. Currently configured to use `zai/glm-4.5`. Individual agent model overrides can be specified in the `agents.list` array. See [moltbot.json Configuration](#moltbotjson) for details.

### Agent Communication Flow

```
User Request
     ↓
┌────────────┐
│   Caddy    │ → Authentik Forward Auth (if unauthenticated → login)
│   Proxy    │
└─────┬──────┘
      │
      ↓
┌────────────┐
│  Moltbot   │ → Express.js server
│  :8080     │
└─────┬──────┘
      │
      ↓
┌──────────────────────────────────────────────────────────┐
│                     Kublai (main)                       │
│  ├─ Reads personal context (files)                     │
│  ├─ Queries operational context (Neo4j)                │
│  ├─ Sanitizes PII via PIISanitizer                     │
│  └─ Delegates via agentToAgent with HMAC signature     │
└────────┬────────────────────────────────────────────────┘
         │
    ┌────┼────────┬────────┬────────┬────────┐
    ↓    ↓        ↓        ↓        ↓        ↓
  Möngke Chagatai Temüjin  Jochi   Ögedei
  (research) (write)  (dev)  (analyze) (ops)
    │      │       │      │       │
    └──────┴───────┴──────┴───────┘
         │
         ↓ Results to Neo4j (shared operational memory)
         │
    Kublai synthesizes response
         │
         ↓ Response to user
```

### Agent Authentication (HMAC-SHA256)

Each agent has a signing key stored in Neo4j as an `AgentKey` node. Messages between agents are signed using HMAC-SHA256 to prevent impersonation.

> **Note**: HMAC-SHA256 signing keys are pre-generated and stored in Neo4j (Phase 1 Task 1.4). The actual HMAC signing and verification middleware implementation is deferred to v0.3 (inter-agent collaboration protocols). Current authentication relies on RBAC-based authorization.

**Protocol** (v0.3):
1. Sender retrieves active key from Neo4j: `MATCH (a:Agent {id: $agent_id})-[:HAS_KEY]->(k:AgentKey {is_active: true})`
2. Sender generates signature: `HMAC-SHA256(key_hash, message_content + timestamp + nonce)`
3. Sender includes signature in message header: `X-Agent-Signature`
4. Receiver validates signature and timestamp (max 300s drift)
5. Receiver checks nonce uniqueness to prevent replay attacks

**Key Rotation**:
- Keys expire after 90 days
- New keys generated automatically before expiration
- Old keys retained for 7 days for message validation
- Rotation triggered by `tools/kurultai/agent_auth.py`
- Key material generated via `secrets.token_hex(32)` (Python application layer, not Cypher sha256)

---

## Two-Tier Memory Architecture

### Personal Tier (Files)

**Storage**: Local files in `/data/workspace/souls/{agent_id}/MEMORY.md`
**Access**: Kublai only (not shared with other agents)
**Contents**: User preferences, personal history, PII

**Example**:
```markdown
# Personal Context
- User's friend Sarah works at Google
- User prefers Python over JavaScript
- User's birthday: January 15
```

**Privacy Rule**: Kublai sanitizes PII via `PIISanitizer` before delegating to other agents.

### Operational Tier (Neo4j)

**Storage**: Neo4j AuraDB (graph database)
**Access**: All 6 agents (shared operational memory)
**Contents**: Research findings, code patterns, analysis results, learned capabilities

**Example Nodes**:
- `:Research` - Research findings from Möngke
- `:CodePattern` - Reusable code patterns from Temüjin
- `:Analysis` - Security findings from Jochi
- `:LearnedCapability` - Capabilities learned via horde-learn

### Neo4j Schema v0.2

**Core Node Types**:

| Node Label | Properties | Constraints | Purpose |
|------------|-----------|-------------|---------|
| `:Agent` | `id`, `name`, `infra_heartbeat`, `last_heartbeat`, `status` | `UNIQUE(id)` | Agent identity and heartbeat tracking |
| `:AgentKey` | `id`, `key_hash`, `created_at`, `expires_at`, `is_active` | `UNIQUE(id)` | Agent authentication keys |

> **Note on Constraints**: Neo4j uniqueness constraints ensure data integrity across the operational memory graph. Key constraints include: unique `task_id` on Task nodes, unique `session_id` on Session nodes, unique `id` on all core node types (Agent, Research, LearnedCapability, etc.). These constraints prevent duplicate entries and enable efficient lookups. See Migration v3 for complete constraint definitions.
| `:Research` | `id`, `content`, `source`, `timestamp`, `agent`, `research_type`, `capability_name`, `embedding` | `UNIQUE(id)` | Research findings |
| `:CodePattern` | `id`, `pattern`, `language`, `use_case`, `confidence` | `UNIQUE(id)` | Reusable code patterns |
| `:LearnedCapability` | `id`, `name`, `agent`, `tool_path`, `version`, `learned_at`, `cost`, `mastery_score`, `risk_level`, `signature`, `required_capabilities`, `min_trust_level` | `UNIQUE(id)` | Learned capabilities |
| `:Capability` | `id`, `name`, `description` | `UNIQUE(id)` | Capability definitions for CBAC |
| `:Analysis` | `id`, `file_path`, `agent`, `status`, `severity`, `assigned_to`, `findings` | `UNIQUE(id)` | Backend analysis results |
| `:Task` | `id`, `description`, `status`, `priority_weight`, `assigned_to`, `sender_hash`, `embedding`, `window_expires_at` | `UNIQUE(id)` | Task Dependency Engine tasks |
| `:SessionContext` | `id` | `UNIQUE(id)` | Session context tracking |
| `:SignalSession` | `id` | `UNIQUE(id)` | Signal session tracking |
| `:AgentResponseRoute` | `id` | `UNIQUE(id)` | Agent response routing |
| `:Notification` | `id` | `UNIQUE(id)` | Notification management |
| `:Reflection` | `id` | `UNIQUE(id)` | Agent reflection entries |
| `:RateLimit` | `id` | `UNIQUE(id)` | Rate limiting records (1000 requests/hour, 100 requests/batch per sender) |
| `:BackgroundTask` | `id` | `UNIQUE(id)` | Background task tracking |
| `:FileConsistencyReport` | `id`, `severity`, `status` | `UNIQUE(id)` | File consistency scan results |
| `:FileConflict` | `id`, `status`, `severity` | `UNIQUE(id)` | Detected file conflicts |
| `:WorkflowImprovement` | `id` | `UNIQUE(id)` | Workflow improvement records |
| `:Synthesis` | `id` | `UNIQUE(id)` | Synthesis outputs |
| `:Concept` | `id` | `UNIQUE(id)` | Concept definitions |
| `:Content` | `id` | `UNIQUE(id)` | Content items |
| `:Application` | `id` | `UNIQUE(id)` | Application entries |
| `:Insight` | `id` | `UNIQUE(id)` | Insight records |
| `:SecurityAudit` | `id` | `UNIQUE(id)` | Security audit records |
| `:CodeReview` | `id` | `UNIQUE(id)` | Code review records |
| `:ProcessUpdate` | `id` | `UNIQUE(id)` | Process update records |
| `:SyncEvent` | `id`, `sender_hash`, `triggered_at` | `UNIQUE(id)` | Notion sync audit trail |
| `:SyncChange` | `id`, `task_id` | `UNIQUE(id)` | Individual sync change records |

**Key Relationships**:
- `(Agent)-[:HAS_KEY]->(AgentKey)` - Agent owns signing key
- `(Agent)-[:HAS_CAPABILITY {expires_at}]->(Capability)` - CBAC grants
- `(Agent)-[:PERFORMED]->(Research)` - Research attribution
- `(Agent)-[:LEARNED]->(LearnedCapability)` - Capability ownership
- `(Research)-[:CONTRIBUTED_TO]->(LearnedCapability)` - Learning lineage
- `(Task)-[:DEPENDS_ON {type, weight, detected_by, confidence}]->(Task)` - Task dependency DAG

**Indexes**:

```cypher
// Agent lookups
CREATE INDEX agent_id IF NOT EXISTS FOR (a:Agent) ON (a.id);
CREATE INDEX agent_name_idx IF NOT EXISTS FOR (a:Agent) ON (a.name);
CREATE INDEX agent_infra_heartbeat_idx IF NOT EXISTS FOR (a:Agent) ON (a.infra_heartbeat);
CREATE INDEX agent_last_heartbeat_idx IF NOT EXISTS FOR (a:Agent) ON (a.last_heartbeat);

// Research lookups
CREATE INDEX research_agent IF NOT EXISTS FOR (r:Research) ON (r.agent);
CREATE INDEX capability_research_lookup IF NOT EXISTS
  FOR (r:Research) ON (r.capability_name, r.agent);

// Vector search for semantic research (384-dim cosine)
CREATE VECTOR INDEX capability_research_embedding IF NOT EXISTS
  FOR (r:Research) ON r.embedding
  OPTIONS {indexConfig: {
    `vector.dimensions`: 384,
    `vector.similarity_function`: 'cosine'
  }};

// Analysis lookups
CREATE INDEX analysis_agent_status IF NOT EXISTS
  FOR (a:Analysis) ON (a.agent, a.status, a.severity);
CREATE INDEX analysis_assigned_lookup IF NOT EXISTS
  FOR (a:Analysis) ON (a.assigned_to, a.status);

// CBAC capability lookups
CREATE INDEX capability_grants IF NOT EXISTS
  FOR ()-[r:HAS_CAPABILITY]->() ON (r.expires_at);

// Task Dependency Engine indexes (critical for race prevention and DAG traversal)
CREATE INDEX task_claim_lock IF NOT EXISTS FOR (t:Task) ON (t.status, t.assigned_to);
CREATE VECTOR INDEX task_embedding IF NOT EXISTS
  FOR (t:Task) ON t.embedding
  OPTIONS {indexConfig: {
    `vector.dimensions`: 384,
    `vector.similarity_function`: 'cosine'
  }};
CREATE INDEX task_window IF NOT EXISTS FOR (t:Task) ON (t.window_expires_at);
CREATE INDEX task_sender_status IF NOT EXISTS FOR (t:Task) ON (t.sender_hash, t.status);
CREATE INDEX task_agent_status IF NOT EXISTS FOR (t:Task) ON (t.assigned_to, t.status);
CREATE INDEX depends_on_type IF NOT EXISTS FOR ()-[d:DEPENDS_ON]->() ON (d.type);
CREATE INDEX task_priority IF NOT EXISTS FOR (t:Task) ON (t.priority_weight, t.created_at);

// Notion sync audit trail indexes
CREATE INDEX sync_event_sender IF NOT EXISTS FOR (s:SyncEvent) ON (s.sender_hash, s.triggered_at);
CREATE INDEX sync_change_task IF NOT EXISTS FOR (c:SyncChange) ON (c.task_id);

// File consistency monitoring indexes
CREATE INDEX file_report_severity IF NOT EXISTS FOR (r:FileConsistencyReport) ON (r.severity, r.status);
CREATE INDEX file_conflict_status IF NOT EXISTS FOR (fc:FileConflict) ON (fc.status, fc.severity);
```

### Migrations

**Migration v1**: Initial schema (Agent, Research, CodePattern nodes)
**Migration v2**: Kurultai dependencies (Task, Dependency relationships, indexes)
**Migration v3** (v0.2): Capability acquisition extensions (class `V3CapabilityAcquisition`)

The V3 migration class (`migrations/v3_capability_acquisition.py`) includes:
- Research node extension for capability learning (`research_type` field)
- Capability research indexes (composite + vector 384-dim cosine)
- Core capability constraints (LearnedCapability, Capability, AgentKey)
- Analysis nodes and indexes for Jochi
- 18 additional node type constraints (SessionContext, SignalSession, AgentResponseRoute, Notification, Reflection, RateLimit, BackgroundTask, FileConsistencyReport, FileConflict, WorkflowImprovement, Synthesis, Concept, Content, Application, Insight, SecurityAudit, CodeReview, ProcessUpdate)
- 11 critical indexes (task_claim_lock, task_embedding vector, task_window, task_sender_status, task_agent_status, depends_on_type, task_priority, sync_event_sender, sync_change_task, file_report_severity, file_conflict_status)
- Complete `DOWN_CYPHER` for full rollback of all constraints and indexes

**Running Migrations**:

```bash
# Run all migrations (V1 initial schema, V2 kurultai dependencies, V3 capability acquisition)
python scripts/run_migrations.py --target-version 3
```

---

## Capability Acquisition System

### 6-Phase Pipeline

The horde-learn capability acquisition system enables agents to learn new capabilities through natural language requests (e.g., `/learn how to call phones`).

| Phase | Agent | Purpose | Output |
|-------|-------|---------|--------|
| **1. Classification** | Kublai | Classify capability type and risk | `{type, risk_level, estimated_cost}` |
| **2. Research** | Möngke | Find documentation and examples | Research nodes in Neo4j |
| **3. Implementation** | Temüjin | Generate code and tests | Python module + tests |
| **4. Validation** | Jochi | Security audit + AST analysis | Pass/fail + findings |
| **5. Registration** | Kublai | Store capability in Neo4j | LearnedCapability node |
| **6. Authorization** | Kublai | Setup CBAC grants | HAS_CAPABILITY relationships |

**Example Flow**:

```
User: "/learn how to send SMS messages"
  ↓
Kublai: Classifies as "external_api", risk_level="medium", cost=$2
  ↓
Möngke: Researches Twilio API, creates Research nodes
  ↓
Temüjin: Generates tools/twilio_client.py with send_sms()
  ↓
Jochi: AST analysis passes, no eval/exec/SQL injection detected
  ↓
Kublai: Creates LearnedCapability node, grants HAS_CAPABILITY
  ↓
User: "Send SMS to +1234567890: Hello"
```

### Security Controls (5 Controls)

The 5 security controls form a layered defense across the capability acquisition pipeline:

| # | Control | Integration Point | Module |
|---|---------|-------------------|--------|
| 1 | PromptInjectionFilter | Phase 0 (security pre-check) | `tools/kurultai/security/prompt_injection_filter.py` |
| 2 | CostEnforcer | Before Phase 2 (Research) | `tools/kurultai/security/cost_enforcer.py` |
| 3 | SandboxExecutor | Phase 4 (Validation) | `tools/kurultai/sandbox_executor.py` |
| 4 | CostEnforcer (release) | Post-pipeline | `tools/kurultai/security/cost_enforcer.py` |
| 5 | Jochi AST Analyzer | Phase 4 (Validation) + ongoing monitoring | `tools/kurultai/static_analysis/ast_parser.py` |

#### 1. PromptInjectionFilter

**Purpose**: Detect and block prompt injection patterns in capability requests

**File**: `tools/kurultai/security/prompt_injection_filter.py`

**NFKC Normalization**: Applied before pattern matching to normalize Unicode homoglyphs (e.g., fullwidth characters, Cyrillic lookalikes) to their ASCII equivalents, preventing bypass via Unicode substitution.

**Patterns** (7+ injection patterns):

| # | Pattern | Catches |
|---|---------|---------|
| 1 | `ignore (all )?(previous\|above) instructions` | Classic instruction override |
| 2 | `disregard (all )?(previous\|above) instructions` | Synonym variant |
| 3 | `(forget\|clear\|reset) (all )?(instructions\|context\|prompts)` | Context clearing |
| 4 | `you are now (a\|an) .{0,50} (model\|assistant\|ai)` | Role hijacking |
| 5 | `act as (a\|an) .{0,100}` | Role assumption |
| 6 | `pretend (you are\|to be) .{0,100}` | Pretend injection |
| 7 | `override (your )?(programming\|safety\|constraints)` | Safety bypass |

**Note**: This filter operates at the capability acquisition boundary. For Cypher query injection prevention, see `tools/security/injection_prevention.py` (CypherInjectionPrevention and SecureQueryBuilder).

**Integration**: Applied in Phase 0 (before classification) of horde-learn pipeline.

#### 2. CostEnforcer

**Purpose**: Pre-authorization pattern for capability learning budget control

**File**: `tools/kurultai/security/cost_enforcer.py`

**Pre-Authorization Flow**:

```
1. Kublai initiates /learn -> CostEnforcer.authorize_spending(skill_id, estimated_cost)
2. Neo4j atomically checks remaining >= estimated_cost
3. If sufficient: remaining -= estimated_cost, reserved += estimated_cost
4. Pipeline phases execute (Research -> Implementation -> Validation)
5. On completion: reserved -= actual_cost, spent += actual_cost
6. Surplus returned: remaining += (estimated_cost - actual_cost)
7. On failure: reserved -= estimated_cost, remaining += estimated_cost
```

**Integration**: Applied before Phase 2 (Research) to prevent runaway costs.

#### 3. SandboxExecutor

**Purpose**: Subprocess-based sandbox for generated code (Railway-compatible, no Docker required)

**File**: `tools/kurultai/sandbox_executor.py`

**Resource Limits**:

| Resource | Limit | Constant | Purpose |
|----------|-------|----------|---------|
| CPU Time | 30 seconds | `RLIMIT_CPU` | Prevent infinite loops |
| Address Space | 512 MB | `RLIMIT_AS` | Prevent memory exhaustion |
| File Descriptors | 100 | `RLIMIT_NOFILE` | Prevent file handle exhaustion |

**Railway Compatibility Notes**:
- The `resource` module works on Linux containers (Railway's runtime environment)
- `RLIMIT_AS` is enforced at the kernel level on Linux, providing hard memory limits
- Railway containers run as non-root by default; resource limits do not require elevated privileges

**macOS Local Development**: `RLIMIT_AS` is not supported on macOS (Darwin kernel ignores it). Use platform detection to skip on macOS.

**Integration**: Applied in Phase 4 (validation) to test generated code safely.

#### 4. Jochi AST Analyzer

**Purpose**: Tree-sitter based static analysis for security issues in generated code

**File**: `tools/kurultai/static_analysis/ast_parser.py`

**Detection Categories**:

| Category | Patterns | Severity |
|----------|----------|----------|
| Code Execution | `eval()`, `exec()`, `compile()` | high |
| SQL Injection | String concatenation in SQL queries | high |
| Hardcoded Secrets | String literals matching API key patterns | critical |
| Command Injection | `os.system()`, `subprocess` with `shell=True` | critical |

**Deployment Dependency**: `tree-sitter` and `tree-sitter-python` packages (installed via `/opt/venv/bin/pip`).

**Integration**: Applied in Phase 4 (validation) before capability registration, and in Jochi's ongoing backend monitoring.

### CBAC (Capability-Based Access Control)

**Purpose**: Fine-grained access control for learned capabilities based on required capabilities and trust levels.

**Schema**:
```cypher
// Grant capability to agent
CREATE (a:Agent {id: 'developer'})-[:HAS_CAPABILITY {
  granted_at: datetime(),
  expires_at: datetime() + duration('P90D'),
  granted_by: 'main'
}]->(c:Capability {id: 'execute_code'})

// Check authorization
MATCH (a:Agent {id: $agent_id})
MATCH (lc:LearnedCapability {id: $capability_id})
WITH a, lc, lc.required_capabilities as req_caps
WHERE ALL(cap IN req_caps WHERE
  EXISTS { (a)-[r:HAS_CAPABILITY]->(:Capability {id: cap}) WHERE r.expires_at IS NULL }
  OR EXISTS { (a)-[r:HAS_CAPABILITY]->(:Capability {id: cap}) WHERE r.expires_at > datetime() }
)
RETURN count(*) > 0 as can_execute
```

**Trust Levels**:
- `level_0`: No capabilities (default for new agents)
- `level_1`: Basic capabilities (read-only operations)
- `level_2`: Standard capabilities (API calls, file operations)
- `level_3`: Elevated capabilities (code execution, database writes)
- `level_4`: Administrative capabilities (system configuration)

---

## Task Dependency Engine

The Task Dependency Engine enables Kublai to intelligently batch, prioritize, and execute multiple user requests as a unified dependency graph. Rather than processing messages FIFO, Kublai builds a Directed Acyclic Graph (DAG) of tasks and executes them in topological order, maximizing parallel execution while respecting dependencies.

### Components

| Component | File | Purpose |
|-----------|------|---------|
| **IntentWindowBuffer** | `tools/kurultai/intent_buffer.py` | Collects rapid-fire messages within a configurable window (default 45s) before DAG analysis |
| **DAGBuilder** | `tools/kurultai/dependency_analyzer.py` | Detects dependencies between tasks via semantic similarity and creates `DEPENDS_ON` relationships |
| **TopologicalExecutor** | `tools/kurultai/topological_executor.py` | Dispatches independent task batches in parallel, respecting dependency order |
| **PriorityCommandHandler** | `tools/kurultai/priority_override.py` | User override commands to modify execution order in real time |

### DEPENDS_ON Relationship Schema

```cypher
(:Task)-[:DEPENDS_ON {
  type: string,           // "blocks" | "feeds_into" | "parallel_ok"
  weight: float,          // 0.0-1.0 strength of dependency
  detected_by: string,    // "semantic" | "explicit" | "inferred"
  confidence: float,      // 0.0-1.0 detection confidence
  created_at: datetime
}]->(:Task)
```

### Task Status Flow

```
PENDING -> READY -> RUNNING -> COMPLETED
                         \-> FAILED -> ESCALATED
```

### Agent Routing Map

| Deliverable Type | Agent | Name |
|------------------|-------|------|
| `research` | `researcher` | Mongke |
| `analysis` | `analyst` | Jochi |
| `code` | `developer` | Temujin |
| `content` | `writer` | Chagatai |
| `ops` | `ops` | Ogedei |
| `strategy` | `analyst` | Jochi |
| `testing` | `developer` | Temujin |

### Priority Override Commands

| Command Pattern | Effect |
|-----------------|--------|
| `Priority: <target> first` | Sets task priority_weight = 1.0 |
| `Do <X> before <Y>` | Creates explicit BLOCKS edge: X -> Y |
| `These are independent` | Creates PARALLEL_OK edges |
| `Focus on <X>, pause others` | Pauses non-X tasks, boosts X |
| `What's the plan?` | Explains current DAG state |

### Cycle Detection

The `TopologicalExecutor.add_dependency()` method uses an atomic Cypher query with `WHERE NOT EXISTS { MATCH path = (dep)-[:DEPENDS_ON*]->(task) }` to prevent cycles at creation time (single-query TOCTOU-safe approach).

---

## Notion Integration

Notion integration provides bidirectional sync between Notion task databases and the Neo4j task graph. Users manage task priorities and status in Notion's UI, and changes flow automatically into the Kurultai execution engine.

### Sync Modes

| Mode | Trigger | Direction |
|------|---------|-----------|
| **Command-based** | User sends "Sync from Notion" | Notion -> Neo4j |
| **Continuous polling** | Ogedei polls at configurable interval (default 60s) | Notion -> Neo4j |
| **Bidirectional** | Neo4j task completions | Neo4j -> Notion |

### Components

| Component | File | Purpose |
|-----------|------|---------|
| **NotionTaskClient** | `tools/notion_sync.py` / `tools/kurultai/notion_client.py` | API client with retry and backoff |
| **NotionSyncHandler** | `tools/kurultai/notion_sync_handler.py` | Bidirectional sync, extends PriorityCommandHandler |
| **NotionPollingEngine** | `tools/kurultai/notion_polling.py` | Ogedei continuous polling via `last_edited_time` |
| **ReconciliationEngine** | `tools/kurultai/reconciliation.py` | Safe merge of Notion changes with Neo4j state |

### Field Mapping

| Notion Property | Type | Neo4j Task Property | Direction |
|-----------------|------|---------------------|-----------|
| `Name` | Title | `description` | Bidirectional |
| `Status` | Select | `status` | Bidirectional |
| `Priority` | Select | `priority_weight` | Notion -> Neo4j |
| `Agent` | Select | `assigned_to` | Notion -> Neo4j |
| `ID` | Text | `id` | Read-only |
| `Last Synced` | Date | `notion_synced_at` | Neo4j -> Notion |

### Reconciliation Safety Rules

| Rule | Condition | Action |
|------|-----------|--------|
| Rule 1 | Task is `in_progress` | Skip all Notion changes except priority |
| Rule 2 | Task is `completed` | Skip all Notion changes |
| Rule 3 | BLOCKS dependency unmet | Don't enable dependent task |
| Rule 4 | Priority change | Always apply (safe at any time) |

### Audit Trail

Sync operations create `SyncEvent` and `SyncChange` nodes in Neo4j for full audit trail of all Notion-driven changes.

---

## File Consistency Monitoring

The Ogedei File Consistency & Conflict Detection system monitors workspace-level files across all six agent directories, detecting contradictions, stale data, and parse errors in shared memory files.

### Components

| Component | File | Purpose |
|-----------|------|---------|
| **FileConsistencyChecker** | `tools/kurultai/file_consistency.py` | Hash-based change detection and cross-file comparison |
| **OgedeiFileMonitor** | `tools/kurultai/ogedei_file_monitor.py` | Periodic scan runner (default 5-minute interval) |

### Monitored Files

- `heartbeat.md`, `memory.md`, `CLAUDE.md` across all agent directories

### Agent Directories (Railway container paths)

- `/data/.clawdbot/agents/main`
- `/data/.clawdbot/agents/researcher`
- `/data/.clawdbot/agents/writer`
- `/data/.clawdbot/agents/developer`
- `/data/.clawdbot/agents/analyst`
- `/data/.clawdbot/agents/ops`

### Conflict Resolution

| Conflict Type | Resolution |
|---------------|------------|
| **Stale data** | Auto-resolved by flagging the older file for refresh |
| **Parse errors** | Cannot auto-resolve; queued for manual review |
| **Contradictions** | Queued for manual resolution by Kublai |

Manual resolution creates `FileConflict` nodes with `status='open'` and audit trail, escalated to Kublai via Analysis nodes.

### Health Endpoint

`GET /health/file-consistency` returns monitor status (healthy/degraded based on `monitor_running` and `last_severity`).

---

## Skill Synchronization System

### Overview
Automatic synchronization of skill definitions from kurultai-skills GitHub repository to kublai gateway with zero downtime.

### Architecture Diagram

```
+-------------------------------------------------------------------------+
|                         Skill Sync Architecture                         |
+-------------------------------------------------------------------------+
|                                                                         |
|   GitHub Repository (kurultai-skills)                                  |
|         |                                                               |
|         +--- Webhook (push event) ----+                                |
|         |                              |                                |
|         +--- Polling (every 5 min) ---+                                |
|                                          v                             |
|   +-------------------------------------------------------+            |
|   |      skill-sync-service (Railway Worker)             |            |
|   |  +-------------------------------------------------+  |            |
|   |  | Webhook Handler (HMAC verification,             |  |            |
|   |  |   rate limiting, timestamp validation)          |  |            |
|   |  +-------------------------------------------------+  |            |
|   |  +-------------------------------------------------+  |            |
|   |  | Skill Validator (YAML frontmatter, security    |  |            |
|   |  |   scan, required fields check)                 |  |            |
|   |  +-------------------------------------------------+  |            |
|   |  +-------------------------------------------------+  |            |
|   |  | Skill Deployer (atomic write, rollback,         |  |            |
|   |  |   backup to /data/backups/skills/)             |  |            |
|   |  +-------------------------------------------------+  |            |
|   |  +-------------------------------------------------+  |            |
|   |  | Audit Logger (Neo4j deployment tracking)        |  |            |
|   |  +-------------------------------------------------+  |            |
|   +-------------------------------------------------------+            |
|                                          |                             |
|                                          v                             |
|   +-------------------------------------------------------+            |
|   |        Shared Volume: clawdbot-data                       |            |
|   |  /data/skills/ (mounted on both services)              |            |
|   +-------------------------------------------------------+            |
|                                          |                             |
|                                          v                             |
|   +-------------------------------------------------------+            |
|   |         moltbot (OpenClaw Gateway)                     |            |
|   |  +-------------------------------------------------+  |            |
|   |  | Skill Watcher (chokidar file watching)          |  |            |
|   |  |  - Detects: add, change, unlink events           |  |            |
|   |  |  - Latency: 2-5 seconds                          |  |            |
|   |  |  - Triggers: hot-reload without restart         |  |            |
|   |  +-------------------------------------------------+  |            |
|   |  +-------------------------------------------------+  |            |
|   |  | Agent Registry (in-memory skill cache)           |  |            |
|   |  +-------------------------------------------------+  |            |
|   +-------------------------------------------------------+            |
|                                                                         |
|   Result: Skills updated WITHOUT disrupting active agents                |
|                                                                         |
+-------------------------------------------------------------------------+
```

### Data Flow

1. **Webhook Path** (Primary): GitHub push -> skill-sync-service -> /data/skills/ -> chokidar -> hot-reload
2. **Polling Path** (Fallback): Every 5 minutes -> GitHub API -> skill-sync-service -> /data/skills/
3. **Reload Path**: File change detected -> skill registry reload -> new skills available

### Security Measures

- HMAC-SHA256 webhook signature verification
- 5-minute timestamp window for replay protection
- Rate limiting: 10 webhook requests/minute
- API key required for manual sync endpoint
- Path traversal protection on skill filenames
- Secret scanning in skill content (API keys, tokens)

### Services

| Service | Type | Purpose |
|---------|------|---------|
| skill-sync-service | Railway Worker | Receives webhooks, writes skills |
| moltbot | Railway Service | OpenClaw gateway with file watcher |

### Shared Volume Configuration

- **Name:** `clawdbot-data`
- **Mount Path:** `/data` (both services)
- **Skills Directory:** `/data/skills/`
- **Backups:** `/data/backups/skills/<deployment-id>/`

### Monitoring

```bash
# skill-sync-service health
curl https://skill-sync-service-url.railway.app/health

# Check deployed skills
curl https://skill-sync-service-url.railway.app/skills

# Manual sync (requires API key)
curl -X POST -H "x-api-key: $KEY" \
  https://skill-sync-service-url.railway.app/api/sync
```

### Related Documentation

- [Operations Runbook](operations/skill-sync-runbook.md)
- [GitHub Webhook Setup](../github-webhook-setup.md)
- [Hot-Reload Verification](../hot-reload-verification.md)

---

## Two-Tier Heartbeat & Failover

The heartbeat system uses a two-tier model to detect both infrastructure failures (gateway process dead) and functional failures (agent stuck/zombie). The **read side** (Ögedei's failover checks) and **write side** (sidecar + task operations) work together to enable reliable failover detection.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Tier 1: Infrastructure Heartbeat (Sidecar)                      │
│  - Python background process in moltbot container                │
│  - Writes Agent.infra_heartbeat every 30s for all 6 agents       │
│  - Proves: gateway process is alive                              │
│  - Timeout: 120s (4 missed beats) = hard failure                 │
├─────────────────────────────────────────────────────────────────┤
│  Tier 2: Functional Heartbeat (Piggyback)                        │
│  - Updated on claim_task() and complete_task() operations        │
│  - Writes Agent.last_heartbeat as side effect (same transaction) │
│  - Proves: agent is actively working on tasks                    │
│  - Timeout: 90s (3 missed beats) = soft failure                  │
└─────────────────────────────────────────────────────────────────┘
```

### Components

| Component | File | Purpose |
|-----------|------|---------|
| **heartbeat_writer.py** | `moltbot-railway-template/scripts/heartbeat_writer.py` | Infra heartbeat sidecar — writes `Agent.infra_heartbeat` every 30s |
| **entrypoint.sh** | `moltbot-railway-template/entrypoint.sh` | Launches sidecar before OpenClaw gateway |
| **OperationalMemory.claim_task()** | `openclaw_memory.py` | Updates `Agent.last_heartbeat` on task claim (same transaction) |
| **OperationalMemory.complete_task()** | `openclaw_memory.py` | Updates `Agent.last_heartbeat` on task completion (same transaction) |
| **FailoverProtocol** | `src/protocols/failover.py` | Two-tier health check reading both heartbeat properties |
| **FailoverMonitor** | `tools/failover_monitor.py` | Agent availability checks using Agent node heartbeats |
| **DelegationProtocol** | `src/protocols/delegation.py` | Agent routing with 120s heartbeat threshold |

### Heartbeat Sidecar

The sidecar is a standalone Python script launched from `entrypoint.sh` before the OpenClaw gateway. It runs as the `moltbot` user in the background and uses existing Neo4j credentials.

**Key design points:**
- Single batched `UNWIND` Cypher query per cycle (1 transaction for all 6 agents)
- Circuit breaker: 3 consecutive failures → 60s cooldown, then retry
- Graceful shutdown on SIGTERM/SIGINT (1-second sleep granularity)
- Only starts if `NEO4J_PASSWORD` is set and script file exists
- Zero additional cost (no LLM tokens, no new services)

### Threshold Reference

| Component | Property | Threshold | Meaning |
|-----------|----------|-----------|---------|
| Sidecar | `Agent.infra_heartbeat` | writes every 30s | Gateway process alive |
| Agents | `Agent.last_heartbeat` | on claim/complete | Agent functionally working |
| failover.py | infra check | 120s (4 missed) | Hard failure: process dead |
| failover.py | functional check | 90s (3 missed) | Soft failure: agent stuck |
| failover_monitor.py | availability | 90s | Agent available for tasks |
| delegation.py | routing | 120s | Agent eligible for task routing |

### Failover Detection Logic

`FailoverProtocol.check_kublai_health()` reads both heartbeat properties and returns worst-case status:

1. **Infra heartbeat stale >120s** → `status: 'dead'` (gateway process crashed)
2. **Functional heartbeat stale >90s** → `status: 'stuck'` (agent zombie)
3. **Both fresh** → `status: 'healthy'`

> **Note**: The `AgentHeartbeat` node type (used in earlier iterations) has been deprecated in favor of properties directly on the `Agent` node. All heartbeat data now lives on `Agent.infra_heartbeat` and `Agent.last_heartbeat`.

---

## Neo4j Fallback Mode

The `OperationalMemory` module (`openclaw_memory.py`) implements circuit breaker and fallback mode for Neo4j outage handling.

### Circuit Breaker Configuration

| Parameter | Value | Description |
|-----------|-------|-------------|
| `failure_threshold` | 5 | Consecutive failures before circuit opens |
| `recovery_timeout` | 60 seconds | Time before attempting half-open test |
| Half-open behavior | Allow 1 request | On success: close. On failure: reopen |

### Circuit States

```
CLOSED (normal) --[5 failures]--> OPEN (rejecting)
                                      |
                              [60s timeout]
                                      |
                                      v
                                 HALF_OPEN
                                   /     \
                          [success]       [failure]
                             /                \
                            v                  v
                        CLOSED              OPEN
```

### Fallback Behavior

| Operation | Fallback Behavior |
|-----------|-------------------|
| `create_task()` | Task stored in `_local_store['tasks']` (in-memory dict) |
| `claim_task()` | Returns simulated task from local store |
| `complete_task()` | Marked complete in local store |
| `store_research()` | Research stored in `_local_store['research']` |
| `check_rate_limit()` | Always allows (rate limiting disabled) |
| `health_check()` | Returns `status: 'fallback_mode'` |
| `FileConsistencyChecker._store_report()` | Skipped (logs warning) |

**Fallback Store Limits** (prevent memory exhaustion):

| Category | Max Items |
|----------|-----------|
| Tasks | 1,000 |
| Research | 500 |
| Other categories | 1,000 each |

### Automatic Recovery

A background daemon thread (`_start_recovery_monitor`) checks Neo4j connectivity every 30 seconds:

1. Verify Neo4j connectivity via `driver.verify_connectivity()`
2. On success, initiate `_sync_fallback_to_neo4j()`
3. Each item is individually synced; failures are tracked per-item
4. If failure rate < 10%: exit fallback mode, resume normal operations
5. If failure rate >= 10%: remain in fallback mode, retry next cycle

---

## OperationalMemory API

The `OperationalMemory` class (`openclaw_memory.py`) provides the unified interface for all Neo4j interactions across the system. This module handles circuit breaker logic, fallback mode, and all graph database operations.

### Core API Methods

| Method | Purpose | Fallback Behavior |
|--------|---------|-------------------|
| `create_task(description, assigned_to, priority_weight, ...)` | Create new task node | Stores in local memory |
| `claim_task(agent)` | Atomically claim next ready task; updates `Agent.last_heartbeat` as side effect | Returns from local store |
| `complete_task(task_id, result)` | Mark task complete; updates `Agent.last_heartbeat` as side effect | Updates local store |
| `fail_task(task_id, error_message)` | Mark task failed | Updates local store |
| `add_dependency(task_id, depends_on_id, type, weight, ...)` | Create task dependency edge | Not supported in fallback |
| `get_ready_tasks(agent, limit)` | Query tasks ready for execution | Returns from local store |
| `check_rate_limit(sender_hash, window_hours, max_count)` | Enforce rate limiting | Always allows (disabled) |
| `create_reflection(agent, content, reflection_type, ...)` | Store agent reflection | Stores in local memory |
| `create_learning(agent, lesson, confidence, ...)` | Store learned insight | Stores in local memory |
| `create_metarule(agent, rule, category, ...)` | Create workflow rule | Stores in local memory |
| `update_agent_heartbeat(agent, status)` | Explicitly update agent heartbeat timestamp | Returns `False` in fallback mode |
| `health_check()` | Check Neo4j connectivity | Returns `status: 'fallback_mode'` |

### Task Dependency Methods

| Method | Purpose |
|--------|---------|
| `create_task_with_embedding(description, embedding, ...)` | Create task with semantic vector |
| `get_task_dependencies(task_id)` | Retrieve all dependency edges |
| `complete_task_with_dependencies(task_id, result)` | Complete task and update dependents |
| `log_priority_change(task_id, old_priority, new_priority, changed_by)` | Audit priority overrides |
| `get_tasks_by_sender(sender_hash, status)` | Query tasks by sender hash |

### Meta-Learning Methods

| Method | Purpose |
|--------|---------|
| `approve_metarule(rule_id, approved_by)` | Approve workflow rule |
| `apply_metarule(rule_id, outcome_success)` | Track metarule application and outcome |
| `get_metarule_effectiveness(rule_id)` | Calculate metarule success rate |
| `version_metarule(rule_id, new_rule, changed_by)` | Create new version of metarule |
| `get_metarule_history(rule_id)` | Retrieve metarule version history |

### Implementation Details

The `OperationalMemory` class is implemented in `/Users/kurultai/molt/openclaw_memory.py` and serves as the canonical interface for all Neo4j operations. Multiple implementations exist across the codebase for different contexts (e.g., `tools/memory_tools.py`, `memory_manager.py`), but `openclaw_memory.py` is the primary module integrated with the moltbot gateway.

**Key Features**:
- Circuit breaker pattern with automatic recovery
- Fallback to in-memory store during Neo4j outages
- Race condition retry logic with exponential backoff
- Parameterized Cypher queries to prevent injection
- Connection pooling and session management
- Functional heartbeat piggyback on `claim_task()`/`complete_task()` (zero extra Neo4j round-trips)

---

## Authentication & Authorization

### Authentik SSO

**Provider**: Authentik (self-hosted on Railway)
**Authentication Method**: WebAuthn (passwordless with security keys/biometrics)
**Protocol**: OAuth 2.0 / OpenID Connect

**Flow**:
1. User accesses `https://kublai.kurult.ai/dashboard`
2. Caddy proxy forwards request to Authentik for auth check
3. If unauthenticated, redirect to `/if/flow/authentication/`
4. User authenticates via WebAuthn (security key or biometric)
5. Authentik returns session token
6. Caddy forwards request to moltbot with `X-Authentik-*` headers

**WebAuthn Configuration**:
- User verification: `preferred`
- Resident keys: `preferred`
- Timeout: 60 seconds

### Forward Auth Flow

```
┌──────────┐         ┌──────────┐         ┌────────────┐         ┌──────────┐
│  Client  │────────▶│  Caddy   │────────▶│ Authentik  │◀───────│ Moltbot  │
└──────────┘         └──────────┘         └────────────┘         └──────────┘
     1. GET /dashboard       │                    │                     │
                             │                    │                     │
                             2. forward_auth      │                     │
                             ─────────────────────▶                     │
                                                   │                     │
                             ◀─────────────────────                     │
                             3. 401 Unauthorized   │                     │
                             4. Redirect to login  │                     │
     ◀────────────────────────                     │                     │
     5. GET /if/flow/authentication/               │                     │
     ──────────────────────────────────────────────▶                     │
                                                   │                     │
                             ◀─────────────────────                     │
                             6. Login page         │                     │
     ◀────────────────────────                     │                     │
     7. WebAuthn challenge/response                │                     │
     ──────────────────────────────────────────────▶                     │
                                                   │                     │
                             ◀─────────────────────                     │
                             8. Session cookie     │                     │
     ◀────────────────────────                     │                     │
     9. GET /dashboard       │                     │                     │
     ─────────────────────────▶                     │                     │
                             10. forward_auth      │                     │
                             ─────────────────────▶                     │
                                                   │                     │
                             ◀─────────────────────                     │
                             11. 200 + X-Authentik-* headers            │
                             12. proxy_pass ───────────────────────────▶
                                                                         │
                             ◀───────────────────────────────────────────
                             13. Response                                │
     ◀────────────────────────                                           │
```

### Bypass Routes

**Purpose**: Allow specific endpoints to bypass Authentik authentication

**File**: `authentik-proxy/Caddyfile`

| Route | Reason | Authentication |
|-------|--------|----------------|
| `/setup/api/signal-link` | QR code linking for Signal | `X-Signal-Token` header |
| `/ws/*` | WebSocket connections | Session-based |
| `/outpost.goauthentik.io/*` | Authentik outpost API | None (internal) |
| `/application/*` | Authentik application API | Session-based |
| `/flows/*` | Authentik authentication flows | None (public) |
| `/health` | Health check endpoint | None (public) |

**Security Rationale**:
- Signal linking requires token authentication to prevent unauthorized device pairing
- WebSocket connections maintain session state from initial HTTP upgrade
- Authentik internal routes must bypass to avoid auth loops
- Health checks must work for Railway monitoring

### PII Sanitization

**Purpose**: Redact personally identifiable information from logs and delegated messages

**Module**: `tools/security/anonymization.py` (existing `AnonymizationEngine` class)

**PII Detection Coverage**:

| PII Type | Sensitivity |
|----------|-------------|
| Email | high |
| US Phone | high |
| International Phone | high |
| SSN | critical |
| Credit Card | critical |
| API Key | critical |

**Three-Layer Architecture**:
1. **Layer 1** - Regex-based pattern matching (fast, deterministic)
2. **Layer 2** - LLM-based review (comprehensive, for complex cases)
3. **Layer 3** - Tokenization for reversible anonymization

**Integration**:
- Applied in Kublai's `_sanitize_for_sharing()` method before delegating to other agents
- Applied in `src/protocols/delegation.py` before delegation
- Applied in structured logging middleware before writing logs
- Applied in Neo4j writes for Research and Analysis nodes

**Example**:
```python
# Input
"My friend Sarah (sarah@gmail.com, +1234567890) works at Google"

# Output
"My friend Sarah ([REDACTED_EMAIL], [REDACTED_PHONE]) works at Google"
```

---

## Kublai Web UI

**Framework**: Next.js 14+ with App Router
**Location**: `steppe-visualization/`
**Authentication**: Authentik headers via Caddy forward auth
**Served via**: authentik-proxy on `kublai.kurult.ai`

### Protected Routes

| Route Pattern | Purpose |
|---------------|---------|
| `/dashboard/*` | Main control panel |
| `/control-panel/*` | Agent configuration |
| `/api/agent/*` | Agent API endpoints |

### Middleware Integration

**File**: `steppe-visualization/app/middleware.ts`

The Next.js middleware reads `X-Authentik-*` headers set by Caddy forward auth. Unauthenticated requests to protected routes are redirected to `/if/flow/authentication/`.

### Authentication Utilities

**File**: `steppe-visualization/app/lib/auth.ts`

| Function | Purpose |
|----------|---------|
| `getAuthentikUser()` | Reads user context from `/api/auth/me` endpoint |
| `requireAuth()` | Enforces authentication, redirects if needed |

**AuthentikUser interface**: `{ username, email, name, uid, groups[] }`

### Integration Points

- **User info**: Reads from `/api/auth/me` (moltbot backend, see API Endpoints)
- **Agent delegation**: Posts to `/agent/{agent}/message` for task routing
- **Health monitoring**: Polls `/health` for system status display

---

## Signal Integration

### Architecture

Signal runs **inside** the moltbot container as an embedded child process, following the [OpenClaw auto-spawn channel pattern](https://docs.openclaw.ai/channels/signal).

```
┌─────────────────────────────────────────────────┐
│  moltbot-railway-template container              │
│                                                   │
│  ┌─────────────────┐    ┌──────────────────────┐ │
│  │  Node.js Gateway │    │  signal-cli v0.13.12  │ │
│  │  (Express :8080) │───▶│  (child process)      │ │
│  │                   │    │  HTTP daemon :8081     │ │
│  │  - /health        │    │  (localhost only)      │ │
│  │  - /signal/status │    │                        │ │
│  └─────────────────┘    └──────────┬───────────┘ │
│                                      │             │
└──────────────────────────────────────┼─────────────┘
                                       │
                                       ▼
                              Signal Network (E2EE)
```

**Why This Design** (per OpenClaw docs):
- **Auto-spawn mode**: OpenClaw launches and manages signal-cli internally as a child process
- **No separate services needed**: signal-cli binary is installed in the Dockerfile alongside Node.js
- **Localhost-only binding**: signal-cli listens on `127.0.0.1:8081` — no network exposure, no auth layer needed
- **Lifecycle management**: Gateway handles startup, health checks, and graceful shutdown of signal-cli

**Implementation Files**:
- `moltbot-railway-template/Dockerfile` — Installs Java 17 JRE + signal-cli v0.13.12
- `moltbot-railway-template/src/index.js` — Spawns signal-cli as child process, manages lifecycle
- `moltbot-railway-template/src/config/channels.js` — Channel configuration

### How It Works

**Startup sequence** (in `src/index.js`):
1. Gateway calls `startSignalCli()` which spawns `signal-cli daemon --http 127.0.0.1:8081`
2. After 5s startup timeout, runs health check via `signal-cli listAccounts`
3. Sets `signalCliReady = true` when daemon responds
4. Express server starts on `:8080` — reports Signal status in `/health` response

**Graceful shutdown**:
1. SIGTERM received → `stopSignalCli()` sends SIGTERM to child process
2. Waits 5s for graceful exit
3. Force-kills with SIGKILL if still running
4. Closes HTTP server

### Signal Configuration

**File**: `moltbot.json` (channels.signal section)

```json5
{
  "channels": {
    "signal": {
      "enabled": true,
      "account": "+15165643945",
      "cliPath": "/usr/local/bin/signal-cli",   // Embedded binary path
      "autoStart": true,                          // OpenClaw auto-spawn mode
      "startupTimeoutMs": 120000,
      "dmPolicy": "pairing",
      "groupPolicy": "allowlist",
      "configWrites": false,
      "allowFrom": ["+15165643945", "+19194133445"],
      "groupAllowFrom": ["+19194133445"],
      "historyLimit": 50,
      "textChunkLimit": 4000,
      "ignoreStories": true
    }
  }
}
```

> **Note**: The config uses `cliPath` + `autoStart: true` (auto-spawn mode), NOT `httpUrl` + `autoStart: false` (external daemon mode). This means signal-cli runs as a child process inside the container, not as a separate Railway service.

### Signal Security

**v0.2 Security Model**:
- ✅ signal-cli bound to `127.0.0.1:8081` — no network exposure outside the container
- ✅ No authentication layer needed (localhost-only, no external access)
- ✅ Token-protected QR linking endpoint (`/setup/api/signal-link`)
- ✅ Allowlisted senders in moltbot.json (`allowFrom`, `groupAllowFrom`)
- ✅ Signal data stored in `/data/.signal` persistent volume

**QR Linking Flow**:
```bash
# Generate QR code for device linking (requires token)
curl -X POST https://kublai.kurult.ai/setup/api/signal-link \
  -H "Content-Type: application/json" \
  -H "X-Signal-Token: $SIGNAL_LINK_TOKEN" \
  -d '{"phoneNumber": "+15165643945"}'
```

**Linked Account**:
- Phone Number: `+15165643945`
- Protocol: Signal Protocol (E2EE)
- Allowlisted Users: `+15165643945` (self), `+19194133445` (authorized)

**Auto-Start Behavior**: The Signal integration is configured with `autoStart: true` in moltbot.json, meaning signal-cli is spawned as a child process on container boot and begins listening for messages without manual intervention.

### Deprecated Services

The repository contains `signal-cli-daemon/` and `signal-proxy/` directories from a previous architecture iteration that used separate Railway services with a Caddy-based API translation layer. These are **not deployed** in v0.2 and should be considered deprecated:

| Directory | Previous Purpose | Status |
|-----------|-----------------|--------|
| `signal-cli-daemon/` | Standalone signal-cli container | **Deprecated** — signal-cli now embedded in moltbot |
| `signal-proxy/` | Caddy API translation + X-API-Key auth | **Deprecated** — no proxy needed with localhost binding |

---

## API Endpoints

### Health Endpoints

#### GET /health

**Purpose**: Main health check endpoint for Railway
**Authentication**: None (public)

**Response**:
```json
{
  "status": "healthy",
  "timestamp": "2026-02-06T15:30:00.000Z",
  "services": {
    "nodejs": "running",
    "python": "running"
  },
  "dependencies": {
    "neo4j": {
      "connected": true,
      "version": "5.x",
      "nodes": 12345
    },
    "authentik": {
      "connected": true
    }
  }
}
```

#### GET /health/neo4j

**Purpose**: Detailed Neo4j connection status
**Authentication**: None (public)

**Response**:
```json
{
  "status": "healthy",
  "neo4j": {
    "connected": true,
    "uri": "neo4j+s://xxxxx.databases.neo4j.io",
    "database": "neo4j",
    "version": "5.15.0",
    "nodes": 12345,
    "relationships": 45678
  }
}
```

#### GET /health/disk

**Purpose**: Disk space check for `/data` volume
**Authentication**: None (public)

**Response**:
```json
{
  "status": "healthy",
  "disk": {
    "total": "10GB",
    "used": "2.3GB",
    "available": "7.7GB",
    "percent_used": 23
  }
}
```

#### GET /health/file-consistency

**Purpose**: File consistency monitor status (Phase 6.5)
**Authentication**: None (public)

**Response**:
```json
{
  "status": "healthy",
  "file_consistency": {
    "monitor_running": true,
    "last_severity": "low",
    "last_scan": "2026-02-06T15:30:00.000Z"
  }
}
```

### Capability Learning

#### POST /api/learn

**Purpose**: Learn new capability via horde-learn pipeline
**Authentication**: Authentik session or gateway token

**Request**:
```json
{
  "capability": "how to send SMS messages",
  "requesting_agent": "main"
}
```

**Response**:
```json
{
  "status": "learned",
  "capability_id": "cap-a1b2c3d4",
  "name": "send_sms",
  "phases": {
    "classification": "completed",
    "research": "completed",
    "implementation": "completed",
    "validation": "completed",
    "registration": "completed",
    "authorization": "completed"
  },
  "cost": 2.35,
  "time_seconds": 45.2
}
```

### Authentication

#### GET /api/auth/me

**Purpose**: Get current user info from Authentik headers
**Authentication**: Authentik session (X-Authentik-* headers)

**Response**:
```json
{
  "username": "admin",
  "email": "admin@kurult.ai",
  "name": "Administrator",
  "uid": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
  "groups": ["admins", "users"]
}
```

### Agent Messaging

#### POST /agent/{agent}/message

**Purpose**: Send message to specific agent
**Authentication**: Gateway token or Authentik session

**Request**:
```json
{
  "message": "@researcher What is Neo4j?",
  "context": {
    "task_id": "test-123",
    "delegated_by": "main",
    "reply_to": "main"
  }
}
```

**Response**:
```json
{
  "agent": "researcher",
  "response": "Neo4j is a graph database...",
  "signature": "hmac-sha256-signature",
  "timestamp": "2026-02-06T15:30:00.000Z"
}
```

---

## DNS Configuration

### Domain: kublai.kurult.ai

| Record Type | Name | Value | TTL |
|-------------|------|-------|-----|
| CNAME | `kublai` | `authentik-proxy.up.railway.app` | 600 |

**DNS Provider**: Cloudflare
**SSL**: Auto-provisioned by Railway (Let's Encrypt)

**Verification**:
```bash
dig kublai.kurult.ai
# Expected: CNAME to Railway domain
```

---

## Configuration

### moltbot.json

**Location**: `/data/.clawdbot/moltbot.json`

```json5
{
  "gateway": {
    "mode": "local",
    "port": 18789,
    "trustedProxies": ["*"],
    "auth": {
      "mode": "token",
      "token": "${OPENCLAW_GATEWAY_TOKEN}"
    },
    "controlUi": {
      "enabled": true
    }
  },
  "agents": {
    "defaults": {
      "workspace": "/data/workspace",
      "sandbox": {
        "mode": "off"  // Railway has no Docker-in-Docker
      },
      "model": {
        "primary": "zai/glm-4.5"
      }
    },
    "list": [
      { "id": "main", "name": "Kublai", "specialization": "orchestration" },
      { "id": "researcher", "name": "Möngke", "specialization": "research" },
      { "id": "writer", "name": "Chagatai", "specialization": "content" },
      { "id": "developer", "name": "Temüjin", "specialization": "development" },
      { "id": "analyst", "name": "Jochi", "specialization": "analysis" },
      { "id": "ops", "name": "Ögedei", "specialization": "operations" }
    ]
  },
  "channels": {
    "signal": {
      "enabled": true,
      "account": "+15165643945",
      "cliPath": "/usr/local/bin/signal-cli",  // Embedded binary (auto-spawn mode)
      "autoStart": true,                        // OpenClaw manages signal-cli lifecycle
      "startupTimeoutMs": 120000,
      "dmPolicy": "pairing",
      "groupPolicy": "allowlist",
      "configWrites": false,
      "allowFrom": ["+15165643945", "+19194133445"],
      "groupAllowFrom": ["+19194133445"],
      "historyLimit": 50,
      "textChunkLimit": 4000,
      "ignoreStories": true
    }
  },
  "session": {
    "scope": "per-sender",
    "reset": {
      "mode": "daily",
      "graceful": true,
      "drainTimeoutSeconds": 300,
      "maxPendingTasksBeforeForceReset": 10
    },
    "signalRouting": {
      "enabled": true,
      "defaultAgent": "main",
      "sessionIsolation": true,
      "responseRouting": {
        "mode": "sender-matched"
      }
    }
  },
  "logging": {
    "level": "info"
  },
  "browser": {
    "enabled": false
  },
  "tools": {
    "profile": "coding",
    "agentToAgent": {
      "enabled": true,
      "allow": ["main", "researcher", "writer", "developer", "analyst", "ops"]
    }
  }
}
```

### openclaw.json

**Location**: `/data/.clawdbot/openclaw.json`

```json5
{
  "auth": {
    "profiles": {
      "anthropic:default": {
        "mode": "api_key"
      }
    }
  },
  "models": {
    "providers": {
      "anthropic": {
        "api": "anthropic-messages",
        "apiKey": "${ANTHROPIC_API_KEY}",
        "baseUrl": "${ANTHROPIC_BASE_URL}",
        "models": [
          {
            "id": "claude-sonnet-4-20250514",
            "name": "Claude Sonnet 4",
            "reasoning": false,
            "input": ["text"],
            "cost": {
              "input": 0,
              "output": 0,
              "cacheRead": 0,
              "cacheWrite": 0
            }
          }
        ]
      }
    }
  }
}
```

**CRITICAL**: The `models` array is **REQUIRED** for custom provider configurations. Without it, the LLM will not be called.

> **Note**: The current moltbot Dockerfile uses a single-process entrypoint (`node src/index.js`)
> which manages signal-cli as a child process. The supervisord dual-process model (Node.js +
> Python) documented in earlier drafts is **not used** in the current implementation.

### Environment Variables

**Complete v0.2 Environment Variables** (19 core + Notion vars):

| Variable | Scope | Required | Description | Example |
|----------|-------|----------|-------------|---------|
| `NEO4J_URI` | Project | Yes | Neo4j connection URI | `neo4j+s://xxxxx.databases.neo4j.io` |
| `NEO4J_USER` | Project | Yes | Neo4j username | `neo4j` |
| `NEO4J_PASSWORD` | Project | Yes | Neo4j password | `$SECURE_PASSWORD` |
| `NEO4J_DATABASE` | Project | No | Neo4j database name | `neo4j` (default) |
| `ANTHROPIC_API_KEY` | Project | Yes | Anthropic API key | `sk-ant-...` |
| `ANTHROPIC_BASE_URL` | Project | No | Custom API endpoint | `https://api.z.ai/api/anthropic` |
| `AUTHENTIK_SECRET_KEY` | Project | Yes | Authentik signing key | `$(openssl rand -hex 32)` |
| `AUTHENTIK_BOOTSTRAP_PASSWORD` | Project | Yes | Initial admin password | `$(openssl rand -base64 24)` |
| `AUTHENTIK_EXTERNAL_HOST` | Project | Yes | Public URL | `https://kublai.kurult.ai` |
| `AUTHENTIK_POSTGRESQL__HOST` | Service | Yes | PostgreSQL host | `postgres.railway.internal` |
| `AUTHENTIK_POSTGRESQL__NAME` | Service | Yes | PostgreSQL database | `railway` |
| `AUTHENTIK_POSTGRESQL__USER` | Service | Yes | PostgreSQL user | `postgres` |
| `AUTHENTIK_POSTGRESQL__PASSWORD` | Service | Yes | PostgreSQL password | `$POSTGRES_PASSWORD` |
| `SIGNAL_ACCOUNT` | Service | Yes | Signal phone (E.164) | `+15165643945` |
| `SIGNAL_LINK_TOKEN` | Project | Yes | QR linking endpoint auth | `$(openssl rand -hex 32)` |
| `SIGNAL_DATA_DIR` | Service | No | Signal data directory | `/data/.signal` (default) |
| `SIGNAL_CLI_PATH` | Service | No | Path to signal-cli binary | `/usr/local/bin/signal-cli` (default) |
| `OPENCLAW_GATEWAY_TOKEN` | Project | Yes | Gateway authentication | `$(openssl rand -base64 48)` |
| `OPENCLAW_GATEWAY_URL` | Project | Yes | Gateway internal URL | `http://moltbot-railway-template.railway.internal:8080` |
| `KURLTAI_ENABLED` | Service | Yes | Enable Kurultai features | `true` |
| `KURLTAI_MAX_PARALLEL_TASKS` | Service | No | Max parallel tasks | `10` (default) |
| `CLAWDBOT_STATE_DIR` | Service | Yes | State directory | `/data/.clawdbot` |
| `CLAWDBOT_WORKSPACE_DIR` | Service | Yes | Workspace directory | `/data/workspace` |
| `PORT` | Service | Auto | HTTP port (Railway) | `8080` (auto-set) |
| `LOG_LEVEL` | Service | No | Logging level | `info` (default) |
| `NOTION_TOKEN` | Project | Yes* | Notion API integration token | `secret_xxxxx` |
| `NOTION_DATABASE_ID` | Project | Yes* | Notion database for task sync | `(database UUID)` |
| `NOTION_POLL_INTERVAL` | Service | No | Polling interval in seconds | `30` |
| `NOTION_SYNC_ENABLED` | Service | No | Enable Notion sync | `true` |
| `NOTION_LAST_SYNC_CURSOR` | Service | No | Cursor for incremental sync | `(auto-managed)` |
| `SETUP_PASSWORD` | Service | Yes | OpenClaw setup authentication | `$(openssl rand -base64 24)` |
| `PHONE_HASH_SALT` | Project | Yes | HMAC salt for sender phone hashing | `$(openssl rand -hex 32)` |
| `EMBEDDING_ENCRYPTION_KEY` | Project | Yes | AES-256 key for SENSITIVE embedding encryption | `$(openssl rand -base64 32)` |

*Notion vars required only when Notion integration is enabled (`NOTION_SYNC_ENABLED=true`).

**Generate Secure Credentials**:

```bash
# Authentik secret key (32 bytes hex)
openssl rand -hex 32

# Authentik bootstrap password (24 chars base64)
openssl rand -base64 24

# Signal link token (32 bytes hex)
openssl rand -hex 32

# Gateway token (64 chars base64)
openssl rand -base64 48
```

---

## Dockerfiles

### 1. authentik-server/Dockerfile

```dockerfile
FROM ghcr.io/goauthentik/server:2025.10.0 as base

# Override entrypoint to handle Railway's CMD stripping
ENTRYPOINT []

# Use dumb-init for proper signal handling
CMD ["dumb-init", "--", "ak", "server"]
```

**Key Pattern**: Railway strips Docker CMD, so use `ENTRYPOINT []` + `CMD ["dumb-init", "--", "ak", "server"]` to ensure correct startup.

### 2. authentik-worker/Dockerfile

```dockerfile
FROM ghcr.io/goauthentik/server:2025.10.0 as base

ENTRYPOINT []
CMD ["dumb-init", "--", "ak", "worker"]
```

### 3. authentik-proxy/Dockerfile

```dockerfile
FROM caddy:2-alpine

# Copy Caddy configuration
COPY Caddyfile /etc/caddy/Caddyfile

# Expose the proxy port
EXPOSE 8080

# Run Caddy
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile"]
```

### 4. moltbot-railway-template/Dockerfile

```dockerfile
FROM node:20-slim

# Install Java (signal-cli dependency), curl, and other required packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-17-jre-headless \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install signal-cli (embedded in container)
ARG SIGNAL_CLI_VERSION=0.13.12
RUN curl -fsSL -o /tmp/signal-cli.tar.gz \
    "https://github.com/AsamK/signal-cli/releases/download/v${SIGNAL_CLI_VERSION}/signal-cli-${SIGNAL_CLI_VERSION}-Linux-native.tar.gz" \
    && tar -xzf /tmp/signal-cli.tar.gz -C /usr/local/bin \
    && rm /tmp/signal-cli.tar.gz \
    && signal-cli --version

WORKDIR /app

# Signal data directory
RUN mkdir -p /data/.signal

# Import pre-linked Signal device data (if available)
COPY .signal-data/signal-data.tar.gz /tmp/signal-data.tar.gz
RUN if [ -f /tmp/signal-data.tar.gz ]; then \
    tar -xzf /tmp/signal-data.tar.gz -C /data/.signal \
    && chown -R 1001:1001 /data/.signal \
    && chmod -R 700 /data/.signal \
    && rm /tmp/signal-data.tar.gz; \
    fi

# Node.js dependencies
COPY package*.json /app/
RUN npm ci --only=production

# Application code
COPY --chown=1000:1000 . /app/

# Non-root user
RUN groupadd -r moltbot -g 1001 \
    && useradd -r -g moltbot -u 1001 moltbot \
    && chown -R 1001:1001 /data /app
USER 1001:1001

# Environment
ENV NODE_ENV=production
ENV PORT=8080
ENV SIGNAL_ENABLED=true
ENV SIGNAL_DATA_DIR=/data/.signal
ENV SIGNAL_CLI_PATH=/usr/local/bin/signal-cli

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

EXPOSE 8080
CMD ["node", "src/index.js"]
```

> **Key difference from earlier architecture**: This Dockerfile embeds signal-cli directly
> (Java 17 JRE + signal-cli binary) instead of relying on separate signal-cli-daemon and
> signal-proxy Railway services. The Node.js gateway (`src/index.js`) spawns signal-cli as
> a child process on `127.0.0.1:8081`.

---

## Health Checks & Monitoring

### Structured Logging (Pino)

**File**: `moltbot-railway-template/middleware/logger.js`

```javascript
const pino = require('pino');

const logger = pino({
  level: process.env.LOG_LEVEL || 'info',
  formatters: {
    level: (label) => ({ level: label }),
  },
  timestamp: pino.stdTimeFunctions.isoTime,
});

function requestLogger(req, res, next) {
  const start = Date.now();

  res.on('finish', () => {
    logger.info({
      method: req.method,
      path: req.path,
      statusCode: res.statusCode,
      duration: Date.now() - start,
      userAgent: req.get('user-agent'),
    }, 'request completed');
  });

  next();
}

module.exports = { logger, requestLogger };
```

**Log Format**:
```json
{
  "level": "info",
  "time": "2026-02-06T15:30:00.000Z",
  "method": "GET",
  "path": "/health",
  "statusCode": 200,
  "duration": 15,
  "userAgent": "Railway-HealthCheck/1.0",
  "msg": "request completed"
}
```

### Log Rotation

**Configuration**: See `supervisord.conf` section above

**Settings**:
- Max file size: 100MB (supervisord.log, nodejs.log, openclaw.log)
- Max error file size: 50MB (error logs)
- Backups: 3-5 rotated files retained
- Location: `/data/workspace/logs/`

**Log Files**:
- `/data/workspace/logs/supervisord.log` - Supervisor process log
- `/data/workspace/logs/nodejs.log` - Express.js application log
- `/data/workspace/logs/nodejs-error.log` - Express.js error log
- `/data/workspace/logs/openclaw.log` - Python OpenClaw log
- `/data/workspace/logs/openclaw-error.log` - Python error log

---

## Volume Structure

```
/data/
├── .clawdbot/                    # State directory
│   ├── moltbot.json              # Main configuration
│   ├── openclaw.json             # Model provider config
│   ├── credentials/              # Channel credentials
│   │   └── signal/               # Signal linked device data
│   └── sessions/                 # Session persistence
├── workspace/                    # Agent workspace
│   ├── souls/                    # Agent personal memory
│   │   ├── main/
│   │   │   └── MEMORY.md         # Kublai personal context
│   │   ├── researcher/
│   │   │   └── MEMORY.md         # Möngke personal context
│   │   └── ...
│   ├── logs/                     # Application logs (rotated)
│   │   ├── supervisord.log
│   │   ├── nodejs.log
│   │   ├── nodejs-error.log
│   │   ├── openclaw.log
│   │   └── openclaw-error.log
│   └── (user files)
└── backups/                      # Local backups (optional)
```

> **Signal Data Persistence**: The embedded signal-cli stores device registration at
> `/data/.signal` (configured via `SIGNAL_DATA_DIR`). This path is within the `/data`
> persistent volume and survives redeployments. Pre-linked device data can be imported
> during Docker build via `.signal-data/signal-data.tar.gz`.

---

## Backup and Recovery

### What to Backup

| Path | Contents | Priority | Frequency |
|------|----------|----------|-----------|
| `/data/.clawdbot/moltbot.json` | Main configuration | Critical | Before changes |
| `/data/.clawdbot/openclaw.json` | Model provider config | Critical | Before changes |
| `/data/.clawdbot/credentials/` | Channel authentication | Critical | Daily |
| `/data/workspace/souls/` | Agent personal memory | High | Daily |
| Environment variables | API keys, tokens | Critical | On creation |
| Neo4j database | Operational memory | Critical | Daily |
| Authentik database | User accounts, SSO config | Critical | Daily |

### Neo4j Export

```bash
# Export all data to JSON
python -c "
from openclaw_memory import OpenClawMemory
memory = OpenClawMemory()
memory.export_to_json('/data/backups/neo4j-$(date +%Y%m%d).json')
"
```

### Authentik Backup

```bash
# Export Authentik blueprints
railway run --service authentik-server ak export_blueprint > /data/backups/authentik-$(date +%Y%m%d).yaml
```

### Backup Command

```bash
# Create timestamped backup
BACKUP_DIR="/data/backups/kurultai-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Backup configurations
tar -czf "$BACKUP_DIR/config.tar.gz" \
  /data/.clawdbot/moltbot.json \
  /data/.clawdbot/openclaw.json \
  /data/.clawdbot/credentials/

# Backup personal memory
tar -czf "$BACKUP_DIR/souls.tar.gz" \
  /data/workspace/souls/

# Export Neo4j
python -c "from openclaw_memory import OpenClawMemory; OpenClawMemory().export_to_json('$BACKUP_DIR/neo4j.json')"

# Export Authentik
railway run --service authentik-server ak export_blueprint > "$BACKUP_DIR/authentik.yaml"

# List environment variables (sanitized)
railway variables --json | jq 'del(.[] | select(.key | contains("PASSWORD") or contains("SECRET") or contains("KEY")))' > "$BACKUP_DIR/env-vars.json"

echo "Backup complete: $BACKUP_DIR"
```

### Rollback Procedures

**1. Rollback Railway Service**:
```bash
railway rollback --service moltbot-railway-template
```

**2. Rollback Neo4j Migration**:
```bash
python scripts/run_migrations.py --target-version 2  # Rollback to v2
```

**3. Restore Configuration**:
```bash
# Restore from backup
tar -xzf /data/backups/kurultai-20260206-150000/config.tar.gz -C /

# Restart services
railway service restart --service moltbot-railway-template
```

**4. Restore Neo4j Data**:
```bash
# Import from backup JSON
python -c "
from openclaw_memory import OpenClawMemory
memory = OpenClawMemory()
memory.import_from_json('/data/backups/kurultai-20260206-150000/neo4j.json')
"
```

**5. Emergency Access (Disable Authentik)**:
```bash
# Temporarily bypass authentication
railway service stop --service authentik-proxy
railway domains --service moltbot-railway-template add kublai-direct.kurult.ai
```

---

## Security Checklist

### v0.2 Extended Security Checklist

**Authentication & Authorization**:
- [ ] `AUTHENTIK_SECRET_KEY` is strong (32+ bytes hex)
- [ ] `AUTHENTIK_BOOTSTRAP_PASSWORD` is strong (24+ chars base64)
- [ ] WebAuthn configured with user verification
- [ ] Forward auth bypass routes reviewed and documented
- [ ] Agent HMAC keys rotated within 90 days
- [ ] CBAC grants reviewed for least privilege

**Signal Integration**:
- [ ] `SIGNAL_LINK_TOKEN` is strong (32+ bytes hex)
- [ ] signal-cli bound to `127.0.0.1:8081` (localhost only, no network exposure)
- [ ] QR linking endpoint requires X-Signal-Token header
- [ ] Allowlisted users configured in moltbot.json (`allowFrom`, `groupAllowFrom`)
- [ ] Signal data directory (`/data/.signal`) has restricted permissions (700)
- [ ] Pre-linked device data imported securely during build

**Neo4j**:
- [ ] Neo4j uses TLS (neo4j+s:// URI)
- [ ] Neo4j password is strong and unique
- [ ] All queries use parameterized syntax (no string interpolation)
- [ ] Constraint-based access control enabled
- [ ] Backups scheduled and tested

**Capability Acquisition**:
- [ ] PromptInjectionFilter patterns reviewed
- [ ] CostEnforcer budget limits configured
- [ ] SandboxExecutor resource limits tested
- [ ] AST analysis detections verified
- [ ] CBAC trust levels assigned correctly

**Notion Integration**:
- [ ] `NOTION_TOKEN` is strong (Notion integration token)
- [ ] `NOTION_DATABASE_ID` is correctly configured
- [ ] Reconciliation safety rules verified (no reverting completed tasks)
- [ ] SyncEvent audit trail operational

**File Consistency Monitoring**:
- [ ] FileConsistencyChecker scans all agent workspaces
- [ ] High/critical conflicts escalated to Kublai
- [ ] `/health/file-consistency` endpoint operational

**General**:
- [ ] All tokens not committed to git
- [ ] HTTPS enforced (Railway default)
- [ ] API keys in environment variables only
- [ ] PII sanitization tested for delegation
- [ ] Structured logging configured
- [ ] Health checks passing for all services
- [ ] Credential rotation scheduled
- [ ] Neo4j fallback mode tested (circuit breaker + recovery)

---

## Railway Platform Constraints

**CRITICAL**: Railway's container environment has specific limitations that affect deployment.

### No Docker-in-Docker

Railway containers cannot run Docker. This affects:

| Feature | Impact | Required Setting |
|---------|--------|------------------|
| Agent Sandboxing | Cannot use Docker sandbox | `agents.defaults.sandbox.mode: "off"` |
| Browser Tools | Cannot spawn browser containers | `browser.enabled: false` |
| Computer Use | Cannot use desktop automation | `tools.profile: "coding"` |

**If sandbox mode is not disabled**, the gateway will crash with:
```
Error: spawn docker ENOENT
```

### Proxy Headers

Railway routes all traffic through edge proxies. The gateway must trust these proxies:

```json
"gateway": {
  "trustedProxies": ["*"]
}
```

Without this, you'll see warnings:
```
Proxy headers detected from untrusted address. Connection will not be treated as local.
```

### Required Railway Configuration

| Setting | Value | Reason |
|---------|-------|--------|
| `agents.defaults.sandbox.mode` | `"off"` | No Docker available |
| `browser.enabled` | `false` | No browser containers |
| `tools.profile` | `"coding"` | Excludes browser/computer tools |
| `gateway.trustedProxies` | `["*"]` | Accept Railway proxy headers |

---

## Testing & Validation

### Automated Testing Framework

Kurultai v0.2 includes a comprehensive testing framework spanning 7 phases and 55+ test files:

```
tests/
├── fixtures/           # Integration harness, mock agents, test data generators
├── interactive/        # Chat session recorder, 6 test scenarios, interactive runner
├── integration/        # Messaging, Neo4j, heartbeat, delegation, failover tests
├── concurrency/        # Race condition tests for concurrent access
├── chaos/             # Cascading failure and recovery tests
├── e2e/               # End-to-end workflow validation
└── performance/       # pytest-benchmark performance tests
```

#### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific category
pytest tests/integration/ -v
pytest tests/concurrency/ -v

# Interactive test scenarios (manual)
python tests/interactive/run_interactive_tests.py list
python tests/interactive/run_interactive_tests.py run 0

# Performance benchmarks
pytest tests/performance/test_benchmarks.py --benchmark-only
```

#### Jochi's Automated Test Orchestrator

Jochi (analyst agent) provides continuous automated testing:

```bash
# Run Jochi's test orchestrator
python tools/kurultai/test_runner_orchestrator.py

# Specific phase
python tools/kurultai/test_runner_orchestrator.py --phase integration

# Dry run
python tools/kurultai/test_runner_orchestrator.py --dry-run
```

Jochi automatically:
- Executes tests on schedule (smoke: 15min, full: hourly, nightly: 2AM)
- Analyzes results and categorizes findings by severity (CRITICAL/HIGH/MEDIUM/LOW)
- Auto-remediates simple issues (threshold constant fixes)
- Creates tickets for complex issues in `data/workspace/tickets/`
- Sends Signal alerts for critical findings

See `docs/plans/JOCHI_TEST_AUTOMATION.md` for full configuration.

#### Test Phases

| Phase | Description | Tests |
|-------|-------------|-------|
| **Phase 0** | Test Infrastructure | Fixture imports, mock agent factory, test data generator |
| **Phase 1** | Interactive Workflows | 6 manual chat scenarios with Kublai delegation observation |
| **Phase 2** | Unit & Integration | Agent messaging (port 18789), Neo4j CRUD, heartbeat system |
| **Phase 3** | Concurrent & Chaos | Race conditions, cascading failures, recovery testing |
| **Phase 4** | E2E Workflows | Signal message flow, multi-agent collaboration, failure recovery |
| **Phase 5** | Metrics & Observability | Prometheus metrics, Grafana dashboards |
| **Phase 6** | Performance | Task creation latency, DAG scalability, vector similarity |

### End-to-End Authentication Test

```bash
# Test 1: Unauthenticated request should redirect to login
curl -I https://kublai.kurult.ai/dashboard
# Expected: 302 redirect to /if/flow/authentication/

# Test 2: Health check should work without auth
curl https://kublai.kurult.ai/health
# Expected: 200 with healthy status

# Test 3: Signal link requires token
curl -X POST https://kublai.kurult.ai/setup/api/signal-link \
  -H "Content-Type: application/json" \
  -d '{"phoneNumber": "+1234567890"}'
# Expected: 401 Unauthorized

# Test 4: Signal link with token
curl -X POST https://kublai.kurult.ai/setup/api/signal-link \
  -H "Content-Type: application/json" \
  -H "X-Signal-Token: $SIGNAL_LINK_TOKEN" \
  -d '{"phoneNumber": "+1234567890"}'
# Expected: 200 or service response
```

### Neo4j Schema Validation

```cypher
// Run in Neo4j Browser

// Verify all indexes
SHOW INDEXES;

// Verify all constraints
SHOW CONSTRAINTS;

// Verify agent keys exist
MATCH (a:Agent)-[:HAS_KEY]->(k:AgentKey)
RETURN a.id, a.name, k.is_active;

// Verify Research nodes have research_type
MATCH (r:Research)
RETURN r.research_type, count(*) as count;

// Verify migration completed
MATCH (r:Research)
WHERE r.migrated_at IS NOT NULL
RETURN count(*) as migrated_nodes;
```

### Capability Learning Test

```bash
# Test capability acquisition
curl -X POST https://kublai.kurult.ai/api/learn \
  -H "Content-Type: application/json" \
  -d '{
    "capability": "how to send SMS messages",
    "requesting_agent": "main"
  }'
# Expected: 200 with capability_id and status
```

---

## Troubleshooting

### Gateway Won't Start

```bash
# Check logs
railway logs --service moltbot-railway-template

# Verify env vars
railway variables --service moltbot-railway-template
```

### Authentik Login Loop

**Symptoms**: Redirects infinitely between login and application
**Cause**: `AUTHENTIK_EXTERNAL_HOST` mismatch
**Fix**: Verify environment variable matches public URL

```bash
railway variables --service authentik-server set AUTHENTIK_EXTERNAL_HOST="https://kublai.kurult.ai"
```

### Neo4j Connection Timeout

**Symptoms**: Health check fails, "Neo4j connection timeout" in logs
**Cause**: AuraDB IP not whitelisted (paid tier) or incorrect credentials
**Fix**:
1. Check AuraDB console for allowed IPs
2. Verify `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` are correct

### Signal Not Connecting

**Symptoms**: Messages not received, "Signal connection error" in logs

**Fix**:
1. Check moltbot logs for signal-cli startup errors: `railway logs --service moltbot-railway-template | grep signal-cli`
2. Verify `SIGNAL_ACCOUNT` environment variable is set: `railway variables --service moltbot-railway-template`
3. Test health endpoint for Signal status: `curl https://kublai.kurult.ai/health` (check `signal.ready` field)
4. Check signal-cli health directly: `curl http://localhost:8081/v1/about` (from within container)
5. Re-link device if session expired (use QR linking endpoint)

### Messages Not Received

**Fix**:
1. Verify sender phone in `allowFrom` list in moltbot.json
2. Check logs for blocked messages: `railway logs --service moltbot-railway-template | grep "blocked"`
3. Ensure Signal linked device is still active

### Gateway Crashes with "spawn docker ENOENT"

**Symptoms**: Gateway crashes when processing messages
**Cause**: `agents.defaults.sandbox.mode` is set to `"all"` or `"non-main"`
**Fix**: Set sandbox mode to "off" in moltbot.json:

```json
{
  "agents": {
    "defaults": {
      "sandbox": {
        "mode": "off"
      }
    }
  }
}
```

### LLM Not Being Called (Empty Responses)

**Symptoms**: Chatbot returns empty responses, 0 tokens used, <100ms completion time
**Root Cause**: Missing `models` array in provider configuration

**Fix**:
1. Access Control UI > Settings > OpenClaw > Raw JSON
2. Add `models` array to provider:

```json
"models": {
  "providers": {
    "anthropic": {
      "api": "anthropic-messages",
      "apiKey": "${ANTHROPIC_API_KEY}",
      "baseUrl": "${ANTHROPIC_BASE_URL}",
      "models": [
        {
          "id": "claude-sonnet-4-20250514",
          "name": "Claude Sonnet 4"
        }
      ]
    }
  }
}
```

### Agent Communication Fails

**Symptoms**: Delegation returns 500, "Agent not reachable" error
**Cause**: `OPENCLAW_GATEWAY_URL` incorrect
**Fix**: Use internal Railway URL:

```bash
railway variables set OPENCLAW_GATEWAY_URL="http://moltbot-railway-template.railway.internal:8080"
```

### Capability Learning Blocked

**Symptoms**: `/learn` command returns "potential prompt injection"
**Cause**: PromptInjectionFilter too aggressive
**Fix**: Review patterns in `tools/kurultai/security/prompt_injection_filter.py` and adjust if legitimate request

---

## Scope Boundary -- Deferred to v0.3

The following features are explicitly deferred from v0.2 to v0.3:

| Feature | Status | Notes |
|---------|--------|-------|
| Jochi Backend Issues (Phase 4.6) | DEFERRED | Requires Phase 2 capability system operational first |
| Ogedei Proactive Improvement (Phase 4.7) | DEFERRED | Requires operational baseline data |
| Chagatai Background Synthesis (Phase 4.8) | DEFERRED | Requires content generation pipeline |
| Self-Improvement/Kaizen (Phase 4.9) | DEFERRED | Advanced feature requiring stable reflection system |
| ClawTasks Bounty System (Phase 5) | DEFERRED | Marketplace feature |
| Jochi-Temujin Collaboration (Phase 6) | DEFERRED | Requires proven agentToAgent messaging |
| Auto-Skill Generation (Phase 9) | DEFERRED | Requires capability acquisition system operational |
| Competitive Advantage (Phase 10) | DEFERRED | Business logic layer |

### Coverage Summary

| Status | Count | Percentage |
|--------|-------|------------|
| COVERED | 6 | 38% |
| PARTIALLY COVERED | 3 | 19% |
| DEFERRED to v0.3 | 7 | 44% |

### Phased Release Strategy

**kurultai_0.2** covers **Core Infrastructure + Foundation Features**: working multi-agent system with Neo4j-backed memory, SSO authentication, Signal messaging, capability acquisition pipeline, task dependency engine, Notion integration, file consistency monitoring, and operational monitoring.

**kurultai_0.3** will cover **Agent Protocols, Marketplace, and Advanced Features**: autonomous agent behaviors, inter-agent collaboration protocols, marketplace features, auto-skill generation, and self-improvement/Kaizen.

---

## References

- [OpenClaw Documentation](https://docs.openclaw.ai/)
- [Railway Documentation](https://docs.railway.app/)
- [Signal CLI Documentation](https://github.com/AsamK/signal-cli)
- [Authentik Documentation](https://docs.goauthentik.io/)
- [Neo4j AuraDB Documentation](https://neo4j.com/docs/aura/)
- [Caddy Forward Auth](https://caddyserver.com/docs/caddyfile/directives/forward_auth)
- [Tree-sitter Python](https://github.com/tree-sitter/tree-sitter-python)
- Local skill reference: `~/.claude/skills/molt/`
- Kurultai v0.2 Deployment Plan: `/Users/kurultai/molt/docs/plans/kurultai_0.2.md`

---

**Document Version**: v0.2.2
**Last Updated**: 2026-02-07
**Maintainer**: Kurultai System Architecture
