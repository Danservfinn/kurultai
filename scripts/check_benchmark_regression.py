#!/usr/bin/env python3
"""
Benchmark Regression Checker

Compares benchmark results against baseline to detect performance regressions.
Usage: python scripts/check_benchmark_regression.py output.json
"""

import json
import sys
from pathlib import Path


def load_benchmark_results(file_path: str) -> dict:
    """Load benchmark results from JSON file."""
    with open(file_path, "r") as f:
        data = json.load(f)
    return data


def check_regression(results: dict, baseline_file: str = None, threshold: float = 1.2) -> dict:
    """Check benchmark results for regressions.

    Args:
        results: Current benchmark results
        baseline_file: Optional baseline file to compare against
        threshold: Regression threshold (e.g., 1.2 = 20% slower)

    Returns:
        Dictionary with regression status and details
    """
    if baseline_file:
        baseline = load_benchmark_results(baseline_file)
    else:
        baseline = {}

    regressions = []
    improvements = []

    # Extract benchmark data from pytest-benchmark format
    benchmarks = results.get("benchmarks", {})

    for name, data in benchmarks.items():
        if "stats" in data and "stddev" in data["stats"]:
            current_mean = data["stats"]["mean"]
            current_stddev = data["stats"]["stddev"]

            if name in baseline:
                baseline_mean = baseline[name]["stats"]["mean"]
                ratio = current_mean / baseline_mean if baseline_mean > 0 else 1.0

                if ratio > threshold:
                    regressions.append({
                        "name": name,
                        "baseline": baseline_mean,
                        "current": current_mean,
                        "ratio": ratio,
                        "regression_percent": (ratio - 1) * 100,
                    })
                elif ratio < 1.0:
                    improvements.append({
                        "name": name,
                        "baseline": baseline_mean,
                        "current": current_mean,
                        "ratio": ratio,
                        "improvement_percent": (1 - ratio) * 100,
                    })

    return {
        "has_regressions": len(regressions) > 0,
        "regressions": regressions,
        "improvements": improvements,
        "threshold": threshold,
        "status": "FAILED" if regressions else "PASSED",
    }


def print_report(check_result: dict):
    """Print regression check report."""
    print("\n" + "=" * 60)
    print("BENCHMARK REGRESSION CHECK")
    print("=" * 60)

    if check_result["regressions"]:
        print(f"\n❌ REGRESSIONS DETECTED (threshold: {check_result['threshold'] * 100:.0f}%)")
        print("\nRegressions:")
        for reg in check_result["regressions"]:
            print(f"  - {reg['name']}")
            print(f"    Baseline: {reg['baseline']:.4f}s")
            print(f"    Current:  {reg['current']:.4f}s")
            print(f"    Ratio:    {reg['ratio']:.2f}x")
            print(f"    Change:   +{reg['regression_percent']:.1f}%")
    else:
        print("\n✅ NO REGRESSIONS DETECTED")

    if check_result["improvements"]:
        print(f"\n✨ IMPROVEMENTS:")
        for imp in check_result["improvements"]:
            print(f"  - {imp['name']}: -{imp['improvement_percent']:.1f}%")

    print("\n" + "=" * 60)
    print(f"Status: {check_result['status']}")
    print("=" * 60 + "\n")

    return check_result["status"]


def main():
    if len(sys.argv) < 2:
        print("Usage: python check_benchmark_regression.py <results.json> [baseline.json]")
        sys.exit(1)

    results_file = sys.argv[1]
    baseline_file = sys.argv[2] if len(sys.argv) > 2 else None

    results = load_benchmark_results(results_file)
    check_result = check_regression(results, baseline_file)

    status = print_report(check_result)

    sys.exit(0 if status == "PASSED" else 1)


if __name__ == "__main__":
    main()
