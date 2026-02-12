#!/bin/bash
# Signal SSE Bridge Startup Script
# Start the SSE bridge before OpenClaw gateway

cd /data/workspace/souls/main

echo "Starting Signal-CLI SSE Bridge..."
echo "================================"

# Check if bridge is already running
if pgrep -f "signal_cli_sse_bridge.py" > /dev/null; then
    echo "✅ Bridge already running"
    exit 0
fi

# Set environment
export SIGNAL_ACCOUNT="+15165643945"
export SIGNAL_CLI_PATH="/usr/local/bin/signal-cli"
export BRIDGE_HOST="127.0.0.1"
export BRIDGE_PORT="8080"
export SIGNAL_HTTP_PORT="8081"

# Start bridge in background
nohup python3 tools/signal_cli_sse_bridge.py > /tmp/signal_bridge.log 2>&1 &
BRIDGE_PID=$!

echo "🚀 Bridge started (PID: $BRIDGE_PID)"
echo "📋 Logs: tail -f /tmp/signal_bridge.log"
echo ""
echo "Waiting for bridge to be ready..."

# Wait for health endpoint
for i in {1..30}; do
    if curl -s http://127.0.0.1:8080/health > /dev/null 2>&1; then
        echo "✅ Bridge is ready!"
        echo ""
        echo "Now start OpenClaw gateway:"
        echo "  openclaw gateway"
        exit 0
    fi
    sleep 1
done

echo "❌ Bridge failed to start. Check logs:"
tail -20 /tmp/signal_bridge.log
exit 1
