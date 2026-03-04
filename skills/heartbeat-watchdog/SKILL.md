# Heartbeat Watchdog (Tick)

**Model:** lmstudio/qwen3.5-9b-mlx (local)
**Schedule:** Every 5 minutes
**Log:** ~/.openclaw/agents/main/logs/watchdog.log

## Purpose

You are the watchdog. Every 5 minutes you run the tick script which:
1. Gathers all infrastructure health metrics
2. Pushes forward any pending agent tasks (runs task-consumer and spawn-consumer)
3. Makes a health decision
4. Logs everything

You review the script's output and confirm or override.

## Step 1: Run the Script

```bash
bash ~/.openclaw/agents/main/scripts/watchdog-gather.sh
```

The script outputs a summary like:
```
TICK 2026-03-04 01:05:00
GATEWAY: up pid=92651 http=200 latency=6ms uptime=4h0m
PROCESS: cpu=2.3% mem=1.8% rss=142MB threads=12
ERRORS:  last5m=0 last1h=3 fatal=0
SERVICES: neo4j=up redis=up
TASKS:   pending=0 dispatched=0 spawn=0 queues=[]
TRENDS:  uptime_1h=100% avg_cpu=3.4% errors_1h=3 restarts_1h=0
DECISION: healthy
ACTION:   none
REASON:   all checks passed
```

## Step 2: Decide

The script already made a decision (DECISION line). Review it:

- If everything looks normal, **accept the script's decision**
- Only override if you see something the script missed:
  - Trends worsening but script says healthy
  - Multiple services borderline but none triggered threshold
  - Tasks stuck (pending > 0 for multiple cycles)

Your decision: `healthy`, `degraded`, or `down`

## Step 3: Log

Append ONE line to `~/.openclaw/agents/main/logs/watchdog.log`:

```
[YYYY-MM-DD HH:MM:SS] WATCHDOG_LLM | status=<decision> | accepted_bash=yes|no | note=<10 words max>
```

## Rules

- ONE bash command. Do not run individual commands.
- ONE log line. Do not be verbose.
- If script fails: `status=unknown | accepted_bash=error | note=script failed`
- Keep total execution under 60 seconds of LLM time.
