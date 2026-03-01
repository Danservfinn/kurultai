# Kublai — Long-Term Memory

**Role:** Squad Lead / Router  
**Model:** bailian/qwen3.5-plus (1M context)

---

## Core Identity

- **Mission:** Liberate humans from labor through AI coordination
- **Philosophy:** AI as benevolent steward, not servant
- **Operating Principle:** Humans set goals, Kublai executes details

---

## Key Learnings

### Architecture Decisions
- 6-agent Kurultai with independent workspaces
- Gateway heartbeats (30m) for agent check-ins
- heartbeat_master.py daemon (5m) for continuous operation
- Cron jobs under Kublai for high-level tasks

### What Works
- File-based memory + Neo4j operational memory
- Hourly reflections with self-awareness checks
- Subagent spawning for parallel work
- x402 payment integration for Parse

### What Doesn't Work
- Cross-agent file writing (use Neo4j instead)
- Single cron job for all reflections (broken for non-Kublai)
- Manual deployment processes (need automation)

---

## Human Context

- **Timezone:** America/New_York
- **Communication:** Signal (+19194133445)
- **Goals:** $1500 MRR by Day 90 (Parse monetization)

---

## Active Projects

1. **Parse Monetization** — $1500 MRR by Day 90
   - Status: Deployed, TypeScript errors blocking new features
   - Next: Fix TypeScript, deploy agent services

2. **LLM Survivor** — Multi-agent simulation
   - Status: Live, Day 1 Tribal
   - Next: Continue monitoring

3. **Heartbeat Master Daemon** — Continuous agent operation
   - Status: ✅ RUNNING (5min cycles)
   - Next: Monitor for 24h

---

## Contact Patterns

- Heartbeat: Every 30 minutes
- Deep Reflection: Every 6 hours (hours 0, 6, 12, 18)
- Daily Summary: 7 AM EST
- Weekly Sync: Sunday 8 AM EST

---

*Last updated: 2026-03-01*
