#!/bin/bash
# Signal Diagnostics Script
# Troubleshoot Signal integration issues

echo "========================================"
echo "Signal Diagnostics"
echo "========================================"
echo ""

# System checks
echo "--- System Checks ---"
echo ""

# Check Java
if command -v java &> /dev/null; then
    echo "✓ Java installed: $(java -version 2>&1 | head -1)"
else
    echo "✗ Java not found (required for signal-cli)"
fi

# Check signal-cli
if command -v signal-cli &> /dev/null; then
    echo "✓ signal-cli installed: $(signal-cli --version | head -1)"
    echo "  Path: $(which signal-cli)"
else
    echo "✗ signal-cli not found"
fi

# Check directories
echo ""
echo "--- Directory Checks ---"
echo ""

echo "Signal data directory:"
if [ -d "/data/.signal" ]; then
    ls -la /data/.signal
else
    echo "✗ /data/.signal does not exist"
fi

echo ""
echo "Signal-cli binary:"
if [ -L "/usr/local/bin/signal-cli" ]; then
    ls -la /usr/local/bin/signal-cli
else
    echo "✗ signal-cli symlink not found"
fi

# Check environment
echo ""
echo "--- Environment Variables ---"
echo ""
echo "SIGNAL_DATA_DIR: ${SIGNAL_DATA_DIR:-'not set'}"
echo "SIGNAL_ACCOUNT: ${SIGNAL_ACCOUNT:-'not set'}"
echo "HOME: ${HOME}"

# Check processes
echo ""
echo "--- Process Checks ---"
echo ""
if pgrep -f signal-cli > /dev/null; then
    echo "✓ signal-cli daemon running"
    pgrep -f signal-cli
else
    echo "⚠ signal-cli daemon not running (may be managed by OpenClaw)"
fi

# Test signal-cli commands
echo ""
echo "--- signal-cli Tests ---"
echo ""

echo "Listing accounts:"
signal-cli listAccounts 2>&1 || echo "✗ listAccounts failed"

echo ""
echo "Checking daemon status:"
signal-cli daemon --help 2>&1 | head -5 || echo "✗ daemon check failed"

# Config check
echo ""
echo "--- Configuration Check ---"
echo ""
if [ -f "/app/moltbot.json" ]; then
    echo "✓ moltbot.json exists"
    if grep -q '"cliPath"' /app/moltbot.json; then
        echo "✓ cliPath configured"
        grep '"cliPath"' /app/moltbot.json
    else
        echo "✗ cliPath not configured in moltbot.json"
    fi
else
    echo "✗ moltbot.json not found"
fi

# Logs
echo ""
echo "--- Recent Logs ---"
echo ""
if [ -d "/data/workspace/logs" ]; then
    ls -lt /data/workspace/logs | head -5
else
    echo "No log directory found"
fi

echo ""
echo "========================================"
echo "Diagnostics Complete"
echo "========================================"
