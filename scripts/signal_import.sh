#!/bin/bash
# Signal Data Import Script
# Run this inside the Railway container to import linked device data

set -e

SIGNAL_ACCOUNT="+15165643945"
DATA_DIR="/data/.signal"

echo "========================================"
echo "Signal Data Import"
echo "========================================"
echo ""

# Check if data archive exists
if [ ! -f "/tmp/signal-data.tar.gz" ]; then
    echo "ERROR: /tmp/signal-data.tar.gz not found"
    echo ""
    echo "Upload the data file first:"
    echo "  railway login"
    echo "  railway link"
    echo "  railway upload /tmp/signal-data.tar.gz"
    exit 1
fi

echo "✓ Data archive found"

# Backup existing data if present
if [ -d "$DATA_DIR" ] && [ "$(ls -A $DATA_DIR 2>/dev/null)" ]; then
    echo "Backing up existing data..."
    mv "$DATA_DIR" "${DATA_DIR}.backup.$(date +%s)"
    mkdir -p "$DATA_DIR"
fi

# Extract data
echo "Extracting Signal data..."
tar -xzf /tmp/signal-data.tar.gz -C "$DATA_DIR" --strip-components=1

# Fix permissions
echo "Setting permissions..."
chown -R 1000:1000 "$DATA_DIR"
chmod -R 755 "$DATA_DIR"

# Verify
echo ""
echo "Verifying import..."
if signal-cli listAccounts 2>/dev/null | grep -q "$SIGNAL_ACCOUNT"; then
    echo "✓ Account $SIGNAL_ACCOUNT successfully imported"
    echo ""
    echo "Signal is now configured and ready to use!"
    echo ""
    echo "Test with:"
    echo "  signal-cli receive"
else
    echo "✗ Import verification failed"
    echo "Check logs: signal-cli listAccounts"
    exit 1
fi

echo ""
echo "========================================"
echo "Import Complete"
echo "========================================"
