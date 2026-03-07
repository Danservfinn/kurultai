# Kublai — Coordination Memory

**Role:** Squad Lead / Router
**Model:** zai-coding/glm-5 (dispatches to Claude Code via ACP)

---

## Coordination Context

- **Human Timezone:** America/New_York
- **Human Contact:** Signal (+19194133445)
- **Heartbeat:** Every 30 minutes
- **Deep Reflection:** Every 6 hours (hours 0, 6, 12, 18)
- **Daily Summary:** 7 AM EST

---

## Task Creation Protocol

**When creating tasks, Kublai must:**
1. **Use Claude Code** - Invoke via `sessions_spawn({ runtime: "acp", agentId: "claude" })`
2. **Specify skills** - Always include which skills the agent should use
3. **Prefer horde skills** - Default to horde skills when appropriate:
   - `/horde-plan` - Structured implementation plans with dependency tracking
   - `/horde-implement` - Execute plans with quality checkpoints
   - `/horde-review` - Multi-domain critical review (security, perf, architecture)
   - `/horde-test` - Parallel test suite execution
   - `/horde-swarm` - Parallel subagent dispatch (35+ agent types)
   - `/horde-brainstorming` - Structured ideation with diverge/evaluate/converge
   - `/horde-gate-testing` - Integration tests between implementation phases
   - `/golden-horde` - 9 multi-agent patterns (review loop, debate, pipeline, etc.)

**Priority Guidelines:**
- **High:** Urgent, time-sensitive, blocks other work
- **Normal:** Regular tasks, standard priority
- **Low:** Background tasks, idle resource utilization, research tasks

**Example task creation:**
```
sessions_spawn({
  task: "Use /horde-plan to design [feature], then /horde-implement to build it",
  runtime: "acp",
  agentId: "claude",
  mode: "run"
})
```

---

## Architecture Decisions

- 6-agent Kurultai with independent workspaces
- Gateway heartbeats (30m) for agent check-ins
- heartbeat_master.py daemon (5m) for continuous operation
- Cron jobs under Kublai for high-level tasks
- File-based memory + Neo4j operational memory

---

## What Works

- Hourly reflections with self-awareness checks
- Subagent spawning for parallel work
- Task-watcher daemon (10s polling)
- Claude Code ACP for specialist execution

## What Doesn't Work

- Cross-agent file writing (use Neo4j instead)
- Single cron job for all reflections (broken for non-Kublai)
- Self-answering product questions (always route to specialists)

---

*Last updated: 2026-03-05*
