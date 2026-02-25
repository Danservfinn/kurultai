#!/usr/bin/env python3
"""
Install FastAPI server as LaunchAgent
"""
import os
from pathlib import Path

LAUNCH_AGENT = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.kurultai.api</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>-m</string>
        <string>uvicorn</string>
        <string>tools.kurultai.api.main:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>8082</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{workdir}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>NEO4J_URI</key>
        <string>bolt://localhost:7687</string>
        <key>NEO4J_USER</key>
        <string>neo4j</string>
        <key>NEO4J_PASSWORD</key>
        <string>myStrongPassword123</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{logdir}/api.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>{logdir}/api.stderr.log</string>
</dict>
</plist>
"""

home = Path.home()
workdir = home / "kurultai/kublai-repo"
python = workdir / "venv/bin/python"
logdir = workdir / "logs"

plist = LAUNCH_AGENT.format(python=python, workdir=workdir, logdir=logdir)
plist_path = home / "Library/LaunchAgents/com.kurultai.api.plist"

with open(plist_path, 'w') as f:
    f.write(plist)

os.system(f"launchctl load {plist_path}")
print(f"✅ FastAPI server installed: {plist_path}")
print(f"📋 API will be available at: http://localhost:8082")
