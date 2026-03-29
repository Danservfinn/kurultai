#!/usr/bin/env python3
"""
Anomaly Detector — Baseline-based Anomaly Detection
Learns normal error patterns and detects deviations (2+ sigma)
"""
import json
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
import statistics

def load_baseline_history(tick_file: str, days: int = 7) -> List[Dict]:
    """Load tick history for baseline learning"""
    ticks = []
    cutoff = datetime.now() - timedelta(days=days)

    try:
        with open(tick_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    tick = json.loads(line)
                    epoch = tick.get("epoch", 0)
                    tick_time = datetime.fromtimestamp(epoch)

                    # Only include ticks within the time window
                    if tick_time > cutoff:
                        ticks.append(tick)
                except (json.JSONDecodeError, ValueError):
                    continue
    except FileNotFoundError:
        pass

    return ticks

def calculate_time_of_day_baseline(ticks: List[Dict]) -> Dict[int, Dict]:
    """Calculate baseline statistics per hour of day"""
    hourly_data = {}  # hour -> list of error counts

    for tick in ticks:
        try:
            epoch = tick.get("epoch", 0)
            tick_time = datetime.fromtimestamp(epoch)
            hour = tick_time.hour
            errors_1h = tick.get("errors", {}).get("last_1h", 0)

            if hour not in hourly_data:
                hourly_data[hour] = []
            hourly_data[hour].append(errors_1h)
        except (ValueError, OSError):
            continue

    # Calculate stats per hour
    baseline = {}
    for hour, values in hourly_data.items():
        if len(values) >= 3:  # Need at least 3 samples
            baseline[hour] = {
                "mean": statistics.mean(values),
                "stdev": statistics.stdev(values) if len(values) > 1 else 0,
                "median": statistics.median(values),
                "min": min(values),
                "max": max(values),
                "samples": len(values)
            }

    return baseline

def detect_anomaly(current_errors: int, baseline: Dict, current_hour: int) -> Dict:
    """Detect if current error rate is anomalous"""
    if current_hour not in baseline:
        return {
            "is_anomaly": False,
            "reason": "insufficient_baseline_data"
        }

    hour_baseline = baseline[current_hour]
    mean = hour_baseline["mean"]
    stdev = hour_baseline["stdev"]

    # Calculate z-score (how many standard deviations from mean)
    if stdev > 0:
        z_score = (current_errors - mean) / stdev
    else:
        z_score = 0

    # Anomaly if 2+ sigma deviation
    is_anomaly = abs(z_score) >= 2.0

    # Determine severity
    if abs(z_score) >= 3.0:
        severity = "CRITICAL"
    elif abs(z_score) >= 2.0:
        severity = "HIGH"
    elif abs(z_score) >= 1.5:
        severity = "MODERATE"
    else:
        severity = "NORMAL"

    return {
        "is_anomaly": is_anomaly,
        "z_score": round(z_score, 2),
        "severity": severity,
        "current_errors": current_errors,
        "baseline_mean": round(mean, 1),
        "baseline_stdev": round(stdev, 1),
        "deviation_from_mean": round(current_errors - mean, 1),
        "baseline_samples": hour_baseline["samples"]
    }

def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: anomaly-detector.py <ticks.jsonl> <current_errors_1h>"}))
        sys.exit(1)

    tick_file = sys.argv[1]
    current_errors = int(sys.argv[2])

    ticks = load_baseline_history(tick_file, days=7)

    if len(ticks) < 50:  # Need reasonable sample size
        print(json.dumps({
            "error": "insufficient_data",
            "message": f"Only {len(ticks)} ticks available, need at least 50 for reliable baseline"
        }))
        sys.exit(0)  # Not an error, just not ready yet

    baseline = calculate_time_of_day_baseline(ticks)
    current_hour = datetime.now().hour

    detection = detect_anomaly(current_errors, baseline, current_hour)

    # Add context
    detection["current_hour"] = current_hour
    detection["baseline_hours_available"] = len(baseline)
    detection["total_samples_analyzed"] = len(ticks)

    # Add interpretation
    interpretation = []
    if detection["is_anomaly"]:
        if detection["z_score"] > 0:
            interpretation.append(f"ERROR RATE {detection['severity']}: {detection['deviation_from_mean']:+.1f} above baseline for this time of day")
        else:
            interpretation.append(f"ERROR RATE UNUSUALLY LOW: {detection['deviation_from_mean']:+.1f} below baseline (good!)")
    else:
        interpretation.append(f"Error rate within normal range for this time of day (baseline: {detection['baseline_mean']:.1f} ± {detection['baseline_stdev']:.1f})")

    detection["interpretation"] = interpretation

    print(json.dumps(detection, indent=2))

if __name__ == "__main__":
    main()
