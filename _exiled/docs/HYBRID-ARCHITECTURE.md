# Hybrid Architecture - Kurultai Agent System

**Version:** 3.0
**Last Updated:** 2026-03-04
**Status:** Active Implementation (post-KURULTAI-FORGE consolidation)

---

## Overview

The Kurultai system uses a **hybrid architecture** combining:
1. **6 Persistent Full Agents** (Kublai, Temujin, Mongke, Chagatai, Jochi, Ogedei)
2. **Temporary Subagents** (for parallel work)

This provides the best of both worlds:
- Persistent agents with memory and context
- Subagents for parallel execution
- 60% cost savings vs full-agent-only approach

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    KURULTAI (6 Full Agents)                 │
│  Each agent has:                                            │
│  - Persistent memory (Neo4j + files)                        │
│  - Own workspace                                            │
│  - Can spawn subagents                                      │
│  - Handles task queue                                       │
└─────────────────────────────────────────────────────────────┘
         │              │              │
         ▼              ▼              ▼
    ┌────────┐    ┌────────┐    ┌────────┐
    │Temujin │    │ Mongke │    │  Jochi │  ... (all 6)
    │(code)  │    │(research)│  │(test)  │
    └───┬────┘    └───┬────┘    └───┬────┘
        │             │             │
        │ Spawns      │ Spawns      │ Spawns
        ▼             ▼             ▼
    ┌────────────────────────────────────────┐
    │         SUBAGENTS (Temporary)          │
    │  - Parallel code reviews               │
    │  - Research deep-dives                 │
    │  - Test execution                      │
    └────────────────────────────────────────┘
```

---

## Task Workflow (post-KURULTAI-FORGE)

Complete lifecycle from task creation to completion:

```
                         ┌──────────────────────┐
                         │   TASK SOURCES        │
                         │                       │
                         │  kublai-actions.py    │
                         │  kublai-initiative.py │
                         │  CLI / API / cron     │
                         └──────────┬────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │       task_intake.py           │
                    │   (Single Entry Point)         │
                    │                               │
                    │  1. Depth check (max 3)       │
                    │  2. Auto-route via router     │
                    │  3. Duplicate check (fs)      │
                    │  4. Create in Neo4j           │
                    │  5. Write filesystem (.md)    │
                    └──────────┬────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
     ┌─────────────┐  ┌─────────────┐  ┌──────────────┐
     │ task-router  │  │  Neo4j      │  │  Filesystem  │
     │   .py        │  │ (primary)   │  │  (compat)    │
     │              │  │             │  │              │
     │ Keywords +   │  │ Task node   │  │ {agent}/     │
     │ Disambig.    │  │ PENDING     │  │  tasks/      │
     │ → agent name │  │ state       │  │  high-*.md   │
     └─────────────┘  └──────┬──────┘  └──────┬───────┘
                              │                │
                              └────────┬───────┘
                                       │
                                       ▼
                    ┌──────────────────────────────────┐
                    │     task-watcher.py (launchd)     │
                    │     SOLE DISPATCHER               │
                    │                                  │
                    │  Poll every 15s for new .md      │
                    │  Execute via agent-task-handler   │
                    │  Cleanup .done files (hourly)    │
                    └──────────────┬───────────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────────┐
                    │    agent-task-handler.py          │
                    │                                  │
                    │  1. Mark .executing              │
                    │  2. Extract depth from frontmatter│
                    │  3. Call LLM (openclaw agent)    │
                    │  4. Mark .done / .failed         │
                    │  5. Neo4j transition_task()      │
                    │  6. Can spawn subtasks (depth+1) │
                    └──────────────┬───────────────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    │              │              │
                    ▼              ▼              ▼
              ┌──────────┐  ┌──────────┐  ┌──────────┐
              │COMPLETED │  │ FAILED   │  │ TIMEOUT  │
              │          │  │          │  │          │
              │ .done    │  │ retry →  │  │ retry →  │
              │ file     │  │ PENDING  │  │ PENDING  │
              │ (48h TTL)│  │ (max 3x) │  │          │
              └──────────┘  └──────────┘  └──────────┘
```

### Subagent Spawn Pipeline (separate path)

```
  kublai-actions.py / agent-task-handler.py
              │
              │  spawn request
              ▼
  ┌──────────────────────────────┐
  │  spawn-pending.json          │  ← locked via json_state.py
  │  (status: ready)             │
  └──────────────┬───────────────┘
                 │
                 │  cron */2
                 ▼
  ┌──────────────────────────────┐
  │  spawn-consumer.sh           │
  │  → spawn_consumer_worker.py  │
  │                              │
  │  1. Validate agent allowlist │
  │  2. Sanitize input text      │
  │  3. Route: subagent or agent │
  │  4. Launch openclaw agent    │
  │  5. Track status             │
  │  6. Retry on failure (3x)   │
  │  7. Dead-letter on exhaust   │
  └──────────────────────────────┘
```

### State Machine (Neo4j)

```
  PENDING ──→ ASSIGNED ──→ EXECUTING ──→ COMPLETED
                                │
                                ├──→ FAILED ──→ (retry) ──→ PENDING
                                │
                                ├──→ TIMEOUT ──→ (retry) ──→ PENDING
                                │
                                └──→ CANCELLED

  Each transition logged as:
    (Task)-[:TRANSITIONED {from, to, actor, timestamp}]->(Task)
```

### Monitoring

```
  ┌──────────────────────────────────┐
  │      health_dashboard.py         │
  │                                  │
  │  Queue depths (per agent)        │
  │  Spawn queue depth               │
  │  Dispatch status (task-watcher)  │
  │  Neo4j: task stats, completion   │
  │         rate, bottlenecks,       │
  │         workload, hypotheses,    │
  │         active rules             │
  └──────────────────────────────────┘
```

### Safety Guards

```
  ┌─────────────────────────────────────────────────┐
  │  Depth limit: MAX_TASK_DEPTH = 3                │
  │  Dedup: has_pending_task() filesystem check     │
  │  Rate limit: MAX_ACTIONS_PER_CYCLE = 3          │
  │  Cooldown: error_spike at 7200s (2h)            │
  │  Agent allowlist: VALID_AGENTS set              │
  │  Input sanitization: sanitize_text()            │
  │  File locking: json_state.py (fcntl.flock)      │
  │  Credentials: ~/.openclaw/credentials/neo4j.env │
  └─────────────────────────────────────────────────┘
```

---

## Agent Workspaces

Each agent has a dedicated workspace:

```
/Users/kublai/.openclaw/agents/main/agent/{agent}/
├── config.json         # Agent configuration
├── tasks/              # Pending task queue (high-*.md, normal-*.md, low-*.md)
│   └── *.done          # Completed tasks (auto-cleaned after 48h by task-watcher.py)
├── workspace/          # Persistent files
└── memory/             # Agent-specific memory
    └── context.md      # Current context
```

### Agent Configuration Schema

```json
{
  "agent_name": "temujin",
  "agent_role": "Developer",
  "model": "qwen3.5-plus",
  "capabilities": ["code_generation", "code_review", "debugging"],
  "workspace_path": "/Users/kublai/.openclaw/agents/temujin/workspace",
  "memory_path": "/Users/kublai/.openclaw/agents/temujin/memory",
  "task_queue_path": "/Users/kublai/.openclaw/agents/temujin/tasks",
  "max_concurrent_subagents": 3,
  "auto_spawn_subagents": true,
  "heartbeat_interval_minutes": 5
}
```

---

## Neo4j Schema

### AgentState Node

```cypher
(:AgentState {
  name: "temujin",
  role: "Developer",
  status: "idle|busy|offline|restarting",
  current_task: "task-label-123",
  workspace_path: "/path/to/workspace",
  memory_path: "/path/to/memory",
  task_queue_path: "/path/to/tasks",
  last_heartbeat: datetime(),
  tasks_completed: 42,
  subagents_spawned: 15,
  created: datetime(),
  started: datetime()
})
```

### Relationships

```cypher
(:AgentState)-[:EXECUTING]->(:Task)
(:AgentState)-[:SPAWNED]->(:SubagentSession)
(:AgentState)-[:OWNS]->(:Workspace)
```

---

## Canonical Model Mapping

**Authoritative source:** `~/.openclaw/openclaw.json` → `agents.list[].model`

| Agent | Model | Role |
|-------|-------|------|
| Kublai | bailian/qwen3.5-plus | Orchestrator |
| Mongke | bailian/MiniMax-M2.5 | Researcher |
| Chagatai | bailian/kimi-k2.5 | Writer |
| Temujin | bailian/MiniMax-M2.5 | Developer |
| Jochi | bailian/qwen3.5-plus | Tester/Security |
| Ogedei | bailian/qwen3.5-plus | Ops/Monitor |

> **Important:** `openclaw.json` is the single source of truth for model assignments.
> The now-archived `task-consumer.sh` had incorrect mappings. Always read from
> `openclaw.json` programmatically; do not hardcode model names in scripts.

---

## Task Routing

### Canonical Router: `task-router.py` (aka `task_router.py`)

All routing goes through the canonical router. Import via:
```python
from task_router import classify_task, route_by_text, route_by_category
```

### Decision Tree

```
Task → classify_task(text)
       ├─ Score keywords per agent
       ├─ Apply disambiguation rules
       ├─ Assess complexity (simple/moderate/complex)
       │
       ├─ Simple + no context → Subagent
       ├─ Code/infra task → Temujin
       ├─ Research/analysis → Mongke
       ├─ Writing/content → Chagatai
       ├─ Test/security/audit → Jochi
       └─ Ops/monitoring → Ogedei
```

### Routing Keywords (canonical, from task-router.py)

| Agent | Primary Keywords |
|-------|----------|
| Temujin | code, build, implement, fix, bug, feature, deploy, api, database, typescript, python, infrastructure, automation, integration, sandbox, llm |
| Mongke | research, analyze, investigate, discover, find, study, competitor, market, trend, data, intelligence, survey, explore, ecosystem |
| Chagatai | write, document, blog, post, content, article, creative, copy, marketing, social, twitter, readme, changelog |
| Jochi | test, verify, validate, check, security, audit, vulnerability, scan, prompt injection, safety, review, pattern, analysis |
| Ogedei | monitor, health, alert, uptime, status, dashboard, failover, ops, cron, restart, backup, watch, track |

### Disambiguation Rules

- "research" + "security" → Jochi (not Mongke)
- "research" + "prompt injection" → Jochi
- "build" + "infrastructure" → Temujin
- "monitor" + "infrastructure" → Ogedei

---

## Scripts (post-KURULTAI-FORGE)

### Core Pipeline

| Script | Purpose |
|--------|---------|
| `task-watcher.py` | **Sole task dispatcher** (launchd daemon, 15s poll). Detects new tasks, calls agent-task-handler.py, cleans up old .done files |
| `agent-task-handler.py` | Full task lifecycle: mark executing, call LLM, mark completed/failed, update Neo4j |
| `task-router.py` | **Canonical router** — single source of truth for task routing keywords and disambiguation |
| `task_intake.py` | **Single entry point** for all task creation (depth check, route, dedup, Neo4j+filesystem) |
| `spawn-consumer.sh` | Process subagent spawn queue (*/2 cron, calls spawn_consumer_worker.py) |
| `spawn_consumer_worker.py` | Spawn queue processing with input sanitization and agent allowlist |

### Support

| Script | Purpose |
|--------|---------|
| `neo4j_task_tracker.py` | Neo4j connection factory, task state machine, hypothesis validation, rule lifecycle |
| `json_state.py` | Shared file-locking module (fcntl.flock) for all JSON state files |
| `health_dashboard.py` | Consolidated system health monitoring (replaces agent-manager.py --status) |
| `kublai-actions.py` | Rule-based actions (tick/tock cycles, with depth limits and dedup guards) |
| `kublai-initiative.py` | Proactive initiative engine |
| `agent-dashboard.py` | Real-time agent status dashboard |

### Archived (no longer active)

| Script | Replaced By |
|--------|------------|
| `task-consumer.sh` | task-watcher.py (launchd) |
| `task-queue-monitor.py` | task-watcher.py (launchd) |
| `classify-task.py` | task-router.py |
| `chat-execute.py` | agent-task-handler.py |
| `direct-execute.py` | agent-task-handler.py |
| `complete-task.py` | neo4j_task_tracker.transition_task() |

---

## Agent Lifecycle

### Launch
```bash
python3 launch-agent.py --agent temujin
# or
python3 launch-agent.py --all-agents
```

### Task Processing
```bash
python3 agent-task-handler.py --agent temujin --poll
```

### Health Monitoring
```bash
python3 agent-health-monitor.py --daemon
```

### Dashboard
```bash
python3 agent-dashboard.py --watch
```

---

## Decision Framework

### Use SUBAGENTS when:
- One-shot task (<5 min)
- No context needed
- No file persistence needed
- Simple classification/research

### Use FULL AGENTS when:
- Multi-step task (>5 min)
- Context from previous tasks needed
- File workspace needed
- Can benefit from delegation
- Part of ongoing project

---

## Cost Analysis

| Scenario | Subagents Only | Full Agents Only | Hybrid |
|----------|---------------|------------------|--------|
| 100 simple tasks/day | $2/day | $20/day | $5/day |
| 10 complex tasks/day | $5/day | $10/day | $8/day |
| **Total/month** | **$210** | **$900** | **$390** |

**Hybrid saves ~60% vs full agents while getting 90% of benefits.**

---

## Monitoring

### Health Checks
- Heartbeat every 5 minutes
- Auto-restart on stale heartbeat (>10 min)
- Alert Kublai on critical failures

### Metrics Tracked
- Agent status (idle/busy/offline)
- Current task
- Tasks completed (24h, 7d, 30d)
- Avg task duration
- Subagents spawned
- Success rate
- Local vs cloud LLM usage

### Dashboard Commands
```bash
# Real-time dashboard
python3 agent-dashboard.py --watch

# Health summary
python3 agent-health-monitor.py --summary

# Metrics (last 24h)
python3 local_llm_router.py --metrics --hours 24
```

---

## Troubleshooting

### Agent Not Responding
```bash
# Check health
python3 agent-health-monitor.py --agent temujin

# Restart agent
python3 launch-agent.py --agent temujin
```

### Tasks Not Processing
```bash
# Check task queue
ls /Users/kublai/.openclaw/agents/temujin/tasks/

# Manually process
python3 agent-task-handler.py --agent temujin
```

### Subagent Not Completing
```bash
# Check completion tracker
ps aux | grep subagent_completion_tracker

# Restart tracker
nohup python3 subagent_completion_tracker.py &
```

---

## Implementation Status

| Phase | Status | Completion |
|-------|--------|------------|
| Phase 1: Foundation | ✅ Complete | 100% |
| Phase 2: Agent Runtime | ✅ Complete | 100% |
| Phase 3: Task Routing | ✅ Complete | 100% |
| Phase 4: Monitoring | ✅ Complete | 100% |
| Phase 5: Testing | ⏳ In Progress | 0% |
| Phase 6: Documentation | ✅ Complete | 100% |

---

## Next Steps

1. Run integration tests (Phase 5)
2. Benchmark performance
3. Deploy to production
4. Monitor for 7 days
5. Optimize based on metrics
