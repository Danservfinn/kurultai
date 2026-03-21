#!/usr/bin/env python3
"""
Eval Dashboard — Runs all evaluation metrics and outputs a formatted report.

Usage:
    python3 eval_dashboard.py                    # All humans
    python3 eval_dashboard.py --human UUID       # Specific human
"""

import sys
import os
import json
import time
import argparse
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_task_tracker import get_driver
from eval_identity_isolation import test_identity_isolation
from eval_context_relevance import eval_context_relevance
from eval_engagement import eval_engagement
from eval_gds_health import eval_gds_health


def run_eval_dashboard(human_id: str = None) -> dict:
    """Run complete evaluation suite."""
    t0 = time.monotonic()
    report = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "sections": {}}

    # 1. Identity isolation (always run)
    print("Running identity isolation tests...")
    try:
        isolation = test_identity_isolation()
        report["sections"]["identity_isolation"] = {
            "passed": isolation["passed"],
            "failed": isolation["failed"],
            "tests": isolation["tests"],
        }
    except Exception as e:
        report["sections"]["identity_isolation"] = {"error": str(e)}

    if human_id:
        # 2. Context relevance
        print(f"Evaluating context relevance for {human_id[:8]}...")
        try:
            relevance = eval_context_relevance(human_id)
            report["sections"]["context_relevance"] = relevance
        except Exception as e:
            report["sections"]["context_relevance"] = {"error": str(e)}

        # 3. Engagement accuracy
        print(f"Evaluating engagement decisions for {human_id[:8]}...")
        try:
            engagement = eval_engagement(human_id)
            report["sections"]["engagement"] = engagement
        except Exception as e:
            report["sections"]["engagement"] = {"error": str(e)}

        # 4. GDS health
        print(f"Checking GDS health for {human_id[:8]}...")
        try:
            gds = eval_gds_health(human_id)
            report["sections"]["gds_health"] = gds
        except Exception as e:
            report["sections"]["gds_health"] = {"error": str(e)}

    report["total_ms"] = round((time.monotonic() - t0) * 1000)
    return report


def format_report(report: dict) -> str:
    """Format report as human-readable text."""
    lines = ["=" * 60, "CONVERSATIONAL MEMORY EVALUATION REPORT", "=" * 60, ""]

    for section_name, section_data in report.get("sections", {}).items():
        lines.append(f"--- {section_name.upper()} ---")

        if "error" in section_data:
            lines.append(f"  ERROR: {section_data['error']}")
        elif section_name == "identity_isolation":
            lines.append(f"  Passed: {section_data['passed']}, Failed: {section_data['failed']}")
            for t in section_data.get("tests", []):
                status = "PASS" if t["passed"] else "FAIL"
                lines.append(f"    [{status}] {t['name']}")
        else:
            for key, value in section_data.items():
                if key not in ("queries", "tests"):
                    lines.append(f"  {key}: {value}")

        lines.append("")

    lines.append(f"Total time: {report.get('total_ms', 0)}ms")
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Eval Dashboard")
    parser.add_argument("--human", help="Human UUID for per-human evals")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)

    report = run_eval_dashboard(args.human)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(format_report(report))
