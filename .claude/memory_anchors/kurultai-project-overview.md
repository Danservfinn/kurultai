---
title: Kurultai Multi-Agent Orchestration Platform
link: kurultai-project-overview
type: memory_anchors
tags: [architecture, multi-agent, orchestration, kublai, openclaw]
ontological_relations:
  - relates_to: [[openclaw-gateway-architecture]]
  - relates_to: [[neo4j-operational-memory]]
  - builds_on: [[golden-horde-skill-system]]
uuid: 550e8400-e29b-41d4-a716-446655440001
created_at: 2026-02-07T12:00:00Z
updated_at: 2026-02-07T12:00:00Z
---

# Kurultai Multi-Agent Orchestration Platform

## Overview

Kurultai is a 6-agent multi-agent orchestration platform built on OpenClaw gateway messaging and Neo4j-backed operational memory. Named after the Kurultai (the council of Mongol/Turkic tribal leaders), the system enables collaborative AI agent workflows with task delegation, capability-based routing, and failure recovery.

## Agent Roster

| Agent | Role | Capabilities |
|-------|------|--------------|
| **Kublai** | Orchestrator | Delegation protocol, task classification, synthesis |
| **Möngke** | Researcher | Information search, summarization, extraction |
| **Chagatai** | Writer | Content creation, documentation, prose |
| **Temüjin** | Developer | Code implementation, technical architecture |
| **Jochi** | Analyst | Security review, code analysis, metrics |
| **Ögedei** | Operations | Failover, monitoring, recovery orchestration |

## Architecture Components

### OpenClaw Gateway (Port 18789)
- WebSocket-based agent-to-agent messaging
- Operator role authentication with token-based auth
- Bidirectional streaming for agent responses
- Built-in webchat control UI at `:18789/`

### Neo4j Operational Memory
- Task tracking with DAG-based dependencies
- Agent heartbeat monitoring (infra + functional tiers)
- Capability nodes for dynamic routing
- Vector embeddings for semantic search

### Delegation Protocol
- Complexity scoring system (0.0-1.0)
- Team size classification (1-8 agents)
- Capability-based agent selection
- Automatic task reassignment on failure

## Key Features

1. **Dynamic Team Composition**: Automatically scales team size based on task complexity
2. **Capability Acquisition**: `/learn` command for runtime skill acquisition
3. **Two-Tier Heartbeat**: Infrastructure (30s) + functional (90s) health monitoring
4. **Graceful Failover**: Ögedei activates when Kublai becomes unavailable
5. **Fallback Mode**: In-memory operations when Neo4j is unavailable

## External Integrations

- **Signal Messaging**: Via signal-cli-daemon
- **Authentik SSO**: Authentication and authorization
- **Railway Deployment**: Containerized service deployment
- **Caddy Reverse Proxy**: SSL termination and routing

## Project Status

Current development phase: v0.2 (82% complete)

See [[kurultai-testing-metrics-framework]] for testing infrastructure.
