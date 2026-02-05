# Signal Device Linking Guide

> **Status:** Pending Deployment
> **Account:** +15165643945
> **Container:** kublai.kurult.ai

---

## Overview

After the Dockerfile changes deploy to Railway, you need to link the Signal device using a QR code.

## Prerequisites

- [ ] Phone with Signal app installed
- [ ] Access to Railway dashboard or CLI
- [ ] New deployment is live (check Railway dashboard)

---

## Phase 3: Device Linking

### Step 3.1: Verify Deployment

1. Check Railway dashboard for successful deployment
2. Verify container is running without errors
3. Check logs for any signal-cli related errors

### Step 3.2: Generate QR Code

**Option A: Using Railway CLI**

```bash
# Install Railway CLI if not already installed
npm install -g @railway/cli

# Login to Railway
railway login

# Connect to your project
railway link

# Open a shell in the running container
railway shell

# Generate QR code for linking
signal-cli link -n "OpenClaw"
```

**Option B: Using Railway Dashboard**

1. Go to [Railway Dashboard](https://railway.app)
2. Select your project
3. Click on the deployment
4. Go to the "Logs" tab
5. Click "Shell" or "Console" button
6. Run: `signal-cli link -n "OpenClaw"`

**Option C: Local signal-cli + Data Transfer**

If container access is limited:

```bash
# On local machine with Java installed
wget https://github.com/AsamK/signal-cli/releases/download/v0.13.12/signal-cli-0.13.12.tar.gz
tar -xzf signal-cli-0.13.12.tar.gz
./signal-cli-0.13.12/bin/signal-cli link -n "OpenClaw"

# After linking, copy the data directory to the container
# The data is stored in ~/.local/share/signal-cli/
```

### Step 3.3: Scan QR Code

1. Open Signal app on your phone
2. Go to Settings → Linked Devices
3. Tap "Link New Device"
4. Scan the QR code displayed in the terminal
5. Wait for confirmation

### Step 3.4: Verify Registration

```bash
# In the container shell
signal-cli listAccounts
```

You should see +15165643945 listed.

---

## Phase 4: Verification

### Test Incoming Messages

1. Send a message from your phone to +15165643945
2. Check OpenClaw logs for message receipt
3. Verify agent responds appropriately

### Test Outgoing Messages

1. Use OpenClaw to send a test message
2. Verify message received on your phone

### Test Pairing Policy

1. Have a new number send a message to +15165643945
2. Verify pairing code is generated
3. Approve pairing via OpenClaw
4. Verify conversation proceeds

---

## Troubleshooting

### signal-cli not found

```bash
which signal-cli
# Should return: /usr/local/bin/signal-cli

signal-cli --version
# Should show version 0.13.12
```

### Permission errors

```bash
# Check Signal data directory permissions
ls -la /data/.signal
# Should be owned by UID 1000

# Fix permissions if needed
chown -R 1000:1000 /data/.signal
```

### Linking fails

1. Ensure phone has internet connectivity
2. Try generating a new QR code
3. Check signal-cli logs for specific errors

### Container crashes on startup

1. Check Railway logs for Java/signal-cli errors
2. Verify SIGNAL_DATA_DIR environment variable is set
3. Ensure /data/.signal directory exists and is writable

---

## Environment Variables

The following are already configured in the Dockerfile:

| Variable | Value | Purpose |
|----------|-------|---------|
| `SIGNAL_DATA_DIR` | `/data/.signal` | signal-cli data storage |
| `SIGNAL_ACCOUNT` | `+15165643945` | Default Signal account |

---

## Configuration Reference

See `moltbot.json` for Signal channel configuration:

```json
{
  "channels": {
    "signal": {
      "enabled": true,
      "account": "+15165643945",
      "cliPath": "/usr/local/bin/signal-cli",
      "autoStart": true,
      "startupTimeoutMs": 120000,
      "dmPolicy": "pairing",
      "groupPolicy": "allowlist",
      "allowFrom": ["+15165643945", "+19194133445"],
      "groupAllowFrom": ["+19194133445"]
    }
  }
}
```

---

## Post-Setup Checklist

- [ ] signal-cli --version works in container
- [ ] Device linked (shows in Signal app Settings → Linked Devices)
- [ ] Test message sent and received successfully
- [ ] Pairing policy working for unknown contacts
- [ ] No persistent errors in Railway logs

---

## Support

- [OpenClaw Signal Docs](https://docs.openclaw.ai/channels/signal)
- [signal-cli GitHub](https://github.com/AsamK/signal-cli)
- [Railway Documentation](https://docs.railway.app)
