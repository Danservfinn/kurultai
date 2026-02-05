#!/bin/bash
# Signal Setup Helper Script
# Run this inside the Railway container to link the Signal device

set -e

SIGNAL_ACCOUNT="+15165643945"
DATA_DIR="/data/.signal"

echo "========================================"
echo "Signal Device Linking Helper"
echo "Account: $SIGNAL_ACCOUNT"
echo "========================================"
echo ""

# Check if signal-cli is installed
if ! command -v signal-cli &> /dev/null; then
    echo "ERROR: signal-cli not found"
    exit 1
fi

echo "✓ signal-cli found: $(signal-cli --version | head -1)"
echo ""

# Check data directory
if [ ! -d "$DATA_DIR" ]; then
    echo "Creating Signal data directory..."
    mkdir -p "$DATA_DIR"
    chown 1000:1000 "$DATA_DIR"
fi
echo "✓ Data directory: $DATA_DIR"
echo ""

# Check if already registered
if signal-cli listAccounts 2>/dev/null | grep -q "$SIGNAL_ACCOUNT"; then
    echo "✓ Account $SIGNAL_ACCOUNT is already registered"
    echo ""
    echo "To re-link, first unregister:"
    echo "  signal-cli unregister"
    exit 0
fi

# Generate QR code for linking
echo "Generating QR code for device linking..."
echo ""
echo "========================================"
echo "SCAN THIS QR CODE WITH YOUR SIGNAL APP"
echo "========================================"
echo ""
echo "Steps:"
echo "1. Open Signal on your phone"
echo "2. Go to Settings → Linked Devices"
echo "3. Tap 'Link New Device'"
echo "4. Point camera at the QR code below"
echo ""
echo "========================================"

# Generate the QR code
signal-cli link -n "OpenClaw" || {
    echo "ERROR: Failed to generate QR code"
    exit 1
}

echo ""
echo "========================================"
echo "Device linking complete!"
echo "========================================"
echo ""

# Verify registration
sleep 2
echo "Verifying registration..."
if signal-cli listAccounts | grep -q "$SIGNAL_ACCOUNT"; then
    echo "✓ Account $SIGNAL_ACCOUNT successfully linked"
else
    echo "⚠ Could not verify registration. Check Signal app for linked device."
fi
