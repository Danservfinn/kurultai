# the.kurult.ai Uptime Monitoring

## Overview

Browser-based monitoring for https://the.kurult.ai that detects JavaScript errors and rendering failures. HTTP-only checks **CANNOT** detect JavaScript syntax errors because the page returns HTTP 200 with valid HTML but is broken.

## Script Location

`~/.openclaw/agents/main/scripts/kurultai-monitor.py`

## Schedule

Every 5 minutes via cron (OpenClaw cron system)

## What It Checks

| Check | Why | Detection Method |
|-------|-----|------------------|
| HTTP Status | Basic connectivity | Response.status |
| Page Load | Server responding | goto() with timeout |
| Console Errors | **JavaScript syntax errors** | Playwright console handler |
| Board Rendering | Page stuck on "Loading..." | wait_for_selector() |
| Network Idle | All requests finished | wait_for_load_state() |

## Alert Thresholds

| Consecutive Failures | Downtime | Action |
|---------------------|----------|--------|
| 3 | 15 minutes | Create high-priority task for Ogedei |
| 10 | 50 minutes | Escalate to Kublai (critical priority) |

## State File

`~/.openclaw/agents/main/logs/kurultai-monitor-state.json`

Tracks:
- `consecutive_failures` - Current failure streak
- `last_failure` - ISO timestamp of last failure
- `last_success` - ISO timestamp of last success
- `downtime_start` - When the current downtime began

## Log File

`~/.openclaw/agents/main/logs/kurultai-monitor.log`

Format: `[timestamp] [level] message`

## Benign Errors Filtered

The following console errors are filtered as non-critical:
- Cloudflare Insights CSP violations
- Non-Error promise rejection
- chrome-extension:// errors
- Any CSP directive violations

## Recovery Detection

When the site recovers after failures:
- Logs recovery event with downtime duration
- Creates normal-priority task for Ogedei
- Resets consecutive failure counter

## Testing

To test the monitor manually:
```bash
python3 ~/.openclaw/agents/main/scripts/kurultai-monitor.py
```

To simulate a failure (for testing alerts):
1. Add `throw new Error("TEST");` to the.kurult.ai inline JavaScript
2. Wait 15 minutes (3 checks) for Ogedei alert
3. Fix the error
4. Verify recovery task is created

## Dependencies

- Python 3
- playwright (`pip install playwright`)
- Chromium browser (`playwright install chromium`)

## Why Browser-Based Monitoring Matters

On 2026-03-07, the.kurult.ai had a JavaScript syntax error that caused:
- HTTP 200 response (server OK)
- Valid HTML returned
- Page stuck on "Loading..." forever
- **20-minute outage went undetected** by HTTP-only checks

This monitoring system would have detected the console error and alerted within 15 minutes.

## Cron Configuration

In `~/.openclaw/cron/jobs.json`:
```json
{
  "id": "kurultai-uptime-monitor",
  "name": "the.kurult.ai uptime monitor",
  "schedule": {
    "expr": "*/5 * * * *"
  },
  "payload": {
    "text": "/usr/bin/python3 /Users/kublai/.openclaw/agents/main/scripts/kurultai-monitor.py"
  }
}
```
