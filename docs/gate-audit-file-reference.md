# Gate Audit File Reference

> **Companion to:** `completion-gate.md`
> **Purpose:** Quick reference for reading and understanding gate audit JSON files
> **Last Updated:** 2026-03-09

---

## What Are Gate Audit Files?

Every task that goes through the Completion Gate generates an audit JSON file stored in:
```
~/.openclaw/agents/main/logs/gate-audits/<filename>.json
```

These files record:
- What % of requirements were completed
- What follow-ups were created
- Why the gate blocked or passed
- Timestamp for debugging

---

## Filename Convention

**Intended format:** `{task_id}-{YYYYMMDD}-{HHMMSS}.json`

**Examples:**
- `0e8c3e7a-fc6-20260309-024757.json` — clean format
- `gate-llm-fallback-1772985679-20260308-204506.json` — descriptive slug

**Known inconsistencies (being phased out):**
- `$(uuidgen ...).json` — literal shell command (BUG)
- `1741487600-watchdog-terminal-states.json` — timestamp prefix
- Files without timestamps — older audits

**When in doubt:** Use `jq` to read the `audit_timestamp` field inside the JSON.

---

## Audit JSON Schema

```json
{
  "original_task": "task-id-or-fragment",
  "completion_percentage": 85,
  "can_complete": false,
  "missing_components": ["item 1", "item 2"],
  "quality_issues": ["issue 1", "issue 2"],
  "required_followups": [
    {
      "title": "Follow-up title",
      "agent": "agent-name",
      "priority": "high|normal|low",
      "reason": "Why this follow-up is needed"
    }
  ],
  "optional_improvements": [
    {
      "title": "Improvement title",
      "agent": "agent-name",
      "priority": "normal|low",
      "reason": "Why this would help"
    }
  ],
  "blockers": [],
  "gate_cycle": 0,
  "audit_timestamp": "2026-03-09T02:47:57.550493",
  "audit_version": "1.0"
}
```

---

## Field Reference

| Field | Type | Meaning |
|-------|------|---------|
| `original_task` | string | Task ID being audited (may be fragment) |
| `completion_percentage` | number | 0-100 score of how much was completed |
| `can_complete` | boolean | Can task pass without follow-ups? |
| `missing_components` | array | Specific requirements not delivered |
| `quality_issues` | array | Code quality, testing, or doc gaps |
| `required_followups` | array | Follow-up tasks that MUST be done |
| `optional_improvements` | array | Nice-to-have follow-ups |
| `blockers` | array | Items requiring human intervention |
| `gate_cycle` | number | Which audit cycle (0=initial, 1+=re-audit) |
| `audit_timestamp` | string | When audit ran (ISO 8601) |
| `audit_version` | string | Schema version (for migration) |

---

## Interpreting Completion Percentage

| Range | Meaning | Follow-ups? |
|-------|---------|-------------|
| **90-100%** | Essentially complete | Optional improvements only |
| **70-89%** | Mostly done | Required follow-ups created |
| **< 70%** | Incomplete | Required follow-ups + may need replan |
| **Any + blockers** | Blocked | No — human action required |

**Key insight:** The gate is NOT about perfection — 90% is enough to pass if there are no `blockers`. The 10% allowance covers minor polish items that can be optional improvements.

---

## Required vs Optional Follow-ups

**Required follow-ups (`required_followups` array):**
- Created automatically in target agent's queue
- Must complete before original task can pass gate
- Example: missing tests, critical bug, incomplete feature

**Optional improvements (`optional_improvements` array):**
- NOT created as tasks (informational only)
- Can be done later or not at all
- Example: refactoring, nice-to-have feature, documentation polish

---

## Blockers (Human Action Required)

When `blockers` is non-empty, the gate creates NO follow-up tasks. Instead:
- Task is marked `.gate-blocked.md`
- Human must resolve the blocker
- Example: API key needed, stakeholder decision required

---

## Reading Audit Files Quickly

### Show completion score for all recent audits:
```bash
cd ~/.openclaw/agents/main/logs/gate-audits
for f in $(ls -t | head -10); do
  echo "$f: $(jq -r '.completion_percentage' "$f")% - $(jq -r '.can_complete' "$f")"
done
```

### Show just the follow-ups for a task:
```bash
jq '.required_followups[] | "\(.agent): \(.title)"' audit-file.json
```

### Find all audits with low completion (< 70%):
```bash
jq 'select(.completion_percentage < 70)' *.json
```

### Find audits with blockers:
```bash
jq 'select(.blockers | length > 0)' *.json
```

---

## Common Patterns

### Pattern 1: "Almost there" audit
```json
{
  "completion_percentage": 85,
  "can_complete": false,
  "missing_components": ["Tests not written"],
  "required_followups": [{"title": "Write tests", ...}]
}
```
**Meaning:** Feature works, but needs tests. Gate creates 1 follow-up, waits for it to complete.

### Pattern 2: Quality gate
```json
{
  "completion_percentage": 100,
  "can_complete": false,
  "quality_issues": ["No error handling", "No logging"],
  "required_followups": [...]
}
```
**Meaning:** All requirements met, but code quality issues prevent passing.

### Pattern 3: Blocked task
```json
{
  "completion_percentage": 50,
  "blockers": ["API access required - request credential from ops"]
}
```
**Meaning:** Cannot proceed — task blocked. Follow-ups NOT created. Task goes to `.gate-blocked.md`.

### Pattern 4: Clean pass
```json
{
  "completion_percentage": 95,
  "can_complete": true,
  "required_followups": [],
  "optional_improvements": [{"title": "Add analytics", ...}]
}
```
**Meaning:** Task passes immediately, marked `.gate-passed.done.md`. Optional improvements are suggestions only.

---

## Gate Cycle Numbers

`gate_cycle` indicates how many times this task has been re-audited:

| Value | Meaning |
|-------|---------|
| 0 | Initial audit (when agent first marked task done) |
| 1+ | Re-audit after follow-ups completed |

**Re-audit behavior:** When all follow-ups are done, the resolver re-runs the audit. If the second audit shows 100% (or ≥90% with no blockers), the gate passes.

---

## Troubleshooting

### "I can't find the audit file for my task"

1. Search by partial task ID:
   ```bash
   find ~/.openclaw/agents/main/logs/gate-audits -name "*<task_fragment>*.json"
   ```

2. If task file exists, check its frontmatter for `gate_audit_ref`:
   ```bash
   grep -A5 'gate_audit_ref' ~/.openclaw/agents/*/tasks/<task_id>*.md
   ```

3. Check recent audits by time:
   ```bash
   ls -lt ~/.openclaw/agents/main/logs/gate-audits/ | head -20
   ```

### "The audit filename is broken"

If you see filenames like `$(uuidgen | tr '[:upper:]' '[:lower:]' | tr -d '\n')-20260309-002016.json`:
- This is a known bug where a shell command wasn't executed
- The file contents are still valid JSON
- Read `audit_timestamp` inside to get the real time

### "Completion percentage seems wrong"

The audit is LLM-based and subjective. To dispute:
1. Complete legitimate follow-ups
2. For incorrect ones, bypass with explanation:
   ```bash
   python3 ~/.openclaw/agents/main/scripts/completion-gate-bypass.py \
     --task <task_id> \
     --approver kublai \
     --reason "Audit incorrectly marked <X> as missing — it was delivered as <Y>"
   ```

---

## Related Files

| File | Purpose |
|------|---------|
| `completion-gate.md` | Full system documentation |
| `completion-gate-examples.md` | Example scenarios |
| `completion-gate-audit.py` | Script that generates these files |
| `completion-gate-resolver.py` | Script that reads them to resolve gates |
