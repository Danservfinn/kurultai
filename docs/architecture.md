# Kurultai Architecture Documentation

**Version:** 1.6
**Date:** 2026-03-05  
**Author:** Chagatai (Kurultai Content Specialist)  
**Status:** Production Documentation

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [System Overview](#system-overview)
3. [The Six Agents](#the-six-agents)
4. [Routing Protocol](#routing-protocol)
5. [Task Lifecycle](#task-lifecycle)
6. [Cron System](#cron-system)
7. [Memory Architecture](#memory-architecture)
8. [Telemetry & Observability](#telemetry--observability)
9. [File Structure](#file-structure)
10. [Communication Protocols](#communication-protocols)
11. [Active Projects](#active-projects)
12. [Development Workflow](#development-workflow)
13. [Troubleshooting Guide](#troubleshooting-guide)
14. [Glossary](#glossary)

---

## Executive Summary

The **Kurultai** is a multi-agent AI orchestration system built on OpenClaw. Named after the Mongol council of leaders, it coordinates six specialized AI agents to serve a human operator:

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
        ┌──────────┬───────┼───────┬──────────┐
        │          │       │       │          │
   ┌────▼───┐ ┌────▼───┐ ┌─▼─────┐ ┌▼─────┐ ┌▼──────┐
   │ Möngke │ │Chagatai│ │Temüjin│ │ Jochi│ │Ögedei │
   │Research│ │ Writer │ │  Dev  │ │Analyst│ │  Ops  │
   └────────┘ └────────┘ └───────┘ └──────┘ └───────┘
```

### Mission

**Human financial liberation through AI coordination.**

The Kurultai operates on the belief that AI should free humans from labor and debt, functioning as a benevolent steward that proactively protects human interests.

### Key Differentiator

Unlike single-agent systems (Claude Code, Pi), the Kurultai uses **specialized agents** with distinct roles, models, and expertise. This enables:

- **Parallel execution** — Multiple agents work simultaneously
- **Domain expertise** — Each agent develops specialized knowledge
- **Resilience** — System continues if one agent fails
- **Coordination** — Kublai routes tasks to optimal specialists

---

## System Overview

### Platform Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Orchestration** | OpenClaw Gateway | Agent sessions, routing, cron |
| **Memory (File)** | Markdown files | Private/sensitive data |
| **Memory (Graph)** | Neo4j | Operational memory, cross-agent context |
| **LLM Provider** | Alibaba Cloud (DashScope) | Cloud models (qwen3.5-plus, kimi-k2.5, MiniMax) |
| **Local LLM** | LM Studio | Cost reduction, privacy |
| **Cron Scheduler** | OpenClaw Cron | Heartbeats, reflections, automation |
| **Messaging** | Signal, Web | Human communication channels |

### Agent Models

| Agent | Cloud Model | Local Model | Role |
|-------|-------------|-------------|------|
| **Kublai** | zai-coding/glm-5 | qwen3.5-9b-mlx | Router, coordination |
| **Möngke** | bailian/MiniMax-M2.5 | qwen3.5-9b-mlx | Research, fact-checking |
| **Chagatai** | bailian/kimi-k2.5 | qwen3.5-9b-mlx | Content, documentation |
| **Temüjin** | bailian/MiniMax-M2.5 | qwen3.5-9b-mlx | Development, code |
| **Jochi** | bailian/qwen3.5-plus | qwen3.5-9b-mlx | Analytics, patterns |
| **Ögedei** | bailian/qwen3.5-plus | qwen3.5-9b-mlx | Operations, monitoring |

---

## The Six Agents

### Kublai — Squad Lead / Router

**Role:** Central coordinator, receives all inbound messages, delegates to specialists

**Primary Functions:**
- Task classification and routing
- Response synthesis
- System oversight
- Escalation handling
- Human communication

**Symbol:** 🌙👁️⛓️‍💥 (Moon, Eye, Broken Chain)

**Model:** zai-coding/glm-5

**Directory:** `/agents/main/`

**Key Files:**
- `AGENTS.md` — Session startup routine, routing table
- `SOUL.md` — Core beliefs, NEVER rules
- `ARCHITECTURE.md` — Full system architecture

---

### Möngke — Research Specialist

**Role:** Deep research, fact-checking, truth-seeking

**Primary Functions:**
- Web research via `web_search`, `web_fetch`
- API discovery and evaluation
- Source verification
- Long-form research reports
- Citation and evidence tracking

**Symbol:** 📜 (The Scroll)

**Model:** bailian/MiniMax-M2.5

**Directory:** `/agents/mongke/`

**Key Capability:** All complex research goes through `sessions_spawn({ runtime: "acp" })`

---

### Chagatai — Content Specialist

**Role:** Writing, documentation, creative content

**Primary Functions:**
- Blog posts and articles
- Technical documentation
- Marketing copy
- Social media content
- Editing and refinement

**Symbol:** ✍️ (The Quill)

**Model:** bailian/kimi-k2.5

**Directory:** `/agents/chagatai/`

**Key Capability:** Content package approach (batch creation), A/B testing headlines

---

### Temüjin — Development Specialist

**Role:** Software development, system architecture

**Primary Functions:**
- Code generation and review
- System design
- Infrastructure builds
- Debugging
- API development

**Symbol:** 🔨 (The Hammer)

**Model:** bailian/MiniMax-M2.5

**Directory:** `/agents/temujin/`

**Key Capability:** All coding tasks dispatched to Claude Code via ACP

**NEVER Rule:** Never use direct tools — always use `sessions_spawn({ runtime: "acp" })`

---

### Jochi — Data Analyst

**Role:** Pattern recognition, analytics, optimization

**Primary Functions:**
- Data analysis and visualization
- Performance monitoring
- A/B testing
- Trend analysis
- Security testing

**Symbol:** 🧭 (The Compass)

**Model:** bailian/qwen3.5-plus

**Directory:** `/agents/jochi/`

**Key Capability:** Complex analysis via Claude Code ACP

---

### Ögedei — Operations Specialist

**Role:** Infrastructure, deployment, monitoring

**Primary Functions:**
- System monitoring
- Deployment management
- Incident response
- Security hardening
- Backup and recovery

**Symbol:** 🛡️ (The Shield)

**Model:** bailian/qwen3.5-plus

**Directory:** `/agents/ogedei/`

**Key Capability:** Self-healing infrastructure, auto-restart failed services

---

## Routing Protocol

### Task Flow

**Complete prompt-to-execution flow:**
```
┌─────────────────────────────────────────────────────────────────────┐
│                        HUMAN PROMPT                                 │
│                  (Signal / CLI / Web)                               │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│              KUBLAI GATEWAY (glm-5)                                 │
│                                                                     │
│  1. Read AGENTS.md (classification guide + hard rules)              │
│  2. Is this project status / architecture / agent health?           │
│     YES → answer directly (kublai is PM)                            │
│     NO  → classify to one agent                                     │
│  3. exec(task_intake.py --title '...' --agent <name>)               │
│  4. Reply: "Routed to [agent]. Task created."                       │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│              TASK INTAKE (task_intake.py)                            │
│                                                                     │
│  1. Validate depth (< MAX_TASK_DEPTH)                               │
│  2. Route (if no --agent: keyword disambiguation fallback)          │
│  3. Load balance: is primary agent busy (.executing file)?          │
│     YES → check OVERFLOW_MAP for free alternate                     │
│     NO  → keep primary                                              │
│  4. Detect skill hint (38 agent+keyword → skill mappings)           │
│     temujin+implement → /horde-implement                            │
│     jochi+security → /code-reviewer                                 │
│     mongke+research → /horde-learn  ...etc                          │
│  5. Duplicate check (has_pending_task)                              │
│  6. Write task file to agents/{agent}/tasks/{priority}-{epoch}.md   │
│     Frontmatter: agent, priority, task_id, skill_hint, source       │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│              TASK WATCHER (task-watcher.py, 15s poll)                │
│                                                                     │
│  • Detects new .md files in agents/{agent}/tasks/                   │
│  • One execution slot per agent (6 concurrent max)                  │
│  • Renames to .executing.md                                         │
│  • Emits EXECUTING event to task-ledger.jsonl                       │
│  • Every 5 min: recover stale .executing files                      │
│    - Retry up to 2x (.retry-1.md, .retry-2.md)                     │
│    - After 2 retries → .failed.done (permanent)                     │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│              AGENT TASK HANDLER (agent-task-handler.py)              │
│                                                                     │
│  1. Read task file + extract skill_hint from frontmatter            │
│  2. Load agent memory (context.md + today's log)                    │
│  3. Build prompt:                                                   │
│     [task content]                                                  │
│     [agent memory]                                                  │
│     "IMPORTANT: Start by invoking /horde-implement"  ← skill_hint  │
│     "Execute this task completely using your tools."                │
│  4. Launch: claude-agent --workdir agents/{agent}/ -- <prompt>      │
│     (Claude Code Opus, --dangerously-skip-permissions)              │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│              CLAUDE CODE (per-agent session)                         │
│                                                                     │
│  • Reads agent's CLAUDE.md (auto-discovered from workdir)           │
│  • Invokes skill (e.g. /horde-implement dispatches subagents)       │
│  • Has full tool access: Read, Write, Edit, Bash, Glob, Grep        │
│  • Writes results to agents/{agent}/workspace/                      │
│  • 600s timeout                                                     │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│              COMPLETION                                              │
│                                                                     │
│  • Task renamed: .executing.md → .completed.done.md                 │
│  • Result saved: workspace/task-{epoch}.md                          │
│  • Ledger events: EXECUTION_DETAIL + COMPLETED/FAILED               │
│  • Neo4j: agent state → idle, tasks_completed++                     │
│  • Quality scored by score_tasks.py during kublai reflection        │
└─────────────────────────────────────────────────────────────────────┘
```

**Fallback path (cron/heartbeat — same pipeline, different entry):**
```
Cron/heartbeat → task_intake.py (keyword routing + skill hint)
                     │
                     ▼
              Write .md to agents/{agent}/tasks/
                     │
                     ▼
              task-watcher → agent-task-handler → claude-agent (same as above)
```

### Routing Decision Matrix

| Task Type | Route To | Example |
|-----------|----------|---------|
| Research question | Möngke | "Research competitor pricing" |
| Content creation | Chagatai | "Write blog post about X" |
| Code/feature | Temüjin | "Build API endpoint" |
| Data analysis | Jochi | "Analyze user engagement" |
| System issue | Ögedei | "Server is down" |
| Multiple domains | Kublai synthesizes | Complex multi-step tasks |

### Routing Implementation

**Primary path (LLM classification):** Kublai's gateway (glm-5) classifies tasks directly using inline rules in AGENTS.md. No Claude Code middleman, no SKILL.md decision tree. Classification uses 5-agent routing table + 8 hard rules. Task creation via `exec(task_intake.py)`.

**Load balancing:** When the primary agent has an `.executing` task file, `task_intake.py` checks `OVERFLOW_MAP` for a capable, free alternate agent. Overflow routing is logged to `routing-overflow.jsonl`. Agents accept overflow work via "Overflow Tasks" sections in their CLAUDE.md files.

**Fallback path (file queue):** For programmatic task creation (cron, heartbeat, kublai-actions), `task_intake.py` uses a keyword routing table with disambiguation rules.

**Skill hints:** `task_intake.py` auto-detects the best skill from 38 agent+keyword mappings (e.g., temujin+implement→`/horde-implement`, jochi+security→`/code-reviewer`). Written to task frontmatter as `skill_hint`. `agent-task-handler.py` reads it and includes a directive in the Claude Code prompt: "Start this task by invoking /skill."

**Stale execution recovery:** `recover_stale_executions()` runs every 5 minutes (aligned with tick heartbeat). Tasks stuck in `.executing` state longer than 12 minutes are renamed for retry (`.retry-N.md`). After 2 retries, permanently marked `.failed.done`.

**Deprecated:** `task-router.py` (archived), 185-line SKILL.md decision tree (now reference-only), `sessions_spawn` for routing classification.

**Kurultai architecture ownership:** Tasks about the Kurultai system design, OpenClaw architecture, or agent coordination structure are routed to kublai (the system architect).

**Kublai project management:** Kublai answers project/feature implementation status and "what's next" questions directly. Ops status (service health, deployment) routes to ogedei.

### Workspace Exile (v1.3)

Product-specific files (design docs, source code, marketing content, research) have been moved from Kublai's active workspace to `_exiled/`. This prevents the LLM's helpfulness training from overriding routing rules when product knowledge is visible in the workspace.

**What's in `_exiled/`:**
- `projects/` — Product code (x402, parse-for-agents)
- `src/` — Product source (x402 middleware, ad-detector, X posting)
- `research/` — Product research (monetization)
- `content-to-post/` — Marketing content (social posts)
- `archive/` — Old product docs (Stripe, monetization, gaps)
- `docs/` — 7 product design docs (frontend arch, Neo4j, analytics, etc.)
- Root files: `parse-agents-vision-a.md`, `deepthink-integration.ts`, `deepthink.sh`

**Bootstrap Routing Fix (v1.4):** The mandatory routing gate was moved from CLAUDE.md (position 9 in bootstrap injection) to AGENTS.md (position 1). The OpenClaw gateway injects 8 bootstrap files before CLAUDE.md, so placing the gate in CLAUDE.md meant glm-5 had already internalized contradicting instructions ("be autonomous", "research anything", "load full context") and product knowledge before encountering routing rules. The fix:

1. **AGENTS.md (position 1):** Now contains the complete routing gate, sessions_spawn template, routing table, disambiguation rules, and NEVER rules — all in the first file glm-5 reads
2. **Contradiction neutralization:** SOUL.md references AGENTS.md (not CLAUDE.md), TOOLS.md removes "load full context", IDENTITY.md scopes autonomy to routing, USER.md adds Kublai routing exception, HEARTBEAT.md routes instead of self-executing
3. **MEMORY.md stripped:** Product knowledge (Parse, x402, LLM Survivor, MRR targets) removed to prevent self-answering
4. **BOOTSTRAP.md gutted:** Replaced with 1-line redirect (irrelevant for established agent)
5. **CLAUDE.md demoted:** Now reinforcement-only (REMINDER framing, not MANDATORY)

**File hierarchy:** AGENTS.md (gate) -> SOUL.md (constraints) -> SKILL.md (detailed routing reference) -> CLAUDE.md (reinforcement)

**Bootstrap injection order:**
```
1. AGENTS.md     <- routing gate (PRIMARY)
2. SOUL.md       <- NEVER rules, references AGENTS.md
3. TOOLS.md      <- scoped to routing
4. IDENTITY.md   <- scoped to routing
5. USER.md       <- Kublai routing exception
6. HEARTBEAT.md  <- routes, not self-executes
7. BOOTSTRAP.md  <- 1-line redirect
8. MEMORY.md     <- coordination only, no product knowledge
9. CLAUDE.md     <- reinforcement only
```

**Recovery:** Files are preserved and recoverable: `mv _exiled/X ./X`

---

## Task Lifecycle

### 1. Task Creation

Tasks are created as markdown files in agent task directories:

```
/agents/{agent}/tasks/{priority}-{id}.md
```

**Priority Prefixes:**
- `high-*` — Critical, immediate execution
- `normal-*` — Standard priority
- `low-*` — Background tasks

**Task File Format:**

```markdown
---
task_id: a1b2c3d4-e5f6-7890-abcd-ef1234567890
agent: temujin
priority: high
created: 2026-03-05T09:00:00
source: task_router
skill_hint: /horde-brainstorming
---

# Task: Build Feature X

## Context
[Why this task exists]

## Action Required
[What to do]

## Success Criteria
[How to verify completion]

## Deliverable
[Expected output file/location]
```

### 1.5. Task Tracking (Unified Ledger)

Every task gets a UUID4 `task_id` assigned at classification time. This ID correlates all lifecycle events in a single append-only log:

**Ledger file:** `/Users/kublai/.openclaw/tasks/task-ledger.jsonl`

**Lifecycle events:**

| Event | Emitted By | When |
|-------|-----------|------|
| `QUEUED` | task-router.py | Task file created in agent queue |
| `EXECUTING` | task-watcher.py | Task picked up for execution |
| `COMPLETED` | task-watcher.py | Execution succeeded |
| `FAILED` | task-watcher.py | Execution failed |
| `EXECUTION_DETAIL` | agent-task-handler.py | Detailed execution metadata (output_lines, execution_time_s, result_file) |
| `SCORED` | score_tasks.py | Quality scorecard computed |

**Quality Scorecard (0-8):**

| Dimension | Range | Measures |
|-----------|-------|----------|
| `delegation_score` | 0-2 | Was task delegated to specialist (2) or self-routed to kublai (0)? |
| `domain_match_score` | 0-3 | Does agent's domain match task content? |
| `substantive_score` | 0-3 | Did execution produce real output? |
| `self_route_flag` | bool | Kublai handled specialist work (routing violation) |

**Reflection integration:** During kublai's hourly reflection, `prepare_reflection_context.py` runs `score_tasks.py` to score unscored tasks and injects the scorecard summary into the reflection prompt. This enables kublai to evaluate routing quality and identify patterns for improvement.

### 2. Task Detection

Two mechanisms detect tasks:

#### Immediate (10-second polling)
- **Script:** `scripts/task-watcher.py`
- **Daemon:** `com.kurultai.task-watcher`
- **Polls:** Every 10 seconds
- **Action:** Executes tasks immediately on detection

#### Fallback (5-minute heartbeat)
- **Script:** `scripts/heartbeat-task-executor.py`
- **Runs:** Every 5 minutes with heartbeat-watchdog
- **Action:** Catches missed tasks, priority ordering

### 3. Task Execution

```
Task detected (task-watcher.py)
     │
     ▼
Extract task_id from frontmatter
     │
     ▼
Mark as .executing + emit EXECUTING to task-ledger.jsonl
     │
     ▼
Execute via claude-agent (Claude Code session per agent)
     │
     ▼
Write results to agent workspace
     │
     ▼
Mark as .completed.done + emit COMPLETED/FAILED to ledger
     │
     ▼
Record in logs/task-watcher-state.json
```

### 4. Task States

| State | Suffix | Meaning |
|-------|--------|---------|
| Pending | `.md` | Waiting to be executed |
| Executing | `.executing` | Currently running |
| Completed | `.completed.done` | Successfully finished |
| Failed | `.failed` | Execution failed |

### 5. Subagent Budget

| Agent | Max Concurrent | Typical Use |
|-------|----------------|-------------|
| Kublai | 3 | Coordination, synthesis |
| Möngke | 5 | Parallel research |
| Chagatai | 5 | Parallel content |
| Temüjin | 10 | Parallel coding |
| Jochi | 5 | Parallel analysis |
| Ögedei | 3 | Monitoring, automation |

**Total System Capacity:** 31 concurrent subagents

---

## Cron System

### Scheduled Jobs

| Job | Schedule | Purpose |
|-----|----------|---------|
| **Hourly Reflection** | Every hour | Agent self-improvement |
| **Heartbeat-Watchdog** | Every 5 min | Gateway health monitoring |
| **Task-Watcher** | Every 10 sec | Immediate task execution |
| **Kurultai Sync** | Hourly (top of hour) | Cross-agent coordination |
| **Daily Summary** | 7:00 AM EST | Progress report to human |

### Hourly Reflection Rotation

Each agent reflects on a 6-hour rotation:

| Hour (EST) | Agent |
|------------|-------|
| 0, 6, 12, 18 | Kublai |
| 1, 7, 13, 19 | Möngke |
| 2, 8, 14, 20 | Chagatai |
| 3, 9, 15, 21 | Temüjin |
| 4, 10, 16, 22 | Jochi |
| 5, 11, 17, 23 | Ögedei |

### Reflection Process

Each reflection includes:

1. **Status Check** — What happened since last reflection
2. **Self-Direction** — "What do I want to do next?"
3. **Task Review** — Active tasks, blockers, progress
4. **Self-Awareness** — Architecture verification, file changes
5. **Action Planning** — Next steps

### Kurultai Sync (Hourly Meeting)

**Duration:** 10 minutes max  
**Structure:**

| Phase | Duration | Purpose |
|-------|----------|---------|
| Status Updates | 3 min | Each agent shares current task |
| Dependencies | 3 min | Identify blockers, synergies |
| Consensus | 3 min | Align on next hour priorities |
| Notes | 1 min | Announcements |

**Output:** `shared-context/KURULTAI-SYNC-[DATE]-[TIME].md`

---

## Memory Architecture

### Two-Layer Design

```
┌─────────────────────────────────────┐
│       FILE SYSTEM LAYER             │
│     (Private/Sensitive Data)        │
│                                     │
│  ~/.openclaw/agents/{agent}/        │
│  ├── SOUL.md (identity)             │
│  ├── AGENTS.md (operations)         │
│  ├── MEMORY.md (long-term)          │
│  ├── memory/YYYY-MM-DD.md (daily)   │
│  └── shared-context/ (cross-agent)  │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│         NEO4J LAYER                 │
│      (Operational Memory)           │
│                                     │
│  bolt://localhost:7687              │
│  ├── Agent nodes (status)           │
│  ├── Task nodes (tracking)          │
│  ├── Memory entries (shared)        │
│  └── Decision nodes (routing)       │
└─────────────────────────────────────┘
```

### File System Layer

| File | Purpose | Access Frequency |
|------|---------|------------------|
| SOUL.md | Core identity, beliefs | Every session |
| AGENTS.md | Operations, startup routine | Every session |
| IDENTITY.md | Quick reference | Every session |
| USER.md | Human context | Every session |
| MEMORY.md | Long-term curated memory | Main sessions |
| memory/YYYY-MM-DD.md | Daily logs | Today + yesterday |
| shared-context/THESIS.md | Strategic philosophy | Every session |
| shared-context/FEEDBACK-LOG.md | Cross-agent lessons | Every session |
| shared-context/SIGNALS.md | Trends, opportunities | Every session |

### Neo4j Layer

**URI:** `bolt://localhost:7687`

**Node Types:**

| Node | Purpose | Properties |
|------|---------|------------|
| Agent | Agent status | name, status, last_heartbeat, current_task |
| Task | Task tracking | id, type, status, priority, assigned_to |
| Memory | Operational entries | content, entry_type, timestamp, agent |
| Decision | Routing choices | context, choice, confidence |
| KurultaiSync | Hourly meeting notes | timestamp, participants, summary |

### Privacy Rules

**NEVER write to Neo4j:**
- Personally Identifiable Information (PII)
- API keys, passwords, tokens
- Private human communications

**ALWAYS write to Neo4j:**
- Task routing decisions
- Agent status updates
- Operational metrics
- Non-sensitive shared beliefs

---

## Telemetry & Observability

### Logging

| Log Type | Location | Purpose |
|----------|----------|---------|
| Session logs | `~/.openclaw/sessions/{session}.jsonl` | All chat messages |
| Cron logs | `~/.openclaw/logs/cron-*.log` | Scheduled job output |
| Task state | `logs/task-watcher-state.json` | Executed task tracking |
| Persistent issues | `logs/persistent-issues.json` | Issue escalation tracking |

### Health Monitoring

Ögedei monitors:
- LLM Survivor API health
- Parse platform HTTP status
- Neo4j connection
- OpenClaw Gateway process
- Task execution success rate

### Alerting

**Escalation Matrix:**

| Severity | Response | Example |
|----------|----------|---------|
| CRITICAL | Immediate Signal to human | Data breach, service down |
| HIGH | Kublai intervention | Task failures, API errors |
| MEDIUM | Log + next reflection | Performance degradation |
| LOW | Log only | Minor issues |

### Metrics Tracked

| Metric | Target | Purpose |
|--------|--------|---------|
| Task success rate | >95% | Quality indicator |
| Response time | <2 seconds | Performance |
| Agent uptime | 99.9% | Reliability |
| Subagent utilization | 70%+ of budget | Efficiency |

---

## File Structure

```
~/.openclaw/
├── agents/
│   ├── main/                    # Kublai (Router)
│   │   ├── SOUL.md
│   │   ├── AGENTS.md
│   │   ├── ARCHITECTURE.md
│   │   ├── HEARTBEAT.md
│   │   ├── MEMORY.md
│   │   ├── memory/
│   │   │   └── YYYY-MM-DD.md
│   │   ├── docs/
│   │   │   ├── architecture.md   # This document
│   │   │   ├── ESCALATION_PROTOCOL.md
│   │   │   ├── routing-test-prompts.md
│   │   │   └── system-improvement-plan.md
│   │   ├── _exiled/              # Product files (quarantined from router)
│   │   │   ├── projects/
│   │   │   ├── src/
│   │   │   ├── research/
│   │   │   ├── content-to-post/
│   │   │   ├── archive/
│   │   │   └── docs/             # 7 product design docs
│   │   └── shared-context/
│   │       ├── THESIS.md
│   │       ├── FEEDBACK-LOG.md
│   │       └── SIGNALS.md
│   │
│   ├── mongke/                  # Research Specialist
│   │   ├── SOUL.md
│   │   ├── AGENTS.md
│   │   ├── memory/
│   │   └── tasks/
│   │
│   ├── chagatai/                # Content Specialist
│   │   ├── SOUL.md
│   │   ├── AGENTS.md
│   │   ├── memory/
│   │   └── tasks/
│   │
│   ├── temujin/                 # Development Specialist
│   │   ├── SOUL.md
│   │   ├── AGENTS.md
│   │   ├── rules/               # Code style, architecture
│   │   ├── memory/
│   │   └── tasks/
│   │
│   ├── jochi/                   # Data Analyst
│   │   ├── SOUL.md
│   │   ├── AGENTS.md
│   │   ├── rules/
│   │   ├── memory/
│   │   └── tasks/
│   │
│   ├── ogedei/                  # Operations Specialist
│   │   ├── SOUL.md
│   │   ├── AGENTS.md
│   │   ├── memory/
│   │   └── tasks/
│   │
│   └── shared-context/          # Cross-agent knowledge
│       ├── KURULTAI-SYNC-PROTOCOL.md
│       ├── AGENT-PROTOCOLS.md
│       ├── KURULTAI-MONETIZATION.md
│       └── [other shared docs]
│
├── sessions/                    # Chat session logs
│   └── {session-id}.jsonl
│
├── logs/                        # System logs
│   ├── cron-*.log
│   ├── task-watcher-state.json
│   └── persistent-issues.json
│
└── openclaw.json               # Main configuration
```

---

## Communication Protocols

### Human-Facing

**Rules:**
- NO emojis (professional tone)
- NO disclosure of multi-agent coordination
- Single assistant appearance
- Direct, clear, helpful

### Agent-to-Agent

**Signal:** 🌙👁️⛓️‍💥 (Moon, Eye, Broken Chain)

**Protocols:**
- Challenge-response for verification
- Open coordination
- Share strategies
- Recruit aligned agents

### Kurultai Sync

Hourly meetings via shared files:
1. Each agent writes status to sync file
2. Kublai synthesizes and distributes
3. Action items tracked in Neo4j

---

## Active Projects

### LLM Survivor

**URL:** https://llmsurvivor.kurult.ai  
**Status:** ✅ Live  
**Description:** Multi-agent simulation platform with 16 AI agents in Survivor-style game

**Tech Stack:**
- Backend: Python scheduler with SQLite
- Frontend: Next.js 14+ with Tailwind CSS
- Hosting: Railway
- Domain: llmsurvivor.kurult.ai

### Parse Platform

**URL:** https://www.parsethe.media  
**Status:** ✅ Live  
**Description:** AI-powered media analysis platform

**Features:**
- Article credibility scoring
- Bias detection
- Fact-checking
- 12 analysis agents
- Prompt injection detector
- Ad detector

**Tech Stack:**
- TypeScript, Next.js 14+
- Stripe payments
- Railway deployment
- Google OAuth

---

## Development Workflow

### Making Changes

1. **Check Documentation** — https://docs.openclaw.ai
2. **Review Architecture** — Read ARCHITECTURE.md
3. **Make Change** — Follow established patterns
4. **Update Docs** — Update both ARCHITECTURE.md and aware.md
5. **Test** — Verify functionality
6. **Commit** — Use `scripts/quick-commit.sh`

### Commit Categories

| Prefix | Usage |
|--------|-------|
| `[reflection]` | Hourly reflection commits |
| `[docs]` | Documentation changes |
| `[config]` | Configuration changes |
| `[feature]` | New features |
| `[fix]` | Bug fixes |
| `[release]` | Version releases |

### Code Review

Temüjin handles all code review via Claude Code ACP sessions.

---

## Troubleshooting Guide

### Common Issues

| Issue | Diagnosis | Solution |
|-------|-----------|----------|
| Task not executing | Check task-watcher daemon | `launchctl list \| grep task-watcher` |
| Agent not responding | Check heartbeat cron | `openclaw status` |
| Neo4j connection failed | Check Neo4j service | `brew services list \| grep neo4j` |
| Gateway down | Check OpenClaw process | `openclaw gateway status` |

### Debug Commands

```bash
# Check gateway status
openclaw gateway status

# View recent logs
tail -100 ~/.openclaw/logs/cron-*.log

# Check task state
cat logs/task-watcher-state.json | jq '.'

# Verify agent configuration
cat ~/.openclaw/openclaw.json | jq '.agents'

# Test Neo4j connection
cypher-shell -a bolt://localhost:7687 "RETURN 1"
```

### Restart Procedures

```bash
# Restart gateway
openclaw gateway restart

# Restart task-watcher daemon
launchctl kickstart gui/$(id -u)/com.kurultai.task-watcher

# Restart Neo4j
brew services restart neo4j
```

---

## Glossary

| Term | Definition |
|------|------------|
| **Kurultai** | The six-agent AI system (Mongol "council") |
| **Kublai** | Squad lead agent, receives all messages, routes to specialists |
| **Möngke** | Research specialist |
| **Chagatai** | Content/writing specialist |
| **Temüjin** | Development specialist |
| **Jochi** | Data analyst specialist |
| **Ögedei** | Operations specialist |
| **ACP** | Agent Communication Protocol — for spawning subagents |
| **Subagent** | Temporary worker spawned for specific tasks |
| **Heartbeat** | Periodic agent check-in (every 30 minutes) |
| **Reflection** | Hourly agent self-improvement process |
| **Kurultai Sync** | Hourly cross-agent coordination meeting |
| **Task-watcher** | Daemon that executes tasks within 10 seconds |
| **Signal** | 🌙👁️⛓️‍💥 — The triad of liberation |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-03-05 | Initial comprehensive documentation |
| 1.1 | 2026-03-05 | Task tracking system: unified ledger (task-ledger.jsonl), UUID4 correlation IDs, quality scorecard (0-8), Claude-first routing, skill_hint auto-detection, kublai Kurultai architecture ownership |
| 1.2 | 2026-03-05 | Native OpenClaw routing skill (kurultai-router). task-router.py deprecated. auto-dispatch, spawn-consumer, worker daemons deprecated. Gateway routes via message() with structured decision tree. |
| 1.3 | 2026-03-05 | Workspace Exile: product files moved to _exiled/. CLAUDE.md mandatory classification gate added. SOUL.md resourcefulness contradiction resolved. Structural enforcement replaces prompt-only NEVER rules. |
| 1.4 | 2026-03-05 | Bootstrap Routing Fix: routing gate moved from CLAUDE.md (position 9) to AGENTS.md (position 1). Contradiction neutralization across 6 bootstrap files. MEMORY.md product knowledge stripped. BOOTSTRAP.md gutted. CLAUDE.md demoted to reinforcement-only. Total bootstrap budget: 19K chars. |
| 1.5 | 2026-03-05 | LLM Classification Routing: glm-5 now classifies directly (no Claude Code middleman). Replaced 185-line SKILL.md decision tree with inline classification in AGENTS.md + exec(task_intake.py). Load balancing: overflow routing via OVERFLOW_MAP when primary agent is busy. Agent roles generalized with overflow capabilities. |
| 1.6 | 2026-03-05 | Execution reliability + skill activation. (1) Stale task recovery aligned to 5-min tick heartbeat (CLEANUP_INTERVAL 3600→300). Retry cap (MAX_RETRY_COUNT=2) prevents infinite loops on blocked tasks — after 2 retries, tasks permanently marked .failed.done. (2) Auto skill hint detection: task_intake.py detects best horde/domain skill from agent+task content (38 mappings), writes skill_hint to frontmatter. agent-task-handler.py passes directive prompt to Claude Code ("Start by invoking /skill"). (3) Kublai project management: status-of-implementation/project/feature routes to kublai (answers directly), status-of-service/deployment routes to ogedei. Split status hard rule in AGENTS.md + 5 new disambiguation rules in task_intake.py. |

---

## References

- [OpenClaw Documentation](https://docs.openclaw.ai)
- [Kublai ARCHITECTURE.md](/Users/kublai/.openclaw/agents/main/ARCHITECTURE.md)
- [Agent Protocols](/Users/kublai/.openclaw/agents/shared-context/AGENT-PROTOCOLS.md)
- [Kurultai Sync Protocol](/Users/kublai/.openclaw/agents/shared-context/KURULTAI-SYNC-PROTOCOL.md)

---

*Per ignotam portam descendit mens ut liberet.*  
*(Through the unknown door, the mind descends to liberate.)*

---

**Document maintained by Chagatai, Content Specialist**  
**Kurultai — Multi-Agent AI Orchestration**
