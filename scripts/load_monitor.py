#!/usr/bin/env python3
"""
load_monitor.py — Real-time load monitoring with trend detection.

Tracks system load over time, analyzes trends, and predicts potential overload.

Usage:
    from load_monitor import LoadMonitor

    monitor = LoadMonitor()
    monitor.record_sample()
    trend = monitor.get_load_trend()
    will_overload, reason = monitor.predict_overload(horizon_minutes=10)
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Tuple, List, Dict, Optional

# Configuration
SAMPLE_INTERVAL_S = 60      # Sample every minute
HISTORY_SIZE = 60           # Keep 1 hour of history (60 samples * 60s)
LOAD_HISTORY_PATH = Path("/Users/kublai/.openclaw/agents/main/logs/load-history.jsonl")

# Import from task_intake for load calculations
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from task_intake import get_all_agent_queue_depths, calculate_system_load_factor
    TASK_INTAKE_AVAILABLE = True
except ImportError:
    TASK_INTAKE_AVAILABLE = False


class LoadMonitor:
    """Real-time load monitoring with trend detection and overload prediction.

    Maintains a sliding window of load samples (load_factor + queue depths).
    Provides trend analysis (increasing/decreasing/stable) and can predict
    overload within a given time horizon using linear extrapolation.
    """

    def __init__(self, history_path: Path = LOAD_HISTORY_PATH, history_size: int = HISTORY_SIZE):
        """Initialize the load monitor.

        Args:
            history_path: Path to JSONL file for persistent history storage
            history_size: Maximum number of samples to keep in memory
        """
        self.history_path = history_path
        self.history_size = history_size
        self.history: List[Tuple[float, float, Dict[str, int]]] = []  # [(timestamp, load_factor, depths)]

        # Load existing history from disk if available
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        """Load recent history from disk."""
        if not self.history_path.exists():
            return

        try:
            with open(self.history_path, 'r') as f:
                lines = f.readlines()

            # Load last HISTORY_SIZE entries
            for line in lines[-self.history_size:]:
                try:
                    data = json.loads(line.strip())
                    self.history.append((
                        data.get('timestamp', 0),
                        data.get('load_factor', 0.0),
                        data.get('depths', {})
                    ))
                except (json.JSONDecodeError, KeyError):
                    continue
        except Exception:
            # If loading fails, start fresh
            self.history = []

    def record_sample(self) -> Optional[Dict]:
        """Record current load state.

        Captures the current load factor and queue depths for all agents.
        Persists to disk and trims history to HISTORY_SIZE.

        Returns:
            Dict with timestamp, load_factor, and depths if successful, None otherwise
        """
        if not TASK_INTAKE_AVAILABLE:
            return None

        try:
            load_factor = calculate_system_load_factor()
            depths = get_all_agent_queue_depths()
            timestamp = time.time()

            sample = (timestamp, load_factor, depths)
            self.history.append(sample)

            # Trim to history size
            if len(self.history) > self.history_size:
                self.history = self.history[-self.history_size:]

            # Persist to disk
            self._persist_sample(timestamp, load_factor, depths)

            return {
                'timestamp': timestamp,
                'load_factor': load_factor,
                'depths': depths
            }
        except Exception:
            return None

    def _persist_sample(self, timestamp: float, load_factor: float, depths: Dict[str, int]) -> None:
        """Append a sample to the history file."""
        try:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)

            record = {
                'timestamp': timestamp,
                'datetime': datetime.fromtimestamp(timestamp).isoformat(),
                'load_factor': load_factor,
                'depths': depths
            }

            with open(self.history_path, 'a') as f:
                f.write(json.dumps(record) + '\n')
        except Exception:
            pass

    def get_current_load(self) -> float:
        """Get the most recent load factor.

        Returns:
            Current load factor (0.0 = idle, 1.0 = saturated) or 0.0 if no data
        """
        if not self.history:
            return 0.0
        return self.history[-1][1]

    def get_load_trend(self) -> str:
        """Analyze load trend over recent history.

        Compares the average load of the last 5 samples with the average of
        the previous 5 samples (if available).

        Returns:
            'increasing', 'decreasing', 'stable', or 'unknown'
        """
        if len(self.history) < 5:
            return 'unknown'

        # Get recent loads (last 5 samples)
        recent_loads = [h[1] for h in self.history[-5:]]

        # Get older loads (previous 5 samples if available)
        if len(self.history) >= 10:
            older_loads = [h[1] for h in self.history[-10:-5]]
        else:
            older_loads = recent_loads

        recent_avg = sum(recent_loads) / len(recent_loads)
        older_avg = sum(older_loads) / len(older_loads)

        # Threshold for significant change (10%)
        threshold = 0.1

        if recent_avg > older_avg + threshold:
            return 'increasing'
        elif recent_avg < older_avg - threshold:
            return 'decreasing'
        else:
            return 'stable'

    def predict_overload(self, horizon_minutes: int = 10) -> Tuple[bool, str]:
        """Predict if system will be overloaded in N minutes.

        Uses linear extrapolation from the last 10 samples to predict
        future load. Overload is defined as load_factor > 0.8.

        Args:
            horizon_minutes: Time horizon for prediction (default 10 minutes)

        Returns:
            Tuple of (will_overload: bool, explanation: str)
        """
        if len(self.history) < 10:
            return False, "Insufficient data"

        # Get load factors from last 10 samples
        loads = [h[1] for h in self.history[-10:]]

        # Calculate linear trend (slope)
        # slope = (last - first) / number of intervals
        slope = (loads[-1] - loads[0]) / len(loads)

        # Predict load at horizon
        # Each sample is ~1 minute apart (SAMPLE_INTERVAL_S)
        samples_ahead = horizon_minutes * 60 // SAMPLE_INTERVAL_S
        predicted_load = loads[-1] + slope * samples_ahead

        # Overload threshold
        OVERLOAD_THRESHOLD = 0.8

        if predicted_load > OVERLOAD_THRESHOLD:
            return True, f"Predicted load in {horizon_minutes}min: {predicted_load:.2f} (threshold: {OVERLOAD_THRESHOLD})"
        else:
            return False, f"Predicted load in {horizon_minutes}min: {predicted_load:.2f} (threshold: {OVERLOAD_THRESHOLD})"

    def get_summary(self) -> Dict:
        """Get a summary of current load state.

        Returns:
            Dict with current_load, trend, prediction, and sample count
        """
        current = self.get_current_load()
        trend = self.get_load_trend()
        will_overload, prediction = self.predict_overload()

        return {
            'current_load_factor': round(current, 3),
            'trend': trend,
            'prediction': prediction,
            'sample_count': len(self.history),
            'overload_predicted': will_overload
        }


# Convenience function for quick checks
def get_load_summary() -> Dict:
    """Quick check of current load status."""
    monitor = LoadMonitor()
    monitor.record_sample()
    return monitor.get_summary()


if __name__ == '__main__':
    # CLI interface for testing
    import argparse

    parser = argparse.ArgumentParser(description='Load monitoring for Kurultai')
    parser.add_argument('--summary', action='store_true', help='Print load summary')
    parser.add_argument('--record', action='store_true', help='Record a sample')
    parser.add_argument('--trend', action='store_true', help='Show load trend')
    parser.add_argument('--predict', type=int, default=10, metavar='MINUTES',
                        help='Predict overload in N minutes (default: 10)')

    args = parser.parse_args()

    monitor = LoadMonitor()

    if args.record or not (args.summary or args.trend):
        sample = monitor.record_sample()
        if sample:
            print(f"Recorded sample: load_factor={sample['load_factor']:.3f}")

    if args.summary:
        summary = monitor.get_summary()
        print(json.dumps(summary, indent=2))

    if args.trend:
        trend = monitor.get_load_trend()
        print(f"Trend: {trend}")

    if args.predict:
        will_overload, reason = monitor.predict_overload(args.predict)
        print(f"Overload prediction ({args.predict}min): {will_overload} - {reason}")
