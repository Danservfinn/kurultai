# Signal Integration Issue - Diagnosis & Resolution

## Issue Summary
Signal messages were delayed or not arriving consistently. The "cartoon" message sent at ~04:58 was not received, though previous messages ("Sweet", "What's your status") had worked.

## Root Cause

The **signal-cli daemon was not running**. OpenClaw's signal-channel plugin was trying to connect to the SSE events endpoint at `http://127.0.0.1:8080/api/v1/events`, but the daemon process had crashed or failed to start, resulting in continuous `fetch failed` errors.

### Evidence Chain:
1. **04:30** - Last successful message received
2. **04:52-04:58** - Continuous SSE connection errors in logs:
   ```
   Signal SSE stream error: TypeError: fetch failed
   Signal SSE connection lost, reconnecting in 10s...
   ```
3. **Port 8080** - Not responding to HTTP requests
4. **No signal-cli process** - Daemon not running in process list

## Why OpenClaw Didn't Auto-Restart the Daemon

The OpenClaw signal plugin has `autoStart: true` by default, but it appears the daemon startup had failed earlier and the retry logic only attempts to connect to the existing daemon, not respawn it. The plugin continuously retried the SSE connection without attempting to restart the daemon process.

## Fix Applied

Manually started the signal-cli daemon with the correct parameters:

```bash
signal-cli daemon --http 127.0.0.1:8080 --receive-mode on-start --ignore-stories
```

This started the HTTP interface on port 8080 with:
- `--receive-mode on-start`: Start receiving messages immediately
- `--ignore-stories`: Skip story messages (per config)

## Verification

1. **Health check**: `openclaw status --deep` now shows:
   ```
   │ Signal   │ OK        │ ok (default:default:47ms) │
   ```

2. **Daemon logs**: Confirmed receipt of messages:
   ```
   Envelope from: "Danny" +19194133445 (device: 1) to +15165643945
   Timestamp: 1770699926999 (2026-02-10T05:05:26.999Z)
   Received a receipt message
   ```

3. **Endpoints verified**:
   - `GET /api/v1/check` → 200 OK
   - `GET /api/v1/events` → SSE stream (kept-alive)
   - `POST /api/v1/rpc` → JSON-RPC working

## Preventive Measures

To prevent this issue in the future:

1. **Monitor daemon health** - Set up a cron job or systemd service to ensure signal-cli daemon stays running
2. **Auto-restart** - Configure OpenClaw or a process manager (supervisord, systemd) to restart the daemon if it crashes
3. **Log alerts** - Set up alerts for repeated "fetch failed" errors in OpenClaw logs

## Configuration Reference

Current working config in `~/.openclaw/openclaw.json`:
```json
{
  "channels": {
    "signal": {
      "enabled": true,
      "account": "+15165643945",
      "cliPath": "/app/signal-cli-wrapper.sh",
      "httpHost": "127.0.0.1",
      "httpPort": 8080,
      "startupTimeoutMs": 120000,
      "receiveMode": "on-start",
      "dmPolicy": "allowlist",
      "groupPolicy": "allowlist",
      "allowFrom": ["+15165643945", "+19194133445"],
      "ignoreStories": true
    }
  }
}
```

## Signal Flow Architecture

```
Signal App → Signal Servers → signal-cli daemon (port 8080) 
                                           ↓
                                     OpenClaw Gateway (SSE /api/v1/events)
                                           ↓
                                     Agent Session
```

The daemon must be running for message flow. OpenClaw connects via SSE to receive real-time events.

---
**Resolved**: 2026-02-10 05:05 UTC
**Status**: Messages flowing correctly
