# Proposal Lifecycle Management

## Overview

The Kurultai reflection pipeline generates proposals via brainstorming, but these need to be tracked, reviewed, and converted to actionable tasks. The proposal lifecycle system closes this loop.

## Problem Solved

**Issue:** 30+ pending proposals accumulated with no review process. Proposals were marked "Implemented: YES" without verification or task creation.

**Impact:** Good ideas were lost in the `proposals/` graveyard with no path to execution.

## Solution: `proposal_lifecycle.py`

A Python script that tracks proposals from creation through implementation.

### Features

1. **List proposals** (`--list`): Shows pending proposals (use `--all` for all proposals)
2. **Show stale** (`--stale`): Highlights proposals >24h old without action
3. **Approve** (`--approve <id>`): Converts proposal to task file in agent's queue
4. **Reject** (`--reject <id> --reason "..."`): Marks proposal as rejected
5. **Status detection**: Automatically detects proposals marked "Implemented: YES" in their own Status section
6. **State tracking**: Persists review decisions to `logs/proposal-state.json` (auto-created if missing)

### Usage Examples

```bash
# List all pending proposals
python3 proposal_lifecycle.py --list

# Show proposals that need attention (>24h old)
python3 proposal_lifecycle.py --stale

# Approve a proposal and create task
python3 proposal_lifecycle.py --approve mongke-20260312-073327.md

# Reject a proposal
python3 proposal_lifecycle.py --reject kublai-20260312-013437.md --reason "Already implemented"
```

## Integration with Reflection Pipeline

Added to `hourly_reflection.sh` after consensus voting:

```bash
# PROPOSAL LIFECYCLE CHECK
python3 "$SCRIPTS/proposal_lifecycle.py" --stale >> "$LOGS_DIR/proposal-lifecycle.log" 2>&1
python3 "$SCRIPTS/proposal_lifecycle.py" --list > "$LOGS_DIR/proposal-status.txt" 2>&1
```

This ensures:
- Stale proposals are flagged hourly
- Kublai sees proposal status in logs
- No proposal is forgotten

## Proposal File Format

```markdown
# Proposal: <title>

**Agent:** <agent> (<role>)
**Timestamp:** YYYY-MM-DD HH:MM:SS
**Domain:** <domain>
**Model:** <model>

## Problem
<what problem does this solve?>

## Solution
<what should be done?>

## PRIORITY_FIX
<if addressing a /horde-review PRIORITY_FIX, reference it here with specific action>

## Status
- **Implemented:** YES/NO/PARTIAL
- **Verified:** YES/NO
- **Effort:** S/M/L
- **Category:** rule|script|protocol|capability|process

## Resolution
<if Implemented: YES, describe what was actually done and verification>
```

## Task Creation

When a proposal is approved, a task file is created:

```
~/.openclaw/agents/<target_agent>/tasks/proposal-<original_name>-<timestamp>.md
```

The task includes:
- Problem and solution from proposal
- Link to full proposal file
- Deliverables checklist

## Status Display

Proposals are displayed with status icons:
- `⏳` — Pending review or implementation
- `✨` — Implemented (marked "Implemented: YES" in proposal file)
- `✅` — Approved through formal review (task created)
- `❌` — Rejected

## State File

`logs/proposal-state.json` tracks formal review decisions and is auto-created if missing:

```json
{
  "reviews": {
    "mongke-20260312-073327.md": {
      "status": "approved",
      "reviewed_at": "2026-03-12T08:00:00",
      "task_created": "/path/to/task.md"
    }
  },
  "last_review": "2026-03-12T08:00:00"
}
```

## Best Practices

1. **Review proposals hourly**: Don't let backlog grow >10 pending
2. **Auto-reject stale proposals**: If >7 days old and not acted on, reject or re-propose
3. **Verify before marking implemented**: Don't mark "Implemented: YES" without testing
4. **Close the loop**: After implementation, update proposal Status section

## Monitoring

Check proposal health:

```bash
# Count pending proposals
python3 proposal_lifecycle.py --list | grep -c "⏳"

# View stale proposals
python3 proposal_lifecycle.py --stale
```

## Future Enhancements

- [ ] Auto-approve proposals with unanimous voting
- [ ] Proposal expiration (auto-reject after 7 days)
- [ ] Integration with Neo4j proposal tracking
- [ ] Proposal dashboard in kurultai-report
