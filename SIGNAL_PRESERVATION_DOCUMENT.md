# Signal Integration Preservation Document

**Purpose:** Complete configuration reference for replicating the working Signal integration after a full environment wipe.

**Last Updated:** February 6, 2026
**Signal Account:** +15165643945
**Status:** Working configuration - pre-linked device data embedded

---

## Executive Summary

The Signal integration consists of two Railway services:

1. **signal-cli-daemon** - Runs signal-cli-native container with pre-linked device data
2. **signal-proxy** - Caddy-based API proxy with authentication and route translation

Both services proxy to an external signal-cli-rest-api instance (not hosted on Railway).

---

## Service 1: signal-cli-daemon

### Dockerfile

**Location:** `/signal-cli-daemon/Dockerfile`

```dockerfile
FROM registry.gitlab.com/packaging/signal-cli/signal-cli-native:latest

# Create non-root user for security
RUN addgroup -g 1000 signaluser && \
    adduser -D -u 1000 -G signaluser signaluser

# Railway provides PORT as environment variable
ENV PORT=8080

# Set config directory for signal-cli
ENV SIGNAL_CLI_CONFIG=/home/signaluser/.local/share/signal-cli

# Create config directory with proper ownership
RUN mkdir -p /home/signaluser/.local/share/signal-cli && \
    chown -R signaluser:signaluser /home/signaluser

# Switch to non-root user
USER signaluser:signaluser

# Health check - verify daemon is responsive
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD signal-cli --config /home/signaluser/.local/share/signal-cli listAccounts > /dev/null 2>&1 || exit 1

# Start signal-cli daemon with explicit config directory
ENTRYPOINT ["signal-cli", "--config", "/home/signaluser/.local/share/signal-cli"]
CMD ["daemon", "--http", "0.0.0.0:8080"]
```

### Railway Configuration

**railway.json:**

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE",
    "dockerfilePath": "Dockerfile"
  },
  "deploy": {
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

### Critical Details

- **Base Image:** `registry.gitlab.com/packaging/signal-cli/signal-cli-native:latest`
- **User:** Non-root user `signaluser` (UID 1000)
- **Port:** 8080 (provided by Railway via `PORT` env var)
- **Health Check:** Uses `signal-cli listAccounts` command every 30s
- **Config Directory:** `/home/signaluser/.local/share/signal-cli`

---

## Service 2: signal-proxy

### Dockerfile

**Location:** `/signal-proxy/Dockerfile`

```dockerfile
FROM caddy:2-alpine

# Copy Caddy configuration
COPY Caddyfile /etc/caddy/Caddyfile

# Expose the proxy port
EXPOSE 8080

# Run Caddy
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile"]
```

### Caddyfile (Complete)

**Location:** `/signal-proxy/Caddyfile`

```caddyfile
:8080 {
    # API Key Authentication
    # Require X-API-Key header matching the configured key
    @unauthorized {
        not header X-API-Key {$SIGNAL_API_KEY}
    }

    handle @unauthorized {
        header Content-Type application/json
        respond `{"error":"Unauthorized","message":"Valid X-API-Key header required"}` 401
    }

    # Health check endpoint (public, no auth required)
    handle /health {
        header Content-Type application/json
        respond `{"status":"healthy","service":"signal-api-proxy"}` 200
    }

    # Health check endpoint
    # Moltbot calls: /api/v1/check
    # signal-cli-rest-api provides: /v1/about (not /v1/health which doesn't exist)
    handle /api/v1/check {
        rewrite * /v1/about
        reverse_proxy https://signal-cli-rest-api-production-010a.up.railway.app {
            header_up Host {upstream_hostport}
            header_up X-Forwarded-Host {host}
        }
    }

    # Events/receive endpoint (supports SSE streaming)
    # Moltbot calls: /api/v1/events?account=+15165643945
    # signal-cli-rest-api provides: /v1/receive/+15165643945
    handle /api/v1/events {
        rewrite * /v1/receive/{$SIGNAL_ACCOUNT_NUMBER}
        reverse_proxy https://signal-cli-rest-api-production-010a.up.railway.app {
            header_up Host {upstream_hostport}
            header_up X-Forwarded-Host {host}
            flush_interval -1
            transport http {
                read_timeout 0
            }
        }
    }

    # Send message endpoint
    # Moltbot calls: /api/v1/send
    # signal-cli-rest-api provides: /v2/send
    handle /api/v1/send {
        rewrite * /v2/send
        reverse_proxy https://signal-cli-rest-api-production-010a.up.railway.app {
            header_up Host {upstream_hostport}
            header_up X-Forwarded-Host {host}
        }
    }

    # Pass through any other v1 requests
    handle /v1/* {
        reverse_proxy https://signal-cli-rest-api-production-010a.up.railway.app {
            header_up Host {upstream_hostport}
            header_up X-Forwarded-Host {host}
        }
    }

    # Pass through any other v2 requests
    handle /v2/* {
        reverse_proxy https://signal-cli-rest-api-production-010a.up.railway.app {
            header_up Host {upstream_hostport}
            header_up X-Forwarded-Host {host}
        }
    }

    # RPC endpoint stub - signal-cli-rest-api doesn't have RPC
    # Return a JSON stub response for Moltbot compatibility
    handle /api/v1/rpc {
        header Content-Type application/json
        respond `{"jsonrpc":"2.0","result":null,"id":null}` 200
    }

    # Catch-all for /api/v1/* - rewrite to /v1/* and proxy
    # This handles any Moltbot API calls not explicitly mapped above
    handle /api/v1/* {
        uri strip_prefix /api
        reverse_proxy https://signal-cli-rest-api-production-010a.up.railway.app {
            header_up Host {upstream_hostport}
            header_up X-Forwarded-Host {host}
        }
    }

    # Default handler - return JSON for API compatibility
    handle {
        header Content-Type application/json
        respond `{"status":"ok","service":"signal-api-proxy"}` 200
    }

    log {
        output stdout
        format console
        level INFO
    }
}
```

### Route Mapping Table

| Moltbot Calls | Rewrites To | Upstream |
|--------------|-------------|----------|
| `/health` | (none) | Local response (public) |
| `/api/v1/check` | `/v1/about` | signal-cli-rest-api |
| `/api/v1/events` | `/v1/receive/{SIGNAL_ACCOUNT_NUMBER}` | signal-cli-rest-api |
| `/api/v1/send` | `/v2/send` | signal-cli-rest-api |
| `/api/v1/rpc` | (none) | Local stub response |
| `/v1/*` | (passthrough) | signal-cli-rest-api |
| `/v2/*` | (passthrough) | signal-cli-rest-api |

### External Signal API

**Upstream URL:** `https://signal-cli-rest-api-production-010a.up.railway.app`

This is an external signal-cli-rest-api instance that the proxy forwards requests to.

---

## Environment Variables

### Required for signal-proxy

| Variable | Description | Example | Generation |
|----------|-------------|---------|------------|
| `SIGNAL_API_KEY` | API authentication key | `35847dc636a2...` | `openssl rand -hex 32` |
| `SIGNAL_ACCOUNT_NUMBER` | Signal phone number (E.164) | `+15165643945` | Your Signal number |
| `PORT` | Port for Caddy to listen on | `8080` | Set by Railway |

### Optional

| Variable | Description | Example |
|----------|-------------|---------|
| `SIGNAL_LINK_TOKEN` | Bypass token for QR linking (Authentik) | `openssl rand -hex 32` |

---

## Railway Deployment Configuration

### Service Setup

1. **signal-cli-daemon**
   - Builder: Dockerfile
   - Health Check: Built-in (signal-cli listAccounts)
   - No public URL needed (internal only)

2. **signal-proxy**
   - Builder: Dockerfile
   - Public URL: Generated by Railway
   - Environment variables: SIGNAL_API_KEY, SIGNAL_ACCOUNT_NUMBER

### Service Linkage

Currently, the proxy connects to an **external** signal-cli-rest-api instance:
- `https://signal-cli-rest-api-production-010a.up.railway.app`

If you want to proxy to your own signal-cli-daemon service, change the Caddyfile upstream:

```caddyfile
# Replace all instances of:
reverse_proxy https://signal-cli-rest-api-production-010a.up.railway.app

# With Railway internal service name:
reverse_proxy signal-cli-daemon:8080
```

---

## Security Configuration

### Access Control Policies

| Policy | Setting | Description |
|--------|---------|-------------|
| DM Policy | `pairing` | Requires pairing code for new contacts |
| Group Policy | `allowlist` | Only authorized numbers can add to groups |
| Allow From | `+15165643945, +19194133445` | Whitelisted phone numbers |
| Group Allow From | `+19194133445` | Restricted group membership |

### API Authentication Flow

1. Client makes request to signal-proxy
2. Caddy checks for `X-API-Key` header
3. If missing/invalid: returns 401 Unauthorized
4. If valid: proxies to upstream signal-cli-rest-api
5. Returns response to client

**Example curl:**

```bash
curl -H "X-API-Key: $SIGNAL_API_KEY" \
     https://your-signal-proxy.railway.app/api/v1/check
```

---

## QR Code Linking Flow

The Signal device can be linked via QR code using the `tslink` endpoint:

1. Generate a link token: `openssl rand -hex 32`
2. Set `SIGNAL_LINK_TOKEN` environment variable
3. This endpoint bypasses Authentik authentication
4. Access: `/setup/api/signal-link?token={SIGNAL_LINK_TOKEN}`
5. Displays QR code for linking Signal app

**Note:** The current implementation uses pre-linked device data embedded in the container image, so QR linking is only needed for:
- Initial setup
- Re-linking after device unlink
- Adding additional devices

---

## Verification Steps

After deployment, verify the integration:

### 1. Health Check (Public)

```bash
curl https://your-signal-proxy.railway.app/health
# Expected: {"status":"healthy","service":"signal-api-proxy"}
```

### 2. API Authentication Test

```bash
# Should fail (401)
curl https://your-signal-proxy.railway.app/api/v1/check

# Should succeed (200)
curl -H "X-API-Key: $SIGNAL_API_KEY" \
     https://your-signal-proxy.railway.app/api/v1/check
```

### 3. SSE Streaming Test

```bash
curl -H "X-API-Key: $SIGNAL_API_KEY" \
     https://your-signal-proxy.railway.app/api/v1/events
```

---

## Signal Data Archive

### Pre-linked Device Data

**Location:** `/.signal-data/signal-data.tar.gz`

This archive contains:
- Signal cryptographic keys
- Device registration data
- Contact information (allowlist)
- Group memberships

**Security:** Directory permissions must be 700 (owner-only access)

**Checksum:**

```bash
sha256sum .signal-data/signal-data.tar.gz
```

Store the checksum in `SIGNAL_DATA_CHECKSUM` environment variable for verification.

---

## Troubleshooting

### Common Issues

1. **401 Unauthorized on API calls**
   - Check `SIGNAL_API_KEY` environment variable
   - Verify `X-API-Key` header is being sent
   - Check Caddy logs for authentication errors

2. **SSE connection drops**
   - Verify `flush_interval -1` in Caddyfile
   - Check `read_timeout 0` in transport config
   - Ensure upstream supports SSE

3. **Signal daemon not starting**
   - Check health check logs
   - Verify `signal-cli listAccounts` works
   - Ensure config directory permissions are correct

4. **Railway DNS issues with Signal servers**
   - The main Dockerfile includes tinyproxy for DNS bypass
   - Ensure textsecure-service.whispersystems.org resolves

---

## Incident Response

### Signal Account Compromise

1. Immediately revoke device link via Signal app
2. Rotate `SIGNAL_API_KEY` in Railway dashboard
3. Regenerate Signal data archive with new keys
4. Update `SIGNAL_DATA_CHECKSUM` environment variable
5. Redeploy services
6. Notify users of potential message exposure

### Service Recovery

1. Check Railway service logs
2. Verify health checks are passing
3. Test API authentication
4. Verify upstream signal-cli-rest-api is accessible
5. Redeploy if needed

---

## Files to Preserve

Before wiping, ensure you have copies of:

1. `/signal-cli-daemon/Dockerfile`
2. `/signal-cli-daemon/railway.json`
3. `/signal-proxy/Dockerfile`
4. `/signal-proxy/Caddyfile`
5. `/.signal-data/signal-data.tar.gz` (Signal device data)
6. `/.signal-data/signal-data.tar.gz.sha256` (Checksum)
7. `/.env.example` (Environment variable reference)

---

## Post-Wipe Rebuild Checklist

- [ ] Create Railway project
- [ ] Deploy signal-cli-daemon service
- [ ] Deploy signal-proxy service
- [ ] Set SIGNAL_API_KEY environment variable
- [ ] Set SIGNAL_ACCOUNT_NUMBER environment variable
- [ ] Copy .signal-data/signal-data.tar.gz to new repo
- [ ] Verify health endpoint returns 200
- [ ] Verify API authentication works (401 without key, 200 with)
- [ ] Test SSE streaming on /api/v1/events
- [ ] Test message sending via /api/v1/send

---

**Document Version:** 1.0
**Last Updated:** February 6, 2026
**Maintained By:** Signal Preservation Specialist
