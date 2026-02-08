---
title: Kurultai Unified Heartbeat System
type: heartbeat-spec
link: kurultai-unified-heartbeat
tags: [heartbeat, unified-heartbeat, background-tasks, multi-agent, kurultai]
ontological_relations:
  - relates_to: [[kurultai-architecture]]
  - relates_to: [[two-tier-heartbeat-system]]
  - relates_to: [[golden-horde-consensus-heartbeat-tasks]]
uuid: AUTO_GENERATED
created_at: AUTO_GENERATED
updated_at: 2026-02-08
---

# Kurultai Unified Heartbeat System

**Version**: 0.3
**Last Updated**: 2026-02-08
**Status**: Production
**Cycle Interval**: 5 minutes

---

## Executive Summary

The Unified Heartbeat is a consolidated background task scheduler that drives all agent operations in the Kurultai multi-agent system. It replaces fragmented scheduling with a single 5-minute heartbeat cycle coordinating all 6 agents and their 12 distinct background tasks.

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

## Two-Tier Heartbeat Architecture

### Overview

The heartbeat system uses a **two-tier model** that distinguishes between infrastructure health and functional agent activity:

| Tier | Property | Written By | Threshold | Meaning |
|------|----------|------------|-----------|---------|
| **Infrastructure** | `Agent.infra_heartbeat` | Python sidecar (every 30s) | 120s (4 missed) | Gateway process alive |
| **Functional** | `Agent.last_heartbeat` | Agent activity (claim/complete) | 90s (3 missed) | Agent functionally working |

### Why Two Tiers?

- **Infra heartbeat** proves the gateway process is running (even if agents are idle)
- **Functional heartbeat** proves agents are actually processing work
- **Failover decisions** use worst-case of both signals
- **No false positives** from agents that are "up" but stuck

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
Every 5 minutes (3 tasks, 650 tokens):
  - Ögedei: health_check (150)
  - Jochi: memory_curation_rapid (300)
  - Kublai: status_synthesis (200)

Every 15 minutes (2 tasks, 1000 tokens):
  - Ögedei: file_consistency (200)
  - Jochi: smoke_tests (800)

Every 30 minutes (1 task, 500 tokens):
  - Chagatai: reflection_consolidation (500)

Every 60 minutes (2 tasks, 2300 tokens):
  - Jochi: full_tests (1500)
  - System: notion_sync (800)

Every 6 hours (1 task, 2000 tokens):
  - Jochi: deep_curation (2000)

Every 24 hours (2 tasks, 1800 tokens):
  - Möngke: knowledge_gap_analysis (600)
  - Möngke: ordo_sacer_research (1200)

Every 7 days (1 task, 2000 tokens):
  - Möngke: ecosystem_intelligence (2000)
```

### Peak Token Usage

**Peak per cycle:** ~8,250 tokens (once daily at 24-hour alignment)
**Average per cycle:** ~1,500 tokens

---

## Agent Task Details

### Ögedei (Operations Agent)

**Role:** System health monitoring, file consistency, failover orchestration

#### health_check (5 min, 150 tokens)

```python
async def health_check(driver) -> Dict:
    """
    Check system health:
    - Neo4j connectivity
    - Agent heartbeat ages (both infra and functional)
    - Disk space usage
    - Log file sizes
    """
```

**Two-tier checks:**
- `infra_heartbeat` > 120s → gateway process dead (hard failure)
- `last_heartbeat` > 90s → agent stuck (functional failure)

**Actions on failure:**
- Log warning to Neo4j
- Escalate to Kublai if critical
- Trigger failover if Kublai unavailable

#### file_consistency (15 min, 200 tokens)

Verify file consistency across agent workspaces, check ARCHITECTURE.md sync status.

---

### Jochi (Analyst Agent)

**Role:** Memory curation, testing, analysis

#### memory_curation_rapid (5 min, 300 tokens)

Enforce token budgets, clean expired notifications, clear stale sessions.

#### smoke_tests (15 min, 800 tokens)

Run quick smoke tests via test runner. On failure: create ticket for Temüjin.

#### full_tests (60 min, 1500 tokens)

Run full test suite with remediation. On critical failure: create ticket immediately.

#### deep_curation (6 hours, 2000 tokens)

Delete orphaned nodes, purge tombstoned entries, archive COLD tier to file.

---

### Chagatai (Writer Agent)

**Role:** Content creation, documentation, reflection

#### reflection_consolidation (30 min, 500 tokens)

Consolidate reflections when system idle (no pending user tasks).

---

### Möngke (Research Agent)

**Role:** Research, knowledge gathering, ecosystem tracking

| Task | Frequency | Budget | Description |
|------|-----------|--------|-------------|
| knowledge_gap_analysis | 24h | 600 | Identify sparse knowledge areas |
| ordo_sacer_research | 24h | 1200 | Research esoteric concepts |
| ecosystem_intelligence | 7d | 2000 | Track ecosystem changes |

---

### Kublai (Main/Orchestrator Agent)

**Role:** Task delegation, response synthesis, system coordination

#### status_synthesis (5 min, 200 tokens)

```python
async def status_synthesis(driver) -> Dict:
    """
    Synthesize agent status:
    - Query all agent heartbeats (both tiers)
    - Check for critical issues
    - Escalate if needed
    """
```

**Two-tier query:**
```cypher
MATCH (a:Agent)
RETURN a.name, a.status,
       a.infra_heartbeat, a.last_heartbeat,
       a.current_task
ORDER BY a.last_heartbeat DESC
```

---

### System Tasks

#### notion_sync (60 min, 800 tokens)

Bidirectional Notion↔Neo4j task sync for users with `notion_integration_enabled: true`.

---

## Core Components

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

## Heartbeat Execution Flow

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

### Frequency Predicates

| Frequency | Predicate | Cycles/Execution |
|-----------|-----------|------------------|
| 5 min | `cycle % 1 == 0` | Every cycle |
| 15 min | `cycle % 3 == 0` | Every 3 cycles |
| 30 min | `cycle % 6 == 0` | Every 6 cycles |
| 60 min | `cycle % 12 == 0` | Every 12 cycles |
| 6 hours | `cycle % 72 == 0` | Every 72 cycles |
| 24 hours | `cycle % 288 == 0` | Every 288 cycles |
| 7 days | `cycle % 2016 == 0` | Every 2016 cycles |

---

## Neo4j Schema

### HeartbeatCycle Node

```cypher
(:HeartbeatCycle {
  id: string,              # UUID
  cycle_number: int,       # Incrementing cycle counter
  started_at: datetime,
  completed_at: datetime,
  tasks_run: int,
  tasks_succeeded: int,
  tasks_failed: int,
  total_tokens: int,
  duration_seconds: float
})
```

### TaskResult Node

```cypher
(:TaskResult {
  agent: string,           # Agent name (ögedei, jochi, etc.)
  task_name: string,       # Task identifier
  status: string,          # success, error, timeout
  started_at: datetime,
  completed_at: datetime,
  summary: string,         # Human-readable summary
  error_message: string,   # If status == error
  tokens_used: int         # Actual tokens consumed
})
```

### Agent Node (Two-Tier Properties)

```cypher
(:Agent {
  id: string,              # main, researcher, writer, developer, analyst, ops
  name: string,            # Kublai, Möngke, Chagatai, Temüjin, Jochi, Ögedei
  type: string,            # orchestrator, specialist
  status: string,          # active, inactive, error
  infra_heartbeat: datetime,   # Written by sidecar every 30s
  last_heartbeat: datetime,    # Written on claim/complete
  current_task: string,    # Currently assigned task ID
  trust_level: string      # LOW, MEDIUM, HIGH
})
```

### Relationships

```cypher
// Heartbeat cycle contains task results
(HeartbeatCycle)-[:HAS_RESULT]->(TaskResult)

// Task result associated with agent
(Agent)-[:PERFORMED]->(TaskResult)
```

### Required Indexes

```cypher
CREATE INDEX heartbeat_cycle_number IF NOT EXISTS
FOR (hc:HeartbeatCycle) ON (hc.cycle_number);

CREATE INDEX task_result_agent IF NOT EXISTS
FOR (tr:TaskResult) ON (tr.agent);

CREATE INDEX task_result_status IF NOT EXISTS
FOR (tr:TaskResult) ON (tr.status);

CREATE INDEX agent_infra_heartbeat IF NOT EXISTS
FOR (a:Agent) ON (a.infra_heartbeat);

CREATE INDEX agent_last_heartbeat IF NOT EXISTS
FOR (a:Agent) ON (a.last_heartbeat);
```

---

## CLI Usage

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

---

## Railway Cron Configuration

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
| Infra heartbeat age | `Agent.infra_heartbeat` | > 120s |
| Functional heartbeat age | `Agent.last_heartbeat` | > 90s |

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

**Get agent health (two-tier):**
```cypher
MATCH (a:Agent)
RETURN a.name, a.status,
       datetime() - a.infra_heartbeat as infra_age_seconds,
       datetime() - a.last_heartbeat as func_age_seconds,
       a.current_task
ORDER BY a.infra_heartbeat DESC;
```

---

## Failure Handling

### Task Timeout

- Default timeout: 60 seconds
- On timeout: Task marked `status: "timeout"`
- Cycle continues with remaining tasks

### Task Error

- On exception: Task marked `status: "error"`
- Error message captured
- Critical tasks trigger ticket creation

### Critical Failure Escalation

**Critical tasks that create tickets on failure:**
- `smoke_tests` - System functionality
- `full_tests` - Critical test failures
- `health_check` - Infrastructure issues

**Ticket routing:**
- Infrastructure issues → Ögedei
- Code/test issues → Temüjin
- Analysis issues → Jochi

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NEO4J_URI` | No | `bolt://localhost:7687` | Neo4j connection URI |
| `NEO4J_USER` | No | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | **Yes** | - | Neo4j password |
| `PROJECT_ROOT` | No | `os.getcwd()` | Project root directory |
| `HEARTBEAT_LOG_LEVEL` | No | `INFO` | Logging level |

---

## File Locations

| Component | Path |
|-----------|------|
| Heartbeat Master | `tools/kurultai/heartbeat_master.py` |
| Agent Tasks | `tools/kurultai/agent_tasks.py` |
| Simple Curation | `tools/kurultai/curation_simple.py` |
| Test Runner | `tools/kurultai/test_runner_orchestrator.py` |
| Ticket Manager | `tools/kurultai/ticket_manager.py` |
| Notion Sync | `tools/notion_sync.py` |
| Infra Sidecar | `scripts/heartbeat_writer.py` |
| Log File | `/data/logs/heartbeat.log` |

---

## Related Documentation

- [Kurultai Unified Architecture](ARCHITECTURE.md) - Full system architecture
- [Two-Tier Heartbeat System](docs/plans/2026-02-07-two-tier-heartbeat-system.md) - Implementation plan
- [Golden Horde Consensus: Heartbeat Background Tasks](.claude/memory_anchors/golden-horde-consensus-heartbeat-tasks.md) - Design deliberation

---

**Document Status**: v0.3 - Production
**Last Updated**: 2026-02-08
**Maintainer**: Kurultai System Architecture

### Changelog

**v0.3** (2026-02-08):
- Aligned with two-tier heartbeat system (infra + functional)
- Consolidated from kurultai_0.3.md and JOCHI_TEST_AUTOMATION.md
- Unified 12 tasks across 6 agents into single 5-minute cycle
- Simplified curation from 15 queries to 4 operations
- Added token budgeting per task
- Added comprehensive monitoring queries

**v0.2** (2026-02-05):
- Added Möngke research tasks
- Added Chagatai reflection consolidation
- Added Notion sync integration

**v0.1** (2026-02-01):
- Initial unified heartbeat design
