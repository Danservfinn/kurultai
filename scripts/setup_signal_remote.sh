#!/bin/bash
# Signal Setup Script for Railway Container
# Run this in the Railway container to download and setup Signal data

set -e

SIGNAL_DATA_URL="${SIGNAL_DATA_URL:-}"
SIGNAL_ACCOUNT="+15165643945"
DATA_DIR="/data/.signal"

echo "========================================"
echo "Signal Remote Setup"
echo "========================================"
echo ""

# Check if data already exists
if [ -d "$DATA_DIR" ] && [ "$(ls -A $DATA_DIR 2>/dev/null)" ]; then
    echo "Signal data already exists. Checking registration..."
    if signal-cli listAccounts 2>/dev/null | grep -q "$SIGNAL_ACCOUNT"; then
        echo "✓ Account $SIGNAL_ACCOUNT is already registered"
        exit 0
    else
        echo "Data exists but account not registered. Re-extracting..."
    fi
fi

# If URL is provided, download data
if [ -n "$SIGNAL_DATA_URL" ]; then
    echo "Downloading Signal data from URL..."
    curl -L -o /tmp/signal-data.tar.gz "$SIGNAL_DATA_URL"
    echo "✓ Downloaded"
else
    echo "ERROR: No SIGNAL_DATA_URL environment variable set"
    echo ""
    echo "To setup Signal:"
    echo "1. Upload signal-data.tar.gz to a temporary file host"
    echo "2. Set SIGNAL_DATA_URL environment variable in Railway"
    echo "3. Restart the service"
    exit 1
fi

# Create data directory
mkdir -p "$DATA_DIR"

# Extract data
echo "Extracting Signal data..."
tar -xzf /tmp/signal-data.tar.gz -C "$DATA_DIR"

# Fix permissions
chown -R 1000:1000 "$DATA_DIR"
chmod -R 755 "$DATA_DIR"

# Verify
echo ""
echo "Verifying setup..."
if signal-cli listAccounts 2>/dev/null | grep -q "$SIGNAL_ACCOUNT"; then
    echo "✓ Account $SIGNAL_ACCOUNT successfully configured"
    rm -f /tmp/signal-data.tar.gz
else
    echo "✗ Setup verification failed"
    exit 1
fi

echo ""
echo "========================================"
echo "Signal Setup Complete"
echo "========================================"
