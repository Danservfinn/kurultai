#!/usr/bin/env python3
"""
Pipeline Health Monitoring - Ogedei
Monitors the three Kurultai pipelines and alerts on anomalies.

Pipelines:
1. Message Ingestion - conversation_ingester.py
2. Extraction Pipeline - async_extractor.py
3. GDS Analytics - TemporalMarker nodes

Usage:
    python3 pipeline_health_check.py [--verbose] [--json]

Exit codes:
    0 - All pipelines healthy
    1 - One or more pipelines degraded
    2 - One or more pipelines critical
"""

import os
import sys
import json
import subprocess
import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import argparse

# Add scripts directory to path for imports
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

# Load Neo4j credentials from env file before importing
_NEO4J_ENV_FILE = os.path.expanduser("~/.openclaw/credentials/neo4j.env")
if os.path.exists(_NEO4J_ENV_FILE):
    with open(_NEO4J_ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, value = line.partition('=')
                if key.strip() not in os.environ:
                    os.environ[key.strip()] = value.strip()

try:
    from neo4j_task_tracker import get_driver, is_neo4j_available
except ImportError:
    # Fallback if neo4j_task_tracker not available
    def get_driver():
        from neo4j import GraphDatabase
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")
        if not password:
            raise EnvironmentError("NEO4J_PASSWORD environment variable not set")
        return GraphDatabase.driver(uri, auth=(user, password))

    def is_neo4j_available():
        try:
            driver = get_driver()
            with driver.session() as session:
                session.run("RETURN 1")
            return True
        except Exception:
            return False

# Configuration
LOG_DIR = Path("/Users/kublai/.openclaw/logs")
BACKUP_DIR = Path("/Users/kublai/.openclaw/backups/daily")
HEALTH_LOG = LOG_DIR / "pipeline-health.jsonl"

# Thresholds
MESSAGE_INGESTION_ALERT_HOURS = 6
EXTRACTION_BACKLOG_ALERT_THRESHOLD = 50
GDS_TEMPORAL_MARKER_ALERT_DAYS = 8


class HealthStatus(Enum):
    """Pipeline health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class PipelineCheck:
    """Result of a pipeline health check."""
    name: str
    status: HealthStatus
    message: str
    details: Dict
    timestamp: str


class PipelineHealthChecker:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.timestamp = datetime.datetime.now().isoformat()
        self.checks: List[PipelineCheck] = []
        self.overall_status = HealthStatus.HEALTHY
        self.driver = None

    def log(self, message: str, level: str = "INFO"):
        """Log a message if verbose mode is enabled."""
        if self.verbose:
            print(f"[{level}] {message}")

    def connect_to_neo4j(self) -> bool:
        """Establish connection to Neo4j."""
        if not is_neo4j_available():
            self.log("Neo4j not available", "ERROR")
            return False

        try:
            self.driver = get_driver()
            self.log("Connected to Neo4j", "INFO")
            return True
        except Exception as e:
            self.log(f"Failed to connect to Neo4j: {e}", "ERROR")
            return False

    def check_message_ingestion_freshness(self) -> PipelineCheck:
        """Check 1: Message ingestion freshness.

        Alert if newest message is older than MESSAGE_INGESTION_ALERT_HOURS.
        """
        self.log("Checking message ingestion freshness...", "INFO")

        if not self.driver:
            return PipelineCheck(
                name="message_ingestion_freshness",
                status=HealthStatus.CRITICAL,
                message="Cannot check - Neo4j not available",
                details={},
                timestamp=self.timestamp
            )

        try:
            with self.driver.session() as session:
                # Get the newest Message timestamp
                result = session.run("""
                    MATCH (m:Message)
                    WHERE m.timestamp IS NOT NULL
                    RETURN m.timestamp AS newest_timestamp
                    ORDER BY m.timestamp DESC
                    LIMIT 1
                """)

                record = result.single()
                if not record:
                    return PipelineCheck(
                        name="message_ingestion_freshness",
                        status=HealthStatus.CRITICAL,
                        message="No Message nodes found",
                        details={"message_count": 0},
                        timestamp=self.timestamp
                    )

                newest_timestamp = record["newest_timestamp"]
                # Convert Neo4j DateTime to Python datetime
                if hasattr(newest_timestamp, 'to_native'):
                    newest_timestamp = newest_timestamp.to_native()
                if isinstance(newest_timestamp, str):
                    newest_timestamp = datetime.datetime.fromisoformat(newest_timestamp.replace('Z', '+00:00'))
                elif not isinstance(newest_timestamp, datetime.datetime):
                    newest_timestamp = datetime.datetime.fromtimestamp(newest_timestamp / 1000, tz=datetime.timezone.utc)

                # Make both timezone-aware or both naive
                now = datetime.datetime.now(datetime.timezone.utc)
                if newest_timestamp.tzinfo is None:
                    newest_timestamp = newest_timestamp.replace(tzinfo=datetime.timezone.utc)
                if now.tzinfo is None:
                    now = now.replace(tzinfo=datetime.timezone.utc)

                age_hours = (now - newest_timestamp).total_seconds() / 3600

                details = {
                    "newest_message_timestamp": newest_timestamp.isoformat(),
                    "age_hours": round(age_hours, 2),
                    "threshold_hours": MESSAGE_INGESTION_ALERT_HOURS
                }

                if age_hours > MESSAGE_INGESTION_ALERT_HOURS:
                    return PipelineCheck(
                        name="message_ingestion_freshness",
                        status=HealthStatus.CRITICAL,
                        message=f"Newest message is {age_hours:.1f} hours old (threshold: {MESSAGE_INGESTION_ALERT_HOURS}h)",
                        details=details,
                        timestamp=self.timestamp
                    )
                else:
                    return PipelineCheck(
                        name="message_ingestion_freshness",
                        status=HealthStatus.HEALTHY,
                        message=f"Newest message is {age_hours:.1f} hours old",
                        details=details,
                        timestamp=self.timestamp
                    )

        except Exception as e:
            self.log(f"Error checking message ingestion: {e}", "ERROR")
            return PipelineCheck(
                name="message_ingestion_freshness",
                status=HealthStatus.UNKNOWN,
                message=f"Error during check: {str(e)}",
                details={"error": str(e)},
                timestamp=self.timestamp
            )

    def check_extraction_backlog(self) -> PipelineCheck:
        """Check 2: Extraction backlog.

        Alert if PENDING task count exceeds EXTRACTION_BACKLOG_ALERT_THRESHOLD.
        """
        self.log("Checking extraction backlog...", "INFO")

        if not self.driver:
            return PipelineCheck(
                name="extraction_backlog",
                status=HealthStatus.CRITICAL,
                message="Cannot check - Neo4j not available",
                details={},
                timestamp=self.timestamp
            )

        try:
            with self.driver.session() as session:
                # Count PENDING tasks
                result = session.run("""
                    MATCH (t:Task)
                    WHERE t.status = 'PENDING'
                    RETURN count(t) AS pending_count
                """)

                record = result.single()
                pending_count = record["pending_count"] if record else 0

                details = {
                    "pending_count": pending_count,
                    "threshold": EXTRACTION_BACKLOG_ALERT_THRESHOLD
                }

                if pending_count > EXTRACTION_BACKLOG_ALERT_THRESHOLD:
                    return PipelineCheck(
                        name="extraction_backlog",
                        status=HealthStatus.DEGRADED,
                        message=f"{pending_count} PENDING tasks (threshold: {EXTRACTION_BACKLOG_ALERT_THRESHOLD})",
                        details=details,
                        timestamp=self.timestamp
                    )
                else:
                    return PipelineCheck(
                        name="extraction_backlog",
                        status=HealthStatus.HEALTHY,
                        message=f"{pending_count} PENDING tasks",
                        details=details,
                        timestamp=self.timestamp
                    )

        except Exception as e:
            self.log(f"Error checking extraction backlog: {e}", "ERROR")
            return PipelineCheck(
                name="extraction_backlog",
                status=HealthStatus.UNKNOWN,
                message=f"Error during check: {str(e)}",
                details={"error": str(e)},
                timestamp=self.timestamp
            )

    def check_gds_freshness(self) -> PipelineCheck:
        """Check 3: GDS (Graph Data Science) freshness.

        Alert if no TemporalMarker updated in GDS_TEMPORAL_MARKER_ALERT_DAYS.
        """
        self.log("Checking GDS freshness...", "INFO")

        if not self.driver:
            return PipelineCheck(
                name="gds_freshness",
                status=HealthStatus.CRITICAL,
                message="Cannot check - Neo4j not available",
                details={},
                timestamp=self.timestamp
            )

        try:
            with self.driver.session() as session:
                # Get the newest TemporalMarker update
                result = session.run("""
                    MATCH (tm:TemporalMarker)
                    WHERE tm.detectedAt IS NOT NULL
                    RETURN tm.detectedAt AS newest_update
                    ORDER BY tm.detectedAt DESC
                    LIMIT 1
                """)

                record = result.single()
                if not record:
                    return PipelineCheck(
                        name="gds_freshness",
                        status=HealthStatus.CRITICAL,
                        message="No TemporalMarker nodes found - GDS pipeline may not be running",
                        details={"temporal_marker_count": 0},
                        timestamp=self.timestamp
                    )

                newest_update = record["newest_update"]
                # Convert Neo4j DateTime to Python datetime
                if hasattr(newest_update, 'to_native'):
                    newest_update = newest_update.to_native()
                if isinstance(newest_update, str):
                    newest_update = datetime.datetime.fromisoformat(newest_update.replace('Z', '+00:00'))
                elif not isinstance(newest_update, datetime.datetime):
                    newest_update = datetime.datetime.fromtimestamp(newest_update / 1000, tz=datetime.timezone.utc)

                # Make both timezone-aware or both naive
                now = datetime.datetime.now(datetime.timezone.utc)
                if newest_update.tzinfo is None:
                    newest_update = newest_update.replace(tzinfo=datetime.timezone.utc)
                if now.tzinfo is None:
                    now = now.replace(tzinfo=datetime.timezone.utc)

                age_days = (now - newest_update).total_seconds() / 86400

                details = {
                    "newest_temporal_marker_update": newest_update.isoformat(),
                    "age_days": round(age_days, 2),
                    "threshold_days": GDS_TEMPORAL_MARKER_ALERT_DAYS
                }

                if age_days > GDS_TEMPORAL_MARKER_ALERT_DAYS:
                    return PipelineCheck(
                        name="gds_freshness",
                        status=HealthStatus.CRITICAL,
                        message=f"No TemporalMarker update in {age_days:.1f} days (threshold: {GDS_TEMPORAL_MARKER_ALERT_DAYS}d)",
                        details=details,
                        timestamp=self.timestamp
                    )
                else:
                    return PipelineCheck(
                        name="gds_freshness",
                        status=HealthStatus.HEALTHY,
                        message=f"Newest TemporalMarker is {age_days:.1f} days old",
                        details=details,
                        timestamp=self.timestamp
                    )

        except Exception as e:
            self.log(f"Error checking GDS freshness: {e}", "ERROR")
            return PipelineCheck(
                name="gds_freshness",
                status=HealthStatus.UNKNOWN,
                message=f"Error during check: {str(e)}",
                details={"error": str(e)},
                timestamp=self.timestamp
            )

    def check_neo4j_export(self) -> PipelineCheck:
        """Check 4: Neo4j export backup.

        Alert if no backup file from yesterday.
        """
        self.log("Checking Neo4j export backup...", "INFO")

        try:
            # Get yesterday's date
            yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
            yesterday_str = yesterday.strftime("%Y%m%d")

            # Check for backup directory from yesterday
            backup_dirs = list(BACKUP_DIR.glob(f"backup_{yesterday_str}_*"))

            if not backup_dirs:
                return PipelineCheck(
                    name="neo4j_export",
                    status=HealthStatus.CRITICAL,
                    message=f"No backup found from {yesterday.strftime('%Y-%m-%d')}",
                    details={
                        "expected_date": yesterday.strftime('%Y-%m-%d'),
                        "backup_dir": str(BACKUP_DIR),
                        "found_backup": False
                    },
                    timestamp=self.timestamp
                )

            # Check for neo4j_export.json in the backup directory
            backup_path = backup_dirs[0]
            export_file = backup_path / "neo4j_export.json"

            if not export_file.exists():
                return PipelineCheck(
                    name="neo4j_export",
                    status=HealthStatus.CRITICAL,
                    message=f"Backup directory exists but neo4j_export.json missing",
                    details={
                        "expected_date": yesterday.strftime('%Y-%m-%d'),
                        "backup_path": str(backup_path),
                        "found_backup_dir": True,
                        "found_export_file": False
                    },
                    timestamp=self.timestamp
                )

            # Check file size
            file_size = export_file.stat().st_size
            details = {
                "expected_date": yesterday.strftime('%Y-%m-%d'),
                "backup_path": str(backup_path),
                "found_backup": True,
                "file_size_bytes": file_size,
                "file_size_mb": round(file_size / 1024 / 1024, 2)
            }

            return PipelineCheck(
                name="neo4j_export",
                status=HealthStatus.HEALTHY,
                message=f"Backup found from {yesterday.strftime('%Y-%m-%d')} ({details['file_size_mb']} MB)",
                details=details,
                timestamp=self.timestamp
            )

        except Exception as e:
            self.log(f"Error checking Neo4j export: {e}", "ERROR")
            return PipelineCheck(
                name="neo4j_export",
                status=HealthStatus.UNKNOWN,
                message=f"Error during check: {str(e)}",
                details={"error": str(e)},
                timestamp=self.timestamp
            )

    def run_all_checks(self) -> Dict:
        """Run all pipeline health checks."""
        self.log("Starting pipeline health checks...", "INFO")

        # Connect to Neo4j
        if not self.connect_to_neo4j():
            # If Neo4j is unavailable, mark all Neo4j-dependent checks as CRITICAL
            self.checks = [
                PipelineCheck(
                    name="message_ingestion_freshness",
                    status=HealthStatus.CRITICAL,
                    message="Neo4j not available",
                    details={},
                    timestamp=self.timestamp
                ),
                PipelineCheck(
                    name="extraction_backlog",
                    status=HealthStatus.CRITICAL,
                    message="Neo4j not available",
                    details={},
                    timestamp=self.timestamp
                ),
                PipelineCheck(
                    name="gds_freshness",
                    status=HealthStatus.CRITICAL,
                    message="Neo4j not available",
                    details={},
                    timestamp=self.timestamp
                ),
            ]
            # Still run the backup check (doesn't require Neo4j)
            self.checks.append(self.check_neo4j_export())
        else:
            # Run all checks
            self.checks = [
                self.check_message_ingestion_freshness(),
                self.check_extraction_backlog(),
                self.check_gds_freshness(),
                self.check_neo4j_export(),
            ]

        # Determine overall status
        critical_count = sum(1 for c in self.checks if c.status == HealthStatus.CRITICAL)
        degraded_count = sum(1 for c in self.checks if c.status == HealthStatus.DEGRADED)

        if critical_count > 0:
            self.overall_status = HealthStatus.CRITICAL
        elif degraded_count > 0:
            self.overall_status = HealthStatus.DEGRADED
        else:
            self.overall_status = HealthStatus.HEALTHY

        # Build report with JSON-serializable checks
        checks_json = []
        for check in self.checks:
            checks_json.append({
                "name": check.name,
                "status": check.status.value,
                "message": check.message,
                "details": check.details,
                "timestamp": check.timestamp
            })

        report = {
            "timestamp": self.timestamp,
            "overall_status": self.overall_status.value,
            "checks": checks_json,
            "summary": {
                "total": len(self.checks),
                "healthy": sum(1 for c in self.checks if c.status == HealthStatus.HEALTHY),
                "degraded": degraded_count,
                "critical": critical_count,
                "unknown": sum(1 for c in self.checks if c.status == HealthStatus.UNKNOWN)
            }
        }

        return report

    def print_report(self, report: Dict, json_output: bool = False):
        """Print the health check report."""
        if json_output:
            print(json.dumps(report, indent=2))
        else:
            # Human-readable output
            status_icon_map = {
                HealthStatus.HEALTHY: "✓",
                HealthStatus.DEGRADED: "⚠",
                HealthStatus.CRITICAL: "✗",
                HealthStatus.UNKNOWN: "?"
            }
            status_icon = status_icon_map.get(self.overall_status, "?")

            print(f"\n[{self.timestamp}] Pipeline Health Check: {self.overall_status.value.upper()} {status_icon}\n")

            for check in self.checks:
                icon = status_icon_map.get(check.status, "?")
                print(f"  {icon} {check.name.replace('_', ' ').title()}: {check.status.value.upper()}")
                print(f"      {check.message}")
                if self.verbose and check.details:
                    for key, value in check.details.items():
                        print(f"      - {key}: {value}")
                print()

            print(f"Summary: {report['summary']['healthy']}/{report['summary']['total']} healthy")
            if report['summary']['degraded'] > 0:
                print(f"  ⚠ {report['summary']['degraded']} degraded")
            if report['summary']['critical'] > 0:
                print(f"  ✗ {report['summary']['critical']} critical")
            print()

    def save_report(self, report: Dict):
        """Save the health check report to the log file."""
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)

            # Convert checks to JSON-serializable format
            serializable_checks = []
            for check in self.checks:
                check_dict = {
                    "name": check.name,
                    "status": check.status.value,
                    "message": check.message,
                    "details": check.details,
                    "timestamp": check.timestamp
                }
                serializable_checks.append(check_dict)

            log_entry = {
                "timestamp": report["timestamp"],
                "overall_status": report["overall_status"] if isinstance(report["overall_status"], str) else report["overall_status"].value,
                "summary": report["summary"]
            }

            with open(HEALTH_LOG, 'a') as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            self.log(f"Failed to save report: {e}", "ERROR")

    def close(self):
        """Clean up resources."""
        if self.driver:
            self.driver.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Pipeline Health Monitoring")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of human-readable text")
    args = parser.parse_args()

    checker = PipelineHealthChecker(verbose=args.verbose)

    try:
        report = checker.run_all_checks()
        checker.print_report(report, json_output=args.json)
        checker.save_report(report)

        # Exit codes
        if report["overall_status"] == "critical":
            sys.exit(2)
        elif report["overall_status"] == "degraded":
            sys.exit(1)
        else:
            sys.exit(0)

    finally:
        checker.close()


if __name__ == "__main__":
    main()
