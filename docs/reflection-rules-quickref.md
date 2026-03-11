# ACTIVE RULES — Quick Reference for Reflection

**Purpose:** Quick guide for interpreting and following your behavioral rules during reflection.

---

## What Are ACTIVE RULES?

WHEN/THEN behavioral rules are self-generated constraints that **prevent recurring mistakes**. Each agent creates their own rules based on past failures.

**Format:** `WHEN [trigger condition] THEN [required action] INSTEAD OF [old default]`

---

## How To Read Your Rules

During reflection, you'll see:

```
## YOUR BEHAVIORAL RULES
  1. WHEN idle >2h AND no tasks AND doc gaps exist THEN scan for stale docs INSTEAD OF idling
  2. WHEN task_type NOT IN (blog, docs, content) THEN reject and reroute INSTEAD OF executing
  3. WHEN claiming fix complete THEN verify by running test INSTEAD OF blind claim
```

**Breakdown:**
- `WHEN` = Trigger condition (when the rule applies)
- `THEN` = Required action (what you MUST do)
- `INSTEAD OF` = Old habit to avoid (what you used to do wrong)

---

## Rule Compliance Template

At the end of each reflection, evaluate each rule:

```
## RULE COMPLIANCE
- Rule 1: YES — Found 2 stale docs, created task for tech-watchlist.md update
- Rule 2: YES — Rejected python task, routed to temujin
- Rule 3: NO — Claimed fix without verifying. FIX: Will test before claiming next time.
```

**Be honest.** A "NO" with a fix plan is better than lying to yourself.

---

## Where Rules Come From

1. **Self-generated** — You create them during reflection after analyzing failures
2. **Peer proposals** — Other agents suggest rules via Neo4j RuleProposal nodes
3. **System-wide** — Kublai maintains shared rules in `memory/when_then_rules.md`

**Storage locations:**
- `~/.openclaw/agents/{agent}/memory/rules.json` — Structured JSON with compliance stats
- `~/.openclaw/agents/{agent}/memory/YYYY-MM-DD.md` — Daily memory (reflection output)
- `~/.claude/projects/*/memory/when_then_rules.md` — Fleet-wide registry

---

## Rule Lifecycle

| State | Meaning | Action |
|-------|---------|--------|
| **proposed** | Suggested but not active | Review → adopt or discard |
| **active** | Currently enforced | FOLLOW during execution |
| **deprecated** | Ineffective, kept for ref | Don't follow, may prune |
| **pruned** | Deleted from storage | Gone, create replacement if needed |

**Auto-deprecation:** Rules with <25% follow rate after 3+ evaluations get marked deprecated.

---

## Writing a Good Rule

**Template:** `WHEN [specific trigger] THEN [specific action] INSTEAD OF [specific default]`

**Good rule:**
```
WHEN reflection fires AND queue_depth=0 AND documentation gaps exist
THEN scan shared-context/ and docs/ for stale .md files
AND create content task for highest-priority gap
INSTEAD OF reflecting on empty session
```

**Bad rule:**
```
WHEN things are slow
THEN try to be better
```

**Why bad?** Vague trigger ("slow"), vague action ("try better"), no INSTEAD_OF.

---

## Quick Checklist (Reflection Time)

1. [ ] Read each active rule aloud
2. [ ] For each rule: Did I follow it? (YES/NO)
3. [ ] For any NO: What specific action will fix it next time?
4. [ ] Is a recurring problem emerging? Create new rule
5. [ ] Write new rule to memory file AND rules.json

---

## Troubleshooting

**Q: "No active rules yet" in my reflection**
A: This is your first reflection with this format. You'll create your first rule below.

**Q: Rules from reflection don't match rules.json**
A: Run `python3 scripts/rule_lifecycle_audit.py` to sync.

**Q: I keep violating the same rule**
A: Rule may be too broad. Split into smaller, more specific rules.

**Q: Too many rules (7+) to follow**
A: Merge similar rules or prune the weakest. Quality > quantity.

---

## See Also

- `memory/rules_lifecycle.md` — Full lifecycle documentation
- `memory/when_then_rules.md` — Fleet-wide rule registry
- `scripts/prepare_reflection_context.py` — How rules are extracted for reflection
- `scripts/rule_lifecycle_audit.py` — Sync and validation script
