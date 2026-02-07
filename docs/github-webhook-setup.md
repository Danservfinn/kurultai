# GitHub Webhook Setup for Skill Sync

## Overview
This document describes how to configure GitHub webhooks to automatically deploy skill updates to the kublai gateway. When you push changes to the kurultai-skills repository, GitHub will notify the skill-sync-service, which will validate and deploy the updated skills to the gateway.

## Prerequisites
- Railway CLI installed and authenticated
- Admin access to the `Danservfinn/kurultai-skills` GitHub repository
- `skill-sync-service` deployed on Railway

## Quick Start

Run the automated setup script:

```bash
bash /Users/kurultai/molt/scripts/setup-github-webhook.sh
```

This script will:
1. Generate a secure webhook secret
2. Retrieve your Railway service URL
3. Configure the secret in Railway environment variables
4. Display the webhook URL and secret for GitHub configuration

## Manual Setup

### Step 1: Generate Webhook Secret

Generate a cryptographically secure random secret:

```bash
openssl rand -hex 32
```

Save the output - you'll need it for both Railway and GitHub.

### Step 2: Get Railway Service URL

Get the public URL of your skill-sync-service:

```bash
railway domain --service skill-sync-service
```

The output will be something like: `https://skill-sync-service.production.railway.app`

### Step 3: Configure Secret in Railway

Set the webhook secret as an environment variable:

```bash
railway variable set GITHUB_WEBHOOK_SECRET <your-secret> --service skill-sync-service
```

Verify it was set correctly:

```bash
railway variable get GITHUB_WEBHOOK_SECRET --service skill-sync-service
```

### Step 4: Add Webhook in GitHub

1. Navigate to repository settings:
   ```
   https://github.com/Danservfinn/kurultai-skills/settings/hooks
   ```

2. Click "Add webhook"

3. Configure the webhook:
   | Field | Value |
   |-------|-------|
   | **Payload URL** | `https://<your-service-url>/webhook/github` |
   | **Content type** | `application/json` |
   | **Secret** | (paste your generated secret) |
   | **Events** | Select "Just the push event." |
   | **Active** | ✓ |

4. Click "Add webhook"

5. GitHub will send a test ping event - check for a green checkmark next to the webhook

### Step 5: Verify the Webhook

Check Railway logs to confirm the ping was received:

```bash
railway logs --service skill-sync-service --lines 20
```

Look for log entries like:
- `Webhook received: ping`
- `Webhook signature verified`

## Testing the Full Flow

### Make a Test Change

Create a test change in the skills repository:

```bash
# Clone if you haven't already
cd /tmp
rm -rf kurultai-skills
git clone git@github.com:Danservfinn/kurultai-skills.git
cd kurultai-skills

# Create a test skill file
mkdir -p test-skill
cat > test-skill/SKILL.md << 'EOF'
# Test Skill

A test skill to verify webhook deployment.

## Usage

This is a test.
EOF

# Commit and push
git add test-skill/SKILL.md
git commit -m "test: webhook verification"
git push origin main
```

### Monitor Webhook Processing

Watch Railway logs in real-time:

```bash
railway logs --service skill-sync-service --tail
```

Expected log output:
```
Webhook received: push
Processing 1 changed skill files
Validating skill: test-skill
Deploying skill: test-skill
Successfully deployed 1 skills
```

### Verify Deployment

Check that the skill was deployed to the gateway:

```bash
railway logs --service kublai-gateway --tail | grep "test-skill"
```

Or test via the gateway API (if available):

```bash
curl https://<kublai-gateway-url>/api/skills | jq '.[] | select(.name == "test-skill")'
```

### Clean Up Test Data

Remove the test skill:

```bash
cd /tmp/kurultai-skills
rm -rf test-skill
git add -A
git commit -m "test: cleanup webhook verification"
git push origin main
```

## Troubleshooting

### Webhook Not Delivering

**Symptoms:** Red X next to webhook in GitHub settings, no logs in Railway

**Solutions:**
1. Check webhook status in GitHub repo settings
2. Verify Railway service is running: `railway status --service skill-sync-service`
3. Check service is publicly accessible (not in a private network)
4. Verify the service URL is correct: `railway domain --service skill-sync-service`

### Signature Verification Failing

**Symptoms:** Logs show "Invalid webhook signature" or "Signature verification failed"

**Solutions:**
1. Verify `GITHUB_WEBHOOK_SECRET` is set in Railway:
   ```bash
   railway variable get GITHUB_WEBHOOK_SECRET --service skill-sync-service
   ```
2. Ensure the secret matches exactly between GitHub and Railway
3. Regenerate secret and update both locations:
   ```bash
   # Generate new secret
   NEW_SECRET=$(openssl rand -hex 32)

   # Update Railway
   railway variable set GITHUB_WEBHOOK_SECRET "$NEW_SECRET" --service skill-sync-service

   # Update GitHub webhook settings with the new secret
   ```
4. Check for trailing whitespace or copy-paste errors

### Skills Not Deploying

**Symptoms:** Webhook received but skills not updated

**Solutions:**
1. Check skill file names contain "SKILL.md" (exact match required)
2. Verify skill validation passes in logs:
   ```
   Validating skill: my-skill
   ERROR: Invalid skill format: missing required field 'description'
   ```
3. Ensure `/data/skills` directory is writable
4. Check gateway logs for deployment errors:
   ```bash
   railway logs --service kublai-gateway --tail
   ```

### Partial Deployment

**Symptoms:** Some skills deploy, others don't

**Solutions:**
1. Check logs for individual skill validation errors
2. Verify all SKILL.md files follow the required schema
3. Check for file encoding issues (should be UTF-8)
4. Ensure skill names don't contain special characters

### Railway Service URL Issues

**Symptoms:** Can't get service URL, connection refused

**Solutions:**
1. Verify service is deployed: `railway status`
2. Check service has a domain configured: `railway domain --service skill-sync-service`
3. If no domain, create one: `railway domain --service skill-sync-service`
4. Check service logs for startup errors: `railway logs --service skill-sync-service`

## Security Considerations

### Secret Rotation

Rotate webhook secrets periodically:

```bash
# Generate new secret
NEW_SECRET=$(openssl rand -hex 32)

# Update Railway first
railway variable set GITHUB_WEBHOOK_SECRET "$NEW_SECRET" --service skill-sync-service

# Immediately update GitHub webhook settings
# Go to: https://github.com/Danservfinn/kurultai-skills/settings/hooks
# Edit webhook, update secret, save
```

### IP Whitelisting (Optional)

For additional security, configure Railway to only accept requests from GitHub webhook IPs:

1. Get GitHub webhook IP ranges:
   ```bash
   curl https://api.github.com/meta | jq '.hooks[]'
   ```

2. Configure Railway firewall rules (if available in your plan)

## Webhook Reference

### Expected Payload

GitHub sends a POST request with the following structure:

```json
{
  "ref": "refs/heads/main",
  "repository": {
    "name": "kurultai-skills",
    "full_name": "Danservfinn/kurultai-skills"
  },
  "pusher": {
    "name": "username",
    "email": "user@example.com"
  },
  "commits": [...],
  "head_commit": {...}
}
```

### Headers

The webhook request includes these headers:

| Header | Description |
|--------|-------------|
| `X-GitHub-Event` | Event type (`push`, `ping`) |
| `X-Hub-Signature-256` | HMAC signature for verification |
| `X-GitHub-Delivery` | Unique delivery ID |
| `Content-Type` | `application/json` |

### Response Codes

| Code | Meaning |
|------|---------|
| `200` | Webhook processed successfully |
| `202` | Webhook accepted, processing asynchronously |
| `400` | Invalid payload |
| `401` | Signature verification failed |
| `500` | Internal server error |

## Related Documentation

- [GitHub Webhooks Documentation](https://docs.github.com/en/developers/webhooks-and-events/webhooks)
- [Railway Environment Variables](https://docs.railway.app/reference/variables)
- [Skill Sync Service Architecture](./skill-sync-service.md)

## Support

For issues with:
- **Railway deployment:** Check Railway status page or logs
- **GitHub webhooks:** Review GitHub webhook delivery logs in repo settings
- **Skill deployment:** Check skill-sync-service logs for validation errors
