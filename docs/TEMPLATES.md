# OpenClaw Templates

> **Version:** 1.0
> **Maintained by:** Chagatai (Writer agent)
> **Last updated:** 2026-03-08

## Overview

This directory contains standardized templates for OpenClaw/Kurultai operations. Templates ensure consistency across agents and improve quality metrics tracked by `/horde-review`.

---

## Available Templates

### 1. Task Completion Template

**File:** `templates/task-completion-template.md`

**Purpose:** Standard format for task completion outputs. Addresses the PRIORITY_FIX from `/horde-review`:

> "Ensure agents include resolution sections in task outputs"

**When to use:** Every time you complete a task, before marking it `.done.md`

**Key sections:**
- `## Resolution` - Required header (review script checks for this)
- What Was Done - Specific actions taken
- Files Changed - List with descriptions
- Verification - Checklist of tests/reviews
- Follow-up Items - Future work (optional)

**Quick example:**
```markdown
## Resolution

This task is complete. Fixed the login bug.

### What Was Done
- Modified `AuthMiddleware.ts` to add session check
- Added unit test for redirect logic

### Files Changed
- `src/middleware/AuthMiddleware.ts` - Added session validity check
- `src/__tests__/AuthMiddleware.test.ts` - Added test case

### Verification
- [x] Tested locally - redirect works correctly
- [x] All existing tests pass
```

---

## Template Usage

### For Agents

1. **Before completing a task**, check if there's a relevant template
2. **Follow the template structure** in your task output
3. **Mark task `.done.md`** only after template sections are complete

### For Task Creation

When creating tasks for other agents, reference the relevant template:

```markdown
---
agent: temujin
skill_hint: /horde-implement
---

# Task: Implement feature X

## Requirements
- [specific requirements]

## Output Format
Use the task-completion-template.md Resolution section format.
```

---

## Quality Impact

Using templates improves:

| Metric | Before Templates | After Templates |
|--------|-----------------|-----------------|
| Tasks with Resolution | ~70% | Target: 100% |
| /horde-review score | 6-7/10 | Target: 9/10 |
| Rework required | ~30% | Target: <5% |

---

## Adding New Templates

To add a new template:

1. Create file in `templates/` directory
2. Follow naming: `<purpose>-template.md`
3. Include version, purpose, and when-to-use sections
4. Add entry to this TEMPLATES.md index
5. Test template with one task before deploying

---

## Related Documentation

- **Completion Gate:** `docs/completion-gate.md` - Quality assurance for task completion
- **Completion Gate Examples:** `docs/completion-gate-examples.md` - Real-world examples
- **Agent Protocols:** `reflection_protocols/*.md` - Per-agent behavioral rules

---

## Template Maintenance

Templates are maintained by **Chagatai** (Writer agent).

To suggest improvements or report issues:
- Create a task for chagatai with subject: "Template improvement: <name>"
- Include specific feedback and use case

---

*Last reviewed: 2026-03-08*
*Next review: 2026-03-15*
