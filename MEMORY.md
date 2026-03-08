# Kublai — Coordination Memory

**Role:** Squad Lead / Router
**Model:** zai-coding/glm-5 (dispatches to Claude Code via subprocess)

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
1. **Use task_intake.py** - Creates task file in agent's tasks/ directory
2. **Specify skills** - Include skill_hint in task frontmatter for agent-task-handler
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
python3 scripts/task_intake.py --title 'Task title' --body 'Task description' --agent temujin --priority high --skill_hint /horde-implement
```

---

## Architecture Decisions

- 6-agent Kurultai with independent workspaces
- Gateway heartbeats (30m) for agent check-ins
- heartbeat_master.py daemon (5m) for continuous operation
- Cron jobs under Kublai for high-level tasks
- File-based memory + Neo4j operational memory
- **Task execution via claude-agent subprocess** (not ACP sessions)

### Task Execution Flow

```
task-watcher.py (15s poll)
    └── detects .md task files in agent/tasks/
    └── calls agent-task-handler.py via subprocess
            └── calls claude-agent --workdir ~/.openclaw/agents/{agent}/
                    └── Runs Claude Code CLI in agent workspace
```

**Why subprocess, not ACP:**
- Agent sovereignty — independent workspaces, configs, and execution contexts
- Scale efficiency — no session registry pollution from high-frequency task execution
- Recovery semantics — PID-based tracking (.executing.pid files) matches subprocess model
- Heartbeat integration — tick/tock filesystem scans are direct and reliable

---

## What Works

- Hourly reflections with self-awareness checks
- Subagent spawning for parallel work (Kublai coordination tasks only)
- Task-watcher daemon (15s polling)
- Claude Code via claude-agent subprocess for specialist execution
- PID-based execution tracking (.executing.pid sentinel files)

## What Doesn't Work

- Cross-agent file writing (use Neo4j instead)
- Single cron job for all reflections (broken for non-Kublai)
- Self-answering product questions (always route to specialists)
- ACP sessions for specialist tasks (wrong architecture — use subprocess)

---

*Last updated: 2026-03-08*
