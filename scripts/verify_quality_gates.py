#!/usr/bin/env python3
"""
Comprehensive Code Quality Gates Verification Script

This script performs automated verification of all code quality gates including:
- Test execution with pytest
- Coverage verification (overall and per-module thresholds)
- Static analysis (ruff, black, mypy)
- Security module coverage checks

Usage:
    python scripts/verify_quality_gates.py
    python scripts/verify_quality_gates.py --verbose --fail-fast
    python scripts/verify_quality_gates.py --skip-coverage --json-output results.json

Exit Codes:
    0 - All quality gates passed
    1 - One or more quality gates failed
    2 - Script execution error
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any


class GateStatus(Enum):
    """Status of a quality gate check."""
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    ERROR = "ERROR"


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

    @classmethod
    def disable(cls):
        """Disable all colors (for non-TTY output)."""
        for attr in dir(cls):
            if not attr.startswith("_") and attr != "disable":
                setattr(cls, attr, "")


@dataclass
class GateResult:
    """Result of a single quality gate check."""
    name: str
    status: GateStatus
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "duration_ms": round(self.duration_ms, 2),
        }


@dataclass
class QualityReport:
    """Complete quality gates report."""
    overall_status: GateStatus
    gates: List[GateResult]
    summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_status": self.overall_status.value,
            "gates": [g.to_dict() for g in self.gates],
            "summary": self.summary,
        }


class QualityGateVerifier:
    """
    Comprehensive code quality gate verifier.

    Performs all quality checks and generates detailed reports.
    """

    # Coverage thresholds
    OVERALL_COVERAGE_THRESHOLD = 80.0
    CRITICAL_MODULE_THRESHOLD = 90.0
    SECURITY_MODULE_THRESHOLD = 90.0

    # Critical modules requiring high coverage
    CRITICAL_MODULES = [
        "openclaw_memory.py",
        "tools/multi_goal_orchestration.py",
    ]

    # Security modules requiring high coverage
    SECURITY_MODULES = [
        "tools/security/privacy_boundary.py",
        "tools/security/anonymization.py",
        "tools/security/encryption.py",
        "tools/security/tokenization.py",
        "tools/security/access_control.py",
        "tools/security/injection_prevention.py",
    ]

    def __init__(
        self,
        verbose: bool = False,
        fail_fast: bool = False,
        skip_coverage: bool = False,
        json_output: Optional[str] = None,
    ):
        self.verbose = verbose
        self.fail_fast = fail_fast
        self.skip_coverage = skip_coverage
        self.json_output = json_output
        self.results: List[GateResult] = []
        self.project_root = Path(__file__).parent.parent

        # Disable colors if not TTY or JSON output
        if json_output or not sys.stdout.isatty():
            Colors.disable()

    def log(self, message: str, level: str = "info"):
        """Log a message with optional verbosity control."""
        if self.verbose or level in ("error", "warning"):
            prefix = {
                "info": f"{Colors.BLUE}[INFO]{Colors.RESET}",
                "success": f"{Colors.GREEN}[PASS]{Colors.RESET}",
                "error": f"{Colors.RED}[FAIL]{Colors.RESET}",
                "warning": f"{Colors.YELLOW}[WARN]{Colors.RESET}",
                "phase": f"{Colors.CYAN}[PHASE]{Colors.RESET}",
            }.get(level, "[INFO]")
            print(f"{prefix} {message}")

    def print_header(self, title: str):
        """Print a formatted section header."""
        width = 70
        print(f"\n{Colors.BOLD}{Colors.CYAN}{'=' * width}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}{title.center(width)}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}{'=' * width}{Colors.RESET}\n")

    def print_result(self, result: GateResult):
        """Print a gate result with color coding."""
        status_color = {
            GateStatus.PASS: Colors.GREEN,
            GateStatus.FAIL: Colors.RED,
            GateStatus.SKIP: Colors.YELLOW,
            GateStatus.ERROR: Colors.RED,
        }.get(result.status, Colors.RESET)

        status_str = f"{status_color}[{result.status.value}]{Colors.RESET}"
        print(f"  {status_str} {result.name}")

        if result.message and (self.verbose or result.status != GateStatus.PASS):
            for line in result.message.split("\n"):
                print(f"      {line}")

    def run_command(
        self,
        cmd: List[str],
        cwd: Optional[Path] = None,
        capture: bool = True,
    ) -> tuple[int, str, str]:
        """Run a shell command and return exit code, stdout, stderr."""
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd or self.project_root,
                capture_output=capture,
                text=True,
                timeout=300,  # 5 minute timeout
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out after 300 seconds"
        except Exception as e:
            return -2, "", str(e)

    def check_tool_available(self, tool: str) -> bool:
        """Check if a Python tool is available."""
        exit_code, _, _ = self.run_command(["python", "-m", tool, "--version"])
        if exit_code == 0:
            return True
        # Try alternative check
        exit_code, _, _ = self.run_command(["python", "-c", f"import {tool}"])
        return exit_code == 0

    def phase_test_execution(self) -> List[GateResult]:
        """
        Phase 1: Test Execution

        Runs full test suite with pytest and collects pass/fail counts.
        """
        self.print_header("PHASE 1: TEST EXECUTION")
        results = []

        # Check if pytest is available
        if not self.check_tool_available("pytest"):
            result = GateResult(
                name="Pytest Availability",
                status=GateStatus.ERROR,
                message="pytest is not installed. Install with: pip install pytest pytest-cov",
            )
            results.append(result)
            self.print_result(result)
            return results

        self.log("Running full test suite with pytest...", "phase")

        # Build pytest command
        cmd = [
            "python", "-m", "pytest",
            "-v",
            "--tb=short",
            "-ra",
        ]

        if not self.skip_coverage:
            cmd.extend([
                "--cov=openclaw_memory",
                "--cov=tools.multi_goal_orchestration",
                "--cov=tools.delegation_protocol",
                "--cov=tools.failover_monitor",
                "--cov=tools.notion_integration",
                "--cov=tools.backend_collaboration",
                "--cov=tools.background_synthesis",
                "--cov=tools.file_consistency",
                "--cov=tools.meta_learning",
                "--cov=tools.reflection_memory",
                "--cov=tools.security",
                "--cov-report=term-missing",
                "--cov-report=json",
            ])

        cmd.append("tests/")

        import time
        start_time = time.time()
        exit_code, stdout, stderr = self.run_command(cmd)
        duration = (time.time() - start_time) * 1000

        # Parse test results
        passed = stdout.count(" PASSED")
        failed = stdout.count(" FAILED")
        errors = stdout.count(" ERROR")
        skipped = stdout.count(" SKIPPED")

        # Check for test failures
        if exit_code == 0 and failed == 0 and errors == 0:
            result = GateResult(
                name="Test Suite Execution",
                status=GateStatus.PASS,
                message=f"All tests passed: {passed} passed, {skipped} skipped",
                details={
                    "passed": passed,
                    "failed": failed,
                    "errors": errors,
                    "skipped": skipped,
                },
                duration_ms=duration,
            )
        else:
            details = f"Exit code: {exit_code}\n"
            if failed > 0:
                details += f"Failed tests: {failed}\n"
            if errors > 0:
                details += f"Errors: {errors}\n"

            result = GateResult(
                name="Test Suite Execution",
                status=GateStatus.FAIL,
                message=f"Test failures detected:\n{details}",
                details={
                    "passed": passed,
                    "failed": failed,
                    "errors": errors,
                    "skipped": skipped,
                    "exit_code": exit_code,
                    "stderr": stderr[-1000:] if stderr else "",
                },
                duration_ms=duration,
            )

        results.append(result)
        self.print_result(result)

        return results

    def phase_coverage_verification(self) -> List[GateResult]:
        """
        Phase 2: Coverage Verification

        Checks overall coverage >= 80%
        Checks critical modules >= 90%
        Checks security modules >= 90%
        """
        self.print_header("PHASE 2: COVERAGE VERIFICATION")
        results = []

        if self.skip_coverage:
            result = GateResult(
                name="Coverage Verification",
                status=GateStatus.SKIP,
                message="Coverage verification skipped (--skip-coverage flag)",
            )
            results.append(result)
            self.print_result(result)
            return results

        # Check if coverage.json exists
        coverage_file = self.project_root / "coverage.json"
        if not coverage_file.exists():
            # Try to generate it
            self.log("Generating coverage report...", "phase")
            self.run_command([
                "python", "-m", "coverage", "json",
                "-o", "coverage.json",
            ])

        if not coverage_file.exists():
            result = GateResult(
                name="Coverage Data Availability",
                status=GateStatus.ERROR,
                message="Could not generate or find coverage.json",
            )
            results.append(result)
            self.print_result(result)
            return results

        # Parse coverage data
        try:
            with open(coverage_file) as f:
                coverage_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            result = GateResult(
                name="Coverage Data Parsing",
                status=GateStatus.ERROR,
                message=f"Failed to parse coverage.json: {e}",
            )
            results.append(result)
            self.print_result(result)
            return results

        # Check overall coverage
        overall_pct = coverage_data.get("totals", {}).get("percent_covered", 0)
        overall_pass = overall_pct >= self.OVERALL_COVERAGE_THRESHOLD

        result = GateResult(
            name=f"Overall Coverage (>= {self.OVERALL_COVERAGE_THRESHOLD}%)",
            status=GateStatus.PASS if overall_pass else GateStatus.FAIL,
            message=f"Overall coverage: {overall_pct:.2f}%",
            details={
                "threshold": self.OVERALL_COVERAGE_THRESHOLD,
                "actual": overall_pct,
                "covered_lines": coverage_data.get("totals", {}).get("covered_lines", 0),
                "missing_lines": coverage_data.get("totals", {}).get("missing_lines", 0),
            },
        )
        results.append(result)
        self.print_result(result)

        # Check critical modules
        files_coverage = coverage_data.get("files", {})

        for module in self.CRITICAL_MODULES:
            # Find the file in coverage data
            module_coverage = None
            for file_path, file_data in files_coverage.items():
                if file_path.endswith(module):
                    module_coverage = file_data
                    break

            if module_coverage is None:
                result = GateResult(
                    name=f"Critical Module: {module}",
                    status=GateStatus.ERROR,
                    message=f"Module {module} not found in coverage data",
                )
            else:
                pct = module_coverage.get("summary", {}).get("percent_covered", 0)
                passed = pct >= self.CRITICAL_MODULE_THRESHOLD
                result = GateResult(
                    name=f"Critical Module: {module} (>= {self.CRITICAL_MODULE_THRESHOLD}%)",
                    status=GateStatus.PASS if passed else GateStatus.FAIL,
                    message=f"Coverage: {pct:.2f}%",
                    details={
                        "threshold": self.CRITICAL_MODULE_THRESHOLD,
                        "actual": pct,
                        "covered_lines": module_coverage.get("summary", {}).get("covered_lines", 0),
                        "missing_lines": module_coverage.get("summary", {}).get("missing_lines", 0),
                    },
                )
            results.append(result)
            self.print_result(result)

        # Check security modules
        for module in self.SECURITY_MODULES:
            module_path = self.project_root / module
            if not module_path.exists():
                # Skip if module doesn't exist
                continue

            module_coverage = None
            for file_path, file_data in files_coverage.items():
                if file_path.endswith(module):
                    module_coverage = file_data
                    break

            if module_coverage is None:
                result = GateResult(
                    name=f"Security Module: {module}",
                    status=GateStatus.ERROR,
                    message=f"Module {module} not found in coverage data",
                )
            else:
                pct = module_coverage.get("summary", {}).get("percent_covered", 0)
                passed = pct >= self.SECURITY_MODULE_THRESHOLD
                result = GateResult(
                    name=f"Security Module: {module} (>= {self.SECURITY_MODULE_THRESHOLD}%)",
                    status=GateStatus.PASS if passed else GateStatus.FAIL,
                    message=f"Coverage: {pct:.2f}%",
                    details={
                        "threshold": self.SECURITY_MODULE_THRESHOLD,
                        "actual": pct,
                    },
                )
            results.append(result)
            if self.verbose:
                self.print_result(result)

        return results

    def phase_static_analysis(self) -> List[GateResult]:
        """
        Phase 3: Static Analysis

        Runs ruff check (zero errors required)
        Runs black --check
        Runs mypy (if config exists)
        """
        self.print_header("PHASE 3: STATIC ANALYSIS")
        results = []

        # Ruff check
        self.log("Running ruff check...", "phase")
        import time
        start_time = time.time()

        # Check if ruff is available
        if not self.check_tool_available("ruff"):
            result = GateResult(
                name="Ruff Lint Check",
                status=GateStatus.SKIP,
                message="ruff is not installed. Install with: pip install ruff",
            )
            results.append(result)
            self.print_result(result)
        else:
            exit_code, stdout, stderr = self.run_command(
                ["python", "-m", "ruff", "check", "."]
            )
            duration = (time.time() - start_time) * 1000

            if exit_code == 0:
                result = GateResult(
                    name="Ruff Lint Check",
                    status=GateStatus.PASS,
                    message="No linting errors found",
                    duration_ms=duration,
                )
            else:
                # Count errors by lines with actual error output
                error_lines = [l for l in (stdout + stderr).split("\n") if l.strip() and not l.startswith(" ")]
                error_count = len(error_lines)
                result = GateResult(
                    name="Ruff Lint Check",
                    status=GateStatus.FAIL,
                    message=f"Found {error_count} linting errors:\n{(stdout + stderr)[:500]}",
                    details={
                        "error_count": error_count,
                        "full_output": stdout + stderr,
                    },
                    duration_ms=duration,
                )
            results.append(result)
            self.print_result(result)

            if self.fail_fast and result.status == GateStatus.FAIL:
                return results

        # Black format check
        self.log("Running black format check...", "phase")
        start_time = time.time()

        # Check if black is available
        if not self.check_tool_available("black"):
            result = GateResult(
                name="Black Format Check",
                status=GateStatus.SKIP,
                message="black is not installed. Install with: pip install black",
            )
            results.append(result)
            self.print_result(result)
        else:
            exit_code, stdout, stderr = self.run_command(
                ["python", "-m", "black", "--check", "."]
            )
            duration = (time.time() - start_time) * 1000

            if exit_code == 0:
                result = GateResult(
                    name="Black Format Check",
                    status=GateStatus.PASS,
                    message="All files are properly formatted",
                    duration_ms=duration,
                )
            else:
                # Parse files that would be reformatted
                files_to_format = []
                for line in (stdout + stderr).split("\n"):
                    if "would reformat" in line:
                        files_to_format.append(line.split()[-1])

                result = GateResult(
                    name="Black Format Check",
                    status=GateStatus.FAIL,
                    message=f"{len(files_to_format)} files would be reformatted",
                    details={
                        "files_to_format": files_to_format,
                        "hint": "Run 'black .' to auto-format",
                    },
                    duration_ms=duration,
                )
            results.append(result)
            self.print_result(result)

        if self.fail_fast and result.status == GateStatus.FAIL:
            return results

        # MyPy type check (if pyproject.toml or mypy.ini exists)
        mypy_config = self.project_root / "pyproject.toml"
        mypy_ini = self.project_root / "mypy.ini"

        if not (mypy_config.exists() or mypy_ini.exists()):
            result = GateResult(
                name="MyPy Type Check",
                status=GateStatus.SKIP,
                message="No mypy configuration found (pyproject.toml or mypy.ini)",
            )
            results.append(result)
            self.print_result(result)
        elif not self.check_tool_available("mypy"):
            result = GateResult(
                name="MyPy Type Check",
                status=GateStatus.SKIP,
                message="mypy is not installed. Install with: pip install mypy",
            )
            results.append(result)
            self.print_result(result)
        else:
            self.log("Running mypy type check...", "phase")
            start_time = time.time()
            exit_code, stdout, stderr = self.run_command(
                ["python", "-m", "mypy", "."]
            )
            duration = (time.time() - start_time) * 1000

            # Parse mypy output for error count
            error_lines = [l for l in (stdout + stderr).split("\n") if ": error:" in l]
            error_count = len(error_lines)

            if exit_code == 0 and error_count == 0:
                result = GateResult(
                    name="MyPy Type Check",
                    status=GateStatus.PASS,
                    message="No type errors found",
                    duration_ms=duration,
                )
            else:
                result = GateResult(
                    name="MyPy Type Check",
                    status=GateStatus.FAIL if error_count > 0 else GateStatus.ERROR,
                    message=f"Found {error_count} type errors",
                    details={
                        "error_count": error_count,
                        "sample_errors": error_lines[:5],
                    },
                    duration_ms=duration,
                )
            results.append(result)
            self.print_result(result)

        return results

    def generate_summary(self) -> QualityReport:
        """Generate final summary report."""
        self.print_header("GATE SUMMARY REPORT")

        # Calculate statistics
        total = len(self.results)
        passed = sum(1 for r in self.results if r.status == GateStatus.PASS)
        failed = sum(1 for r in self.results if r.status == GateStatus.FAIL)
        skipped = sum(1 for r in self.results if r.status == GateStatus.SKIP)
        errors = sum(1 for r in self.results if r.status == GateStatus.ERROR)

        overall = GateStatus.PASS if failed == 0 and errors == 0 else GateStatus.FAIL

        # Print summary table
        print(f"\n{Colors.BOLD}Results Summary:{Colors.RESET}")
        print(f"  {Colors.GREEN}Passed:  {passed}{Colors.RESET}")
        print(f"  {Colors.RED}Failed:  {failed}{Colors.RESET}")
        print(f"  {Colors.YELLOW}Skipped: {skipped}{Colors.RESET}")
        print(f"  {Colors.RED}Errors:  {errors}{Colors.RESET}")
        print(f"  {Colors.BOLD}Total:   {total}{Colors.RESET}")

        # Overall status
        status_color = Colors.GREEN if overall == GateStatus.PASS else Colors.RED
        print(f"\n{Colors.BOLD}Overall Status: {status_color}{overall.value}{Colors.RESET}")

        # List failures if any
        if failed > 0 or errors > 0:
            print(f"\n{Colors.RED}{Colors.BOLD}Failed Gates:{Colors.RESET}")
            for result in self.results:
                if result.status in (GateStatus.FAIL, GateStatus.ERROR):
                    print(f"  - {result.name}: {result.message[:100]}")

        summary = {
            "total_gates": total,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "errors": errors,
            "pass_rate": round(passed / total * 100, 2) if total > 0 else 0,
        }

        return QualityReport(
            overall_status=overall,
            gates=self.results,
            summary=summary,
        )

    def save_json_report(self, report: QualityReport):
        """Save report to JSON file."""
        if self.json_output:
            output_path = Path(self.json_output)
            with open(output_path, "w") as f:
                json.dump(report.to_dict(), f, indent=2)
            print(f"\n{Colors.BLUE}JSON report saved to: {output_path}{Colors.RESET}")

    def run(self) -> int:
        """
        Run all quality gate phases.

        Returns:
            Exit code: 0 for success, 1 for failures, 2 for errors
        """
        print(f"{Colors.BOLD}{Colors.MAGENTA}")
        print("╔══════════════════════════════════════════════════════════════════════╗")
        print("║         CODE QUALITY GATES VERIFICATION                              ║")
        print("╚══════════════════════════════════════════════════════════════════════╝")
        print(f"{Colors.RESET}")

        print(f"Project root: {self.project_root}")
        print(f"Verbose: {self.verbose}")
        print(f"Fail-fast: {self.fail_fast}")
        print(f"Skip coverage: {self.skip_coverage}")
        if self.json_output:
            print(f"JSON output: {self.json_output}")

        try:
            # Phase 1: Test Execution
            phase1_results = self.phase_test_execution()
            self.results.extend(phase1_results)

            if self.fail_fast and any(
                r.status == GateStatus.FAIL for r in phase1_results
            ):
                self.log("Fail-fast enabled, stopping after test failures", "warning")

            # Phase 2: Coverage Verification
            if not (self.fail_fast and any(r.status == GateStatus.FAIL for r in phase1_results)):
                phase2_results = self.phase_coverage_verification()
                self.results.extend(phase2_results)

            # Phase 3: Static Analysis
            if not (self.fail_fast and any(r.status == GateStatus.FAIL for r in self.results)):
                phase3_results = self.phase_static_analysis()
                self.results.extend(phase3_results)

            # Generate summary
            report = self.generate_summary()

            # Save JSON report if requested
            self.save_json_report(report)

            # Return appropriate exit code
            if report.overall_status == GateStatus.PASS:
                return 0
            else:
                return 1

        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}[INTERRUPTED] Verification cancelled by user{Colors.RESET}")
            return 130
        except Exception as e:
            print(f"\n{Colors.RED}[ERROR] Unexpected error: {e}{Colors.RESET}")
            if self.verbose:
                import traceback
                traceback.print_exc()
            return 2


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Comprehensive Code Quality Gates Verification",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/verify_quality_gates.py
  python scripts/verify_quality_gates.py --verbose --fail-fast
  python scripts/verify_quality_gates.py --skip-coverage
  python scripts/verify_quality_gates.py --json-output results.json
        """,
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first failure",
    )
    parser.add_argument(
        "--skip-coverage",
        action="store_true",
        help="Skip coverage verification phase",
    )
    parser.add_argument(
        "--json-output",
        type=str,
        metavar="FILE",
        help="Save JSON report to file",
    )

    args = parser.parse_args()

    verifier = QualityGateVerifier(
        verbose=args.verbose,
        fail_fast=args.fail_fast,
        skip_coverage=args.skip_coverage,
        json_output=args.json_output,
    )

    sys.exit(verifier.run())


if __name__ == "__main__":
    main()
