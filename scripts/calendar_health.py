#!/usr/bin/env python3
"""calendar_health.py — Health check for calendar system.

Returns exit code 0 if healthy, 1 if stale or unhealthy.
Designed to be called by monitoring systems or OpenClaw health endpoint.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

HEALTH_FILE = Path.home() / ".openclaw/state/calendar_health.json"
STALE_THRESHOLD_SECONDS = 180  # 3 minutes (worker runs every 60s)

def check():
    if not HEALTH_FILE.exists():
        print(json.dumps({"status": "unknown", "reason": "no health file"}))
        return 1

    health = json.loads(HEALTH_FILE.read_text())
    last_run = datetime.fromisoformat(health["last_run"])
    age = (datetime.now() - last_run).total_seconds()

    if age > STALE_THRESHOLD_SECONDS:
        health["status"] = "stale"
        health["age_seconds"] = int(age)
        print(json.dumps(health))
        return 1

    health["status"] = "healthy"
    health["age_seconds"] = int(age)
    print(json.dumps(health))
    return 0

if __name__ == "__main__":
    sys.exit(check())
