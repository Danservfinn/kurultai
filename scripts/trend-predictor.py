#!/usr/bin/env python3
"""
Trend Predictor — Predictive Analysis for Error Rate Trends
Projects when error thresholds will be hit based on current acceleration
"""
import json
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional

def load_recent_ticks(tick_file: str, count: int = 12) -> List[Dict]:
    """Load last N ticks for trend analysis"""
    ticks = []
    try:
        with open(tick_file, 'r') as f:
            lines = f.readlines()
            for line in lines[-count:]:
                line = line.strip()
                if line:
                    try:
                        ticks.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except FileNotFoundError:
        pass
    return ticks

def calculate_trend_metrics(ticks: List[Dict]) -> Dict:
    """Calculate trend acceleration and prediction"""
    if len(ticks) < 3:
        return {
            "errors_5m_current": 0,
            "errors_1h_current": 0,
            "trend_direction": "unknown",
            "acceleration": 0,
            "predicted_threshold_hits": {}
        }

    # Extract error counts
    errors_5m = [t.get("errors", {}).get("last_5m", 0) for t in ticks]
    errors_1h = [t.get("errors", {}).get("last_1h", 0) for t in ticks]
    timestamps = [t.get("epoch", 0) for t in ticks]

    # Calculate rate of change (errors per tick)
    if len(errors_5m) >= 2:
        changes_5m = [errors_5m[i] - errors_5m[i-1] for i in range(1, len(errors_5m))]
        avg_change = sum(changes_5m) / len(changes_5m) if changes_5m else 0
    else:
        avg_change = 0

    # Calculate acceleration (change in rate of change)
    if len(changes_5m) >= 2:
        accelerations = [changes_5m[i] - changes_5m[i-1] for i in range(1, len(changes_5m))]
        acceleration = sum(accelerations) / len(accelerations) if accelerations else 0
    else:
        acceleration = 0

    # Determine trend direction
    if avg_change > 1:
        trend_direction = "rising"
    elif avg_change < -1:
        trend_direction = "falling"
    else:
        trend_direction = "stable"

    # Predict when thresholds will be hit
    predicted_threshold_hits = {}
    current_errors_5m = errors_5m[-1] if errors_5m else 0
    current_errors_1h = errors_1h[-1] if errors_1h else 0

    # Thresholds to predict (CAUTION, WARNING, DEGRADED, CRITICAL)
    thresholds = {
        "CAUTION": 50,
        "WARNING": 75,
        "DEGRADED": 150,
        "CRITICAL": 400
    }

    # Only predict if trend is rising
    if trend_direction == "rising" and avg_change > 0:
        for level, threshold in thresholds.items():
            if current_errors_1h < threshold:
                # Linear extrapolation: when will we hit this threshold?
                if avg_change > 0:
                    ticks_to_threshold = (threshold - current_errors_1h) / avg_change
                    minutes_to_threshold = ticks_to_threshold * 5  # Each tick = 5 minutes
                    predicted_threshold_hits[level] = {
                        "threshold": threshold,
                        "current": current_errors_1h,
                        "ticks_until": int(ticks_to_threshold),
                        "minutes_until": int(minutes_to_threshold),
                        "predicted_time": datetime.now() + timedelta(minutes=minutes_to_threshold)
                    }

    return {
        "errors_5m_current": current_errors_5m,
        "errors_1h_current": current_errors_1h,
        "trend_direction": trend_direction,
        "avg_change_per_tick": round(avg_change, 2),
        "acceleration": round(acceleration, 2),
        "predicted_threshold_hits": predicted_threshold_hits,
        "sample_count": len(ticks)
    }

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: trend-predictor.py <ticks.jsonl>"}))
        sys.exit(1)

    tick_file = sys.argv[1]
    ticks = load_recent_ticks(tick_file)

    if not ticks:
        print(json.dumps({"error": "No ticks found"}))
        sys.exit(1)

    metrics = calculate_trend_metrics(ticks)

    # Add human-readable interpretation
    interpretation = []
    if metrics["trend_direction"] == "rising":
        if metrics["acceleration"] > 1:
            interpretation.append("ACCELERATING RISING TREND")
        elif metrics["acceleration"] < -1:
            interpretation.append("DECELERATING (still rising but slowing)")
        else:
            interpretation.append("STEADY RISING TREND")

        # Check if approaching thresholds
        for level, hit_info in metrics["predicted_threshold_hits"].items():
            if hit_info["minutes_until"] < 30:  # Within 30 minutes
                interpretation.append(f"WILL HIT {level} IN ~{hit_info['minutes_until']}min")
    elif metrics["trend_direction"] == "falling":
        interpretation.append("FALLING TREED (improving)")
    else:
        interpretation.append("STABLE")

    metrics["interpretation"] = interpretation

    print(json.dumps(metrics, indent=2, default=str))

if __name__ == "__main__":
    main()
