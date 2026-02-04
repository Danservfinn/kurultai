"""
OpenClaw Pre-Flight Testing Checklist

Comprehensive pre-flight validation system for the 6-agent OpenClaw system.
Validates environment, Neo4j connectivity, authentication, and agent operational
status before production deployment.

Overall Go/No-Go Criteria:
- ALL critical checks must pass (marked with [CRITICAL])
- At least 90% of all checks must pass
- No critical errors in logs
- All 6 agents operational and communicating

Usage:
    python -m scripts.pre_flight_check

    Or programmatically:
    from scripts.pre_flight_check import PreFlightCheck
    checker = PreFlightCheck()
    result = checker.run_all_checks()
    print(checker.generate_report())
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import check modules
from scripts.check_types import CheckResult, CheckCategory, CheckStatus, GoNoGoDecision
from scripts.check_environment import EnvironmentChecker
from scripts.check_neo4j import Neo4jChecker
from scripts.check_auth import AuthChecker
from scripts.check_agents import AgentChecker

# Configure logging
logger = logging.getLogger(__name__)

# Re-export for backward compatibility
__all__ = [
    "PreFlightCheck",
    "CheckResult",
    "CheckCategory",
    "CheckStatus",
    "GoNoGoDecision"
]


class PreFlightCheck:
    """
    Comprehensive pre-flight testing checklist.

    Runs all validation checks and returns Go/No-Go decision for
    production deployment.

    Critical Thresholds:
        - CRITICAL_GATEWAY_TOKEN_MIN: 32 chars
        - CRITICAL_NEO4J_PASSWORD_MIN: 16 chars
        - CRITICAL_HMAC_SECRET_MIN: 64 chars
        - MIN_AGENTS_COUNT: 6
        - MIN_INDEXES: 10
        - MIN_CONSTRAINTS: 5
        - QUERY_PERFORMANCE_MS: 100
        - PASS_THRESHOLD: 90% (0.90)

    Example:
        >>> checker = PreFlightCheck()
        >>> results = checker.run_all_checks()
        >>> decision = checker.get_go_no_go_decision()
        >>> if decision["decision"] == "GO":
        ...     print("Ready for production deployment!")
    """

    # Critical thresholds
    CRITICAL_GATEWAY_TOKEN_MIN = 32
    CRITICAL_NEO4J_PASSWORD_MIN = 16
    CRITICAL_HMAC_SECRET_MIN = 64
    MIN_AGENTS_COUNT = 6
    MIN_INDEXES = 10
    MIN_CONSTRAINTS = 5
    QUERY_PERFORMANCE_MS = 100
    PASS_THRESHOLD = 0.90  # 90%

    def __init__(
        self,
        config_path: str = "moltbot.json",
        env_path: str = ".env",
        verbose: bool = False
    ):
        """
        Initialize pre-flight checker.

        Args:
            config_path: Path to moltbot.json config file
            env_path: Path to .env file
            verbose: Enable verbose logging
        """
        self.config_path = config_path
        self.env_path = env_path
        self.verbose = verbose

        # Load config
        self.config = self._load_config()
        self.env_vars = self._load_env_vars()

        # Initialize checkers
        self.env_checker = EnvironmentChecker(
            config_path=config_path,
            env_path=env_path,
            verbose=verbose
        )
        self.neo4j_checker = Neo4jChecker(
            uri=self.env_vars.get("NEO4J_URI", "bolt://localhost:7687"),
            username=self.env_vars.get("NEO4J_USER", "neo4j"),
            password=self.env_vars.get("NEO4J_PASSWORD"),
            database=self.env_vars.get("NEO4J_DATABASE", "neo4j"),
            verbose=verbose
        )
        self.auth_checker = AuthChecker(
            gateway_token=self.env_vars.get("OPENCLAW_GATEWAY_TOKEN", ""),
            hmac_secret=self.env_vars.get("AGENTS_HMAC_SECRET", ""),
            verbose=verbose
        )
        self.agent_checker = AgentChecker(
            config=self.config,
            verbose=verbose
        )

        # Results storage
        self.results: List[CheckResult] = []
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None

    def _load_config(self) -> Dict:
        """Load moltbot.json configuration."""
        try:
            with open(self.config_path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"Config file not found: {self.config_path}")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
            return {}

    def _load_env_vars(self) -> Dict[str, str]:
        """Load environment variables from .env file."""
        env_vars = dict(os.environ)

        # Also try to load from .env file
        try:
            with open(self.env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        env_vars[key.strip()] = value.strip()
        except FileNotFoundError:
            logger.debug(f".env file not found: {self.env_path}")

        return env_vars

    def run_all_checks(self) -> Dict[str, Any]:
        """
        Run all pre-flight checks.

        Returns:
            Dictionary with all check results and summary
        """
        self.start_time = datetime.now(timezone.utc)
        logger.info("Starting pre-flight checks...")

        all_results = []

        # Run environment checks
        logger.info("Running environment checks...")
        env_results = self.run_environment_checks()
        all_results.extend(env_results)

        # Run Neo4j checks
        logger.info("Running Neo4j checks...")
        neo4j_results = self.run_neo4j_checks()
        all_results.extend(neo4j_results)

        # Run authentication checks
        logger.info("Running authentication checks...")
        auth_results = self.run_auth_checks()
        all_results.extend(auth_results)

        # Run agent checks
        logger.info("Running agent checks...")
        agent_results = self.run_agent_checks()
        all_results.extend(agent_results)

        self.results = all_results
        self.end_time = datetime.now(timezone.utc)

        duration = (self.end_time - self.start_time).total_seconds()
        logger.info(f"Pre-flight checks completed in {duration:.2f}s")

        return self._summarize_results()

    def run_environment_checks(self) -> List[CheckResult]:
        """Run environment validation checks (ENV-001 through ENV-012)."""
        return self.env_checker.run_all_checks()

    def run_neo4j_checks(self) -> List[CheckResult]:
        """Run Neo4j connectivity tests (NEO-001 through NEO-010)."""
        return self.neo4j_checker.run_all_checks()

    def run_auth_checks(self) -> List[CheckResult]:
        """Run agent authentication tests (AUTH-001 through AUTH-007)."""
        return self.auth_checker.run_all_checks()

    def run_agent_checks(self) -> List[CheckResult]:
        """Run agent operational tests."""
        return self.agent_checker.run_all_checks()

    def _summarize_results(self) -> Dict[str, Any]:
        """Generate summary of all check results."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.status == CheckStatus.PASS)
        failed = sum(1 for r in self.results if r.status == CheckStatus.FAIL)
        warned = sum(1 for r in self.results if r.status == CheckStatus.WARN)
        skipped = sum(1 for r in self.results if r.status == CheckStatus.SKIP)

        critical_total = sum(1 for r in self.results if r.critical)
        critical_passed = sum(1 for r in self.results if r.critical and r.status == CheckStatus.PASS)
        critical_failed = sum(1 for r in self.results if r.critical and r.status == CheckStatus.FAIL)

        pass_rate = passed / total if total > 0 else 0.0

        return {
            "total_checks": total,
            "passed_checks": passed,
            "failed_checks": failed,
            "warning_checks": warned,
            "skipped_checks": skipped,
            "critical_total": critical_total,
            "critical_passed": critical_passed,
            "critical_failed": critical_failed,
            "pass_rate": pass_rate,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": (self.end_time - self.start_time).total_seconds()
                if self.start_time and self.end_time else 0.0
        }

    def get_go_no_go_decision(self) -> GoNoGoDecision:
        """
        Get Go/No-Go decision with reasoning.

        Returns:
            GoNoGoDecision object with decision and reasoning
        """
        summary = self._summarize_results()

        # Count by category
        by_category = {
            CheckCategory.ENVIRONMENT: [],
            CheckCategory.NEO4J: [],
            CheckCategory.AUTHENTICATION: [],
            CheckCategory.AGENTS: []
        }
        for result in self.results:
            by_category[result.category].append(result)

        # Check critical failures
        critical_failures = [
            r for r in self.results
            if r.critical and r.status == CheckStatus.FAIL
        ]

        # Determine decision
        all_critical_passed = len(critical_failures) == 0
        pass_threshold_met = summary["pass_rate"] >= self.PASS_THRESHOLD

        decision = "GO"
        reasoning_parts = []
        blockers = []
        recommendations = []

        if not all_critical_passed:
            decision = "NO-GO"
            reasoning_parts.append(
                f"{len(critical_failures)} critical check(s) failed"
            )
            for cf in critical_failures:
                blockers.append(
                    f"[{cf.check_id}] {cf.description}: {cf.output}"
                )

        if not pass_threshold_met:
            decision = "NO-GO"
            reasoning_parts.append(
                f"Pass rate {summary['pass_rate']:.1%} is below {self.PASS_THRESHOLD:.0%} threshold"
            )

        if decision == "GO":
            reasoning_parts.append(
                f"All {summary['critical_total']} critical checks passed "
                f"and {summary['pass_rate']:.1%} overall pass rate meets threshold"
            )

        # Add recommendations for warnings
        warnings = [r for r in self.results if r.status == CheckStatus.WARN]
        if warnings:
            recommendations.append(
                f"Review {len(warnings)} warning(s) before production"
            )

        # Check specific categories
        env_failed = sum(1 for r in by_category[CheckCategory.ENVIRONMENT] if r.status == CheckStatus.FAIL)
        if env_failed > 0:
            recommendations.append(f"Fix {env_failed} environment check failure(s)")

        neo4j_failed = sum(1 for r in by_category[CheckCategory.NEO4J] if r.status == CheckStatus.FAIL)
        if neo4j_failed > 0:
            recommendations.append(f"Fix {neo4j_failed} Neo4j check failure(s)")

        auth_failed = sum(1 for r in by_category[CheckCategory.AUTHENTICATION] if r.status == CheckStatus.FAIL)
        if auth_failed > 0:
            recommendations.append(f"Fix {auth_failed} authentication check failure(s)")

        agent_failed = sum(1 for r in by_category[CheckCategory.AGENTS] if r.status == CheckStatus.FAIL)
        if agent_failed > 0:
            recommendations.append(f"Fix {agent_failed} agent check failure(s)")

        reasoning = " | ".join(reasoning_parts)

        return GoNoGoDecision(
            decision=decision,
            pass_rate=summary["pass_rate"],
            critical_passed=all_critical_passed,
            total_checks=summary["total_checks"],
            passed_checks=summary["passed_checks"],
            failed_checks=summary["failed_checks"],
            warning_checks=summary["warning_checks"],
            skipped_checks=summary["skipped_checks"],
            reasoning=reasoning,
            blockers=blockers,
            recommendations=recommendations
        )

    def generate_report(self) -> str:
        """
        Generate human-readable report.

        Returns:
            Formatted report string
        """
        decision = self.get_go_no_go_decision()
        summary = self._summarize_results()

        lines = []
        lines.append("=" * 80)
        lines.append("OPENCLAW PRE-FLIGHT CHECKLIST REPORT")
        lines.append("=" * 80)
        lines.append("")

        # Decision banner
        if decision.decision == "GO":
            lines.append("  " + "=" * 40)
            lines.append(f"  DECISION: {decision.decision}")
            lines.append("  " + "=" * 40)
            lines.append("")
        else:
            lines.append("  " + "#" * 40)
            lines.append(f"  DECISION: {decision.decision}")
            lines.append("  " + "#" * 40)
            lines.append("")

        # Summary
        lines.append("SUMMARY")
        lines.append("-" * 40)
        lines.append(f"  Total Checks:    {summary['total_checks']}")
        lines.append(f"  Passed:          {summary['passed_checks']} ({summary['pass_rate']:.1%})")
        lines.append(f"  Failed:          {summary['failed_checks']}")
        lines.append(f"  Warnings:        {summary['warning_checks']}")
        lines.append(f"  Skipped:         {summary['skipped_checks']}")
        lines.append(f"  Critical Passed: {summary['critical_passed']}/{summary['critical_total']}")
        lines.append("")

        # Reasoning
        lines.append("DECISION REASONING")
        lines.append("-" * 40)
        lines.append(f"  {decision.reasoning}")
        lines.append("")

        # Blockers
        if decision.blockers:
            lines.append("BLOCKING ISSUES")
            lines.append("-" * 40)
            for blocker in decision.blockers:
                lines.append(f"  - {blocker}")
            lines.append("")

        # Recommendations
        if decision.recommendations:
            lines.append("RECOMMENDATIONS")
            lines.append("-" * 40)
            for rec in decision.recommendations:
                lines.append(f"  - {rec}")
            lines.append("")

        # Category breakdown
        lines.append("CATEGORY BREAKDOWN")
        lines.append("-" * 40)
        for category in CheckCategory:
            cat_results = [r for r in self.results if r.category == category]
            if cat_results:
                cat_passed = sum(1 for r in cat_results if r.status == CheckStatus.PASS)
                cat_failed = sum(1 for r in cat_results if r.status == CheckStatus.FAIL)
                cat_warned = sum(1 for r in cat_results if r.status == CheckStatus.WARN)
                lines.append(f"  {category.value.upper()}:")
                lines.append(f"    Passed: {cat_passed}/{len(cat_results)}")
                if cat_failed > 0:
                    lines.append(f"    Failed: {cat_failed}")
                if cat_warned > 0:
                    lines.append(f"    Warnings: {cat_warned}")
        lines.append("")

        # Detailed results
        lines.append("DETAILED RESULTS")
        lines.append("-" * 40)

        # Group by category
        for category in CheckCategory:
            cat_results = [r for r in self.results if r.category == category]
            if not cat_results:
                continue

            lines.append(f"\n{category.value.upper()} CHECKS")
            lines.append("-" * 40)

            for result in cat_results:
                status_symbol = {
                    CheckStatus.PASS: "PASS",
                    CheckStatus.FAIL: "FAIL",
                    CheckStatus.WARN: "WARN",
                    CheckStatus.SKIP: "SKIP"
                }[result.status]

                critical_marker = " [CRITICAL]" if result.critical else ""

                lines.append(f"\n  [{result.check_id}] {result.description}{critical_marker}")
                lines.append(f"    Status:   {status_symbol}")
                if result.expected:
                    lines.append(f"    Expected: {result.expected}")
                if result.actual:
                    lines.append(f"    Actual:   {result.actual}")
                if result.output:
                    lines.append(f"    Output:   {result.output}")
                if result.duration_ms > 0:
                    lines.append(f"    Duration: {result.duration_ms:.2f}ms")
                if result.details:
                    for key, value in result.details.items():
                        lines.append(f"    {key}: {value}")

        lines.append("")
        lines.append("=" * 80)
        lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
        lines.append("=" * 80)

        return "\n".join(lines)

    def save_results(self, filepath: str) -> None:
        """
        Save check results to JSON file.

        Args:
            filepath: Path to save results
        """
        output = {
            "summary": self._summarize_results(),
            "decision": self.get_go_no_go_decision().to_dict(),
            "results": [r.to_dict() for r in self.results]
        }

        with open(filepath, "w") as f:
            json.dump(output, f, indent=2, default=str)

        logger.info(f"Results saved to: {filepath}")

    def load_results(self, filepath: str) -> None:
        """
        Load check results from JSON file.

        Args:
            filepath: Path to load results from
        """
        with open(filepath, "r") as f:
            data = json.load(f)

        self.results = [
            CheckResult.from_dict(r) for r in data["results"]
        ]

        logger.info(f"Loaded {len(self.results)} results from: {filepath}")


def main():
    """Main entry point for command-line usage."""
    import argparse

    parser = argparse.ArgumentParser(
        description="OpenClaw Pre-Flight Testing Checklist"
    )
    parser.add_argument(
        "-c", "--config",
        default="moltbot.json",
        help="Path to moltbot.json config file"
    )
    parser.add_argument(
        "-e", "--env",
        default=".env",
        help="Path to .env file"
    )
    parser.add_argument(
        "-o", "--output",
        help="Save results to JSON file"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--category",
        choices=["environment", "neo4j", "auth", "agents"],
        help="Run only specific category of checks"
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Run checks
    checker = PreFlightCheck(
        config_path=args.config,
        env_path=args.env,
        verbose=args.verbose
    )

    if args.category:
        # Run specific category
        if args.category == "environment":
            results = checker.run_environment_checks()
        elif args.category == "neo4j":
            results = checker.run_neo4j_checks()
        elif args.category == "auth":
            results = checker.run_auth_checks()
        elif args.category == "agents":
            results = checker.run_agent_checks()
        checker.results = results
    else:
        # Run all checks
        checker.run_all_checks()

    # Generate and print report
    report = checker.generate_report()
    print(report)

    # Save results if requested
    if args.output:
        checker.save_results(args.output)

    # Exit with appropriate code
    decision = checker.get_go_no_go_decision()
    sys.exit(0 if decision.decision == "GO" else 1)


if __name__ == "__main__":
    main()
