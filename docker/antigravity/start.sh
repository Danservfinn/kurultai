#!/bin/bash
# Start Antigravity with virtual display
export DISPLAY=:99
Xvfb :99 -screen 0 1024x768x24 > /dev/null 2>&1 &

# Start Antigravity headless or web mode
# This is a placeholder - actual command depends on Antigravity's CLI
if [ -f /opt/antigravity/bin/antigravity ]; then
    /opt/antigravity/bin/antigravity --headless --port 3000
else
    echo "Antigravity not installed - serving placeholder"
    python3 -m http.server 3000
fi
