# Heartbeat Watchdog Skill

**Name:** heartbeat-watchdog  
**Description:** Monitors OpenClaw gateway health using local LLM for intelligent diagnostics and decision-making  
**Model:** lmstudio/qwen3.5-9b-mlx (local)

---

## Purpose

This skill monitors the OpenClaw gateway daemon and uses local LLM inference to:
1. Analyze gateway health metrics
2. Detect anomalies in process behavior
3. Make intelligent restart decisions
4. Generate contextual diagnostic reports

---

## Execution Flow

### 1. Gather System State

Run these commands to collect health data:

```bash
# Check gateway process
pgrep -f "openclaw-gateway"

# Get process details
ps -p <PID> -o pid,cpu,mem,rss,time,command

# Check gateway endpoint
curl -s http://127.0.0.1:18789/health 2>/dev/null || echo "UNREACHABLE"

# Check recent logs
tail -50 ~/.openclaw/logs/openclaw.log 2>/dev/null

# Check system load
top -l 1 | head -10
```

### 2. Analyze with Local LLM

Pass the collected metrics to the local LLM with this prompt:

```
Analyze this OpenClaw gateway health data:

[INSERT METRICS HERE]

Determine:
1. Is the gateway healthy? (YES/NO/DEGRADED)
2. Any anomalies detected? (list them)
3. Action required? (NONE/WARN/RESTART/ALERT)
4. Confidence level? (0-100%)

Respond in JSON format:
{
  "status": "healthy|degraded|down",
  "anomalies": [],
  "action": "none|warn|restart|alert",
  "confidence": 0-100,
  "reasoning": "brief explanation"
}
```

### 3. Execute Decision

Based on LLM output:

| Action | Execute |
|--------|---------|
| `none` | Log status, exit |
| `warn` | Log warning, notify Kublai |
| `restart` | Run `launchctl kickstart` |
| `alert` | Restart + notify + create alert file |

### 4. Log Results

Write to `/Users/kublai/.openclaw/agents/main/logs/watchdog.log`:

```
[YYYY-MM-DD HH:MM:SS] === Watchdog Check (LLM-Powered) ===
[YYYY-MM-DD HH:MM:SS] Gateway PID: <pid>
[YYYY-MM-DD HH:MM:SS] CPU: X%, MEM: Y%
[YYYY-MM-DD HH:MM:SS] LLM Status: <status>
[YYYY-MM-DD HH:MM:SS] LLM Action: <action>
[YYYY-MM-DD HH:MM:SS] Confidence: XX%
[YYYY-MM-DD HH:MM:SS] Reasoning: <reasoning>
[YYYY-MM-DD HH:MM:SS] === Check Complete ===
```

---

## Tools to Use

- `exec` - Run system commands (pgrep, ps, curl, top)
- `read` - Read log files
- `write` - Append to watchdog.log
- `message` - Send alerts to Kublai if needed
- `sessions_spawn` - Spawn local LLM session for analysis (model: lmstudio/qwen3.5-9b-mlx)

---

## Response Format

Always end with a concise summary:

```
**Watchdog Check Complete**
- Gateway: ✅ Running (PID: XXXXX)
- Health: HEALTHY / DEGRADED / DOWN
- Action: None / Warned / Restarted / Alerted
- LLM Confidence: XX%
```

---

## Error Handling

- If gateway is unreachable AND no PID: Restart immediately (no LLM needed)
- If LLM fails to respond: Fall back to threshold-based logic (CPU >80% = warn, MEM >50% = warn)
- If logs unavailable: Proceed with process checks only

---

## Schedule

Runs every 5 minutes via OpenClaw cron.
