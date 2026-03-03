# Hybrid Architecture - Kurultai Agent System

**Version:** 2.0  
**Last Updated:** 2026-03-03  
**Status:** Active Implementation

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

## Agent Workspaces

Each agent has a dedicated workspace:

```
/Users/kublai/.openclaw/agents/{agent}/
├── config.json         # Agent configuration
├── tasks/              # Pending task queue
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

## Task Routing

### Smart Router Decision Tree

```
Task → Classify complexity
       ├─ Simple (<5 min, no context) → Subagent
       ├─ Code task → Temujin (full agent)
       ├─ Research task → Mongke (full agent)
       ├─ Writing task → Chagatai (full agent)
       ├─ Testing task → Jochi (full agent)
       └─ Ops task → Ogedei (full agent)
```

### Routing Keywords

| Agent | Keywords |
|-------|----------|
| Temujin | code, build, implement, fix, bug, feature, deploy, api |
| Mongke | research, analyze, investigate, discover, competitor, market |
| Chagatai | write, document, blog, post, content, article, creative |
| Jochi | test, security, audit, review, verify, validate, pattern |
| Ogedei | monitor, health, alert, failover, ops, uptime, status |

---

## Scripts

| Script | Purpose |
|--------|---------|
| `launch-agent.py` | Launch persistent agents |
| `agent-task-handler.py` | Process agent task queues |
| `smart-task-router.py` | Route tasks to appropriate destination |
| `agent-health-monitor.py` | Monitor agent health, auto-restart |
| `agent-dashboard.py` | Real-time agent status dashboard |
| `subagent_completion_tracker.py` | Track subagent completion |
| `spawn-consumer.sh` | Process spawn queue |

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
