#!/bin/bash
# Quick Signal Data Transfer Script
# Run this on your local machine to transfer Signal data to Railway

set -e

SIGNAL_DATA_LOCAL="$HOME/.local/share/signal-cli/data"
SIGNAL_ARCHIVE="/tmp/signal-data.tar.gz"

echo "========================================"
echo "Signal Data Transfer to Railway"
echo "========================================"
echo ""

# Check if data exists
if [ ! -d "$SIGNAL_DATA_LOCAL" ]; then
    echo "ERROR: Signal data not found at $SIGNAL_DATA_LOCAL"
    echo "Make sure you linked the device first."
    exit 1
fi

echo "✓ Signal data found"
echo "  Location: $SIGNAL_DATA_LOCAL"
echo ""

# Create archive
echo "Creating data archive..."
tar -czf "$SIGNAL_ARCHIVE" -C "$SIGNAL_DATA_LOCAL" .
echo "✓ Archive created: $SIGNAL_ARCHIVE"
echo "  Size: $(du -h "$SIGNAL_ARCHIVE" | cut -f1)"
echo ""

# Check Railway CLI
if ! command -v railway &> /dev/null; then
    echo "ERROR: Railway CLI not found"
    echo "Install with: npm install -g @railway/cli"
    exit 1
fi

echo "✓ Railway CLI found"
echo ""

# Check authentication
echo "Checking Railway authentication..."
if ! railway status &> /dev/null; then
    echo "⚠ Not authenticated with Railway"
    echo "Please run: railway login"
    exit 1
fi

echo "✓ Authenticated with Railway"
echo ""

# Link project if needed
echo "Checking project link..."
if ! railway status 2>&1 | grep -q "Project:"; then
    echo "Linking to Railway project..."
    railway link
fi

echo "✓ Project linked"
echo ""

# Upload to container
echo "Uploading Signal data to Railway container..."
echo "This may take a moment..."
echo ""

# Method 1: Try railway cp if available
if railway cp --help &> /dev/null; then
    echo "Using 'railway cp' method..."
    railway cp "$SIGNAL_ARCHIVE" /tmp/signal-data.tar.gz
else
    # Method 2: Use shell with heredoc
    echo "Using shell method..."
    railway shell << 'RAILWAY_COMMANDS'
cd /tmp
cat > signal-data.b64 << 'DATA_EOF'
RAILWAY_COMMANDS

    # Append base64 data
    base64 -i "$SIGNAL_ARCHIVE" >> /tmp/railway_upload.sh

    # Close the heredoc and add extraction commands
    cat >> /tmp/railway_upload.sh << 'RAILWAY_COMMANDS'
DATA_EOF

# Decode and extract
base64 -d signal-data.b64 > signal-data.tar.gz
cd /app/scripts
./signal_import.sh
RAILWAY_COMMANDS

    bash /tmp/railway_upload.sh
fi

echo ""
echo "========================================"
echo "Transfer Complete!"
echo "========================================"
echo ""
echo "The Signal data has been transferred to the Railway container."
echo ""
echo "To verify, run in the Railway shell:"
echo "  signal-cli listAccounts"
echo ""
