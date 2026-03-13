---
name: orphan-process-oom-fix
description: Exit code -9 SIGKILL from orphaned Claude processes accumulating
type: feedback
---

# Orphan Process OOM Bug (Exit Code -9)

## Rule
**Always run orphaned process cleanup before agent reflection** to prevent SIGKILL from OOM.

## Why
Discovered 2026-03-12 during jochi reflection investigation. Tasks failing with exit code -9:
- 2 tasks failed in the past hour with exit code -9 (SIGKILL)
- `cleanup-orphan-claude.sh` existed but was **manual-only** (not in hourly_reflection.sh)
- Dry run found **10 orphaned processes using 3.9% RAM** (>2 hours old)

Exit code -9 = SIGKILL, typically from OS OOM killer when memory pressure accumulates from orphaned subprocesses (especially /horde-review spawns).

## How to Apply
Integrate `cleanup-orphan-claude.sh` into `hourly_reflection.sh`:
1. Add call after `session_health_watchdog.py` in `run_agent_reflection()` function
2. Use `--run --older-minutes=120` flags (auto-kill processes >2h old)
3. Log to `logs/orphan-cleanup.log`

Fixed in `/Users/kublai/.openclaw/agents/main/scripts/hourly_reflection.sh` lines 387-393.

## Files Modified
- `scripts/hourly_reflection.sh` - Added orphan cleanup call (lines 387-393)
- `memory/orphan-process-oom-fix.md` - This documentation

## Evidence
```
[2026-03-12 14:33:01] Found 40 Claude Code process(es) using 12.3% RAM
[2026-03-12 14:33:01] Found 10 orphaned process(es) using 3.9% RAM
[2026-03-12 14:33:01] DRY RUN: Would terminate 10 process(es)
```
