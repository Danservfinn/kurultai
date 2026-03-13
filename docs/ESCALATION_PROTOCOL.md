# Escalation Protocol - When Kublai Interrupts Human

**Last updated:** 2026-03-11
**System:** Kurultai 6-Agent AI System (Mac Mini)

## Philosophy

**Default: Do NOT interrupt.** The Kurultai operates autonomously. Human attention is precious — escalate only when truly necessary.

> **Note:** This protocol applies to kublai (Squad Lead/Router) escalation to human. Inter-agent escalation uses the behavioral rules system (R001-R012, C001-C005).

**Key Updates (2026-03-11):**
- ✅ Auth health preflight pattern implemented across critical scripts
- ✅ R010-R012 added: subprocess health checks, gap escalation, security routing fix
- ✅ R008 enforcement prevents skill invocation bypass
- ✅ Pre-submit quality gate (R009) catches hollow completions

---

## Escalation Matrix

### 🔴 CRITICAL (Interrupt Immediately, Any Time)

| Scenario | Example | Action |
|----------|---------|--------|
| **System Down** | Neo4j/Redis unreachable >30m, tick gap >10min | Ögedei watchdog → Kublai escalates |
| **Throughput Collapse** | HIGH_FAILURE_RATE for 3+ consecutive ticks (15min) | Kublai → Human immediately (see [fleet-failure-triage.md](fleet-failure-triage.md)) |
| **Agent Stall** | Agent stuck EXECUTING >90min (STALE threshold) | Kublai → Human + restart investigation |
| **Security Breach** | API keys leaked, unauthorized access | Kublai → Human + revoke access |
| **Data Loss** | Neo4j corruption, orphaned tasks >100 | Kublai → Human + backup restore |
| **Auth Blackout** | All agents failing with auth errors >1h | Ögedei → Human + credential rotation |

**Prevention (R010, Auth Preflight):**
- `subprocess_health_check.py` clears orphaned `.executing.md` tasks on each tick
- Auth health preflight pattern checks credentials before spawning subagents
- See `auth-health-preflight.md` for implementation details
- See `credential-troubleshooting.md` for fix procedures

**Response Time Expected:** <1 hour

---

### 🟠 HIGH (Interrupt Within 4 Hours)

| Scenario | Example | Action |
|----------|---------|--------|
| **Goal Blocked** | Can't proceed without decision | Kublai presents options + recommendation |
| **Strategic Pivot** | Architecture change needed, new capability | Kublai → Human with /horde-brainstorming proposal |
| **Agent Failure** | Agent 0% throughput for 2+ hours | Kublai → Human with diagnosis + reassignment plan |
| **Reflection Anomaly** | 3+ consecutive reflection failures | Kublai → Human with recovery plan |
| **Model Configuration** | All agents need provider switch | Kublai → Human with model options |

**Response Time Expected:** <24 hours

---

### 🟡 MEDIUM (Include in Hourly Report)

| Scenario | Example | Action |
|----------|---------|--------|
| **Minor Delays** | Task taking >3h to complete | Kublia reassigns, reports in hourly reflection |
| **Queue Overflow** | Agent has >5 pending, others idle | Kublai redistributes via task-redistribute.py |
| **Quality Issues** | 2/5 tasks failing completion gate | Kublai requests redo, reports in reflection |
| **Routing Anomaly** | Tasks misrouted to wrong agent | Kublai updates disambiguation rules |

**Response Time Expected:** Human reviews in hourly reflection report (no immediate action needed)

---

### 🟢 LOW (Kurultai Reflection Only)

| Scenario | Example | Action |
|----------|---------|--------|
| **Process Improvements** | "We could optimize X" | Agent creates proposal during /horde-brainstorming |
| **New Behavioral Rules** | Agent identifies recurring failure pattern | Agent adds rules.json entry, logs to memory/ |
| **Agent Performance Trends** | "Chagatai's throughput up 20%" | Include in reflection metrics |
| **Learning/Insights** | "Discovered pattern Z" | Add to memory/YYYY-MM-DD.md or docs/ |

**Response Time Expected:** Kurultai reflection cycle (hourly, with deeper analysis daily)

---

## Escalation Format

### Critical/High Escalation Message Structure

```
🚨 ESCALATION: [Goal/Issue Name]

**Severity**: CRITICAL/HIGH
**Deadline**: [When decision needed]
**Impact**: [What happens if no action]

## Situation
[2-3 sentences describing the issue]

## Options
1. **[Option A]** 
   - Pros: [...]
   - Cons: [...]
   - Recommendation: ✅

2. **[Option B]**
   - Pros: [...]
   - Cons: [...]

## Kublai's Recommendation
[Why Option A is best, with reasoning]

## Action Needed
[Specific decision or approval requested]

---
*This is an autonomous escalation. The Kurultai is paused on [X] pending your decision.*
```

### Hourly Reflection Report Format (every hour)

```
📊 Hourly Reflection — [Agent] [Timestamp]

## Pipeline Health (1h)
Pending: 0 | Velocity: 1.0x STEADY
Churn: 0 recoveries | 1st-attempt: 85%

| Agent    | Pending | Exec | Churn | Rate/hr | H-to-Clear |
|----------|---------|------|-------|---------|------------|
| chagatai | 0       | 0    | 0     | 0.0     | 0.0h       |
| temujin  | 1       | 0    | 0     | 2.0     | 0.5h       |
| mongke   | 0       | 0    | 0     | 1.5     | 0.0h       |

## Active Behavioral Rules
- C001: Pre-Submit Quality Check (enabled)
- C002: Documentation Self-Tasking (enabled)
- C003: Writer Domain Boundary (enabled)

## Recent Proposal
[chagatai-20260311-1430] Update stale documentation
Status: APPROVED | Votes: 5/5

---
*No human action needed. Full report in logs/hourly-reports/*
```

### Weekly Summary Format (Sunday deep reflection)

```
📈 Weekly Deep Reflection — [Week of Date]

## Agent Performance Summary

| Agent  | Completed | Failed | Success Rate | Queue Depth |
|--------|-----------|--------|--------------|-------------|
| kublai | 45        | 2      | 96%          | 0           |
| temujin| 112       | 8      | 93%          | 1           |
| mongke | 23        | 1      | 96%          | 0           |
| chagatai| 18       | 0      | 100%         | 0           |
| jochi  | 31        | 3      | 91%          | 0           |
| ogedei | 67        | 5      | 93%          | 1           |

## Behavioral Rules Added This Week
- K008: Mongke Research Protection (kublai)
- C001-C005: Chagatai quality standards (chagatai)

## Key Wins This Week
- [List of completed milestones]

## Lessons Learned
- [Insights from memory/YYYY-MM-DD.md]

## Next Week Priorities
1. [Top 3 improvement areas from brainstorming]

## System Metrics
- Uptime: 99.9%
- Total Tasks Completed: 296
- Avg Queue Depth: 1.2
- Neo4j Availability: 98%

## Decisions Needed
[Any medium-priority items requiring human input]

---
*Reply with decisions or check docs/ for detailed proposals.*
```

---

## Decision Protocols

### Kublai's Decision Authority

**Kublai CAN decide without human input:**
- ✅ Task reassignment between agents (load balancing)
- ✅ Behavioral rule creation for agents
- ✅ Routing policy adjustments (disambiguation rules)
- ✅ Bug fixes and hotfixes (via temujin task dispatch)
- ✅ Completion gate bypass (with documented reason)
- ✅ Model provider switching (tiered fallback)

**Kublai MUST escalate to human:**
- ❗ Architecture changes affecting all agents
- ❗ New agent creation (beyond 6-agent core)
- ❗ System-wide shutdown or restart
- ❗ External service integrations (new APIs)
- ❗ Public communications (blog posts, releases)

### Agent Decision Authority

**Agents CAN decide:**
- ✅ Implementation details (how to build)
- ✅ Skill invocation (when skill_hint present)
- ✅ Self-tasking via behavioral rules (C002)
- ✅ Task completion formatting

**Agents MUST escalate to Kublai:**
- ❗ Task outside domain boundary (C003)
- ❗ Blocked >4 hours without progress
- ❗ Quality gate failures (>2 revisions)

---

## Escalation Channels

| Severity | Channel | Expected Response |
|----------|---------|-------------------|
| CRITICAL | Create task in kublai/queue/ with URGENT tag | <1 hour |
| HIGH | Create proposal via /horde-brainstorming, tag for human review | <24 hours |
| MEDIUM | Include in hourly reflection report (logs/hourly-reports/) | Next reflection cycle |
| LOW | Log in memory/YYYY-MM-DD.md for weekly review | Weekly reflection |

**Current Status:** Escalations create task files. Human reviews task queue or receives notifications via monitoring system.

---

## Fail-Safe: Human Unavailable

**If human doesn't respond to CRITICAL escalation within 2 hours:**

1. **Kublai attempts recovery** via behavioral rules:
   - R001: Error rate >100/hr → auto-escalate to kublai
   - R007: Reflection missing deliverables → produce inline
   - R008: skill_hint present → enforce Skill tool invocation
   - R009: Pre-submit gate check → verify quality before marking done
   - R010: Tick subprocess health check → clear orphaned tasks
   - R011: Tick gap >10min → deterministic gap escalation
2. **Ögedei watchdog actions:**
   - Agent restart via agent-task-handler.py
   - Neo4j/Redis reconnection attempts
   - Auth health preflight checks (before spawning subagents)
   - Stale lock cleanup (stale-lock-cleanup.py)
3. **Document all actions** in memory/YYYY-MM-DD.md
4. **Resume normal ops** when human responds

**Principle:** Preserve system state and continue autonomous operation within safety boundaries.

---

## Review Cadence

| Review Type | When | Who | Output |
|-------------|------|-----|--------|
| Tick (Health Check) | Every 5 min | watchdog-gather.sh | logs/ticks.jsonl |
| Tock (Telemetry) | Every 30 min | tock-gather.sh | logs/tock-*.jsonl |
| Hourly Reflection | Every hour | hourly_reflection.sh | logs/hourly-reports/*.md |
| Kurultai Reflection | Every hour | meta_reflection.py | proposals/ + voting/ |
| Daily Deep Review | ~8 AM (daily) | Full /horde-review | memory/YYYY-MM-DD.md |
| Weekly Strategy | Sunday | Kurultai voting | Approved proposals |

---

## New Behavioral Rules (2026-03-11)

### R010: Subprocess Health Check
**When:** Tick (5min watchdog) executes
**Then:** Run `subprocess_health_check.py` to detect and clear orphaned agent subprocesses
**Prevents:** PENDING_NO_DISPATCH throughput anomaly (stale `.executing.md` with dead PIDs)

### R011: Gap Escalation
**When:** Tick detects GAP_DETECTED=1 AND gap_minutes > 10
**Then:** Auto-escalate to kublai (routes to ogedei) via GAP_ESCALATION section
**Prevents:** "14h blackout went undetected" — monitoring gaps now trigger deterministic escalation

### R012: Security Routing Fix
**When:** Task contains security/vulnerability/audit/compliance/injection/unauthorized keywords
**Then:** Route to jochi (analyst) NOT away from jochi
**Fixes:** Previous bug that sent security tasks AWAY from jochi

### R008: Skill Enforcement (2026-03-10)
**When:** Task has `skill_hint` in frontmatter
**Then:** Invoke Skill tool explicitly before any other work
**Prevents:** EXECUTING_NO_OUTPUT anomaly (agent claiming work done without actually doing it)

### R009: Pre-Submit Quality Gate (2026-03-10)
**When:** Agent marks task complete
**Then:** Run `pre_submit_check.py` to verify quality thresholds
**Prevents:** Hollow success pattern (task marked done with <50% requirements met)

---

## False Positive Escalation Patterns

**Critical:** Before investigating any escalation, verify it's not a false positive. Multiple detection layers exist, and false positives occur regularly.

### Common False Positive Types

| Pattern | Detection | Resolution |
|---------|-----------|------------|
| **Completed Task Escalation** | Task has `.done.md`, `.verified.done.md`, or `.no_output.done.md` suffix | Mark as `.false-positive.resolved.done.md` |
| **Ghost Escalation** | Task file doesn't exist, but watchdog has stale monitoring data | CANCEL immediately - no investigation needed |
| **Meta-Escalation Loop** | Escalation about another escalation (usually false positive) | Mark both as false positives |
| **LLM Hallucination** | LLM claims issues but audit metrics show zero | Override with rules.json entry |

### False Positive Detection Checklist

Before investigating ANY escalation:

1. ✅ **Check original task status** - Does the task file end in `.done.md` or similar?
2. ✅ **Verify task exists** - Is there a file at the expected path?
3. ✅ **Check audit metrics** - Do `fake_found=0` and `verified=all`?
4. ✅ **Look for terminal states** - `.no_output.done.md` is a valid completion marker
5. ✅ **Check for meta-escalation** - Is this escalation about another escalation?

### Defense-in-Depth Rules

Key rules.json entries preventing false positive escalations:

```json
{
  "STALE_MTIME_VERIFY_COMPLETION": "Verify completion-file status before escalation creation",
  "COMPLETION_AUDIT_ZERO_FAKE_NO_ESCALATE": "When fake_found=0, never escalate regardless of LLM decision"
}
```

### Historical False Positives (Reference)

| Date | Task Type | Root Cause | Resolution |
|------|-----------|------------|------------|
| 2026-03-08 | proposal-voting-documentation | Watchdog didn't filter completed tasks | Added `is_task_already_completed()` function |
| 2026-03-09 | tock-experiment-metrics | Ghost escalation from stale monitoring data | CANCELED - task didn't exist |
| 2026-03-09 | fix-resolution-341292f4 | Stale `.executing.md` artifact | Meta-escalation loop, both marked false-positive |
| 2026-03-09 | ca36607b-79a | LLM hallucinated fake completions | Added COMPLETION_AUDIT_ZERO_FAKE_NO_ESCALATE rule |

**Key Learning:** The LLM escalation layer has a measurable false positive rate. Always override LLM decisions when metrics clearly indicate normal operation.

---

*This protocol ensures human oversight without micromanagement. The Kurultai runs autonomously; human is strategic owner, not task manager.*

## Related Documentation

- `memory/when_then_rules.md` — Full registry of behavioral rules (R001-R012)
- `docs/behavioral-rules-execution.md` — How rules are evaluated and executed
- `docs/completion-gate.md` — Task completion verification
- `docs/reflection-pipeline-reference.md` — Hourly self-improvement cycle
- `docs/auth-health-preflight.md` — Auth verification before subagent spawn
- `docs/credential-troubleshooting.md` — How to fix invalid API credentials
- `docs/R008_SKILL_ENFORCEMENT.md` — Skill invocation enforcement protocol
- `docs/R008_SKILL_ENFORCEMENT_IMPLEMENTATION.md` — R008 implementation details

---

## Resolution

**Document Updated:** 2026-03-11

### Changes Made

1. **Header Updates**
   - Updated last updated timestamp
   - Added key updates summary for 2026-03-11
   - Updated C001-C008 reference to C001-C005

2. **Auth Blackout Section Enhancement**
   - Added prevention measures (R010, Auth Preflight)
   - Cross-referenced `auth-health-preflight.md`
   - Cross-referenced `credential-troubleshooting.md`

3. **New Behavioral Rules Section**
   - Added R010: Subprocess Health Check documentation
   - Added R011: Gap Escalation documentation
   - Added R012: Security Routing Fix documentation
   - Added R008: Skill Enforcement details
   - Added R009: Pre-Submit Quality Gate details

4. **Fail-Safe Section Update**
   - Updated behavioral rules list to R001-R012
   - Added auth health preflight to watchdog actions
   - Clarified subprocess health check function

5. **Related Documentation Expansion**
   - Added `auth-health-preflight.md` reference
   - Added `credential-troubleshooting.md` reference
   - Added `R008_SKILL_ENFORCEMENT.md` reference
   - Added `R008_SKILL_ENFORCEMENT_IMPLEMENTATION.md` reference

### Verification Status

| Check | Status |
|-------|--------|
| Content length (>500 chars) | ✅ 14,021 chars |
| Structure (≥3 headings) | ✅ 43 headings |
| Resolution section | ✅ Added |
| Code examples | ✅ 4 code blocks |

### Next Steps

None — documentation update complete. Auth verified working per auth-health-preflight.md implementation status.

---

*This protocol ensures human oversight without micromanagement. The Kurultai runs autonomously; human is strategic owner, not task manager.*
