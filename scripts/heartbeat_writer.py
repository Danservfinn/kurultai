#!/usr/bin/env python3
"""
Heartbeat Writer - Ogedei

Writes heartbeat status to a file for monitoring.
Runs in a loop, writing status every 30 seconds.

Status includes:
- Gateway status (launchd service state, port connectivity)
- Task queue depth (pending tasks across all agents)
- System health indicators

Usage:
    python3 heartbeat_writer.py        # Run once
    python3 heartbeat_writer.py --loop # Run continuously
"""

import argparse
import glob
import json
import os
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# Configuration
LOG_DIR = Path("/Users/kublai/.openclaw/agents/main/logs")
HEARTBEAT_LOG = LOG_DIR / "heartbeat.log"
AGENTS_DIR = Path("/Users/kublai/.openclaw/agents")

# Gateway configuration
GATEWAYS = [
    {
        "name": "main",
        "label": "ai.openclaw.gateway",
        "port": 18789,
    },
    {
        "name": "tolui",
        "label": "ai.openclaw.gateway.tolui",
        "port": 18792,
    }
]

# Agents to monitor for task queue
AGENTS = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei"]


class GracefulExit:
    """Handle graceful exit on SIGTERM/SIGINT"""
    def __init__(self):
        self.shutdown = False
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def _handle_signal(self, signum, frame):
        print("\nReceived shutdown signal, exiting gracefully...")
        self.shutdown = True


def check_launchd_service(label: str) -> Tuple[bool, Optional[int]]:
    """Check if a launchd service is running. Returns (running, pid)."""
    try:
        result = subprocess.run(
            ["launchctl", "list"],
            capture_output=True,
            text=True,
            timeout=5
        )
        for line in result.stdout.split("\n"):
            parts = line.strip().split("\t")
            if len(parts) >= 3 and parts[2] == label:
                pid = int(parts[0]) if parts[0] != "-" else None
                running = pid is not None and pid > 0
                return running, pid
        return False, None
    except Exception:
        return False, None


def check_port_connectivity(port: int, timeout: int = 2) -> bool:
    """Check if a port is accepting connections."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            result = sock.connect_ex(("127.0.0.1", port))
            return result == 0
    except Exception:
        return False


def get_gateway_status() -> List[Dict]:
    """Get status of all configured gateways."""
    gateways = []
    for gateway in GATEWAYS:
        running, pid = check_launchd_service(gateway["label"])
        port_open = check_port_connectivity(gateway["port"])

        gateways.append({
            "name": gateway["name"],
            "label": gateway["label"],
            "port": gateway["port"],
            "running": running,
            "pid": pid,
            "port_open": port_open,
            "healthy": running and port_open
        })
    return gateways


def get_task_queue_depth() -> Dict:
    """Count pending tasks across all agents."""
    total_pending = 0
    by_agent = {}
    by_priority = {"high": 0, "normal": 0, "low": 0}

    for agent in AGENTS:
        task_dir = AGENTS_DIR / agent / "tasks"
        if not task_dir.exists():
            by_agent[agent] = 0
            continue

        agent_pending = 0
        for pattern in ['high-*.md', 'normal-*.md', 'low-*.md']:
            # Exclude executed, done, gate-passed files
            for task_file in task_dir.glob(pattern):
                if any(suffix in task_file.name for suffix in ['.executing', '.done', '.gate-passed']):
                    continue

                agent_pending += 1
                if 'high-' in task_file.name:
                    by_priority["high"] += 1
                elif 'normal-' in task_file.name:
                    by_priority["normal"] += 1
                else:
                    by_priority["low"] += 1

        by_agent[agent] = agent_pending
        total_pending += agent_pending

    return {
        "total": total_pending,
        "by_agent": by_agent,
        "by_priority": by_priority
    }


def get_system_load() -> Dict:
    """Get basic system load info."""
    try:
        result = subprocess.run(
            ["sysctl", "-n", "vm.loadavg"],
            capture_output=True,
            text=True,
            timeout=5
        )
        # Output format: "{ 2.45 1.87 1.52 }"
        load_str = result.stdout.strip()
        loads = [float(x) for x in load_str.strip("{}").split()[:3]]
        return {
            "1min": loads[0] if len(loads) > 0 else 0,
            "5min": loads[1] if len(loads) > 1 else 0,
            "15min": loads[2] if len(loads) > 2 else 0
        }
    except Exception:
        return {"1min": 0, "5min": 0, "15min": 0}


def write_heartbeat() -> Dict:
    """Write a single heartbeat entry."""
    timestamp = datetime.now().isoformat()

    # Collect status
    gateways = get_gateway_status()
    task_queue = get_task_queue_depth()
    system_load = get_system_load()

    # Calculate overall status
    all_gateways_healthy = all(g["healthy"] for g in gateways)
    overall_status = "healthy" if all_gateways_healthy else "degraded"

    # Build heartbeat record
    heartbeat = {
        "timestamp": timestamp,
        "status": overall_status,
        "gateways": gateways,
        "task_queue": task_queue,
        "system_load": system_load
    }

    # Write to log
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(HEARTBEAT_LOG, 'a') as f:
        f.write(json.dumps(heartbeat) + "\n")

    # Also write human-readable status line
    gateway_summary = " ".join(
        f"{g['name']}={'UP' if g['healthy'] else 'DOWN'}"
        for g in gateways
    )
    status_line = (
        f"[{timestamp}] HEARTBEAT | status={overall_status} | "
        f"gateways={gateway_summary} | "
        f"queue_depth={task_queue['total']} | "
        f"load={system_load['1min']:.2f}\n"
    )

    with open(HEARTBEAT_LOG.with_suffix(".human"), 'a') as f:
        f.write(status_line)

    return heartbeat


def print_status(heartbeat: Dict):
    """Print heartbeat status to stdout."""
    ts = heartbeat["timestamp"]
    status = heartbeat["status"]
    queue_depth = heartbeat["task_queue"]["total"]
    load = heartbeat["system_load"]["1min"]

    gateway_str = ", ".join(
        f"{g['name']}:{'UP' if g['healthy'] else 'DOWN'}"
        for g in heartbeat["gateways"]
    )

    print(f"[{ts}] status={status} | gateways={gateway_str} | queue={queue_depth} | load={load:.2f}")


def run_once():
    """Run a single heartbeat write."""
    heartbeat = write_heartbeat()
    print_status(heartbeat)
    return heartbeat


def run_loop(interval: int = 30):
    """Run heartbeat writer in a loop."""
    graceful_exit = GracefulExit()

    print(f"Heartbeat writer started (interval: {interval}s)")
    print(f"Log: {HEARTBEAT_LOG}")
    print(f"Human-readable: {HEARTBEAT_LOG.with_suffix('.human')}")

    while not graceful_exit.shutdown:
        run_once()
        time.sleep(interval)

    print("Heartbeat writer stopped")


def main():
    parser = argparse.ArgumentParser(
        description="Write heartbeat status for monitoring"
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run continuously in a loop"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Interval between heartbeats in seconds (default: 30)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit"
    )

    args = parser.parse_args()

    if args.loop or not args.once:
        run_loop(args.interval)
    else:
        run_once()


if __name__ == "__main__":
    main()
