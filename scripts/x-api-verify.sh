#!/bin/bash
# Quick verification of X/Twitter API OAuth 1.0a credentials
# Use this after regenerating tokens in the X Developer Portal

# Load credentials
CREDS_FILE="$HOME/.openclaw/credentials/x-api.env"

if [ ! -f "$CREDS_FILE" ]; then
    echo "❌ Credentials file not found: $CREDS_FILE"
    exit 1
fi

# Source credentials (with safety checks)
source "$CREDS_FILE" 2>/dev/null || true

# Check if required variables are set
if [ -z "$X_CONSUMER_KEY" ] || [ -z "$X_CONSUMER_SECRET" ] || [ -z "$X_ACCESS_TOKEN" ] || [ -z "$X_ACCESS_TOKEN_SECRET" ]; then
    echo "❌ Missing required credentials in $CREDS_FILE"
    echo "Required: X_CONSUMER_KEY, X_CONSUMER_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET"
    exit 1
fi

echo "🔍 Testing X/Twitter API OAuth 1.0a credentials..."
echo ""

# Test with Python client (more reliable)
python3 "$HOME/.openclaw/agents/main/scripts/x-twitter-client.py" --verify-credentials

exit_code=$?

if [ $exit_code -eq 0 ]; then
    echo ""
    echo "✅ Credentials verified! You can now post tweets."
    echo ""
    echo "To post a test tweet:"
    echo '  python3 ~/.openclaw/agents/main/scripts/x-twitter-client.py --post "Test tweet from Kurultai"'
else
    echo ""
    echo "❌ Credentials verification failed."
    echo ""
    echo "Next steps:"
    echo "1. Go to https://developer.twitter.com/en/portal/dashboard"
    echo "2. Check your API tier (Free tier cannot post tweets)"
    echo "3. Regenerate OAuth 1.0a tokens"
    echo "4. Update $CREDS_FILE with new tokens"
fi

exit $exit_code
