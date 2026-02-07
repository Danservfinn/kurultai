# Kurultai v0.2 Architecture

**Version**: 2.0
**Last Updated**: 2026-02-06
**Status**: Production Architecture

---

## Overview

Kurultai v0.2 is a multi-agent orchestration system with capability acquisition through horde-learn, backed by Neo4j graph memory, and secured by Authentik SSO. The system enables agents to learn new capabilities autonomously while maintaining strict security controls through CBAC (Capability-Based Access Control) and agent authentication.

## System Architecture

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
│  │  │   Agent    │    │   Task     │    │  Research  │         │    │
│  │  │   Nodes    │    │   Nodes    │    │   Nodes    │         │    │
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
| **Kurultai Engine** | Python | Task orchestration, agent routing, capability management |
| **Task Registry** | Neo4j | Task tracking, dependencies, state management |
| **Capability Classifier** | Python | Hybrid rule-based + semantic + LLM capability classification |

### Agent Layer

| Agent | Role | Specialization |
|-------|------|----------------|
| **Kublai** (main) | Orchestrator | Task delegation, response synthesis, personal context |
| **Möngke** (researcher) | Research | API discovery, documentation extraction, pattern analysis |
| **Chagatai** (writer) | Writing | Content creation, documentation, meta-rule extraction |
| **Temüjin** (developer) | Development | Code generation, implementation, bug fixes |
| **Jochi** (analyst) | Analysis | Code review, security analysis, backend monitoring, validation |
| **Ögedei** (ops) | Operations | Monitoring, improvements, failure recovery |

### Memory Layer

| Node Type | Purpose | Key Properties |
|-----------|---------|----------------|
| **Agent** | Agent identity | id, name, type, created_at |
| **Task** | Task tracking | id, description, status, assigned_to, priority |
| **Research** | Knowledge storage | research_type, findings, sources, reliability_score, embedding |
| **LearnedCapability** | Acquired capabilities | id, name, tool_path, version, risk_level, required_capabilities |
| **Capability** | CBAC capability definitions | id, name, description, risk_level |
| **AgentKey** | Agent authentication | key_hash, expires_at, is_active |
| **Analysis** | Jochi backend findings | analysis_type, severity, findings, recommendations, status |

## Data Flows

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

### Jochi Backend Analysis Flow

```
1. Trigger: Kublai directive / Scheduled / Event-based
2. Jochi → BackendCodeReviewer.analyze_code(files)
3. ASTParser → tree-sitter parsing
4. RuleEngine → YAML rule matching
5. Findings → Analysis nodes in Neo4j
6. Kublai queries open Analysis nodes
7. Kublai → delegate to Temüjin (assigned_to: 'temujin')
8. Temüjin → implements fix
9. Jochi → validate_fix() → updates Analysis status
```

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

## Deployment Architecture

### Railway Services

| Service | Docker Base | Port | Purpose |
|---------|-------------|------|---------|
| `authentik-server` | `ghcr.io/goauthentik/server:2025.10.0` | 9000 (internal) | SSO authentication |
| `authentik-worker` | `ghcr.io/goauthentik/server:2025.10.0` | N/A | Background tasks |
| `authentik-proxy` | `caddy:2` | 8080 (public) | Reverse proxy + forward auth |
| `moltbot-railway-template` | `node:22-bookworm-slim` | 18789 (internal) | Main application |

### External Services

| Service | Type | Purpose |
|---------|------|---------|
| **Neo4j 5 Community (self-hosted on Railway)** | Self-hosted database | Graph database for operational memory |
| **Railway PostgreSQL** | Managed database | Authentik data store |

### Network Topology

```
Internet
   │
   ▼
┌──────────────┐
│ Railway DNS  │ (kublai.kurult.ai)
└──────┬───────┘
       │
       ▼
┌──────────────────────────────┐
│   Railway Load Balancer      │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐      ┌──────────────┐
│   authentik-proxy (Caddy)    │◀────►│ authentik-   │
│   Port: 8080 (public)        │      │ server       │
│                              │      │ Port: 9000   │
└──────┬───────────────────────┘      └──────┬───────┘
       │                                   │
       │ forward_auth                       │
       ▼                                   │
┌──────────────────────────────┐           │
│   moltbot-railway-template   │           │
│   Port: 18789 (internal)     │           │
└──────┬───────────────────────┘           │
       │                                   │
       │                                   │
       ▼                                   ▼
┌──────────────────┐    ┌─────────────────────────────┐
│  Kurultai Engine   │    │  Neo4j 5 Community          │
│  (Python)          │    │  (self-hosted on Railway)   │
│                    │    │                             │
└───────────────────┘    └─────────────────────────────┘
```

## Environment Configuration

### Project-Level Variables

```ini
# Neo4j
NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=*******
NEO4J_DATABASE=neo4j

# Kurultai
KURLTAI_ENABLED=true
KURLTAI_MAX_PARALLEL_TASKS=10

# Authentik
AUTHENTIK_SECRET_KEY=********************************
AUTHENTIK_BOOTSTRAP_PASSWORD=********************************
AUTHENTIK_EXTERNAL_HOST=https://kublai.kurult.ai

# Signal
SIGNAL_LINK_TOKEN=********************************

# Gateway
OPENCLAW_GATEWAY_URL=http://moltbot.railway.internal:18789
OPENCLAW_GATEWAY_TOKEN=********************************
```

### Service-Specific Variables

**authentik-server**:
```ini
AUTHENTIK_POSTGRESQL__HOST=postgres.railway.internal
AUTHENTIK_POSTGRESQL__NAME=railway
AUTHENTIK_POSTGRESQL__USER=postgres
AUTHENTIK_POSTGRESQL__PASSWORD=*******
```

**authentik-proxy**:
```ini
PORT=8080
```

**moltbot-railway-template**:
```ini
PORT=18789
```

## Development vs Production

### Development
- Local Neo4j instance (Docker)
- Mock Authentik (bypass forward auth)
- Hot reloading enabled
- Debug logging

### Production
- Neo4j 5 Community (self-hosted) (managed)
- Full Authentik SSO
- Optimized builds
- Structured logging with log rotation
- Health check monitoring
- Graceful shutdown with dumb-init

## Monitoring & Observability

### Health Check Endpoints

| Endpoint | Purpose | Response |
|----------|---------|----------|
| `/health` | Main health check | Service status, dependency status |
| `/health/neo4j` | Neo4j connectivity | Connection status, node counts |
| `/health/disk` | Disk usage | Total, used, free, percent used |

### Metrics to Track

- Agent communication success rate
- Capability learning success/failure ratio
- Average task completion time
- Neo4j query performance
- Authentication success rate
- Jochi analysis findings count

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

**Document Status**: v2.0 Architecture
**Last Updated**: 2026-02-06
**Maintainer**: Kurultai System Architecture
