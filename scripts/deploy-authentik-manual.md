# Authentik Manual Deployment Guide

This guide provides step-by-step instructions for deploying Authentik to Railway when CLI automation is limited.

## Prerequisites

- Railway CLI installed and authenticated
- Access to Railway dashboard: https://railway.com/project/26201f75-3375-46ce-98c7-9d1dde5f9569
- Domain `kublai.kurult.ai` configured

## Quick Start

Run the setup script to generate credentials and configure environment variables:

```bash
./scripts/deploy-authentik-simple.sh
```

This will:
1. Generate secure secrets
2. Set project-level environment variables
3. Set service-level environment variables
4. Output the manual deployment steps below

## Manual Deployment Steps

### Step 1: Verify/Create Services

Check that these services exist in your Railway project:

| Service | Purpose | Status |
|---------|---------|--------|
| Postgres-P5UQ | PostgreSQL database | Needs deployment |
| unique-manifestation | Authentik server | Needs deployment |
| powerful-growth | Authentik worker | Needs deployment |
| loyal-enchantment | Caddy proxy | Needs deployment |

If any are missing, create them via Railway dashboard:
1. Click "New" → "Database" → "PostgreSQL" for the database
2. Click "New" → "Empty Service" for the other services

### Step 2: Set Environment Variables

#### Project-Level Variables (Already Set)

These should already be configured at the project level:

```
AUTHENTIK_SECRET_KEY=b230c9e141acbdb429bd280d39d2f54a08a6b453829c94ca64bbd4d0ee1de153
AUTHENTIK_BOOTSTRAP_PASSWORD=5bAQmpdbqXgfwjV7P4JcSsK1t42+bAiF
AUTHENTIK_EXTERNAL_HOST=https://kublai.kurult.ai
SIGNAL_LINK_TOKEN=ec97a4567daf32eccb0cd381b070a1141ebbd6b7bfaf9f1ba279350e825b381a
AUTHENTIK_URL=http://authentik-server:9000
```

#### Service-Level Variables

For **unique-manifestation** (Authentik Server):
```
AUTHENTIK_SECRET_KEY=b230c9e141acbdb429bd280d39d2f54a08a6b453829c94ca64bbd4d0ee1de153
AUTHENTIK_BOOTSTRAP_PASSWORD=5bAQmpdbqXgfwjV7P4JcSsK1t42+bAiF
AUTHENTIK_EXTERNAL_HOST=https://kublai.kurult.ai
AUTHENTIK_POSTGRESQL__HOST=postgres-p5uq.railway.internal
AUTHENTIK_POSTGRESQL__NAME=railway
AUTHENTIK_POSTGRESQL__USER=postgres
AUTHENTIK_POSTGRESQL__PASSWORD=brJcintESOyGTKjVWVuJMWbzaznnPCEI
```

For **powerful-growth** (Authentik Worker):
```
AUTHENTIK_SECRET_KEY=b230c9e141acbdb429bd280d39d2f54a08a6b453829c94ca64bbd4d0ee1de153
AUTHENTIK_EXTERNAL_HOST=https://kublai.kurult.ai
AUTHENTIK_POSTGRESQL__HOST=postgres-p5uq.railway.internal
AUTHENTIK_POSTGRESQL__NAME=railway
AUTHENTIK_POSTGRESQL__USER=postgres
AUTHENTIK_POSTGRESQL__PASSWORD=brJcintESOyGTKjVWVuJMWbzaznnPCEI
```

For **loyal-enchantment** (Caddy Proxy):
```
SIGNAL_LINK_TOKEN=ec97a4567daf32eccb0cd381b070a1141ebbd6b7bfaf9f1ba279350e825b381a
AUTHENTIK_URL=http://authentik-server:9000
PORT=8080
```

### Step 3: Deploy Services

Deploy in this order:

1. **Postgres-P5UQ** (Database)
   - Go to service → Click "Deploy"
   - Wait for status: "Success"

2. **unique-manifestation** (Authentik Server)
   - Settings → Build → Builder: Dockerfile
   - Settings → Deploy → Healthcheck Path: `/-/health/ready/`
   - Click "Deploy"
   - Wait for status: "Success"

3. **powerful-growth** (Authentik Worker)
   - Settings → Build → Builder: Dockerfile
   - Click "Deploy"
   - Wait for status: "Success"

4. **loyal-enchantment** (Caddy Proxy)
   - Settings → Build → Builder: Dockerfile
   - Settings → Deploy → Healthcheck Path: `/health`
   - Click "Deploy"
   - Wait for status: "Success"

### Step 4: Configure Domain

1. Go to **loyal-enchantment** service
2. Click "Settings" → "Domains"
3. Add custom domain: `kublai.kurult.ai`
4. Wait for SSL certificate provisioning

### Step 5: Run Bootstrap Script

Once all services are healthy:

```bash
# Get Railway API token
railway token

# Run bootstrap script
python authentik-proxy/bootstrap_authentik.py
```

### Step 6: Verify Deployment

1. Access admin UI: https://kublai.kurult.ai/if/admin/
2. Login with:
   - Username: `akadmin`
   - Password: `5bAQmpdbqXgfwjV7P4JcSsK1t42+bAiF`
3. Change the admin password immediately
4. Configure WebAuthn:
   - Go to Flows & Stages → Stages
   - Create WebAuthn authenticator stage
   - Add to authentication flow

## Troubleshooting

### Service Crashes

Check logs:
```bash
railway logs --service unique-manifestation
```

Common issues:
- Missing environment variables
- Database connection failures
- Invalid secret key format

### Database Connection Issues

Verify database is running:
```bash
railway status --json | grep -A 5 Postgres-P5UQ
```

Check database variables:
```bash
railway variables -s Postgres-P5UQ
```

### Domain Issues

Verify DNS:
```bash
dig kublai.kurult.ai
```

Check SSL certificate:
```bash
curl -v https://kublai.kurult.ai/health
```

## Rollback

To rollback in case of issues:

```bash
# Stop proxy first (disables auth)
railway service stop --service loyal-enchantment

# Restart moltbot to ensure it's accessible
railway service restart --service moltbot-railway-template
```

## Support

For issues with Railway:
- Dashboard: https://railway.com/project/26201f75-3375-46ce-98c7-9d1dde5f9569
- Docs: https://docs.railway.com/

For issues with Authentik:
- Docs: https://docs.goauthentik.io/
- Community: https://goauthentik.io/discord
