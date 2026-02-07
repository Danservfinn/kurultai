#!/usr/bin/env python3
"""
Complexity Scoring Validation Runner

This script runs the complexity scoring validation framework for the
Kurultai agent teams integration. It can be used in staging to validate
the TeamSizeClassifier before production deployment.

Usage:
    # Run full validation suite
    python scripts/run_complexity_validation.py --full

    # Run quick validation (edge cases + known simple/complex)
    python scripts/run_complexity_validation.py --quick

    # Run with custom thresholds
    python scripts/run_complexity_validation.py --lower 0.65 --upper 0.85

    # Calibrate thresholds
    python scripts/run_complexity_validation.py --calibrate

    # Generate report only (from previous results)
    python scripts/run_complexity_validation.py --report results.json

    # Export to Neo4j
    python scripts/run_complexity_validation.py --full --store-neo4j

Environment Variables:
    NEO4J_URI: Neo4j connection URI (default: bolt://localhost:7687)
    NEO4J_USER: Neo4j username (default: neo4j)
    NEO4J_PASSWORD: Neo4j password (default: password)
    CLASSIFIER_MODULE: Python module path to classifier (default: tools.kurultai.team_size_classifier)
    LOG_LEVEL: Logging level (default: INFO)

Exit Codes:
    0: Validation passed (GO recommendation)
    1: Validation failed (NO_GO recommendation)
    2: Error during validation
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tools.kurultai.complexity_config import DEFAULT_CONFIG
from tools.kurultai.complexity_validation_framework import (
    ComplexityValidationFramework,
    ThresholdCalibrator,
    StagingValidationPipeline,
    TestCaseLibrary,
    ValidationMetrics,
    create_validation_suite,
    run_quick_validation,
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def load_classifier(module_path: Optional[str] = None) -> Any:
    """Load the TeamSizeClassifier from specified module.

    Args:
        module_path: Python import path to classifier module (not used, fixed to TeamSizeClassifier)

    Returns:
        Loaded classifier instance
    """
    # Fixed import for security - no dynamic module loading
    try:
        from tools.kurultai.team_size_classifier import TeamSizeClassifier
        return TeamSizeClassifier()
    except Exception as e:
        raise RuntimeError(
            f"Failed to load TeamSizeClassifier: {e}\n"
            "Ensure the tools.kurultai module is installed and importable."
        ) from e


def save_results(results: Dict[str, Any], output_path: str):
    """Save validation results to file.

    Args:
        results: Validation results dictionary
        output_path: Path to output file
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    logger.info(f"Results saved to {output_path}")


def load_results(input_path: str) -> Dict[str, Any]:
    """Load validation results from file.

    Args:
        input_path: Path to input file

    Returns:
        Loaded results dictionary
    """
    with open(input_path, "r") as f:
        return json.load(f)


async def run_full_validation(
    classifier: Any,
    lower_threshold: float = None,  # Uses DEFAULT_CONFIG.individual_threshold if None
    upper_threshold: float = None,  # Uses DEFAULT_CONFIG.small_team_threshold if None
    store_neo4j: bool = False
) -> Dict[str, Any]:
    """Run full validation suite.

    Args:
        classifier: TeamSizeClassifier instance
        lower_threshold: Lower complexity threshold (default from config: 0.21)
        upper_threshold: Upper complexity threshold (default from config: 0.64)
        store_neo4j: Whether to store results in Neo4j

    Returns:
        Validation results dictionary
    """
    from tools.kurultai.complexity_config import DEFAULT_CONFIG

    # Use config defaults if not specified
    lower_threshold = lower_threshold if lower_threshold is not None else DEFAULT_CONFIG.individual_threshold
    upper_threshold = upper_threshold if upper_threshold is not None else DEFAULT_CONFIG.small_team_threshold

    logger.info("Running full validation suite")
    logger.info(f"Thresholds: lower={lower_threshold:.2f}, upper={upper_threshold:.2f}")

    # Create Neo4j client if needed
    neo4j_client = None
    if store_neo4j:
        try:
            # Require NEO4J_PASSWORD to be set - no default for security
            neo4j_password = os.getenv("NEO4J_PASSWORD")
            if not neo4j_password:
                raise SystemExit(
                    "NEO4J_PASSWORD environment variable required for Neo4j storage. "
                    "Set it in your .env file or environment."
                )
            from neo4j import AsyncGraphDatabase
            neo4j_client = AsyncGraphDatabase.driver(
                os.getenv("NEO4J_URI", "bolt://localhost:7687"),
                auth=(
                    os.getenv("NEO4J_USER", "neo4j"),
                    neo4j_password
                )
            )
        except SystemExit:
            raise
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            logger.warning("Continuing without Neo4j storage")

    # Run validation pipeline
    pipeline = StagingValidationPipeline(classifier, neo4j_client)
    results = await pipeline.run_full_validation()

    # Close Neo4j connection
    if neo4j_client:
        await neo4j_client.close()

    return results


async def run_quick_validation_flow(classifier: Any) -> ValidationMetrics:
    """Run quick validation.

    Args:
        classifier: TeamSizeClassifier instance

    Returns:
        Validation metrics
    """
    logger.info("Running quick validation")
    return await run_quick_validation(classifier)


async def calibrate_thresholds(
    classifier: Any,
    min_precision: float = 0.90,
    min_recall: float = 0.95
) -> Dict[str, Any]:
    """Calibrate thresholds based on validation results.

    Args:
        classifier: TeamSizeClassifier instance
        min_precision: Minimum required precision
        min_recall: Minimum required recall

    Returns:
        Calibration results
    """
    logger.info("Calibrating thresholds")
    logger.info(f"Constraints: min_precision={min_precision}, min_recall={min_recall}")

    # Run validation
    framework = create_validation_suite(classifier, include_synthetic=True)
    results = await framework.run_validation_suite()

    # Calibrate
    calibrator = ThresholdCalibrator(framework, min_precision, min_recall)
    calibration = calibrator.calibrate_thresholds(results)

    # Generate A/B test suggestion
    current = framework
    current_calibration = {
        "lower_threshold": current.lower_threshold,
        "upper_threshold": current.upper_threshold
    }
    new_calibration = {
        "lower_threshold": calibration.lower_threshold,
        "upper_threshold": calibration.upper_threshold
    }

    ab_test = calibrator.suggest_ab_test(
        type('obj', (object,), current_calibration)(),
        type('obj', (object,), new_calibration)()
    )

    return {
        "current_thresholds": current_calibration,
        "recommended_thresholds": new_calibration,
        "confidence": calibration.confidence,
        "recommendation": calibration.recommendation,
        "ab_test_configuration": ab_test,
        "metrics_at_recommended": calibration.metrics_at_thresholds.to_dict() if calibration.metrics_at_thresholds else None
    }


def print_report(results: Dict[str, Any]):
    """Print validation report to console.

    Args:
        results: Validation results dictionary
    """
    print("\n" + "=" * 80)
    print("COMPLEXITY SCORING VALIDATION RESULTS")
    print("=" * 80)

    if "report" in results:
        print(results["report"])
    else:
        print(json.dumps(results, indent=2, default=str))

    print("\n" + "=" * 80)
    print("GO/NO-GO DECISION")
    print("=" * 80)

    if "recommendation" in results:
        rec = results["recommendation"]
        print(f"Decision: {rec.get('decision', 'UNKNOWN')}")
        print(f"Confidence: {rec.get('confidence', 'unknown')}")

        if rec.get("issues"):
            print("\nIssues:")
            for issue in rec["issues"]:
                print(f"  - {issue}")

        print(f"\nAction: {rec.get('action', 'No action specified')}")

        if rec.get("optimal_thresholds"):
            print("\nOptimal Thresholds:")
            print(f"  Lower: {rec['optimal_thresholds']['lower']}")
            print(f"  Upper: {rec['optimal_thresholds']['upper']}")

    print("=" * 80)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate complexity scoring for Kurultai agent teams"
    )

    parser.add_argument(
        "--full",
        action="store_true",
        help="Run full validation suite"
    )

    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run quick validation (edge cases + known simple/complex)"
    )

    parser.add_argument(
        "--calibrate",
        action="store_true",
        help="Calibrate thresholds based on validation results"
    )

    parser.add_argument(
        "--report",
        type=str,
        metavar="PATH",
        help="Generate report from saved results file"
    )

    parser.add_argument(
        "--lower",
        type=float,
        default=DEFAULT_CONFIG.individual_threshold,
        help=f"Lower complexity threshold (default: {DEFAULT_CONFIG.individual_threshold})"
    )

    parser.add_argument(
        "--upper",
        type=float,
        default=DEFAULT_CONFIG.small_team_threshold,
        help=f"Upper complexity threshold (default: {DEFAULT_CONFIG.small_team_threshold})"
    )

    parser.add_argument(
        "--min-precision",
        type=float,
        default=0.90,
        help="Minimum required precision for calibration (default: 0.90)"
    )

    parser.add_argument(
        "--min-recall",
        type=float,
        default=0.95,
        help="Minimum required recall for calibration (default: 0.95)"
    )

    parser.add_argument(
        "--output",
        type=str,
        metavar="PATH",
        help="Save results to file"
    )

    parser.add_argument(
        "--store-neo4j",
        action="store_true",
        help="Store results in Neo4j"
    )

    parser.add_argument(
        "--classifier-module",
        type=str,
        help="Python module path to classifier"
    )

    args = parser.parse_args()

    # Default to full validation if no mode specified
    if not any([args.full, args.quick, args.calibrate, args.report]):
        args.full = True

    try:
        if args.report:
            # Generate report from saved results
            results = load_results(args.report)
            print_report(results)

            # Exit based on previous decision
            rec = results.get("recommendation", {})
            if rec.get("decision") == "NO_GO":
                sys.exit(1)
            sys.exit(0)

        # Load classifier
        classifier = load_classifier(args.classifier_module)

        if args.calibrate:
            # Calibrate thresholds
            results = asyncio.run(calibrate_thresholds(
                classifier,
                args.min_precision,
                args.min_recall
            ))

            print(json.dumps(results, indent=2, default=str))

            if args.output:
                save_results(results, args.output)

        elif args.quick:
            # Run quick validation
            metrics = asyncio.run(run_quick_validation_flow(classifier))

            print("\n" + "=" * 80)
            print("QUICK VALIDATION RESULTS")
            print("=" * 80)
            print(f"Accuracy: {metrics.accuracy:.2%}")
            print(f"Precision: {metrics.precision:.2%}")
            print(f"Recall: {metrics.recall:.2%}")
            print(f"F1 Score: {metrics.f1_score:.2%}")
            print(f"Mean Absolute Error: {metrics.mean_absolute_error:.4f}")
            print("=" * 80)

            # Exit with error if accuracy is too low
            if metrics.accuracy < 0.85:
                logger.error("Accuracy below 85% - validation failed")
                sys.exit(1)

        elif args.full:
            # Run full validation
            results = asyncio.run(run_full_validation(
                classifier,
                args.lower,
                args.upper,
                args.store_neo4j
            ))

            print_report(results)

            if args.output:
                save_results(results, args.output)

            # Exit based on recommendation
            rec = results.get("recommendation", {})
            if rec.get("decision") == "NO_GO":
                sys.exit(1)

        sys.exit(0)

    except Exception as e:
        logger.exception("Validation failed with error")
        sys.exit(2)


if __name__ == "__main__":
    main()
