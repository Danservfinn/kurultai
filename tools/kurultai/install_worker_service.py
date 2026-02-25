#!/usr/bin/env python3
"""
Kurultai RQ Worker LaunchAgent Setup

This script creates a macOS LaunchAgent for the RQ worker.
Run once to install: python -m tools.kurultai.install_worker_service
"""

import os
import sys
from pathlib import Path

LAUNCH_AGENT_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.kurultai.worker</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>-m</string>
        <string>tools.kurultai.worker</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{working_dir}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>NEO4J_URI</key>
        <string>bolt://localhost:7687</string>
        <key>NEO4J_USER</key>
        <string>neo4j</string>
        <key>NEO4J_PASSWORD</key>
        <string>myStrongPassword123</string>
        <key>REDIS_URL</key>
        <string>redis://localhost:6379</string>
        <key>USE_ASYNC_QUEUE</key>
        <string>true</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log_dir}/worker.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/worker.stderr.log</string>
</dict>
</plist>
"""

def install_service():
    """Install the LaunchAgent service."""
    home = Path.home()
    launch_agents = home / "Library/LaunchAgents"
    launch_agents.mkdir(parents=True, exist_ok=True)
    
    working_dir = home / "kurultai/kublai-repo"
    python_path = working_dir / "venv/bin/python"
    log_dir = working_dir / "logs"
    log_dir.mkdir(exist_ok=True)
    
    plist_path = launch_agents / "com.kurultai.worker.plist"
    
    plist_content = LAUNCH_AGENT_PLIST.format(
        python_path=python_path,
        working_dir=working_dir,
        log_dir=log_dir
    )
    
    with open(plist_path, 'w') as f:
        f.write(plist_content)
    
    print(f"✅ Created LaunchAgent: {plist_path}")
    
    # Load the service
    os.system(f"launchctl load {plist_path}")
    print(f"✅ Loaded service. Worker will start automatically.")
    print(f"📋 Check logs: {log_dir}/worker.*.log")

if __name__ == '__main__':
    install_service()
