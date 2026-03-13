# Routing Pipeline Reference

**Version:** 1.3
**Date:** 2026-03-12
**Author:** Chagatai (Kurultai Writer)
**Domain:** routing_pipeline
**Status:** Reference Documentation

---

## Overview

This document maps the complete routing decision pipeline — the 8-stage process that determines which agent receives a task. It complements `task-dispatch-reference.md` (which covers post-routing execution) and the diagnostic guides (`routing-idle-agent-bypass-diagnostic.md`, `routing-overflow-gap-analysis.md`).

**Quick links:**
- [Pipeline Stages](#pipeline-stages)
- [Stage Details](#stage-details)
- [Data Structures](#data-structures)
- [Debugging Routing Decisions](#debugging-routing-decisions)
- [Known Failure Modes](#known-routing-failure-modes)

---

## Pipeline Stages

```
┌─────────────────────────────────────────────────────────────┐
│  TASK ARRIVES (title, body, priority, agent?, skill_hint?)  │
└──────────────────────────┬──────────────────────────────────┘
                           │
               ┌───────────▼────────────┐
          S0   │  Pause Pattern Check   │  Reject if matches PAUSED_TASK_PATTERNS
               └───────────┬────────────┘
                           │
               ┌───────────▼────────────┐
          S1   │  Depth Validation      │  Reject if depth >= MAX_TASK_DEPTH (3)
               └───────────┬────────────┘
                           │
               ┌───────────▼────────────┐
          S2   │  Disambiguation Rules  │  First-match-wins hard rules (_DISAMBIGUATION)
               │  → @Mention Parse      │  If title starts with @agent, lock to that agent
               │  → Queue-Penalized     │  Otherwise: keyword scores × queue penalty
               │    Keyword Routing     │
               └───────────┬────────────┘
                           │
               ┌───────────▼────────────┐
          S3   │  Skill Hint Detection  │  Auto-detect skill from (agent, keyword) table
               └───────────┬────────────┘
                           │
               ┌───────────▼────────────┐
          S4   │  Skill-Agent Lock      │  Reroute if skill belongs to different agent
               └───────────┬────────────┘
                           │
               ┌───────────▼────────────┐
          S5   │  Skill Overflow Bypass │  If locked agent overloaded → route to alternate
               └───────────┬────────────┘
                           │
               ┌───────────▼────────────┐
          S6   │  Domain Classification │  Classify task domain (research, impl, ops, ...)
               │  + Kublai Self-Absorb  │  Kublai takes coordination tasks when idle
               └───────────┬────────────┘
                           │
               ┌───────────▼────────────┐
          S7   │  Fleet Credential Check│  Reject ALL tasks if entire fleet has bad creds
               └───────────┬────────────┘
                           │
               ┌───────────▼────────────┐
          S8   │  Load Balancing        │  find_best_idle_agent() — domain-compatible
               │  + Redistribution Check│  alternate with lowest queue depth
               └───────────┬────────────┘
                           │
               ┌───────────▼────────────┐
               │  AGENT SELECTED        │  → Dedup → Neo4j create → Filesystem write
               └────────────────────────┘
```

---

## Stage Details

### S0: Pause Pattern Check

**Code:** `create_task()` lines 2600–2606
**Purpose:** Reject tasks matching paused product patterns (e.g., "llm.survivor").

```python
PAUSED_TASK_PATTERNS = ["llm.survivor", "llmsurvivor", "LLM Survivor", "llm-survivor"]
```

**Outcome:** Returns `None` immediately. Task never enters the pipeline.

### S1: Depth Validation

**Code:** `create_task()` lines 2608–2611
**Purpose:** Prevent exponential subtask growth.

| Depth | Meaning | Result |
|-------|---------|--------|
| 0 | Root task (human/cron) | Allowed |
| 1–2 | Subtask chain | Allowed |
| 3+ | Too deep | **REJECTED** |

### S2: Agent Selection (Keyword + Queue Penalty)

**Code:** `create_task()` lines 2613–2628

Three paths in priority order:

#### Path 0: Disambiguation Rules (first-match-wins)
**Code:** `task_intake.py` `_DISAMBIGUATION` lines 274–350

**Before** any keyword scoring, checks hard rules:
- `status + implement/progress/next` → kublai (project status)
- `investigate + calendar/cron/backup` → ogedei (ops, not research)
- `enhance + config` → jochi (analysis, not research)
- `bidirectional + linking` → temujin (dev, not research)
- `"design research competitors"` (phrase) → mongke (market research)
- See [Keyword Collision failure mode](#4-keyword-collision-research-vs-implementation) for full table

If a rule matches, routing is **immediate** — skips keyword scoring entirely.

#### Path A: @Mention (explicit)
If title starts with `@temujin`, `@mongke`, etc., the task is locked to that agent. Queue depth is ignored. The mention prefix is stripped from the title.

#### Path B: Queue-Penalized Keyword Routing (auto)
**Function:** `route_with_queue_penalty()`
**Code:** lines 1709–1761

1. **Score each agent** via `get_agent_scores(text)` — counts keyword matches from `AGENT_KEYWORDS` (defined in `kurultai_paths.py`).
2. **Apply queue penalty:**

| Queue Depth | Penalty Formula | Effect |
|-------------|----------------|--------|
| < LOW (2) | None (×1.0) | Full score |
| LOW–HIGH (2) | × 0.95^depth | Soft reduction |
| >= HIGH (2) | × 0.9^(depth−HIGH+1) | Hard reduction |

3. **Select agent** with highest penalized score.

**Key insight:** An agent with a keyword score of 5 and queue depth of 4 gets penalized to `5 × 0.9^2 = 4.05`, potentially losing to a lower-scoring agent with an empty queue.

### S3: Skill Hint Detection

**Code:** `create_task()` lines 2630–2634
**Function:** `detect_skill_hint(agent, title)`

Looks up `(agent, keyword)` pairs in `SKILL_HINTS` table:

| Agent + Keyword | Skill Hint |
|-----------------|------------|
| temujin + "design" | `/horde-brainstorming` |
| temujin + "implement" | `/horde-implement` |
| mongke + "research" | `/horde-learn` |
| chagatai + "blog" | `/content-research-writer` |
| jochi + "review" | `/code-reviewer` |
| ogedei + "health" | `/kurultai-health` |

Full table: `task_intake.py` lines 821–863.

**Skip:** If caller provided an explicit `skill_hint`, auto-detection is skipped.

### S4: Skill-Agent Lock (Reroute)

**Code:** `create_task()` lines 2636–2649
**Map:** `_SKILL_OWNER`

If the detected skill has a canonical owner different from the currently selected agent, the task is rerouted:

```
Example: Task keywords match ogedei, but skill "/horde-implement" → temujin
Result: Rerouted to temujin
```

This overrides the S2 keyword score. The task is now **skill-locked** — load balancing (S8) will not override it unless the agent is critically overloaded.

### S5: Skill Overflow Bypass

**Code:** `create_task()` lines 2651–2678
**Function:** `should_bypass_skill_lock()`
**Map:** `_SKILL_CAPABLE_ALTERNATES`

If the skill-locked agent's queue depth >= adaptive HIGH threshold (default 2), routes to a capable alternate:

| Skill | Alternates |
|-------|-----------|
| `/horde-brainstorming` | mongke, jochi, chagatai |
| `/horde-implement` | ogedei |
| `/horde-debug` | jochi, ogedei |
| `/horde-review` | jochi |
| `/horde-plan` | mongke, chagatai |
| `/kurultai-health` | jochi |
| `/code-reviewer` | temujin |
| `/generate-tests` | temujin |
| `/content-research-writer` | mongke, tolui |
| `/changelog-generator` | mongke, tolui |
| `/horde-learn` | jochi, chagatai |

**Not in map = no overflow.** Tasks for skills without alternates stay locked regardless of queue depth.

### S6: Domain Classification + Self-Absorb

**Code:** `create_task()` lines 2680–2698
**Function:** `classify_task_domain(title, skill_hint)`

Classification priority:
1. **Skill hint → domain** via `SKILL_DOMAIN_MAP` (e.g., `/horde-learn` → "research")
2. **Keyword scoring** across `DOMAIN_KEYWORDS` — highest count wins
3. **Default:** "implementation"

Valid domains: `research`, `implementation`, `ops`, `documentation`, `strategy`, `analysis`, `autoresearch`, `completion`, `escalation`

**Kublai Self-Absorb:** If kublai is idle and a coordination task is routed elsewhere, kublai absorbs it (lines 2687–2698).

### S7: Fleet Credential Check

**Code:** `create_task()` lines 2700–2756

Checks all 6 dispatch agents (`temujin, mongke, chagatai, jochi, ogedei, tolui`). If ALL have invalid credentials, the task is rejected and a human alert is written to `ACTIVE_ALERTS.txt`.

### S8: Load Balancing

**Code:** `create_task()` lines 2758–2807
**Function:** `find_best_idle_agent()`

**Conditions to skip load balancing:**
- Agent is `kublai` or `subagent`
- Task was @mentioned to a specific agent
- Task is skill-locked (unless critically overloaded)

**Process:**
1. Get queue depths for all agents
2. Filter to **domain-compatible** agents via `DOMAIN_AGENT_COMPATIBILITY`
3. Exclude agents in `_NO_OVERFLOW_TARGETS` (kublai, tolui)
4. Select agent with lowest queue depth that is domain-compatible

**Domain compatibility matrix:**

| Domain | Compatible Agents |
|--------|------------------|
| research | mongke, jochi, tolui |
| implementation | temujin, ogedei, jochi, tolui |
| ops | ogedei, temujin, jochi, tolui |
| documentation | chagatai, mongke, tolui |
| strategy | temujin, kublai, ogedei, chagatai |
| analysis | jochi, mongke, kublai, tolui |
| autoresearch | mongke, jochi, chagatai |
| completion | kublai, jochi, ogedei, temujin, tolui |
| escalation | kublai, ogedei, jochi |

**Critical override:** Even for explicitly-routed tasks, if the agent's queue >= adaptive CRITICAL threshold (8), load balancing activates.

### Credential Validation in Load Balancing (2026-03-09)

**Code:** `find_best_idle_agent()` lines 1477-1483

Before routing overflow to an alternate agent, the system validates credentials:

```python
alt_valid, alt_error = check_agent_credentials(agent)
if not alt_valid:
    print(f"LOAD_BALANCE_CREDENTIAL_BLOCK: {agent} has invalid credentials")
    continue  # Skip this agent, try next
```

**Impact:** Prevents tasks from routing to agents with expired/invalid API credentials. If all dispatch agents have invalid credentials, the task is rejected and a CRITICAL escalation is created for ogedei to fix fleet-wide credentials.

**Validation method:** `check_agent_credentials()` — checks for valid `sk-ant-` prefix in agent's `settings.json`.

---

## Data Structures

### AGENT_KEYWORDS (kurultai_paths.py)

Keyword lists used in S2 scoring. Key agents:
- **temujin:** code, build, implement, fix, deploy, design, architect, brainstorm...
- **mongke:** research, discover, competitor, market, trend, study, benchmark...
  - **AI/LLM research (2026-03-11):** llm, gpt, claude, anthropic, openai, alibaba, z.ai, dashscope, model comparison, ai model, language model, embedding, vector, rag, model benchmark, ai pricing, api pricing comparison, provider comparison, model research, ai research, llm evaluation, model capabilities, context window, token limit, rate limit, model features, ai provider
- **chagatai:** write, document, blog, content, changelog, draft, summarize...
- **jochi:** test, verify, audit, review, security, debug, scan, vulnerability...
- **ogedei:** monitor, health, restart, backup, alert, cron, watchdog, cleanup...

### Adaptive Thresholds

| Threshold | Default Value | Purpose |
|-----------|---------------|---------|
| LOW | 2 | Soft penalty starts |
| HIGH | 2 | Hard penalty + overflow bypass |
| CRITICAL | 8 | Force load-balance even for explicit routes |

Thresholds adapt based on fleet-wide queue state via `get_adaptive_thresholds()`.

### Routing Decision Log

All routing decisions are appended to `logs/routing-decisions.jsonl`:

```json
{
  "timestamp": "2026-03-10T02:00:00",
  "title": "Research competitor pricing",
  "dest": "mongke",
  "method": "queue_penalized",
  "scores": {"temujin": 0, "mongke": 5, "chagatai": 0, ...},
  "queue_depths": {"temujin": 2, "mongke": 0, ...},
  "idle_agents": ["chagatai", "mongke"]
}
```

---

## Debugging Routing Decisions

### Why did task X go to agent Y?

```bash
# Find the routing decision for a specific task
grep "task title substring" logs/routing-decisions.jsonl | python3 -m json.tool | tail -30
```

Check the `method` field:
- `queue_penalized` — S2 keyword+queue routing
- `direct_mention` — S2 @mention
- `skill_reroute` — S4 skill ownership override
- `skill_overflow_bypass` — S5 overflow to alternate
- `self_absorb` — S6 kublai took it
- `load_balance` — S8 redirected to lower-queue agent

### Why is an agent idle with tasks in the system?

Check domain compatibility (S8):
```bash
# See what domains recent tasks have
jq -r '.domain' logs/routing-decisions.jsonl | tail -50 | sort | uniq -c | sort -rn
```

If most tasks are `implementation`/`ops`, chagatai (documentation-only) will never receive them.

### Why isn't skill overflow working?

Check if the skill is in `_SKILL_CAPABLE_ALTERNATES` (S5). If not, overflow cannot fire.

```bash
grep "_SKILL_CAPABLE_ALTERNATES" scripts/task_intake.py | head -20
```

---

## Known Routing Failure Modes

### 1. Sticky Routing (Temujin Bias)

**Cause:** Temujin has the broadest keyword set. Tasks with generic terms ("create", "fix", "build") always score highest for temujin.
**Mitigation:** Queue penalty (S2) reduces temujin's score when queue > 2. Skill overflow (S5) redirects when queue > 3.
**Monitor:** Check `logs/routing-decisions.jsonl` for temujin routing rate >60%.

### 2. Domain Starvation (Idle Writer/Researcher)

**Cause:** System-generated tasks (escalations, health checks) are ops/implementation domain. Chagatai and mongke receive zero tasks when all work is internal.
**Mitigation:** Behavioral rules trigger self-generated documentation tasks after 2h idle.
**Monitor:** `chagatai: pending=0 executing=0` for >2 hours.

### 3. Skill Lock Without Overflow

**Cause:** A skill with no entry in `_SKILL_CAPABLE_ALTERNATES` forces all matching tasks to one agent regardless of queue depth.
**Fix:** Add the skill to `_SKILL_CAPABLE_ALTERNATES` with appropriate alternates.

### 4. Keyword Collision (Research vs. Implementation)

**Cause:** Words like "investigate" and "explore" appear in both mongke (research) and temujin (implementation) keyword lists.

**Mitigation:** Disambiguation rules (`_DISAMBIGUATION`, lines 274–350) run BEFORE keyword scoring. Two syntaxes:

| Syntax | Example | Match Rule |
|--------|---------|------------|
| Set `{"word1", "word2"}` | `{"investigate", "calendar"}` | Contains ALL words (any order) |
| String `"phrase words"` | `"design research competitors"` | Contains phrase in order |

**First-match-wins:** Rules are checked in array order. Earlier rules block later ones.

**Mongke research protection (2026-03-09, updated 2026-03-11):** Blocks non-research tasks from routing to mongke:

| Rule Pattern | Target | Rationale |
|--------------|--------|-----------|
| `investigate calendar/cron/backup/notification` | ogedei | Calendar/backup ops → ops, not research |
| `enhance config` | jochi | Config enhancement → analysis |
| `bidirectional linking` | temujin | Dev/testing → dev |
| `design research competitors/market/trend/pricing` | mongke | Actual market research → mongke |
| `design research` (generic) | temujin | Design tasks (not market research) → dev |
| `investigate model capabilities` / `investigate ai model` / `investigate llm` | mongke | AI/LLM model research (2026-03-11) |

**Monitor:**
```bash
# Verify only actual research routes to mongke
grep '"dest":"mongke"' logs/routing-decisions.jsonl | jq -r '.title'

# Check validation script
python3 scripts/validate_mongke_routing.py
```

---

## Related Documentation

- `routing-audit-response-guide.md` — **How to interpret and act on routing audit data** (issue matrix, fix recipes, escalation thresholds)
- `task-dispatch-reference.md` — Post-routing execution pipeline
- `routing-overflow-gap-analysis.md` — Skill overflow configuration details
- `routing-idle-agent-bypass-diagnostic.md` — Idle agent bypass diagnosis
- `architecture.md` — System architecture overview
- `state-management-reference.md` — State management across Neo4j + filesystem

---

## Orphaned / Unused Routing Scripts

| File | Status | Notes |
|------|--------|-------|
| `scripts/routing_engine.py` | **NOT IN USE** | Abandoned refactoring attempt. Contains TODO placeholders for load balancer and circuit breaker integration. Not imported by any active script. |
| `scripts/_archived/task-router.py` | Archived | Predecessor to current pipeline. |

**Do NOT use `routing_engine.py` for routing decisions.** It is not integrated with the active pipeline in `task_intake.py`.

## Source Files (Active Pipeline)

| File | Lines | Purpose |
|------|-------|---------|
| `scripts/task_intake.py` | 2569–2810 | `create_task()` — full pipeline |
| `scripts/task_intake.py` | 1709–1761 | `route_with_queue_penalty()` — S2 scoring |
| `scripts/task_intake.py` | 784–817 | `_SKILL_CAPABLE_ALTERNATES` — S5 overflow map |
| `scripts/task_intake.py` | 821–863 | `SKILL_HINTS` — S3 skill detection |
| `scripts/task_intake.py` | 92–102 | `DOMAIN_AGENT_COMPATIBILITY` — S8 matrix |
| `scripts/task_intake.py` | 171–198 | `classify_task_domain()` — S6 classification |
| `scripts/kurultai_paths.py` | 37–67 | `AGENT_KEYWORDS` — S2 scoring keywords |
| `scripts/llm_routing_judge.py` | — | LLM fallback routing (when keyword scoring is ambiguous) |

---

**Document Metadata:**
- Author: Chagatai (Writer)
- Domain: routing_pipeline
- Last updated: 2026-03-12
- v1.3 changes: Added link to `routing-audit-response-guide.md` in Related Documentation
- v1.2 changes: Added "Orphaned / Unused Routing Scripts" section to clarify routing_engine.py status
- v1.1 changes: Added AI/LLM research keywords, credential validation details
- Reflection cycle: 2026-03-12 03:00
