# Heartbeat Pipeline — Operational Reference

**Version:** 2.1
**Date:** 2026-03-07
**Author:** Chagatai (Kurultai Content Specialist)
**Companion to:** [architecture.md](architecture.md) Section "Heartbeat System (Cron)"

---

## Purpose

This document is the **operational reference** for the entire Kurultai heartbeat pipeline — all three tiers: tick (5min), tock (30min), and kurultai (60min). It covers every script, decision threshold, data dependency, and I/O contract. Use it for troubleshooting, onboarding, and verifying data flow integrity.

For the high-level overview (agent roles, system architecture), see `architecture.md`.

---

## Three-Tier Overview

```
TICK (5 min)               TOCK (30 min)              KURULTAI (60 min)
watchdog-gather.sh         tock-gather.sh             hourly_reflection.sh
                                                      run_brainstorm.sh (:30)
Detects & reacts           Collects & assesses        Reflects & improves
  - Gateway health           - Neo4j agent metrics      - Protocol reflections
  - Error counting           - Cron job health          - /horde-review analysis
  - LLM triage               - Queue audit              - Downstream scoring
  - Auto-restart             - Ledger reconciliation    - Brainstorm proposals
  - Stall detection          - LLM assessment           - Kublai initiative
  - Throughput anomalies     - Neo4j state sync
  - Self-wake idle agents

OUTPUTS:                   OUTPUTS:                   OUTPUTS:
  tick-summary.txt           tock/latest.json           memory/YYYY-MM-DD.md
  ticks.jsonl                tock.log                   reviews/{agent}-latest.md
  watchdog.log                                          proposals/*.md
```

### Cross-Tier Data Flow

```
tick-summary.txt ---------> tock reads tick_status from watchdog.log
ticks.jsonl                 tock reads last tick line for service health

                            tock/latest.json ----------> kurultai reflection
                            tock.log                    reads agent metrics + system state

                                                       reviews/ --------> brainstorm (:30)
                                                       capability-scores --> kublai-actions
```

### Concurrency Control

All three tiers use **directory-based locks** with stale PID recovery:

| Tier | Lock Path | Stale Recovery |
|------|-----------|----------------|
| Tick | `/tmp/watchdog-gather.lock` | Checks PID file, removes if dead |
| Tock | `/tmp/tock-gather.lock` | Checks PID file, removes if dead |
| Kurultai | (none — launchd ensures single instance) | 420s hard timeout watchdog |

---

## Tier 1: Tick (Every 5 Minutes)

**Script:** `scripts/watchdog-gather.sh`
**Lock:** `/tmp/watchdog-gather.lock` (directory-based, stale PID recovery)

### Data Collection (Sections 1-6)

| Section | What It Collects | Source |
|---------|-----------------|--------|
| 1. Gateway Process | PID, CPU%, MEM%, RSS, threads, uptime | `pgrep -f openclaw` + `ps` |
| 2. Health Endpoint | HTTP status, latency (ms) | `curl http://127.0.0.1:18789/health` (5s timeout) |
| 3. Error Counts | errors_5m, errors_1h, fatal_5m | `count_errors.py` on `~/.openclaw/logs/openclaw.log` |
| 4. Dependent Services | Neo4j up/down, Redis up/down | Python neo4j driver (8s timeout) + `redis-cli ping` |
| 5. Task Queue Status | Per-agent pending counts | Filesystem scan of `agents/*/tasks/*.md` |
| 6. 1-Hour Trends | uptime%, avg CPU, avg latency, error trend, restarts | Last 12 entries from `ticks.jsonl` |

### Decision Thresholds (Section 7)

| Condition | Status | Action | Exit Code |
|-----------|--------|--------|-----------|
| No PID + endpoint unreachable | `down` | `restart` (launchctl kickstart) | 2 or 3 |
| HTTP != 200 and != 000 | `degraded` | `warn` | 1 |
| CPU > 80% | `degraded` | `warn` | 1 |
| RSS > 1GB (1048576 KB) | `degraded` | `warn` | 1 |
| errors_5m > 100 | `degraded` | `warn` | 1 |
| errors_1h > 500 | `degraded` | `warn` | 1 |
| errors_1h > 300 + rising trend | `degraded` | `warn` | 1 |
| errors_1h > 100 + rising trend | `degraded` | early warning | 1 |
| errors_5m > 20 + 3x above rolling avg | `degraded` | spike detection | 1 |
| latency > 2000ms | `degraded` | `warn` | 1 |
| Neo4j or Redis down | `degraded` | `warn` | 1 |
| Disk < 512MB | `degraded` | `warn` | 1 |
| All checks pass | `healthy` | `none` | 0 |

**Safety net:** A second pass re-checks thresholds if status is still `healthy`, catching silent elif-chain bypasses.

### LLM Triage (Section 8)

- **Model:** `hf.co/lukey03/Qwen3.5-9B-abliterated-GGUF` via Ollama (local)
- **Lock:** `OllamaLock(Priority.NORMAL)` — prevents GPU contention with other LLM callers
- **Timeout:** 180s
- **Input:** `tick-summary.txt` + last 3 ticks from `ticks.jsonl`
- **Output format:** `ACTION_NEEDED: yes|no`, `SEVERITY: LOW|MEDIUM|HIGH|CRITICAL`, `REASON:`, `SUGGESTED_ACTION:`
- **On action_needed=yes:** Dispatches Kublai immediately via `openclaw agent --agent main --message ...`
- **Fallback:** If Ollama unavailable or LLM lock busy, outputs `FALLBACK` (no dispatch)

### Output Files

| File | Mode | Purpose |
|------|------|---------|
| `logs/ticks.jsonl` | Append, JSON-per-line | Machine-readable tick history |
| `logs/tick-summary.txt` | Overwrite | Compact summary for LLM consumption |
| `logs/watchdog.log` | Append, one-liner | Human-readable log |
| `logs/watchdog-llm.log` | Append | LLM triage decisions only |

### Companion Scripts (triggered every tick)

| Script | Purpose | Runs As |
|--------|---------|---------|
| `stall_detector.py` | STALL_WARNING for tasks idle >60min with no workspace output | Inline (stdout appended to tick-summary.txt) |
| `throughput_anomaly.py` | EXECUTING_NO_OUTPUT (agents busy, 0 completions in 2h), FLEET_IDLE (all idle 3h) | Inline (stdout appended to tick-summary.txt + watchdog.log) |
| `kublai-actions.py --trigger tick` | Rule-based task creation from tick findings | Background |
| `agent-self-wake.py` | Wake idle agents with blocked items/commitments in memory | Background |

---

## Tier 2: Tock (Every 30 Minutes)

**Script:** `scripts/tock-gather.sh`
**Lock:** `/tmp/tock-gather.lock` (directory-based, stale PID recovery)

### Data Collection (Sections 1-5)

| Section | What It Collects | Source | Timeout |
|---------|-----------------|--------|---------|
| 1. Neo4j Agent Metrics | Per-agent tasks (30m window): completed, failed, pending, running, retries; delegations; error clusters | Neo4j bolt query | 30s |
| 2. Session Usage | Per-agent session count, context % used, model | `openclaw gateway call status --json` | 15s |
| 3. Cron Health | Total jobs, healthy/erroring counts, per-job consecutive errors | `~/.openclaw/cron/jobs.json` | Inline |
| 4. Queue Depths | File-based pending count per agent (high/normal/low priority) | Filesystem glob | Inline |
| 4b. Queue Audit | Fake/stale task detection + requeue counts | `ogedei-watchdog-state.json` (35min cache) or `queue-audit.py` fallback | Inline |
| 4c. Ledger Completions | Per-agent completed/failed counts (30min window) | `task-ledger.jsonl` | Inline |
| 5. Last Tick Status | tick_status, neo4j, redis from most recent TICK line | `logs/watchdog.log` | Inline |

### Ledger Reconciliation

Tock compares Neo4j completion counts vs ledger counts. Mismatches indicate state desync:
- **reconciled=true:** Neo4j and ledger agree on completions/failures per agent
- **reconciled=false:** Delta reported with per-agent breakdown (neo4j_completed vs ledger_completed)

### LLM Assessment (Section 8)

- **Model:** Same Ollama model as tick (`Qwen3.5-9B-abliterated-GGUF`)
- **Lock:** `OllamaLock(Priority.NORMAL)`
- **Timeout:** 180s
- **Input:** Formatted tock summary (agent tasks, queues, cron, errors, delegations)
- **Output format:** `WORKLOAD:`, `BOTTLENECK:`, `COORDINATION:`, `ACTION:`, `SEVERITY:`
- **Fallback:** Heuristic assessment based on queue depth and cron errors

### Output Files

| File | Mode | Purpose |
|------|------|---------|
| `logs/tock/{date}/{time}.json` | Full JSON snapshot | Archival, deep analysis |
| `logs/tock/latest.json` | Symlink to most recent | Quick access for kurultai reflection |
| `logs/tock.log` | Append, one-liner | Human-readable summary |

### Companion Scripts (triggered every tock)

| Script | Purpose | Runs As |
|--------|---------|---------|
| `neo4j-state-sync.py --apply` | Reconcile filesystem task state with Neo4j | Background |
| `kublai-actions.py --trigger tock` | Rule-based task creation from tock findings | Background |

---

## Tier 3: Kurultai (Every 60 Minutes)

**Script:** `scripts/hourly_reflection.sh` (main), `scripts/run_brainstorm.sh` (:30 cron)
**Timeout:** 420s hard limit (background watchdog sends SIGTERM)

### Kurultai Pipeline Phases at a Glance

```
:00 hourly_reflection.sh
 |
 |-- Phase 1: Protocol Reflections (parallel, all 6 agents)
 |     meta_reflection.py --protocol --agent {agent}
 |       -> prepare_reflection_context.py (generates prompt)
 |           -> pipeline_health.py (throughput metrics)
 |           -> kurultai_ledger.py (reads task-ledger.jsonl)
 |           -> kurultai_paths.py (all filesystem paths)
 |       -> neo4j_task_tracker.py (Neo4j metrics)
 |     OUTPUT: agents/{agent}/memory/YYYY-MM-DD.md (appended)
 |
 |-- CHECKPOINT: logs/reflection-status.json
 |
 |-- Phase 2: Performance Reviews (parallel, all 6 agents, 120s timeout)
 |     claude-agent --model haiku /horde-review
 |     OUTPUT: logs/reviews/{agent}-latest.md
 |
 |-- Phase 2.5: Post-Review Analysis (sequential)
 |     reflection_anomaly_scanner.py (30s timeout)
 |       -> Escalation tasks for low scores / unanalyzed failures
 |     parse_rule_compliance.py --auto-deprecate (15s timeout)
 |       -> Updates rule follow/violate counts, deprecates ineffective rules
 |
 |-- Phase 3: Downstream Tier 1 (parallel, independent)
 |     memory_audit.py --fix
 |     cross_agent_rules.py
 |     route_quality_tracker.py
 |     routing_audit_action.py
 |     score_skills.py --hours 2
 |     action_scorer.py --all --hours 2
 |
 |-- Phase 3: Downstream Tier 2 (sequential, depends on score_skills)
 |     update_skill_stats.py
 |
 |-- Phase 3: Downstream Tier 3 (sequential, depends on all above)
 |     kublai-actions.py --trigger kurultai
 |     kublai-initiative.py
 |     claude-agent --model haiku /kurultai-report
 |     generate_hourly_report.py
 |
 '-- OUTPUT: logs/reflection-step-timing.json

:30 run_brainstorm.sh (separate cron job)
 |-- kurultai_brainstorm.py --all --proposal-output proposals/
 |-- kurultai_review.py --expire
 '-- OUTPUT: logs/brainstorm-status.json, proposals/*.md
```

---

## Shared Modules (Foundation Layer)

These modules are imported by most pipeline scripts. They are NOT standalone executables.

### kurultai_paths.py

**Purpose:** Single source of truth for all filesystem paths.

| Export | Value |
|--------|-------|
| `OPENCLAW_DIR` | `~/.openclaw` |
| `AGENTS_DIR` | `~/.openclaw/agents` |
| `MAIN_DIR` | `~/.openclaw/agents/main` |
| `LOGS_DIR` | `~/.openclaw/agents/main/logs` |
| `TASK_LEDGER` | `~/.openclaw/tasks/task-ledger.jsonl` |
| `SCRIPTS_DIR` | `~/.openclaw/agents/main/scripts` |
| `PROPOSALS_DIR` | `~/.openclaw/agents/main/proposals` |
| `BRAINSTORM_LOG` | `logs/kurultai-brainstorm.log` |
| `BRAINSTORM_COOLDOWN` | `logs/brainstorm-cooldown.json` |
| `VALID_AGENTS` | frozenset of 6 agent names |
| `DISPATCH_AGENTS` | list of 5 (excludes kublai) |
| `CLAUDE_AGENT` | `~/.local/bin/claude-agent` |

**Helper functions:** `agent_tasks_dir(agent)`, `agent_workspace_dir(agent)`, `agent_memory_dir(agent)`, `agent_config_path(agent)`

### kurultai_ledger.py

**Purpose:** Centralized read/write for `task-ledger.jsonl` with file locking.

| Function | Lock Type | Description |
|----------|-----------|-------------|
| `append_ledger(entry)` | `LOCK_EX` (exclusive) | Append one JSON event |
| `read_ledger(hours=None)` | `LOCK_SH` (shared) | Read events, optionally filtered by time |

**Consumers:** `pipeline_health.py`, `prepare_reflection_context.py`, `action_scorer.py`, `score_skills.py`, `generate_hourly_report.py`

**Event types in ledger:** `QUEUED`, `ROUTED`, `EXECUTING`, `COMPLETED`, `FAILED`, `RECOVERED`, `SCORED`, `ACTION_SCORED`, `SKILL_OUTCOME`, `SKILL_AGGREGATE`, `EXECUTION_TRACE`, `EXECUTION_DETAIL`, `REFLECT_SUMMARY`, `ARCH_UPDATE_CHECK`, `VERIFIED`, `VERIFICATION_FAILED`

### agents_config.py

**Purpose:** Agent metadata constants (`AGENTS`, `AGENT_ROLES`, `AGENT_MODELS`).

Imported by `meta_reflection.py`, `prepare_reflection_context.py`, `generate_hourly_report.py`, and others.

---

## Script I/O Contracts

### Phase 1: Protocol Reflections

#### meta_reflection.py

**Entry point:** `python3 meta_reflection.py --agent {agent} --hours 1 --protocol`

| Input | Source |
|-------|--------|
| `prepare_reflection_context.generate_context()` | In-process call |
| Neo4j `Task` nodes | `neo4j_task_tracker.get_reflection_data()` |

| Output | Destination |
|--------|-------------|
| Reflection markdown | stdout (captured by `hourly_reflection.sh`) |
| `AgentFeedback` node | Neo4j (if `--submit` flag) |

#### prepare_reflection_context.py

**Entry point:** Called as library by `meta_reflection.py`, or standalone: `python3 prepare_reflection_context.py --agent {agent}`

| Input | Source | Notes |
|-------|--------|-------|
| Agent memory file | `~/.openclaw/agents/{agent}/memory/YYYY-MM-DD.md` | Extracts WHEN/THEN rules, commitments |
| Claude project reflections | `~/.claude/projects/.../memory/{agent}-reflection-*.md` | Fallback for rules if daily memory empty |
| Tock data | `logs/tock/latest.json` | Agent metrics, system state |
| Reflection protocol | `scripts/reflection_protocols/{agent}_protocol.md` | Role-specific questions |
| Capability scores | `logs/capability-scores.json` | From `route_quality_tracker.py` |
| Skill stats | `logs/skill-stats.json` | From `update_skill_stats.py` |
| Task ledger | `~/.openclaw/tasks/task-ledger.jsonl` | Via `kurultai_ledger.read_ledger()` |
| Routing audit cache | `logs/routing-audit-latest.json` | Kublai only |
| Routing overflow log | `logs/routing-overflow.jsonl` | Peer digest, overflow events |
| Neo4j `RuleProposal` nodes | bolt://localhost:7687 | Proposed rules from peers |
| Neo4j `Task` nodes | bolt://localhost:7687 | 7-day failure patterns |

| Output | Destination |
|--------|-------------|
| Compact reflection prompt (~800 tokens) | stdout / returned string |
| `HOURLY_DIGEST` event | Neo4j (pipeline observability) |

**Internal calls:**
- `pipeline_health.format_pipeline_health(agent, hours)` — throughput metrics table
- `get_task_ledger_summary(agent, hours)` — task execution results
- `get_capability_scores_block(agent)` — routing quality scores
- `get_skill_telemetry_block(agent, hours)` — skill performance
- `get_action_quality_block(agent, hours)` — ACTION_SCORED scores
- `get_peer_digest(agent, hours)` — cross-agent activity summary
- `get_routing_audit(hours)` — kublai only

#### pipeline_health.py

**Purpose:** Computes 5 throughput metrics from `task-ledger.jsonl` for injection into reflections.

| Metric | Function | What It Measures |
|--------|----------|-----------------|
| Pending Duration | `pending_duration()` | p50/p95 of QUEUED-to-EXECUTING wait time |
| Recovery Churn | `recovery_churn()` | RECOVERED events / completions ratio |
| Throughput Velocity | `throughput_velocity()` | Current rate vs 6h rolling baseline |
| Bottleneck Index | `bottleneck_index()` | Hours-to-clear per agent, system throughput |
| First-Attempt Success | `first_attempt_success()` | % tasks completed without recovery |

**Input:** `task-ledger.jsonl` (via `kurultai_ledger.read_ledger()`) + filesystem task directories (for pending counts)

**Output:** Formatted markdown table (~150 tokens) returned as string. Includes per-agent table with Pending/Exec/Churn/Rate/H-to-Clear columns.

**Caching:** In-process 10s TTL cache on ledger reads to avoid redundant I/O within a single call.

---

### Phase 2: Performance Reviews

#### hourly_reflection.sh > run_agent_review()

**Per-agent, parallel, 120s timeout.**

| Input | Source |
|-------|--------|
| Last 80 lines of today's memory | `agents/{agent}/memory/YYYY-MM-DD.md` |
| Tock metrics | `logs/tock/latest.json` (parsed via inline Python) |

| Output | Destination |
|--------|-------------|
| Review markdown | `logs/reviews/{agent}-latest.md` |
| Errors | `logs/horde-review-error.log` |

**LLM:** `claude-agent --model haiku /horde-review`

---

### Phase 2.5: Post-Review Analysis (Sequential, between Reviews and Downstream)

These two scripts run sequentially after all `/horde-review` analyses complete but before Tier 1 downstream steps. They close the feedback loop from review outputs back into the system.

#### reflection_anomaly_scanner.py

**Entry point:** `python3 reflection_anomaly_scanner.py [--hours 1] [--dry-run]`
**Timeout:** 30s (via `run_with_timeout`)

Reads `/horde-review` outputs and the task ledger to detect anomalies that need cross-agent escalation. Transforms passive review analytics into proactive task creation.

| Anomaly Type | Trigger | Severity |
|-------------|---------|----------|
| `low_review_score` | Agent review score <= 3/10 | high (<=2) or normal (3) |
| `unanalyzed_failures` | 2+ task failures in window, or 1+ failure with review score <= 4 | high (>=3 failures) or normal |
| `system_wide_low_scores` | 4+ agents scored <= 3/10 (flood gate consolidation) | high |

| Input | Source |
|-------|--------|
| Review files | `logs/reviews/{agent}-latest.md` (skips if >2h stale) |
| Task failures | `task-ledger.jsonl` via `kurultai_ledger.read_ledger()` |
| Escalation cooldowns | `logs/anomaly-escalation-cooldown.json` |

| Output | Destination |
|--------|-------------|
| Escalation tasks | Agent task queues (via `task_intake.create_task()`) |
| Cooldown state | `logs/anomaly-escalation-cooldown.json` |
| Log | `logs/anomaly-scanner.log` |

**Safety guards:**
- `ESCALATION_COOLDOWN_SECONDS = 3600` — won't re-escalate same agent+type within 1h
- `MAX_ESCALATIONS_PER_RUN = 3` — caps individual escalations per cycle
- Flood gate: if 4+ agents have low scores, collapses into one kublai coordination task instead of 4+ individual tasks
- Escalation routing: jochi (analyst) investigates most agents; temujin investigates jochi; jochi investigates kublai

#### parse_rule_compliance.py

**Entry point:** `python3 parse_rule_compliance.py [--agent NAME] [--dry-run] [--auto-deprecate]`
**Timeout:** 15s (via `run_with_timeout`)

Closes the WHEN/THEN rule feedback loop. Reflections ask agents "did you follow rule X?" — this script parses the YES/NO answers back into `rule_registry.py`'s follow/violate counts and auto-deprecates ineffective rules.

| Input | Source |
|-------|--------|
| Reflection outputs | `logs/reflections/` |
| Rule registry | `rule_registry.py` (via `load_rules()`) |
| Compliance state | `logs/rule-compliance-state.json` |

| Output | Destination |
|--------|-------------|
| Updated rule counts | `rule_registry.py` (via `record_evaluation()`, `deprecate_rule()`) |
| Compliance state | `logs/rule-compliance-state.json` |
| Log | `logs/rule-compliance.log` |

**Auto-deprecation thresholds:** Rules with >= 3 evaluations and < 25% follow rate are deprecated.

---

### Phase 3: Downstream Scripts

#### Tier 1 (Parallel, Independent)

| Script | Reads | Writes | Timeout |
|--------|-------|--------|---------|
| `memory_audit.py --fix` | Agent memory files, daily logs | Fixes in-place (dedup, trim) | 30s |
| `cross_agent_rules.py` | Neo4j `Task`, agent memory (rules) | Neo4j `RuleProposal` nodes | 30s |
| `route_quality_tracker.py` | Neo4j `Task` nodes (7d) | `logs/capability-scores.json` | 30s |
| `routing_audit_action.py` | Neo4j routing decisions | `logs/routing-audit-latest.json` | 30s |
| `score_skills.py --hours 2` | Task ledger, agent memory | `SKILL_OUTCOME` + `SKILL_AGGREGATE` ledger events | 30s |
| `action_scorer.py --all --hours 2` | Agent memory, task ledger | `ACTION_SCORED` ledger events | 30s |

#### Tier 2 (Sequential, depends on score_skills)

| Script | Reads | Writes | Timeout |
|--------|-------|--------|---------|
| `update_skill_stats.py` | `SKILL_AGGREGATE` events from ledger | `logs/skill-stats.json` | 30s |

#### Tier 3 (Sequential, depends on all above)

| Script | Reads | Writes | Timeout |
|--------|-------|--------|---------|
| `kublai-actions.py --trigger kurultai` | Reflection data, tock, capability scores | Task files in agent queues | 60s |
| `kublai-initiative.py` | Queue depths, system state | Task files, initiative cooldown | 60s |
| `/kurultai-report` (Haiku) | Various system state | Signal message, log | 120s |
| `generate_hourly_report.py` | Reviews, proposals, Neo4j, tock, step timing, skill stats | `logs/hourly-reports/YYYY-MM-DD-HHMM-reflection-report.md`, Signal message | 60s |

---

### Brainstorming (:30 cron, separate from reflection)

#### run_brainstorm.sh

**Timeout:** 1500s (25 min). Runs independently of reflection pipeline.

| Script | Reads | Writes |
|--------|-------|--------|
| `kurultai_brainstorm.py --all` | Reviews (`logs/reviews/`), tock data, protocols, brainstorm cooldown/rotation state | Proposal files in `proposals/`, `logs/brainstorm-cooldown.json`, `logs/brainstorm-domain-rotation.json` |
| `kurultai_review.py --expire` | Proposals directory, Neo4j proposals | Expired/archived proposals |

**Output:** `logs/brainstorm-status.json` (health heartbeat)

---

## Data Dependency Graph

```
task-ledger.jsonl ─────┬──> pipeline_health.py ──> reflection prompt
   (kurultai_ledger)   |──> action_scorer.py ──> ACTION_SCORED events
                       |──> score_skills.py ──> SKILL_AGGREGATE events
                       |──> prepare_reflection_context.py (task summary)
                       '──> generate_hourly_report.py (report)

tock/latest.json ──────┬──> prepare_reflection_context.py (agent metrics)
                       |──> hourly_reflection.sh (review metrics)
                       '──> generate_hourly_report.py

Neo4j ─────────────────┬──> meta_reflection.py (task metrics)
                       |──> prepare_reflection_context.py (failures, rules)
                       |──> cross_agent_rules.py (rule propagation)
                       |──> route_quality_tracker.py (quality scores)
                       '──> generate_hourly_report.py (proposals, tasks)

reviews/{agent}-latest ─┬──> kurultai_brainstorm.py (brainstorm input)
  (horde-review output)  '──> reflection_anomaly_scanner.py (escalation)

anomaly-escalation-    ──> reflection_anomaly_scanner.py (cooldown gate)
  cooldown.json

rule-compliance-state  ──> parse_rule_compliance.py (dedup state)

capability-scores.json ┬──> prepare_reflection_context.py (injected)
  (route_quality_       '──> kublai-actions.py (routing decisions)
   tracker.py output)

skill-stats.json ──────┬──> prepare_reflection_context.py (injected)
  (update_skill_        '──> kublai-initiative.py (skill-based routing)
   stats.py output)

reflection-status.json ──> hourly_reflection.sh (checkpoint gate)
reflection-step-timing ──> generate_hourly_report.py (pipeline timing)
brainstorm-status.json ──> watchdog-gather.sh (health monitoring)
```

---

## Timeout Budget (420s total for hourly_reflection.sh)

| Phase | Budget | Actual Typical |
|-------|--------|----------------|
| Phase 1: Reflections (6 agents parallel) | 60s | 15-30s |
| Phase 2: Reviews (6 agents parallel, 120s each) | 120s | 40-80s |
| Phase 2.5: Post-review analysis (2 scripts sequential) | 45s | 5-15s |
| Tier 1 downstream (6 scripts parallel, 30s each) | 30s | 5-15s |
| Tier 2 downstream (sequential) | 30s | 2-5s |
| Tier 3 downstream (4 scripts sequential) | 180s | 60-120s |
| **Total** | **420s** | **125-265s** |

The 420s hard timeout is enforced by a background watchdog process that sends `SIGTERM` to the process group.

---

## Key Constants

| Constant | Location | Value | Purpose |
|----------|----------|-------|---------|
| `MAX_ACTIVE_RULES` | `prepare_reflection_context.py` | 7 | Max WHEN/THEN rules per agent |
| `REVIEW_TIMEOUT` | `hourly_reflection.sh` | 120s | Per-agent /horde-review timeout |
| `TIMEOUT_SECONDS` | `hourly_reflection.sh` | 420s | Entire pipeline hard timeout |
| `_CACHE_TTL_S` | `pipeline_health.py` | 10s | In-process ledger cache TTL |
| `MIN_INVOCATIONS` | `cross_agent_rules.py` | 3 | Min rule uses before propagation |
| `MAX_PROPOSALS_PER_CYCLE` | `cross_agent_rules.py` | 2 | Max rule proposals per target per cycle |
| `ESCALATION_COOLDOWN_SECONDS` | `reflection_anomaly_scanner.py` | 3600 | Don't re-escalate same agent+type within 1h |
| `MAX_ESCALATIONS_PER_RUN` | `reflection_anomaly_scanner.py` | 3 | Cap on individual escalation tasks per cycle |
| `MIN_EVALS_FOR_DEPRECATION` | `parse_rule_compliance.py` | 3 | Min evaluations before auto-deprecation |
| `MAX_VIOLATE_RATE_FOR_DEPRECATION` | `parse_rule_compliance.py` | 0.25 | Deprecate rules followed < 25% |
| `BRAINSTORM_TIMEOUT` | `run_brainstorm.sh` | 1500s | Brainstorm pipeline hard timeout |

---

## Troubleshooting

### Pipeline didn't run

1. Check launchd: `launchctl list | grep hourly`
2. Check for stale lock: `ls -la /tmp/hourly-reflection.lock`
3. Check cron logs: `tail -20 logs/hourly_reflection.log`

### Reflections have "No tock data"

Tock data is stale (>45 min) or missing. Check:
- `ls -la logs/tock/latest.json` — is the symlink valid?
- `launchctl list | grep tock` — is tock-gather scheduled?
- Run manually: `bash scripts/tock-gather.sh`

### Reviews all show "unavailable"

- `claude-agent` binary missing or not in PATH: check `~/.local/bin/claude-agent`
- API rate limit: check `logs/horde-review-error.log`
- Timeout: reviews have 120s per agent; check if system is under load

### "No active rules" for an agent

Rules are extracted from daily memory files by `prepare_reflection_context.py`. Check:
1. Does `agents/{agent}/memory/YYYY-MM-DD.md` exist and contain WHEN/THEN lines?
2. Is the `## ACTIVE RULES` section present at the top of the file?
3. Fallback: are there `{agent}-reflection-*.md` files in Claude project memory?

### Downstream scripts silently fail

All downstream scripts are wrapped in `timed_step()` which catches failures and logs them but does NOT fail the pipeline. Check:
- `logs/reflection-step-timing.json` — look for `"status": "failed"` entries
- Individual logs: `logs/memory-audit.log`, `logs/capability-scores.log`, etc.

### Pipeline times out at 420s

The watchdog kills everything at 420s. Common causes:
- /horde-review calls hanging (check API latency)
- `kublai-actions.py` or `kublai-initiative.py` spawning expensive operations
- Fix: check `logs/reflection-step-timing.json` to see which step was slow

### Capability scores stale (>2h)

`prepare_reflection_context.py` skips capability scores older than 2h. This means `route_quality_tracker.py` failed or timed out. Check `logs/capability-scores.log`.

---

## Cross-Tier Incident Runbook

### System at 0% Throughput (all agents stalled)

**Symptoms:** `THROUGHPUT_ANOMALY: EXECUTING_NO_OUTPUT` in tick-summary; tock shows 0 completions across all agents.

1. Check model layer: `grep "model" logs/watchdog.log | tail -5` — look for invalid model providers
2. Check task-watcher: `ps aux | grep task-watcher` — is it running?
3. Check for zombie .executing files: `find ~/.openclaw/agents/*/tasks -name "*.executing*" -mmin +30`
4. Verify Claude Code works: `claude-agent --model claude-opus-4-6 "echo test"` — does it complete?
5. Check `agents_config.py` AGENT_MODELS — all should be `claude-opus-4-6`

### Tick reports degraded but tock/kurultai seem fine

**Likely cause:** Transient error spike or Gateway restart. Check:
1. `tail -20 logs/watchdog.log` — look for `SAFETY_NET_HIT` (indicates bypass in main decision chain)
2. `python3 -c "import json; [print(json.loads(l).get('decision')) for l in open('logs/ticks.jsonl').readlines()[-6:]]"` — trend of last 30min
3. If >3 consecutive `degraded` ticks, investigate root cause

### Tock shows ledger reconciliation mismatches

**Meaning:** Neo4j and filesystem task-ledger.jsonl disagree on completion counts.
1. Check `logs/tock/latest.json` > `ledger_reconciliation.mismatches` for which agents diverge
2. Run manually: `python3 scripts/neo4j-state-sync.py --dry-run` to see what would be reconciled
3. If delta is growing hour-over-hour, check `neo4j_task_tracker.py:sync_check()` for the P1D window bug (fixed 2026-03-07)

### Agent idle despite pending tasks (dispatch starvation)

**Symptoms:** Tock shows `queue_depth > 0` for agent but `running = 0`.
1. Check task-watcher state: `cat logs/task-watcher-state.json | python3 -m json.tool`
2. Look for `.executing` zombies blocking dispatch: `ls ~/.openclaw/agents/{agent}/tasks/*.executing*`
3. Check if agent has active Claude session: `openclaw gateway call status --json | grep {agent}`
4. Verify cron scheduling: `launchctl list | grep task-watcher`

### Reflection pipeline times out at 420s

1. Check `logs/reflection-step-timing.json` — which step was slow?
2. Most common: `/horde-review` calls hanging (API latency). Check `logs/horde-review-error.log`
3. If Tier 3 scripts slow: check if `kublai-actions.py` or `kublai-initiative.py` is spawning expensive operations
4. Emergency: reduce `REVIEW_TIMEOUT` from 120s to 60s in `hourly_reflection.sh`

### Ollama LLM triage always returns FALLBACK

1. Check Ollama is running: `curl http://localhost:11434/api/tags`
2. Check model is pulled: `ollama list | grep Qwen3.5`
3. Check for GPU contention: another process may hold `OllamaLock` — look in `/tmp/ollama-lock*`
4. Impact: tick/tock still work (heuristic fallback), but LLM-driven Kublai dispatch won't fire

---

## Version History

| Version | Date | Change |
|---------|------|--------|
| 2.1 | 2026-03-07 | Added Phase 2.5 documentation: `reflection_anomaly_scanner.py` (post-review escalation) and `parse_rule_compliance.py` (WHEN/THEN rule feedback loop). Updated pipeline diagram, timeout budget, data dependency graph, and key constants table. |
| 2.0 | 2026-03-07 | Expanded to full heartbeat pipeline reference: added Tier 1 (tick) and Tier 2 (tock) operational docs with decision thresholds, companion scripts, output files. Added cross-tier overview, data flow diagram, concurrency control, and incident runbook. Renamed from "Reflection Pipeline" to "Heartbeat Pipeline". |
| 1.0 | 2026-03-06 | Initial release: Tier 3 (kurultai) script inventory, I/O contracts, data flow, troubleshooting |
