# Heartbeat System Troubleshooting Guide

## Overview

The Kurultai heartbeat system consists of three scheduled phases:

| Phase | Interval | Script | Purpose |
|-------|----------|--------|---------|
| **tick** | 5 minutes | `watchdog-gather.sh` | Health monitor + task driver |
| **tock** | 30 minutes | `tock-gather.sh` | Agent telemetry collection |
| **kurultai** | 60 minutes | `hourly_reflection.sh` | Self-improvement cycle |

The **tick** is the heartbeat of the entire system. When ticks stop running, the fleet loses:
- Task queue monitoring
- Health endpoint checks
- Completion audit
- Subprocess anomaly detection
- Throughput anomaly alerts

## Tick Gap Detection

### What is a Tick Gap?

A tick gap occurs when `watchdog-gather.sh` doesn't run at its scheduled 5-minute interval. Gaps are detected by comparing the current time against the last successful tick epoch stored in:
```
~/.openclaw/agents/main/logs/.last_tick_epoch
```

### Alert Threshold

- **GAP_ALERT_THRESHOLD**: 480 seconds (8 minutes)
- Allows for some jitter + sleep/wake transitions
- Gaps > 8 minutes trigger `GAP_DETECTED` log entries

### Reading Gap Data

Gap data appears in tick telemetry (`logs/ticks.jsonl`):
```json
{
  "heartbeat": {
    "gap_detected": 1,
    "gap_minutes": 65,
    "last_epoch": 1773019200
  }
}
```

And in human-readable form (`logs/watchdog.log`):
```
[2026-03-09 01:19:35] GAP_DETECTED | missed=13 ticks | gap=65m | last_run_ts=2026-03-09 00:14:33
```

## Common Causes

### 1. Cron Job Not Running

**Symptoms:**
- Consistent gaps > 30 minutes
- No watchdog.log entries during gap period
- System otherwise healthy

**Diagnosis:**
```bash
# Check if OpenClaw cron is running
pgrep -f "openclaw-cron"

# Check cron job configuration
cat ~/.openclaw/cron/jobs.json | grep watchdog

# Check last execution time
stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" ~/.openclaw/agents/main/logs/.last_tick_epoch
```

**Recovery:**
```bash
# Restart OpenClaw cron
launchctl kickstart -k gui/$(id -u)/ai.openclaw.cron

# Or manually trigger one tick to verify
~/.openclaw/agents/main/scripts/watchdog-gather.sh
```

### 2. Lock Contention

**Symptoms:**
- Gaps of exactly 10-15 minutes
- Log shows "SKIP: already running"

**Root Cause:**
The watchdog uses a single-instance lock at `/tmp/watchdog-gather.lock`. If a previous tick crashes without cleanup, subsequent ticks skip execution.

**Diagnosis:**
```bash
# Check for stale lock
ls -la /tmp/watchdog-gather.lock
cat /tmp/watchdog-gather.lock/pid

# Verify if PID is still running
ps -p $(cat /tmp/watchdog-gather.lock/pid)
```

**Recovery:**
```bash
# Remove stale lock if PID is not running
rm -rf /tmp/watchdog-gather.lock

# Trigger immediate tick
~/.openclaw/agents/main/scripts/watchdog-gather.sh
```

### 3. System Sleep / Wake

**Symptoms:**
- Gaps correlate with sleep periods
- Single large gap (not multiple consecutive gaps)
- System resumes normal operation after wake

**Recovery:**
Automatic - no action needed. The gap detection tolerates sleep/wake transitions up to 8 minutes.

### 4. Script Crash (Unhandled Exception)

**Symptoms:**
- Gaps of 10-20 minutes
- Partial log entries (truncated mid-execution)
- No completion message in logs

**Diagnosis:**
```bash
# Run watchdog manually to see errors
~/.openclaw/agents/main/scripts/watchdog-gather.sh 2>&1 | tee /tmp/watchdog-debug.log
```

**Recovery:**
- Fix the script error (often Python import or Neo4j connection issue)
- Verify dependencies: `python3 -c "import neo4j; import redis"`

### 5. Neo4j Connection Issues

**Symptoms:**
- TICK reports `degraded` status with Neo4j disconnected
- Log entries: `TICK_LLM | action_needed=yes | severity=MEDIUM | reason=Neo4j graph database disconnected`
- Scripts using Neo4j fail or timeout
- Reflection pipeline completes but skips Neo4j-dependent steps

**Root Causes:**
1. Neo4j service not running
2. Network connectivity to Neo4j (bolt://localhost:7687)
3. Neo4j database in recovery or maintenance mode
4. Credential rotation (neo4j password changed)

**Diagnosis:**
```bash
# Check if Neo4j is running
pgrep -f neo4j

# Check Neo4j service status (if using launchd)
launchctl list | grep neo4j

# Test bolt connection
nc -z localhost 7687 && echo "Bolt port open" || echo "Bolt port CLOSED"

# Quick connectivity test via Python
python3 -c "
from neo4j import GraphDatabase
try:
    driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'password'))
    driver.verify_connectivity()
    print('Neo4j: CONNECTED')
    driver.close()
except Exception as e:
    print(f'Neo4j: FAILED - {e}')
"
```

**Recovery:**
```bash
# If Neo4j service stopped, restart it
launchctl start com.neo4j.service  # Adjust service name as needed

# Or if using manual Neo4j installation
neo4j start

# After restart, verify connection
~/.openclaw/agents/main/scripts/neo4j-state-sync.py --health-check

# If credential issue, update in scripts that need it
# Most scripts use environment or ~/.openclaw/config
grep -r "BOLT_URI\|NEO4J_URI" ~/.openclaw/agents/main/scripts/
```

**Graceful Degradation:**
The system is designed to operate with Neo4j temporarily disconnected:
- TICK continues monitoring (degraded status)
- Tasks still execute (filesystem-based queuing works)
- Reflection completes but skips graph operations
- When Neo4j reconnects, `neo4j-state-sync.py` backfills missing data

### 6. Gateway Process Down

**Symptoms:**
- Gaps combined with gateway restarts
- `action=restart` or `action=restart_ok` in log entries

**Recovery:**
- Automatic restart is attempted by the watchdog
- Manual: `launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway`

## Health Status Indicators

The watchdog reports three statuses:

| Status | Exit Code | Meaning |
|--------|-----------|---------|
| `healthy` | 0 | All checks passed |
| `degraded` | 1 | Warning condition (high CPU, errors, latency, etc.) |
| `down` | 2 | Gateway not running, restart attempted |
| `down` | 3 | Gateway restart failed |

## Verification Commands

### Check Current Tick Health
```bash
# Latest tick summary
cat ~/.openclaw/agents/main/logs/tick-summary.txt

# Recent tick log entries
tail -20 ~/.openclaw/agents/main/logs/watchdog.log

# Tick telemetry (last 10 ticks)
tail -10 ~/.openclaw/agents/main/logs/ticks.jsonl | jq
```

### Time Since Last Tick
```bash
EPOCH_NOW=$(date +%s)
LAST_EPOCH=$(cat ~/.openclaw/agents/main/logs/.last_tick_epoch)
GAP_SECONDS=$((EPOCH_NOW - LAST_EPOCH))
GAP_MINUTES=$((GAP_SECONDS / 60))
echo "Last tick: ${GAP_MINUTES} minutes ago"
```

### Monitor Tick Gaps in Real-Time
```bash
# Watch for new GAP_DETECTED entries
tail -f ~/.openclaw/agents/main/logs/watchdog.log | grep --line-buffered GAP_DETECTED
```

## Recovery Checklist

When you detect a tick gap:

1. **Check lock contention**
   ```bash
   ls -la /tmp/watchdog-gather.lock
   ps -p $(cat /tmp/watchdog-gather.lock/pid 2>/dev/null) || rm -rf /tmp/watchdog-gather.lock
   ```

2. **Verify cron is running**
   ```bash
   pgrep -f "openclaw-cron" || launchctl kickstart -k gui/$(id -u)/ai.openclaw.cron
   ```

3. **Check gateway status**
   ```bash
   pgrep -f "openclaw-gateway" || launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway
   ```

4. **Run manual tick to verify**
   ```bash
   ~/.openclaw/agents/main/scripts/watchdog-gather.sh
   echo "Exit code: $?"
   ```

5. **Verify tick was recorded**
   ```bash
   stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" ~/.openclaw/agents/main/logs/.last_tick_epoch
   ```

## Related Files

| File | Purpose |
|------|---------|
| `scripts/watchdog-gather.sh` | Main tick script |
| `scripts/heartbeat-watchdog.sh` | Legacy (superseded by task-watcher.py) |
| `logs/.last_tick_epoch` | Timestamp of last successful tick |
| `logs/watchdog.log` | Human-readable tick log |
| `logs/ticks.jsonl` | Machine-readable tick history |
| `logs/tick-summary.txt` | Compact summary for LLM consumption |

## Related Documentation

- `docs/kurultai-monitoring.md` - the.kurult.ai uptime monitoring
- `docs/reflection-pipeline-reference.md` - Hourly self-improvement cycle
- `docs/completion-gate.md` - Task completion verification
- `docs/throughput-anomaly-executing-no-output.md` - EXECUTING_NO_OUTPUT diagnostic guide
- `docs/auth-health-preflight.md` - LLM authentication preflight pattern (prevents reflection blackouts)
- `docs/NEO4J_PATTERNS.md` - Neo4j graph database usage patterns

## Alerts and Escalation

| Gap Duration | Severity | Action |
|--------------|----------|--------|
| < 10 minutes | INFO | Log only |
| 10-30 minutes | LOW | Create task for Ogedei |
| 30-60 minutes | MEDIUM | Escalate to Kublai |
| > 60 minutes | HIGH | Critical alert |

## Notes

- Tick gaps are measured wall-clock time, not CPU time
- The system tolerates brief gaps (< 8 minutes) for normal jitter
- Persistent gaps indicate a deeper issue (cron, lock, or gateway)
- After recovering from a gap, monitor for 3-5 ticks to confirm stability
