# Composio Integration Setup Guide

## Overview

Composio provides AI agent integration with various apps including Twitter/X. This enables the **x-research skill** for Kurultai's Möngke (Researcher) agent to perform Twitter research tasks.

## Prerequisites

- Bun runtime (for x-research skill execution)
- Composio account (free tier available)

## Getting Your Composio API Key

### Step 1: Sign Up

1. Visit https://composio.dev
2. Click "Get Started" or "Sign Up"
3. Create an account using:
   - Email/password
   - GitHub OAuth
   - Google OAuth

### Step 2: Get API Key

1. Log in to https://app.composio.dev
2. Navigate to **Settings** → **API Keys**
3. Click "Create New API Key"
4. Copy the generated key (format: `cpr-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`)

### Step 3: Connect Twitter/X Integration

1. In the Composio dashboard, go to **Integrations**
2. Find **Twitter/X** in the app list
3. Click "Connect" and authorize the connection
4. This enables the x-research skill to access Twitter data

## Configuration

### 1. Add API Key to Environment

Edit `/data/workspace/souls/main/.env`:

```bash
# Composio API key for X/Twitter research integration
COMPOSIO_API_KEY=cpr-your_actual_api_key_here
```

### 2. Verify Bun Runtime

The x-research skill requires Bun:

```bash
# Check if Bun is installed
bun --version

# If not installed:
curl -fsSL https://bun.sh/install | bash
```

### 3. Restart Services

After adding the API key, restart the OpenClaw gateway:

```bash
openclaw gateway restart
```

## Testing the Integration

Once configured, test the x-research skill:

```bash
# Via agent message to Möngke
"Research the latest AI developments on Twitter using x-research"
```

## Free Tier Limits

- **20,000 API calls/month**
- Rate limits apply per integration
- Monitor usage in Composio dashboard

## Troubleshooting

### "API key invalid" error
- Verify the key is copied correctly (includes `cpr-` prefix)
- Check if key is active in Composio dashboard

### "Twitter not connected" error
- Ensure Twitter/X integration is connected in Composio dashboard
- Re-authorize if tokens have expired

### Bun runtime errors
- Verify Bun installation: `bun --version`
- Ensure Bun is in PATH

## Security Notes

- Store API key in `.env` only (never commit to git)
- Rotate keys every 90 days
- Monitor API usage for anomalies
- Use environment-specific keys (dev/staging/prod)

## Related Documentation

- [Composio Docs](https://docs.composio.dev)
- [Kurultai Improvement Plan](../KURULTAI_IMPROVEMENT_PLAN.md)
- [x-research skill (when installed)](../.claude/skills/x-research/SKILL.md)

## Status

- [ ] API key obtained
- [ ] Twitter/X connected
- [ ] Environment configured
- [ ] Integration tested
