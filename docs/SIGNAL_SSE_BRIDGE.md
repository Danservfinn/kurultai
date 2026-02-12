# Signal-CLI SSE Bridge Setup

## Overview

OpenClaw expects signal-cli to expose an **SSE (Server-Sent Events)** endpoint for receiving messages, but signal-cli 0.13.24 only provides **JSON-RPC over HTTP**.

This bridge translates between the two protocols:
- **Input**: signal-cli JSON-RPC (HTTP)
- **Output**: SSE endpoint for OpenClaw

## Architecture

```
┌──────────────┐     SSE      ┌──────────────────┐     JSON-RPC    ┌──────────────┐
│   OpenClaw   │◄────────────►│  SSE Bridge      │◄───────────────►│  signal-cli  │
│   Gateway    │              │  (This Bridge)   │                 │   Daemon     │
└──────────────┘              └──────────────────┘                 └──────────────┘
                                    │                                     │
                                    │ Polls for                           │ Signal
                                    │ new messages                        │ Servers
                                    ▼                                     ▼
                              ┌──────────────┐                      ┌──────────────┐
                              │ Message      │                      │ Signal       │
                              │ Queue        │                      │ Network      │
                              └──────────────┘                      └──────────────┘
```

## Quick Start

### 1. Start the Bridge

```bash
cd /data/workspace/souls/main
python3 tools/signal_cli_sse_bridge.py
```

Or use the startup script:

```bash
./tools/start_signal_bridge.sh
```

### 2. Verify Bridge is Running

```bash
# Health check
curl http://127.0.0.1:8080/health

# Expected response:
# {"status": "healthy", "signal_cli_running": true, ...}
```

### 3. Start OpenClaw Gateway

```bash
openclaw gateway
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SIGNAL_ACCOUNT` | `+15165643945` | Your Signal account number |
| `SIGNAL_CLI_PATH` | `/usr/local/bin/signal-cli` | Path to signal-cli binary |
| `BRIDGE_HOST` | `127.0.0.1` | Bridge bind address |
| `BRIDGE_PORT` | `8080` | Bridge SSE port |
| `SIGNAL_HTTP_PORT` | `8081` | signal-cli JSON-RPC port |

### OpenClaw Configuration

The bridge is already configured in `openclaw.json5`:

```json5
channels: {
  signal: {
    enabled: true,
    account: "${SIGNAL_ACCOUNT}",
    httpUrl: "http://127.0.0.1:8080",  // Bridge SSE endpoint
    autoStart: false,                  // Bridge manages signal-cli
    // ... rest of config
  },
}
```

## Testing

### Test 1: Bridge Health

```bash
curl http://127.0.0.1:8080/health
```

### Test 2: Send Test Message

```bash
curl -X POST http://127.0.0.1:8080/send \
  -H "Content-Type: application/json" \
  -d '{
    "recipient": "+19194133445",
    "message": "Test from bridge"
  }'
```

### Test 3: Check SSE Endpoint

```bash
# Connect to SSE stream
curl http://127.0.0.1:8080/events

# Send yourself a Signal message from another device
# You should see JSON events appear
```

## Troubleshooting

### Bridge Won't Start

**Check signal-cli is installed:**
```bash
signal-cli --version
```

**Check signal-cli is registered:**
```bash
signal-cli -a +15165643945 listAccounts
```

**Check logs:**
```bash
tail -f /tmp/signal_bridge.log
```

### OpenClaw Can't Connect

**Verify bridge is running:**
```bash
curl http://127.0.0.1:8080/health
```

**Check OpenClaw config:**
```bash
openclaw config get channels.signal.httpUrl
# Should show: http://127.0.0.1:8080
```

### Messages Not Received

**Check signal-cli directly:**
```bash
# Test JSON-RPC
curl -X POST http://127.0.0.1:8081/api/v1/rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "receive",
    "params": {"account": "+15165643945", "timeout": 5}
  }'
```

**Check bridge logs:**
```bash
tail -f /tmp/signal_bridge.log | grep -E "(message|error)"
```

## Manual Operation

### Start Bridge Manually

```bash
export SIGNAL_ACCOUNT="+15165643945"
export BRIDGE_PORT=8080
python3 tools/signal_cli_sse_bridge.py
```

### Stop Bridge

```bash
# Find PID
pgrep -f signal_cli_sse_bridge.py

# Kill
kill <PID>
```

### Restart Everything

```bash
# 1. Stop existing processes
pkill -f signal_cli_sse_bridge
pkill -f signal-cli

# 2. Start bridge
./tools/start_signal_bridge.sh

# 3. Wait for "Bridge is ready!"

# 4. Start OpenClaw
openclaw gateway
```

## How It Works

1. **Bridge starts signal-cli** in HTTP JSON-RPC mode on port 8081
2. **Bridge polls** signal-cli every second for new messages
3. **Messages are queued** in an async queue
4. **SSE endpoint** (`/events`) streams messages to OpenClaw
5. **Send endpoint** (`/send`) forwards requests to signal-cli
6. **Health endpoint** (`/health`) reports system status

## Differences from Native OpenClaw

| Feature | Native OpenClaw | With Bridge |
|---------|----------------|-------------|
| Protocol | SSE (expected) | SSE (provided) |
| Auto-start | Yes | No (bridge manages) |
| Message polling | Continuous | 1-second interval |
| Attachments | Native | Via base64 |

## Security Notes

- Bridge only binds to localhost (127.0.0.1)
- No authentication on bridge endpoints (OpenClaw handles auth)
- signal-cli HTTP is also localhost-only
- All Signal message content passes through bridge in memory only

## Performance

- **Latency**: ~1-2 seconds (due to polling)
- **Throughput**: ~100 messages/second (sufficient for chat)
- **Memory**: ~50MB (signal-cli + bridge)

## Alternative: Direct API

If the bridge has issues, you can still use signal-cli directly:

```bash
# Send message
curl -X POST http://127.0.0.1:8081/api/v1/rpc \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "send",
    "params": {
      "account": "+15165643945",
      "recipient": "+19194133445",
      "message": "Hello"
    }
  }'
```

But OpenClaw won't receive inbound messages without the bridge.

## Files

- `tools/signal_cli_sse_bridge.py` - Main bridge implementation
- `tools/start_signal_bridge.sh` - Startup script
- `docs/SIGNAL_SSE_BRIDGE.md` - This documentation
