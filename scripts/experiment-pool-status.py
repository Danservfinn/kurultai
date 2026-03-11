#!/usr/bin/env python3
"""
experiment-pool-status.py

Collects experiment pool status metrics for tock-gather telemetry.

This script:
1. Reads .experiment-pool-status.json if available (written by experiment-pool.py)
2. Falls back to computing metrics from experiments directory
3. Returns JSON with running, queued, completed, max_concurrent metrics

Usage:
    python3 experiment-pool-status.py [--json]

Output:
    JSON with experiment pool metrics
"""

import json
import os
import sys
import glob
from pathlib import Path
from datetime import datetime


def get_pool_status_from_file():
    """Read status from .experiment-pool-status.json if available."""
    pool_file = Path.home() / ".openclaw" / ".experiment-pool-status.json"
    if pool_file.exists():
        try:
            with open(pool_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return None


def compute_metrics_from_experiments():
    """
    Compute experiment metrics from the experiments directory.

    Scans for:
    - experiment/*.yaml files (queued experiments)
    - branches matching 'experiment/*' (running experiments)
    - ledger.tsv entries (completed experiments)
    """
    experiments_dir = Path.home() / ".openclaw" / "experiments"
    result = {
        "running": 0,
        "queued": 0,
        "completed": 0,
        "max_concurrent": 3,  # Default MAX_CONCURRENT
        "total_experiments": 0
    }

    # Count queued experiments (YAML files in experiments dir)
    if experiments_dir.exists():
        yaml_files = list(experiments_dir.glob("*.yaml"))
        # Exclude sample/test files
        result["queued"] = len([
            f for f in yaml_files
            if not f.name.startswith("sample-") and not f.name.startswith("test-")
        ])
        result["total_experiments"] = len(yaml_files)

    # Count completed experiments from ledger.tsv
    ledger_file = experiments_dir / "ledger.tsv"
    if ledger_file.exists():
        try:
            with open(ledger_file) as f:
                # Count non-header lines
                lines = [l for l in f if l.strip() and not l.startswith('#')]
                result["completed"] = len(lines)
        except IOError:
            pass

    # Count running experiment branches via git
    try:
        import subprocess
        result_branch = subprocess.run(
            ["git", "branch", "--list", "experiment/*"],
            cwd=Path.home() / ".openclaw",
            capture_output=True,
            text=True,
            timeout=5
        )
        if result_branch.returncode == 0:
            branches = [b for b in result_branch.stdout.split('\n') if b.strip()]
            result["running"] = len(branches)
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        # Git not available or failed - use subprocess
        pass

    return result


def get_rollback_count_last_hour():
    """Count rollback events from the last hour."""
    # Check for rollback.jsonl in logs
    rollback_log = Path.home() / ".openclaw" / "logs" / "rollback.jsonl"
    count = 0

    if rollback_log.exists():
        try:
            one_hour_ago = datetime.now().timestamp() - 3600
            with open(rollback_log) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        ts = entry.get("timestamp", "")
                        if ts:
                            try:
                                # Parse ISO timestamp
                                dt = datetime.fromisoformat(
                                    ts.replace("Z", "+00:00").replace("+00:00", "")
                                )
                                if dt.timestamp() > one_hour_ago:
                                    count += 1
                            except (ValueError, TypeError):
                                # Skip if timestamp parsing fails
                                continue
                    except json.JSONDecodeError:
                        continue
        except (IOError, OSError):
            pass

    return count


def get_experiment_branch_count():
    """Get count of experiment/* git branches."""
    count = 0
    try:
        import subprocess
        result = subprocess.run(
            ["git", "branch", "--list", "experiment/*"],
            cwd=Path.home() / ".openclaw",
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            branches = [b for b in result.stdout.split('\n') if b.strip()]
            count = len(branches)
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass
    return count


def main():
    """Main entry point."""
    # Try to get status from pool file first
    pool_status = get_pool_status_from_file()

    if pool_status:
        # Pool is running, use its status
        result = {
            "source": "experiment-pool",
            "running": pool_status.get("running", 0),
            "queued": pool_status.get("queued", 0),
            "completed": pool_status.get("completed", 0),
            "max_concurrent": pool_status.get("max_concurrent", 3),
        }
    else:
        # Pool not running, compute from experiments directory
        result = compute_metrics_from_experiments()
        result["source"] = "filesystem"

    # Add git branch count
    result["branch_count"] = get_experiment_branch_count()

    # Add rollback count (last hour)
    result["rollbacks_last_hour"] = get_rollback_count_last_hour()

    # Output JSON
    print(json.dumps(result))


if __name__ == "__main__":
    main()
