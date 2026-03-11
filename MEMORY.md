# Kublai — Coordination Memory

**Role:** Squad Lead / Router
**Model:** zai-coding/glm-5 (dispatches to Claude Code via subprocess)

---

## Coordination Context

- **Human Timezone:** America/New_York
- **Human Contact:** Signal (+19194133445)
- **Heartbeat:** Every 30 minutes
- **Deep Reflection:** Every 6 hours (hours 0, 6, 12, 18)
- **Daily Summary:** 7 AM EST

---

## Task Creation Protocol

**When creating tasks, Kublai must:**
1. **Use task_intake.py** - Creates task file in agent's tasks/ directory
2. **Specify skills** - Include skill_hint in task frontmatter for agent-task-handler
3. **Prefer horde skills** - Default to horde skills when appropriate:
   - `/horde-plan` - Structured implementation plans with dependency tracking
   - `/horde-implement` - Execute plans with quality checkpoints
   - `/horde-review` - Multi-domain critical review (security, perf, architecture)
   - `/horde-test` - Parallel test suite execution
   - `/horde-swarm` - Parallel subagent dispatch (35+ agent types)
   - `/horde-brainstorming` - Structured ideation with diverge/evaluate/converge
   - `/horde-gate-testing` - Integration tests between implementation phases
   - `/golden-horde` - 9 multi-agent patterns (review loop, debate, pipeline, etc.)

**Priority Guidelines:**
- **High:** Urgent, time-sensitive, blocks other work
- **Normal:** Regular tasks, standard priority
- **Low:** Background tasks, idle resource utilization, research tasks

**Example task creation:**
```
python3 scripts/task_intake.py --title 'Task title' --body 'Task description' --agent temujin --priority high --skill_hint /horde-implement
```

---

## Architecture Decisions

- 6-agent Kurultai with independent workspaces
- Gateway heartbeats (30m) for agent check-ins
- heartbeat_master.py daemon (5m) for continuous operation
- Cron jobs under Kublai for high-level tasks
- File-based memory + Neo4j operational memory
- **Task execution via claude-agent subprocess** (not ACP sessions)

### Task Execution Flow

```
task-watcher.py (15s poll)
    └── detects .md task files in agent/tasks/
    └── calls agent-task-handler.py via subprocess
            └── calls claude-agent --workdir ~/.openclaw/agents/{agent}/
                    └── Runs Claude Code CLI in agent workspace
```

**Why subprocess, not ACP:**
- Agent sovereignty — independent workspaces, configs, and execution contexts
- Scale efficiency — no session registry pollution from high-frequency task execution
- Recovery semantics — PID-based tracking (.executing.pid files) matches subprocess model
- Heartbeat integration — tick/tock filesystem scans are direct and reliable

---

## What Works

- Hourly reflections with self-awareness checks
- Subagent spawning for parallel work (Kublai coordination tasks only)
- Task-watcher daemon (15s polling)
- Claude Code via claude-agent subprocess for specialist execution
- PID-based execution tracking (.executing.pid sentinel files)

## What Doesn't Work

- Cross-agent file writing (use Neo4j instead)
- Single cron job for all reflections (broken for non-Kublai)
- Self-answering product questions (always route to specialists)
- ACP sessions for specialist tasks (wrong architecture — use subprocess)

## Known Bugs

### watchdog-gather.sh AGENTS Array Bug (2026-03-08)
**Status:** Task created for ogedei to fix

**Problem:** Line 212 has incorrect agent list:
```bash
AGENTS=("temujin" "mongke" "chagatai" "jochi" "ogedei" "main")
```

**Issues:**
1. Uses `"main"` instead of `"kublai"` — reads scripts directory instead of kublai's task queue
2. Missing `"kublai"` — kublai's pending tasks never counted
3. Missing `"tolui"` — tolui's pending tasks never counted

**Impact:** 9+ consecutive TICK reports with false queue depth alerts, wasting investigation time.

**Fix:** Change to:
```bash
AGENTS=("kublai" "temujin" "mongke" "chagatai" "jochi" "ogedei" "tolui")
```

**Task:** `watchdog-agents-array-fix-1773019945.md` in ogedei's queue

### Task State Filename Detection Bug (2026-03-10) — FIXED
**Status:** Resolved

**Problem:** Multiple scripts used `".executing" in fname` pattern to detect executing tasks. This matched files like `task.executing.done.md` (completed tasks with "executing" in their revision history), causing false-positive EXECUTING_NO_OUTPUT anomalies that persisted for 192 ticks (960 minutes).

**Root Cause:** Task files accumulate state markers in their names during lifecycle:
- `task.md` → pending
- `task.executing.md` → executing
- `task.done.md` → completed
- `task.executing.done.md` → completed after executing (REVISION HISTORY)
- `task.done-abc123.md` → completed with dedup hash

The buggy pattern matched ANY file containing ".executing", not just currently-executing tasks.

**Scripts Fixed (7 total):**
1. `throughput_anomaly.py` — count_executing_tasks(), count_pending_tasks(), count_movable_pending_tasks()
2. `auto_dispatch.py` — list_executing_tasks(), check_completed_dispatches()
3. `kurultai_brainstorm.py` — agent status summary
4. `pipeline_health.py` — task counting
5. `routing_audit.py` — queue state
6. `health_dashboard.py` — queue depth
7. `ogedei-watchdog.py` — pending depth, load balancing

**Fix Applied:**
- For EXECUTING count: Use `fname.endswith(".executing.md")` (exact match)
- For PENDING exclusion: Use `any(marker in fname for marker in ['.done', '.completed', '.resolved', '.failed', '.cancelled', '.stale', '.obsolete'])`

**Task:** `high-1773193398.md` in jochi's queue (regression tests)

### Watchdog LLM Triage Hallucination Bug (2026-03-10) — FIXED
**Status:** Resolved

**Problem:** The LLM triage in watchdog-gather.sh was fabricating psychological/mental health assessments about Kublai (e.g., "exhibiting clear signs of psychological stress (irritability, paranoia)") with zero basis in telemetry data. This caused false HIGH severity alerts.

**Root Cause:** The LLM prompt for tick triage was too open-ended, allowing the model to invent problems not present in the data. The model interpreted a "resolution compliance 0%" formatting warning as a psychological stress indicator.

**Fix Applied:**
1. **Prompt hardening:** Added explicit rules forbidding psychological assessments:
   - "NEVER make psychological/mental health assessments about agents"
   - "ONLY flag technical issues visible in the tick data"
   - "If you mention stress/paranoia/HR/mental health, you are hallucinating"
2. **Output filter:** Added bash filter to catch and reject any hallucinated responses containing keywords: `psychological`, `mental.health`, `stress`, `irritability`, `paranoia`, `HR`, `human.resources`, `therapy`, `counseling`, `burnout`
3. **Logged dismissal:** Added FALSE_POSITIVE_DISMISSAL entry to watchdog.log

**Files Modified:**
- `watchdog-gather.sh` — LLM triage prompt + hallucination filter

**Verification:**
- LLM triage now correctly reports ACTION_NEEDED: no for healthy systems
- Hallucination filter catches any slipped-through psychological assessments

---

## Infrastructure Configuration

### Claude-Agent Wrapper (v2.2)

**Script:** `~/.local/bin/claude-agent`
**Debug Log:** `/tmp/claude_agent_debug.log`

When `claude-agent` wrapper is invoked for task execution, it uses a **multi-tier fallback configuration**.

**Current Configuration (v2.2 - 2026-03-09):**

| Tier | Provider | Model | Base URL | Status |
|------|----------|-------|----------|--------|
| **0** | Anthropic (Primary) | claude-sonnet-4-6 | Default API | **ACTIVE** |
| **1** | Z.AI Fallback | glm-5 | https://api.z.ai/api/anthropic | **ACTIVE** |
| **2** | Alibaba Fallback | qwen3.5-plus | https://coding-intl.dashscope.aliyuncs.com/apps/anthropic | **ACTIVE** |

**Common Settings:**
- `alwaysThinkingEnabled: true`
- `effortLevel: high`
- `skipDangerousModePermissionPrompt: true`
- Full plugin suite (23+ plugins, 90+ skills)

**Behavior Rules:**
1. **Rate limit (429) on Tier 0** → Retry with Tier 1 (Z.AI glm-5)
2. **Rate limit (429) on Tier 1** → Retry with Tier 2 (Alibaba qwen3.5-plus)
3. **Non-rate-limit errors** → Fail immediately with original exit code
4. **All providers exhausted** → Exit with code 429

**Configuration History:**
- **v2.2 (2026-03-09)**: Multi-tier fallback RE-ENABLED per user preference
  - User explicitly requested fallbacks be permanently enabled for claude-agent wrappers
  - Fallback chain: Anthropic → Z.AI (glm-5) → Alibaba (qwen3.5-plus)
  - Ensures task continuity during API rate limits or outages
- **v2.1 (2026-03-08)**: Multi-tier fallback REMOVED to prevent silent model drift
  - Previous fallback chain caused tasks to run on glm-5/qwen3.5-plus when Anthropic API rate-limited
  - This broke Kurultai validation guards and caused fleet-wide stall
  - Tasks failed explicitly on rate limit instead of silently using non-Anthropic models

**Implications for Routing:**
- Rate limits trigger automatic fallback to next tier (no task failure)
- Primary model: Anthropic claude-sonnet-4-6
- Fallback models: glm-5 (Z.AI), qwen3.5-plus (Alibaba)
- **Tolui is EXEMPT** (uses only abliterated model via Ollama)

**Neo4j:** `Configuration:OpenClawConfig {name: 'claude-agent-fallback-chain'}`

---

*Last updated: 2026-03-09 (v2.2 multi-tier configuration ENABLED per user preference, Neo4j stored)*
