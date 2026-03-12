# Auth Heartbeat — Credential Health Monitoring

## Overview

The auth heartbeat system provides **real-time credential health status** for all agents. Unlike the credential format check (`credential-health-monitor.py`), auth heartbeat **actually tests authentication** by attempting a minimal claude-agent request.

## Purpose

1. **Prevent auth failures during task execution** — Tasks are only dispatched to agents with healthy auth
2. **Reduce false-positive task failures** — Auth issues caught before spawn, not during execution
3. **Early detection of credential expiry** — 5-minute stale threshold catches issues quickly
4. **Minimal overhead** — Auth check only runs once per tick (5 min), reuses cached results

## How It Works

### 1. Auth Check (every tick)

`auth_heartbeat.py` runs during each tick (watchdog-gather.sh SECTION 4c):

```bash
AUTH_HEARTBEAT_OUTPUT=$(python3 "$SCRIPTS/auth_heartbeat.py" 2>&1 || true)
AUTH_HEARTBEAT_FAILED=$(echo "$AUTH_HEARTBEAT_OUTPUT" | grep -c "✗" || true)
```

For each agent:
1. Changes to agent directory
2. Sets `CLAUDE_PROVIDER` (zai or alibaba)
3. Runs `claude-agent` with a minimal prompt ("Respond with exactly: OK")
4. Records success/failure with timestamp

### 2. Heartbeat File

Results written to `logs/auth-heartbeat.json`:

```json
{
  "jochi": {
    "status": "ok",
    "last_success": "2026-03-11T23:39:34.818899",
    "error": null
  },
  "_meta": {
    "last_check": "2026-03-11T23:40:20.261585",
    "stale_threshold_seconds": 300
  }
}
```

### 3. Stale Detection

Auth status is considered **stale** after 5 minutes (300 seconds). On next tick:
- If still fresh (< 5 min): Skip recheck, use cached result
- If stale (> 5 min) or missing: Run actual auth test

### 4. Integration Points

| Location | Purpose |
|----------|---------|
| `watchdog-gather.sh` SECTION 4c | Run auth check during tick |
| `tick-summary.txt` | Line: `AUTH_HEARTBEAT: failed_checks=N` |
| `ticks.jsonl` | Field: `auth_heartbeat.failed_checks` |
| `watchdog.log` | Field: `auth_heartbeat_failed=N` |
| `auth-failures.jsonl` | Log entries when checks fail |

## Provider Mapping

Matches `hourly_reflection.sh` provider configuration:

| Agent | Provider | Token Type |
|-------|----------|------------|
| kublai, temujin, mongke, chagatai | zai | Z.AI proxy tokens |
| jochi, ogedei | alibaba | sk-sp-* tokens |

## Usage

### Check all agents
```bash
python3 scripts/auth_heartbeat.py
```

### Check specific agent
```bash
python3 scripts/auth_heartbeat.py --agent jochi
```

### Check-only (don't update file)
```bash
python3 scripts/auth_heartbeat.py --check-only
```

### JSON output
```bash
python3 scripts/auth_heartbeat.py --json
```

### Force recheck (ignore cache)
```bash
python3 scripts/auth_heartbeat.py --force
```

## Error Handling

When auth check fails:
1. Logs to `auth-failures.jsonl` with timestamp and agent
2. Sets `status: "fail"` and `error` message in heartbeat file
3. Continues to next agent (doesn't stop the tick)
4. Failed count appears in tick outputs

## Monitoring

### Healthy tick output
```
AUTH_HEARTBEAT: failed_checks=0
```

### Degraded tick output
```
AUTH_HEARTBEAT: failed_checks=2
```

### Investigating failures
```bash
# Check heartbeat file
cat logs/auth-heartbeat.json | jq '.[] | select(.status=="fail")'

# Check auth failure log
tail -20 logs/auth-failures.jsonl | jq
```

## Implementation History

- **2026-03-11**: Initial implementation to address jochi/ogedei auth preflight failures
  - Created `auth_heartbeat.py` script
  - Integrated into watchdog-gather.sh SECTION 4c
  - Added to tick-summary.txt, ticks.jsonl, watchdog.log
  - 5-minute stale threshold balances freshness vs overhead

## Related Files

- `scripts/auth_heartbeat.py` — Main auth check script
- `scripts/watchdog-gather.sh` — Tick integration (SECTION 4c)
- `scripts/credential-health-monitor.py` — Format validation (sk-ant- check)
- `scripts/hourly_reflection.sh` — Kurultai auth preflight (60-min cycle)
- `logs/auth-heartbeat.json` — Auth status cache
- `logs/auth-failures.jsonl` — Failure log
