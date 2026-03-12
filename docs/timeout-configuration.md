# Timeout Configuration

## Priority Timeouts
- High: 7200s (2 hours)
- Normal: 7200s (2 hours)
- Low: 7200s (2 hours)

## Skill-Specific Timeouts
Skills that require extra time:
- /horde-brainstorming: +7200s (2 hours)
- /golden-horde: +7200s (2 hours)
- /horde-implement: +7200s (2 hours)
- /horde-review: +7200s (2 hours)

- /horde-plan: +7200s (2 hours)

## API Latency Buffer
All timeouts include +300s (5 minutes) API latency buffer to account for:
- Model response delays
- Rate limiting backoff
- Network latency

## Timeout Enforcement
1. Warning at 30s before hard limit (logged to console)
2. SIGTERM (graceful shutdown signal sent)
3. 30-second grace period for cleanup
4. SIGKILL (forceful termination)

## Configuration
Timeout values are defined in `task-watcher.py`:
- `TIMEOUT_DEFAULT = 7200`
- `TIMEOUT_BY_PRIORITY = {'high': 7200, 'normal': 7200, 'low': 7200}`
- `API_LATENCY_BUFFER = 300`
