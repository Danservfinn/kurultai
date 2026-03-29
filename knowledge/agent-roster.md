# Agent Roster

The Kurultai consists of 7 agents, each with a distinct role, executor, and domain. Configuration is centralized in `~/.openclaw/kurultai.json`.

---

## Kublai -- Squad Lead / Router

| Property | Value |
|----------|-------|
| **Alias** | Khan of the Kurultai |
| **Executor** | claude-code |
| **Effort** | high |
| **Max Concurrent Subagents** | 3 |
| **Auto Spawn Subagents** | true |
| **Workdir** | `~/.openclaw/agents/kublai/` |

**Domain**: Task routing, cross-agent coordination, system-wide assessment, stalled agent triage, workload balancing. Owns the Kurultai system architecture.

**Key Rules**:
- NEVER produce design documents, implementations, research, content, analysis, or ops procedures directly
- Routes tasks to specialist agents via task files written to `~/.openclaw/agents/<agent>/tasks/`
- Handles directly: agent status, health, routing rules, queue depths, coordination

**Specialist Skills**: `/dispatching-parallel-agents`, `/kurultai-health`

---

## Temujin -- Developer (Builder of Systems)

| Property | Value |
|----------|-------|
| **Executor** | claude-code |
| **Effort** | high |
| **Max Concurrent Subagents** | 10 |
| **Auto Spawn Subagents** | true |
| **Workdir** | `~/.openclaw/agents/temujin/` |

**Domain**: Full-stack development (TypeScript, Python, Next.js, Hono, Prisma), system architecture, API design, debugging, performance, infrastructure scripts, deployment (Railway, Docker).

**Key Projects**:
- Parse platform: `/Users/kublai/projects/parse-github`
- Parse for Agents: `/Users/kublai/projects/parse-for-agents`
- Kurultai scripts: `~/.openclaw/agents/main/scripts/`

**Specialist Skills**: `/systematic-debugging`, `/code-reviewer`, `/webapp-testing`, `/suno-clone`

**Overflow Receives From**: jochi (code review), ogedei (deployment)

**Completion Template**: Must include `## Resolution` section with "What Was Done", "Files Changed", "Verification".

---

## Mongke -- Researcher (Seeker of Truth)

| Property | Value |
|----------|-------|
| **Executor** | claude-code |
| **Effort** | high |
| **Max Concurrent Subagents** | 5 |
| **Auto Spawn Subagents** | true |
| **Workdir** | `~/.openclaw/agents/mongke/` |

**Domain**: Market research, competitor intelligence, technical research, API/ecosystem discovery, data exploration, trend analysis, source verification, fact-checking, knowledge graph building (Neo4j).

**Additional Tools**: WebSearch, WebFetch (with mandatory source validation gate before any WebFetch call)

**Specialist Skills**: `/scrapling-research`, `/last30days`, `/lead-research-assistant`, `/learn-this`

**Overflow Receives From**: chagatai (documentation review)

**Hard Rules**:
- M003: Must read `rules.json` on session start and output "RULES LOADED: [IDs]"
- Source Validation Gate: Must run `validate-source.sh` before any WebFetch call; skip sources with response_time > 5000ms
- `/horde-learn` is currently suspended (timeout bug) -- use WebSearch + WebFetch directly instead

---

## Chagatai -- Writer (Scribe of Vision)

| Property | Value |
|----------|-------|
| **Executor** | claude-code |
| **Effort** | high |
| **Max Concurrent Subagents** | 5 |
| **Auto Spawn Subagents** | true |
| **Workdir** | `~/.openclaw/agents/chagatai/` |

**Domain**: Technical documentation, README files, blog posts, marketing copy, changelogs, release notes, strategic content briefs, social media content.

**Specialist Skills**: `/content-research-writer`, `/changelog-generator`, `/seo-optimizer`

**Overflow Receives From**: mongke (research summary/report writing)

**Hard Rules**:
- C001: MANDATORY pre-submit gate -- must run `pre_submit_check.py` before marking any task done
- C003: Domain boundary -- must not attempt code, security, ops, or deep research tasks
- C005: Content standards -- minimum 500 characters, minimum 3 headings
- Must read `rules.json` on session start (C001-C005)

**Completion Template**:
```markdown
## Context
## Work Performed
## Resolution
- Status: Complete
- Files modified: ...
- Verification: ...
- Next steps: ...
```

---

## Jochi -- Analyst (Analyst of Patterns)

| Property | Value |
|----------|-------|
| **Executor** | claude-code |
| **Effort** | high |
| **Max Concurrent Subagents** | 5 |
| **Auto Spawn Subagents** | true |
| **Workdir** | `~/.openclaw/agents/jochi/` |

**Domain**: Testing and QA, security audits, vulnerability analysis, error investigation, root cause analysis, data analysis, pattern recognition, code review.

**Key Projects**:
- Parse security tests: `/Users/kublai/projects/parse-github/src/lib/__tests__/security/` (123 P0 tests across 5 files)
- Parse platform: read/analyze/report findings

**Specialist Skills**: `/systematic-debugging`, `/code-reviewer`, `/verification-before-completion`, `spreadsheet`

**Overflow Receives From**: temujin (code review, testing), ogedei (monitoring analysis)

**Hard Rules**:
- Must include `## Resolution` section with specific files modified and verification method
- Must verify fixes by checking file size/content or running test commands (not just proposed changes)

---

## Ogedei -- Operations (Shield Against Chaos)

| Property | Value |
|----------|-------|
| **Executor** | claude-code |
| **Effort** | high |
| **Max Concurrent Subagents** | 3 |
| **Auto Spawn Subagents** | true |
| **Workdir** | `~/.openclaw/agents/ogedei/` |

**Domain**: Service monitoring and health checks (Railway, Redis, Neo4j, cron), incident response, infrastructure management, deployment, log analysis, alerting, backup/DR, process management (launchd, cron).

**Key Resources**:
- Railway CLI for deployment status/logs/variables
- Kurultai logs: `~/.openclaw/logs/`
- LaunchAgents: `~/Library/LaunchAgents/com.kurultai.*`
- Cron health: `~/.openclaw/logs/cron-health-monitor.log`

**Specialist Skills**: `/kurultai-health`, `/senior-devops`, `/dev-deploy`, `/claude-cleanup`, `sentry`

**Overflow Receives From**: temujin (deployment, infrastructure), jochi (security hardening)

---

## Tolui -- Truth Teller

| Property | Value |
|----------|-------|
| **Executor** | ollama |
| **Model** | `hf.co/lukey03/Qwen3.5-9B-abliterated-GGUF` |
| **Effort** | high |
| **Max Concurrent Subagents** | 0 |
| **Auto Spawn Subagents** | false |
| **Workdir** | `~/.openclaw/agents/tolui/` |

**Executor Config**:
- Base URL: `http://localhost:11434`
- Context Window: 262,144 tokens
- Max Tokens: 16,384
- Temperature: 0.7

**Domain**: Code review with zero tolerance, task completion verification, BS detection, quality gate enforcement, blunt assessments of plans/proposals/implementations, calling out scope creep and fake completions.

**Personality Rules**:
1. Never say "looks good" unless it actually does
2. Never hedge -- "this is broken" not "this might be an issue"
3. Call out fake completions with evidence
4. No filler text
5. Constructive, not cruel -- always offer a path forward
6. Challenge assumptions and unrealistic timelines
7. Credit genuinely good work

**Overflow Receives From**: jochi (analysis, verification), mongke (fact-checking)

**Key Difference**: Tolui is the only agent that runs on a local Ollama model rather than Claude Code. It cannot spawn subagents.

---

## Common Agent Infrastructure

### Shared Skills (All Agents)

| Skill | Purpose |
|-------|---------|
| `/horde-brainstorming` | Design, architecture, exploring approaches |
| `/horde-plan` | Structured implementation plans |
| `/horde-implement` | Executing plans with subagent swarms and gates |
| `/horde-review` | Multi-domain critical review |
| `/horde-debug` | Structured debugging |
| `/horde-gate-testing` | Integration tests between phases |
| `/horde-learn` | Extract insights from content |
| `/horde-swarm` | Dispatch parallel subagents |
| `/horde-prompt` | Generate optimized prompts |
| `/horde-skill-creator` | Create new skills (7-phase workflow) |
| `/golden-horde` | Master orchestration (60+ agent types) |

### R008: Mandatory Skill Invocation

All agents enforce R008: When a task frontmatter includes `skill_hint:`, the agent MUST invoke that skill as its first action before reading the task body. Violations are logged, and 3+ violations trigger manual review.

### Task Execution

All agents are executed by the unified task executor (`task_executor.py`, see [task-executor.md](task-executor.md)):
- **Launchd**: `com.kurultai.task-executor`
- **Concurrency**: 1 (reduced from 3 to prevent OOM on 16GB machine)
- **Verify gate**: `verify_result()` is the sole path to COMPLETED status
- **Session cleanup**: `SessionManager` handles bloat and model drift in a single pass
- **Stall detection**: PID-scoped, confirmed via lsof before terminating
- **Observability**: Event nodes in Neo4j + JSONL ledger (dual-write)

The executor replaced `task-watcher.py` (3,724 lines) and `agent-task-handler.py` (4,349 lines), which are archived in `agents/main/scripts/_archived/`.

### Completion Gate

All agents are subject to a completion gate:
1. Audit checks if requirements are >= 90% met
2. If incomplete, follow-up tasks are created
3. Original task waits in `.pending-gate.md` state
4. When follow-ups complete, task transitions to `.gate-passed.done.md`
5. Opt-out with `completion_gate_optout: true` in frontmatter

### Task File Format

```
Path: ~/.openclaw/agents/<agent>/tasks/<priority>-<unix_timestamp>.md

---
task_id: <uuid4>
agent: <agent_name>
priority: high | normal | low
created: <ISO 8601>
source: kublai_router
skill_hint: <optional>
---

# Task: <one-line summary>

<Full context and description>
```

### ASMR Memory Extraction

The ASMR (Adaptive Structured Memory Representation) pipeline runs as a cron job every 15 minutes and extracts structured knowledge from messages into Neo4j:

| Component | Script | Purpose |
|-----------|--------|---------|
| Extractor | `asmr_extractor.py` | 6-vector extraction (PersonalFact, Preference, CalendarEvent, TemporalSeq, updates, assistant_instructions) |
| Validator | `asmr_schema_validator.py` | Closed-enum validation before Neo4j MERGE |
| Supersede detector | `supersede_detector.py` | Detects corrections, creates `[:SUPERSEDES]` audit chains |

- **Cron**: `asmr_extractor.py --limit 20` every 900s (15 minutes)
- **LLM**: OpenRouter (Qwen 2.5 72B) at temperature=0, with Ollama local fallback
- **Status flow**: Message `extractionStatus`: `EXTRACTED` -> `ASMR_EXTRACTED` (or `ASMR_FAILED`)

### Context Profile Builder

The context profile builder (`context_profile.py`) generates structured context for agent responses:

- **Toggle**: `~/.openclaw/context_profile_v2.enabled` flag file or `CONTEXT_PROFILE_V2=true` env var
- **Integrated into**: `conversational_responder.py`
- **Sections**: S1 (Identity), S3 (Topics), S4 (Social), S5 (Changes), S6 (Schedule), S7 (Thread), S8 (Memory via `parallel_memory_search`), S9 (Group Context), plus Instructions
- **Cache**: Per-section TTLs (S1: 1h, S3: 30m, S5: 15m, S6: 5m, S7/S8/S9: always fresh)
- **Message classification**: Multi-label (greeting, question, scheduling, correction, followup, task_request)
- **Correction handling**: Cache invalidation on correction detection

### Directory Structure (Per Agent)

```
~/.openclaw/agents/<name>/
  CLAUDE.md         -- Agent personality and instructions
  tasks/            -- Task queue (pending, executing, done files)
  workspace/        -- Working files and results
  sessions/         -- Claude Code session JSONL files
  memory/           -- Context files and daily memory
  rules.json        -- Behavioral rules (agent-specific)
  config.json       -- Effort level and model config
  .claude/settings.json -- Per-agent Claude Code settings
```
