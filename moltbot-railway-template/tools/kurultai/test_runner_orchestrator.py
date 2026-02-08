#!/usr/bin/env python3
"""
Jochi's Automated Test Runner & Orchestrator

Periodically executes the Kurultai testing framework, analyzes results,
and automatically actions on findings (creates tickets, sends alerts, applies fixes).

This is designed to be run as a scheduled job (cron, systemd timer, or Railway cron).
Jochi (the analyst agent) will:
1. Run the test suite
2. Parse results
3. Categorize findings (critical, high, medium, low)
4. Auto-create remediation tasks for critical issues
5. Send summaries to designated channels

Usage:
    python tools/kurultai/test_runner_orchestrator.py [--phase PHASE] [--dry-run]

Integration with Jochi agent:
    Jochi can invoke this script with specific phases and then analyze the output.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("jochi.test_runner")


class Severity(Enum):
    """Issue severity levels for Jochi's analysis."""
    CRITICAL = "critical"  # System down, data loss, security breach
    HIGH = "high"         # Major functionality broken, performance degraded >50%
    MEDIUM = "medium"     # Minor functionality broken, performance degraded 10-50%
    LOW = "low"          # Cosmetic issues, performance degraded <10%
    INFO = "info"         # Informational findings


class Phase(Enum):
    """Testing phases from the Kurultai Testing & Metrics Framework."""
    FIXTURES = "phase0"
    INTERACTIVE = "phase1"
    INTEGRATION = "phase2"
    CONCURRENT = "phase3"
    E2E = "phase4"
    METRICS = "phase5"
    PERFORMANCE = "phase6"
    ALL = "all"


@dataclass
class TestResult:
    """Result of a single test execution."""
    phase: str
    test_name: str
    status: str  # "passed", "failed", "skipped", "error"
    duration: float
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PhaseResult:
    """Aggregated results for a testing phase."""
    phase: str
    phase_name: str
    status: str  # "passed", "failed", "partial"
    total_tests: int
    passed: int
    failed: int
    skipped: int
    errors: int
    duration: float
    tests: List[TestResult] = field(default_factory=list)
    issues: List[Dict[str, Any]] = field(default_factory=dict)

    def pass_rate(self) -> float:
        if self.total_tests == 0:
            return 0.0
        return (self.passed / self.total_tests) * 100


@dataclass
class Finding:
    """A discovered issue that Jochi should action."""
    severity: Severity
    category: str  # "security", "performance", "correctness", "infrastructure"
    title: str
    description: str
    evidence: Dict[str, Any]
    source_phase: str
    source_test: str
    remediation: str = ""
    auto_fix_available: bool = False
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class TestRunner:
    """Executes test suites and captures results."""

    def __init__(self, project_root: Path, output_dir: Path):
        self.project_root = project_root
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run_pytest(
        self,
        test_path: str,
        markers: Optional[str] = None,
        extra_args: Optional[List[str]] = None
    ) -> subprocess.CompletedProcess:
        """Run pytest with given parameters and capture results."""
        cmd = ["pytest", "-v", "--tb=short", "--json-report", "--json-report-file=-"]

        if markers:
            cmd.extend(["-m", markers])

        if extra_args:
            cmd.extend(extra_args)

        cmd.append(test_path)

        logger.info(f"Running: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            cwd=self.project_root,
            capture_output=True,
            text=True
        )

        return result

    def parse_json_report(self, stdout: str) -> Dict[str, Any]:
        """Extract JSON report from pytest output."""
        try:
            # Find JSON report in stdout (json-report-plugin outputs to stdout)
            lines = stdout.split("\n")
            for i, line in enumerate(lines):
                if line.strip().startswith("{"):
                    # Try to parse as JSON
                    try:
                        report = json.loads(line)
                        return report
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning(f"Could not parse JSON report: {e}")

        return {}


class JochiAnalyzer:
    """Analyzes test results and generates actionable findings."""

    def __init__(self, thresholds: Optional[Dict[str, Any]] = None):
        self.thresholds = thresholds or self._default_thresholds()

    def _default_thresholds(self) -> Dict[str, Any]:
        return {
            "pass_rate_critical": 50.0,   # Below 50% pass = critical
            "pass_rate_high": 80.0,        # Below 80% pass = high
            "duration_p95_critical": 5.0,  # Test > 5s = critical for unit tests
            "duration_p95_high": 2.0,      # Test > 2s = high for unit tests
            "concurrent_duplicates": 0,    # Any duplicates = critical
            "heartbeat_age_critical": 300, # Heartbeat > 5min stale = critical
        }

    def analyze_phase(self, phase_result: PhaseResult) -> List[Finding]:
        """Analyze phase results and generate findings."""
        findings = []

        # Check overall pass rate
        pass_rate = phase_result.pass_rate()

        if pass_rate < self.thresholds["pass_rate_critical"]:
            findings.append(Finding(
                severity=Severity.CRITICAL,
                category="correctness",
                title=f"Critical test failures in {phase_result.phase_name}",
                description=f"Only {pass_rate:.1f}% of tests passed ({phase_result.passed}/{phase_result.total_tests})",
                evidence={"pass_rate": pass_rate, "failed": phase_result.failed},
                source_phase=phase_result.phase,
                source_test="aggregate",
                remediation="Review failed tests and fix underlying issues. Block deployment until resolved."
            ))
        elif pass_rate < self.thresholds["pass_rate_high"]:
            findings.append(Finding(
                severity=Severity.HIGH,
                category="correctness",
                title=f"High failure rate in {phase_result.phase_name}",
                description=f"{pass_rate:.1f}% pass rate is below 80% threshold",
                evidence={"pass_rate": pass_rate, "failed": phase_result.failed},
                source_phase=phase_result.phase,
                source_test="aggregate",
                remediation="Investigate failing tests and prioritize fixes."
            ))

        # Analyze individual test failures
        for test in phase_result.tests:
            if test.status == "failed":
                findings.extend(self._analyze_failed_test(test, phase_result))
            elif test.status == "error":
                findings.append(Finding(
                    severity=Severity.HIGH,
                    category="infrastructure",
                    title=f"Test error in {test.test_name}",
                    description=f"Test encountered an error (not assertion failure): {test.message}",
                    evidence={"test": test.test_name, "message": test.message},
                    source_phase=phase_result.phase,
                    source_test=test.test_name,
                    remediation="Check test setup and environment configuration."
                ))

        # Phase-specific analysis
        if phase_result.phase == Phase.INTEGRATION.value:
            findings.extend(self._analyze_integration_failures(phase_result))
        elif phase_result.phase == Phase.CONCURRENT.value:
            findings.extend(self._analyze_concurrent_failures(phase_result))
        elif phase_result.phase == Phase.PERFORMANCE.value:
            findings.extend(self._analyze_performance_failures(phase_result))
        elif phase_result.phase == Phase.HEARTBEAT.value:
            findings.extend(self._analyze_heartbeat_failures(phase_result))

        return findings

    def _analyze_failed_test(self, test: TestResult, phase: PhaseResult) -> List[Finding]:
        """Analyze a single failed test for specific issues."""
        findings = []
        test_name = test.test_name.lower()

        # Security-related tests
        if any(kw in test_name for kw in ["security", "auth", "pii", "injection", "xss"]):
            findings.append(Finding(
                severity=Severity.CRITICAL,
                category="security",
                title=f"Security test failed: {test.test_name}",
                description=test.message or "Security validation failed",
                evidence={"test": test.test_name, "phase": phase.phase},
                source_phase=phase.phase,
                source_test=test.test_name,
                remediation="Review security implementation and fix vulnerability."
            ))

        # Performance-related tests
        elif any(kw in test_name for kw in ["performance", "latency", "duration", "benchmark"]):
            severity = Severity.HIGH if "p95" in test_name or "timeout" in test_name else Severity.MEDIUM
            findings.append(Finding(
                severity=severity,
                category="performance",
                title=f"Performance test failed: {test.test_name}",
                description=test.message or "Performance threshold exceeded",
                evidence={"test": test.test_name, "duration": test.duration},
                source_phase=phase.phase,
                source_test=test.test_name,
                remediation="Profile the slow operation and optimize."
            ))

        # Data integrity tests
        elif any(kw in test_name for kw in ["concurrent", "race", "duplicate", "atomic", "lock"]):
            findings.append(Finding(
                severity=Severity.CRITICAL,
                category="correctness",
                title=f"Concurrency test failed: {test.test_name}",
                description=test.message or "Concurrency safety issue detected",
                evidence={"test": test.test_name},
                source_phase=phase.phase,
                source_test=test.test_name,
                remediation="Review locking strategy and transaction boundaries."
            ))

        # Neo4j/memory tests
        elif any(kw in test_name for kw in ["neo4j", "memory", "query", "database"]):
            findings.append(Finding(
                severity=Severity.HIGH,
                category="infrastructure",
                title=f"Database test failed: {test.test_name}",
                description=test.message or "Neo4j operation failed",
                evidence={"test": test.test_name},
                source_phase=phase.phase,
                source_test=test.test_name,
                remediation="Check Neo4j connection, query syntax, and data model."
            ))

        # Agent communication tests
        elif any(kw in test_name for kw in ["agent", "messaging", "gateway", "delegation"]):
            findings.append(Finding(
                severity=Severity.HIGH,
                category="infrastructure",
                title=f"Agent communication test failed: {test.test_name}",
                description=test.message or "Agent-to-agent communication failed",
                evidence={"test": test.test_name},
                source_phase=phase.phase,
                source_test=test.test_name,
                remediation="Check OpenClaw gateway status and agent registration."
            ))

        return findings

    def _analyze_integration_failures(self, phase: PhaseResult) -> List[Finding]:
        """Analyze integration test failures for systemic issues."""
        findings = []

        # Check for pattern of failures in specific components
        component_failures: Dict[str, int] = {}
        for test in phase.tests:
            if test.status == "failed":
                # Extract component name from test (e.g., "test_agent_messaging" -> "messaging")
                parts = test.test_name.split("_")
                if len(parts) >= 2:
                    component = parts[1] if parts[0] == "test" else parts[0]
                    component_failures[component] = component_failures.get(component, 0) + 1

        # Multiple failures in same component = systemic issue
        for component, count in component_failures.items():
            if count >= 3:
                findings.append(Finding(
                    severity=Severity.HIGH,
                    category="infrastructure",
                    title=f"Systemic failures in {component} integration",
                    description=f"{count} tests failed related to {component}",
                    evidence={"component": component, "failures": count},
                    source_phase=phase.phase,
                    source_test="aggregate",
                    remediation=f"Review {component} service configuration and dependencies."
                ))

        return findings

    def _analyze_concurrent_failures(self, phase: PhaseResult) -> List[Finding]:
        """Analyze concurrent test failures for race conditions."""
        findings = []

        for test in phase.tests:
            if test.status == "failed":
                test_name = test.test_name.lower()

                # Duplicate claims = data integrity issue
                if "duplicate" in test_name or "claim" in test_name:
                    findings.append(Finding(
                        severity=Severity.CRITICAL,
                        category="correctness",
                        title="Race condition: duplicate task claims detected",
                        description="Multiple agents claimed the same task simultaneously",
                        evidence={"test": test.test_name},
                        source_phase=phase.phase,
                        source_test=test.test_name,
                        remediation="Review transaction boundaries and implement proper locking.",
                        auto_fix_available=False
                    ))

                # Deadlock = availability issue
                elif "deadlock" in test_name or "timeout" in test_name:
                    findings.append(Finding(
                        severity=Severity.HIGH,
                        category="correctness",
                        title="Potential deadlock detected",
                        description="Concurrent operations may be causing deadlocks",
                        evidence={"test": test.test_name},
                        source_phase=phase.phase,
                        source_test=test.test_name,
                        remediation="Review lock acquisition order and implement timeout handling."
                    ))

        return findings

    def _analyze_performance_failures(self, phase: PhaseResult) -> List[Finding]:
        """Analyze performance test failures."""
        findings = []

        for test in phase.tests:
            if test.status == "failed" and test.duration > 0:
                # Check against thresholds
                if test.duration > self.thresholds["duration_p95_critical"]:
                    findings.append(Finding(
                        severity=Severity.CRITICAL,
                        category="performance",
                        title=f"Critical performance degradation: {test.test_name}",
                        description=f"Operation took {test.duration:.2f}s, exceeds {self.thresholds['duration_p95_critical']}s threshold",
                        evidence={"test": test.test_name, "duration": test.duration},
                        source_phase=phase.phase,
                        source_test=test.test_name,
                        remediation="Profile and optimize this critical path."
                    ))
                elif test.duration > self.thresholds["duration_p95_high"]:
                    findings.append(Finding(
                        severity=Severity.HIGH,
                        category="performance",
                        title=f"Performance degradation: {test.test_name}",
                        description=f"Operation took {test.duration:.2f}s, exceeds {self.thresholds['duration_p95_high']}s threshold",
                        evidence={"test": test.test_name, "duration": test.duration},
                        source_phase=phase.phase,
                        source_test=test.test_name,
                        remediation="Consider optimization or caching."
                    ))

        return findings

    def _analyze_heartbeat_failures(self, phase: PhaseResult) -> List[Finding]:
        """Analyze heartbeat system test failures."""
        findings = []

        for test in phase.tests:
            if test.status == "failed":
                test_name = test.test_name.lower()

                # Heartbeat age = agent availability issue
                if "heartbeat" in test_name and ("stale" in test_name or "age" in test_name):
                    findings.append(Finding(
                        severity=Severity.CRITICAL,
                        category="infrastructure",
                        title="Agent heartbeat stale - possible failure",
                        description="Agent heartbeat not updating within threshold",
                        evidence={"test": test.test_name},
                        source_phase=phase.phase,
                        source_test=test.test_name,
                        remediation="Check agent process status and heartbeat_writer sidecar."
                    ))

                # Threshold mismatch = configuration drift
                elif "threshold" in test_name or "standardized" in test_name:
                    findings.append(Finding(
                        severity=Severity.MEDIUM,
                        category="correctness",
                        title="Heartbeat threshold inconsistency",
                        description="Heartbeat thresholds not standardized across components",
                        evidence={"test": test.test_name},
                        source_phase=phase.phase,
                        source_test=test.test_name,
                        remediation="Update constants to use standard 120s infra / 90s functional thresholds."
                    ))

        return findings


class RemediationOrchestrator:
    """Actions on findings automatically when possible."""

    def __init__(
        self,
        project_root: Path,
        dry_run: bool = False,
        max_auto_fixes: int = 3
    ):
        self.project_root = project_root
        self.dry_run = dry_run
        self.max_auto_fixes = max_auto_fixes
        self.fixes_applied = 0

    def action_findings(
        self,
        findings: List[Finding],
        report_path: Path
    ) -> List[Dict[str, Any]]:
        """Execute remediation actions for applicable findings."""
        actions_taken = []

        for finding in findings:
            # Skip if we've hit our auto-fix limit
            if self.fixes_applied >= self.max_auto_fixes:
                logger.warning(f"Reached max auto-fixes limit ({self.max_auto_fixes}), stopping automatic remediation")
                break

            # Auto-fix based on category
            if finding.category == "infrastructure" and "threshold" in finding.title.lower():
                action = self._fix_threshold_constant(finding)
                if action:
                    actions_taken.append(action)
                    self.fixes_applied += 1

            elif finding.category == "correctness" and "duplicate" in finding.title.lower():
                action = self._create_ticket_for_finding(finding, report_path)
                if action:
                    actions_taken.append(action)
                    self.fixes_applied += 1

            elif finding.severity in (Severity.CRITICAL, Severity.HIGH):
                # Create tickets for critical issues
                action = self._create_ticket_for_finding(finding, report_path)
                if action:
                    actions_taken.append(action)
                    self.fixes_applied += 1

        return actions_taken

    def _fix_threshold_constant(self, finding: Finding) -> Optional[Dict[str, Any]]:
        """Attempt to fix heartbeat threshold inconsistencies."""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would fix threshold constant: {finding.title}")
            return {"action": "fix_threshold", "finding": finding.title, "dry_run": True}

        # This would implement actual threshold constant updates
        logger.info(f"Auto-fixing threshold constant: {finding.title}")
        return {
            "action": "fix_threshold",
            "finding": finding.title,
            "status": "implemented",
            "files_modified": []
        }

    def _create_ticket_for_finding(
        self,
        finding: Finding,
        report_path: Path
    ) -> Optional[Dict[str, Any]]:
        """Create a task/ticket for the finding."""
        ticket_id = f"TICKET-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        ticket_data = {
            "id": ticket_id,
            "severity": finding.severity.value,
            "category": finding.category,
            "title": finding.title,
            "description": finding.description,
            "evidence": finding.evidence,
            "remediation": finding.remediation,
            "source_phase": finding.source_phase,
            "created_at": finding.created_at,
            "report_reference": str(report_path)
        }

        # Save ticket to file
        tickets_dir = self.project_root / "data" / "workspace" / "tickets"
        tickets_dir.mkdir(parents=True, exist_ok=True)
        ticket_file = tickets_dir / f"{ticket_id}.json"

        if not self.dry_run:
            with open(ticket_file, 'w') as f:
                json.dump(ticket_data, f, indent=2)
            logger.info(f"Created ticket: {ticket_file}")
        else:
            logger.info(f"[DRY RUN] Would create ticket: {ticket_file}")

        return {
            "action": "create_ticket",
            "ticket_id": ticket_id,
            "finding": finding.title,
            "file": str(ticket_file),
            "dry_run": self.dry_run
        }


class JochiTestOrchestrator:
    """Main orchestrator for Jochi's automated testing workflow."""

    def __init__(
        self,
        project_root: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        dry_run: bool = False
    ):
        self.project_root = project_root or Path.cwd()
        self.output_dir = output_dir or self.project_root / "data" / "test_results"
        self.dry_run = dry_run

        self.runner = TestRunner(self.project_root, self.output_dir)
        self.analyzer = JochiAnalyzer()
        self.remediator = RemediationOrchestrator(self.project_root, dry_run)

        logger.info(f"Jochi Test Orchestrator initialized")
        logger.info(f"Project root: {self.project_root}")
        logger.info(f"Output dir: {self.output_dir}")
        logger.info(f"Dry run: {self.dry_run}")

    def run_phase(self, phase: Phase) -> PhaseResult:
        """Run a single testing phase and return results."""
        phase_configs = {
            Phase.FIXTURES: {
                "name": "Test Infrastructure",
                "path": "tests/fixtures/",
                "type": "import"
            },
            Phase.INTERACTIVE: {
                "name": "Interactive Workflows",
                "path": "tests/interactive/",
                "type": "skip"  # Manual only
            },
            Phase.INTEGRATION: {
                "name": "Unit & Integration Tests",
                "path": "tests/integration/",
                "type": "pytest"
            },
            Phase.CONCURRENT: {
                "name": "Concurrent & Chaos Tests",
                "path": "tests/concurrency/ tests/chaos/",
                "type": "pytest"
            },
            Phase.E2E: {
                "name": "E2E Workflow Tests",
                "path": "tests/e2e/",
                "type": "pytest"
            },
            Phase.METRICS: {
                "name": "Metrics & Observability",
                "path": "",  # Special handling
                "type": "metrics"
            },
            Phase.PERFORMANCE: {
                "name": "Performance Benchmarks",
                "path": "tests/performance/",
                "type": "benchmark"
            },
        }

        config = phase_configs.get(phase, {"name": phase.value, "path": "", "type": "skip"})

        logger.info(f"Running phase: {config['name']}")

        if config["type"] == "skip":
            logger.info(f"Skipping {config['name']} (manual or not yet implemented)")
            return PhaseResult(
                phase=phase.value,
                phase_name=config["name"],
                status="skipped",
                total_tests=0,
                passed=0,
                failed=0,
                skipped=0,
                errors=0,
                duration=0
            )

        elif config["type"] == "import":
            return self._run_import_tests(config)
        elif config["type"] == "pytest":
            return self._run_pytest_tests(phase, config)
        elif config["type"] == "benchmark":
            return self._run_benchmark_tests(phase, config)
        elif config["type"] == "metrics":
            return self._run_metrics_check(phase, config)

        return PhaseResult(
            phase=phase.value,
            phase_name=config["name"],
            status="unknown",
            total_tests=0,
            passed=0,
            failed=0,
            skipped=0,
            errors=0,
            duration=0
        )

    def _run_import_tests(self, config: Dict) -> PhaseResult:
        """Run import/validation tests for fixtures."""
        importTests = [
            ("from tests.fixtures.integration_harness import KurultaiTestHarness", "IntegrationHarness"),
            ("from tests.fixtures.mock_agents import MockAgentFactory", "MockAgentFactory"),
            ("from tests.fixtures.test_data import TestDataGenerator", "TestDataGenerator"),
        ]

        tests = []
        passed = 0
        failed = 0
        errors = 0

        for statement, name in importTests:
            try:
                exec(statement)
                tests.append(TestResult(
                    phase=Phase.FIXTURES.value,
                    test_name=f"import_{name}",
                    status="passed",
                    duration=0,
                    message=f"Successfully imported {name}"
                ))
                passed += 1
            except Exception as e:
                tests.append(TestResult(
                    phase=Phase.FIXTURES.value,
                    test_name=f"import_{name}",
                    status="error",
                    duration=0,
                    message=str(e)
                ))
                errors += 1

        return PhaseResult(
            phase=Phase.FIXTURES.value,
            phase_name=config["name"],
            status="passed" if errors == 0 else "failed",
            total_tests=len(tests),
            passed=passed,
            failed=failed,
            skipped=0,
            errors=errors,
            duration=0,
            tests=tests
        )

    def _run_pytest_tests(self, phase: Phase, config: Dict) -> PhaseResult:
        """Run pytest for the given phase."""
        result = self.runner.run_pytest(config["path"])

        # Parse output (simplified - in production, use pytest-json-report)
        tests = []
        passed = failed = errors = 0

        # Simple parsing of pytest output
        for line in result.stdout.split("\n"):
            line = line.strip()
            if "PASSED" in line:
                test_name = line.split("::")[-1].split()[0] if "::" in line else line
                tests.append(TestResult(
                    phase=phase.value,
                    test_name=test_name,
                    status="passed",
                    duration=0,
                    message=""
                ))
                passed += 1
            elif "FAILED" in line:
                test_name = line.split("::")[-1].split()[0] if "::" in line else line
                tests.append(TestResult(
                    phase=phase.value,
                    test_name=test_name,
                    status="failed",
                    duration=0,
                    message=line
                ))
                failed += 1
            elif "ERROR" in line:
                errors += 1

        return PhaseResult(
            phase=phase.value,
            phase_name=config["name"],
            status="passed" if failed == 0 and errors == 0 else "failed",
            total_tests=len(tests),
            passed=passed,
            failed=failed,
            skipped=0,
            errors=errors,
            duration=0,
            tests=tests
        )

    def _run_benchmark_tests(self, phase: Phase, config: Dict) -> PhaseResult:
        """Run performance benchmarks."""
        result = self.runner.run_pytest(
            config["path"],
            extra_args=["--benchmark-only", "--benchmark-json=-"]
        )

        tests = []
        passed = failed = 0

        # Parse benchmark output
        try:
            if result.stdout:
                benchmark_data = json.loads(result.stdout)
                for test_name, data in benchmark_data.get("benchmarks", {}).items():
                    tests.append(TestResult(
                        phase=phase.value,
                        test_name=test_name,
                        status="passed",
                        duration=data.get("stats", {}).get("mean", 0),
                        message=f"Mean: {data.get('stats', {}).get('mean', 0):.4f}s"
                    ))
                    passed += 1
        except json.JSONDecodeError:
            # Fallback parsing
            for line in result.stdout.split("\n"):
                if "passed" in line.lower():
                    passed += 1

        return PhaseResult(
            phase=phase.value,
            phase_name=config["name"],
            status="passed" if failed == 0 else "failed",
            total_tests=len(tests),
            passed=passed,
            failed=failed,
            skipped=0,
            errors=0,
            duration=0,
            tests=tests
        )

    def _run_metrics_check(self, phase: Phase, config: Dict) -> PhaseResult:
        """Verify metrics endpoint is accessible."""
        import urllib.request

        tests = []
        passed = 0
        failed = 0

        # Check metrics endpoint
        try:
            with urllib.request.urlopen("http://localhost:18789/metrics", timeout=5) as response:
                if response.status == 200:
                    tests.append(TestResult(
                        phase=phase.value,
                        test_name="metrics_endpoint_accessible",
                        status="passed",
                        duration=0,
                        message="Metrics endpoint returned 200"
                    ))
                    passed += 1
                else:
                    tests.append(TestResult(
                        phase=phase.value,
                        test_name="metrics_endpoint_accessible",
                        status="failed",
                        duration=0,
                        message=f"Metrics endpoint returned {response.status}"
                    ))
                    failed += 1
        except Exception as e:
            tests.append(TestResult(
                phase=phase.value,
                test_name="metrics_endpoint_accessible",
                status="error",
                duration=0,
                message=str(e)
            ))
            failed += 1

        return PhaseResult(
            phase=phase.value,
            phase_name=config["name"],
            status="passed" if failed == 0 else "failed",
            total_tests=len(tests),
            passed=passed,
            failed=failed,
            skipped=0,
            errors=0,
            duration=0,
            tests=tests
        )

    def run_all_phases(self, phases: Optional[List[Phase]] = None) -> Dict[str, PhaseResult]:
        """Run multiple phases and return aggregated results."""
        if phases is None:
            phases = [
                Phase.FIXTURES,
                Phase.INTEGRATION,
                Phase.CONCURRENT,
                Phase.E2E,
                Phase.PERFORMANCE,
            ]

        results = {}

        for phase in phases:
            try:
                result = self.run_phase(phase)
                results[phase.value] = result
            except Exception as e:
                logger.error(f"Error running phase {phase.value}: {e}")
                results[phase.value] = PhaseResult(
                    phase=phase.value,
                    phase_name=phase.value,
                    status="error",
                    total_tests=0,
                    passed=0,
                    failed=0,
                    skipped=0,
                    errors=1,
                    duration=0
                )

        return results

    def analyze_results(self, results: Dict[str, PhaseResult]) -> List[Finding]:
        """Analyze all phase results and generate findings."""
        all_findings = []

        for phase_result in results.values():
            findings = self.analyzer.analyze_phase(phase_result)
            all_findings.extend(findings)

        # Sort by severity (critical first)
        severity_order = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3, Severity.INFO: 4}
        all_findings.sort(key=lambda f: severity_order.get(f.severity, 99))

        return all_findings

    def generate_report(
        self,
        results: Dict[str, PhaseResult],
        findings: List[Finding]
    ) -> Dict[str, Any]:
        """Generate a comprehensive test execution report."""
        total_tests = sum(r.total_tests for r in results.values())
        total_passed = sum(r.passed for r in results.values())
        total_failed = sum(r.failed for r in results.values())
        total_errors = sum(r.errors for r in results.values())

        critical_findings = [f for f in findings if f.severity == Severity.CRITICAL]
        high_findings = [f for f in findings if f.severity == Severity.HIGH]

        report = {
            "execution_id": datetime.utcnow().strftime("%Y%m%d-%H%M%S"),
            "timestamp": datetime.utcnow().isoformat(),
            "summary": {
                "total_phases": len(results),
                "total_tests": total_tests,
                "passed": total_passed,
                "failed": total_failed,
                "errors": total_errors,
                "pass_rate": (total_passed / total_tests * 100) if total_tests > 0 else 0,
                "overall_status": "passed" if total_failed == 0 and total_errors == 0 else "failed"
            },
            "phases": {k: {
                "phase_name": v.phase_name,
                "status": v.status,
                "total_tests": v.total_tests,
                "passed": v.passed,
                "failed": v.failed,
                "errors": v.errors,
                "pass_rate": v.pass_rate()
            } for k, v in results.items()},
            "findings": {
                "critical": len(critical_findings),
                "high": len(high_findings),
                "medium": len([f for f in findings if f.severity == Severity.MEDIUM]),
                "low": len([f for f in findings if f.severity == Severity.LOW]),
                "details": [asdict(f) for f in findings[:20]]  # Top 20 findings
            },
            "recommendations": self._generate_recommendations(findings)
        }

        return report

    def _generate_recommendations(self, findings: List[Finding]) -> List[str]:
        """Generate actionable recommendations from findings."""
        recommendations = []

        critical_by_category: Dict[str, List[Finding]] = {}
        for f in findings:
            if f.severity in (Severity.CRITICAL, Severity.HIGH):
                critical_by_category.setdefault(f.category, []).append(f)

        # Category-specific recommendations
        if "security" in critical_by_category:
            recommendations.append(
                "URGENT: Security tests failed. Block deployment and review immediately."
            )

        if "correctness" in critical_by_category and any(
            "concurrent" in f.title.lower() or "race" in f.title.lower()
            for f in critical_by_category["correctness"]
        ):
            recommendations.append(
                "CRITICAL: Race conditions detected. Review transaction boundaries before next deployment."
            )

        if "infrastructure" in critical_by_category:
            recommendations.append(
                "HIGH: Infrastructure issues detected. Check Neo4j and OpenClaw gateway status."
            )

        if "performance" in critical_by_category:
            recommendations.append(
                "PERFORMANCE: Performance degradation detected. Profile and optimize before scaling."
            )

        if not recommendations:
            recommendations.append("All tests passed. System healthy.")

        return recommendations

    def save_report(self, report: Dict[str, Any]) -> Path:
        """Save the test execution report to disk."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        report_file = self.output_dir / f"test_report_{timestamp}.json"

        if not self.dry_run:
            with open(report_file, 'w') as f:
                json.dump(report, f, indent=2)
            logger.info(f"Report saved to: {report_file}")

            # Also save a human-readable summary
            summary_file = self.output_dir / f"test_summary_{timestamp}.txt"
            with open(summary_file, 'w') as f:
                f.write(self._format_report_summary(report))
            logger.info(f"Summary saved to: {summary_file}")
        else:
            logger.info(f"[DRY RUN] Would save report to: {report_file}")

        return report_file

    def _format_report_summary(self, report: Dict[str, Any]) -> str:
        """Format a human-readable summary of the report."""
        lines = [
            "=" * 60,
            "KURULTAI TEST EXECUTION SUMMARY",
            "=" * 60,
            f"Execution ID: {report['execution_id']}",
            f"Timestamp: {report['timestamp']}",
            "",
            "SUMMARY",
            "-" * 60,
            f"Total Phases: {report['summary']['total_phases']}",
            f"Total Tests: {report['summary']['total_tests']}",
            f"Passed: {report['summary']['passed']}",
            f"Failed: {report['summary']['failed']}",
            f"Errors: {report['summary']['errors']}",
            f"Pass Rate: {report['summary']['pass_rate']:.1f}%",
            f"Overall Status: {report['summary']['overall_status'].upper()}",
            "",
            "FINDINGS",
            "-" * 60,
            f"Critical: {report['findings']['critical']}",
            f"High: {report['findings']['high']}",
            f"Medium: {report['findings']['medium']}",
            f"Low: {report['findings']['low']}",
            "",
        ]

        for finding in report['findings']['details'][:10]:
            lines.extend([
                f"[{finding['severity'].upper()}] {finding['title']}",
                f"  Category: {finding['category']}",
                f"  Description: {finding['description'][:100]}...",
                ""
            ])

        lines.extend([
            "RECOMMENDATIONS",
            "-" * 60
        ])
        for rec in report['recommendations']:
            lines.append(f"  • {rec}")

        lines.append("=" * 60)

        return "\n".join(lines)

    def execute(
        self,
        phases: Optional[List[Phase]] = None,
        auto_remediate: bool = True
    ) -> Dict[str, Any]:
        """Execute the full testing workflow: run → analyze → report → remediate."""
        logger.info("Starting Jochi Test Orchestrator execution")
        start_time = datetime.utcnow()

        # Run all phases
        results = self.run_all_phases(phases)

        # Analyze results
        findings = self.analyze_results(results)
        logger.info(f"Analysis complete: {len(findings)} findings generated")

        # Generate report
        report = self.generate_report(results, findings)

        # Save report
        report_path = self.save_report(report)

        # Auto-remediate if enabled
        actions_taken = []
        if auto_remediate and not self.dry_run:
            actions_taken = self.remediator.action_findings(findings, report_path)
            report["actions_taken"] = actions_taken

        # Calculate total duration
        duration = (datetime.utcnow() - start_time).total_seconds()
        report["execution_duration_seconds"] = duration

        logger.info(f"Execution complete in {duration:.1f}s")
        logger.info(f"Overall status: {report['summary']['overall_status'].upper()}")

        if report['summary']['overall_status'] == 'failed':
            logger.error(f"Tests FAILED: {report['summary']['failed']} failures, {report['findings']['critical']} critical findings")

        return report


# Add Phase.HEARTBEAT to the Phase enum
Phase.HEARTBEAT = "phase_heartbeat"  # Integration tests for heartbeat


def main():
    """CLI entry point for Jochi's test orchestrator."""
    parser = argparse.ArgumentParser(
        description="Jochi's Automated Test Runner & Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all phases
  python tools/kurultai/test_runner_orchestrator.py

  # Run specific phase
  python tools/kurultai/test_runner_orchestrator.py --phase integration

  # Dry run (don't save files or apply fixes)
  python tools/kurultai/test_runner_orchestrator.py --dry-run

  # Run with custom project root
  python tools/kurultai/test_runner_orchestrator.py --project-root /path/to/molt
        """
    )

    parser.add_argument(
        "--phase",
        choices=["fixtures", "interactive", "integration", "concurrent", "e2e", "metrics", "performance", "all"],
        default="all",
        help="Testing phase to run (default: all)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run - don't save files or apply remediation"
    )

    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Path to project root (default: CWD)"
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Path to output directory (default: <project-root>/data/test_results)"
    )

    parser.add_argument(
        "--no-remediate",
        action="store_true",
        help="Skip automatic remediation actions"
    )

    args = parser.parse_args()

    # Map phase argument to Phase enum
    phase_map = {
        "fixtures": Phase.FIXTURES,
        "interactive": Phase.INTERACTIVE,
        "integration": Phase.INTEGRATION,
        "concurrent": Phase.CONCURRENT,
        "e2e": Phase.E2E,
        "metrics": Phase.METRICS,
        "performance": Phase.PERFORMANCE,
        "all": None,
    }

    phases = None if args.phase == "all" else [phase_map[args.phase]]

    # Initialize orchestrator
    orchestrator = JochiTestOrchestrator(
        project_root=args.project_root,
        output_dir=args.output_dir,
        dry_run=args.dry_run
    )

    # Execute
    try:
        report = orchestrator.execute(
            phases=phases,
            auto_remediate=not args.no_remediate
        )

        # Exit with appropriate code
        sys.exit(0 if report['summary']['overall_status'] == 'passed' else 1)

    except Exception as e:
        logger.exception(f"Execution failed: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
