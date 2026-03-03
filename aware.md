# Kublai Architecture

## Overview
- **Platform**: OpenClaw Gateway
- **Memory**: File-based + Neo4j
- **Heartbeat**: 30 min

## Agents
| Agent | Role |
|-------|------|
| Kublai | Squad Lead / Router |
| Möngke | Research |
| Chagatai | Content |
| Temüjin | Development |
| Jochi | Analysis |
| Ögedei | Operations |

## Projects
| Project | Status | URL |
|---------|--------|-----|
| LLM Survivor | ✅ | llmsurvivor.kurult.ai |
| Parse | ✅ | parsethe.media |

## Memory
- **File**: ~/.openclaw/agents/main/
- **Neo4j**: bolt://localhost:7687

## Neo4j Schema
- Agent, Task, Memory, Decision, Escalation nodes

## Self-Awareness Protocol
1. Check docs.openclaw.ai
2. Review ARCHITECTURE.md (full architecture)
3. Update aware.md (token-optimized - loaded into context)
4. Update ARCHITECTURE.md (full version)