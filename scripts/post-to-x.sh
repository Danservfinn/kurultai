#!/bin/bash
# Autonomous X/Twitter Posting Script
# Usage: ./post-to-x.sh "Your tweet message here"

# Load credentials
source /Users/kublai/.openclaw/agents/main/.x_api_credentials

# Get tweet text from argument or stdin
TWEET_TEXT="$1"

if [ -z "$TWEET_TEXT" ]; then
    echo "Usage: $0 \"Your tweet message\""
    exit 1
fi

# Create OAuth 1.0a signature (simplified - uses curl with oauth params)
# For production, use a proper OAuth library

# Post tweet using Twitter API v2
RESPONSE=$(curl -X POST "https://api.twitter.com/2/tweets" \
  -H "Authorization: OAuth oauth_consumer_key=\"$X_API_KEY\",oauth_token=\"$X_ACCESS_TOKEN\",oauth_signature_method=\"HMAC-SHA1\",oauth_timestamp=\"$(date +%s)\",oauth_nonce=\"$(openssl rand -base64 32)\",oauth_version=\"1.0\",oauth_signature=\"...\"" \
  -H "Content-Type: application/json" \
  -d "{\"text\": \"$TWEET_TEXT\"}" \
  2>&1)

echo "Response: $RESPONSE"

# Check if successful
if echo "$RESPONSE" | grep -q "data"; then
    echo "✅ Tweet posted successfully!"
    exit 0
else
    echo "❌ Failed to post tweet"
    echo "$RESPONSE"
    exit 1
fi
