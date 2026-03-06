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
