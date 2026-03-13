# Heartbeat Quick-Reference Card

> **One-page diagnostic guide for Kurultai heartbeat incidents**
> Last updated: 2026-03-12

## Status Check (30 seconds)

```bash
# All-in-one health check
echo "=== TICK STATUS ===" && \
cat ~/.openclaw/agents/main/logs/tick-summary.txt 2>/dev/null | head -5 && \
echo -e "\n=== TIME SINCE LAST TICK ===" && \
EPOCH_NOW=$(date +%s) && \
LAST_EPOCH=$(cat ~/.openclaw/agents/main/logs/.last_tick_epoch 2>/dev/null || echo 0) && \
GAP_MINUTES=$(( (EPOCH_NOW - LAST_EPOCH) / 60 )) && \
echo "${GAP_MINUTES} minutes ago" && \
echo -e "\n=== CRITICAL SERVICES ===" && \
echo -n "Neo4j: " && (nc -z localhost 7687 2>/dev/null && echo "UP" || echo "DOWN") && \
echo -n "Redis:  " && (nc -z localhost 6379 2>/dev/null && echo "UP" || echo "DOWN") && \
echo -e "\n=== AGENT PROCESSES ===" && \
pgrep -f "claude-agent" | wc -l | xargs echo "Active claude-agent processes:"
```

## Threshold Reference

| Metric | Healthy | Warning | Critical |
|--------|---------|---------|----------|
| Tick gap | < 8 min | 8-30 min | > 30 min |
| Queue depth | < 3 | 3-8 | > 8 |
| Neo4j latency | < 100ms | 100-500ms | > 500ms |
| Auth heartbeat age | < 5 min | 5-15 min | > 15 min |
| Reflection lag | < 90 min | 90-120 min | > 120 min |

## Exit Codes

| Code | Meaning | Action |
|------|---------|--------|
| 0 | Healthy | None |
| 1 | Degraded | Monitor |
| 2 | Down + restart attempted | Check logs |
| 3 | Down + restart failed | Manual intervention |

## Common Fixes (copy-paste ready)

### Tick not running
```bash
# Remove stale lock
rm -rf /tmp/watchdog-gather.lock
# Trigger immediate tick
~/.openclaw/agents/main/scripts/watchdog-gather.sh
```

### Cron job stopped
```bash
launchctl kickstart -k gui/$(id -u)/ai.openclaw.cron
```

### Gateway down
```bash
launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway
```

### Neo4j connection failed
```bash
# Check if Neo4j is running
pgrep -f neo4j || echo "Neo4j not running"
# Test bolt port
nc -z localhost 7687 && echo "Bolt OK" || echo "Bolt FAIL"
# Restart if needed (adjust for your installation)
brew services restart neo4j 2>/dev/null || neo4j start
```

### Redis connection failed
```bash
# Check Redis
redis-cli ping
# Restart if needed
brew services restart redis
```

### Stuck reflection process
```bash
# Kill stuck reflection
pkill -9 -f "claude-agent.*reflection"
# Clear checkpoint
rm -f ~/.openclaw/agents/main/logs/reflection-status.json
```

### Circuit breaker deadlock
```bash
# Force circuit breaker health check
python3 ~/.openclaw/agents/main/scripts/circuit_breaker_health.py
# Check state
cat ~/.openclaw/agents/main/logs/circuit-breaker-state.json | python3 -m json.tool
```

## File Locations

| Purpose | Path |
|---------|------|
| Tick log | `logs/watchdog.log` |
| Tick telemetry | `logs/ticks.jsonl` |
| Tick summary | `logs/tick-summary.txt` |
| Last tick epoch | `logs/.last_tick_epoch` |
| Auth heartbeat | `logs/auth-heartbeat.json` |
| Circuit breaker state | `logs/circuit-breaker-state.json` |
| Reflection status | `logs/reflection-status.json` |
| Tock snapshots | `logs/tock/*.json` |

## Alert Severity Actions

| Severity | Response Time | Action |
|----------|---------------|--------|
| INFO | None | Log only |
| LOW | 30 min | Create task for Ogedei |
| MEDIUM | 10 min | Escalate to Kublai |
| HIGH | Immediate | Critical alert + manual fix |

## Phase Intervals

| Phase | Interval | Script | Timeout |
|-------|----------|--------|---------|
| TICK | 5 min | `watchdog-gather.sh` | 180s |
| TOCK | 30 min | `tock-gather.sh` | 30s |
| KURULTAI | 60 min | `hourly_reflection.sh` | 7200s |

## Related Docs

- Full architecture: `docs/heartbeat-system.md`
- Troubleshooting: `docs/heartbeat-troubleshooting.md`
- Reflection pipeline: `docs/reflection-pipeline-reference.md`
- Auth heartbeat: `docs/auth-heartbeat-reference.md`
