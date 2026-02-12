#!/bin/bash
# Signal Setup Script for Kurultai
# Fixes "User not registered" error by linking device

set -e

echo "========================================"
echo "Signal-CLI Setup for Kurultai"
echo "========================================"
echo ""

# Check if already registered
if signal-cli -a +15165643945 getUserStatus +15165643945 >/dev/null 2>&1; then
    echo "✅ Signal account +15165643945 is already registered!"
    exit 0
fi

echo "⚠️  Signal account is not registered."
echo ""
echo "To fix this, you need to link this device to your Signal phone app."
echo ""
echo "Step 1: Open Signal on your phone"
echo "Step 2: Go to Settings → Linked Devices"
echo "Step 3: Tap '+' to add a new device"
echo "Step 4: Scan the QR code that will appear below"
echo ""
read -p "Press ENTER when ready to generate QR code..."
echo ""
echo "Generating QR code (valid for 60 seconds)..."
echo ""

# Generate QR code and display it
timeout 60 signal-cli link --name="Kurultai-OpenClaw" 2>&1 | while read line; do
    if [[ "$line" == sgnl://* ]]; then
        echo "🔗 Link URL: $line"
        echo ""
        # Try to generate QR code if qrencode is available
        if command -v qrencode >/dev/null 2>&1; then
            echo "$line" | qrencode -t ANSIUTF8
        else
            echo "(Install qrencode to see QR code: apt-get install qrencode)"
        fi
        echo ""
        echo "⏳ Waiting for you to scan... (60 seconds)"
    fi
done

echo ""
echo "Checking registration status..."
if signal-cli -a +15165643945 getUserStatus +15165643945 >/dev/null 2>&1; then
    echo "✅ SUCCESS! Signal account is now registered."
    echo ""
    echo "You can now start the Signal bridge:"
    echo "  bash tools/start_signal_bridge.sh"
else
    echo "❌ Registration failed or timed out."
    echo ""
    echo "Try again with:"
    echo "  bash tools/fix_signal_registration.sh"
    exit 1
fi
