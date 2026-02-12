#!/bin/bash
# Start LLM-powered Discord bot with proper environment

cd /data/workspace/souls/main

# Source the discord .env file
if [ -f tools/discord/.env ]; then
    export $(grep -v '^#' tools/discord/.env | xargs)
fi

# Set the main webhook URL
export DISCORD_WEBHOOK_URL="${DISCORD_COUNCIL_CHAMBER_WEBHOOK_URL:-${DISCORD_WEBHOOK_URL}}"

# Check if webhook is set
if [ -z "$DISCORD_WEBHOOK_URL" ]; then
    echo "❌ DISCORD_WEBHOOK_URL not set"
    echo "Please check tools/discord/.env"
    exit 1
fi

# Kill any existing bot
if [ -f /tmp/discord_bot.pid ]; then
    kill $(cat /tmp/discord_bot.pid) 2>/dev/null
    rm /tmp/discord_bot.pid
fi

echo "🤖 Starting LLM Discord bot..."
echo "  Webhook: ${DISCORD_WEBHOOK_URL:0:50}..."
echo "  Log: /tmp/discord_bot.log"
echo ""

# Start the bot
nohup python3 tools/discord/bot_natural.py > /tmp/discord_bot.log 2>&1 &
echo $! > /tmp/discord_bot.pid

echo "✅ Bot started with PID: $(cat /tmp/discord_bot.pid)"
echo ""
echo "To test, mention an agent in Discord:"
echo "  @Möngke what are you working on?"
echo "  @Kublai what's the status?"
