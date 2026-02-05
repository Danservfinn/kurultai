# Signal Integration for OpenClaw/Moltbot

> **Account:** +15165643945
> **Status:** Phases 1-2 Complete, Phases 3-4 Pending
> **Deployment:** kublai.kurult.ai (Railway)

---

## Quick Start

```bash
# 1. Access Railway container shell
railway shell

# 2. Run setup script
cd /app/scripts && ./signal_setup.sh

# 3. Scan QR code with Signal app

# 4. Verify installation
./signal_verify.sh
```

---

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Signal App    │────▶│  Signal Servers │◀────│  OpenClaw Bot   │
│   (Your Phone)  │◀────│                 │────▶│  +15165643945   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
                              ┌─────────────────────────┘
                              ▼
                       ┌─────────────────┐
                       │   signal-cli    │
                       │   v0.13.12      │
                       │   (Java)        │
                       └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │  /data/.signal  │
                       │  (persistent)   │
                       └─────────────────┘
```

---

## Implementation Status

| Phase | Task | Status |
|-------|------|--------|
| **Phase 1** | Install signal-cli | ✅ Complete |
| | Configure Signal data directory | ✅ Complete |
| **Phase 2** | Update moltbot.json | ✅ Complete |
| | Add environment variables | ✅ Complete |
| **Phase 3** | Deploy updated container | ✅ Complete |
| | Generate QR code + Link device | ⏳ Pending |
| **Phase 4** | Test send/receive | ⏳ Pending |
| | Verify pairing policy | ⏳ Pending |

---

## Files Modified

### Dockerfile
- Added OpenJDK 17 runtime
- Installed signal-cli v0.13.12
- Created `/data/.signal` directory
- Added `SIGNAL_DATA_DIR` and `SIGNAL_ACCOUNT` environment variables

### moltbot.json
- Added `cliPath`: `/usr/local/bin/signal-cli`
- Added `startupTimeoutMs`: `120000`

---

## Helper Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `signal_setup.sh` | Generate QR code for device linking | `./signal_setup.sh` |
| `signal_verify.sh` | Verify Signal integration | `./signal_verify.sh` |
| `signal_diagnose.sh` | Troubleshoot issues | `./signal_diagnose.sh` |

---

## Device Linking Process

### Step 1: Access Container

```bash
# Using Railway CLI
railway login
railway link
railway shell

# Or use Railway Dashboard
# 1. Go to railway.app
# 2. Select your project
# 3. Click "Shell" button
```

### Step 2: Run Setup Script

```bash
cd /app/scripts
./signal_setup.sh
```

This will:
1. Verify signal-cli installation
2. Check data directory permissions
3. Generate QR code for linking

### Step 3: Scan QR Code

1. Open Signal app on your phone
2. Go to **Settings** → **Linked Devices**
3. Tap **Link New Device**
4. Scan the QR code displayed in the terminal

### Step 4: Verify

```bash
./signal_verify.sh
```

---

## Configuration Reference

### Environment Variables

```bash
SIGNAL_DATA_DIR=/data/.signal      # signal-cli data storage
SIGNAL_ACCOUNT=+15165643945        # Default account number
```

### moltbot.json Signal Settings

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
      "groupAllowFrom": ["+19194133445"],
      "historyLimit": 50,
      "textChunkLimit": 4000,
      "ignoreStories": true
    }
  }
}
```

---

## Troubleshooting

### signal-cli: command not found

```bash
# Check if installed
which signal-cli
ls -la /usr/local/bin/signal-cli
ls -la /opt/signal-cli-*/

# Check PATH
echo $PATH
```

### Permission Denied

```bash
# Fix data directory permissions
chown -R 1000:1000 /data/.signal
chmod -R 755 /data/.signal
```

### QR Code Not Displaying

```bash
# Try direct command
signal-cli link -n "OpenClaw"

# Or with explicit output
signal-cli link -n "OpenClaw" > /tmp/qr.txt
cat /tmp/qr.txt
```

### Already Registered Error

```bash
# Check registration status
signal-cli listAccounts

# Unregister if needed
signal-cli unregister

# Then re-run setup
./signal_setup.sh
```

---

## Manual Commands

### Registration

```bash
# Generate QR code for linking
signal-cli link -n "OpenClaw"

# Check registration status
signal-cli listAccounts

# Unregister
signal-cli unregister
```

### Messaging

```bash
# Send message
signal-cli send -m "Hello" +19194133445

# Receive messages
signal-cli receive

# List contacts
signal-cli listContacts
```

### Daemon

```bash
# Start daemon (for OpenClaw integration)
signal-cli daemon

# Start with systemd (if available)
systemctl --user start signal-cli
```

---

## Security Notes

- Signal data is stored in `/data/.signal` (persistent volume)
- Container runs as non-root user (UID 1000)
- Pairing policy requires approval for new contacts
- Allowlist restricts DM access to known numbers

---

## Resources

- [OpenClaw Signal Docs](https://docs.openclaw.ai/channels/signal)
- [signal-cli GitHub](https://github.com/AsamK/signal-cli)
- [signal-cli Releases](https://github.com/AsamK/signal-cli/releases)
- [Railway Documentation](https://docs.railway.app)

---

## Support

For issues with:
- **signal-cli**: Check [GitHub Issues](https://github.com/AsamK/signal-cli/issues)
- **OpenClaw**: Refer to [official docs](https://docs.openclaw.ai)
- **Railway deployment**: Check Railway dashboard logs
