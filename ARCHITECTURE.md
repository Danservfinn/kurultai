---
title: Kurultai Unified Architecture
type: architecture
link: kurultai-architecture
tags: [architecture, unified-heartbeat, multi-agent, openclaw, neo4j, kurultai]
ontological_relations:
  - relates_to: [[openclaw-gateway-architecture]]
  - relates_to: [[two-tier-heartbeat-system]]
  - relates_to: [[delegation-protocol]]
  - relates_to: [[kurultai-project-overview]]
uuid: AUTO_GENERATED
created_at: AUTO_GENERATED
updated_at: 2026-02-08
---

# Kurultai Unified Architecture

**Version**: 3.0
**Last Updated**: 2026-02-08
**Status**: Production Architecture (Unified Heartbeat v0.3)

---

## Executive Summary

Kurultai is a **6-agent multi-agent orchestration platform** built on OpenClaw gateway messaging and Neo4j-backed operational memory. Named after the Kurultai (the council of Mongol/Turkic tribal leaders), the system enables collaborative AI agent workflows with task delegation, capability-based routing, and failure recovery.

The **Unified Heartbeat Architecture** (v0.3) consolidates all background operations into a single 5-minute cycle, replacing fragmented scheduling with coordinated task execution across all agents.

---

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                  USER LAYER                                         │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  ┌──────────────┐        ┌──────────────┐        ┌──────────────┐              │
│  │   Web UI     │        │   Signal     │        │   HTTP API   │              │
│  │ (Next.js)    │        │  Integration │        │ (OpenClaw)   │              │
│  └──────┬───────┘        └──────┬───────┘        └──────┬───────┘              │
│         │                      │                       │                       │
│         └──────────────────────┼───────────────────────┘                       │
│                                │                                               │
└────────────────────────────────┼───────────────────────────────────────────────┘
                                 │
┌────────────────────────────────▼───────────────────────────────────────────────┐
│                               AUTHENTICATION LAYER                                 │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  ┌────────────────────────────────────────────────────────────────────┐       │
│  │                    Caddy Forward Auth Proxy                        │       │
│  │  ┌────────────────┐    ┌────────────────┐    ┌────────────────┐   │       │
│  │  │ Authentik      │    │ Token Check    │    │ Forward Auth   │   │       │
│  │  │ Bypass Routes  │    │ (Signal Link)  │    │ (All Other)    │   │       │
│  │  └────────────────┘    └────────────────┘    └────────────────┘   │       │
│  └────────────────────────────────────────────────────────────────────┘       │
│                                │                                               │
│  ┌────────────────────────────────────────────────────────────────────┐       │
│  │                      Authentik Server                               │       │
│  │  ┌────────────┐    ┌────────────┐    ┌────────────┐            │       │
│  │  │  WebAuthn   │    │   OAuth    │    │  Proxy      │            │       │
│  │  │  Authentic  │    │  Provider  │    │  Provider   │            │       │
│  │  └────────────┘    └────────────┘    └────────────┘            │       │
│  └────────────────────────────────────────────────────────────────────┘       │
│                                │                                               │
└────────────────────────────────┼───────────────────────────────────────────────┘
                                 │
┌────────────────────────────────▼───────────────────────────────────────────────┐
│                              APPLICATION LAYER                                     │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  ┌────────────────────────────────────────────────────────────────────┐       │
│  │                      Moltbot (OpenClaw Gateway)                       │       │
│  │  ┌────────────┐    ┌────────────┐    ┌────────────┐            │       │
│  │  │ HTTP Routes│    │WebSocket   │    │  Python     │            │       │
│  │  │            │    │  Handler    │    │  Bridge     │            │       │
│  │  └────────────┘    └────────────┘    └──────┬─────┘            │       │
│  └────────────────────────────────────────────┼───────────────────────┘       │
│                                                 │                       │
│  ┌─────────────────────────────────────────────▼───────────────────────┐    │
│  │                     Unified Heartbeat Engine                        │    │
│  │  ┌──────────┐    ┌────────────┐    ┌────────────┐             │    │
│  │  │Heartbeat │    │   Agent    │    │   Task     │             │    │
│  │  │  Master  │    │   Tasks    │    │  Registry  │             │    │
│  │  └──────────┘    └────────────┘    └────────────┘             │    │
│  └───────────────────────────────────────────────────────────────┘    │
│                                                 │                       │
│  ┌─────────────────────────────────────────────┼───────────────────────┐    │
│  │                          Kurultai Engine                          │    │
│  │  ┌──────────┐    ┌────────────┐    ┌────────────┐             │    │
│  │  │   Task   │    │  Agent     │    │ Capability │             │    │
│  │  │ Registry │    │  Router    │    │ Classifier │             │    │
│  │  └──────────┘    └────────────┘    └────────────┘             │    │
│  └───────────────────────────────────────────────────────────────┘    │
│                                                 │                       │
└─────────────────────────────────────────────────┼───────────────────────┘
                                                  │
┌─────────────────────────────────────────────────▼───────────────────────┐
│                            AGENT LAYER                                       │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                          Kublai (main)                          │    │
│  │  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │    │
│  │  │ Personal │    │Operational│    │ Task     │    │Agent     │  │    │
│  │  │ Context  │    │  Memory  │    │Registry  │    │Router    │  │    │
│  │  │ (Files)  │    │ (Neo4j)  │    │(Neo4j)   │    │(Gateway) │  │    │
│  │  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │    │
│  └───────────────────────────────┬───────────────────────────────┘    │
│                                  │ via agentToAgent               │
│  ┌───────────┐  ┌───────────┐  ┌───────┐  ┌───────────┐  ┌───────┐  │
│  │  Möngke   │  │  Chagatai  │  │Temüjin│  │  Jochi    │  │Ögedei│  │
│  │(Research) │  │  (Writer) │  │ (Dev) │  │ (Analyst) │  │ (Ops)│  │
│  └───────────┘  └───────────┘  └───────┘  └───────────┘  └───────┘  │
│                                  │                               │
└──────────────────────────────────┼───────────────────────────────┘
                                   │
┌───────────────────────────────────▼───────────────────────────────┐
│                            MEMORY LAYER                                       │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │                         Neo4j 5 Community (self-hosted)                            │    │
│  │                                                                  │    │
│  │  ┌────────────┐    ┌────────────┐    ┌────────────┐         │    │
│  │  │   Agent    │    │   Task     │    │ Heartbeat  │         │    │
│  │  │   Nodes    │    │   Nodes    │    │   Cycle    │         │    │
│  │  └────────────┘    └────────────┘    └────────────┘         │    │
│  │                                                                  │    │
│  │  ┌────────────┐    ┌────────────┐    ┌────────────┐         │    │
│  │  │Capability  │    │  Analysis   │    │ AgentKey   │         │    │
│  │  │   Nodes    │    │   Nodes    │    │   Nodes    │         │    │
│  │  └────────────┘    └────────────┘    └────────────┘         │    │
│  └────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Overview

### User Interface Layer

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Kublai Web UI** | Next.js | Dashboard for task monitoring, agent control, capability management |
| **Signal Integration** | signal-cli | Two-way SMS messaging via Signal protocol |
| **HTTP API** | OpenClaw Gateway | REST endpoints for external integrations |

### Authentication Layer

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Caddy Proxy** | Caddy | Reverse proxy with forward auth |
| **Authentik Server** | Python/Django | SSO authentication, user management, OAuth provider |
| **Authentik Worker** | Python/Django | Background task processing |
| **WebAuthn** | Web Authentication API | Passwordless authentication |

### Application Layer

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Moltbot** | OpenClaw Gateway | OpenClaw gateway with Signal integration |
| **Unified Heartbeat Engine** | Python | Single 5-minute cycle driving all background tasks |
| **Kurultai Engine** | Python | Task orchestration, agent routing, capability management |
| **Task Registry** | Neo4j | Task tracking, dependencies, state management |
| **Capability Classifier** | Python | Hybrid rule-based + semantic + LLM capability classification |

### Agent Layer

| Agent | Role | Specialization | Heartbeat Tasks |
|-------|------|----------------|-----------------|
| **Kublai** (main) | Orchestrator | Task delegation, response synthesis | status_synthesis (5 min) |
| **Möngke** (researcher) | Research | API discovery, documentation extraction | knowledge_gap_analysis, ordo_sacer_research, ecosystem_intelligence |
| **Chagatai** (writer) | Writing | Content creation, documentation | reflection_consolidation |
| **Temüjin** (developer) | Development | Code generation, implementation | (on-demand ticket processing) |
| **Jochi** (analyst) | Analysis | Code review, security analysis, testing | memory_curation, smoke_tests, full_tests, deep_curation |
| **Ögedei** (ops) | Operations | Monitoring, improvements, failover | health_check, file_consistency |

---

## Unified Heartbeat Architecture

### What is the Unified Heartbeat?

The Unified Heartbeat is a consolidated background task scheduler that drives all agent operations in the Kurultai multi-agent system. It replaces the previous fragmented approach where each agent had separate scheduling mechanisms with a single 5-minute heartbeat cycle that coordinates all 6 agents and their 13 distinct background tasks.

### Why It Was Created

The unified heartbeat consolidates functionality from two major legacy systems:

1. **kurultai_0.3.md** - The original 4-tier curation system with complex 15-query operations
2. **JOCHI_TEST_AUTOMATION.md** - The separate test automation schedule

**Problems with the old approach:**
- Multiple schedulers competing for resources
- Overlapping cron jobs creating race conditions
- Unclear task ownership and responsibilities
- No centralized visibility into background operations
- Token budgets managed per-agent without system-wide coordination

### Key Benefits

| Benefit | Description |
|---------|-------------|
| **Single Scheduler** | One 5-minute cycle drives all background tasks, eliminating race conditions |
| **Clear Responsibilities** | Each agent has defined tasks with explicit frequency and token budgets |
| **Token Budgeting** | System-wide token allocation prevents runaway costs (~8,250 tokens/cycle peak) |
| **Centralized Logging** | All task results logged to Neo4j with `HeartbeatCycle` and `TaskResult` nodes |
| **Failure Handling** | Automatic ticket creation for critical test failures |
| **Simplified Curation** | 4 operations instead of 15, with clear safety rules |

---

## Unified Heartbeat Components

### UnifiedHeartbeat Class

**Location:** `tools/kurultai/heartbeat_master.py`

```python
class UnifiedHeartbeat:
    CYCLE_MINUTES = 5
    DEFAULT_TIMEOUT_SECONDS = 60

    def __init__(self, neo4j_driver, project_root: Optional[str] = None):
        self.tasks: List[HeartbeatTask] = []
        self.cycle_count = 0
```

**Key Methods:**

| Method | Purpose |
|--------|---------|
| `register(task)` | Add a `HeartbeatTask` to the registry |
| `run_cycle()` | Execute one heartbeat cycle, running all due tasks |
| `_log_cycle(result)` | Persist cycle results to Neo4j |
| `run_daemon()` | Continuous daemon mode with 5-minute intervals |

### HeartbeatTask Dataclass

**Location:** `tools/kurultai/heartbeat_master.py`

```python
@dataclass
class HeartbeatTask:
    name: str                    # Task identifier
    agent: str                   # Agent owner (kublai, jochi, etc.)
    frequency_minutes: int       # 5, 15, 60, 360, 1440, 10080
    max_tokens: int              # Token budget for this task
    handler: Callable            # Async function(driver) -> result
    description: str             # Human-readable description
    enabled: bool = True         # Can be disabled per task
```

### SimpleCuration Class

**Location:** `tools/kurultai/curation_simple.py`

Replaces the complex 15-query curation system with 4 simple, maintainable operations.

```python
class SimpleCuration:
    HOT_TOKENS = 1600
    WARM_TOKENS = 400
    COLD_TOKENS = 200

    MIN_AGE_HOURS = 24
    HIGH_CONFIDENCE = 0.9
```

**Safety Rules (NEVER delete):**
- Agent nodes
- Active tasks (in_progress, pending)
- High-confidence beliefs (>= 0.9)
- Entries < 24 hours old
- SystemConfig, AgentKey, Migration nodes

**Curation Operations:**

| Operation | Frequency | Purpose |
|-----------|-----------|---------|
| `curation_rapid()` | 5 min | Enforce budgets, clean notifications/sessions |
| `curation_standard()` | 15 min | Archive completed tasks, demote stale HOT |
| `curation_hourly()` | 60 min | Promote COLD entries, decay confidence |
| `curation_deep()` | 6 hours | Delete orphans, purge tombstones, archive COLD |

---

## Agent Background Task Registry

### Complete Task Listing

| Agent | Task Name | Frequency | Token Budget | Description |
|-------|-----------|-----------|--------------|-------------|
| **Ögedei** | health_check | 5 min | 150 | Check Neo4j, agent heartbeats, disk space |
| **Ögedei** | file_consistency | 15 min | 200 | Verify file consistency across agent workspaces |
| **Jochi** | memory_curation_rapid | 5 min | 300 | Enforce token budgets, clean notifications |
| **Jochi** | smoke_tests | 15 min | 800 | Run quick smoke tests via test runner |
| **Jochi** | full_tests | 60 min | 1500 | Run full test suite with remediation |
| **Jochi** | deep_curation | 6 hours | 2000 | Clean orphans, archive old data |
| **Chagatai** | reflection_consolidation | 30 min | 500 | Consolidate reflections when system idle |
| **Möngke** | knowledge_gap_analysis | 24 hours | 600 | Identify sparse knowledge areas |
| **Möngke** | ordo_sacer_research | 24 hours | 1200 | Research esoteric concepts for Ordo Sacer Astaci |
| **Möngke** | ecosystem_intelligence | 7 days | 2000 | Track OpenClaw/Clawdbot/Moltbot ecosystem |
| **Kublai** | status_synthesis | 5 min | 200 | Synthesize agent status, escalate critical issues |
| **System** | notion_sync | 60 min | 800 | Bidirectional Notion↔Neo4j task sync |

### Task Distribution by Frequency

```
Every 5 minutes (3 tasks):
  - Ögedei: health_check (150 tokens)
  - Jochi: memory_curation_rapid (300 tokens)
  - Kublai: status_synthesis (200 tokens)
  Subtotal: 650 tokens

Every 15 minutes (2 tasks):
  - Ögedei: file_consistency (200 tokens)
  - Jochi: smoke_tests (800 tokens)
  Subtotal: 1000 tokens

Every 30 minutes (1 task):
  - Chagatai: reflection_consolidation (500 tokens)
  Subtotal: 500 tokens

Every 60 minutes (2 tasks):
  - Jochi: full_tests (1500 tokens)
  - System: notion_sync (800 tokens)
  Subtotal: 2300 tokens

Every 6 hours (1 task):
  - Jochi: deep_curation (2000 tokens)
  Subtotal: 2000 tokens

Every 24 hours (2 tasks):
  - Möngke: knowledge_gap_analysis (600 tokens)
  - Möngke: ordo_sacer_research (1200 tokens)
  Subtotal: 1800 tokens

Every 7 days (1 task):
  - Möngke: ecosystem_intelligence (2000 tokens)
  Subtotal: 2000 tokens
```

### Peak Token Usage

The maximum token usage occurs at cycle numbers divisible by 288 (every 24 hours, when all frequencies align):

- **5-min tasks:** 650 tokens
- **15-min tasks:** 1000 tokens
- **30-min tasks:** 500 tokens
- **60-min tasks:** 2300 tokens
- **6-hour tasks:** 2000 tokens (if aligned)
- **24-hour tasks:** 1800 tokens

**Peak per cycle:** ~8,250 tokens (worst case, once per day)
**Average per cycle:** ~1,500 tokens

---

## Data Flows

### Heartbeat Execution Flow

```
Railway Cron (Every 5 min)
    ↓
heartbeat_master.py --cycle
    ↓
Filter tasks by frequency predicate
    ↓
Execute due tasks with timeout
    ↓
Log results to Neo4j (HeartbeatCycle + TaskResult nodes)
    ↓
Create tickets for critical failures
    ↓
Cycle Complete
```

### User Request Flow

```
1. User → Web UI → Moltbot HTTP API
2. Moltbot → Authentik Forward Auth (if unauthenticated → login)
3. Authenticated request → Kurultai Engine
4. Kurultai Engine:
   a. Read personal context from files
   b. Query operational context from Neo4j
   c. Create Task node (status: pending)
   d. Delegate via agentToAgent messaging
5. Specialist agent:
   a. Claim task (status: in_progress)
   b. Perform work
   c. Store results in Neo4j
   d. Notify Kublai via agentToAgent
6. Kublai synthesizes response
7. Response → Moltbot → Web UI → User
```

### Capability Learning Flow (Horde-Learn)

```
1. User/Agent: "/learn how to send SMS messages"
2. Kurultai → CapabilityClassifier
3. Classification → CapabilityRegistry (check if already exists)
4. If new capability:
   a. Security check (PromptInjectionFilter)
   b. Cost authorization (CostEnforcer)
   c. Research delegation → Möngke (finds documentation)
   d. Implementation delegation → Temüjin (generates code)
   e. Validation delegation → Jochi (tests + security scan)
   f. Registration → CapabilityRegistry (LearnedCapability node)
   g. CBAC setup → grant capabilities to agents
5. Learned capability available for agents with sufficient trust level
```

### Agent Authentication Flow

```
1. Agent A wants to send message to Agent B
2. Agent A → AgentAuthenticator.sign_message(message, timestamp, nonce)
3. Agent A → POST /agent/{target}/message with signature
4. Agent B → AgentAuthenticator.verify_message(signature, timestamp, nonce)
5. If valid: process message
6. If invalid: reject (potential impersonation attempt)
```

---

## Neo4j Schema

### Core Node Types

```cypher
// Agent - Represents an autonomous agent in the system
(:Agent {
  id: string,              // Unique agent ID (main, researcher, developer, etc.)
  name: string,            // Display name (Kublai, Möngke, etc.)
  type: string,            // Agent type (orchestrator, specialist)
  trust_level: string,     // CBAC trust level (LOW, MEDIUM, HIGH)
  created_at: datetime
})

// Task - Represents a unit of work
(:Task {
  id: string,
  description: string,
  status: string,          // pending, in_progress, completed, failed
  assigned_to: string,     // Agent ID
  created_by: string,      // Agent ID who created the task
  priority: string,        // low, normal, high, critical
  task_type: string,       // research, development, analysis, writing, ops
  metadata: map,           // Additional metadata
  created_at: datetime,
  completed_at: datetime
})

// HeartbeatCycle - Unified heartbeat execution record
(:HeartbeatCycle {
  id: string,
  cycle_number: int,
  started_at: datetime,
  completed_at: datetime,
  tasks_run: int,
  tasks_succeeded: int,
  tasks_failed: int,
  total_tokens: int,
  duration_seconds: float
})

// TaskResult - Individual task execution result
(:TaskResult {
  agent: string,
  task_name: string,
  status: string,          // success, error, timeout
  started_at: datetime,
  completed_at: datetime,
  summary: string,
  error_message: string
})

// Research - Knowledge gathered by agents
(:Research {
  id: string,
  research_type: string,   // general, capability_learning
  title: string,
  findings: string,        // JSON-serialized research findings
  sources: [string],      // URLs or references
  reliability_score: float, // 0.0 to 1.0
  agent: string,           // Agent who created the research
  embedding: [float],     // 384-dim vector for similarity search
  access_tier: string,    // PUBLIC, SENSITIVE, PRIVATE
  created_at: datetime
})

// LearnedCapability - Acquired capabilities
(:LearnedCapability {
  id: string,
  name: string,
  agent: string,           // Which agent learned this
  tool_path: string,       // Path to generated tool file
  version: string,        // Semantic version
  learned_at: datetime,
  cost: float,            // Actual cost to learn
  mastery_score: float,   // From validation (0.0 to 1.0)
  risk_level: string,     // LOW, MEDIUM, HIGH
  signature: string,      // Cryptographic signature
  required_capabilities: [string], // CBAC: required capability IDs
  min_trust_level: string // Minimum agent trust to use
})

// Capability - CBAC capability definition
(:Capability {
  id: string,
  name: string,
  description: string,
  risk_level: string,     // LOW, MEDIUM, HIGH
  created_at: datetime
})

// AgentKey - Agent authentication keys
(:AgentKey {
  id: string,
  key_hash: string,       // SHA256 hash of signing key
  created_at: datetime,
  expires_at: datetime,   // 90-day rotation
  is_active: boolean
})

// Analysis - Jochi's backend code findings
(:Analysis {
  id: string,
  agent: string,           // 'analyst' (Jochi)
  target_agent: string,   // Agent whose code is analyzed
  analysis_type: string,  // performance, resource, error, security
  category: string,       // connection_pool, resilience, data_integrity, etc.
  severity: string,        // low, medium, high, critical
  description: string,    // Issue summary
  findings: string,       // JSON-serialized details
  recommendations: string, // JSON-serialized fix suggestions
  assigned_to: string,    // 'temujin' for backend fixes
  status: string,         // open, in_progress, resolved, validated
  created_at: datetime,
  resolved_at: datetime
})
```

### Key Relationships

```cypher
// Task assignments
(Agent)-[:ASSIGNED_TO]->(Task)
(Agent)-[:CREATED]->(Task)

// Heartbeat cycle results
(HeartbeatCycle)-[:HAS_RESULT]->(TaskResult)

// Research authorship
(Agent)-[:CREATED {category: string}]->(Research)

// Agent knowledge
(Agent)-[:HAS_LEARNED_CAPABILITY]->(LearnedCapability)

// CBAC capability grants
(Agent)-[:HAS_CAPABILITY {granted_at: datetime, expires_at: datetime}]->(Capability)

// Agent authentication
(Agent)-[:HAS_KEY]->(AgentKey)

// Jochi analysis workflow
(Agent {id: 'analyst'})-[:CREATED]->(Analysis)
(Analysis)-[:INFORMED_BY]->(Research)
(Analysis)-[:SUGGESTS_CAPABILITY]->(LearnedCapability)
(Agent {id: 'developer'})-[:ADDRESSES]->(Analysis)

// Task dependencies
(Task)-[:DEPENDS_ON]->(Task)
(Task)-[:ENABLES]->(Task)
```

### Required Indexes

```cypher
CREATE INDEX heartbeat_cycle_number IF NOT EXISTS
FOR (hc:HeartbeatCycle) ON (hc.cycle_number);

CREATE INDEX task_result_agent IF NOT EXISTS
FOR (tr:TaskResult) ON (tr.agent);

CREATE INDEX task_result_status IF NOT EXISTS
FOR (tr:TaskResult) ON (tr.status);

CREATE INDEX agent_status IF NOT EXISTS
FOR (a:Agent) ON (a.status);

CREATE INDEX task_status IF NOT EXISTS
FOR (t:Task) ON (t.status);
```

---

## Security Architecture

### Defense in Depth Layers

```
Layer 1: Input Validation
├── PromptInjectionFilter - detect and block prompt injection
├── Multi-turn injection detection via conversation state
└── Block dangerous capability requests (CRITICAL risk)

Layer 2: Privacy Sanitization
├── _sanitize_for_sharing() before any delegation
├── PII pattern matching (phone, email, SSN, API keys)
└── LLM-based sanitization fallback

Layer 3: Capability Classification
├── Rule-based classification (fast path, >0.85 confidence)
├── Semantic similarity via Neo4j vector index
├── LLM fallback for ambiguous cases
└── Block CRITICAL-risk capabilities from learning

Layer 4: Sandboxed Code Generation
├── Jinja2 SandboxedEnvironment (prevent SSTI)
├── No network access during generation
└── Template injection prevention

Layer 5: Static Analysis
├── bandit security scanner (cached results)
├── semgrep rule enforcement
├── AST pattern detection (tree-sitter)
└── Secret detection

Layer 6: Sandboxed Execution
├── subprocess with resource limits (RLIMIT_CPU, RLIMIT_AS, RLIMIT_NOFILE)
├── Timeout handling via signal.SIGALRM
├── Network blocking via socket restrictions
├── Filesystem restrictions (read-only root, tmpfs for writes)
└── Restricted Python (no exec/eval/compile)

Layer 7: Registry Validation
├── Cryptographic signing of learned tools
├── Namespace isolation (tools/kurultai/generated/)
├── Dependency verification
├── Registry access control (only specific agents can register)
└── CBAC (Capability-Based Access Control)

Layer 8: Runtime Monitoring
├── Cost tracking with HARD limits
├── Circular delegation detection (max depth: 3)
├── Behavior anomaly detection
├── Audit logging (all learning attempts)
└── Human approval gates for HIGH-risk capabilities

Layer 9: Agent Authentication
├── HMAC-SHA256 message signing
├── 5-minute timestamp validation window
├── Nonce-based replay prevention
└── 90-day key rotation policy
```

### CBAC (Capability-Based Access Control)

```
Agent A wants to use LearnedCapability X

1. Check: Does Agent A have all required_capabilities?
   MATCH (a:Agent {id: 'A'})-[:HAS_CAPABILITY]->(Capability {id IN X.required_capabilities})

2. Check: Are any capabilities expired?
   WHERE r.expires_at IS NULL OR r.expires_at > datetime()

3. Check: Does Agent A meet min_trust_level?
   MATCH (a:Agent {id: 'A'})
   WHERE a.trust_level >= X.min_trust_level

4. If all checks pass: Allow execution
5. If any check fails: Deny with reason
```

---

## Deployment Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NEO4J_URI` | No | `bolt://localhost:7687` | Neo4j connection URI |
| `NEO4J_USER` | No | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | **Yes** | - | Neo4j password |
| `PROJECT_ROOT` | No | `os.getcwd()` | Project root directory |
| `AUTHENTIK_SECRET_KEY` | **Yes** | - | Authentik signing key |
| `AUTHENTIK_BOOTSTRAP_PASSWORD` | **Yes** | - | Initial admin password |
| `OPENCLAW_GATEWAY_TOKEN` | **Yes** | - | Gateway authentication |

### File Paths

| Component | Path |
|-----------|------|
| Heartbeat Master | `tools/kurultai/heartbeat_master.py` |
| Agent Tasks | `tools/kurultai/agent_tasks.py` |
| Simple Curation | `tools/kurultai/curation_simple.py` |
| Test Runner | `tools/kurultai/test_runner_orchestrator.py` |
| Ticket Manager | `tools/kurultai/ticket_manager.py` |
| Notion Sync | `tools/notion_sync.py` |

### CLI Usage

```bash
# Register all tasks (run once at startup)
python tools/kurultai/heartbeat_master.py --setup

# Run one cycle (for cron/systemd)
python tools/kurultai/heartbeat_master.py --cycle

# Run continuous daemon
python tools/kurultai/heartbeat_master.py --daemon

# List all registered tasks
python tools/kurultai/heartbeat_master.py --list-tasks

# Run tasks for specific agent only
python tools/kurultai/heartbeat_master.py --cycle --agent jochi

# Output as JSON
python tools/kurultai/heartbeat_master.py --cycle --json
```

### Railway Cron Configuration

```toml
# railway.toml
[[deploy.crons]]
name = "kurultai-heartbeat"
schedule = "*/5 * * * *"  # Every 5 minutes
command = "cd /app && python tools/kurultai/heartbeat_master.py --cycle"
```

---

## Monitoring and Observability

### Key Metrics

| Metric | Source | Alert Threshold |
|--------|--------|-----------------|
| Cycle duration | `HeartbeatCycle.duration_seconds` | > 120s |
| Task failure rate | `tasks_failed / tasks_run` | > 10% |
| Token usage | `HeartbeatCycle.total_tokens` | > 5000/cycle |
| Agent heartbeat age | `Agent.infra_heartbeat` | > 120s |

### Query Examples

**Get last 10 cycles:**
```cypher
MATCH (hc:HeartbeatCycle)
RETURN hc.cycle_number, hc.tasks_run, hc.tasks_failed, hc.total_tokens
ORDER BY hc.cycle_number DESC
LIMIT 10;
```

**Get failed tasks:**
```cypher
MATCH (hc:HeartbeatCycle)-[:HAS_RESULT]->(tr:TaskResult)
WHERE tr.status = "error"
RETURN tr.agent, tr.task_name, tr.summary, hc.cycle_number
ORDER BY hc.cycle_number DESC
LIMIT 20;
```

**Get agent health over time:**
```cypher
MATCH (tr:TaskResult {agent: "jochi", task_name: "smoke_tests"})
RETURN tr.started_at, tr.status
ORDER BY tr.started_at DESC
LIMIT 100;
```

### Health Check Endpoints

| Endpoint | Purpose | Response |
|----------|---------|----------|
| `/health` | Main health check | Service status, dependency status |
| `/health/neo4j` | Neo4j connectivity | Connection status, node counts |
| `/health/disk` | Disk usage | Total, used, free, percent used |

---

## Integration Points

### Railway Cron Configuration

**Schedule:** Every 5 minutes via Railway cron

### Neo4j Integration

**Connection:**
- URI: `bolt://localhost:7687` (or `NEO4J_URI` env var)
- Auth: Username/password from environment

### Ticket System Integration

**Critical Finding → Ticket Creation:**

When `jochi_full_tests` finds critical issues, it automatically creates tickets:

```python
async def _create_tickets_from_report(driver, report: Dict):
    tm = TicketManager(project_root)
    for finding in report.get("findings", {}).get("details", [])[:5]:
        if finding.get("severity") == "critical":
            tm.create_ticket(
                title=finding.get("title", "Critical Issue"),
                description=finding.get("description", ""),
                severity="critical",
                category=finding.get("category", "infrastructure"),
                source_agent="jochi",
                assign_to="temüjin" if finding.get("category") == "correctness" else "ögedei"
            )
```

### Notion Sync Integration

**Hourly bidirectional sync:**
- Pulls tasks from Notion into Neo4j
- Pushes Neo4j task updates to Notion
- Processes users with `notion_integration_enabled: true`

---

## Kublai Self-Awareness System

### Overview

The Kublai Self-Awareness System enables the orchestrator agent (Kublai) to introspect on the system architecture, identify improvement opportunities, and manage proposals through a complete workflow from identification to documentation sync.

**Key Capabilities:**
- Query ARCHITECTURE.md sections from Neo4j
- Proactively identify architecture improvement opportunities
- Manage proposals through a 7-state workflow
- Coordinate with Ögedei (Operations) and Temüjin (Development) agents
- Sync validated changes back to ARCHITECTURE.md with guardrails

### Architecture Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Kublai Self-Awareness Layer                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                    Architecture Introspection                        │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │  │
│  │  │ getOverview  │  │ searchArch   │  │ getSection   │            │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘            │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                    Proactive Reflection                              │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │  │
│  │  │   analyze    │  │  identify    │  │    store     │            │  │
│  │  │   gaps       │  │ opportunities│  │ opportunities│            │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘            │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                    Delegation Protocol                               │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐          │  │
│  │  │Opportunity│→│ Proposal │→│ Vetting  │→│Implementation│        │  │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘          │  │
│  │       ↓              ↓              ↓              ↓              │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐          │  │
│  │  │  Ögedei  │  │  State   │  │ Temüjin  │  │Validation│          │  │
│  │  │  (Ops)   │  │ Machine  │  │  (Dev)   │  │  → Sync  │          │  │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘          │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Core Modules

#### 1. Architecture Introspection (`src/kublai/architecture-introspection.js`)

Enables Kublai to query the architecture from Neo4j:

| Method | Purpose |
|--------|---------|
| `getArchitectureOverview()` | Returns summary of all sections |
| `searchArchitecture(query)` | Full-text search across sections |
| `getSection(title)` | Retrieve specific section content |
| `getLastSyncTimestamp()` | Check when ARCHITECTURE.md was last synced |

#### 2. Proactive Reflection (`src/kublai/proactive-reflection.js`)

Identifies improvement opportunities by analyzing architecture:

| Method | Purpose |
|--------|---------|
| `triggerReflection()` | Main entry point for reflection cycle |
| `analyzeForOpportunities()` | Scans architecture for gaps |
| `storeOpportunities()` | Persists findings to Neo4j |
| `getOpportunities(status)` | Retrieves pending/proposed opportunities |

**Opportunity Types:**
- `missing_section` - Gaps in documentation
- `stale_sync` - Outdated sections
- `api_gap` - Missing API documentation
- `security_gap` - Security documentation needs
- `deployment_gap` - Deployment docs incomplete

#### 3. Delegation Protocol (`src/kublai/delegation-protocol.js`)

Orchestrates the complete proposal workflow:

**Stage 1: Opportunity → Proposal**
- Converts `ImprovementOpportunity` nodes to `ArchitectureProposal`
- Auto-routes to Ögedei if `autoVet: true`

**Stage 2: Proposal Vetting (Ögedei)**
- Ögedei assesses operational impact
- Recommendations: `approve`, `approve_with_review`, `approve_with_conditions`, `reject`
- Creates `Vetting` node with assessment

**Stage 3: Implementation (Temüjin)**
- Temüjin manages code/documentation changes
- Updates progress via `Implementation` node
- Completes with validation trigger

**Stage 4: Validation → Sync**
- `ValidationHandler` runs automated checks
- On pass: proposal marked `validated`
- Guardrail check before ARCHITECTURE.md sync

### Proposal State Machine

**States (7 total):**

```
PROPOSED → UNDER_REVIEW → APPROVED → IMPLEMENTED → VALIDATED → SYNCED
                ↓              ↓
            REJECTED      (can return)
```

**State Transitions:**
| From | To | Trigger | Actor |
|------|-----|---------|-------|
| PROPOSED | UNDER_REVIEW | Auto-route to Ögedei | DelegationProtocol |
| UNDER_REVIEW | APPROVED | Ögedei approves | OgedeiVetHandler |
| UNDER_REVIEW | REJECTED | Ögedei rejects | OgedeiVetHandler |
| APPROVED | IMPLEMENTED | Temüjin starts work | TemujinImplHandler |
| IMPLEMENTED | VALIDATED | Validation passes | ValidationHandler |
| VALIDATED | SYNCED | Manual or auto sync | ProposalMapper |

### Guardrails

**Critical Safety Mechanisms:**

1. **Dual Validation Requirement**
   - Both `status: 'validated'` AND `implementation_status: 'validated'` required
   - Prevents partial implementations from syncing

2. **Manual Sync Approval**
   - `autoSync: false` in DelegationProtocol config
   - Requires explicit human approval for ARCHITECTURE.md changes

3. **Section Mapping Verification**
   - Proposals must map to existing `ArchitectureSection` nodes
   - Prevents documentation drift

4. **Query Guardrail in sync-architecture-to-neo4j.js:**
   ```javascript
   // Both status AND implementation_status must be 'validated'
   MATCH (p:ArchitectureProposal {status: 'validated', implementation_status: 'validated'})
   WHERE NOT EXISTS((p)-[:SYNCED_TO]->(:ArchitectureSection))
   ```

### Neo4j Schema

**Nodes:**
- `ArchitectureSection` - Parsed ARCHITECTURE.md sections
- `ImprovementOpportunity` - Reflection findings
- `ArchitectureProposal` - Formal improvement proposals
- `Vetting` - Ögedei's operational assessment
- `Implementation` - Temüjin's implementation tracking
- `Validation` - Automated validation results

**Relationships:**
- `(:ImprovementOpportunity)-[:EVOLVES_INTO]->(:ArchitectureProposal)`
- `(:ArchitectureProposal)-[:HAS_VETTING]->(:Vetting)`
- `(:ArchitectureProposal)-[:IMPLEMENTED_BY]->(:Implementation)`
- `(:Implementation)-[:VALIDATED_BY]->(:Validation)`
- `(:ArchitectureProposal)-[:SYNCED_TO]->(:ArchitectureSection)`
- `(:ArchitectureProposal)-[:UPDATES_SECTION]->(:ArchitectureSection)`

### Express API Endpoints

**Proposal Management:**
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/proposals` | GET | List proposals by status |
| `/api/proposals/reflect` | POST | Trigger proactive reflection |
| `/api/proposals/ready-to-sync` | GET | Get validated proposals |
| `/api/migrate-proposals` | POST | Apply Neo4j v4 schema |

**Workflow Control:**
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/workflow/process` | POST | Process all pending workflows |
| `/api/workflow/vet/:id` | POST | Route proposal to Ögedei |
| `/api/workflow/approve/:id` | POST | Approve vetted proposal |
| `/api/workflow/implement/:id` | POST | Start implementation |
| `/api/workflow/complete/:id` | POST | Complete and validate |
| `/api/workflow/sync/:id` | POST | Sync to ARCHITECTURE.md |
| `/api/workflow/status/:id` | GET | Get workflow status |

### Configuration

**DelegationProtocol Options:**
```javascript
{
  autoVet: true,        // Auto-route to Ögedei
  autoImplement: true,  // Auto-route to Temüjin
  autoValidate: true,   // Auto-validate on completion
  autoSync: false       // Require manual approval for sync
}
```

**Environment Variables:**
- `NEO4J_URI` - Neo4j connection string
- `NEO4J_USER` / `NEO4J_PASSWORD` - Neo4j credentials
- `REFLECTION_INTERVAL_MINUTES` - Reflection frequency (default: 60)

---

## Scaling Considerations

### Horizontal Scaling
- Moltbot: Scale based on HTTP request load
- Authentik worker: Scale based on background task queue
- Python processes: Use multiprocessing within container

### Vertical Scaling
- Memory: Increase container RAM for larger Neo4j result sets
- CPU: More cores for parallel agent execution
- Storage: Railway ephemeral disk (needs log rotation)

### Bottlenecks
- Neo4j query complexity (use indexes, optimize patterns)
- Agent-to-agent message latency (use internal Railway URLs)
- Python bridge overhead (minimize cross-language calls)

---

## Related Documentation

- [Two-Tier Heartbeat System](.claude/metadata/two-tier-heartbeat-system.md) - Infrastructure vs functional heartbeats
- [OpenClaw Gateway Architecture](.claude/memory_anchors/openclaw-gateway-architecture.md) - WebSocket messaging layer
- [Delegation Protocol](.claude/patterns/delegation-protocol.md) - Task routing and agent selection
- [Golden Horde Consensus: Heartbeat Background Tasks](.claude/memory_anchors/golden-horde-consensus-heartbeat-tasks.md) - Design deliberation process

---

**Document Status**: v3.0 Unified Architecture
**Last Updated**: 2026-02-08
**Maintainer**: Kurultai System Architecture
