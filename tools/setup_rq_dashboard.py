#!/usr/bin/env python3
"""
RQ Dashboard Setup Script
Installs RQ dashboard for monitoring the async queue
"""

import os
import subprocess

# Install rq-dashboard
subprocess.run(["pip", "install", "rq-dashboard", "-q"], check=True)

# Create LaunchAgent for dashboard
dashboard_plist = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.kurultai.rq-dashboard</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/rq-dashboard</string>
        <string>--redis-url</string>
        <string>redis://localhost:6379</string>
        <string>--port</string>
        <string>9181</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
"""

plist_path = os.path.expanduser("~/Library/LaunchAgents/com.kurultai.rq-dashboard.plist")
with open(plist_path, 'w') as f:
    f.write(dashboard_plist)

# Load the service
subprocess.run(["launchctl", "load", plist_path], check=False)

print("✅ RQ Dashboard installed")
print("📊 Access at: http://localhost:9181")
print("   Shows: Queue status, jobs, workers, statistics")
