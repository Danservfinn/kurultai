# Auto-Dispatch Cron

Automatic task dispatcher for Kurultai agents. Runs every 5 minutes via the heartbeat-watchdog cron job.

## Problem Solved

Tasks created in agent queues (`~/.openclaw/agents/{agent}/tasks/*.md`) by kublai-actions.py, kublai-initiative.py, and task_router.py were not being dispatched to agents. The legacy `session-runner.sh` was a stub, and `heartbeat-task-executor.py` was not being called reliably. Result: tasks sat in queues for hours.

## Architecture

```
heartbeat-watchdog (OpenClaw cron, every 5min)
    └── heartbeat-watchdog.sh
        ├── auto_dispatch.py     ← PRIMARY dispatcher
        └── heartbeat-task-executor.py  ← fallback
```

## How It Works

Every 5 minutes, `auto_dispatch.py`:

1. **Cleans stale tasks**: `.executing` files stuck >15 minutes are reverted to pending
2. **Checks agent availability**: Skips agents with active `.executing` tasks (max 1 concurrent)
3. **Priority dispatch**: Picks highest-priority pending task (high > normal > low, FIFO within)
4. **Dispatches via `openclaw agent`**: Non-blocking Popen, one task per agent per cycle
5. **Logs everything**: JSONL log for tock metrics, per-agent dispatch logs

## Files

| File | Purpose |
|------|---------|
| `auto_dispatch.py` | Main dispatcher script |
| `auto-dispatch.sh` | Shell wrapper for cron |
| `test_auto_dispatch.py` | 30 unit tests |
| `heartbeat-watchdog.sh` | Integration point (calls auto_dispatch.py) |

## Usage

```bash
# Normal operation (via heartbeat-watchdog, automatic)
python3 auto_dispatch.py

# Dispatch single agent
python3 auto_dispatch.py --agent temujin

# Preview what would be dispatched
python3 auto_dispatch.py --dry-run

# Only clean stale tasks, no dispatch
python3 auto_dispatch.py --cleanup

# Skip lock (for testing)
python3 auto_dispatch.py --dry-run --no-lock
```

## Logs

- `~/.openclaw/agents/main/logs/auto-dispatch.jsonl` — Machine-readable dispatch log
- `~/.openclaw/agents/main/logs/auto-dispatch-cron.log` — Cron output
- `~/.openclaw/agents/main/logs/auto-dispatch-state.json` — Current dispatch state
- `~/.openclaw/agents/main/logs/dispatch-{agent}.log` — Per-agent dispatch output

## Configuration

| Constant | Value | Description |
|----------|-------|-------------|
| `STALE_EXECUTING_SECS` | 900 (15min) | Timeout before reverting stuck tasks |
| `MAX_DISPATCHES_PER_CYCLE` | 3 | Max tasks dispatched per 5-min cycle |
| `DISPATCH_AGENTS` | temujin, mongke, chagatai, jochi, ogedei | Agents eligible for dispatch |

## Optional: System Crontab

For belt-and-suspenders reliability, also add to system crontab:

```
*/5 * * * * /Users/kublai/.openclaw/agents/main/scripts/auto-dispatch.sh >> /Users/kublai/.openclaw/agents/main/logs/auto-dispatch-cron.log 2>&1
```

The lock file prevents duplicate cycles if both OpenClaw cron and system crontab fire.

## Tests

```bash
cd ~/.openclaw/agents/main/scripts
python3 test_auto_dispatch.py
```

30 tests covering: task listing, priority ordering, stale cleanup, dispatch, dry-run, lock file, cycle stats.
