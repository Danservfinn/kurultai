# OpenClaw/Moltbot Architecture

**Deployment**: Railway Pro
**Domain**: `bot.kurult.ai`
**Channel**: Signal
**Owner**: Kurultai LLC
**Last Updated**: 2026-01-30

---

## Overview

This document describes the production deployment of OpenClaw (Moltbot) on Railway with Signal integration. Use this as a reference to replicate or restore the configuration.

```
                                    ┌─────────────────────────────────────┐
                                    │           Railway Pro               │
┌──────────────┐                    │  ┌───────────────────────────────┐  │
│              │                    │  │    moltbot-railway-template   │  │
│   Signal     │◄──────────────────►│  │                               │  │
│   (Phone)    │  Signal Protocol   │  │  ┌─────────┐    ┌──────────┐  │  │
│              │                    │  │  │ Gateway │◄───│  Agent   │  │  │
└──────────────┘                    │  │  │ :8080   │    │ (Claude) │  │  │
                                    │  │  └────┬────┘    └──────────┘  │  │
┌──────────────┐                    │  │       │                       │  │
│              │  HTTPS             │  │       ▼                       │  │
│  Control UI  │◄──────────────────►│  │  ┌─────────┐                  │  │
│  (Browser)   │  bot.kurult.ai     │  │  │ Volume  │                  │  │
│              │                    │  │  │ /data   │                  │  │
└──────────────┘                    │  │  └─────────┘                  │  │
                                    │  └───────────────────────────────┘  │
                                    │                                     │
                                    │  ┌───────────────────────────────┐  │
                                    │  │   signal-cli-native (sidecar) │  │
                                    │  │   Internal: :8080             │  │
                                    │  └───────────────────────────────┘  │
                                    └─────────────────────────────────────┘
```

---

## Railway Project Structure

### Project Details

| Property | Value |
|----------|-------|
| Project Name | `clever-blessing` |
| Environment | `production` |
| Template | `codetitlan/moltbot-railway-template` |
| Region | US East (default) |

### Services

#### 1. moltbot-railway-template (Main Service)

| Property | Value |
|----------|-------|
| Image | Built from template |
| Port (External) | 8080 |
| Port (Internal Gateway) | 18789 |
| Volume | `/data` (persistent) |
| Custom Domain | `bot.kurult.ai` |

#### 2. signal-cli-native (Sidecar)

| Property | Value |
|----------|-------|
| Purpose | Signal protocol bridge |
| Internal URL | `http://signal-cli-native.railway.internal:8080` |
| Visibility | Internal only (no public access) |

---

## DNS Configuration

### Domain: bot.kurult.ai

| Record Type | Name | Value | TTL |
|-------------|------|-------|-----|
| CNAME | `bot` | `xod4zi0r.up.railway.app` | 600 |

**DNS Provider**: GoDaddy
**SSL**: Auto-provisioned by Railway (Let's Encrypt)

---

## Environment Variables

### Required Variables (Railway Dashboard)

```bash
# Authentication (SECURITY-CRITICAL - generate unique values)
SETUP_PASSWORD=<32-char-random-password>
CLAWDBOT_GATEWAY_TOKEN=<64-char-random-token>
OPENCLAW_GATEWAY_TOKEN=<64-char-random-token>  # Alternative name

# AI Provider
ANTHROPIC_API_KEY=sk-ant-...

# Storage paths
CLAWDBOT_STATE_DIR=/data/.clawdbot
CLAWDBOT_WORKSPACE_DIR=/data/workspace
```

### Generate Secure Tokens

```bash
# SETUP_PASSWORD (32 chars, ~192 bits entropy)
openssl rand -base64 24

# GATEWAY_TOKEN (64 chars, ~384 bits entropy)
openssl rand -base64 48
```

### Optional Variables

```bash
# Additional AI providers
OPENAI_API_KEY=sk-...
OPENROUTER_API_KEY=sk-or-...

# Other channels (if adding later)
TELEGRAM_BOT_TOKEN=123456:ABC...
DISCORD_BOT_TOKEN=...
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
```

---

## Configuration File

### Location

`/data/.clawdbot/moltbot.json` (on Railway volume)

Also committed locally at: `/Users/kurultai/molt/moltbot.json`

### Current Configuration

```json5
{
  "gateway": {
    "mode": "local",
    "port": 18789,
    "trustedProxies": ["loopback", "uniquelocal"],
    "auth": {
      "mode": "token",
      "token": "${OPENCLAW_GATEWAY_TOKEN}"
    },
    "controlUi": {
      "enabled": true
    }
  },
  "agents": {
    "defaults": {
      "workspace": "/data/workspace"
    }
  },
  "channels": {
    "signal": {
      "enabled": true,
      "account": "+15165643945",
      "httpUrl": "http://signal-cli-native.railway.internal:8080",
      "autoStart": false,
      "dmPolicy": "pairing",
      "configWrites": false,
      "allowFrom": ["+15165643945", "+19194133445"],
      "groupAllowFrom": ["+19194133445"],
      "historyLimit": 50,
      "textChunkLimit": 4000,
      "ignoreStories": true
    }
  },
  "session": {
    "scope": "per-sender",
    "reset": {
      "mode": "daily"
    }
  },
  "logging": {
    "level": "info"
  }
}
```

### Configuration Explained

| Section | Setting | Purpose |
|---------|---------|---------|
| `gateway.mode` | `local` | Gateway runs behind Railway's proxy |
| `gateway.port` | `18789` | Internal gateway port |
| `gateway.auth.mode` | `token` | Token-based authentication |
| `gateway.controlUi.enabled` | `true` | Web UI at root URL |
| `agents.defaults.workspace` | `/data/workspace` | Persistent file storage |
| `channels.signal.account` | `+15165643945` | Linked Signal phone number |
| `channels.signal.httpUrl` | Internal Railway URL | Signal CLI sidecar |
| `channels.signal.allowFrom` | Phone numbers | Allowlisted users |
| `channels.signal.dmPolicy` | `pairing` | DM handling mode |
| `session.scope` | `per-sender` | Separate sessions per user |
| `session.reset.mode` | `daily` | Reset sessions daily |

---

## Signal Channel Setup

### Linked Account

| Property | Value |
|----------|-------|
| Phone Number | `+15165643945` |
| Protocol | Signal Protocol (E2EE) |
| Bridge | signal-cli-native sidecar |

### Allowlisted Users

| Phone Number | Role |
|--------------|------|
| `+15165643945` | Owner (self) |
| `+19194133445` | Authorized user |

### Linking New Device

1. Access Control UI: `https://bot.kurult.ai/`
2. Navigate to Channels > Signal
3. Click "Link Device" to generate QR code
4. On phone: Signal > Settings > Linked Devices > Link New Device
5. Scan QR code

---

## Access URLs

### Control UI (Web Dashboard)

| Type | URL |
|------|-----|
| Base URL | `https://bot.kurult.ai/` |
| Tokenized URL | `https://bot.kurult.ai/?token=<GATEWAY_TOKEN>` |
| Chat | `https://bot.kurult.ai/chat` |
| Channels | `https://bot.kurult.ai/channels` |
| Sessions | `https://bot.kurult.ai/sessions` |
| Settings | `https://bot.kurult.ai/settings` |
| Skills | `https://bot.kurult.ai/skills` |

### Railway Dashboard

| Resource | URL |
|----------|-----|
| Project | `https://railway.com/project/9a3e528b-28b5-44f1-b037-9bb0ad4f992b` |
| Service Settings | `https://railway.com/project/.../service/.../settings` |
| Logs | `https://railway.com/project/.../service/.../logs` |
| Variables | `https://railway.com/project/.../service/.../variables` |

### Legacy URLs (Still Functional)

| URL | Purpose |
|-----|---------|
| `https://moltbot-railway-template-production-75e7.up.railway.app/` | Original Railway domain |

---

## Volume Structure

```
/data/
├── .clawdbot/                    # State directory
│   ├── moltbot.json              # Main configuration
│   ├── credentials/              # Channel credentials
│   │   └── signal/               # Signal linked device data
│   └── sessions/                 # Session persistence
├── workspace/                    # Agent workspace
│   └── (user files)
└── backups/                      # Local backups (optional)
```

---

## Replication Steps

### 1. Deploy Template

```bash
# Via Railway CLI
railway init
railway link

# Or via browser
# Navigate to: https://railway.com/deploy/moltbot-railway-template
```

### 2. Set Environment Variables

In Railway Dashboard > Variables:

```bash
SETUP_PASSWORD=$(openssl rand -base64 24)
CLAWDBOT_GATEWAY_TOKEN=$(openssl rand -base64 48)
ANTHROPIC_API_KEY=sk-ant-your-key-here
CLAWDBOT_STATE_DIR=/data/.clawdbot
CLAWDBOT_WORKSPACE_DIR=/data/workspace
```

### 3. Configure Custom Domain

1. Railway > Service > Settings > Networking > Custom Domain
2. Add: `bot.kurult.ai`
3. Copy CNAME value
4. Add DNS record at GoDaddy:
   - Type: CNAME
   - Name: `bot`
   - Value: `<railway-cname>.up.railway.app`
5. Wait for verification (5-15 minutes)

### 4. Link Signal Account

1. Access: `https://bot.kurult.ai/setup`
2. Enter SETUP_PASSWORD
3. Complete setup wizard
4. Navigate to Channels > Signal
5. Link device via QR code

### 5. Configure moltbot.json

Copy configuration to `/data/.clawdbot/moltbot.json` or edit via Control UI.

### 6. Add Allowlisted Users

Update `channels.signal.allowFrom` array with authorized phone numbers.

---

## Backup and Recovery

### What to Backup

| Path | Contents | Priority |
|------|----------|----------|
| `/data/.clawdbot/moltbot.json` | Configuration | Critical |
| `/data/.clawdbot/credentials/` | Channel auth | Critical |
| `/data/workspace/` | User files | High |
| Environment variables | API keys, tokens | Critical |

### Backup Command

```bash
# SSH into Railway or run via Control UI terminal
tar -czf /data/backups/moltbot-$(date +%Y%m%d).tar.gz \
  /data/.clawdbot \
  /data/workspace
```

### Recovery

1. Deploy fresh template
2. Set same environment variables
3. Restore `/data` volume contents
4. Re-link Signal if credentials expired

---

## Troubleshooting

### Gateway Won't Start

```bash
# Check logs
railway logs

# Verify env vars
railway variables
```

### Signal Not Connecting

1. Verify signal-cli-native sidecar is running
2. Check `httpUrl` matches sidecar internal URL
3. Re-link device if session expired

### Messages Not Received

1. Verify sender phone in `allowFrom` list
2. Check logs for blocked messages
3. Ensure Signal linked device is still active

### Domain Not Working

1. Verify DNS CNAME record
2. Check Railway domain verification status
3. Wait for SSL certificate provisioning

---

## Security Checklist

- [ ] SETUP_PASSWORD is strong (32+ chars)
- [ ] GATEWAY_TOKEN is strong (64+ chars)
- [ ] Tokens not committed to git
- [ ] allowFrom restricts to known users
- [ ] HTTPS enforced (Railway default)
- [ ] API keys in environment variables only
- [ ] Regular credential rotation scheduled

---

## Updates

### Checking for Updates

1. Railway > Service > Settings > Source
2. Look for "New version of upstream repo available"
3. Click "Update" to pull latest

### Update Procedure

1. Note current working state
2. Export configuration backup
3. Apply update
4. Verify services restart correctly
5. Test Signal connectivity

**Warning**: Updates restart the container and interrupt active sessions.

---

## References

- [OpenClaw Documentation](https://docs.openclaw.ai/)
- [Railway Documentation](https://docs.railway.app/)
- [Signal CLI Documentation](https://github.com/AsamK/signal-cli)
- Local skill reference: `~/.claude/skills/molt/`
