# OpenClaw/Moltbot Architecture

**Deployment**: Railway Pro
**Domain**: `kublai.kurult.ai`
**Channel**: Signal
**Owner**: Kurultai LLC
**Last Updated**: 2026-01-31

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
│  (Browser)   │  kublai.kurult.ai  │  │  │ Volume  │                  │  │
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
| Custom Domain | `kublai.kurult.ai` |

#### 2. signal-cli-native (Sidecar)

| Property | Value |
|----------|-------|
| Purpose | Signal protocol bridge |
| Internal URL | `http://signal-cli-native.railway.internal:8080` |
| Visibility | Internal only (no public access) |

---

## DNS Configuration

### Domain: kublai.kurult.ai

| Record Type | Name | Value | TTL |
|-------------|------|-------|-----|
| CNAME | `kublai` | `xod4zi0r.up.railway.app` | 600 |

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

1. Access Control UI: `https://kublai.kurult.ai/`
2. Navigate to Channels > Signal
3. Click "Link Device" to generate QR code
4. On phone: Signal > Settings > Linked Devices > Link New Device
5. Scan QR code

---

## Access URLs

### Control UI (Web Dashboard)

| Type | URL |
|------|-----|
| Base URL | `https://kublai.kurult.ai/` |
| Tokenized URL | `https://kublai.kurult.ai/?token=<GATEWAY_TOKEN>` |
| Chat | `https://kublai.kurult.ai/chat` |
| Channels | `https://kublai.kurult.ai/channels` |
| Sessions | `https://kublai.kurult.ai/sessions` |
| Settings | `https://kublai.kurult.ai/settings` |
| Skills | `https://kublai.kurult.ai/skills` |

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
2. Add: `kublai.kurult.ai`
3. Copy CNAME value
4. Add DNS record at GoDaddy:
   - Type: CNAME
   - Name: `kublai`
   - Value: `<railway-cname>.up.railway.app`
5. Wait for verification (5-15 minutes)

### 4. Link Signal Account

1. Access: `https://kublai.kurult.ai/setup`
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

## OpenClaw Configuration (openclaw.json)

In addition to `moltbot.json`, OpenClaw uses a separate configuration file for model providers and authentication profiles.

### Location

`/data/.clawdbot/openclaw.json` (on Railway volume) or `~/.openclaw/openclaw.json` locally

This configuration is typically managed through the Control UI at Settings > OpenClaw.

### Model Provider Configuration

**CRITICAL**: When configuring custom model providers (including overriding built-in providers like Anthropic), the `models` array is **REQUIRED**. Without it, the provider configuration is invalid and the LLM will not be called.

#### Working Provider Configuration Example

```json
{
  "auth": {
    "profiles": {
      "anthropic:default": {
        "mode": "api_key"
      }
    }
  },
  "models": {
    "providers": {
      "anthropic": {
        "api": "anthropic-messages",
        "apiKey": "${ANTHROPIC_API_KEY}",
        "baseUrl": "${ANTHROPIC_BASE_URL}",
        "models": [
          {
            "id": "claude-sonnet-4-20250514",
            "name": "Claude Sonnet 4",
            "reasoning": false,
            "input": ["text"],
            "cost": {
              "input": 0,
              "output": 0,
              "cacheRead": 0,
              "cacheWrite": 0
            }
          }
        ]
      }
    }
  }
}
```

#### Required Provider Fields

| Field | Required | Description |
|-------|----------|-------------|
| `api` | Yes | Protocol type: `anthropic-messages`, `openai-completions`, etc. |
| `apiKey` | Yes | API key using env var syntax `${VARIABLE_NAME}` |
| `baseUrl` | Yes* | API endpoint URL (*required for custom endpoints) |
| `models` | **Yes** | Array of available models - **MUST have at least one entry** |

#### Model Entry Fields

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Model identifier (e.g., `claude-sonnet-4-20250514`) |
| `name` | Yes | Display name (e.g., `Claude Sonnet 4`) |
| `reasoning` | No | Whether model supports reasoning traces |
| `input` | No | Supported input types array: `["text"]`, `["text", "image"]` |
| `cost` | No | Token cost configuration (set to 0 for flat-rate/proxy APIs) |

#### Using a Proxy API (Z.AI, LiteLLM, etc.)

When using an API proxy that wraps Anthropic's API:

```bash
# Environment Variables (Railway)
ANTHROPIC_API_KEY=your-proxy-api-key
ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic
```

The `baseUrl` must point to your proxy endpoint while keeping the `api` type as `anthropic-messages`.

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

### LLM Not Being Called (Empty Responses)

**Symptoms:**
- Chatbot returns empty assistant responses
- Agent runs complete in <100ms with 0 tokens used
- No errors in logs but LLM is clearly not invoked

**Root Cause:** The `models.providers` configuration is missing the required `models` array.

**Diagnosis:**
1. Access Control UI > Settings > OpenClaw > Raw JSON
2. Check if `models.providers.anthropic` (or your provider) has a `models` array
3. If `models` is missing or empty, this is the issue

**Fix via Control UI:**
1. Settings > OpenClaw > Form view
2. Navigate to Models > Providers > anthropic (or your provider)
3. Scroll to "Models" section (shows "0 items" if broken)
4. Click "+ Add" to add a model entry
5. Fill in required fields:
   - **Id**: `claude-sonnet-4-20250514` (or your model)
   - **Name**: `Claude Sonnet 4` (display name)
6. Click Save
7. Click Apply to restart with new config

**Fix via Raw JSON:**
Add the `models` array to your provider config:
```json
"models": {
  "providers": {
    "anthropic": {
      "api": "anthropic-messages",
      "apiKey": "${ANTHROPIC_API_KEY}",
      "baseUrl": "${ANTHROPIC_BASE_URL}",
      "models": [
        {
          "id": "claude-sonnet-4-20250514",
          "name": "Claude Sonnet 4"
        }
      ]
    }
  }
}
```

**Important:** The `models` array is REQUIRED for custom provider configurations, even when using built-in provider types like "anthropic".

### Config Won't Save ("Error: invalid config")

**Symptoms:**
- Raw JSON editor shows "valid" badge but save fails
- Form view changes don't persist
- Multiple save attempts all fail

**Common Causes:**
1. Missing required `models` array in provider config
2. Invalid JSON syntax (extra commas, missing quotes)
3. Unknown configuration keys

**Fix:**
1. Check the browser console (F12) for detailed validation errors
2. Verify provider config has all required fields (see Model Provider Configuration section)
3. Use Form view to add missing fields rather than manual JSON editing

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
