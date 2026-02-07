#!/bin/bash
# Setup GitHub webhook for skill-sync-service

set -e

echo "=== Skill Sync Webhook Setup ==="
echo ""

# Check if Railway CLI is available
if ! command -v railway &> /dev/null; then
    echo "ERROR: Railway CLI not found. Install with: npm install -g @railway/cli"
    exit 1
fi

# Check if authenticated
if ! railway status &> /dev/null; then
    echo "ERROR: Not authenticated with Railway. Run: railway login"
    exit 1
fi

# Generate webhook secret
echo "1. Generating webhook secret..."
SECRET=$(openssl rand -hex 32)
echo "   Generated secret: ${SECRET:0:16}..."
echo ""

# Get Railway service URL
echo "2. Getting Railway service URL..."
SERVICE_URL=$(railway domain --service skill-sync-service 2>/dev/null | grep -o 'https://[^ ]*' | head -1 || echo "")
if [ -z "$SERVICE_URL" ]; then
    echo "   WARNING: Could not get service URL via CLI."
    echo "   Attempting alternative method..."
    SERVICE_URL=$(railway domain --json --service skill-sync-service 2>/dev/null | jq -r '.[0].domain // empty' 2>/dev/null || echo "")
    if [ -z "$SERVICE_URL" ]; then
        echo "   ERROR: Could not get service URL. Is Railway linked?"
        echo "   Run: railway link -p <project-id>"
        echo "   Or verify skill-sync-service exists in the project."
        exit 1
    fi
fi
echo "   Service URL: $SERVICE_URL"
echo ""

# Confirm before setting
echo "3. Ready to configure webhook secret in Railway..."
echo "   Service: skill-sync-service"
echo "   Secret: ${SECRET:0:16}..."
read -p "   Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "   Aborted."
    exit 1
fi

# Set the secret
echo "   Setting GITHUB_WEBHOOK_SECRET in Railway..."
railway variable set GITHUB_WEBHOOK_SECRET "$SECRET" --service skill-sync-service
echo "   Secret configured!"
echo ""

# Verify the secret was set
echo "4. Verifying configuration..."
VERIFY_SECRET=$(railway variable get GITHUB_WEBHOOK_SECRET --service skill-sync-service 2>/dev/null | xargs 2>/dev/null || echo "")
if [ "$VERIFY_SECRET" = "$SECRET" ]; then
    echo "   ✓ Secret verified in Railway"
else
    echo "   WARNING: Could not verify secret. Please check manually:"
    echo "   railway variable get GITHUB_WEBHOOK_SECRET --service skill-sync-service"
fi
echo ""

# Output webhook URL
WEBHOOK_URL="${SERVICE_URL}/webhook/github"
echo "=== Webhook Configuration ==="
echo ""
echo "Webhook URL: $WEBHOOK_URL"
echo "Webhook Secret: $SECRET"
echo ""
echo "Save these values for GitHub configuration!"
echo ""

# Instructions for GitHub
echo "=== Next Steps ==="
echo ""
echo "1. Go to GitHub repository settings:"
echo "   https://github.com/Danservfinn/kurultai-skills/settings/hooks"
echo ""
echo "2. Click 'Add webhook'"
echo ""
echo "3. Configure the webhook:"
echo "   - Payload URL: $WEBHOOK_URL"
echo "   - Content type: application/json"
echo "   - Secret: $SECRET"
echo "   - Events: Select 'Just the push event.'"
echo "   - Active: [x]"
echo ""
echo "4. Click 'Add webhook'"
echo ""
echo "5. Test by making a push to the repository:"
echo "   railway logs --service skill-sync-service --tail"
echo ""
