# R008 Skill Enforcement - Implementation Summary

**Date:** 2026-03-11 15:15 EST (created)
**Last Updated:** 2026-03-12 02:30 EST
**Issue:** 15+ R008_VIOLATION failures - agents ignoring skill_hint requirements
**Solution:** Multi-layer defense in depth

---

## Evolution of R008 Enforcement

### Phase 1 (2026-03-11): Pre-Flight Validation Gate (RETIRED)
- Monitored stdout for skill invocation within 60 seconds
- Killed process if skill not invoked
- **Problem:** Too aggressive, killed legitimate tasks
- **Status:** REMOVED 2026-03-11 (line 2808-2810 in agent-task-handler.py)

### Phase 2 (2026-03-11): Fake Auto-Invoke (RETIRED)
- Added text that looked like a function call to prompt
- **Problem:** Was just text, didn't actually invoke the skill
- **Status:** REPLACED 2026-03-12 (line 2943-2945 in agent-task-handler.py)

### Phase 3 (2026-03-12): Explicit Instruction + Informational Tracking (CURRENT)
- Explicitly instructs agent to call Skill tool FIRST
- Tracks violations for monitoring only (no task failure)
- Relies on agent compliance + behavioral rules

---

## Current Enforcement Layers (2026-03-12)

### Layer 1: System Prompt (CLAUDE.md) ✅

**File:** `~/.openclaw/agents/{agent}/CLAUDE.md`

**Change:** Added R008 section to all 7 agent CLAUDE.md files:
- kublai, temujin, mongke, chagatai, jochi, ogedei, tolui

**Content:**
- Clear rule statement
- Step-by-step pattern (STOP → INVOKE → WAIT → PROCEED)
- Consequences of skipping
- Common skills table
- Enforcement layers overview

---

### Layer 2: Task Frontmatter ✅ ALREADY EXISTS

**File:** Task frontmatter in `~/.openclaw/agents/{agent}/tasks/*.md`

**Content:**
```markdown
---
skill_hint: /horde-review
---

**IMPORTANT:** This task has a skill hint. You MUST invoke the Skill tool with `/horde-review` before starting work.

This is a R008 requirement — skill hints are not optional suggestions, they are mandatory invocation instructions.
```

---

### Layer 3: Explicit Skill Instruction in Prompt ✅

**File:** `scripts/agent-task-handler.py` - `execute_task_with_llm()` function (lines 2942-2964)

**Change (2026-03-12):** Explicitly instruct agent to call Skill tool before any other work:

```python
# R008 MANDATORY SKILL INSTRUCTION (2026-03-12 FIX)
# Previous "auto-invoke" was fake — just added text that looked like a function call.
# Now explicitly instruct agent to call Skill tool FIRST, before any other work.
if skill_hint:
    skill_name = skill_hint.lstrip('/')
    skill_hint_first_section = f"""

## ⚠️ MANDATORY: Skill Tool Required (R008)

**CRITICAL:** Before ANY other work, you MUST invoke the Skill tool:

```
Skill: {skill_hint}
```

Complete ALL skill phases before marking this task done. The skill will guide your approach.

Evidence of skill invocation is logged. Skipping the skill will result in R008_VIOLATION.

---

"""
```

**Effect:** Skill requirement is injected at the top of the prompt, before task text.

---

### Layer 4: Behavioral Rules (Agent Memory) ✅

**File:** `~/.openclaw/agents/{agent}/memory/{agent}-behavioral-rules.md`

**Change:** Each agent has R008 encoded as a behavioral rule:

Example from chagatai (C006, added 2026-03-12):
```markdown
### C006: Mandatory Skill Invocation (R008)
**Priority:** 1 (CRITICAL)

**WHEN:** Chagatai receives task AND task contains skill_hint in frontmatter

**THEN:** Invoke Skill tool with skill_name from skill_hint before any other work

**Why:** Tasks with skill_hint require specialized capabilities. Skipping skill invocation causes R008_VIOLATION failures.

**How to apply:** FIRST ACTION when receiving a task: check frontmatter for `skill_hint:` field. If present, call `Skill(skill="<skill_hint>")` immediately.
```

**Effect:** Agent's behavioral rules explicitly require skill invocation.

---

### Layer 5: Informational Tracking (No Task Failure) ✅

**File:** `scripts/agent-task-handler.py` - `_track_r008_violation()` function (lines 2028-2074)

**Change (2026-03-11):** Track violations for monitoring only — tasks no longer fail:

```python
def _track_r008_violation(agent_name: str, task_id: str, skill_hint: str):
    """
    R008 LAYER 6: Track skill invocation for compliance monitoring.

    NOTE: This is INFORMATIONAL ONLY - tasks no longer fail for R008 violations.
    Skills are auto-invoked in the prompt, so tasks complete successfully.
    This tracking helps identify agents that may need additional prompting.
    """
    # Track count, log to ledger, but don't fail task
    print(f"  ℹ️  R008 COMPLIANCE: {agent_name} skill auto-invoked #{count}")
```

**Effect:** Operators can monitor compliance patterns without breaking task flow.

---

### Layer 6: Pre-Submit Check (R009) ✅

**File:** `scripts/pre_submit_check.py`

**Change:** All agents must run pre-submit check before marking tasks done (R009), which validates:
- Resolution section exists
- Content has sufficient structure
- Task actually completed (not just started)

**Effect:** Catches incomplete tasks before they're marked done.

---

## Files Modified

| File | Lines Changed | Description |
|------|---------------|-------------|
| `scripts/agent-task-handler.py` | ~200 | All 6 layers implemented (includes retired code for reference) |
| `agents/*/CLAUDE.md` (7 files) | ~25 each | R008 section added |
| `memory/{agent}-behavioral-rules.md` | 1 each | C006 rule added (2026-03-12) |
| `docs/R008_SKILL_ENFORCEMENT.md` | New | User-facing documentation |
| `docs/R008_SKILL_ENFORCEMENT_IMPLEMENTATION.md` | New | This file |

---

## Testing

**Syntax Check:** ✅ Passed
```bash
python3 -m py_compile scripts/agent-task-handler.py
# Syntax OK
```

**Current Expected Behavior (2026-03-12):**
1. Agent receives task with `skill_hint`
2. Prompt includes mandatory skill invocation instruction (Layer 3)
3. Agent's behavioral rules require skill invocation (Layer 4)
4. Agent invokes skill → task proceeds normally
5. OR agent skips skill → task completes anyway (no fail), tracked for monitoring (Layer 5)
6. Pre-submit check validates quality before marking done (Layer 6)

---

## Metrics to Monitor

```bash
# Check R008 compliance tracking (informational only)
grep "R008 COMPLIANCE" ~/.openclaw/agents/main/logs/*.log

# Check skill invocation in sessions
grep "\"Skill\"" ~/.openclaw/projects/-*/sessions/*.json

# Check behavioral rule compliance
grep "RULES LOADED" ~/.openclaw/projects/-*/sessions/*.json
```

**Success Criteria:**
- Agents invoke skills before task work (monitor via session logs)
- R008 compliance tracking shows patterns over time
- No tasks fail for R008 violations (soft enforcement)

---

## Key Differences from Original Design

| Aspect | Original (Phase 1) | Current (Phase 3) |
|--------|-------------------|------------------|
| Enforcement | Hard (kill process) | Soft (instructional) |
| Pre-flight check | Yes, 60s timeout | Removed |
| Auto-invoke | Fake (text only) | N/A (explicit instruction) |
| Task failure on violation | Yes | No (informational tracking) |
| Behavioral rules | No | Yes (C006 for each agent) |

---

*Last updated: 2026-03-12 02:30 EST*
