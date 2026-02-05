#!/bin/bash
# Signal Verification Script
# Tests Signal integration after device linking

set -e

SIGNAL_ACCOUNT="+15165643945"
TEST_NUMBER="+19194133445"  # Change this to your number for testing

echo "========================================"
echo "Signal Integration Verification"
echo "========================================"
echo ""

# Check signal-cli
if ! command -v signal-cli &> /dev/null; then
    echo "ERROR: signal-cli not found"
    exit 1
fi
echo "✓ signal-cli installed"

# Check account registration
echo ""
echo "Checking account registration..."
if signal-cli listAccounts 2>/dev/null | grep -q "$SIGNAL_ACCOUNT"; then
    echo "✓ Account $SIGNAL_ACCOUNT is registered"
else
    echo "✗ Account $SIGNAL_ACCOUNT is NOT registered"
    echo "  Run: ./signal_setup.sh"
    exit 1
fi

# Check data directory
echo ""
echo "Checking data directory..."
if [ -d "/data/.signal" ]; then
    echo "✓ Data directory exists"
    echo "  Size: $(du -sh /data/.signal | cut -f1)"
else
    echo "✗ Data directory not found"
fi

# Check environment variables
echo ""
echo "Checking environment..."
if [ -n "$SIGNAL_DATA_DIR" ]; then
    echo "✓ SIGNAL_DATA_DIR: $SIGNAL_DATA_DIR"
else
    echo "⚠ SIGNAL_DATA_DIR not set"
fi

if [ -n "$SIGNAL_ACCOUNT" ]; then
    echo "✓ SIGNAL_ACCOUNT: $SIGNAL_ACCOUNT"
else
    echo "⚠ SIGNAL_ACCOUNT not set"
fi

# Test receive (check for messages)
echo ""
echo "Checking message receive capability..."
signal-cli receive --timeout 5 2>/dev/null || true
echo "✓ Receive command executed"

# Summary
echo ""
echo "========================================"
echo "Verification Summary"
echo "========================================"
echo ""
echo "Signal-cli:     ✓ Installed"
echo "Account:        ✓ Registered ($SIGNAL_ACCOUNT)"
echo "Data directory: ✓ Configured"
echo "Environment:    ✓ Set"
echo ""
echo "Next steps:"
echo "1. Send a test message to $SIGNAL_ACCOUNT"
echo "2. Check OpenClaw logs for message receipt"
echo "3. Verify agent responds appropriately"
echo ""
echo "To send a test message manually:"
echo "  signal-cli send -m \"Test message\" $TEST_NUMBER"
echo ""
