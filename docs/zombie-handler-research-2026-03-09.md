# Zombie Handler Process Research Report
**Date:** 2026-03-09
**Researcher:** mongke
**Domain:** heartbeat_system (subprocess lifecycle management)

## Executive Summary

Zombie handler processes are being killed at a rate of ~2-3 per hour by the watchdog-gather.sh zombie cleanup. This research identifies the root cause and proposes a fix to prevent killing legitimate handlers during normal shutdown.

## Problem Statement

**Definition:** A "zombie process" in the Kurultai context is:
- An agent-task-handler process that is running
- But has no corresponding `.executing.md` file

**Current Behavior:**
- Watchdog detects zombies every 5 minutes
- Immediately kills them with `kill` then `kill -9`
- Historical log shows consistent pattern: ~2-3 zombies per hour

**Impact:**
- ERROR_RATE_ESCALATION triggered (128 errors/hour, rising)
- Handlers may be killed during normal shutdown
- Potential task interruption if killed prematurely

## Root Cause Analysis

### Architecture Flow

```
task-watcher.py → agent-task-handler.py → claude-agent
                    ↓
              .executing.md (task state)
              .executing.pid (handler PID + timestamp)
```

### Lifecycle

1. **Start:** `mark_task_executing()` renames `task.md` → `task.executing.md`
2. **Execute:** Handler runs, claude-agent processes task
3. **Complete:** `mark_task_completed()` renames `.executing.md` → `.completed.done.md`
4. **Exit:** Handler process terminates

### The Race Condition

```
Time  Handler              .executing.md    Subprocess Audit    Watchdog Action
----  ------------------   --------------   ----------------    ---------------
T1    running             exists            -                  -
T2    completes           → .done.md        -                  -
T3    exiting (0.5s)       .done.md         ← audit runs        "zombie detected!"
T4    KILLED by watch     .done.md         -                  process killed!
```

**Window of vulnerability:** 5 minutes (tick interval)
**Expected handler shutdown time:** < 1 second
**False positive probability:** HIGH

### Historical Evidence

```
[2026-03-09 15:29:13] ZOMBIE_CLEANUP | killed 2 zombie process(es)
[2026-03-09 15:23:27] ZOMBIE_CLEANUP | killed 2 zombie process(es)
[2026-03-09 15:10:12] ZOMBIE_CLEANUP | killed 2 zombie process(es)
```

The pattern shows:
- Multiple zombies detected simultaneously
- Consistent frequency (every ~10-15 minutes)
- Suggests systematic detection issue, not random hangs

## Classification of Zombie Types

| Type | Cause | Is True Zombie? | Should Kill? |
|------|-------|-----------------|--------------|
| A | Handler completed, process exiting (race) | NO | **NO** |
| B | Handler never created .executing.md (bug) | YES | YES |
| C | Handler hung and will never exit | YES | YES |
| D | .executing.md deleted externally (manual) | YES | YES |

**Hypothesis:** Most detected zombies are Type A (false positives).

## Proposed Solution

### Phase 1: Enhanced Detection (Immediate)

Add age-based filter to distinguish true zombies from shutdown transitions:

```python
# In subprocess-audit.py
TRUE_ZOMBIE_THRESHOLD_SECONDS = 60  # Allow 60s for graceful shutdown

def detect_anomalies(...):
    for pid, info in running_handlers.items():
        if pid not in executing_pids:
            # NEW: Check if there's a recent .done.md for this handler
            if _has_recent_completion(pid, matched_agent):
                # This is likely Type A (normal shutdown)
                continue  # Don't flag as zombie
```

### Phase 2: Staggered Kill Strategy (Recommended)

Instead of immediate kill, use graduated response:

1. **First detection:** Log warning, check age
2. **Second detection (5m later):** Send SIGTERM (graceful shutdown)
3. **Third detection (10m later):** Send SIGKILL (force kill)

### Phase 3: Process Exit Telemetry (Long-term)

Add handler shutdown confirmation:
```python
def mark_task_completed(...):
    # ... existing code ...
    # NEW: Write .exited sentinel
    exited_file = completed_file.replace('.done.md', '.exited')
    write_timestamp(exited_file)
```

## Implementation Priority

1. **HIGH:** Add age-based filter to subprocess-audit.py (prevents false positives)
2. **MEDIUM:** Implement staggered kill strategy (safer cleanup)
3. **LOW:** Add exit telemetry (better observability)

## Success Metrics

- Zombie false positives: Target < 0.5/hour (from ~2-3/hour)
- ERROR_RATE_ESCALATION frequency: Reduced by 50%
- True zombie cleanup: Still effective (< 1 true zombie/day)

## Related Issues

- Credential crisis causing handler failures → increases zombie risk
- Stale task escalations → related subprocess lifecycle issue
- See: memory/bugs.md for full history

## References

- `scripts/watchdog-gather.sh` lines 561-602 (zombie cleanup)
- `scripts/subprocess-audit.py` lines 296-315 (zombie detection)
- `scripts/agent-task-handler.py` lines 921-930 (task execution)
- `logs/watchdog.log` (historical zombie cleanup events)
