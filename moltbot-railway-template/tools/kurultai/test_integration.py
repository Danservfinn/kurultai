#!/usr/bin/env python3
"""
Test Integration - Run tests as part of unified heartbeat.

Integrates test_runner_orchestrator.py into the heartbeat system with
token budget enforcement and result tracking.

Usage:
    from test_integration import HeartbeatTestRunner
    runner = HeartbeatTestRunner(project_root)
    result = await runner.run_smoke_tests()
    result = await runner.run_full_tests()
"""

import json
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("kurultai.test_integration")


@dataclass
class TestRunResult:
    """Result of a test run."""
    phase: str
    status: str  # "passed", "failed", "timeout", "error"
    passed: int
    failed: int
    errors: int
    skipped: int
    duration_seconds: float
    exit_code: int
    report_file: Optional[str] = None
    findings: Dict[str, Any] = field(default_factory=dict)
    output_preview: str = ""


class HeartbeatTestRunner:
    """Run tests within heartbeat token budgets."""

    def __init__(self, project_root: Path, output_dir: Optional[Path] = None):
        self.project_root = project_root
        self.output_dir = output_dir or project_root / "data" / "test_results"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Find test runner script
        self.test_runner = project_root / "tools" / "kurultai" / "test_runner_orchestrator.py"
        if not self.test_runner.exists():
            logger.warning(f"Test runner not found at {self.test_runner}")
            self.test_runner = None

    async def run_smoke_tests(self, timeout: int = 300) -> Dict[str, Any]:
        """
        Run quick smoke tests (~5 min budget).

        Runs integration tests only, no remediation.
        """
        if not self.test_runner:
            return {
                "summary": "Smoke tests: test runner not available",
                "tokens_used": 50,
                "data": {"error": "test_runner_orchestrator.py not found"}
            }

        start_time = datetime.now(timezone.utc)

        try:
            result = subprocess.run(
                [sys.executable, str(self.test_runner), "--phase", "integration", "--no-remediate"],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.project_root)
            )

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Try to parse JSON from output
            output_data = self._parse_json_output(result.stdout)

            # Find most recent report file
            report_file = self._find_latest_report()

            status = "passed" if result.returncode == 0 else "failed"

            # Count findings if available
            critical = 0
            high = 0
            if output_data and "findings" in output_data:
                critical = output_data["findings"].get("critical", 0)
                high = output_data["findings"].get("high", 0)

            summary = f"Smoke tests: {status.upper()}"
            if critical > 0:
                summary += f", {critical} critical"
            if high > 0:
                summary += f", {high} high"

            return {
                "summary": summary,
                "tokens_used": 800,
                "data": {
                    "status": status,
                    "exit_code": result.returncode,
                    "duration_seconds": duration,
                    "critical_findings": critical,
                    "high_findings": high,
                    "report_file": str(report_file) if report_file else None,
                    "output_preview": result.stdout[-500:] if len(result.stdout) > 500 else result.stdout
                }
            }

        except subprocess.TimeoutExpired:
            return {
                "summary": f"Smoke tests: TIMEOUT after {timeout}s",
                "tokens_used": 800,
                "data": {"error": "timeout", "timeout_seconds": timeout}
            }

        except Exception as e:
            logger.exception("Smoke tests failed")
            return {
                "summary": f"Smoke tests error: {e}",
                "tokens_used": 100,
                "data": {"error": str(e)}
            }

    async def run_full_tests(self, timeout: int = 900) -> Dict[str, Any]:
        """
        Run full test suite (~15 min budget).

        Runs all test phases with remediation enabled.
        """
        if not self.test_runner:
            return {
                "summary": "Full tests: test runner not available",
                "tokens_used": 50,
                "data": {"error": "test_runner_orchestrator.py not found"}
            }

        start_time = datetime.now(timezone.utc)

        try:
            result = subprocess.run(
                [sys.executable, str(self.test_runner), "--phase", "all"],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.project_root)
            )

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Parse JSON output
            output_data = self._parse_json_output(result.stdout)

            # Find report file
            report_file = self._find_latest_report()

            # Load report if available
            report_data = None
            if report_file:
                try:
                    with open(report_file) as f:
                        report_data = json.load(f)
                except Exception as e:
                    logger.warning(f"Failed to load report: {e}")

            # Extract findings
            findings = report_data.get("findings", {}) if report_data else {}
            critical = findings.get("critical", 0)
            high = findings.get("high", 0)

            # Get summary stats
            summary_stats = report_data.get("summary", {}) if report_data else {}
            pass_rate = summary_stats.get("pass_rate", 0)
            overall_status = summary_stats.get("overall_status", "unknown")

            test_summary = f"Full tests: {overall_status.upper()}, {pass_rate:.1f}% pass rate"
            if critical > 0:
                test_summary += f", {critical} critical findings"

            return {
                "summary": test_summary,
                "tokens_used": 1500,
                "data": {
                    "status": overall_status,
                    "exit_code": result.returncode,
                    "pass_rate": pass_rate,
                    "duration_seconds": duration,
                    "critical_findings": critical,
                    "high_findings": high,
                    "report_file": str(report_file) if report_file else None,
                    "phases": summary_stats.get("total_phases", 0),
                    "total_tests": summary_stats.get("total_tests", 0)
                }
            }

        except subprocess.TimeoutExpired:
            return {
                "summary": f"Full tests: TIMEOUT after {timeout}s",
                "tokens_used": 1500,
                "data": {"error": "timeout", "timeout_seconds": timeout}
            }

        except Exception as e:
            logger.exception("Full tests failed")
            return {
                "summary": f"Full tests error: {e}",
                "tokens_used": 200,
                "data": {"error": str(e)}
            }

    async def run_specific_category(self, category: str, timeout: int = 300) -> Dict[str, Any]:
        """
        Run tests for a specific category.

        Categories: security, performance, integration, concurrent
        """
        if not self.test_runner:
            return {
                "summary": f"{category} tests: test runner not available",
                "tokens_used": 50,
                "data": {"error": "test_runner_orchestrator.py not found"}
            }

        # Map categories to pytest markers
        marker_map = {
            "security": "security",
            "performance": "performance",
            "integration": "integration",
            "concurrent": "concurrent",
            "e2e": "e2e"
        }

        marker = marker_map.get(category, category)

        start_time = datetime.now(timezone.utc)

        try:
            # Run pytest directly for specific markers
            cmd = [
                sys.executable, "-m", "pytest",
                "-v", "-m", marker,
                "--tb=short",
                "-x"  # Stop on first failure
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.project_root)
            )

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Parse basic results
            passed = result.stdout.count(" PASSED ")
            failed = result.stdout.count(" FAILED ")
            errors = result.stdout.count(" ERROR ")

            status = "passed" if result.returncode == 0 else "failed"

            return {
                "summary": f"{category} tests: {status.upper()} ({passed} passed, {failed} failed)",
                "tokens_used": 600,
                "data": {
                    "category": category,
                    "status": status,
                    "passed": passed,
                    "failed": failed,
                    "errors": errors,
                    "duration_seconds": duration,
                    "exit_code": result.returncode
                }
            }

        except subprocess.TimeoutExpired:
            return {
                "summary": f"{category} tests: TIMEOUT after {timeout}s",
                "tokens_used": 600,
                "data": {"error": "timeout", "timeout_seconds": timeout}
            }

        except Exception as e:
            logger.exception(f"{category} tests failed")
            return {
                "summary": f"{category} tests error: {e}",
                "tokens_used": 100,
                "data": {"error": str(e)}
            }

    def _parse_json_output(self, stdout: str) -> Optional[Dict]:
        """Try to parse JSON from stdout."""
        lines = stdout.strip().split('\n')
        for line in reversed(lines):
            line = line.strip()
            if line.startswith('{') or line.startswith('['):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        return None

    def _find_latest_report(self) -> Optional[Path]:
        """Find the most recent test report."""
        if not self.output_dir.exists():
            return None

        reports = sorted(self.output_dir.glob("test_report_*.json"), reverse=True)
        return reports[0] if reports else None

    def get_recent_reports(self, count: int = 5) -> List[Dict[str, Any]]:
        """Get metadata for recent test reports."""
        if not self.output_dir.exists():
            return []

        reports = sorted(self.output_dir.glob("test_report_*.json"), reverse=True)[:count]

        results = []
        for report_file in reports:
            try:
                with open(report_file) as f:
                    data = json.load(f)

                results.append({
                    "file": str(report_file),
                    "timestamp": data.get("timestamp"),
                    "status": data.get("summary", {}).get("overall_status"),
                    "pass_rate": data.get("summary", {}).get("pass_rate"),
                    "critical_findings": data.get("findings", {}).get("critical", 0)
                })
            except Exception as e:
                logger.warning(f"Failed to load report {report_file}: {e}")

        return results


# ============================================================================
# CLI for testing
# ============================================================================

def main():
    """CLI for testing test integration."""
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Test integration runner")
    parser.add_argument("operation", choices=["smoke", "full", "category", "recent"])
    parser.add_argument("--category", help="Category for category operation")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--timeout", type=int, default=300)

    args = parser.parse_args()

    runner = HeartbeatTestRunner(args.project_root)

    async def run():
        if args.operation == "smoke":
            result = await runner.run_smoke_tests(timeout=args.timeout)
            print(json.dumps(result, indent=2))

        elif args.operation == "full":
            result = await runner.run_full_tests(timeout=args.timeout)
            print(json.dumps(result, indent=2))

        elif args.operation == "category":
            if not args.category:
                print("--category required")
                return
            result = await runner.run_specific_category(args.category, timeout=args.timeout)
            print(json.dumps(result, indent=2))

        elif args.operation == "recent":
            reports = runner.get_recent_reports()
            print(json.dumps(reports, indent=2))

    asyncio.run(run())


if __name__ == "__main__":
    main()
