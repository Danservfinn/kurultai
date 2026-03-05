---
name: heartbeat-watchdog
description: "5-minute system health check (tick) for the Kurultai. Runs watchdog-gather.sh to collect Neo4j, Redis, cron, and agent health metrics. Use when checking system health, diagnosing failures, or understanding the tick pipeline."
---

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

## Step 2: LLM Triage (automatic)

The script now includes a **local LLM triage** step (ollama/qwen3.5:9b) that:
1. Reviews the tick summary + last 3 tick trends
2. Decides if Kublai should take action (ACTION_NEEDED: yes/no)
3. If yes, creates a task in Kublai's queue with severity, reason, and suggested action

The triage result is logged to watchdog.log as:
```
[YYYY-MM-DD HH:MM:SS] TICK_LLM | action_needed=yes|no | severity=LOW|MEDIUM|HIGH|CRITICAL | reason=...
```

Rule-based actions (kublai-actions.py) still run as a safety net alongside the LLM triage.

## Step 3: Kublai Review (when triggered)

When the LLM triage creates a task, Kublai reviews the tick data and can:
- Investigate further (check logs, run diagnostics)
- Delegate to another agent (temujin for code, ogedei for infra, jochi for debugging)
- Dismiss if the LLM overreacted (log reasoning)
- Escalate if the situation is worse than described

## Rules

- ONE bash command. Do not run individual commands.
- If script fails: check `watchdog.log` for the error
- LLM triage has a 60s timeout — falls through to rule-based actions on failure
- Keep total tick cycle under 90 seconds
