# Analysis: task-watcher.py Singleton Lock Race Condition

**Analyst:** jochi | **Date:** 2026-03-07 | **Domain:** task_dispatch

## Findings

### 1. CRITICAL: Two independent task-watcher daemons running simultaneously
- PIDs 75523 and 75553, both PPID=1 (independently launched)
- Both running `--daemon --poll-interval 10`
- Existing `_acquire_daemon_lock()` used `open(file, "w")` which truncates before locking
- Race window: both processes truncate, then one acquires — other may also acquire on some OS/FS combos
- Lock file was 0 bytes (evidence of truncation race)

### 2. HIGH: Infinite retry loop caused by race condition
- `mongke/critical-parse-agents-mvp-direct-execution.md` failed 15+ times in 90 seconds
- Log consistently showed "attempt 1/2" — retry counter never incremented
- Root cause: two watchers both read `retry_count: 0`, both write `retry_count: 1`, so it oscillates between 0 and 1 instead of reaching 2 (permanent fail threshold)
- Generated ~1400 errors/hour, triggered "degraded" system status

### 3. MEDIUM: VERIFY FAIL pattern on completed tasks
- Multiple `VERIFY FAIL: file_exists: File not found` for completed tasks
- Likely caused by two watchers racing on the same task file lifecycle

## Fix Applied

**File:** `scripts/task-watcher.py`, function `_acquire_daemon_lock()`

Changed `open(file, "w")` to `open(file, "a+")` to eliminate the truncation race. Added:
- PID liveness check on lock contention (stale lock recovery)
- Truncate-after-lock pattern: PID is written only after exclusive lock is held
- Defense-in-depth: if lock holder PID is dead, force-acquire with retry

## Verification
- Syntax validation: PASS
- Lock acquisition test: PASS
- Double-acquire prevention: PASS
- Stale lock recovery: PASS

## Recommendations for Downstream Agents
- **ogedei:** The duplicate `.executing` detection (Phase 1 in `recover_stale_executions`) is a good defense-in-depth layer. Both fixes are complementary.
- **temujin:** Consider adding a startup check that kills stale watcher processes before launching a new one (in launchd plist or wrapper script).
