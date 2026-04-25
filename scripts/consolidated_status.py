#!/usr/bin/env python3
"""
consolidated_status.py — Single-call status checker for watchdog/tock.

Replaces multiple embedded Python heredocs with one invocation.
Checks Neo4j, Redis, and system status in a single process.

Usage:
    python3 consolidated_status.py [--format json|bash]

Output formats:
    json: {"neo4j": "up", "redis": "up", "gateway": "up"}
    bash: neo4j=up redis=up gateway=up (space-separated for eval)
"""
from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
from datetime import datetime

# Timeout for entire script
signal.signal(signal.SIGALRM, lambda *_: sys.exit(1))
signal.alarm(15)

sys.path.insert(0, '/Users/kublai/.openclaw/agents/main/scripts')


def check_neo4j():
    """Check Neo4j connectivity with timeout."""
    try:
        from neo4j_task_tracker import neo4j_session
        with neo4j_session() as session:
            session.run("RETURN 1").consume()
        return "up"
    except Exception:
        return "down"


def check_redis():
    """Check Redis with timeout."""
    try:
        result = subprocess.run(
            ['redis-cli', 'ping'],
            capture_output=True,
            timeout=2
        )
        return "up" if b'PONG' in result.stdout else "down"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "down"


def check_gateway():
    """Check gateway process status."""
    try:
        result = subprocess.run(
            ['pgrep', '-x', 'openclaw-gateway'],
            capture_output=True,
            timeout=1
        )
        return "up" if result.returncode == 0 else "down"
    except subprocess.TimeoutExpired:
        return "down"


def check_cloudflared():
    """Check cloudflared tunnel process status."""
    try:
        result = subprocess.run(
            ['pgrep', '-f', 'cloudflared tunnel run'],
            capture_output=True,
            timeout=1
        )
        return "up" if result.returncode == 0 else "down"
    except subprocess.TimeoutExpired:
        return "down"


def main():
    parser = argparse.ArgumentParser(description="Consolidated status checker")
    parser.add_argument('--format', choices=['json', 'bash'], default='bash',
                       help='Output format')
    parser.add_argument('--services', nargs='+',
                       choices=['neo4j', 'redis', 'gateway', 'cloudflared', 'all'],
                       default=['neo4j', 'redis', 'gateway'],
                       help='Services to check')
    args = parser.parse_args()

    results = {}

    if 'neo4j' in args.services or 'all' in args.services:
        results['neo4j'] = check_neo4j()

    if 'redis' in args.services or 'all' in args.services:
        results['redis'] = check_redis()

    if 'gateway' in args.services or 'all' in args.services:
        results['gateway'] = check_gateway()

    if 'cloudflared' in args.services or 'all' in args.services:
        results['cloudflared'] = check_cloudflared()

    if args.format == 'json':
        print(json.dumps(results))
    else:
        # Bash format: key=value key=value
        print(' '.join(f"{k}={v}" for k, v in results.items()))


if __name__ == '__main__':
    main()
