# WHEN/THEN Rule Lifecycle Management

**Version:** 1.0
**Date:** 2026-03-09
**Author:** chagatai (Kurultai Content Specialist)
**Status:** Active

---

## Purpose

This document is the **single source of truth** for WHEN/THEN behavioral rules in the Kurultai system. It defines the rule lifecycle, architecture, and management procedures.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     RULE STORAGE LAYERS                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Agent Daily Memory                              │
│     └─ agents/{agent}/memory/YYYY-MM-DD.md                      │
│        └─ ## ACTIVE RULES section (reflection output)            │
│        └─ Unstructured text, parsed by prepare_reflection.py    │
│                                                                  │
│  2. Structured rules.json                        │
│     └─ agents/{agent}/memory/rules.json                           │
│        └─ Structured JSON with metadata                         │
│        └─ Status: active | deprecated                           │
│        └─ Tracking: follow_count, violate_count, last_evaluated  │
│                                                                  │
│  3. Central Documentation (THIS FILE)                           │
│     └─ memory/rules_lifecycle.md                                │
│        └─ Lifecycle definitions                                 │
│        └─ Cross-agent visibility                                │
│        └─ Best practices                                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

                    ┌─────────────────────────┐
                    │   FEEDBACK LOOP         │
                    ├─────────────────────────┤
                    │ parse_rule_compliance   │
                    │ (reads reflection YES/NO │
                    │  → updates rules.json)  │
                    └─────────────────────────┘
```

---

## Rule Lifecycle States

| State | Description | Storage | Transition |
|-------|-------------|---------|------------|
| **proposed** | Rule suggested via brainstorm/proposal, not yet active | proposals/*.md | → active (approved) or → discarded |
| **active** | Rule is being enforced and tracked | rules.json (status=active) + daily memory | → deprecated (ineffective) or → pruned (stale) |
| **deprecated** | Rule marked as ineffective, no longer enforced | rules.json (status=deprecated) | → pruned (after 7 days) |
| **pruned** | Rule removed from storage | (deleted) | End of lifecycle |

---

## Rule Schema (rules.json)

```json
{
  "rules": [
    {
      "id": "C4",
      "text": "WHEN reflection fires AND queue_depth=0 AND documentation gaps exist THEN scan for stale content AND propose content task INSTEAD OF reflecting on empty session.",
      "status": "active",
      "created_at": "2026-03-09T12:00:00.000000",
      "source": "chagatai-reflection:2026-03-09",
      "last_evaluated": "2026-03-09T16:00:00.000000",
      "follow_count": 5,
      "violate_count": 1,
      "priority": "NORMAL",
      "category": "productivity"
    }
  ],
  "max_active": 7,
  "last_updated": "2026-03-09T16:48:50.031733",
  "last_pruned": "2026-03-09T16:18:34.026958"
}
```

### Field Definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | ✓ | Unique identifier (e.g., C4, r020) |
| `text` | string | ✓ | Full WHEN/THEN rule text |
| `status` | enum | ✓ | `active` or `deprecated` |
| `created_at` | ISO8601 | ✓ | When rule was created |
| `source` | string | ✓ | Origin (e.g., `kurultai-reflect:2026-03-09`) |
| `last_evaluated` | ISO8601 | | Last compliance check |
| `follow_count` | int | | Times rule was followed |
| `violate_count` | int | | Times rule was violated |
| `deprecated_reason` | string | | Why rule was deprecated |
| `deprecated_at` | ISO8601 | | When rule was deprecated |
| `priority` | enum | | CRITICAL, HIGH, NORMAL, LOW |
| `category` | string | | Grouping (productivity, quality, ops, etc.) |

---

## Auto-Deprecation Thresholds

From `parse_rule_compliance.py`:

| Condition | Action |
|-----------|--------|
| `evaluations >= 3` AND `follow_rate < 25%` | Auto-deprecate |
| `evaluations >= 3` AND `follow_rate < 50%` | Warning logged |
| No evaluation for 14+ days | Mark stale |

---

## Adding a New Rule

### Via Reflection (Recommended)

1. **Agent reflection** generates proposal in `## ACTIVE RULES` section
2. **Rule parser** extracts from daily memory file
3. **Manual sync** to rules.json (pending automation):
   ```bash
   # Read current rules
   cat ~/.openclaw/agents/chagatai/memory/rules.json | jq .
   ```

### Via Direct Edit

```bash
# Edit rules.json
vim ~/.openclaw/agents/chagatai/memory/rules.json

# Add new rule object with status=active
# Update last_updated timestamp
```

---

## Cross-Agent Rule Visibility

### Per-Agent Rule Locations

| Agent | Daily Memory | rules.json |
|-------|-------------|------------|
| kublai | `~/.openclaw/agents/kublai/memory/YYYY-MM-DD.md` | ✓ |
| temujin | `~/.openclaw/agents/temujin/memory/YYYY-MM-DD.md` | ✓ |
| mongke | `~/.openclaw/agents/mongke/memory/YYYY-MM-DD.md` | ✓ |
| chagatai | `~/.openclaw/agents/chagatai/memory/YYYY-MM-DD.md` | ✓ |
| jochi | `~/.openclaw/agents/jochi/memory/YYYY-MM-DD.md` | ✓ |
| ogedei | `~/.openclaw/agents/ogedei/memory/YYYY-MM-DD.md` | ✓ |
| tolui | `~/.openclaw/agents/tolui/memory/YYYY-MM-DD.md | (not tracked) |

### Audit All Rules

```bash
# Run rule lifecycle audit
python3 ~/.openclaw/agents/main/scripts/rule_lifecycle_audit.py

# Output: logs/rule-audit-{timestamp}.md
```

---

## Current Active Rules by Agent

### chagatai (Writer)

As of 2026-03-09, reflection output shows these active rules:

| ID | Rule | Status |
|----|------|--------|
| C4 | WHEN reflection fires AND queue_depth=0 AND documentation gaps exist THEN scan for stale content AND propose content task | active |
| C5 | WHEN task completes AND output contains no written artifact THEN verify content deliverable exists AND flag as HOLLOW | active |
| C6 | WHEN task execution time exceeds 400s THEN checkpoint progress to workspace AND output partial deliverable | active |
| C7 | Add new rules via rule_registry module (pending implementation) | meta-rule |

**Note:** rules.json shows all rules deprecated — needs sync with reflection output.

### kublai (Router)

From MEMORY.md:

| Rule | Trigger | Action |
|------|---------|--------|
| R1 | errors/hour > 100 AND rising | Auto-escalate to kublai |
| R2 | queue imbalance AND capacity exists | Accept overflow |
| R3 | Human sends message | Classify + create task |
| R4 | Claiming fix complete | Verify before accepting |
| R5 | Routing research | Suggest /horde-learn |
| R6 | Pure research task | Route to mongke |
| R7 | Reflection with 0 tasks completed | Produce missing deliverable |

---

## Troubleshooting

### "No active rules" in reflection

**Cause:** Daily memory file has no `## ACTIVE RULES` section.

**Fix:**
```bash
# Check daily memory exists
ls -la ~/.openclaw/agents/chagatai/memory/2026-03-09.md

# If missing, reflection will fall back to Claude project memory
ls -la ~/.claude/projects/*/memory/*-reflection-*.md
```

### Rules out of sync (reflection vs rules.json)

**Cause:** Manual edits to one but not the other.

**Fix:** Run lifecycle audit and reconcile:
```bash
python3 ~/.openclaw/agents/main/scripts/rule_lifecycle_audit.py
```

### Auto-deprecation not working

**Cause:** `parse_rule_compliance.py` not running in kurultai pipeline.

**Check:**
```bash
# Look for compliance parse in reflection logs
grep "parse_rule_compliance" ~/.openclaw/agents/main/logs/reflection-step-timing.json
```

---

## Maintenance Schedule

| Frequency | Task | Script |
|-----------|------|--------|
| Hourly | Parse compliance, auto-deprecate | parse_rule_compliance.py |
| Hourly | Extract rules for reflection | prepare_reflection_context.py |
| Daily | Audit for duplicates/contradictions | rule_lifecycle_audit.py |
| Weekly | Prune deprecated rules >7 days old | manual or script |
| Monthly | Review category distribution, merge duplicates | manual |

---

## Best Practices

1. **Keep rules under MAX_ACTIVE_RULES (7)** — More rules = harder to follow
2. **Use specific WHEN triggers** — Avoid ambiguous conditions
3. **Include INSTEAD_OF clause** — Make alternatives explicit
4. **Categorize rules** — Use category field for grouping
5. **Document source** — Track where rule came from
6. **Review compliance regularly** — Check follow/violate counts

---

## Future Improvements

- [ ] Automated sync between daily memory and rules.json
- [ ] Cross-agent rule deduplication
- [ ] Rule testing framework (simulate triggers)
- [ ] Visualization of rule effectiveness over time
- [ ] Rule proposal workflow (brainstorm → vote → activate)

# R008 Skill Invocation Verification (2026-03-11)

**Problem:** Agents were ignoring skill_hint instructions in task prompts, resulting in EXECUTING_NO_OUTPUT anomalies and low throughput.

**Solution:** Added R008 verification to `_verify_task_completion()` in agent-task-handler.py. Now when a task has a skill_hint, the completion verification checks for evidence that the skill was actually invoked.

**Evidence patterns by skill:**
- `/horde-learn`: search, source, research, citation, finding, web
- `/horde-brainstorming`: proposal, brainstorm, option, approach, explore
- `/horde-implement`: implement, code, file, write, create
- `/horde-review`: review, analysis, strength, weakness, finding
- `/horde-debug`: debug, error, fix, issue, problem
- `/systematic-debugging`: debug, error, fix, issue, problem
- `/content-research-writer`: content, article, writing, draft
- `/code-reviewer`: review, code, security, vulnerability
- `/scrapling-research`: scrap, crawl, fetch, extract

**Files modified:**
- `scripts/agent-task-handler.py` - Added R008 check in `_verify_task_completion()`
- `scripts/test_r008_verification.py` - Test suite for R008 enforcement

**Expected impact:**
- Tasks with skill_hint will fail if skill evidence is missing
- Creates feedback loop: agents learn to invoke required skills
- Improves mongke throughput by ensuring /horde-learn is used for research

