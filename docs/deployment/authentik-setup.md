# Authentik Biometric Authentication Setup Guide

This guide walks through deploying Authentik for biometric authentication (Face ID, Touch ID, WebAuthn) to protect the Kublai Control UI.

## Overview

**Architecture:**
```
User → Caddy Proxy (authentik-proxy) → Authentik Server (auth check)
                                      ↓
                                    PostgreSQL
                                      ↓
Steppe Visualization ← (if auth'd) ← Caddy Proxy
```

**Services Deployed:**
- `authentik-db`: PostgreSQL 15 for data persistence
- `authentik-server`: Identity provider (port 9000)
- `authentik-worker`: Background task processor
- `authentik-proxy`: Caddy reverse proxy with forward auth

## Prerequisites

1. **Railway CLI** installed and logged in:
   ```bash
   npm install -g @railway/cli
   railway login
   ```

2. **OpenSSL** for generating secrets:
   ```bash
   # macOS
   brew install openssl
   # Ubuntu/Debian
   sudo apt-get install openssl
   ```

3. **Domain DNS** configured:
   - `kublai.kurult.ai` must point to Railway
   - Verify with: `dig kublai.kurult.ai`

## Quick Start

### Option 1: Automated Deployment (Recommended)

```bash
# Run the deployment script
./scripts/deploy-authentik.sh
```

This will:
1. Check prerequisites
2. Generate secure secrets
3. Set Railway environment variables
4. Deploy all services in order
5. Run the bootstrap configuration
6. Verify deployment health

### Option 2: Manual Deployment

#### Step 1: Generate Secrets

```bash
export AUTHENTIK_SECRET_KEY=$(openssl rand -hex 32)
export AUTHENTIK_BOOTSTRAP_PASSWORD=$(openssl rand -base64 24)
export AUTHENTIK_POSTGRESQL__PASSWORD=$(openssl rand -base64 24)
export SIGNAL_LINK_TOKEN=$(openssl rand -hex 32)

echo "Save these credentials:"
echo "AUTHENTIK_BOOTSTRAP_PASSWORD: $AUTHENTIK_BOOTSTRAP_PASSWORD"
```

#### Step 2: Set Environment Variables

```bash
railway login
railway link

# Core settings
railway variables set AUTHENTIK_SECRET_KEY="$AUTHENTIK_SECRET_KEY"
railway variables set AUTHENTIK_BOOTSTRAP_PASSWORD="$AUTHENTIK_BOOTSTRAP_PASSWORD"
railway variables set AUTHENTIK_EXTERNAL_HOST="https://kublai.kurult.ai"

# Database settings
railway variables set AUTHENTIK_POSTGRESQL__HOST="authentik-db.railway.internal"
railway variables set AUTHENTIK_POSTGRESQL__NAME="authentik"
railway variables set AUTHENTIK_POSTGRESQL__USER="postgres"
railway variables set AUTHENTIK_POSTGRESQL__PASSWORD="$AUTHENTIK_POSTGRESQL__PASSWORD"

# Proxy settings
railway variables set SIGNAL_LINK_TOKEN="$SIGNAL_LINK_TOKEN"
```

#### Step 3: Deploy Services

```bash
# Deploy in order
echo "Deploying database..."
railway up --service authentik-db

sleep 30

echo "Deploying Authentik server..."
railway up --service authentik-server

sleep 60

echo "Deploying worker and proxy..."
railway up --service authentik-worker
railway up --service authentik-proxy
```

#### Step 4: Configure Authentik

```bash
# Run bootstrap script
python authentik-proxy/bootstrap_authentik.py
```

## Post-Deployment Configuration

### 1. Access Admin Interface

1. Navigate to: `https://kublai.kurult.ai/if/admin/`
2. Login with:
   - Username: `akadmin`
   - Password: Your `AUTHENTIK_BOOTSTRAP_PASSWORD`

### 2. Change Admin Password

1. Go to **Directory → Users**
2. Click on `akadmin`
3. Click **Reset Password**
4. Set a new secure password

### 3. Configure WebAuthn

1. Go to **Flows & Stages → Stages**
2. Click **Create Stage**
3. Select **WebAuthn Authenticator Stage**
4. Configure:
   - **Name**: `Kublai WebAuthn`
   - **Friendly Name**: `Kublai Control Panel`
   - **User Verification**: `Preferred` (allows Face ID/Touch ID)
   - **Authenticator Attachment**: `Platform` (for built-in authenticators)
5. Click **Create**

### 4. Update Authentication Flow

1. Go to **Flows & Stages → Flows**
2. Find `Kublai WebAuthn Authentication`
3. Click **Stage Bindings**
4. Add the WebAuthn stage:
   - Click **Bind Stage**
   - Select your WebAuthn stage
   - Set **Order**: `20`
   - Enable **Evaluate when flow is planned**
   - Click **Create**

### 5. Test Authentication

1. Open an incognito window
2. Navigate to `https://kublai.kurult.ai`
3. You should be redirected to Authentik login
4. Login with `akadmin` and password
5. You'll be prompted to register a WebAuthn device:
   - On Mac: Use Touch ID
   - On iPhone: Use Face ID
   - On other devices: Use hardware security key or platform authenticator
6. After registration, you'll be redirected to Kublai Control UI

## Backup Configuration

### Automated Backups (Recommended)

1. Set up Cloudflare R2 or AWS S3:
   ```bash
   railway variables set R2_BUCKET="authentik-backups"
   railway variables set R2_ENDPOINT="https://your-account-id.r2.cloudflarestorage.com"
   railway variables set R2_ACCESS_KEY_ID="your-access-key"
   railway variables set R2_SECRET_ACCESS_KEY="your-secret-key"
   ```

2. Configure Railway cron to run backups:
   ```bash
   # Run daily at 2 AM UTC
   railway cron create "0 2 * * *" --command "./scripts/backup-authentik-db.sh"
   ```

### Manual Backup

```bash
# Run backup script
./scripts/backup-authentik-db.sh
```

### Restore from Backup

```bash
# Download backup from R2/S3
aws s3 cp s3://authentik-backups/authentik/db/authentik_backup_YYYYMMDD_HHMMSS.sql.gz ./

# Restore to database
gunzip < authentik_backup_YYYYMMDD_HHMMSS.sql.gz | \
  psql -h authentik-db.railway.internal -U postgres -d authentik
```

## Security Best Practices

### 1. Secret Management

- **Never commit** `.env` files to version control
- Rotate secrets every 90 days:
  ```bash
  # Generate new secret key
  openssl rand -hex 32
  # Update in Railway and restart services
  ```
- Store `AUTHENTIK_SECRET_KEY` in a secure vault

### 2. Session Configuration

1. Go to **System → Settings**
2. Configure:
   - **Session Duration**: `24h` (recommended)
   - **Remember Me Duration**: `30d`
   - **Logout on password change**: Enabled

### 3. Rate Limiting

1. Go to **Customization → Policies**
2. Create a **Reputation Policy**:
   - Name: `Login Rate Limit`
   - Check IP: Enabled
   - Threshold: `5` failed attempts
   - Action: `Block` for `5` minutes

### 4. Audit Logging

1. Go to **System → Settings**
2. Enable **Event Retention**: `90 days`
3. Export logs regularly:
   ```bash
   # Via API
   curl -H "Authorization: Bearer $AUTHENTIK_API_TOKEN" \
        https://kublai.kurult.ai/api/v3/events/
   ```

## Troubleshooting

### Services Not Starting

```bash
# Check service logs
railway logs --service authentik-server

# Verify health endpoints
curl http://authentik-server.railway.internal:9000/-/health/ready/
```

### Database Connection Issues

```bash
# Test database connection
railway connect authentik-db
pg_isready -U postgres -d authentik
```

### WebAuthn Not Working

1. Check browser console for errors
2. Verify `AUTHENTIK_EXTERNAL_HOST` uses HTTPS
3. Ensure domain is accessible (not localhost)
4. Check WebAuthn stage configuration:
   - User Verification must be `preferred` or `required`
   - Cannot use `discouraged` for Face ID/Touch ID

### Caddy Proxy Errors

```bash
# Check Caddy logs
railway logs --service authentik-proxy

# Verify Caddyfile syntax
docker run --rm -v $(pwd)/authentik-proxy/Caddyfile:/etc/caddy/Caddyfile \
  caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile
```

### Bootstrap Script Fails

1. Wait for Authentik to be fully ready:
   ```bash
   sleep 60
   python authentik-proxy/bootstrap_authentik.py
   ```

2. Check Authentik API health:
   ```bash
   curl http://authentik-server.railway.internal:9000/api/v3/
   ```

## Monitoring

### Health Checks

| Service | Endpoint | Expected |
|---------|----------|----------|
| authentik-server | `/-/health/ready/` | HTTP 200 |
| authentik-proxy | `/health` | HTTP 200 |
| authentik-db | `pg_isready` | `accepting connections` |

### Metrics

Authentik exposes Prometheus metrics at:
```
http://authentik-server.railway.internal:9300/metrics
```

### Alerts

Set up alerts for:
- Service downtime
- Failed authentication attempts > 10/minute
- Database backup failures
- Certificate expiration

## Updates

### Update Authentik Version

1. Edit `authentik-server/Dockerfile` and `authentik-worker/Dockerfile`:
   ```dockerfile
   FROM ghcr.io/goauthentik/server:2025.11  # New version
   ```

2. Redeploy:
   ```bash
   railway up --service authentik-server
   railway up --service authentik-worker
   ```

3. Run migrations (if any):
   ```bash
   docker compose run --rm authentik-server migrate
   ```

## Uninstall

To remove Authentik from Railway:

```bash
# Stop and remove services
railway down --service authentik-proxy
railway down --service authentik-worker
railway down --service authentik-server
railway down --service authentik-db

# Remove volumes (WARNING: This deletes all data!)
railway volume delete authentik-db-data
```

## Support

- **Authentik Docs**: https://docs.goauthentik.io/
- **WebAuthn Guide**: https://webauthn.guide/
- **Railway Docs**: https://docs.railway.app/

## Files Reference

| File | Purpose |
|------|---------|
| `railway.yml` | Railway service definitions |
| `authentik-proxy/Caddyfile` | Reverse proxy configuration |
| `authentik-proxy/bootstrap_authentik.py` | Initial setup script |
| `authentik-proxy/config/*.yaml` | Authentik blueprints |
| `scripts/deploy-authentik.sh` | Deployment automation |
| `scripts/backup-authentik-db.sh` | Database backup script |
| `.env.example` | Environment variable template |
