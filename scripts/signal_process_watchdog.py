#!/usr/bin/env python3
"""
Signal Process Watchdog - Detects and kills orphaned signal-cli processes.

This script is designed to run periodically to clean up zombie signal-cli processes
that can cause lock contention with the main Signal JSON-RPC server.

Usage:
    python3 signal_process_watchdog.py [--dry-run]
"""

import subprocess
import sys
import time
from datetime import datetime


def get_signal_processes():
    """Get all signal-cli processes."""
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
            timeout=10
        )
        processes = []
        for line in result.stdout.strip().split("\n")[1:]:  # Skip header
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) < 11:
                continue
            pid = parts[1]
            command = " ".join(parts[10:])

            # Check for signal-cli processes
            if "signal-cli" in command:
                # Determine if it's the JSON-RPC daemon or a zombie
                is_jsonrpc = "jsonRpc" in command and "--receive-mode" in command
                is_daemon = "daemon" in command and "--http" in command
                is_zombie = not is_jsonrpc and not is_daemon

                processes.append({
                    "pid": int(pid),
                    "command": command[:100],
                    "is_jsonrpc": is_jsonrpc,
                    "is_daemon": is_daemon,
                    "is_zombie": is_zombie,
                    "cpu": float(parts[2]) if parts[2] != "0.0" else 0,
                    "mem": float(parts[3]) if parts[3] != "0.0" else 0,
                })
        return processes
    except Exception as e:
        print(f"ERROR: Failed to get processes: {e}", file=sys.stderr)
        return []


def kill_zombie_processes(dry_run=False):
    """Kill zombie signal-cli processes."""
    processes = get_signal_processes()

    if not processes:
        print("No signal-cli processes found")
        return 0

    print(f"Found {len(processes)} signal-cli process(es)")

    zombies_killed = 0
    for p in processes:
        status = "JSON-RPC" if p["is_jsonrpc"] else ("DAEMON" if p["is_daemon"] else "ZOMBIE")
        print(f"  PID {p['pid']}: {status} - {p['command'][:60]}...")

        if p["is_zombie"]:
            if dry_run:
                print(f"    [DRY-RUN] Would kill zombie process")
            else:
                try:
                    subprocess.run(["kill", "-9", str(p["pid"])], timeout=5)
                    print(f"    ✓ Killed zombie process")
                    zombies_killed += 1
                except Exception as e:
                    print(f"    ✗ Failed to kill: {e}")

    return zombies_killed


def check_signal_lock():
    """Check if Signal config file is locked."""
    try:
        result = subprocess.run(
            ["lsof", "/Users/kublai/.config/signal-cli/data/"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.stdout.strip():
            holders = result.stdout.strip().split("\n")
            print(f"Signal config locked by {len(holders)} process(es)")
            return True
        return False
    except Exception:
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Signal Process Watchdog")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without doing it")
    args = parser.parse_args()

    print(f"=== Signal Process Watchdog ===")
    print(f"Time: {datetime.now().isoformat()}")
    print()

    killed = kill_zombie_processes(dry_run=args.dry_run)

    print()
    if args.dry_run:
        print(f"[DRY-RUN] Would have killed {killed} zombie process(es)")
    else:
        print(f"Killed {killed} zombie process(es)")


if __name__ == "__main__":
    main()
