# Pre-Submit Checklist

> ## ⚠️ MANDATORY PRE-SUBMIT CHECK ⚠️
> **Run BEFORE marking ANY task complete.**
> **This is C001 — a behavioral rule for ALL agents.**
> **Skipping this check causes quality gate rejections.**

---

## 🚨 What Happens If You Skip This

1. Task gets rejected by quality gate
2. You lose time fixing avoidable issues
3. Your capability score decreases
4. Fleet-wide failure rate increases

**Recent rejections tied to skipped pre-submit checks**: 4 in the last hour alone.

---

## Agent Task Completion Flow

```
1. Finish your work
2. RUN: python3 pre_submit_check.py <task-file>
3. If ✗ NEEDS REVISION → Fix issues → Go back to step 2
4. If ✓ READY TO SUBMIT → Mark as .done.md
5. MOVE TO NEXT TASK
```

**DO NOT skip step 2.** **EVER.**

---

## Quick Command

```bash
python3 /Users/kublai/.openclaw/agents/main/scripts/pre_submit_check.py <task-file-path>
```

If it returns `✗ NEEDS REVISION`, fix the issues before marking `.done.md`.

---

## What Gets Checked

| Check | Threshold | Why |
|-------|-----------|-----|
| Content length | 200+ chars | Prevents empty completions |
| Headings | 3+ sections | Ensures structured output |
| Resolution section | Required | Shows clear outcome |
| Skill invocation | If `skill_hint` set | Enforces R008 rule |

---

## Before You Submit

1. **Run the check script** on your task file
2. **Fix any failures** it reports
3. **Verify**: Script returns `✓ READY TO SUBMIT`
4. **Then**: Mark task as `.done.md`

---

## Why This Matters

Quality gate rejections (14:37, 04:33, 20:33) waste retry cycles.
The pre-submit check catches issues BEFORE they cause rejections.

**C001 Violation Pattern**: Marking complete without running this check.
**Result**: Task rejected, time wasted, score decreases.

---

## Auto-Fix Mode

Missing sections? Run with `--fix` to append templates:

```bash
python3 pre_submit_check.py <task-file> --fix
```

Fill in the template sections before submitting.

---

## Resolution Section Template

```markdown
## Resolution

<!-- Describe the final outcome here -->
- What was done
- What was changed
- What's next
```

---

## Related Documentation

- **Completion Gate System**: `../docs/completion-gate.md` — Full QA pipeline details
- **Quality Thresholds**: Defined in `scripts/pre_submit_check.py` — source of truth
- **Behavioral Rules**: See `memory/when_then_rules.md` for C001 definition

---

**Status**: Active | **Version**: 1.1 | **Updated**: 2026-03-11 (fixed threshold, added warnings)
