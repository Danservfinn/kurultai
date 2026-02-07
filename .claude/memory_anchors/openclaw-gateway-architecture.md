---
title: OpenClaw Gateway Architecture
link: openclaw-gateway-architecture
type: memory_anchors
tags: [openclaw, gateway, websocket, messaging, architecture]
ontological_relations:
  - relates_to: [[kurultai-project-overview]]
  - relates_to: [[openclaw-websocket-protocol]]
uuid: 550e8400-e29b-41d4-a716-446655440002
created_at: 2026-02-07T12:00:00Z
updated_at: 2026-02-07T12:00:00Z
---

# OpenClaw Gateway Architecture

## Overview

OpenClaw is the WebSocket-based gateway that enables agent-to-agent messaging in the Kurultai system. It provides bidirectional streaming, authentication, and session management for multi-agent workflows.

## Deployment

### Docker Configuration
```dockerfile
FROM node:22-bookworm-slim
RUN npm install -g openclaw@latest
CMD ["node", "dist/index.js", "gateway", "--bind", "lan", "--port", "18789", "--allow-unconfigured"]
```

### Configuration Location
- **Path**: `/data/.openclaw/openclaw.json5`
- **Format**: JSON5 with environment variable substitution (`${VAR_NAME}`)
- **Environment**: `OPENCLAW_GATEWAY_TOKEN` required for operator authentication

## Port Binding

- **Internal Port**: 18789 (binds to `lan` for internal Docker network access)
- **Health Check**: `curl -f http://localhost:18789/health`
- **WebChat UI**: Available at `http://localhost:18789/`

## WebSocket Protocol

### Connection Handshake
1. Server sends `connect.challenge` with `nonce`
2. Client sends `connect` request with authentication

### Authentication
```javascript
{
  type: "req",
  id: "<uuid>",
  method: "connect",
  params: {
    role: "operator",
    scopes: ["operator.admin", "operator.approvals", "operator.pairing"],
    token: "${OPENCLAW_GATEWAY_TOKEN}"
  }
}
```

### Chat Request
```javascript
{
  type: "req",
  id: "<uuid>",
  method: "chat.send",
  params: {
    sessionKey: "main",
    message: "Your message here",
    deliver: false,
    idempotencyKey: "<uuid>"
  }
}
```

### Streaming Response
Events with `event: "agent"` contain streaming chunks:
- `payload.stream: "assistant"` - Text chunks in `payload.data.delta`
- `payload.stream: "lifecycle"` - Lifecycle events (end: `payload.data.phase: "end"`)

## Key Features

1. **Bidirectional Streaming**: Real-time agent responses
2. **Idempotency Keys**: Prevent duplicate message processing
3. **Session Management**: Multiple concurrent sessions per agent
4. **Built-in WebChat**: Vite+Lit SPA for control and testing

## Integration Points

- **Caddyfile**: Reverse proxy routes from `:9000` → `:18789`
- **Agent Connectors**: Python async clients for each agent
- **Kublai**: Primary orchestrator connects as operator

## Performance

- **Latency**: ~1.5s average for Kimi K2.5 responses
- **Concurrency**: Supports multiple simultaneous agent sessions
- **Reliability**: Automatic reconnection on WebSocket drop
