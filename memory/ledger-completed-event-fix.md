---
name: ledger-completed-event-fix
description: Fix for false 100% HIGH_FAILURE_RATE alert caused by missing COMPLETED events in ledger
type: feedback
---

# COMPLETED Event Logging Fix (2026-03-12)

## Problem
The throughput_anomaly.py script was reporting 100% fleet-wide failure rate (HIGH_FAILURE_RATE) even though tasks were completing successfully. This triggered false CRITICAL alerts.

## Root Cause
The `mark_task_completed()` function in agent-task-handler.py renamed task files to `.done.md` (terminal state) but **never logged COMPLETED events to the ledger**. Only FAILED events were logged.

This caused:
- Ledger: 217 FAILED events, 8 COMPLETED events (~96% failure rate)
- Reality: Many more tasks completed (jochi: 7 done, ogedei: 10 done in task files)

The discrepancy was because:
1. Tasks that succeed -> mark_task_completed() -> `.done.md` -> NO COMPLETED event logged
2. Tasks that fail -> FAILED event logged -> later marked `.failed.done.md` -> NO COMPLETED event logged
3. throughput_anomaly.py reads ledger, sees only FAILED events, triggers false alert

## Solution
Added COMPLETED event logging to `mark_task_completed()` function:
- Normal path (after successful rename via _safe_rename_with_lock)
- Fallback path (after recovery rename)
- All terminal states: completed, failed, no_output, credential_failed, etc.

The COMPLETED event includes:
- `task_id`: Extracted from frontmatter
- `agent`: Agent that executed the task
- `status`: Terminal status (completed/failed/no_output/etc)
- `success`: Boolean (status == 'completed')
- `output_lines`: File size proxy for work done
- `fallback_path`: True if logged via fallback path

## Impact
After this fix:
- Each task reaching terminal state logs COMPLETED event
- Ledger accurately reflects both successes and failures
- HIGH_FAILURE_RATE alerts based on complete data
- False positive 100% failure rate eliminated

## Related Files
- agent-task-handler.py (lines ~1540-1570, ~1656-1680)
- throughput_anomaly.py (consumes COMPLETED events)
- kurultai_ledger.py (VALID_EVENTS includes COMPLETED)
