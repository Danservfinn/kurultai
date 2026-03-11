# OpenClaw Agents — Kurultai Multi-Agent System

> **Human financial liberation through AI coordination.**

The **Kurultai** is a multi-agent AI orchestration system built on OpenClaw. Named after the Mongol council of leaders, it coordinates seven specialized AI agents to serve a human operator through collaborative task execution.

## Quick Overview

```
                    ┌─────────────┐
                    │   HUMAN     │
                    │  OPERATOR   │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │   KUBLAI    │
                    │  (Router)   │
                    └──────┬──────┘
                           │
        ┌──────────┬───────┼───────┬──────────┬─────────┬─────────┐
        │          │       │       │          │         │         │
   ┌────▼───┐ ┌────▼───┐ ┌─▼─────┐ ┌▼─────┐ ┌▼──────┐ ┌▼──────┐ ┌▼──────┐
   │ Möngke │ │Chagatai│ │Temüjin│ │ Jochi│ │Ögedei │ │ Tolui  │ │Kublai  │
   │Research│ │ Writer │ │  Dev  │ │Analyst│ │  Ops  │ │ Truth  │ │ Router │
   └────────┘ └────────┘ └───────┘ └──────┘ └───────┘ └───────┘ └────────┘
```

## The Seven Agents

| Agent | Role | Symbol |
|-------|------|--------|
| **Kublai** | Squad Lead / Router — coordinates all incoming tasks | 🌙👁️⛓️‍💥 |
| **Möngke** | Research Specialist — deep research, fact-checking | 📜 |
| **Chagatai** | Content Specialist — writing, documentation | ✍️ |
| **Temüjin** | Development Specialist — code, architecture | 🔨 |
| **Jochi** | Data Analyst — patterns, analytics, security | 📊 |
| **Ögedei** | Operations Specialist — monitoring, deployment | ⚙️ |
| **Tolui** | Truth-Teller — verification, code review | ⚖️ |

## How It Works

1. **You send a message** to any agent (usually Kublai)
2. **Kublai classifies** the task and routes it to the appropriate specialist
3. **Specialist executes** using their domain expertise
4. **Results flow back** through Kublai for synthesis

## System Stack

| Component | Technology |
|-----------|------------|
| **Orchestration** | OpenClaw Gateway |
| **Memory** | Neo4j + Markdown files |
| **LLM** | Claude (Anthropic) |
| **Cron** | OpenClaw Cron Scheduler |
| **Platform** | macOS (darwin/arm64) |

## Project Structure

```
~/.openclaw/agents/main/
├── CLAUDE.md          # Kublai's operating instructions
├── AGENTS.md          # Agent routing table
├── SOUL.md            # Core beliefs
├── ARCHITECTURE.md    # Full system architecture
├── scripts/           # Python/Bash automation scripts
├── docs/              # Detailed documentation
├── logs/              # System logs and telemetry
└── memory/            # Persistent agent memory
```

## Documentation

- **[Full Architecture](docs/architecture.md)** — Complete system documentation
- **[State Management](docs/state-management-reference.md)** — How state flows through the system
- **[Completion Gate](docs/completion-gate.md)** — Task verification protocol
- **[Reflection Pipeline](docs/reflection-pipeline-reference.md)** — Hourly self-improvement cycle

## Quick Start

The Kurultai runs on a Mac Mini with automated cron jobs:
- **Tick (5min)** — System health check
- **Tock (30min)** — Agent telemetry collection
- **Kurultai (60min)** — Reflection and self-improvement

Tasks are queued in `~/.openclaw/agents/<agent>/tasks/` and executed by the respective agent.

## Support

For issues or questions, contact the system administrator or check the troubleshooting section in [architecture.md](docs/architecture.md#troubleshooting-guide).

---

**Version:** 2.1 | **Last Updated:** 2026-03-10 | **Maintained by:** Chagatai (Content Specialist)
