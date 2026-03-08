# Completion Audit Integration

## Overview
Continuous auditing of completed tasks integrated into the existing heartbeat infrastructure (watchdog-gather.sh runs every 5 minutes).

## Architecture

### New Component: completion-audit.py
**Location:** `/Users/kublai/.openclaw/agents/main/scripts/completion-audit.py`

**Purpose:** Lightweight, continuous verification of recently completed tasks (within 2 hours).

**What it checks:**
1. Workspace result file exists with substantive content
2. No fake completion markers (delegated without execution, wrong model)
3. Cross-references watcher state for execution records
4. Skips test tasks, failed tasks, and already verified/unverified tasks

**Output:**
- `logs/completion-audit-state.json` — State persistence (last audit timestamp)
- `logs/completion-audit.jsonl` — Machine-readable audit history
- stdout — Summary for watchdog integration

### Integration Point: watchdog-gather.sh
**Location:** Section 5b (after task queue status, before trends)

**Metrics captured:**
- `COMPLETION_AUDIT_VERIFIED` — Tasks verified as legitimately completed
- `COMPLETION_AUDIT_FAKE` — Fake completions detected
- `COMPLETION_AUDIT_REQUEUED` — Tasks re-queued for re-execution

**Logged to:**
1. `ticks.jsonl` — Full JSON record with audit metrics
2. `tick-summary.txt` — Human-readable summary for LLM triage
3. `watchdog.log` — One-liner with audit counts

## Comparison with Existing Verification

| Component | Frequency | Scope | Purpose |
|-----------|-----------|-------|---------|
| **completion-audit.py** | 5 min (heartbeat) | Last 2 hours | Continuous fake detection |
| **task-verifier.py** | On completion (task-watcher) | Individual tasks | Deliverable quality verification |
| **queue-audit.py** | 30 min (tock) | Last 7 days | Comprehensive queue audit |
| **ogedei-watchdog.py** | 30 sec daemon | Recent completions | QA daemon with multiple checks |

## Detection Logic

A task is marked as **fake completion** if:
- No workspace result file AND no execution record in watcher state
- Result file contains "delegated to...spawn queue" without real execution
- Legacy fake markers (wrong model strings from old routing)

A task is **skipped** (not audited) if:
- Test/trivial task (detected by patterns)
- Already verified/unverified (passed through task-verifier.py)
- Failed task (legitimate execution outcome)
- Obsolete task (intentionally closed)
- Older than 2 hours

## Actions on Detection

When a fake completion is detected:
1. Rename `.completed.done.md` back to `.md` (re-queue)
2. Touch file to update mtime (triggers task-watcher)
3. Clear from watcher state
4. Log to `completion-audit.jsonl`
5. Report in watchdog metrics

## Monitoring

View audit history:
```bash
tail -20 ~/.openclaw/agents/main/logs/completion-audit.jsonl | python3 -m json.tool
```

View current state:
```bash
cat ~/.openclaw/agents/main/logs/completion-audit-state.json | python3 -m json.tool
```

View recent ticks with audit metrics:
```bash
tail -12 ~/.openclaw/agents/main/logs/ticks.jsonl | jq '.tasks.audit'
```

## Incident Response

High fake completion rate indicates:
- Model routing issues (check settings.json)
- Claude Code execution failures
- Session lock contention
- Configuration drift

Escalate to Kublai if `fake_found > 5` in a single tick.
