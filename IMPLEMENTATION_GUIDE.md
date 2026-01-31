# OpenClaw + Signal on Railway: One-Shot Implementation Guide

**Purpose**: Step-by-step guide for an AI agent to deploy OpenClaw (Moltbot) on Railway Pro with Signal integration, exactly replicating the production deployment at `bot.kurult.ai`.

**Prerequisites**: Railway Pro account, Anthropic API key, Signal account on phone, custom domain (optional)

---

## Quick Reference

```
Template URL:    https://railway.app/template/codetitlan/moltbot-railway-template
Production URL:  https://bot.kurult.ai/
Control UI:      https://<your-domain>/?token=<GATEWAY_TOKEN>
Signal Sidecar:  http://signal-cli-native.railway.internal:8080
```

> **Note**: Verify the template URL is current at https://railway.app before deploying.

---

## Phase 1: Deploy the Template (5 minutes)

### Step 1.1: Create Railway Project

**Option A: One-Click Deploy (Recommended)**
```
Navigate to: https://railway.app/template/codetitlan/moltbot-railway-template
Click "Deploy Now"
Authenticate with GitHub if prompted
Wait for initial deployment to complete
```

**Option B: Railway CLI**
```bash
railway login
railway init --template codetitlan/moltbot-railway-template
railway up
```

### Step 1.2: Create Persistent Volume

**CRITICAL**: The `/data` volume must exist before the service can start.

1. Railway Dashboard > Your Service > Settings > Volumes
2. Click "Create Volume" or "+ New Volume"
3. Mount Path: `/data`
4. Click "Create"
5. Wait for volume to provision (1-2 minutes)

Without this volume, the service will crash with "ENOENT: no such file or directory".

### Step 1.3: Generate Security Tokens

Run these commands locally to generate secure tokens:

```bash
# Generate SETUP_PASSWORD (32 chars)
echo "SETUP_PASSWORD=$(openssl rand -base64 24)"

# Generate GATEWAY_TOKEN (64 chars)
echo "OPENCLAW_GATEWAY_TOKEN=$(openssl rand -base64 48)"
```

**Save these values securely** - you'll need them in the next step.

### Step 1.4: Set Environment Variables

In Railway Dashboard > Your Service > Variables tab, add:

```bash
# REQUIRED - Authentication
SETUP_PASSWORD=<paste-your-32-char-password>
OPENCLAW_GATEWAY_TOKEN=<paste-your-64-char-token>

# REQUIRED - AI Provider
ANTHROPIC_API_KEY=sk-ant-<your-key>

# REQUIRED - Storage Paths
CLAWDBOT_STATE_DIR=/data/.clawdbot
CLAWDBOT_WORKSPACE_DIR=/data/workspace
```

Click "Deploy" or wait for auto-redeploy.

### Step 1.5: Verify Deployment Success

Wait 2-5 minutes for deployment, then verify:

1. Service shows "Active" status (green indicator)
2. No crash loops in Railway logs
3. Check logs for: `Gateway started on port`

**If service crashes repeatedly:**
- Check Railway logs for missing environment variables
- Verify volume is mounted at `/data`
- Ensure all REQUIRED env vars are set

**Do NOT proceed to Phase 2 until the service is stable.**

---

## Phase 2: Configure Custom Domain (10 minutes)

### Step 2.1: Add Domain in Railway

1. Railway Dashboard > Your Service > Settings > Networking
2. Scroll to "Public Networking"
3. Click "+ Custom Domain"
4. Enter your domain: `bot.yourdomain.com`
5. **Copy the CNAME value** shown (e.g., `abc123.up.railway.app`)

### Step 2.2: Configure DNS

At your DNS provider (GoDaddy, Cloudflare, etc.):

| Type | Name | Value | TTL |
|------|------|-------|-----|
| CNAME | `bot` | `<railway-cname>.up.railway.app` | 600 |

### Step 2.3: Wait for Verification

- Railway will show a green checkmark when verified
- DNS propagation: 5-15 minutes (up to 48 hours)
- SSL certificate auto-provisions via Let's Encrypt

### Step 2.4: Verify Access

```
https://bot.yourdomain.com/
```

Should show OpenClaw login page or redirect to setup.

### Step 2.5: Wait for DNS (BLOCKING)

**Do NOT proceed to Phase 3 until DNS is fully propagated.**

Verify with:
```bash
curl -I https://bot.yourdomain.com/ 2>&1 | head -5
```

Expected: `HTTP/2 200` or redirect to `/setup`

If you get SSL errors or DNS failures:
- Wait 5 minutes and retry
- Check DNS propagation at: https://dnschecker.org
- Maximum wait: 48 hours (rare)

---

## Phase 3: Link Signal Account (10 minutes)

### Step 3.1: Access Setup Wizard

```
https://bot.yourdomain.com/setup
```

Enter your `SETUP_PASSWORD` when prompted.

### Step 3.2: Complete Initial Setup

1. Select AI provider (Anthropic recommended)
2. Skip channel configuration for now (we'll do it manually)
3. Complete the wizard

### Step 3.3: Navigate to Signal Channel

```
https://bot.yourdomain.com/channels
```

Or: Click "Channels" in the sidebar > Select "Signal"

### Step 3.4: Link Signal Device

1. Click "Link Device" or "Connect"
2. A QR code will appear on screen
3. On your phone:
   - Open Signal
   - Settings > Linked Devices > Link New Device
   - Scan the QR code
4. Approve the linking on your phone
5. Wait for confirmation in OpenClaw UI

**Important**: The phone number will be displayed after linking. Note it for the next step.

**Warning**: Consider using a **separate Signal number** dedicated to OpenClaw rather than your personal number. This provides better security isolation and prevents personal messages from being processed by the agent.

> **QR Code Expiration**: Signal QR codes expire after approximately 60 seconds. If the QR code expires before scanning, click "Refresh" or re-initiate the linking process. Do not delay once the QR code is displayed.

---

## Phase 4: Configure moltbot.json (5 minutes)

### Step 4.1: Create Configuration File

The configuration lives at `/data/.clawdbot/moltbot.json` on the Railway volume.

**Option A: Via Control UI Terminal**
1. Go to Settings > Terminal (or Chat interface)
2. Use the agent to write the file

**Option B: Via Railway CLI**
```bash
railway shell
cat > /data/.clawdbot/moltbot.json << 'EOF'
<paste configuration below>
EOF
```

### Step 4.2: Configuration Template

Copy this configuration, replacing placeholders:

```json
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
      "account": "+1XXXXXXXXXX",
      "httpUrl": "http://signal-cli-native.railway.internal:8080",
      "autoStart": false,
      "dmPolicy": "pairing",
      "groupPolicy": "allowlist",
      "configWrites": false,
      "allowFrom": ["+1XXXXXXXXXX", "+1YYYYYYYYYY"],
      "groupAllowFrom": ["+1YYYYYYYYYY"],
      "historyLimit": 50,
      "textChunkLimit": 4000,
      "ignoreStories": true
    }
  },
  "session": {
    "dmScope": "per-peer",
    "reset": {
      "mode": "daily"
    }
  },
  "logging": {
    "level": "info"
  }
}
```

### Step 4.3: Configuration Placeholders

Replace these values:

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `+1XXXXXXXXXX` in `account` | Your linked Signal phone number | `+15165643945` |
| `+1XXXXXXXXXX` in `allowFrom` | Your phone number (owner) | `+15165643945` |
| `+1YYYYYYYYYY` in `allowFrom` | Other authorized users | `+19194133445` |
| `+1YYYYYYYYYY` in `groupAllowFrom` | Users who can trigger in groups | `+19194133445` |

### Step 4.4: Configuration Options Explained

| Setting | Value | Purpose |
|---------|-------|---------|
| `gateway.mode` | `local` | Gateway behind Railway's proxy |
| `gateway.trustedProxies` | `["loopback", "uniquelocal"]` | Trust Railway's internal network |
| `channels.signal.httpUrl` | Internal Railway URL | Signal CLI sidecar connection |
| `channels.signal.dmPolicy` | `pairing` | How DMs are handled (pairing/allowlist/open/disabled) |
| `channels.signal.groupPolicy` | `allowlist` | Group message handling policy |
| `channels.signal.allowFrom` | Phone/UUID array | Allowlisted users for DMs (phone: `+1...`, group UUID: `group.xxx`) |
| `channels.signal.groupAllowFrom` | Phone array | Users who can trigger in groups |
| `session.dmScope` | `per-peer` | Separate sessions per user (per-peer/per-channel) |
| `session.reset.mode` | `daily` | Reset sessions daily at 4:00 AM UTC |

### DM Policy Modes

| Mode | Behavior |
|------|----------|
| `pairing` | First-time senders get pairing request; approved users added to allowlist automatically |
| `allowlist` | Only users in `allowFrom` can interact; others silently ignored |
| `open` | Anyone can message (use with caution) |
| `disabled` | DMs disabled entirely |

### Pairing Workflow (dmPolicy: "pairing")

When a new user sends their first message:
1. OpenClaw holds the message and sends a pairing request to the owner
2. Owner receives: "User +1XXXXXXXXXX wants to pair with Moltbot. Reply YES to approve."
3. Owner replies "YES" to approve (or ignores to deny)
4. If approved, user's phone number is automatically added to `allowFrom`
5. Original message is then processed

---

## Phase 5: Verify Deployment (5 minutes)

### Step 5.1: Check Health Status

```
https://bot.yourdomain.com/
```

Look for:
- "Health: OK" indicator (green)
- Gateway status showing "running"

### Step 5.2: Check Signal Channel

Navigate to Channels > Signal:
- Status should show "Connected" or "Linked"
- Phone number should be displayed

### Step 5.3: Test Message Flow

1. From an allowlisted phone, send a message to your linked Signal number
2. Watch the Chat interface in Control UI
3. Verify the message appears and gets a response

### Step 5.4: Check Logs (if issues)

Railway Dashboard > Service > Logs

Look for:
- `Gateway started on port 18789`
- `Signal channel connected`
- Any error messages

### Step 5.5: Run Security Audit (Optional)

Before going live, run the security audit command via Control UI terminal or Railway shell:

```bash
openclaw security audit --deep
```

This verifies:
- Token entropy meets minimum requirements
- No secrets exposed in configuration
- Proper file permissions on credential storage
- TLS configuration is secure

> **Note**: The `openclaw` CLI may not be available in all container images. If the command is not found, verify security manually using the Security Checklist below.

---

## Complete Environment Variables Reference

### Required

```bash
SETUP_PASSWORD=<32-char-random>                    # Setup wizard auth
OPENCLAW_GATEWAY_TOKEN=<64-char-random>            # Gateway API auth
ANTHROPIC_API_KEY=sk-ant-...                       # AI provider
CLAWDBOT_STATE_DIR=/data/.clawdbot                 # Config storage
CLAWDBOT_WORKSPACE_DIR=/data/workspace             # Agent workspace
```

### Optional

```bash
# Alternative AI providers
OPENAI_API_KEY=sk-...
OPENROUTER_API_KEY=sk-or-...

# Additional channels (if needed later)
TELEGRAM_BOT_TOKEN=123456:ABC...
DISCORD_BOT_TOKEN=...
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...

# Voice (optional)
ELEVENLABS_API_KEY=...

# Search (optional)
BRAVE_SEARCH_API_KEY=...
```

---

## Complete moltbot.json Reference

> **Model IDs**: The model identifiers below (e.g., `claude-sonnet-4-20250514`) may change over time. Check the [Anthropic API docs](https://docs.anthropic.com/claude/docs/models-overview) for current model names.

```json
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
      "workspace": "/data/workspace",
      "model": {
        "primary": "anthropic/claude-sonnet-4-20250514",
        "fallbacks": ["openai/gpt-4o"]
      }
    }
  },
  "channels": {
    "signal": {
      "enabled": true,
      "account": "+15165643945",
      "httpUrl": "http://signal-cli-native.railway.internal:8080",
      "autoStart": false,
      "dmPolicy": "pairing",
      "groupPolicy": "allowlist",
      "configWrites": false,
      "allowFrom": ["+15165643945", "+19194133445"],
      "groupAllowFrom": ["+19194133445"],
      "historyLimit": 50,
      "textChunkLimit": 4000,
      "ignoreStories": true
    }
  },
  "session": {
    "dmScope": "per-peer",
    "reset": {
      "mode": "daily"
    }
  },
  "logging": {
    "level": "info"
  },
  "skills": {
    "load": {
      "watch": true
    },
    "entries": {}
  }
}
```

---

## Troubleshooting Playbook

### Problem: Gateway Won't Start

**Symptoms**: Service crashes, restarts repeatedly

**Check**:
```bash
railway logs | grep -i error
```

**Common Causes**:
1. Missing `SETUP_PASSWORD` or `OPENCLAW_GATEWAY_TOKEN`
2. Invalid JSON in moltbot.json
3. Volume not mounted at `/data`

**Fix**:
- Verify all required env vars are set
- Validate JSON syntax
- Check Railway volume configuration

---

### Problem: Signal Not Connecting

**Symptoms**: Channel shows "Disconnected" or "Error"

**Check**:
1. Is signal-cli-native sidecar running?
2. Is `httpUrl` correct?
3. Is the linked device still valid?

**Fix**:

Verify `httpUrl` in moltbot.json matches:
```json
"httpUrl": "http://signal-cli-native.railway.internal:8080"
```

If device expired, re-link via Channels > Signal > Link Device.

---

### Problem: Messages Not Received

**Symptoms**: Send message from phone, nothing appears in Control UI

**Check**:
1. Is sender in `allowFrom` list?
2. Is the phone number format correct (with `+` prefix)?
3. Check logs for "blocked" messages

**Fix**:

Add the phone number to `allowFrom` array:
```json
"allowFrom": ["+15165643945", "+1NEW_NUMBER_HERE"]
```

---

### Problem: Domain Not Working

**Symptoms**: Custom domain shows error or doesn't resolve

**Check**:
1. DNS propagation: `dig bot.yourdomain.com`
2. Railway domain verification status
3. SSL certificate status

**Fix**:
- Wait for DNS propagation (up to 48 hours)
- Verify CNAME points to Railway value
- Delete and re-add domain in Railway if stuck

---

### Problem: "Gateway Token Mismatch"

**Symptoms**: Control UI shows token error

**Check**:
1. Is `OPENCLAW_GATEWAY_TOKEN` set in Railway?
2. Does moltbot.json reference the correct env var?

**Fix**:

Ensure auth block references the env var (not a hardcoded token):
```json
"auth": {
  "mode": "token",
  "token": "${OPENCLAW_GATEWAY_TOKEN}"
}
```

---

## Architecture Summary

```
┌─────────────────────────────────────────────────────────────┐
│                     Railway Pro                              │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              moltbot-railway-template                   │ │
│  │                                                         │ │
│  │  ┌─────────────┐         ┌─────────────────────────┐   │ │
│  │  │   Gateway   │ ◄─────► │       Claude Agent      │   │ │
│  │  │   :8080     │         │   (Anthropic API)       │   │ │
│  │  └──────┬──────┘         └─────────────────────────┘   │ │
│  │         │                                               │ │
│  │         ▼                                               │ │
│  │  ┌─────────────┐                                        │ │
│  │  │   /data     │  Persistent Volume                     │ │
│  │  │   volume    │  - moltbot.json                        │ │
│  │  │             │  - credentials/                        │ │
│  │  │             │  - workspace/                          │ │
│  │  └─────────────┘                                        │ │
│  └────────────────────────────────────────────────────────┘ │
│                          │                                   │
│                          │ Internal Network                  │
│                          ▼                                   │
│  ┌────────────────────────────────────────────────────────┐ │
│  │           signal-cli-native (Sidecar)                   │ │
│  │           Internal: :8080                               │ │
│  │           - Signal Protocol Bridge                      │ │
│  │           - E2EE Message Handling                       │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           │ HTTPS (Let's Encrypt)
                           ▼
                  ┌─────────────────┐
                  │   Custom Domain  │
                  │ bot.kurult.ai   │
                  └─────────────────┘
                           │
            ┌──────────────┼──────────────┐
            │              │              │
            ▼              ▼              ▼
      ┌──────────┐  ┌──────────┐  ┌──────────┐
      │ Control  │  │  Signal  │  │  Signal  │
      │    UI    │  │  Phone   │  │  Phone   │
      │ (Browser)│  │ (Owner)  │  │ (Users)  │
      └──────────┘  └──────────┘  └──────────┘
```

---

## Security Checklist

Before going live, verify:

- [ ] `SETUP_PASSWORD` is 32+ characters (generated randomly)
- [ ] `OPENCLAW_GATEWAY_TOKEN` is 64+ characters (generated randomly)
- [ ] Tokens are NOT committed to any repository
- [ ] `allowFrom` only includes known phone numbers
- [ ] Custom domain uses HTTPS (automatic via Railway)
- [ ] API keys are stored only in Railway environment variables
- [ ] Signal linked device appears in phone's "Linked Devices" list
- [ ] Separate Signal number used (not personal number)
- [ ] Security audit passes: `openclaw security audit --deep`

---

## Post-Deployment Maintenance

### Updating OpenClaw

1. Railway Dashboard > Service > Settings > Source
2. If "New version available" appears, click "Update"
3. **Warning**: This restarts the service and interrupts active sessions

### Rotating Credentials

| Credential | Frequency | Procedure |
|------------|-----------|-----------|
| `SETUP_PASSWORD` | After each admin access | Update in Railway, redeploy |
| `OPENCLAW_GATEWAY_TOKEN` | Monthly | Update in Railway, redeploy |
| `ANTHROPIC_API_KEY` | Quarterly | Regenerate at Anthropic, update Railway |

### Backup Procedure

```bash
# Via Railway shell
# First, ensure backup directory exists
mkdir -p /data/backups

# Create timestamped backup
tar -czf /data/backups/moltbot-$(date +%Y%m%d).tar.gz \
  /data/.clawdbot \
  /data/workspace
```

---

## Agent Execution Checklist

For AI agents following this guide, here's the execution checklist:

```
□ Phase 1: Deploy Template
  □ Deploy from https://railway.app/template/codetitlan/moltbot-railway-template
  □ Create /data volume in Railway (Settings > Volumes)
  □ Generate SETUP_PASSWORD (openssl rand -base64 24)
  □ Generate OPENCLAW_GATEWAY_TOKEN (openssl rand -base64 48)
  □ Set required environment variables in Railway
  □ Wait for deployment to complete
  □ VERIFY: Service shows "Active" (no crash loops)

□ Phase 2: Configure Domain
  □ Add custom domain in Railway Settings
  □ Copy CNAME value
  □ Add DNS record at provider
  □ Wait for verification (green checkmark)
  □ VERIFY: curl https://bot.yourdomain.com/ returns 200
  □ DO NOT proceed until DNS verified

□ Phase 3: Link Signal
  □ Access /setup with SETUP_PASSWORD
  □ Complete setup wizard
  □ Navigate to Channels > Signal
  □ Generate QR code (expires in ~60 seconds!)
  □ Scan immediately with phone's Signal app
  □ Note the linked phone number

□ Phase 4: Configure moltbot.json
  □ Copy template configuration
  □ Replace phone number placeholders
  □ Set allowFrom with authorized numbers
  □ Write to /data/.clawdbot/moltbot.json
  □ Restart service or wait for hot reload

□ Phase 5: Verify
  □ Check Health: OK in Control UI
  □ Verify Signal shows "Connected"
  □ Send test message from allowlisted phone
  □ Confirm response received
  □ Run security audit (if CLI available): openclaw security audit --deep
  □ Complete Security Checklist (manual verification)
  □ Document final configuration
```

---

## Reference Files

| File | Purpose | Location |
|------|---------|----------|
| ARCHITECTURE.md | System design documentation | Same directory as this guide |
| moltbot.json | Runtime configuration | `/data/.clawdbot/moltbot.json` (on Railway) |
| env.example | Environment variable template | Same directory as this guide |

---

*Last Updated: 2026-01-30*
*Deployment: bot.kurult.ai*
*Owner: Kurultai LLC*
