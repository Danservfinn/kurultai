# R008: Mandatory Skill Invocation

## Overview

R008 is a **critical requirement** that ensures agents invoke required skills before proceeding with task execution. Tasks with `skill_hint:` in their frontmatter MUST invoke that skill as their first action.

## Why R008 Exists

Skills provide specialized capabilities that agents need to complete tasks correctly:
- `/horde-review` - Critical analysis across multiple dimensions
- `/horde-implement` - Structured implementation with quality checkpoints
- `/horde-debug` - Methodical root cause analysis
- `/horde-learn` - Research and insight extraction
- `/kurultai-health` - System health assessment

Skipping skill invocation leads to:
- Incomplete task execution
- Missed quality checks
- Poor quality outputs
- Wasted compute resources

## Current Enforcement Approach (2026-03-12)

**IMPORTANT:** R008 enforcement changed significantly in March 2026. The original "hard enforcement" (killing tasks that didn't invoke skills) was replaced with "soft enforcement" (instructional + tracking).

### Soft Enforcement Philosophy

**Old approach (RETIRED):**
- Monitor stdout for skill invocation
- Kill task if skill not invoked within 60 seconds
- Problem: Too aggressive, killed legitimate tasks

**New approach (CURRENT):**
- Explicit instruction in prompt
- Behavioral rules require compliance
- Informational tracking only (no task failure)
- Pre-submit quality gate (R009)

---

## Enforcement Layers (Current)

### Layer 1: System Prompt (CLAUDE.md)

Every agent's CLAUDE.md includes R008 requirements with clear instructions:
- STOP when you see `skill_hint`
- INVOKE the skill immediately
- WAIT for skill output
- PROCEED with task

### Layer 2: Task Frontmatter

Tasks include prominent skill invocation instructions:

```markdown
---
skill_hint: /horde-review
---

**IMPORTANT:** This task has a skill hint. You MUST invoke the Skill tool with `/horde-review` before starting work.
```

### Layer 3: Explicit Prompt Instruction

The task handler injects mandatory skill instruction at the top of every prompt with `skill_hint`:

```
## ⚠️ MANDATORY: Skill Tool Required (R008)

**CRITICAL:** Before ANY other work, you MUST invoke the Skill tool:

Skill: /horde-review

Complete ALL skill phases before marking this task done.
```

### Layer 4: Behavioral Rules

Each agent has R008 encoded as a behavioral rule (e.g., chagatai's C006):

```markdown
### C006: Mandatory Skill Invocation (R008)
**Priority:** 1 (CRITICAL)

WHEN: Chagatai receives task AND task contains skill_hint in frontmatter
THEN: Invoke Skill tool with skill_name from skill_hint before any other work
```

### Layer 5: Informational Tracking

R008 compliance is tracked for monitoring purposes only — tasks do NOT fail for R008 violations. This helps identify agents that may need additional prompting without breaking task flow.

### Layer 6: Pre-Submit Check (R009)

All agents must run `pre_submit_check.py` before marking tasks done, which validates:
- Resolution section exists
- Content has sufficient structure
- Task actually completed (not just started)

---

## For Agents

When you receive a task with `skill_hint:`:

1. **STOP** - Do not read the task body yet
2. **INVOKE** - Call `Skill(skill="<skill_hint>")` as your FIRST action
3. **WAIT** - Let the skill complete and provide its output
4. **PROCEED** - Only then continue with the task

**Pattern:**
```
User: [task with skill_hint: /horde-review]
Assistant: Skill(skill="/horde-review")
[skill output appears]
Assistant: [now proceed with task]
```

**Consequence of Skipping:**
- Under soft enforcement, task will still complete
- Violation is logged for monitoring
- Repeated violations may trigger behavioral rule review

---

## For Operators

### Monitoring R008 Compliance

```bash
# Check R008 compliance tracking (informational only)
grep "R008 COMPLIANCE" ~/.openclaw/agents/main/logs/*.log

# Check skill invocation in sessions
grep "\"Skill\"" ~/.openclaw/projects/-*/sessions/*.json

# Check behavioral rule compliance
grep "RULES LOADED" ~/.openclaw/projects/-*/sessions/*.json
```

### Understanding the Logs

| Event Type | Meaning | Severity |
|------------|---------|----------|
| `R008_COMPLIANCE` | Skill was auto-invoked via prompt instruction | INFO |
| `RULES LOADED` | Agent loaded behavioral rules (including R008) | INFO |

**Note:** Under soft enforcement, there are no R008_VIOLATION failures. Tracking is informational only.

---

## History

| Date | Change | Impact |
|------|--------|--------|
| 2026-03-10 | R008 rule created | Initial hard enforcement |
| 2026-03-11 | Pre-flight check added | 60s timeout for skill invocation |
| 2026-03-11 | Pre-flight removed | Too aggressive, killed legitimate tasks |
| 2026-03-12 | Soft enforcement | Explicit instruction + tracking only |
| 2026-03-12 | Behavioral rules added | C006 for each agent |

---

*Last updated: 2026-03-12 02:30 EST*
