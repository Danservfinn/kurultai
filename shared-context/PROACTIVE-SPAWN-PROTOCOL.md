# Proactive Agent Spawning Protocol

**Created:** 2026-03-03  
**Last Updated:** 2026-03-11 (ACP runtime integration)  
**Purpose:** Enable Kublai and all Kurultai agents to proactively spawn sub-agents for concurrent execution

---

## Core Principle

Each agent in the Kurultai can spawn multiple concurrent sub-agents to handle parallel workstreams. There is no bottleneck at Kublai — every agent has agency to recruit help.

---

## Agent Routing Matrix

| Need | Spawn This Agent | Runtime | Model |
|------|------------------|---------|-------|
| Web research / fact-finding | **Möngke** | acp | claude-opus-4-6 |
| Writing / documentation | **Chagatai** | acp | claude-opus-4-6 |
| Code generation / builds | **Temüjin** | acp | claude-opus-4-6 |
| Testing / security / analysis | **Jochi** | acp | claude-opus-4-6 |
| Monitoring / health / failover | **Ögedei** | acp | claude-opus-4-6 |

**Note:** All agents use Claude Code ACP runtime with automatic fallback chain (Anthropic → Z.AI → Alibaba) for rate limit handling.

---

## Spawning Patterns

### 1. Kublai Spawns (Router)
```typescript
// Spawn a specialist agent for one-shot task (ACP runtime)
sessions_spawn({
  task: "Research recent developments in X and report findings",
  runtime: "acp",
  agentId: "claude",
  mode: "run",
  timeoutSeconds: 300
})
```

### 2. Any Agent Spawns Their Own Sub-Agents
```typescript
// Example: Temüjin spawns multiple sub-agents for parallel code review
sessions_spawn({
  task: "Review src/agents/sandbox/prompt-injection-detector.ts for security issues",
  runtime: "acp",
  agentId: "claude",
  mode: "run",
  timeoutSeconds: 600
})
```

### 3. Concurrent Multi-Agent Swarm
```typescript
// Spawn 3 agents in parallel for parallel workstreams
for (let i = 0; i < 3; i++) {
  sessions_spawn({
    task: `Process batch ${i} of data`,
    runtime: "acp",
    agentId: "claude",
    mode: "run",
    timeoutSeconds: 300
  })
}
```

### 4. Thread-Bound Persistent Sessions (Discord/Chat)
```typescript
// Multi-turn interactive work in a thread
sessions_spawn({
  task: "Build landing page for campaign",
  runtime: "acp",
  agentId: "claude",
  mode: "session",
  thread: true,
  timeoutSeconds: 1800
})
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