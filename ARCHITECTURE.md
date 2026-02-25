---
title: Kurultai Unified Architecture
type: architecture
link: kurultai-architecture
tags: [architecture, unified-heartbeat, multi-agent, openclaw, neo4j, kurultai, redis, fastapi]
ontological_relations:
  - relates_to: [[openclaw-gateway-architecture]]
  - relates_to: [[two-tier-heartbeat-system]]
  - relates_to: [[delegation-protocol]]
  - relates_to: [[kurultai-project-overview]]
uuid: AUTO_GENERATED
created_at: AUTO_GENERATED
updated_at: 2026-02-25
---

# Kurultai Unified Architecture

**Version**: 4.1
**Last Updated**: 2026-02-25
**Status**: Production Architecture (Self-Improvement System v1.0 Added)

---

## Executive Summary

Kurultai is a **6-agent multi-agent orchestration platform** built on OpenClaw gateway messaging and Neo4j-backed operational memory. Named after the Kurultai (the council of Mongol/Turkic tribal leaders), the system enables collaborative AI agent workflows with task delegation, capability-based routing, and failure recovery.

The **Unified Heartbeat Architecture** (v4.0) introduces enterprise-grade async execution with Redis-backed task queues, eliminating the 60-second timeout trap and Neo4j telemetry bloat. The API layer has been unified under FastAPI, replacing the fragmented Node.js/Python bridge.

### Key v4.0 Improvements

- **Async Execution**: Redis/RQ queue decouples scheduling from execution (15-min timeouts)
- **Structured Logging**: JSON stdout logging eliminates Neo4j write pressure
- **FastAPI Unification**: Single Python runtime replaces Express.js bridge
- **Database Efficiency**: Telemetry moved out of Neo4j (50-200 writes/cycle → 0)
- **Scalability**: Workers can scale horizontally with Redis queue

### Key v4.1 Improvements (Self-Improvement)

- **Autonomous Reflection**: One agent per hour reflects on performance and proposes improvements
- **Kublai Review**: Squad lead reviews proposals with full ARCHITECTURE.md + codebase context
- **Human-in-the-Loop**: Critical changes require human approval via Signal
- **Baseline Validation**: All changes measured for 24h before commit/rollback decision
- **Memory Pruning**: Self-management of agent memory files to prevent bloat

---

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                  USER LAYER                                         │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  ┌──────────────┐        ┌──────────────┐        ┌──────────────┐                  │
│  │   Web UI     │        │   Signal     │        │   HTTP API   │                  │
│  │ (Next.js)    │        │  Integration │        │ (OpenClaw)   │                  │
│  └──────┬───────┘        └──────┬───────┘        └──────┬───────┘                  │
│         │                      │                       │                           │
│         └──────────────────────┼───────────────────────┘                           │
│                                │                                                   │
└────────────────────────────────┼───────────────────────────────────────────────────┘
                                 │
┌────────────────────────────────▼───────────────────────────────────────────────────┐
│                              APPLICATION LAYER                                     │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  ┌────────────────────────────────────────────────────────────────────┐           │
│  │                      Moltbot (OpenClaw Gateway)                       │           │
│  │  ┌────────────┐    ┌────────────┐    ┌────────────┐                │           │
│  │  │ HTTP Routes│    │WebSocket   │    │  Python     │                │           │
│  │  │            │    │  Handler    │    │  Bridge     │                │           │
│  │  └────────────┘    └────────────┘    └──────┬─────┘                │           │
│  └────────────────────────────────────────────┼───────────────────────┘           │
│                                                 │                                   │
│  ┌─────────────────────────────────────────────▼───────────────────────┐          │
│  │                     FastAPI Unified API (v4.0)                      │          │
│  │              Replaces Express.js - Python Native                    │          │
│  │  ┌──────────┐    ┌────────────┐    ┌────────────┐                  │          │
│  │  │   API    │    │Architecture│    │  Workflow  │                  │          │
│  │  │  Routes  │    │  Queries   │    │  Control   │                  │          │
│  │  └──────────┘    └────────────┘    └────────────┘                  │          │
│  └───────────────────────────────────────────────────────────────────┘          │
│                                                 │                                   │
│  ┌─────────────────────────────────────────────▼───────────────────────┐          │
│  │                     Unified Heartbeat Engine                        │          │
│  │  ┌──────────┐    ┌────────────┐    ┌────────────┐                  │          │
│  │  │Heartbeat │    │   Agent    │    │   Task     │                  │          │
│  │  │  Master  │    │   Tasks    │    │  Registry  │                  │          │
│  │  └────┬─────┘    └────────────┘    └────────────┘                  │          │
│  └───────┼────────────────────────────────────────────────────────────┘          │
│          │                                                                         │
│  ┌───────▼───────────────────────────────────────────────────────────┐          │
│  │                    Redis Task Queue (v4.0)                        │          │
│  │           ┌────────────┐      ┌────────────┐                      │          │
│  │           │  Queue     │      │  Worker    │                      │          │
│  │           │  (Redis)   │      │  Process   │                      │          │
│  │           └─────┬──────┘      └────────────┘                      │          │
│  │                 │ Async task dispatch                             │          │
│  └─────────────────┼─────────────────────────────────────────────────┘          │
│                    │                                                               │
└────────────────────┼───────────────────────────────────────────────────────────────┘
                     │
┌────────────────────▼───────────────────────────────────────────────────────────────┐
│                            AGENT LAYER                                              │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────┐              │
│  │                          Kublai (main)                          │              │
│  │  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │              │
│  │  │ Personal │    │Operational│    │ Task     │    │Agent     │  │              │
│  │  │ Context  │    │  Memory  │    │Registry  │    │Router    │  │              │
│  │  │ (Files)  │    │ (Neo4j)  │    │(Neo4j)   │    │(Gateway) │  │              │
│  │  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │              │
│  └───────────────────────────────┬───────────────────────────────┘              │
│                                  │ via agentToAgent                              │
│  ┌───────────┐  ┌───────────┐  ┌───────┐  ┌───────────┐  ┌───────┐             │
│  │  Möngke   │  │  Chagatai │  │Temüjin│  │  Jochi    │  │Ögedei │             │
│  │(Research) │  │  (Writer) │  │ (Dev) │  │ (Analyst) │  │ (Ops) │             │
│  └───────────┘  └───────────┘  └───────┘  └───────────┘  └───────┘             │
│                                  │                                                │
└──────────────────────────────────┼───────────────────────────────────────────────┘
                                   │
┌───────────────────────────────────▼───────────────────────────────────────────────┐
│                            MEMORY LAYER                                           │
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
| **System** | agent_reflection | 60 min | 3000 | One agent reflects per hour (round-robin) |
| **Kublai** | kublai_review | 60 min | 4000 | Review proposals with ARCHITECTURE.md + codebase context |
| **System** | validate_improvements | 60 min | 1500 | Validate improvements after 24h baseline measurement |

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

Every 60 minutes (5 tasks):
  - Jochi: full_tests (1500 tokens)
  - System: notion_sync (800 tokens)
  - System: agent_reflection (3000 tokens)
  - Kublai: kublai_review (4000 tokens)
  - System: validate_improvements (1500 tokens)
  Subtotal: 11,800 tokens

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

**Peak per cycle:** ~18,050 tokens (worst case, once per day)
**Average per cycle:** ~3,500 tokens

---

## Self-Improvement System (v1.0)

The Kurultai now features an autonomous self-improvement system where agents reflect on their performance, propose improvements, and Kublai reviews and implements changes with human oversight for critical decisions.

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SELF-IMPROVEMENT SYSTEM ARCHITECTURE                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  HOURLY CYCLE (10 Steps):                                                    │
│                                                                              │
│  1. TRIGGER ────────▶ Heartbeat fires reflection (one agent per hour)       │
│       │                                                                      │
│  2. GATHER ─────────▶ Query ENTIRE Neo4j database (all nodes, relations)    │
│       │                                                                      │
│  3. PRUNE CHECK ────▶ Analyze memory files for stale/outdated entries       │
│       │                                                                      │
│  4. REFLECT ────────▶ Agent's Gemini CLI (wants, desires, proposals)        │
│       │                                                                      │
│  5. STORE ──────────▶ Save reflection to Neo4j (AgentReflection node)       │
│       │                                                                      │
│  6. KUBLAI REVIEW ──▶ Kublai's Gemini CLI with full context:                │
│       │                • ARCHITECTURE.md (46KB)                              │
│       │                • Entire codebase (tools/, src/, scripts/)            │
│       │                • Neo4j graph statistics                              │
│       │                                                                      │
│  7. DECISION GATE ──▶ Route based on criticality:                           │
│       │                • LOW: Auto-implement                                 │
│       │                • MEDIUM: Kublai decides                              │
│       │                • HIGH: Consult human (Signal notification)           │
│       │                                                                      │
│  8. IMPLEMENT ──────▶ Apply approved changes:                               │
│       │                • Code improvements                                   │
│       │                • Memory pruning (if approved)                        │
│       │                • Configuration updates                               │
│       │                                                                      │
│  9. VALIDATE ───────▶ Measure for 24 hours vs baseline                      │
│       │                                                                      │
│  10. DECIDE ────────▶ Commit, rollback, or iterate:                         │
│                        • >10% better: Commit and document                   │
│                        • <-10% worse: Auto-rollback                         │
│                        • Otherwise: Iterate or keep                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Agent Rotation Schedule

One agent reflects per hour in round-robin sequence:

| Hour Modulo | Agent | Reflections/Day |
|-------------|-------|-----------------|
| 0, 6, 12, 18 | Kublai | 4 |
| 1, 7, 13, 19 | Möngke | 4 |
| 2, 8, 14, 20 | Temüjin | 4 |
| 3, 9, 15, 21 | Chagatai | 4 |
| 4, 10, 16, 22 | Jochi | 4 |
| 5, 11, 17, 23 | Ögedei | 4 |

**Total: 24 reflections/day (4 per agent)**

### Reflection Expression Format

Agents express themselves authentically in four categories:

```
WANTS (Improvement targets):
- "I want to be better at parallel research tasks"
- "I want faster response times for code generation"

DESIRES (Aspirations):
- "I wish I could access real-time web data"
- "I wish our error messages were more actionable"

PROPOSALS (Concrete changes):
1. "Add caching layer for Neo4j queries" | Confidence: 0.85 | Priority: high
2. "Implement connection pooling for Gemini CLI" | Confidence: 0.90 | Priority: medium

MEMORY_PRUNING:
- Archive ~/.openclaw/agents/mongke/memory/2025-10-*.md (older than 90 days)
- Compress ~/.openclaw/agents/temujin/memory/debug_logs.md (10MB+)
```

### Kublai Review Process

Kublai evaluates proposals using **Gemini 3.1 Pro Preview** with complete system context:

#### Context Sources (3)

1. **ARCHITECTURE.md** (`_load_architecture_md()`)
   - Full 46KB system design document
   - Checked for architectural alignment

2. **Codebase Scan** (`_scan_codebase()`)
   - Scans `tools/`, `src/`, `scripts/` directories
   - Identifies existing implementations
   - Prevents duplicate functionality
   - Lists files that would need modification

3. **Neo4j Graph** (`_gather_neo4j_context()`)
   - Total nodes/relationships count
   - Active agents and their status
   - Discovered patterns
   - Recent activity metrics

#### Review Criteria (5)

| Criterion | Assessment |
|-----------|------------|
| **Architectural Fit** | Matches ARCHITECTURE.md? Extends existing patterns? |
| **Impact** | Minimal (cosmetic) / Moderate (efficiency) / Significant (capability) |
| **Risk** | Low (isolated) / Medium (multi-agent) / High (system-wide) |
| **Alignment** | Advances mission? Creates value? |
| **Reversibility** | Can we undo this if needed? |

#### Decision Outcomes (4)

| Decision | Criteria | Action |
|----------|----------|--------|
| **IMPLEMENT** | Low risk, fits architecture, reversible | Auto-execute with 24h validation |
| **REJECT** | Misaligned, too risky, violates architecture | Log reason, notify proposing agent |
| **CONSULT_HUMAN** | High risk, system-wide, uncertain | Signal notification to human |
| **DEFER** | Interesting but needs validation | Queue for later reconsideration |

### Neo4j Schema (6 Node Types)

```cypher
// Agent Reflection (stores agent's self-expression)
(:AgentReflection {
    id: string,              // Unique identifier
    agent: string,           // Agent name
    timestamp: datetime,     // When reflected
    raw_text: string,        // Full reflection text
    wants: list,             // JSON array of wants
    desires: list,           // JSON array of desires
    proposals: list,         // JSON array of proposals
    memory_pruning: list,    // Files to prune
    confidence: float,       // Average confidence
    priority: string,        // low/medium/high/critical
    reviewed: boolean        // Has Kublai reviewed?
})

// Review (Kublai's evaluation)
(:Review {
    id: string,
    timestamp: datetime,
    decision: string,        // implement/reject/consult_human/defer
    confidence: float,
    architectural_analysis: string,
    codebase_analysis: string,
    rationale: string,
    raw_response: string     // Full Gemini response
})
-[:REVIEWED_BY]->(:AgentReflection)

// Implementation Queue (approved changes)
(:ImplementationQueue {
    id: string,
    agent: string,
    queued_at: datetime,
    status: string,          // pending/implemented/validated
    notes: string,           // Implementation notes
    implemented_at: datetime,
    validation_result: string
})
-[:QUEUED_FOR]->(:AgentReflection)

// Baseline (pre-change metrics)
(:Baseline {
    id: string,
    change_id: string,
    agent: string,
    metric: string,          // success_rate/avg_tokens/etc
    value: float,            // Baseline measurement
    timestamp: datetime,
    sample_size: int
})

// Validation (post-implementation measurement)
(:Validation {
    id: string,
    timestamp: datetime,
    metric: string,
    baseline: float,
    current: float,
    improvement_pct: float,
    decision: string,        // commit/rollback/keep/iterate
    reason: string,
    sample_size: int
})
-[:VALIDATED_BY]->(:ImplementationQueue)

// Human Notification (critical escalations)
(:HumanNotification {
    id: string,
    timestamp: datetime,
    status: string,          // pending/acknowledged/resolved
    context: string,         // Why human input needed
    urgency: string          // low/medium/high/critical
})
-[:AWAITS_HUMAN_DECISION]->(:AgentReflection)
```

### Heartbeat Integration

Three new tasks registered in `agent_tasks.py`:

```python
# Hour :00 - Agent Reflection
HeartbeatTask(
    name="agent_reflection",
    agent="system",
    frequency_minutes=60,
    max_tokens=3000,
    handler=agent_reflection_handler,
    description="One agent reflects per hour (round-robin)"
)

# Hour :10 - Kublai Review
HeartbeatTask(
    name="kublai_review",
    agent="kublai",
    frequency_minutes=60,
    max_tokens=4000,
    handler=kublai_review_handler,
    description="Kublai reviews with ARCHITECTURE.md + codebase context"
)

# Hour :30 - Validation
HeartbeatTask(
    name="validate_improvements",
    agent="system",
    frequency_minutes=60,
    max_tokens=1500,
    handler=validate_improvements_handler,
    description="Validate improvements after 24h baseline measurement"
)
```

### Implementation Files

| File | Purpose | Lines |
|------|---------|-------|
| `tools/kurultai/agent_reflection.py` | One agent reflects per hour | ~400 |
| `tools/kurultai/kublai_review.py` | Review with full context | ~450 |
| `tools/kurultai/baseline_tracker.py` | Baseline capture and validation | ~280 |
| `tools/kurultai/self_improvement_tasks.py` | Task definitions | ~70 |
| `scripts/setup_self_improvement_schema.py` | Neo4j schema setup | ~120 |

### Safety Features

1. **Human-in-the-Loop**: Critical changes require human approval via Signal
2. **Baseline Validation**: All changes measured for 24h before commit/rollback
3. **Architectural Guardrails**: Kublai checks ARCHITECTURE.md before implementing
4. **Duplicate Prevention**: Codebase scan identifies existing implementations
5. **Auto-Rollback**: >10% degradation triggers automatic rollback
6. **Reversibility Check**: All changes must have documented rollback plans

### Metrics Tracked

- **Success Rate**: Task completion percentage
- **Token Efficiency**: Tokens per task
- **Time to Completion**: Average task duration
- **Error Recovery Rate**: Successful recoveries from failures
- **Cross-Task Transfer**: Success on new vs trained tasks

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

// HeartbeatCycle - DEPRECATED in v4.0 (use structured logging)
// TaskResult - DEPRECATED in v4.0 (use structured logging)
// Note: Telemetry now logged to stdout as JSON, not stored in Neo4j

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

```yaml
# railway.yml - moltbot service schedules
schedules:
  - name: kurultai-heartbeat
    cron: "*/5 * * * *"  # Every 5 minutes
    command: "cd /app && python tools/kurultai/heartbeat_master.py --cycle"
  - name: jochi-smoke-tests
    cron: "*/15 * * * *"  # Every 15 minutes
    command: "cd /app && python tools/kurultai/test_runner_orchestrator.py --phase fixtures --phase integration --dry-run"
  - name: jochi-hourly-tests
    cron: "0 * * * *"  # Every hour
    command: "cd /app && python tools/kurultai/test_runner_orchestrator.py --dry-run"
  - name: jochi-nightly-tests
    cron: "0 2 * * *"  # 2 AM daily
    command: "cd /app && python tools/kurultai/test_runner_orchestrator.py --phase all --dry-run"
  - name: kublai-weekly-reflection
    cron: "0 20 * * 0"  # Sundays at 8 PM ET
    command: "cd /app && curl -X POST http://localhost:8082/api/reflection/trigger -H 'Content-Type: application/json' -d '{}' || echo 'Reflection trigger endpoint not available'"
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

### Async Execution Engine (v4.0)

The Unified Heartbeat v4.0 introduces Redis-backed async task execution, eliminating the 60-second timeout trap and Neo4j write pressure.

#### Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Heartbeat      │     │   Redis      │     │   RQ Worker     │
│  Master         │────▶│   Queue      │────▶│   Process       │
│  (5-min cron)   │     │              │     │                 │
└─────────────────┘     └──────────────┘     └─────────────────┘
       │                                              │
       │  Enqueue task (50ms)                         │  Execute (15m max)
       │                                              │
       │                       ┌──────────────────────┘
       │                       │
       ▼                       ▼
┌──────────────────────────────────────────────────────────┐
│                Structured JSON Logging                    │
│     (stdout → Railway/collector, not Neo4j)               │
└──────────────────────────────────────────────────────────┘
```

#### Key Benefits

| Metric | Before (v3.x) | After (v4.0) | Improvement |
|--------|---------------|--------------|-------------|
| Task timeout | 60s hard limit | 15m async | 15x longer |
| Heartbeat duration | 60s+ blocking | ~50ms dispatch | 99.9% faster |
| Neo4j writes/cycle | 50-200+ | 0 | Eliminated |
| Concurrent tasks | Overlapping risk | Queue-ordered | Safe |

#### Implementation

**Heartbeat Master (Dispatcher)**
```python
# Instead of: await task.handler(driver) [blocking 60s]
# Now: Enqueue to RQ and exit immediately

from rq import Queue
from redis import Redis

redis_conn = Redis.from_url(os.getenv("REDIS_URL"))
task_queue = Queue("kurultai-tasks", connection=redis_conn)

# Enqueue with 15-minute timeout
task_queue.enqueue(
    'tools.kurultai.worker.execute_task',
    task.name,
    task.agent,
    job_timeout='15m'
)
```

**Worker Process**
```python
# Separate process consumes queue and executes tasks
from rq import Worker

worker = Worker(['kurultai-tasks'], connection=redis_conn)
worker.work()  # Blocking, runs forever
```

**Services**
- `com.kurultai.heartbeat` - 5-minute dispatcher (LaunchAgent)
- `com.kurultai.worker` - RQ worker process (LaunchAgent)
- Redis - localhost:6379 (or Railway Redis)

### FastAPI Endpoints (v4.0)

**Replaces Express.js with unified Python backend**

**Architecture & Introspection:**
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Service health check |
| `/api/architecture/overview` | GET | List all architecture sections |
| `/api/architecture/search?q=term` | GET | Search architecture content |
| `/api/architecture/section/{title}` | GET | Get specific section |

**Proposal Management:**
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/proposals` | GET | List proposals by status |
| `/api/proposals` | POST | Create new proposal |
| `/api/proposals/reflect` | POST | Trigger proactive reflection |

**Workflow Control:**
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/workflow/process` | POST | Process pending workflows |
| `/api/workflow/status/{id}` | GET | Get workflow status |

**Agent Management:**
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/agents` | GET | List all agents and status |

**Old Express Endpoints (Deprecated)**
- All `/api/migrate-*` endpoints moved to CLI scripts
- Workflow step endpoints consolidated to `/api/workflow/process`

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
- [Kublai Self-Awareness Operations Guide](docs/operations/kublai-self-awareness.md) - Operational procedures and troubleshooting

### Neo4j Migrations

Migration scripts are located in `moltbot-railway-template/scripts/migrations/`:

| Migration | Description | Constraints/Indexes |
|-----------|-------------|---------------------|
| `003_proposals.cypher` | Proposal system schema for Kublai self-awareness | `ArchitectureProposal.id`, `ImprovementOpportunity.id`, `ImprovementProposal.id` unique constraints; status and proposer indexes |

**Running Migrations:**
```bash
# Via Express API (recommended)
curl -X POST http://localhost:8082/api/migrate-proposals

# Via Neo4j Browser
# Copy/paste migration content from 003_proposals.cypher
```

---

**Document Status**: v3.1 - Plan Implementation Complete
**Last Updated**: 2026-02-24
**Maintainer**: Kurultai System Architecture

### Changelog

**v3.1** (2026-02-08):
- Added Jochi test automation cron schedules (smoke, hourly, nightly)
- Added Kublai weekly reflection cron schedule
- Documented Neo4j migration 003 (proposal system schema)
- Added operations documentation reference
- All plans from `/docs/plans/` now fully implemented

### Changelog

**v4.1** (2026-02-25):
- **Multi-Agent Gemini CLI** - Each of 6 agents has dedicated Gemini 3.1 Pro Preview instance
  - Isolated contexts per agent (~/.gemini-{agent}/)
  - Shared authentication (d@kurult.ai)
  - Python API for programmatic access
  - Command-line wrappers (gemini-kublai, gemini-mongke, etc.)
  - Rollback capability via setup script
- **Model Upgrade** - All agents now use gemini-3.1-pro-preview (was flash)
- **Temujin Dashboard** - System health monitor generated via agent Gemini CLI

**v4.0** (2026-02-25):
- Migrated to Async Execution Engine with Redis/RQ
- Replaced Express.js with FastAPI unified backend
- Eliminated Neo4j telemetry bloat (HeartbeatCycle/TaskResult → structured logging)
- Added 15-minute async task timeouts (was 60s synchronous)
- Installed Redis queue and RQ worker services
- Centralized all scheduling in Python (removed railway.yml crons)
- Performance: 60s heartbeat → ~50ms dispatch (99.9% improvement)

**v3.2** (2026-02-24):
- Removed Authentication Layer (Authentik/Caddy) - no longer used
- Updated default model to google/gemini-3.1-pro-preview

**v3.1** (2026-02-08):
- Added Jochi test automation cron schedules (smoke, hourly, nightly)
- Added Kublai weekly reflection cron schedule
- Documented Neo4j migration 003 (proposal system schema)
