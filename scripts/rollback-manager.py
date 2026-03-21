#!/usr/bin/env python3
"""
Rollback Manager — Automatic regression detection and git revert

Detects metric regression and automatically executes git revert with alerting.
This is a P0 component required before autonomous experiments can run.

Usage:
    # Check if rollback needed
    python3 rollback-manager.py --check --metrics metrics.json

    # Execute rollback
    python3 rollback-manager.py --rollback --commit abc123 --reason "quality_regression_10pct"

    # Test with simulated regression
    python3 rollback-manager.py --test

The rollback thresholds are:
- quality_regression_pct: 5.0 (rollback on > 5% quality drop)
- error_rate_multiplier: 2.0 (rollback on > 2x error rate)
- duration_spike_pct: 50.0 (rollback on > 50% duration increase)
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

# =============================================================================
# CONFIGURATION
# =============================================================================

BASE_DIR = Path.home() / ".openclaw" / "agents" / "main"
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "rollback.jsonl"

# Signal configuration
SIGNAL_RECIPIENT = "+15165643945"
SIGNAL_API_URL = "http://localhost:18789/signal/send"

# Git operation timeout (seconds)
GIT_TIMEOUT = 30

# Neo4j configuration
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

# =============================================================================
# THRESHOLDS
# =============================================================================

class RollbackThresholds:
    """Rollback detection thresholds."""

    QUALITY_REGRESSION_PCT = 5.0      # Rollback on > 5% quality drop
    ERROR_RATE_MULTIPLIER = 2.0       # Rollback on > 2x error rate
    _DURATION_SPIKE_PCT = 50.0         # Rollback on > 50% duration increase


# =============================================================================
# ROLLBACK MANAGER
# =============================================================================

class RollbackManager:
    """
    Manages automatic rollback detection and execution.

    Features:
    - Metric regression detection against baseline
    - Git revert execution with timeout
    - JSONL logging of all rollback events
    - Signal alerts on rollback
    - Neo4j RollbackEvent node creation
    """

    def __init__(self, baseline_metrics: Optional[Dict[str, Any]] = None):
        """
        Initialize rollback manager.

        Args:
            baseline_metrics: Optional baseline metrics for comparison.
                Defaults to system baseline if not provided.
        """
        self.baseline_metrics = baseline_metrics or self._load_baseline()
        self.log_dir = LOG_DIR
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Try to import Neo4j driver
        self.neo4j_available = False
        try:
            from neo4j import GraphDatabase
            self.neo4j_driver = None  # Created on demand
            self.neo4j_available = True
        except ImportError:
            pass

    def _load_baseline(self) -> Dict[str, Any]:
        """Load baseline metrics from system defaults or file."""
        # Default baseline metrics
        default_baseline = {
            "quality": 0.72,
            "error_rate": 0.05,
            "duration_ms": 300.0,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        # Try to load from file if exists
        baseline_file = BASE_DIR / "data" / "baseline-metrics.json"
        if baseline_file.exists():
            try:
                with open(baseline_file) as f:
                    loaded = json.load(f)
                    default_baseline.update(loaded)
            except (json.JSONDecodeError, IOError):
                pass

        return default_baseline

    def check_rollback_needed(self, metrics: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Check if metrics regressed beyond threshold.

        Args:
            metrics: Current metrics to compare against baseline.

        Returns:
            Tuple of (needs_rollback: bool, reason: str)
        """
        baseline = self.baseline_metrics

        # Quality regression check
        current_quality = metrics.get("quality", baseline.get("quality", 1.0))
        baseline_quality = baseline.get("quality", 1.0)

        if baseline_quality > 0:
            quality_threshold = baseline_quality * (
                1 - RollbackThresholds.QUALITY_REGRESSION_PCT / 100
            )
            if current_quality < quality_threshold:
                regression_pct = (
                    (baseline_quality - current_quality) / baseline_quality * 100
                )
                return True, f"quality_regression_{regression_pct:.1f}pct"

        # Error rate spike check
        current_error_rate = metrics.get("error_rate", baseline.get("error_rate", 0))
        baseline_error_rate = baseline.get("error_rate", 0)

        if baseline_error_rate > 0:
            error_threshold = baseline_error_rate * RollbackThresholds.ERROR_RATE_MULTIPLIER
            if current_error_rate > error_threshold:
                multiplier = current_error_rate / baseline_error_rate
                return True, f"error_rate_{multiplier:.1f}x_baseline"

        # Duration spike check
        current_duration = metrics.get("duration_ms", baseline.get("duration_ms", 0))
        baseline_duration = baseline.get("duration_ms", 0)

        if baseline_duration > 0:
            duration_threshold = baseline_duration * (
                1 + RollbackThresholds._DURATION_SPIKE_PCT / 100
            )
            if current_duration > duration_threshold:
                spike_pct = (
                    (current_duration - baseline_duration) / baseline_duration * 100
                )
                return True, f"duration_spike_{spike_pct:.0f}pct"

        return False, ""

    def execute_rollback(
        self,
        commit_hash: str,
        reason: str,
        experiment_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute rollback using git revert.

        Uses `git revert --no-commit` for safer operation (preserves history).

        Args:
            commit_hash: Git commit hash to revert.
            reason: Reason for rollback (from check_rollback_needed).
            experiment_id: Optional associated experiment ID.

        Returns:
            Dict with rollback result including success, duration_ms, etc.
        """
        start_time = time.time()

        result = {
            "commit_hash": commit_hash,
            "reason": reason,
            "experiment_id": experiment_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": "git_revert",
            "success": False,
            "duration_ms": 0,
            "error": None
        }

        try:
            # Execute git revert --no-commit (safer than reset)
            import subprocess
            cmd = ["git", "revert", "--no-commit", commit_hash]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=GIT_TIMEOUT,
                cwd=str(Path.home())
            )

            result["duration_ms"] = int((time.time() - start_time) * 1000)

            if proc.returncode == 0:
                result["success"] = True
                result["git_output"] = proc.stdout
            else:
                result["error"] = proc.stderr or "git revert failed"
                result["git_exit_code"] = proc.returncode

        except subprocess.TimeoutExpired:
            result["error"] = f"git operation timed out after {GIT_TIMEOUT}s"
            result["duration_ms"] = int((time.time() - start_time) * 1000)

        except Exception as e:
            result["error"] = str(e)
            result["duration_ms"] = int((time.time() - start_time) * 1000)

        # Log the rollback event
        self._log_rollback_event(result)

        # Send Signal alert
        self._send_signal_alert(result)

        # Log to Neo4j
        self._log_to_neo4j(result)

        return result

    def _log_rollback_event(self, result: Dict[str, Any]) -> None:
        """
        Log rollback event to JSONL file.

        Args:
            result: Rollback result dictionary.
        """
        try:
            with open(self.log_dir / "rollback.jsonl", "a") as f:
                f.write(json.dumps({
                    "timestamp": result["timestamp"],
                    "experiment_id": result.get("experiment_id"),
                    "commit_hash": result["commit_hash"],
                    "reason": result["reason"],
                    "success": result["success"],
                    "duration_ms": result["duration_ms"],
                    "error": result.get("error")
                }) + "\n")
        except IOError as e:
            print(f"[ERROR] Failed to write rollback log: {e}", file=sys.stderr)

    def _send_signal_alert(self, result: Dict[str, Any]) -> bool:
        """
        Send Signal alert about rollback.

        Args:
            result: Rollback result dictionary.

        Returns:
            True if alert sent successfully, False otherwise.
        """
        try:
            # Format alert message
            commit = result["commit_hash"][:8]  # Short hash
            reason = result["reason"]
            exp_id = result.get("experiment_id", "unknown")
            status = "SUCCESS" if result["success"] else "FAILED"

            message = f"ROLLBACK: {reason}\nCommit: {commit}\nExperiment: {exp_id}\nStatus: {status}"

            # Send via gateway API
            data = json.dumps({
                "recipient": SIGNAL_RECIPIENT,
                "message": f"🔄 {message}"
            }).encode()

            req = urllib.request.Request(
                SIGNAL_API_URL,
                data=data,
                headers={"Content-Type": "application/json"}
            )

            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    return True

        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            print(f"[WARN] Failed to send Signal alert: {e}", file=sys.stderr)
        except Exception as e:
            print(f"[WARN] Signal alert error: {e}", file=sys.stderr)

        return False

    def _log_to_neo4j(self, result: Dict[str, Any]) -> bool:
        """
        Create RollbackEvent node in Neo4j.

        Args:
            result: Rollback result dictionary.

        Returns:
            True if logged successfully, False otherwise.
        """
        if not self.neo4j_available:
            return False

        if not NEO4J_PASSWORD:
            print("[WARN] NEO4J_PASSWORD not set - skipping Neo4j logging", file=sys.stderr)
            return False

        try:
            from neo4j_task_tracker import neo4j_session

            with neo4j_session() as session:
                # Create RollbackEvent node
                query = """
                CREATE (r:RollbackEvent {
                    commit_hash: $commit_hash,
                    reason: $reason,
                    experiment_id: $exp_id,
                    success: $success,
                    duration_ms: $duration_ms,
                    error: $error,
                    timestamp: datetime($timestamp),
                    logged_at: datetime()
                })
                RETURN id(r) as event_id
                """

                session.run(
                    query,
                    commit_hash=result["commit_hash"],
                    reason=result["reason"],
                    exp_id=result.get("experiment_id"),
                    success=result["success"],
                    duration_ms=result["duration_ms"],
                    error=result.get("error"),
                    timestamp=result["timestamp"]
                )

                # Link to Experiment node if experiment_id provided
                if result.get("experiment_id"):
                    link_query = """
                    MATCH (r:RollbackEvent {commit_hash: $commit_hash, timestamp: datetime($timestamp)})
                    MATCH (e:Experiment {experiment_id: $exp_id})
                    MERGE (e)-[:ROLLED_BACK]->(r)
                    """
                    session.run(
                        link_query,
                        commit_hash=result["commit_hash"],
                        timestamp=result["timestamp"],
                        exp_id=result["experiment_id"]
                    )

            return True

        except Exception as e:
            print(f"[WARN] Failed to log to Neo4j: {e}", file=sys.stderr)
            return False

    def get_rollback_history(self, limit: int = 10) -> list:
        """
        Get recent rollback history from JSONL log.

        Args:
            limit: Maximum number of entries to return.

        Returns:
            List of rollback event dictionaries.
        """
        history = []
        log_path = self.log_dir / "rollback.jsonl"

        if not log_path.exists():
            return history

        try:
            with open(log_path) as f:
                for line in f:
                    if line.strip():
                        try:
                            history.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass

            # Return most recent entries (in reverse order)
            return history[-limit:][::-1] if len(history) > limit else history[::-1]

        except IOError:
            return []


# =============================================================================
# CLI
# =============================================================================

def main():
    """CLI entry point for rollback manager."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Rollback Manager — Automatic regression detection and git revert"
    )
    parser.add_argument("--check", action="store_true", help="Check if rollback needed")
    parser.add_argument("--metrics", help="JSON file with current metrics")
    parser.add_argument("--rollback", action="store_true", help="Execute rollback")
    parser.add_argument("--commit", help="Commit hash to revert")
    parser.add_argument("--reason", help="Reason for rollback")
    parser.add_argument("--experiment-id", help="Associated experiment ID")
    parser.add_argument("--test", action="store_true", help="Run simulated regression test")
    parser.add_argument("--baseline", help="Set baseline metrics from JSON file")

    args = parser.parse_args()

    manager = RollbackManager()

    # Handle --baseline: update baseline from file
    if args.baseline:
        try:
            with open(args.baseline) as f:
                baseline = json.load(f)
                manager.baseline_metrics = baseline
                print(f"✓ Baseline metrics updated: {baseline}")
                return 0
        except (IOError, json.JSONDecodeError) as e:
            print(f"Error loading baseline: {e}", file=sys.stderr)
            return 1

    # Handle --test: Run simulated regression test
    if args.test:
        print("Running simulated regression test...")

        # Test 1: Quality regression (>5%)
        needs_rollback, reason = manager.check_rollback_needed({
            "quality": 0.65,  # 9.7% below baseline 0.72
            "error_rate": 0.05,
            "duration_ms": 300
        })
        print(f"Test 1 (Quality regression): needs_rollback={needs_rollback}, reason={reason}")
        assert needs_rollback, "Quality regression should trigger rollback"
        assert "quality_regression" in reason, "Reason should mention quality"

        # Test 2: Error rate spike (>2x)
        needs_rollback, reason = manager.check_rollback_needed({
            "quality": 0.72,
            "error_rate": 0.15,  # 3x baseline 0.05
            "duration_ms": 300
        })
        print(f"Test 2 (Error rate spike): needs_rollback={needs_rollback}, reason={reason}")
        assert needs_rollback, "Error rate spike should trigger rollback"
        assert "error_rate" in reason, "Reason should mention error rate"

        # Test 3: Duration spike (>50%)
        needs_rollback, reason = manager.check_rollback_needed({
            "quality": 0.72,
            "error_rate": 0.05,
            "duration_ms": 500  # 66% above baseline 300
        })
        print(f"Test 3 (Duration spike): needs_rollback={needs_rollback}, reason={reason}")
        assert needs_rollback, "Duration spike should trigger rollback"
        assert "duration_spike" in reason, "Reason should mention duration"

        # Test 4: No rollback needed (good metrics)
        needs_rollback, reason = manager.check_rollback_needed({
            "quality": 0.75,  # Better than baseline
            "error_rate": 0.04,  # Better than baseline
            "duration_ms": 280  # Better than baseline
        })
        print(f"Test 4 (Good metrics): needs_rollback={needs_rollback}, reason={reason}")
        assert not needs_rollback, "Good metrics should not trigger rollback"

        print("✓ All tests passed!")
        return 0

    # Handle --check: Check if rollback needed
    if args.check:
        if not args.metrics:
            # Use sample metrics if none provided
            metrics = {
                "quality": 0.68,
                "error_rate": 0.06,
                "duration_ms": 320
            }
        else:
            with open(args.metrics) as f:
                metrics = json.load(f)

        needs_rollback, reason = manager.check_rollback_needed(metrics)

        print(f"Needs rollback: {needs_rollback}")
        print(f"Reason: {reason}")
        print(f"Baseline: {manager.baseline_metrics}")
        print(f"Current: {metrics}")

        return 0

    # Handle --rollback: Execute rollback
    if args.rollback:
        if not args.commit:
            print("Error: --commit required for rollback", file=sys.stderr)
            return 1

        if not args.reason:
            print("Error: --reason required for rollback", file=sys.stderr)
            return 1

        result = manager.execute_rollback(
            commit_hash=args.commit,
            reason=args.reason,
            experiment_id=args.experiment_id
        )

        print(f"Rollback result: {json.dumps(result, indent=2)}")
        return 0 if result["success"] else 1

    # Default: Show help
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
