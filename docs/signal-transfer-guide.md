# Signal Device Data Transfer Guide

> **Status:** Device Linked Locally ✅
> **Account:** +15165643945
> **Next:** Transfer to Railway Container

---

## Overview

The Signal device has been successfully linked locally. The signal-cli data (containing the device registration and keys) is now stored at:

```
~/.local/share/signal-cli/data/
```

This data needs to be transferred to the Railway container at `/data/.signal`.

---

## Transfer Methods

### Method 1: Railway CLI Upload (Recommended)

**Step 1: Install Railway CLI (if not installed)**

```bash
npm install -g @railway/cli
```

**Step 2: Authenticate**

```bash
railway login
```

**Step 3: Link to your project**

```bash
railway link
# Select your project from the list
```

**Step 4: Upload the data file**

The data has been packaged at `/tmp/signal-data.tar.gz`.

```bash
# Copy the file to a location for upload
cp /tmp/signal-data.tar.gz ~/signal-data.tar.gz

# Use Railway to copy into the container
railway cp ~/signal-data.tar.gz /tmp/signal-data.tar.gz
```

**Note:** If `railway cp` is not available in your CLI version, use Method 2.

---

### Method 2: Railway Dashboard + Shell

**Step 1: Get the data file**

The data archive is ready at: `/tmp/signal-data.tar.gz`

**Step 2: Upload via dashboard**

1. Go to [railway.app](https://railway.app)
2. Select your project
3. Click on your service
4. Go to the "Shell" tab
5. Use the upload button or drag-and-drop to upload `signal-data.tar.gz` to `/tmp/`

**Step 3: Extract in container**

In the Railway shell:

```bash
cd /app/scripts
./signal_import.sh
```

---

### Method 3: Base64 Encoding (No File Upload)

If file upload is not available, encode the data as base64:

**On your local machine:**

```bash
base64 /tmp/signal-data.tar.gz | pbcopy
# (pbcopy copies to clipboard on macOS)
# On Linux: base64 /tmp/signal-data.tar.gz | xclip -selection clipboard
```

**In Railway container shell:**

```bash
# Paste the base64 string into a file
echo "PASTE_BASE64_HERE" | base64 -d > /tmp/signal-data.tar.gz

# Extract
cd /app/scripts
./signal_import.sh
```

---

### Method 4: S3/Cloud Storage (Alternative)

**Upload to temporary storage:**

```bash
# Using a temporary file sharing service
curl -F "file=@/tmp/signal-data.tar.gz" https://file.io
# Returns a URL like: https://file.io/xxxxx
```

**In Railway container:**

```bash
curl -o /tmp/signal-data.tar.gz https://file.io/xxxxx
cd /app/scripts
./signal_import.sh
```

---

## Verification

After transferring the data, verify the setup:

```bash
# Check account registration
signal-cli listAccounts

# Should show: Number: +15165643945

# Test message receive
signal-cli receive

# Test sending (optional)
signal-cli send -m "Test from OpenClaw" +19194133445
```

---

## Troubleshooting

### Permission Errors

```bash
# Fix ownership
chown -R 1000:1000 /data/.signal

# Fix permissions
chmod -R 755 /data/.signal
```

### Data Not Found

```bash
# Check if data exists
ls -la /data/.signal/

# Should show directories like:
# - accounts/
# - avatars/
# - databases/
```

### Registration Lost

If the container says the account is not registered after transfer:

1. The data may not have extracted properly
2. Check logs: `signal-cli listAccounts --verbose`
3. Try re-linking locally and transferring again

---

## Security Note

The signal-data.tar.gz file contains sensitive cryptographic keys for your Signal account. After successful transfer:

```bash
# Delete local archive
rm /tmp/signal-data.tar.gz

# Delete from container after import
rm /tmp/signal-data.tar.gz
```

---

## Quick Reference

| File | Location | Purpose |
|------|----------|---------|
| Data archive | `/tmp/signal-data.tar.gz` | Packaged signal-cli data |
| Import script | `/app/scripts/signal_import.sh` | Extracts data in container |
| Target directory | `/data/.signal` | Where data should live |

---

## Next Steps

After transferring the data:

1. ✅ Restart the OpenClaw service (if needed)
2. ✅ Test incoming messages
3. ✅ Test outgoing messages
4. ✅ Verify pairing policy works

See `docs/signal-integration.md` for full verification steps.
