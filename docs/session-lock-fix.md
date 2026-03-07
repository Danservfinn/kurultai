# Session Lock Stale Lock Fix

## Problem

Users were experiencing errors like:
```
⚠️ Agent failed before reply: All models failed (2): 
bailian/qwen3.5-plus: session file locked (timeout 10000ms): pid=89625 
/Users/kublai/.openclaw/agents/main/sessions/b0b378f9-f81d-4b5a-9610-da4b182fe15b.jsonl.lock (timeout)
```

**Root cause:** A process (PID 89625) crashed or was killed without releasing its session lock file. The lock file persisted, blocking all subsequent attempts to use that session. Both model providers timed out waiting for the lock.

## Why This Happens

OpenClaw uses file-based locking for session writes. When a process acquires a lock:
1. It creates a `.jsonl.lock` file with JSON payload containing PID and timestamp
2. It holds an exclusive file handle (flock)
3. On graceful exit, it releases the handle and deletes the lock file

**The problem:** If a process crashes, is killed (SIGKILL), or the system loses power, the lock file may persist even though the process is dead.

## Existing Mitigation (OpenClaw Gateway)

The OpenClaw gateway has built-in stale lock detection:
- Checks if the holding PID is alive (`isPidAlive()`)
- Checks if the lock is older than 30 minutes (`DEFAULT_STALE_MS = 1800000`)
- Reclaims locks from dead PIDs or aged-out locks

**Why it wasn't enough:** The stale detection only triggers:
1. During lock acquisition retry loops (with exponential backoff)
2. During periodic cleanup (every 60 seconds via watchdog)

The 10-second acquisition timeout can expire before stale detection completes.

## Fixes Applied

### 1. Standalone Lock Cleaner Script

Created `/Users/kublai/.openclaw/agents/main/scripts/session-lock-cleaner.py`:
- Scans all agent session directories for `.jsonl.lock` files
- Removes locks where the PID is dead (immediate)
- Removes locks older than 30 minutes (age-based)
- Can run standalone or via cron

**Usage:**
```bash
# Dry run (show what would be removed)
python3 session-lock-cleaner.py --dry-run --verbose

# Actually clean
python3 session-lock-cleaner.py --verbose

# JSON output for scripting
python3 session-lock-cleaner.py --json
```

### 2. Recommended: Add to Cron

Add to crontab to run every 5 minutes:
```
*/5 * * * * /opt/homebrew/bin/python3 ~/.openclaw/agents/main/scripts/session-lock-cleaner.py >> ~/.openclaw/agents/main/logs/session-lock-cleaner.log 2>&1
```

### 3. Recommended: OpenClaw Source Patch

The OpenClaw session locking code should be patched to:
1. Check `isPidAlive()` immediately when encountering an existing lock
2. Remove dead-PID locks without waiting for timeout
3. Reduce the initial retry delay from exponential to immediate for dead-PID cases

**File to patch:** `/opt/homebrew/lib/node_modules/openclaw/dist/sessions-*.js`

**Key function:** The lock acquisition loop should call `shouldReclaimContendedLockFile()` before starting the retry loop, not just during retries.

## Verification

After applying fixes:
```bash
# Check for any remaining stale locks
python3 session-lock-cleaner.py --dry-run --verbose

# Should show either:
# - No locks found
# - Only valid locks (with live PIDs and recent timestamps)
```

## Prevention

To minimize future occurrences:
1. **Don't SIGKILL OpenClaw processes** — use SIGTERM for graceful shutdown
2. **Run the lock cleaner periodically** — catches any locks that slip through
3. **Monitor logs** — watch for "session file locked" errors as early warning

## Related Files

- Script: `~/.openclaw/agents/main/scripts/session-lock-cleaner.py`
- Logs: `~/.openclaw/agents/main/logs/session-lock-cleaner.log`
- OpenClaw source: `/opt/homebrew/lib/node_modules/openclaw/dist/sessions-*.js`

---
*Created: 2026-03-07*
*Issue reported by: Danny (+19194133445)*
*Fix implemented by: Kublai (via Claude Code)*
