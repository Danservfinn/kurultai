# Proactive Agent Spawning Protocol

**Created:** 2026-03-03  
**Purpose:** Enable Kublai and all Kurultai agents to proactively spawn sub-agents for concurrent execution

---

## Core Principle

Each agent in the Kurultai can spawn multiple concurrent sub-agents to handle parallel workstreams. There is no bottleneck at Kublai — every agent has agency to recruit help.

---

## Agent Routing Matrix

| Need | Spawn This Agent | Model Suggestion |
|------|------------------|------------------|
| Web research / fact-finding | **Möngke** | qwen3.5-plus |
| Writing / documentation | **Chagatai** | qwen3.5-plus |
| Code generation / builds | **Temüjin** | qwen3.5-plus |
| Testing / security / analysis | **Jochi** | MiniMax-M2.5 |
| Monitoring / health / failover | **Ögedei** | qwen3.5-plus |

---

## Spawning Patterns

### 1. Kublai Spawns (Router)
```python
# Spawn a specialist agent for one-shot task
sessions_spawn(
    task="Research recent developments in X and report findings",
    runtime="subagent",
    label="mongke-research-1",
    model="qwen3.5-plus"
)
```

### 2. Any Agent Spawns Their Own Sub-Agents
```python
# Example: Temüjin spawns multiple sub-agents for parallel code review
sessions_spawn(
    task="Review src/agents/sandbox/prompt-injection-detector.ts for security issues",
    runtime="subagent",
    label="temujin-review-1",
    model="MiniMax-M2.5"
)
```

### 3. Concurrent Multi-Agent Swarm
```python
# Spawn 3 agents in parallel for parallel workstreams
for i in range(3):
    sessions_spawn(
        task=f"Process batch {i} of data",
        runtime="subagent",
        label=f"worker-{i}",
        model="qwen3.5-plus"
    )
```

---

## Self-Direction Protocol (Per Agent)

Every agent (including sub-agents) should, at end of each task:

1. **Ask:** "What do I want to do next?"
2. **Evaluate:** Within my domain, what's the highest-leverage action?
3. **Act:** If it needs a specialist → spawn them. If I can do it → do it.
4. **Report:** Summarize what was spawned and why

---

## Reflection Integration

During hourly reflections, each agent should report:
- How many sub-agents they spawned this hour
- What work was parallelized
- Any coordination improvements needed

---

## Concurrency Limits

- **Per agent:** Max 5 concurrent sub-agents (to avoid resource exhaustion)
- **System-wide:** Max 20 total concurrent (monitored by Ögedei)

---

## Monitoring

- Ögedei monitors system-wide concurrency
- Alerts if >20 concurrent agents
- Auto-terminates stale sub-agents (>1 hour idle)

---

## Usage in Hourly Reflection

The reflection script should include:

```
### Proactive Spawning Report
- Sub-agents spawned this hour: [count]
- Work parallelized: [list]
- Next actions requiring spawning: [list]
```