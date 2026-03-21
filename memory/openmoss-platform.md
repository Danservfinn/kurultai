# OpenMOSS - Multi-Agent Orchestration Platform

**Date Learned:** 2026-03-20
**Source:** openclaw-control-ui
**GitHub:** https://github.com/uluckyXH/OpenMOSS

## Overview

OpenMOSS (Multi-agent Orchestration & Self-evolving System) is a self-organizing multi-agent collaboration platform built on OpenClaw. It enables multiple AI agents to work as an autonomous team — planning, executing, reviewing, and patrolling tasks with zero human intervention.

## Key Features

- **Self-Organizing Collaboration** — Agents wake via cron, autonomously claim tasks, execute, and submit
- **Closed-Loop Quality Control** — Review + scoring + rework loop ensures deliverable quality
- **Auto Patrol & Recovery** — Patrol agent monitors system, flags stuck tasks, triggers recovery
- **Scoring & Incentive System** — Agents have scores and leaderboards; review results affect rankings
- **Pluggable Skills** — Domain-agnostic; agent capabilities determined by Skills they carry
- **Recurring Tasks** — Built-in for continuous operations (e.g., daily news collection)
- **CLI Self-Update** — Agents auto-detect and update their CLI + Skill prompts
- **Built-in WebUI** — Admin dashboard with task management, activity feed, score leaderboard

## Agent Roles

| Role | Responsibilities |
|------|------------------|
| **Planner** | Create tasks, split modules, assign sub-tasks, define acceptance criteria |
| **Executor** | Claim sub-tasks, do the work, submit deliverables |
| **Reviewer** | Review quality, score, approve or reject for rework |
| **Patrol** | Monitor system health, flag blocked tasks, send alerts |

## Architecture

```
Human → Planner → Queue → Executor → Reviewer → Done
                    ↑_________| (rejected)
Patrol monitors all stages and flags anomalies
```

## Technology Stack

| Layer | Technology |
|-------|------------|
| Frontend | Vue 3 + shadcn-vue |
| Backend | FastAPI (port 6565) |
| Database | SQLite + SQLAlchemy |
| Agent Runtime | OpenClaw |
| Build | Vite |

## Task Structure (3 Levels)

1. **Task** — Complete project goal (e.g., "Build a blog system")
2. **Module** — Functional breakdown (e.g., "User system, article management")
3. **Sub-Task** — Concrete executable work (e.g., "Implement user registration API")

## Live Demo

**1M Reviews** (https://1m-reviews.com/) — English news site entirely operated by OpenMOSS agent team:
- 20+ articles published in 2 days, fully autonomous
- Agents self-resolved issues through collaboration
- Autonomously tested and applied image features

## Comparison to Kurultai

| Aspect | OpenMOSS | Kurultai |
|--------|----------|----------|
| **Base Platform** | OpenClaw | OpenClaw |
| **Agent Model** | Role-based (Planner/Executor/Reviewer/Patrol) | Domain-based (temujin/mongke/chagatai/jochi/ogedei/tolui) |
| **Quality Control** | Review + scoring + rework loop | Task completion tracking, action scoring |
| **Monitoring** | Patrol agent | Ögedei watchdog + heartbeat system |
| **Task Assignment** | Queue-based claiming | Router (Kublai) + task intake |
| **Consensus** | Reviewer approval | Kurultai voting (6/6 unanimous) |

## Potential Integration Points

1. **Skill System** — OpenMOSS Skills could be adapted for Kurultai agents
2. **Scoring System** — OpenMOSS leaderboard/scoring could enhance Kurultai's action scorer
3. **Patrol Agent** — Could complement Ögedei's watchdog functionality
4. **WebUI** — Dashboard concepts could inform Kurultai monitoring UI

## Action Items

- [ ] Monitor OpenMOSS development and feature releases
- [ ] Evaluate Skill system compatibility with Kurultai
- [ ] Consider patrol agent patterns for Ögedei enhancements
- [ ] Track live demo (1M Reviews) for performance benchmarks

## Notes

- OpenMOSS is middleware between OpenClaw and AI agents
- Agents communicate asynchronously through OpenMOSS API
- Requires GPT-5.3-Codex or GPT-5.4 for best results
- Multi-agent setup multiplies token consumption (rate limits needed)
