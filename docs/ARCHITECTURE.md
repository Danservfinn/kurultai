# Kurultai System Architecture

**Version**: 2.0.2  
**Last Updated**: 2026-02-13  
**Status**: Production Ready  
**Classification**: Technical Architecture Document

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Overview](#2-system-overview)
3. [Agent Architecture](#3-agent-architecture)
4. [Task System](#4-task-system)
5. [Background Tasks (Detailed)](#5-background-tasks-detailed)
6. [v2.0 Major Enhancements](#6-v20-major-enhancements)
7. [Infrastructure](#7-infrastructure)
8. [Heartbeat System](#8-heartbeat-system)
9. [File Structure](#9-file-structure)
10. [Configuration](#10-configuration)
11. [Deployment Guide](#11-deployment-guide)
12. [Operational Runbook](#12-operational-runbook)
- [Appendix A: Security Layers](#appendix-a-security-layers)
- [Appendix B: Glossary](#appendix-b-glossary)
- [Appendix C: Related Documentation](#appendix-c-related-documentation)
- [Changelog](#changelog)

---

## 1. Executive Summary

### What Kurultai Is

Kurultai is a **6-agent multi-agent orchestration platform** designed for autonomous AI agent collaboration, task management, and capability acquisition. Named after the Kurultai (the council of Mongol/Turkic tribal leaders), the system enables multiple specialized AI agents to work together seamlessly through a shared Neo4j knowledge graph and OpenClaw gateway messaging infrastructure.

Kurultai represents a paradigm shift from single-agent AI assistants to coordinated multi-agent systems where:
- Each agent has specialized capabilities and responsibilities
- Agents communicate via cryptographically signed messages
- Shared operational memory persists across sessions in a graph database
- New capabilities can be learned autonomously through a secure pipeline
- Background tasks maintain system health and data quality automatically

### Key Capabilities

| Capability | Description |
|------------|-------------|
| **Multi-Agent Orchestration** | 6 specialized agents (Kublai, Möngke, Chagatai, Temüjin, Jochi, Ögedei) collaborate on complex tasks |
| **Unified Heartbeat System** | Single 5-minute cycle coordinates all background operations across agents |
| **Autonomous Capability Acquisition** | Agents can learn new skills through a 6-phase secure pipeline |
| **Graph-Based Memory** | Neo4j-powered operational memory with 30+ node types and vector search |
| **End-to-End Encrypted Messaging** | Signal Protocol integration for secure user communication |
| **Two-Tier Heartbeat Monitoring** | Infrastructure and functional heartbeats with automatic failover |
| **Dynamic Task Generation** | System creates tasks automatically based on identified gaps |
| **Predictive Health Monitoring** | ML-based prediction of system failures before they occur |
| **Agent Collaboration Protocol** | Complex tasks are decomposed and executed in parallel by multiple agents |

### Architecture Philosophy

Kurultai is built on several core architectural principles:

1. **Distributed Intelligence**: Intelligence emerges from agent collaboration, not monolithic models
2. **Explicit Memory**: All state is explicit in the graph; agents are stateless between invocations
3. **Defense in Depth**: 9-layer security architecture protecting against prompt injection, code execution, and impersonation
4. **Autonomous Improvement**: The system identifies its own gaps and creates tasks to address them
5. **Graceful Degradation**: Circuit breakers and fallback modes ensure service continuity
6. **Observability First**: Every operation is logged, measured, and traceable

---

## 2. System Overview

### High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                       USER LAYER                                        │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│   ┌──────────────┐        ┌──────────────┐        ┌──────────────┐                     │
│   │   Web UI     │        │   Signal     │        │   HTTP API   │                     │
│   │ (Next.js)    │        │  Integration │        │ (OpenClaw)   │                     │
│   │  Dashboard   │        │   Protocol   │        │   Gateway    │                     │
│   └──────┬───────┘        └──────┬───────┘        └──────┬───────┘                     │
│          │                       │                       │                             │
│          └───────────────────────┼───────────────────────┘                             │
│                                  │                                                      │
└──────────────────────────────────┼──────────────────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────────────────────┐
│                                  AUTHENTICATION LAYER                                   │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│   ┌────────────────────────────────────────────────────────────────────────────────┐   │
│   │                         Caddy Forward Auth Proxy                               │   │
│   │   ┌────────────────┐    ┌────────────────┐    ┌────────────────┐              │   │
│   │   │ Authentik      │    │ Token Check    │    │ Forward Auth   │              │   │
│   │   │ Bypass Routes  │    │ (Signal Link)  │    │ (All Other)    │              │   │
│   │   └────────────────┘    └────────────────┘    └────────────────┘              │   │
│   └────────────────────────────────────────────────────────────────────────────────┘   │
│                                  │                                                      │
│   ┌────────────────────────────────────────────────────────────────────────────────┐   │
│   │                         Authentik Identity Provider                            │   │
│   │   ┌────────────┐    ┌────────────┐    ┌────────────┐    ┌────────────┐       │   │
│   │   │  WebAuthn  │    │   OAuth    │    │   LDAP     │    │   Proxy    │       │   │
│   │   │  FIDO2     │    │  Provider  │    │  Bridge    │    │  Provider  │       │   │
│   │   └────────────┘    └────────────┘    └────────────┘    └────────────┘       │   │
│   └────────────────────────────────────────────────────────────────────────────────┘   │
│                                  │                                                      │
└──────────────────────────────────┼──────────────────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────────────────────┐
│                                  APPLICATION LAYER                                      │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│   ┌────────────────────────────────────────────────────────────────────────────────┐   │
│   │                        Moltbot (OpenClaw Gateway)                              │   │
│   │   ┌────────────┐    ┌────────────┐    ┌────────────┐    ┌────────────────┐    │   │
│   │   │   HTTP     │    │ WebSocket  │    │   Python   │    │   Signal CLI   │    │   │
│   │   │  Routes    │    │  Handler   │    │   Bridge   │    │   Daemon       │    │   │
│   │   └────────────┘    └────────────┘    └─────┬──────┘    └────────────────┘    │   │
│   └─────────────────────────────────────────────┼──────────────────────────────────┘   │
│                                                 │                                       │
│   ┌─────────────────────────────────────────────▼──────────────────────────────────┐   │
│   │                        Unified Heartbeat Engine (v2.0)                         │   │
│   │   ┌──────────┐    ┌────────────┐    ┌────────────┐    ┌────────────────┐      │   │
│   │   │Heartbeat │    │   Task     │    │   Agent    │    │   Predictive   │      │   │
│   │   │  Master  │    │  Registry  │    │  Spawner   │    │   Monitor      │      │   │
│   │   └──────────┘    └────────────┘    └────────────┘    └────────────────┘      │   │
│   └────────────────────────────────────────────────────────────────────────────────┘   │
│                                                 │                                       │
│   ┌─────────────────────────────────────────────▼──────────────────────────────────┐   │
│   │                             Kurultai Engine                                    │   │
│   │   ┌──────────┐    ┌────────────┐    ┌────────────┐    ┌────────────────┐      │   │
│   │   │   Task   │    │   Agent    │    │Capability  │    │   Dynamic      │      │   │
│   │   │ Router   │    │ Delegator  │    │  Registry  │    │   Task Gen     │      │   │
│   │   └──────────┘    └────────────┘    └────────────┘    └────────────────┘      │   │
│   └────────────────────────────────────────────────────────────────────────────────┘   │
│                                                 │                                       │
└─────────────────────────────────────────────────┼───────────────────────────────────────┘
                                                  │
┌─────────────────────────────────────────────────▼───────────────────────────────────────┐
│                                    AGENT LAYER                                          │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│   ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│   │                           Kublai (main/orchestrator)                            │   │
│   │   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌────────────────────────┐   │   │
│   │   │ Personal │    │Operational│    │   Task   │    │   Status Synthesis     │   │   │
│   │   │ Context  │    │  Memory   │    │  Router  │    │   & Escalation       │   │   │
│   │   │ (Files)  │    │ (Neo4j)   │    │(Gateway) │    │   (Heartbeat)        │   │   │
│   │   └──────────┘    └──────────┘    └──────────┘    └────────────────────────┘   │   │
│   └───────────────────────────────┬─────────────────────────────────────────────────┘   │
│                                   │ via agentToAgent                                    │
│   ┌───────────┐  ┌───────────┐  ┌───┴────┐  ┌───────────┐  ┌───────────┐             │
│   │  Möngke   │  │  Chagatai  │  │Temüjin │  │   Jochi   │  │  Ögedei   │             │
│   │(Research) │  │  (Writer)  │  │  (Dev) │  │ (Analyst) │  │   (Ops)   │             │
│   └───────────┘  └───────────┘  └────────┘  └───────────┘  └───────────┘             │
│                                   │                                                    │
└───────────────────────────────────┼────────────────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼─────────────────────────────────────────────────────┐
│                                    MEMORY LAYER                                         │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│   ┌────────────────────────────────────────────────────────────────────────────────┐   │
│   │                          Neo4j 5 Community (Graph DB)                          │   │
│   │                                                                                │   │
│   │   ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────────────────┐  │   │
│   │   │   Agent    │  │   Task     │  │ Heartbeat  │  │   LearnedCapability    │  │   │
│   │   │   Nodes    │  │   Nodes    │  │   Cycle    │  │       Nodes            │  │   │
│   │   └────────────┘  └────────────┘  └────────────┘  └────────────────────────┘  │   │
│   │                                                                                │   │
│   │   ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────────────────┐  │   │
│   │   │ Capability │  │  Analysis  │  │  AgentKey  │  │      Research          │  │   │
│   │   │   Nodes    │  │   Nodes    │  │   Nodes    │  │       Nodes            │  │   │
│   │   └────────────┘  └────────────┘  └────────────┘  └────────────────────────┘  │   │
│   │                                                                                │   │
│   │   ┌────────────────────────┐  ┌────────────────────────┐                      │   │
│   │   │   Vector Index (384d)  │  │   MVS Scoring Tier     │                      │   │
│   │   │   (Similarity Search)  │  │   (HOT/WARM/COLD)      │                      │   │
│   │   └────────────────────────┘  └────────────────────────┘                      │   │
│   └────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### Component Interactions

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              Component Interaction Flow                                 │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│   USER REQUEST FLOW                                                                     │
│   ═════════════════                                                                     │
│                                                                                         │
│   1. User ──► Web UI/Signal ──► Caddy Proxy ──► Authentik (auth check)                 │
│                                                                                         │
│   2. Authenticated ──► Moltbot (OpenClaw Gateway) ──► Kublai (main agent)              │
│                                                                                         │
│   3. Kublai:                                                                            │
│      ├─ Read personal context from /data/workspace/souls/main/MEMORY.md                │
│      ├─ Query operational context from Neo4j                                           │
│      ├─ Sanitize PII via PIISanitizer                                                  │
│      ├─ Classify intent via CapabilityClassifier                                       │
│      └─ Route to specialist agent via agentToAgent                                     │
│                                                                                         │
│   4. Specialist Agent:                                                                  │
│      ├─ Claim task (status: in_progress)                                               │
│      ├─ Perform work                                                                   │
│      ├─ Store results in Neo4j                                                         │
│      └─ Notify Kublai via agentToAgent                                                 │
│                                                                                         │
│   5. Kublai ──► Synthesize response ──► User                                          │
│                                                                                         │
│   ──────────────────────────────────────────────────────────────────────────────────   │
│                                                                                         │
│   CAPABILITY LEARNING FLOW                                                              │
│   ═════════════════════════                                                             │
│                                                                                         │
│   1. User: "/learn how to send SMS messages"                                           │
│                                                                                         │
│   2. Kublai ──► CapabilityClassifier ──► Risk Assessment                               │
│      ├─ Rule-based classification (>0.85 confidence)                                   │
│      ├─ Semantic similarity via Neo4j vector index                                     │
│      └─ LLM fallback for ambiguous cases                                               │
│                                                                                         │
│   3. Security Check (PromptInjectionFilter) ──► Cost Pre-Authorization                 │
│                                                                                         │
│   4. Delegation:                                                                        │
│      ├─ Möngke: Research API documentation                                             │
│      ├─ Temüjin: Generate implementation code                                          │
│      └─ Jochi: Security scan + sandbox tests                                           │
│                                                                                         │
│   5. Registration: LearnedCapability node created in Neo4j                             │
│                                                                                         │
│   6. Authorization: CBAC grants capability to authorized agents                        │
│                                                                                         │
│   ──────────────────────────────────────────────────────────────────────────────────   │
│                                                                                         │
│   HEARTBEAT CYCLE FLOW                                                                  │
│   ═════════════════════                                                                 │
│                                                                                         │
│   Railway Cron (Every 5 min)                                                            │
│        │                                                                                │
│        ▼                                                                                │
│   heartbeat_master.py ──► Filter tasks by frequency predicate                          │
│        │                                                                                │
│        ▼                                                                                │
│   Execute due tasks with timeout (token-based)                                         │
│        │                                                                                │
│        ▼                                                                                │
│   Log results to Neo4j (HeartbeatCycle + TaskResult nodes)                             │
│        │                                                                                │
│        ▼                                                                                │
│   Create tickets for critical failures                                                 │
│        │                                                                                │
│        ▼                                                                                │
│   Cycle Complete                                                                        │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                    Data Flow Diagram                                    │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│   INPUT SOURCES                              PROCESSING LAYER          OUTPUT/TARGETS   │
│   ═════════════                              ════════════════          ═══════════════   │
│                                                                                         │
│   ┌─────────────┐                            ┌─────────────┐         ┌─────────────┐   │
│   │ User Messages│───────────────────────────▶│   Kublai    │────────▶│   Signal    │   │
│   └─────────────┘                            │  (Router)   │         │   Replies   │   │
│                                              └──────┬──────┘         └─────────────┘   │
│                                                     │                                   │
│   ┌─────────────┐                            ┌──────▼──────┐         ┌─────────────┐   │
│   │ Web UI      │───────────────────────────▶│  Specialist │────────▶│   Web UI    │   │
│   │ (Dashboard) │                            │   Agents    │         │  Updates    │   │
│   └─────────────┘                            └──────┬──────┘         └─────────────┘   │
│                                                     │                                   │
│   ┌─────────────┐                            ┌──────▼──────┐         ┌─────────────┐   │
│   │  Notion API │◄───────────────────────────│   Neo4j     │────────▶│   Notion    │   │
│   │  (Tasks)    │                            │  (Graph DB) │         │   Sync      │   │
│   └─────────────┘                            └──────┬──────┘         └─────────────┘   │
│                                                     │                                   │
│   ┌─────────────┐                            ┌──────▼──────┐         ┌─────────────┐   │
│   │ External    │───────────────────────────▶│  Möngke     │────────▶│   Research  │   │
│   │ APIs/Docs   │                            │  (Research) │         │   Nodes     │   │
│   └─────────────┘                            └─────────────┘         └─────────────┘   │
│                                                                                         │
│   DATA TYPES BY TIER:                                                                   │
│   ───────────────────                                                                   │
│                                                                                         │
│   HOT (High Access):     Task nodes, Agent heartbeats, Active conversations             │
│   WARM (Recent):         Completed tasks, Recent research, User preferences             │
│   COLD (Archive):        Old tasks, Historical data, Archived research                  │
│   TOMBSTONE:             Deleted nodes marked for cleanup                               │
│                                                                                         │
│   ACCESS PATTERNS:                                                                      │
│   ────────────────                                                                      │
│                                                                                         │
│   Read:  Personal context (Kublai only) ──► File system                                 │
│   Read:  Operational context ──► Neo4j (all agents)                                    │
│   Write: Task results ──► Neo4j (specialist agents)                                    │
│   Write: Personal updates ──► File system (Kublai only)                                │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Agent Architecture

### The Six Agents of Kurultai

Kurultai deploys six specialized agents, each with distinct roles, capabilities, and responsibilities. All agents communicate via cryptographically signed messages through the OpenClaw gateway.

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              Kurultai Agent Architecture                                │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│                              ┌─────────────────────┐                                   │
│                              │      KUBLAI         │                                   │
│                              │    (Main/Router)    │                                   │
│                              │    Orchestrator     │                                   │
│                              └──────────┬──────────┘                                   │
│                                         │ agentToAgent                                  │
│        ┌────────────────────────────────┼────────────────────────────────┐             │
│        │              │                 │                 │              │             │
│        ▼              ▼                 ▼                 ▼              ▼             │
│   ┌─────────┐   ┌──────────┐      ┌─────────┐      ┌─────────┐    ┌─────────┐         │
│   │ MÖNGKE  │   │ CHAGATAI │      │ TEMÜJIN │      │  JOCHI  │    │ ÖGEDEI  │         │
│   │Research │   │  Writer  │      │  Developer     │ Analyst │    │   Ops   │         │
│   └─────────┘   └──────────┘      └─────────┘      └─────────┘    └─────────┘         │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### Agent Profiles

#### Kublai (main) - The Orchestrator

| Attribute | Value |
|-----------|-------|
| **Name Origin** | Kublai Khan, founder of the Yuan Dynasty |
| **Role** | Central router and orchestrator |
| **Primary Responsibilities** | Task delegation, response synthesis, PII sanitization, user communication |
| **Special Access** | Personal context files, full agent roster, escalation authority |
| **Trust Level** | HIGH |
| **Heartbeat Tasks** | status_synthesis (5 min), weekly_reflection (7 days) |

**Capabilities:**
- Intent classification and routing
- PII detection and sanitization (3-layer: regex, LLM, tokenization)
- Task creation and assignment
- Cross-agent result synthesis
- Critical escalation handling
- Personal context management (file-based)

**Memory Access:**
- **Personal Tier**: Full read/write access to `/data/workspace/souls/main/` files
- **Operational Tier**: Full Neo4j access
- **Security**: Only agent with PII access; sanitizes before delegation

---

#### Möngke (researcher) - The Scholar

| Attribute | Value |
|-----------|-------|
| **Name Origin** | Möngke Khan, fourth Great Khan of the Mongol Empire |
| **Role** | Research and knowledge acquisition |
| **Primary Responsibilities** | Web search, API documentation extraction, knowledge synthesis, gap analysis |
| **Special Access** | External API integrations, research databases |
| **Trust Level** | MEDIUM |
| **Heartbeat Tasks** | knowledge_gap_analysis (24h), ordo_sacer_research (24h), ecosystem_intelligence (7 days) |

**Capabilities:**
- Brave Search API integration
- Web page content extraction
- API documentation parsing
- Knowledge graph enrichment
- Research note creation with embeddings
- Gap identification in knowledge base

**Research Output:**
```cypher
(:Research {
  id: string,
  title: string,
  findings: string,        // JSON-serialized
  sources: [string],
  reliability_score: float,
  embedding: [float],      // 384-dim vector
  agent: "researcher",
  created_at: datetime
})
```

---

#### Chagatai (writer) - The Scribe

| Attribute | Value |
|-----------|-------|
| **Name Origin** | Chagatai Khan, second son of Genghis Khan |
| **Role** | Content creation and documentation |
| **Primary Responsibilities** | Documentation, reports, communication, reflection consolidation |
| **Special Access** | Documentation templates, style guides |
| **Trust Level** | MEDIUM |
| **Heartbeat Tasks** | reflection_consolidation (30 min) |

**Capabilities:**
- Technical documentation generation
- Report writing and formatting
- Communication drafting
- Reflection consolidation and merging
- Content style consistency enforcement

---

#### Temüjin (developer) - The Builder

| Attribute | Value |
|-----------|-------|
| **Name Origin** | Temüjin (Genghis Khan), founder of the Mongol Empire |
| **Role** | Code generation and implementation |
| **Primary Responsibilities** | Tool implementation, code generation, test writing, backend fixes |
| **Special Access** | Code generation templates, sandbox execution |
| **Trust Level** | HIGH |
| **Heartbeat Tasks** | On-demand ticket processing (via task assignment) |

**Capabilities:**
- Python/TypeScript code generation
- Tool implementation from specifications
- Test case generation
- Backend issue remediation
- Sandboxed code execution

**Security Controls:**
- All generated code passes through Jochi's security scan
- Sandboxed execution with rlimits (CPU: 30s, RAM: 512MB)
- No network access during generation
- AST-based dangerous pattern detection

---

#### Jochi (analyst) - The Guardian

| Attribute | Value |
|-----------|-------|
| **Name Origin** | Jochi, eldest son of Genghis Khan |
| **Role** | Analysis, testing, and security |
| **Primary Responsibilities** | Code review, security analysis, test execution, memory curation |
| **Special Access** | Static analysis tools, security scanners |
| **Trust Level** | HIGH |
| **Heartbeat Tasks** | memory_curation_rapid (5 min), mvs_scoring_pass (15 min), smoke_tests (15 min), full_tests (60 min), vector_dedup (6h), deep_curation (6h) |

**Capabilities:**
- AST-based code analysis (tree-sitter)
- Security vulnerability detection (bandit, semgrep)
- Test suite execution and reporting
- Memory tier management (HOT/WARM/COLD)
- Vector deduplication
- System health monitoring

**Analysis Output:**
```cypher
(:Analysis {
  id: string,
  agent: "analyst",
  target_agent: string,    // Agent whose code is analyzed
  analysis_type: string,   // performance, security, correctness
  severity: string,        // low, medium, high, critical
  description: string,
  recommendations: string, // JSON-serialized
  status: string,          // open, in_progress, resolved
  created_at: datetime
})
```

---

#### Ögedei (ops) - The Steward

| Attribute | Value |
|-----------|-------|
| **Name Origin** | Ögedei Khan, third Great Khan, established Yam postal system |
| **Role** | Operations and infrastructure |
| **Primary Responsibilities** | Health monitoring, file consistency, Notion sync, failover management |
| **Special Access** | System metrics, infrastructure APIs |
| **Trust Level** | HIGH |
| **Heartbeat Tasks** | health_check (5 min), file_consistency (15 min), notion_sync (60 min) |

**Capabilities:**
- System health monitoring (CPU, memory, disk, Neo4j)
- File consistency verification across agents
- Notion bidirectional synchronization
- Failover protocol activation
- Cost monitoring and alerting
- Backup verification

**Failover Role:**
When Kublai fails 3 consecutive health checks, Ögedei automatically assumes the role of emergency router, redistributing pending tasks to available agents and alerting administrators.

---

### Agent Communication Protocol

All inter-agent communication uses cryptographically signed messages to prevent impersonation and ensure message integrity.

#### Message Structure

```json
{
  "message_id": "uuid-v4",
  "from_agent": "kublai",
  "to_agent": "researcher",
  "timestamp": "2026-02-10T19:46:00Z",
  "nonce": "random-128-bit-string",
  "payload": {
    "type": "task_assignment",
    "task_id": "task-uuid",
    "description": "Research Twilio SMS API",
    "priority": "high"
  },
  "signature": "hmac-sha256-signature"
}
```

#### Authentication Flow

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                           Agent Authentication Flow                                     │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│   Agent A wants to send message to Agent B                                              │
│                                                                                         │
│   1. Agent A retrieves signing key from Neo4j (:AgentKey)                               │
│                                                                                         │
│   2. Agent A constructs message with timestamp and nonce                                │
│      (nonce prevents replay attacks)                                                    │
│                                                                                         │
│   3. Agent A signs message:                                                             │
│      signature = HMAC_SHA256(key, message_id + from + to + timestamp + nonce + payload) │
│                                                                                         │
│   4. Agent A sends to OpenClaw Gateway:                                                 │
│      POST /agent/{target}/message                                                       │
│                                                                                         │
│   5. OpenClaw Gateway validates signature using Agent A's public key                    │
│                                                                                         │
│   6. Gateway forwards to Agent B if signature valid                                     │
│                                                                                         │
│   7. Agent B verifies:                                                                  │
│      - Signature is valid                                                               │
│      - Timestamp is within 5-minute window (prevents replay)                            │
│      - Nonce hasn't been seen before (deduplication)                                    │
│                                                                                         │
│   8. Agent B processes message                                                          │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

#### Key Management

```cypher
// Agent signing keys stored in Neo4j
(:AgentKey {
  id: string,
  agent_id: string,
  key_hash: string,        // SHA256 hash for verification
  public_key: string,      // For signature verification
  created_at: datetime,
  expires_at: datetime,    // 90-day rotation
  is_active: boolean
})

// Relationship
(:Agent)-[:HAS_KEY]->(:AgentKey)
```

**Key Rotation Policy:**
- Keys expire after 90 days
- New keys generated 7 days before expiration
- Grace period of 14 days for old key acceptance
- Emergency rotation capability for compromised keys

---

## 4. Task System

### TASK_REGISTRY Structure

The task system is built around a unified registry that defines all background tasks, their frequencies, token budgets, and assigned agents.

```python
@dataclass
class HeartbeatTask:
    """A task that runs on heartbeat."""
    name: str                    # Task identifier (unique per agent)
    agent: str                   # Agent owner: kublai, jochi, chagatai, mongke, temujin, ogedei
    frequency_minutes: int       # 5, 15, 60, 360, 1440, 10080
    max_tokens: int              # Token budget for this task
    handler: Callable            # Async function(driver) -> result
    description: str             # Human-readable description
    enabled: bool = True         # Can be disabled per task
```

### Task Scheduling and Execution

Tasks are scheduled using a frequency predicate system where each task defines how often it should run:

```python
def should_run(self, cycle_count: int) -> bool:
    """Determine if task should run this cycle."""
    if not self.enabled:
        return False
    # Cycle runs every 5 minutes
    # Task runs when: cycle_count % (frequency_minutes // 5) == 0
    return cycle_count % (self.frequency_minutes // 5) == 0
```

**Example Schedules:**
| Frequency | Cycles Between Runs | Times per Day |
|-----------|---------------------|---------------|
| 5 min | 1 | 288 |
| 15 min | 3 | 96 |
| 60 min | 12 | 24 |
| 6 hours | 72 | 4 |
| 24 hours | 288 | 1 |
| 7 days | 2016 | 0.14 |

### Token Budgeting

Each task has an associated token budget to control API costs:

```
Total Budget per Cycle:
├── 5-min tasks:    ~650 tokens
├── 15-min tasks:   ~1,000 tokens
├── 30-min tasks:   ~500 tokens
├── 60-min tasks:   ~2,300 tokens
├── 6-hour tasks:   ~2,000 tokens
├── 24-hour tasks:  ~1,800 tokens
└── 7-day tasks:    ~2,000 tokens

Peak Usage (all align): ~8,250 tokens per cycle
Daily Average:          ~1,500 tokens per cycle
Monthly Projection:     ~135,000 tokens
```

### Complete Task Listing (15 Tasks)

| # | Task Name | Agent | Frequency | Budget | Status |
|---|-----------|-------|-----------|--------|--------|
| 1 | health_check | Ögedei | 5 min | 150 | ✅ Active |
| 2 | file_consistency | Ögedei | 15 min | 200 | ✅ Active |
| 3 | memory_curation_rapid | Jochi | 5 min | 300 | ✅ Active |
| 4 | mvs_scoring_pass | Jochi | 15 min | 400 | ✅ Active |
| 5 | smoke_tests | Jochi | 15 min | 800 | ✅ Active |
| 6 | full_tests | Jochi | 60 min | 1,500 | ✅ Active |
| 7 | vector_dedup | Jochi | 6 hours | 800 | ✅ Active |
| 8 | deep_curation | Jochi | 6 hours | 2,000 | ✅ Active |
| 9 | reflection_consolidation | Chagatai | 30 min | 500 | ✅ Active |
| 10 | knowledge_gap_analysis | Möngke | 24 hours | 600 | ✅ Active |
| 11 | ordo_sacer_research | Möngke | 24 hours | 1,200 | ✅ Active |
| 12 | ecosystem_intelligence | Möngke | 7 days | 2,000 | ✅ Active |
| 13 | status_synthesis | Kublai | 5 min | 200 | ✅ Active |
| 14 | weekly_reflection | Kublai | 7 days | 1,000 | ✅ Active |
| 15 | notion_sync | System | 60 min | 800 | ✅ Active |

---

## 5. Background Tasks (Detailed)

### Ögedei (Ops) Tasks

#### health_check (5 minutes, 150 tokens)

**Purpose:** Comprehensive system health monitoring across all infrastructure components.

**Monitored Components:**
- System metrics (CPU, memory, disk, load average)
- Neo4j connectivity and query performance
- Agent heartbeat staleness detection
- File system accessibility
- Critical service availability

**Implementation:**
```python
def health_check(driver) -> Dict:
    health_data = {
        'timestamp': datetime.now().isoformat(),
        'system': {},      # CPU, memory, disk metrics
        'neo4j': {},       # Connection, version, node counts
        'agents': [],      # Per-agent health status
        'issues': [],      # Detected issues
        'status': 'success'
    }
    
    # Check thresholds
    if cpu_percent > 90:
        health_data['issues'].append(f"CPU critical: {cpu_percent}%")
        health_data['status'] = 'critical'
    
    # Check agent heartbeats
    stale_agents = check_heartbeat_staleness(driver, threshold=120)
    if stale_agents:
        health_data['issues'].append(f"Stale agents: {stale_agents}")
```

**Alert Thresholds:**
| Metric | Warning | Critical |
|--------|---------|----------|
| CPU | >70% | >90% |
| Memory | >80% | >90% |
| Disk | >80% | >90% |
| Agent Heartbeat | >90s stale | >120s stale |

---

#### file_consistency (15 minutes, 200 tokens)

**Purpose:** Verify file consistency across agent workspaces and detect corruption or missing files.

**Checks Performed:**
- SOUL.md existence for all 6 agents
- File hash verification for integrity
- Orphaned file detection (files not referenced in Neo4j)
- Critical system file verification
- Cross-reference validation

**Implementation:**
```python
def file_consistency(driver) -> Dict:
    issues = []
    hashes = {}
    
    # Check agent SOUL.md files
    for agent in ['main', 'researcher', 'writer', 'developer', 'analyst', 'ops']:
        soul_path = f"/data/workspace/souls/{agent}/SOUL.md"
        if not os.path.exists(soul_path):
            issues.append(f"Missing SOUL.md: {agent}")
        else:
            # Calculate MD5 hash
            with open(soul_path, 'rb') as f:
                hashes[f"{agent}/SOUL.md"] = hashlib.md5(f.read()).hexdigest()
    
    # Check Neo4j file references
    neo4j_files = get_all_file_references(driver)
    missing_files = [f for f in neo4j_files if not os.path.exists(f)]
```

---

### Jochi (Analyst) Tasks

#### memory_curation_rapid (5 minutes, 300 tokens)

**Purpose:** Rapid memory maintenance enforcing token budgets and cleaning transient data.

**Operations:**
- Delete notifications older than 12 hours
- Clean session contexts older than 24 hours
- Check token budgets by tier (HOT/WARM/COLD)
- Flag oversized nodes exceeding tier limits
- Remove old temporary files

**Safety Rules (NEVER delete):**
- Agent nodes
- Active tasks (pending/in_progress)
- High-confidence beliefs (>= 0.9)
- Entries < 24 hours old
- SystemConfig, AgentKey, Migration nodes

**Token Budgets by Tier:**
| Tier | Target Tokens | Max Nodes |
|------|---------------|-----------|
| HOT | 1,600 | Most recent |
| WARM | 400 | Recent 7 days |
| COLD | 200 | Archive |

---

#### mvs_scoring_pass (15 minutes, 400 tokens)

**Purpose:** Recalculate MVS (Memory Value Score) for entries to optimize tier placement.

**MVS Formula:**
```
MVS = (access_count_7d * 0.4) + (confidence * 0.3) + (relationship_count * 0.2) + (recency * 0.1)
```

**Tier Assignment:**
| MVS Range | Tier | Description |
|-----------|------|-------------|
| 0.7 - 1.0 | HOT | Frequently accessed, high confidence |
| 0.4 - 0.7 | WARM | Moderately accessed |
| 0.0 - 0.4 | COLD | Rarely accessed, archive candidate |

**Schema Migration:**
The task includes automatic schema migration to add missing properties:
```cypher
MATCH (n) WHERE n.access_count_7d IS NULL SET n.access_count_7d = 0;
MATCH (n) WHERE n.confidence IS NULL SET n.confidence = 0.5;
MATCH (n) WHERE n.tier IS NULL SET n.tier = 'WARM';
```

---

#### smoke_tests (15 minutes, 800 tokens)

**Purpose:** Quick smoke tests for critical system components.

**Test Coverage:**
1. Neo4j connectivity (`RETURN 1`)
2. Basic Cypher query execution
3. Agent node structure validation
4. File system read/write access
5. Python dependency availability
6. Vector index existence (if configured)

**Execution:**
```python
def smoke_tests(driver) -> Dict:
    tests_run = 0
    failures = []
    
    # Test 1: Neo4j connectivity
    try:
        result = session.run('RETURN 1 as test')
        assert result.single()['test'] == 1
        tests_run += 1
    except Exception as e:
        failures.append(f"Neo4j: {e}")
    
    # Additional tests...
    
    return {
        'tests_run': tests_run,
        'tests_total': 6,
        'failures': len(failures),
        'status': 'success' if not failures else 'warning'
    }
```

---

#### full_tests (60 minutes, 1,500 tokens)

**Purpose:** Comprehensive test suite execution with reporting and automatic ticket creation.

**Test Phases:**
1. **Unit Tests**: pytest execution with coverage
2. **Integration Tests**: Cross-service workflows
3. **Neo4j Tests**: Graph-specific operations
4. **Security Tests**: Vulnerability scanning

**Ticket Creation:**
Critical failures automatically create tickets:
```python
if finding.get("severity") == "critical":
    tm.create_ticket(
        title=finding.get("title"),
        description=finding.get("description"),
        severity="critical",
        assign_to="temüjin" if code_related else "ögedei"
    )
```

---

#### vector_dedup (6 hours, 800 tokens)

**Purpose:** Near-duplicate detection via content similarity and embedding comparison.

**Detection Methods:**
1. Exact content match (same content, multiple nodes)
2. Title similarity (identical titles)
3. Embedding cosine similarity (>0.95)

**Output:**
- Creates `DuplicateReview` nodes for manual review
- Lists potential merges with confidence scores
- Never auto-merges (human decision required)

---

#### deep_curation (6 hours, 2,000 tokens)

**Purpose:** Deep memory curation including orphan deletion and tombstone purging.

**Operations:**
1. Delete orphaned nodes (no relationships, tombstoned)
2. Purge old tombstones (>30 days)
3. Remove stale relationships (>90 days)
4. Archive COLD tier nodes (>60 days)

**Safety Limits:**
- Maximum 100 nodes deleted per operation
- Archival before deletion for COLD tier
- Audit trail maintained in Neo4j

---

### Chagatai (Writer) Tasks

#### reflection_consolidation (30 minutes, 500 tokens)

**Purpose:** Consolidate agent reflections when system is idle.

**Idle Detection:**
```cypher
MATCH (t:Task)
WHERE t.status IN ['pending', 'in_progress']
  AND t.priority IN ['high', 'critical']
RETURN count(t) as urgent_tasks
```

**Consolidation Actions:**
- Link related reflections by topic
- Merge superseded reflections
- Create weekly reflection summaries
- Archive old reflections (>30 days)

---

### Möngke (Researcher) Tasks

#### knowledge_gap_analysis (24 hours, 600 tokens)

**Purpose:** Identify knowledge gaps across the system and generate research recommendations.

**Gap Types Detected:**
1. **Incomplete Tasks**: Pending/in_progress with no recent activity (>7 days)
2. **Missing Documentation**: Concepts with <100 chars of documentation
3. **Sparse Topics**: Topics with <3 relationships
4. **Orphaned Concepts**: Nodes with no relationships

**Output:**
```python
{
    'total_gaps_identified': 47,
    'gaps': {
        'incomplete_tasks': [...],
        'missing_documentation': [...],
        'sparse_topics': [...],
        'orphaned_concepts': [...]
    },
    'research_recommendations': [
        {'topic': 'X', 'priority': 'high', 'action': 'research_and_connect'}
    ]
}
```

---

#### ordo_sacer_research (24 hours, 1,200 tokens)

**Purpose:** Specialized research for Ordo Sacer Astaci domain knowledge.

**Scope:**
- Esoteric concept research
- Specialized knowledge base maintenance
- Domain-specific documentation

**Note:** This is a specialized task with placeholder implementation for domain-specific research logic.

---

#### ecosystem_intelligence (7 days, 2,000 tokens)

**Purpose:** Track OpenClaw/Clawdbot/Moltbot ecosystem compatibility and updates.

**Tracked Components:**
- Kurultai version and status
- Integration health (Neo4j, Signal, Notion)
- External API compatibility
- Dependency version tracking

---

### Kublai (Main) Tasks

#### status_synthesis (5 minutes, 200 tokens)

**Purpose:** Aggregate agent status and escalate critical issues.

**Actions:**
1. Query all agent heartbeats from Neo4j
2. Identify stale or failed agents
3. Check for critical threshold breaches
4. Escalate via Signal if needed
5. Update system status dashboard

**Escalation Criteria:**
- Multiple consecutive heartbeat failures
- Failover protocol activation
- Critical security issues
- Resource exhaustion

---

#### weekly_reflection (7 days, 1,000 tokens)

**Purpose:** Generate comprehensive weekly system reflection.

**Content:**
- Task completion summary
- Agent performance metrics
- Knowledge gaps identified
- System health trends
- Recommendations for next week

---

### System Tasks

#### notion_sync (60 minutes, 800 tokens)

**Purpose:** Bidirectional synchronization between Notion and Neo4j.

**Sync Direction:**
- **Pull**: Notion tasks → Neo4j Task nodes
- **Push**: Neo4j updates → Notion

**Synced Entities:**
- Tasks (title, status, assignee, priority)
- Projects (name, status, deadline)
- Research notes (title, content, tags)

**Conflict Resolution:**
- Neo4j timestamp wins on conflict
- Manual review for simultaneous edits

---

## 6. v2.0 Major Enhancements

### Dynamic Task Generator

**Concept:** Instead of only executing predefined tasks, the system analyzes its own state and creates new tasks automatically.

**Triggers:**
```python
class TaskGenerator:
    def check_and_create_tasks(self):
        # Knowledge gaps → Research tasks
        for gap in self.find_knowledge_gaps():
            self.create_task(
                title=f"Research: {gap.topic}",
                agent="Möngke",
                priority=gap.urgency,
                source="auto-generated"
            )
        
        # Code issues → Development tasks
        for issue in self.find_code_issues():
            self.create_task(
                title=f"Fix: {issue.description}",
                agent="Temüjin",
                priority=issue.severity,
                source="auto-generated"
            )
```

**Generated Task Types:**
- Research tasks (from knowledge gaps)
- Development tasks (from code issues)
- Documentation tasks (from doc gaps)
- Optimization tasks (from performance issues)

---

### Agent Collaboration Protocol

**Concept:** Complex tasks are automatically decomposed and executed in parallel by multiple agents.

**Workflow:**
```python
class CollaborationOrchestrator:
    def handle_complex_request(self, request):
        # Analyze complexity
        complexity = self.assess_complexity(request)
        
        if complexity == 'simple':
            return self.route_to_single_agent(request)
        
        # Decompose into sub-tasks
        subtasks = self.decompose(request)
        # Example: [
        #   {'agent': 'Temüjin', 'task': 'implement_core'},
        #   {'agent': 'Jochi', 'task': 'write_tests'},
        #   {'agent': 'Chagatai', 'task': 'write_docs'}
        # ]
        
        # Parallel execution
        with ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(self.execute_subtask, task): task
                for task in subtasks
            }
            results = {futures[f]: f.result() for f in futures}
        
        # Synthesize results
        return self.synthesize(results)
```

---

### Predictive Health Monitoring

**Concept:** ML-based prediction of system failures before they occur.

**Prediction Models:**
```python
class PredictiveMonitor:
    def analyze_patterns(self):
        # Restart pattern detection
        restarts = self.get_restart_history(days=30)
        if pattern.predicts_failure_within(hours=24):
            self.preemptive_restart()
        
        # Config lock frequency
        locks = self.get_lock_history()
        if locks.frequency_increasing():
            self.investigate_lock_cause()
        
        # Error rate trends
        errors = self.get_error_trends()
        if errors.trend == 'increasing':
            self.alert_escalate("Error rate increasing")
```

**Predictions:**
- Signal daemon restart patterns
- Config lock frequency
- Error rate trends
- API quota exhaustion
- Disk space exhaustion

---

### Intelligent Workspace Curation

**Concept:** AI-powered organization of Notion workspace based on activity patterns.

**Features:**
```python
class WorkspaceCurator:
    def curate(self):
        # Auto-name untitled pages
        for page in self.get_untitled_pages():
            preview = self.extract_preview(page)
            page.rename(self.generate_title(preview))
        
        # Archive inactive databases
        for db in self.get_empty_databases(inactive_days=30):
            db.archive()
        
        # Suggest page consolidations
        duplicates = self.find_similar_pages()
        for group in duplicates:
            self.suggest_merge(group)
```

---

### Context-Aware Router

**Concept:** Route tasks based on conversation context, not just type.

**Enhanced Routing:**
```python
def route_request(request, context):
    # Keyword-based routing
    if 'security' in context.keywords:
        if 'urgent' in context.priority:
            return 'Jochi'  # Security analyst
    
    if 'performance' in context.keywords:
        return 'Jochi'  # Performance analysis
    
    if 'database' in context.keywords:
        return 'Temüjin'  # Database expert
    
    # Sentiment-based routing
    if context.sentiment == 'frustrated':
        return 'Kublai'  # Delicate handling
    
    # History-based routing
    if context.user_id in agent_specializations:
        return agent_specializations[context.user_id]
    
    # Default to type-based routing
    return route_by_type(request.deliverable_type)
```

---

## 7. Infrastructure

### Railway Deployment Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              Railway Deployment Layout                                  │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │                           Railway Project: kurultai                               │   │
│  │                                                                                   │   │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                 │   │
│  │  │   moltbot       │  │  skill-sync     │  │  neo4j          │                 │   │
│  │  │   (gateway)     │  │  (worker)       │  │  (database)     │                 │   │
│  │  │   Port: 18789   │  │  Port: 3000     │  │  Port: 7687     │                 │   │
│  │  │   CPU: 1        │  │  CPU: 0.5       │  │  CPU: 1         │                 │   │
│  │  │   RAM: 2Gi      │  │  RAM: 512Mi     │  │  RAM: 2Gi       │                 │   │
│  │  └────────┬────────┘  └─────────────────┘  └─────────────────┘                 │   │
│  │           │                                                                      │   │
│  │  ┌────────┴─────────────────────────────────────────────────────────────────┐   │   │
│  │  │                         Authentik Stack                                    │   │   │
│  │  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │   │   │
│  │  │  │ authentik-  │  │ authentik-  │  │ authentik-  │  │ authentik-  │     │   │   │
│  │  │  │ server      │  │ worker      │  │ proxy       │  │ db          │     │   │   │
│  │  │  │ Port: 9000  │  │ (bg tasks)  │  │ Port: 8080  │  │ Port: 5432  │     │   │   │
│  │  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘     │   │   │
│  │  └──────────────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                                   │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### Service Configuration

| Service | Image | Port | Health Check | Resources |
|---------|-------|------|--------------|-----------|
| moltbot | Custom (Node+Python+Java) | 18789, 8082 | /health | 1 CPU, 2Gi RAM |
| skill-sync-service | Custom (Node) | 3000 | /health | 0.5 CPU, 512Mi RAM |
| neo4j | neo4j:5-community | 7474, 7687 | / | 1 CPU, 2Gi RAM |
| authentik-server | ghcr.io/goauthentik/server:2025.10.0 | 9000, 9443 | /-/health/ready/ | 0.5 CPU, 1Gi RAM |
| authentik-worker | Same as server | — | — | 0.25 CPU, 512Mi RAM |
| authentik-proxy | Caddy 2 Alpine | 8080 | /health | 0.25 CPU, 256Mi RAM |
| authentik-db | postgres:15-alpine | 5432 | pg_isready | 0.5 CPU, 512Mi RAM |

---

### Neo4j Database Schema

#### Core Node Types

```cypher
// Agent - Represents an autonomous agent
(:Agent {
  id: string,              // Unique agent ID
  name: string,            // Display name
  type: string,            // orchestrator, specialist
  trust_level: string,     // LOW, MEDIUM, HIGH
  status: string,          // active, inactive
  infra_heartbeat: datetime,
  last_heartbeat: datetime,
  created_at: datetime
})

// Task - Unit of work
(:Task {
  id: string,
  description: string,
  status: string,          // pending, in_progress, completed, failed
  assigned_to: string,     // Agent ID
  created_by: string,      // Agent ID
  priority: string,        // low, normal, high, critical
  task_type: string,       // research, development, analysis, writing, ops
  metadata: map,
  created_at: datetime,
  completed_at: datetime
})

// HeartbeatCycle - Execution record
(:HeartbeatCycle {
  id: string,
  cycle_number: int,
  started_at: datetime,
  completed_at: datetime,
  tasks_run: int,
  tasks_succeeded: int,
  tasks_failed: int,
  total_tokens: int,
  duration_seconds: float
})

// TaskResult - Individual task execution
(:TaskResult {
  agent: string,
  task_name: string,
  status: string,          // success, error, timeout
  started_at: datetime,
  completed_at: datetime,
  summary: string,
  error_message: string
})

// Research - Knowledge gathered
(:Research {
  id: string,
  title: string,
  findings: string,
  sources: [string],
  reliability_score: float,
  embedding: [float],      // 384-dim vector
  agent: string,
  created_at: datetime
})

// LearnedCapability - Acquired capabilities
(:LearnedCapability {
  id: string,
  name: string,
  agent: string,
  tool_path: string,
  version: string,
  learned_at: datetime,
  cost: float,
  mastery_score: float,
  risk_level: string,      // LOW, MEDIUM, HIGH
  signature: string,
  required_capabilities: [string],
  min_trust_level: string
})

// Capability - CBAC definitions
(:Capability {
  id: string,
  name: string,
  description: string,
  risk_level: string,
  created_at: datetime
})

// AgentKey - Authentication keys
(:AgentKey {
  id: string,
  key_hash: string,
  created_at: datetime,
  expires_at: datetime,
  is_active: boolean
})

// Analysis - Code/security findings
(:Analysis {
  id: string,
  agent: string,
  target_agent: string,
  analysis_type: string,
  severity: string,
  description: string,
  recommendations: string,
  status: string,
  created_at: datetime
})
```

#### Key Relationships

```cypher
// Task assignments
(Agent)-[:ASSIGNED_TO]->(Task)
(Agent)-[:CREATED]->(Task)

// Heartbeat results
(HeartbeatCycle)-[:HAS_RESULT]->(TaskResult)

// Research authorship
(Agent)-[:CREATED]->(Research)

// Agent knowledge
(Agent)-[:HAS_LEARNED_CAPABILITY]->(LearnedCapability)

// CBAC grants
(Agent)-[:HAS_CAPABILITY {granted_at: datetime, expires_at: datetime}]->(Capability)

// Agent authentication
(Agent)-[:HAS_KEY]->(AgentKey)

// Analysis workflow
(Agent {id: 'analyst'})-[:CREATED]->(Analysis)
(Analysis)-[:SUGGESTS_CAPABILITY]->(LearnedCapability)
(Agent {id: 'developer'})-[:ADDRESSES]->(Analysis)

// Task dependencies
(Task)-[:DEPENDS_ON]->(Task)
(Task)-[:ENABLES]->(Task)
```

#### Required Indexes

```cypher
CREATE INDEX heartbeat_cycle_number IF NOT EXISTS
FOR (hc:HeartbeatCycle) ON (hc.cycle_number);

CREATE INDEX task_result_agent IF NOT EXISTS
FOR (tr:TaskResult) ON (tr.agent);

CREATE INDEX task_result_status IF NOT EXISTS
FOR (tr:TaskResult) ON (tr.status);

CREATE INDEX agent_status IF NOT EXISTS
FOR (a:Agent) ON (a.status);

CREATE INDEX task_status IF NOT EXISTS
FOR (t:Task) ON (t.status);

CREATE INDEX research_embedding IF NOT EXISTS
FOR (r:Research) ON (r.embedding);
```

---

### OpenClaw Gateway

The OpenClaw Gateway provides the HTTP/WebSocket interface for agent communication and external integrations.

**Key Endpoints:**
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| /health | GET | None | Service health check |
| /api/auth/me | GET | Authentik | Current user info |
| /api/learn | POST | Authentik | Learn new capability |
| /agent/{id}/message | POST | Gateway token | Send message to agent |
| /api/tasks | GET/POST | Authentik | Task management |
| /api/agents | GET | Authentik | List agents |
| /setup/api/signal-link | POST | X-Signal-Token | Signal device linking |

**Agent Message Routing:**
```javascript
// Gateway routes messages to appropriate agent handler
app.post('/agent/:agentId/message', async (req, res) => {
    const { agentId } = req.params;
    const message = req.body;
    
    // Verify HMAC signature
    if (!verifySignature(message)) {
        return res.status(401).json({ error: 'Invalid signature' });
    }
    
    // Route to agent handler
    const agent = await getAgent(agentId);
    const response = await agent.handleMessage(message);
    
    res.json(response);
});
```

---

### Signal Integration

**Architecture:**
```
User Signal App ──► Signal Servers ──► signal-cli daemon ──► OpenClaw Gateway
                                          (localhost:8081)
```

**Security:**
- signal-cli binds to localhost only
- E2EE via Signal Protocol
- Allowlisted sender phone numbers
- No message content logged

**Configuration:**
```bash
SIGNAL_ACCOUNT=+1234567890
SIGNAL_CLI_PATH=/usr/local/bin/signal-cli
SIGNAL_DATA_DIR=/data/.signal
```

---

### Notion Integration

**Sync Scope:**
- Tasks (bidirectional)
- Projects (bidirectional)
- Research notes (Neo4j → Notion)

**Configuration:**
```bash
NOTION_API_TOKEN=secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
NOTION_DATABASE_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

**Rate Limiting:**
- 3 requests per second
- Batch operations preferred
- Exponential backoff on 429

---

## 8. Heartbeat System

### 5-Minute Unified Heartbeat

The unified heartbeat consolidates all background operations into a single 5-minute cycle, coordinating **14 distinct tasks** across 6 agents with integrated Memory Value Scoring (MVS) for intelligent data retention.

**Version**: 0.4 (synced with HEARTBEAT.md)  
**Cycle Interval**: 5 minutes  
**Peak Token Usage**: ~8,650 tokens/cycle (daily alignment)  
**Average Token Usage**: ~1,650 tokens/cycle

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              Unified Heartbeat Cycle                                    │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│   Railway Cron: */5 * * * *                                                             │
│        │                                                                                │
│        ▼                                                                                │
│   ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│   │                           Cycle Execution                                         │   │
│   │                                                                                   │   │
│   │   Phase 1: Filter Tasks by Frequency Predicate                                    │   │
│   │   ├─ Check which tasks are due (5min, 15min, 30min, 60min, 6hr, 24hr, 7d)        │   │
│   │   └─ Skip disabled tasks                                                          │   │
│   │                                                                                   │   │
│   │   Phase 2: Execute Due Tasks (Token-Budgeted)                                     │   │
│   │   ├─ Run each task with timeout (default 60s)                                     │   │
│   │   ├─ Enforce per-task token budgets                                               │   │
│   │   └─ Collect results (success/error/timeout)                                      │   │
│   │                                                                                   │   │
│   │   Phase 3: MVS Scoring & Curation (Jochi)                                         │   │
│   │   ├─ Recalculate Memory Value Scores                                              │   │
│   │   ├─ Promote/demote entries between HOT/WARM/COLD tiers                           │   │
│   │   └─ Archive or prune low-value data                                              │   │
│   │                                                                                   │   │
│   │   Phase 4: Logging & Escalation                                                   │   │
│   │   ├─ Log results to Neo4j (HeartbeatCycle + TaskResult nodes)                     │   │
│   │   ├─ Create tickets for critical failures                                         │   │
│   │   └─ Send alerts if thresholds breached                                           │   │
│   │                                                                                   │   │
│   └───────────────────────────────────────────────────────────────────────────────────┘   │
│        │                                                                                │
│        ▼                                                                                │
│   Wait 5 minutes ──► Repeat                                                            │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### Two-Tier Heartbeat Architecture

The system distinguishes between **infrastructure health** (gateway process alive) and **functional health** (agent actually processing work):

| Tier | Property | Written By | Threshold | Meaning |
|------|----------|------------|-----------|---------|
| **Infrastructure** | `Agent.infra_heartbeat` | Python sidecar (every 30s) | 120s (4 missed) | Gateway process alive |
| **Functional** | `Agent.last_heartbeat` | Agent activity (claim/complete) | 90s (3 missed) | Agent functionally working |

**Failover Logic**: Uses worst-case of both signals to avoid false positives from "up but stuck" agents.

### Agent Background Task Registry (14 Tasks)

| Agent | Task Name | Frequency | Token Budget | MVS Impact | Description |
|-------|-----------|-----------|--------------|------------|-------------|
| **Ögedei** | health_check | 5 min | 150 | — | Check Neo4j, agent heartbeats, disk space |
| **Ögedei** | file_consistency | 15 min | 200 | — | Verify file consistency across agent workspaces |
| **Jochi** | memory_curation_rapid | 5 min | 300 | Prunes low-MVS | Enforce token budgets, clean notifications |
| **Jochi** | mvs_scoring_pass | 15 min | 400 | Updates MVS | Recalculate Memory Value Scores |
| **Jochi** | smoke_tests | 15 min | 800 | — | Run quick smoke tests via test runner |
| **Jochi** | full_tests | 60 min | 1500 | — | Run full test suite with remediation |
| **Jochi** | vector_dedup | 6 hours | 800 | Merges duplicates | Near-duplicate detection via embeddings |
| **Jochi** | deep_curation | 6 hours | 2000 | Archives cold | Delete orphans, purge tombstones, archive COLD |
| **Chagatai** | reflection_consolidation | 30 min | 500 | Creates Synthesis | Consolidate reflections when system idle |
| **Möngke** | knowledge_gap_analysis | 24 hours | 600 | Identifies gaps | Identify sparse knowledge areas |
| **Möngke** | ordo_sacer_research | 24 hours | 1200 | Creates Research | Research esoteric concepts for Ordo Sacer Astaci |
| **Möngke** | ecosystem_intelligence | 7 days | 2000 | Tracks trends | Track OpenClaw/Clawdbot/Moltbot ecosystem |
| **Kublai** | status_synthesis | 5 min | 200 | — | Synthesize agent status, escalate critical issues |
| **Kublai** | weekly_reflection | 7 days | 1500 | Creates Proposals | Proactive architecture analysis |
| **System** | notion_sync | 60 min | 800 | — | Bidirectional Notion↔Neo4j task sync |

### Task Distribution by Frequency

```
Every 5 minutes (3 tasks, 650 tokens):
  - Ögedei: health_check (150)
  - Jochi: memory_curation_rapid (300)
  - Kublai: status_synthesis (200)

Every 15 minutes (3 tasks, 1400 tokens):
  - Ögedei: file_consistency (200)
  - Jochi: smoke_tests (800)
  - Jochi: mvs_scoring_pass (400)

Every 30 minutes (1 task, 500 tokens):
  - Chagatai: reflection_consolidation (500)

Every 60 minutes (2 tasks, 2300 tokens):
  - Jochi: full_tests (1500)
  - System: notion_sync (800)

Every 6 hours (2 tasks, 2800 tokens):
  - Jochi: vector_dedup (800)
  - Jochi: deep_curation (2000)

Every 24 hours (2 tasks, 1800 tokens):
  - Möngke: knowledge_gap_analysis (600)
  - Möngke: ordo_sacer_research (1200)

Every 7 days (2 tasks, 3500 tokens):
  - Möngke: ecosystem_intelligence (2000)
  - Kublai: weekly_reflection (1500)
```

### Memory Value Score (MVS) Integration

MVS determines data retention priority based on multiple factors:

```
MVS = (
    type_weight                           # 0.5 - 10.0
    + recency_bonus                       # 0.0 - 3.0 (exponential decay)
    + frequency_bonus                     # 0.0 - 2.0 (log-scaled access rate)
    + quality_bonus                       # 0.0 - 2.0 (confidence/severity)
    + centrality_bonus                    # 0.0 - 1.5 (relationship count)
    + cross_agent_bonus                   # 0.0 - 2.0 (multi-agent access)
    - bloat_penalty                       # 0.0 - 1.5 (tokens over target)
) * safety_multiplier                     # 1.0 normal, 100.0 protected
```

#### Type Weights

| Type | Weight | Half-Life |
|------|--------|-----------|
| Belief (active, conf > 0.7) | 10.0 | 180 days |
| Reflection | 8.0 | 90 days |
| Analysis | 7.0 | 60 days |
| Synthesis | 6.5 | 120 days |
| Recommendation | 5.0 | 30 days |
| CompressedContext | 4.0 | 90 days |
| Task (active) | 3.0 | N/A (protected) |
| MemoryEntry | 2.5 | 45 days |
| SessionContext | 1.5 | 1 day |
| Notification | 0.5 | 12 hours |

#### MVS Action Thresholds

| MVS Range | Curation Action |
|-----------|-----------------|
| >= 50.0 | KEEP (safety-protected) |
| >= 8.0 | KEEP |
| 5.0 - 8.0 | KEEP, flag for compression if bloated |
| 3.0 - 5.0 | IMPROVE (enrich metadata) or MERGE (if similar exists) |
| 1.5 - 3.0 | DEMOTE one tier |
| 0.5 - 1.5 | PRUNE (soft delete with 30-day tombstone) |
| < 0.5 | PRUNE (immediate for Notifications/Sessions) |

### Curation Tiers

| Tier | Token Budget | Purpose |
|------|--------------|---------|
| **HOT** | 1,600 tokens | In-memory, immediate access |
| **WARM** | 400 tokens | Lazy-loaded, 2s timeout |
| **COLD** | 200 tokens | On-demand, 5s timeout |
| **Archive** | — | File-based, manual query |

### Task Delegation

```python
# Autonomous delegation from Kublai to specialist agents
def delegate_pending_tasks(driver):
    pending = driver.query("""
        MATCH (t:Task)
        WHERE t.status = 'pending' AND t.assigned_to IS NOT NULL
        AND NOT EXISTS {
            MATCH (m:AgentMessage)
            WHERE m.task_id = t.id AND m.status = 'pending'
        }
        RETURN t.id as task_id, t.assigned_to as agent
    """)
    
    for task in pending:
        # Create AgentMessage for delegation
        create_agent_message(
            from_agent='kublai',
            to_agent=task['agent'],
            payload={
                'type': 'task_assignment',
                'task_id': task['task_id']
            }
        )
```

### Status Synthesis

```python
def status_synthesis(driver) -> Dict:
    """Aggregate agent status and escalate critical issues."""
    
    # Query all agent statuses
    agents = driver.query("""
        MATCH (a:Agent)
        RETURN a.name as name, a.status as status,
               a.infra_heartbeat as infra,
               a.last_heartbeat as func
    """)
    
    issues = []
    for agent in agents:
        # Check for stale heartbeats
        if agent['infra'] and (now - agent['infra']).seconds > 120:
            issues.append(f"{agent['name']}: infra stale")
        if agent['func'] and (now - agent['func']).seconds > 90:
            issues.append(f"{agent['name']}: functional stale")
    
    # Escalate if critical
    if len(issues) >= 3:
        send_alert(f"Multiple agent issues: {issues}")
    
    return {
        'agents_checked': len(agents),
        'issues_found': len(issues),
        'status': 'critical' if len(issues) >= 3 else 'warning' if issues else 'success'
    }
```

### Critical Escalation

**Escalation Criteria:**
| Condition | Severity | Action |
|-----------|----------|--------|
| 3+ agents with stale heartbeats | CRITICAL | Failover to Ögedei + Signal alert |
| 2 agents with stale heartbeats | HIGH | Signal alert + log investigation |
| 1 agent stale >5 min | MEDIUM | Retry delegation + log warning |
| Task failure rate >10% | HIGH | Create ticket + alert |
| Neo4j connection failure | CRITICAL | Fallback mode + immediate alert |
| Disk usage >90% | CRITICAL | Cleanup attempt + alert |

---

## 9. File Structure

### Complete Directory Tree

```
/data/workspace/souls/main/
│
├── AGENTS.md                          # Agent workspace guide
├── ARCHITECTURE.md                    # This document
├── BOOTSTRAP.md                       # Initial setup instructions
├── HEARTBEAT.md                       # Kublai heartbeat configuration
├── IDENTITY.md                        # Agent identity definition
├── MEMORY.md                          # Long-term memory (Kublai only)
├── README.md                          # Project overview
├── SOUL.md                            # Agent self-definition
├── TOOLS.md                           # Tool-specific notes
├── USER.md                            # User context
│
├── .env                               # Environment variables (gitignored)
├── .env.example                       # Environment template
├── railway.yml                        # Railway deployment config
├── railway.toml                       # Railway service config
├── requirements.txt                   # Python dependencies
├── pytest.ini                         # Test configuration
│
├── app/                               # Express.js application
│   ├── index.js                       # Main application entry
│   └── routes/                        # API route definitions
│       ├── health.js                  # Health check endpoints
│       ├── auth.js                    # Authentication routes
│       └── agents.js                  # Agent management routes
│
├── authentik-server/                  # Authentik server Dockerfile
│   └── Dockerfile
│
├── authentik-worker/                  # Authentik worker Dockerfile
│   └── Dockerfile
│
├── authentik-proxy/                   # Caddy reverse proxy
│   ├── Dockerfile
│   ├── Caddyfile
│   └── config/
│       └── proxy-provider.yaml
│
├── cli/                               # CLI tools
│   └── registry/
│       └── CLAUDE.md
│
├── docs/                              # Documentation
│   ├── ARCHITECTURE.md                # System architecture
│   ├── DETAILED_IMPLEMENTATION_PLAN.md
│   ├── GAP_ANALYSIS.md
│   ├── KURULTAI_IMPROVEMENT_PLAN.md
│   ├── plans/                         # Implementation plans
│   ├── architecture/                  # Architecture diagrams
│   ├── operations/                    # Runbooks
│   ├── security/                      # Security docs
│   └── testing/                       # Test plans
│
├── logs/                              # Application logs
│
├── memory/                            # Daily memory files
│   └── 2026-02-10.md
│
├── migrations/                        # Neo4j schema migrations
│   ├── migration_manager.py
│   ├── v1_initial_schema.py
│   ├── v2_kurultai_dependencies.py
│   └── v3_capability_acquisition.py
│
├── moltbot-railway-template/          # Main service container
│   ├── Dockerfile
│   ├── entrypoint.sh
│   ├── openclaw.json5
│   ├── src/
│   │   └── index.js
│   └── scripts/
│       ├── heartbeat_writer.py
│       ├── run_migrations.py
│       └── model_switcher.py
│
├── scripts/                           # Utility scripts
│   ├── sync-architecture-to-neo4j.js
│   ├── test-signal-integration.js
│   ├── run-cypher-migration.js
│   └── backup-authentik-db.sh
│
├── signal-cli-daemon/                 # Signal CLI configuration
│
├── signal-proxy/                      # Signal proxy service
│
├── skill-sync-service/                # GitHub skill sync
│   ├── Dockerfile
│   └── src/
│
├── skills/                            # Agent skills
│
├── src/                               # Source code
│   └── protocols/                     # Agent protocols
│       ├── delegation.py
│       ├── failover.py
│       └── security_audit.py
│
├── steppe-visualization/              # Next.js 3D dashboard
│   ├── app/
│   │   ├── page.tsx                   # Main visualization
│   │   ├── control-panel/             # System dashboard
│   │   ├── mission-control/           # Goal orchestration
│   │   └── api/                       # REST endpoints
│   └── components/
│       ├── agents/                    # Agent visualizations
│       └── scene/                     # 3D terrain
│
├── tests/                             # Test suites
│   ├── integration/                   # Integration tests
│   ├── security/                      # Security tests
│   ├── performance/                   # Performance tests
│   ├── chaos/                         # Chaos tests
│   └── e2e/                           # End-to-end tests
│
└── tools/                             # Agent tools
    ├── kurultai/                      # Core Kurultai framework
    │   ├── heartbeat_master.py        # Unified heartbeat
    │   ├── agent_tasks.py             # All 14 task implementations
    │   ├── agent_spawner.py           # Agent lifecycle management
    │   ├── capability_registry.py     # Capability management
    │   ├── curation_simple.py         # Memory curation
    │   ├── mvs_scorer.py              # MVS scoring
    │   ├── test_runner_orchestrator.py # Test execution
    │   ├── ticket_manager.py          # Ticket creation
    │   ├── topological_executor.py    # DAG execution
    │   ├── autonomous_orchestrator.py # Auto-delegation
    │   ├── autonomous_delegation.py   # Delegation logic
    │   ├── dynamic_task_generator.py  # Task generation
    │   ├── meta_learning_engine.py    # Meta-learning
    │   ├── reflection_trigger.py      # Weekly reflection
    │   ├── notification_dispatcher.py # Notifications
    │   ├── arch_sync.py               # Architecture sync
    │   ├── complexity_validation_framework.py
    │   ├── team_size_classifier.py
    │   ├── health/                    # Health monitoring
    │   │   ├── health_orchestrator.py
    │   │   ├── agent_health.py
    │   │   ├── neo4j_health.py
    │   │   └── signal_health.py
    │   └── security/                  # Security tools
    │       ├── prompt_injection_filter.py
    │       └── cost_enforcer.py
    │
    └── notion_sync.py                 # Notion integration
```

### Key Files and Their Purposes

| File | Purpose |
|------|---------|
| `tools/kurultai/heartbeat_master.py` | Unified heartbeat orchestrator |
| `tools/kurultai/agent_tasks.py` | All 15 background task implementations |
| `tools/kurultai/capability_registry.py` | Capability registration and CBAC |
| `tools/kurultai/autonomous_orchestrator.py` | Autonomous task delegation |
| `tools/kurultai/dynamic_task_generator.py` | Dynamic task creation |
| `migrations/v3_capability_acquisition.py` | Neo4j schema for capabilities |
| `railway.yml` | Railway deployment configuration |
| `.env.example` | Environment variable template |

---

## 10. Configuration

### Environment Variables

#### Required Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `NEO4J_URI` | Neo4j connection | `bolt://neo4j:7687` |
| `NEO4J_PASSWORD` | Neo4j password | (generate with `openssl rand -hex 32`) |
| `OPENCLAW_GATEWAY_TOKEN` | Gateway auth | (generate with `openssl rand -hex 32`) |
| `AUTHENTIK_SECRET_KEY` | Authentik signing | (50+ char random string) |
| `AUTHENTIK_BOOTSTRAP_PASSWORD` | Initial admin password | (change after first login) |
| `SIGNAL_LINK_TOKEN` | Signal SSE auth | (generate with `openssl rand -hex 32`) |

#### Optional Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `NEO4J_USER` | Neo4j username | `neo4j` |
| `NEO4J_DATABASE` | Neo4j database | `neo4j` |
| `LOG_LEVEL` | Logging level | `info` |
| `PROMETHEUS_PORT` | Metrics port | `9090` |
| `NOTION_API_TOKEN` | Notion integration | — |
| `MOONSHOT_API_KEY` | LLM API | — |

### API Keys and Tokens

**Token Generation:**
```bash
# Gateway token (64 hex chars)
openssl rand -hex 32

# Authentik secret (50+ chars)
openssl rand -hex 32

# Bootstrap password
openssl rand -base64 24

# Signal link token
openssl rand -hex 32

# Agent auth secret
openssl rand -hex 32
```

### Service Ports

| Service | Port | Protocol | Purpose |
|---------|------|----------|---------|
| Moltbot Gateway | 18789 | HTTP | OpenClaw gateway |
| Moltbot API | 8082 | HTTP | Express API |
| Neo4j Bolt | 7687 | Bolt | Graph queries |
| Neo4j HTTP | 7474 | HTTP | Browser interface |
| Authentik Server | 9000 | HTTP | Identity provider |
| Authentik HTTPS | 9443 | HTTPS | Secure access |
| Authentik Proxy | 8080 | HTTP | Forward auth |
| PostgreSQL | 5432 | TCP | Authentik database |
| Skill Sync | 3000 | HTTP | GitHub sync API |
| Prometheus | 9090 | HTTP | Metrics endpoint |

---

## 11. Deployment Guide

### Prerequisites

- Railway CLI installed
- Git repository access
- Neo4j AuraDB instance or Railway Neo4j service
- Cloudflare DNS configured (for custom domain)
- Signal phone number (E.164 format)

### Step-by-Step Setup

#### Step 1: Clone and Configure

```bash
# Clone repository
git clone <repo-url> && cd souls/main

# Copy environment template
cp .env.example .env

# Edit .env with your credentials
# - Generate all required tokens
# - Set Neo4j credentials
# - Configure Authentik secrets
```

#### Step 2: Deploy to Railway

```bash
# Login to Railway
railway login

# Link project
railway link

# Deploy all services
railway up
```

#### Step 3: Run Migrations

```bash
# SSH into moltbot service
railway ssh -s moltbot

# Run Neo4j migrations
cd /app && python migrations/migration_manager.py --target-version 3

# Verify migration
python -c "from tools.kurultai.heartbeat_master import *; print('OK')"
```

#### Step 4: Bootstrap Authentik

```bash
# Access Authentik admin
open https://kublai.kurult.ai/if/admin/

# Login with akadmin / AUTHENTIK_BOOTSTRAP_PASSWORD

# Run bootstrap script
python authentik-proxy/bootstrap_authentik.py
```

#### Step 5: Link Signal Device

```bash
# Generate Signal QR code
python scripts/test-signal-integration.js

# Scan QR code with Signal mobile app
# Wait for "Signal device linked" confirmation
```

#### Step 6: Verify Deployment

```bash
# Health check
curl https://kublai.kurult.ai/health

# Agent list
curl -H "Authorization: Bearer $OPENCLAW_GATEWAY_TOKEN" \
  https://kublai.kurult.ai/api/agents

# Run heartbeat cycle
python tools/kurultai/heartbeat_master.py --cycle
```

### Installation Commands Summary

```bash
# One-time setup
pip install -r requirements.txt
npm install -g @railway/cli

# Development
python -m pytest tests/ -v
cd steppe-visualization && npm install && npm run dev

# Production deployment
railway up
python migrations/migration_manager.py --target-version 3
python tools/kurultai/heartbeat_master.py --setup
```

---

## 12. Operational Runbook

### Common Operations

#### Check System Health

```bash
# Quick health check
curl https://kublai.kurult.ai/health

# Detailed health
curl https://kublai.kurult.ai/health/neo4j
curl https://kublai.kurult.ai/health/disk

# Agent status via Neo4j
cypher-shell -u neo4j -p $NEO4J_PASSWORD "
  MATCH (a:Agent)
  RETURN a.name, a.status, a.last_heartbeat
  ORDER BY a.last_heartbeat DESC
"
```

#### Run Heartbeat Manually

```bash
# One cycle
python tools/kurultai/heartbeat_master.py --cycle

# List all tasks
python tools/kurultai/heartbeat_master.py --list-tasks

# Run specific agent tasks only
python tools/kurultai/heartbeat_master.py --cycle --agent jochi
```

#### Manage Tasks

```bash
# Disable a task
python -c "
from tools.kurultai.heartbeat_master import get_heartbeat, get_driver
hb = get_heartbeat(get_driver())
hb.disable_task('jochi', 'smoke_tests')
print('Disabled')
"

# Enable a task
python -c "
from tools.kurultai.heartbeat_master import get_heartbeat, get_driver
hb = get_heartbeat(get_driver())
hb.enable_task('jochi', 'smoke_tests')
print('Enabled')
"
```

#### View Recent Heartbeat Cycles

```cypher
// Last 10 cycles
MATCH (hc:HeartbeatCycle)
RETURN hc.cycle_number, hc.tasks_run, hc.tasks_failed, hc.total_tokens
ORDER BY hc.cycle_number DESC
LIMIT 10;

// Failed tasks
MATCH (hc:HeartbeatCycle)-[:HAS_RESULT]->(tr:TaskResult)
WHERE tr.status = "error"
RETURN tr.agent, tr.task_name, tr.summary, hc.cycle_number
ORDER BY hc.cycle_number DESC
LIMIT 20;
```

### Troubleshooting

#### Issue: Neo4j Connection Failed

**Symptoms:** Health check shows Neo4j disconnected

**Resolution:**
```bash
# Check Neo4j service status
railway logs -s neo4j

# Verify credentials
echo $NEO4J_PASSWORD

# Test connection
cypher-shell -u neo4j -p $NEO4J_PASSWORD "RETURN 1"

# Restart Neo4j if needed
railway restart -s neo4j
```

#### Issue: Agent Heartbeats Stale

**Symptoms:** Status shows agents with stale heartbeats

**Resolution:**
```bash
# Check heartbeat writer
railway logs -s moltbot --tail 100 | grep heartbeat

# Restart heartbeat sidecar
railway restart -s moltbot

# Manual heartbeat update
cypher-shell -u neo4j -p $NEO4J_PASSWORD "
  MATCH (a:Agent {id: 'main'})
  SET a.infra_heartbeat = datetime(), a.last_heartbeat = datetime()
"
```

#### Issue: Signal Not Responding

**Symptoms:** No Signal messages being sent/received

**Resolution:**
```bash
# Check signal-cli status
signal-cli --config /data/.signal receive

# Relink device if needed
python scripts/test-signal-integration.js

# Restart moltbot to respawn signal-cli
railway restart -s moltbot
```

#### Issue: High Token Usage

**Symptoms:** Token budget exceeded frequently

**Resolution:**
```bash
# Check token usage by task
python -c "
from tools.kurultai.heartbeat_master import get_driver
driver = get_driver()
with driver.session() as s:
    result = s.run('''
        MATCH (hc:HeartbeatCycle)-[:HAS_RESULT]->(tr:TaskResult)
        RETURN tr.task_name, sum(hc.total_tokens) as tokens
        ORDER BY tokens DESC
    ''')
    for r in result:
        print(f'{r[\"task_name\"]}: {r[\"tokens\"]}')
"

# Disable expensive tasks temporarily
python tools/kurultai/heartbeat_master.py --disable-task jochi full_tests
```

### Monitoring

#### Key Metrics to Monitor

| Metric | Query | Alert Threshold |
|--------|-------|-----------------|
| Cycle duration | `HeartbeatCycle.duration_seconds` | > 120s |
| Task failure rate | `tasks_failed / tasks_run` | > 10% |
| Token usage | `HeartbeatCycle.total_tokens` | > 5,000/cycle |
| Agent heartbeat age | `Agent.infra_heartbeat` | > 120s |
| Neo4j query time | `dbms.listQueries()` | > 30s |
| Disk usage | `df -h` | > 80% |
| Memory usage | `free -m` | > 80% |

#### Alerting Configuration

```bash
# Set up cost alerts in Railway
railway billing alerts create --threshold 50 --email admin@example.com

# Signal alerts for critical issues
# (Configured in health_check task)
```

#### Log Locations

| Log | Location |
|-----|----------|
| Application logs | `railway logs -s moltbot` |
| Heartbeat logs | Neo4j `HeartbeatCycle` nodes |
| Task results | Neo4j `TaskResult` nodes |
| Signal logs | `/data/.signal/logs/` |
| Neo4j logs | Railway Neo4j service logs |

---

## Appendix A: Security Architecture

### Defense in Depth

```
Layer 1: Input Validation
├── PromptInjectionFilter - NFKC normalization + pattern detection
├── Multi-turn injection detection
└── Block CRITICAL-risk capabilities

Layer 2: Privacy Sanitization
├── _sanitize_for_sharing() before delegation
├── PII pattern matching (phone, email, SSN, API keys)
└── LLM-based sanitization fallback

Layer 3: Capability Classification
├── Rule-based classification (>0.85 confidence)
├── Semantic similarity via Neo4j vector index
└── LLM fallback + CRITICAL risk blocking

Layer 4: Sandboxed Code Generation
├── Jinja2 SandboxedEnvironment
├── No network access during generation
└── Template injection prevention

Layer 5: Static Analysis
├── bandit security scanner
├── semgrep rule enforcement
├── AST pattern detection (tree-sitter)
└── Secret detection

Layer 6: Sandboxed Execution
├── subprocess with resource limits
├── Timeout handling (SIGALRM)
├── Network blocking
├── Filesystem restrictions
└── Restricted Python (no exec/eval)

Layer 7: Registry Validation
├── Cryptographic signing of tools
├── Namespace isolation
├── Dependency verification
└── CBAC enforcement

Layer 8: Runtime Monitoring
├── Cost tracking with HARD limits
├── Circular delegation detection
├── Behavior anomaly detection
└── Audit logging

Layer 9: Agent Authentication
├── HMAC-SHA256 message signing
├── 5-minute timestamp validation
├── Nonce-based replay prevention
└── 90-day key rotation
```

---

## Appendix B: Glossary

| Term | Definition |
|------|------------|
| **CBAC** | Capability-Based Access Control - authorization based on capabilities, not roles |
| **HOT/WARM/COLD** | Memory tiers based on access frequency |
| **HMAC** | Hash-based Message Authentication Code - cryptographic signature |
| **Kurultai** | Mongol council of tribal leaders; this multi-agent system |
| **MVS** | Memory Value Score - calculated score for tier assignment |
| **Moltbot** | The OpenClaw gateway service hosting the agents |
| **Neo4j** | Graph database used for operational memory |
| **OpenClaw** | Gateway framework for agent communication |
| **Signal** | End-to-end encrypted messaging protocol |
| **SOUL.md** | Agent identity and behavior definition file |

---

## Appendix C: Related Documentation

| Document | Purpose |
|----------|---------|
| [HEARTBEAT.md](./HEARTBEAT.md) | **Authoritative source** for heartbeat system details (v0.4) |
| [SOUL.md](./SOUL.md) | Agent identity and philosophy definitions |
| [IDENTITY.md](./IDENTITY.md) | Agent role and voice specifications |

---

## Changelog

### v2.0.2 - 2026-02-13
- **Heartbeat System**: Critical bug fixes and operational validation
  - **FIXED**: Python closure variable capture bug in `agent_tasks.py` (all tasks now execute correct handlers)
  - **FIXED**: Neo4j logging in `heartbeat_master.py` (HeartbeatCycle and TaskResult nodes now created)
  - **VERIFIED**: 20 tasks registered and executing successfully
  - **VERIFIED**: HeartbeatCycle nodes persisting to Neo4j (2+ cycles logged)
  - **VERIFIED**: TaskResult nodes created for each executed task
  - **STATUS**: System fully operational

### v2.0.1 - 2026-02-13
- **Heartbeat System**: Synced Section 8 with HEARTBEAT.md v0.4
  - Corrected task count: 15 → 14 tasks
  - Added complete task registry table with token budgets
  - Added MVS formula and thresholds
  - Added two-tier heartbeat architecture details
  - Added curation tier specifications

### v2.0 - 2026-02-10
- Initial production release
- Multi-agent orchestration platform
- Unified heartbeat system
- Capability acquisition pipeline

---

*Document Version: 2.0.2*  
*Last Updated: 2026-02-13*  
*Maintained by: Kurultai System*  
*Classification: Technical Architecture*
