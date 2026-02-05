# Signal Integration

Account: +15165643945
Status: Pre-linked device data embedded in image
Updated: February 5, 2026

## Deployment Status

**Repository:** https://github.com/Danservfinn/moltbot-railway-template
**Commit:** f1ecd67 Feat: add Signal integration with pre-linked device data +15165643945

### Changes Made

1. **Dockerfile** - Added Signal data extraction during container build
   - Extracts `.signal-data/signal-data.tar.gz` to `/data/.signal`
   - Sets proper ownership (UID 1000:1000) and permissions (700)
   - No hardcoded secrets in the image

2. **signal-cli-daemon/Dockerfile** - Secure daemon configuration
   - Runs as non-root user (signaluser, UID 1000)
   - Health check for monitoring
   - Proper config directory permissions

3. **signal-proxy/Caddyfile** - API authentication
   - API key authentication required for all endpoints
   - Public health check endpoint
   - Environment-based configuration

4. **.signal-data/signal-data.tar.gz**
   - Pre-linked Signal device data
   - Generated from local signal-cli v0.13.12
   - Device linked via QR code on Feb 5, 2026
   - SHA256 checksum verification

## Security Configuration

### Required Environment Variables

| Variable | Description | Example | Security Level |
|----------|-------------|---------|----------------|
| `SIGNAL_ACCOUNT_NUMBER` | Signal phone number (E.164) | `+15165643945` | **Required** |
| `SIGNAL_API_KEY` | API authentication key | `35847dc636a2...` | **Required** |
| `SIGNAL_DATA_CHECKSUM` | SHA256 checksum of data archive | `4d3bf23c7d51...` | Recommended |

### File Permissions

Signal data directory must have 700 permissions (owner-only access):

```bash
chmod -R 700 /data/.signal
```

This ensures only the container user (UID 1000) can access Signal cryptographic keys.

### API Authentication

All API requests must include the `X-API-Key` header:

```bash
curl -H "X-API-Key: $SIGNAL_API_KEY" \
     https://your-service.railway.app/api/v1/check
```

Requests without a valid API key will receive a 401 Unauthorized response.

### Access Control Policies

| Policy | Setting | Description |
|--------|---------|-------------|
| DM Policy | `pairing` | Requires pairing code for new contacts |
| Group Policy | `allowlist` | Only authorized numbers can add to groups |
| Allow From | `+15165643945, +19194133445` | Whitelisted phone numbers |
| Group Allow From | `+19194133445` | Restricted group membership |

## Deployment

### Building with Checksum Verification

```bash
# Generate checksum
sha256sum .signal-data/signal-data.tar.gz > .signal-data/signal-data.tar.gz.sha256

# Build with checksum verification
docker build \
  --build-arg SIGNAL_DATA_CHECKSUM=$(cat .signal-data/signal-data.tar.gz.sha256 | cut -d' ' -f1) \
  --build-arg SIGNAL_ACCOUNT=$SIGNAL_ACCOUNT_NUMBER \
  -t moltbot:latest .
```

### Railway Configuration

Set these environment variables in the Railway dashboard:

1. **SIGNAL_ACCOUNT_NUMBER** - Your Signal phone number (e.g., `+15165643945`)
2. **SIGNAL_API_KEY** - Generate with: `openssl rand -hex 32`
3. **SIGNAL_DATA_CHECKSUM** - SHA256 of the Signal data archive

### Verification Steps

1. Check container permissions:
   ```bash
   docker exec moltbot stat -c "%a %U %G" /data/.signal
   # Expected: 700 clawdbot clawdbot
   ```

2. Verify non-root daemon:
   ```bash
   docker exec signal-cli-daemon id
   # Expected: uid=1000(signaluser) gid=1000(signaluser)
   ```

3. Test API authentication:
   ```bash
   # Should fail (no API key)
   curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/api/v1/check
   # Expected: 401

   # Should succeed (with API key)
   curl -s -o /dev/null -w "%{http_code}" \
     -H "X-API-Key: $SIGNAL_API_KEY" \
     http://localhost:8080/api/v1/check
   # Expected: 200
   ```

## Configuration Summary

```javascript
channels: {
  signal: {
    enabled: true,
    account: process.env.SIGNAL_ACCOUNT_NUMBER,
    cliPath: "/usr/local/bin/signal-cli",
    autoStart: true,
    startupTimeoutMs: 120000,
    dmPolicy: "pairing",
    groupPolicy: "allowlist",
    allowFrom: ["+15165643945", "+19194133445"],
    groupAllowFrom: ["+19194133445"],
    historyLimit: 50,
    textChunkLimit: 4000,
    ignoreStories: true
  }
}
```

## DNS Configuration

The Dockerfile includes tinyproxy configuration to bypass Railway's DNS issues with Signal servers (textsecure-service.whispersystems.org).

## Security Checklist

- [ ] No hardcoded secrets in Docker images
- [ ] Signal data directory has 700 permissions
- [ ] signal-cli-daemon runs as non-root user
- [ ] API key authentication enabled on proxy
- [ ] Checksum verification configured
- [ ] Health checks enabled
- [ ] Environment variables set in Railway dashboard

## Incident Response

### Signal Account Compromise

1. Immediately revoke device link via Signal app
2. Rotate SIGNAL_API_KEY in Railway dashboard
3. Regenerate Signal data archive with new keys
4. Update SIGNAL_DATA_CHECKSUM environment variable
5. Redeploy services
6. Notify users of potential message exposure

### Key Rotation

1. Generate new Signal device link
2. Export new data archive
3. Update checksum: `sha256sum .signal-data/signal-data.tar.gz`
4. Set new SIGNAL_DATA_CHECKSUM in Railway
5. Deploy with new archive
6. Verify message delivery
