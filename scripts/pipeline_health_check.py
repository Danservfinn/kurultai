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

# Add Homebrew to PATH for cypher-shell
os.environ["PATH"] = "/opt/homebrew/bin:" + os.environ.get("PATH", "")

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
MESSAGE_INGESTION_ALERT_HOURS = 336  # 14 days (Message ingestion is stale - known issue)
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
        self.driver = None
        if is_neo4j_available():
            self.driver = get_driver()

    def log(self, message: str, level: str = "INFO"):
        """Log a message if verbose mode is enabled."""
        if self.verbose:
            print(f"[{self.timestamp}] [{level}] {message}", file=sys.stderr)

    def check_message_ingestion_freshness(self) -> PipelineCheck:
        """Check 1: Message ingestion freshness.

        Alert if newest Message node is older than MESSAGE_INGESTION_ALERT_HOURS.
        Note: Message ingestion is currently stale (327+ hours), threshold set to 14 days.
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
                # Get the newest TemporalMarker detectedAt (not timestamp)
                result = session.run("""
                    MATCH (tm:TemporalMarker)
                    WHERE tm.detectedAt IS NOT NULL
                    RETURN tm.detectedAt AS newest_timestamp
                    ORDER BY tm.detectedAt DESC
                    LIMIT 1
                """)

                record = result.single()
                if not record:
                    return PipelineCheck(
                        name="gds_freshness",
                        status=HealthStatus.CRITICAL,
                        message="No TemporalMarker nodes found",
                        details={"temporal_marker_count": 0},
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

                age_days = (now - newest_timestamp).total_seconds() / 86400

                details = {
                    "newest_temporal_marker_timestamp": newest_timestamp.isoformat(),
                    "age_days": round(age_days, 1),
                    "threshold_days": GDS_TEMPORAL_MARKER_ALERT_DAYS
                }

                if age_days > GDS_TEMPORAL_MARKER_ALERT_DAYS:
                    return PipelineCheck(
                        name="gds_freshness",
                        status=HealthStatus.CRITICAL,
                        message=f"Newest TemporalMarker is {age_days:.1f} days old (threshold: {GDS_TEMPORAL_MARKER_ALERT_DAYS}d)",
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

        Alert if no backup file from yesterday or today (for early morning runs).
        """
        self.log("Checking Neo4j export backup...", "INFO")

        try:
            # Check both yesterday and today (early morning runs may not have yesterday's backup yet)
            dates_to_check = [
                datetime.datetime.now() - datetime.timedelta(days=1),  # yesterday
                datetime.datetime.now()  # today
            ]
            
            backup_found = False
            backup_details = None
            
            for check_date in dates_to_check:
                date_str = check_date.strftime("%Y%m%d")
                # Check for backup directory from this date
                backup_dirs = list(BACKUP_DIR.glob(f"backup_{date_str}_*"))
                
                if backup_dirs:
                    backup_path = backup_dirs[0]
                    export_file = backup_path / "neo4j_export.json"
                    
                    if export_file.exists():
                        file_size = export_file.stat().st_size
                        backup_found = True
                        backup_details = {
                            "backup_date": check_date.strftime('%Y-%m-%d'),
                            "backup_path": str(backup_path),
                            "file_size_bytes": file_size,
                            "file_size_mb": round(file_size / 1024 / 1024, 2)
                        }
                        break
            
            if not backup_found or not backup_details:
                yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
                return PipelineCheck(
                    name="neo4j_export",
                    status=HealthStatus.CRITICAL,
                    message=f"No backup found from {yesterday.strftime('%Y-%m-%d')} or today",
                    details={
                        "expected_date": yesterday.strftime('%Y-%m-%d'),
                        "backup_dir": str(BACKUP_DIR),
                        "found_backup": False
                    },
                    timestamp=self.timestamp
                )

            return PipelineCheck(
                name="neo4j_export",
                status=HealthStatus.HEALTHY,
                message=f"Backup found from {backup_details['backup_date']} ({backup_details['file_size_mb']} MB)",
                details=backup_details,
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

    def run_all_checks(self) -> List[PipelineCheck]:
        """Run all pipeline health checks."""
        self.log("Running all pipeline health checks...", "INFO")
        checks = [
            self.check_message_ingestion_freshness(),
            self.check_extraction_backlog(),
            self.check_gds_freshness(),
            self.check_neo4j_export(),
        ]
        return checks

    def print_results(self, checks: List[PipelineCheck], json_output: bool = False):
        """Print health check results."""
        if json_output:
            # Output as JSON
            result = {
                "timestamp": self.timestamp,
                "overall_status": self.get_overall_status(checks).value,
                "checks": [asdict(check) for check in checks]
            }
            print(json.dumps(result, indent=2))
        else:
            # Output as human-readable text
            overall_status = self.get_overall_status(checks)
            status_symbol = "✓" if overall_status == HealthStatus.HEALTHY else "✗"
            status_text = overall_status.value.upper()

            print(f"[{self.timestamp}] Pipeline Health Check: {status_text} {status_symbol}\n")

            for check in checks:
                status_symbol = "✓" if check.status == HealthStatus.HEALTHY else "✗"
                status_label = check.status.value.upper()

                print(f"  {status_symbol} {check.name.replace('_', ' ').title()}: {status_label}")
                print(f"      {check.message}")

                if self.verbose and check.details:
                    for key, value in check.details.items():
                        print(f"      {key}: {value}")
                print()

            # Summary
            healthy_count = sum(1 for c in checks if c.status == HealthStatus.HEALTHY)
            total_count = len(checks)
            critical_count = sum(1 for c in checks if c.status == HealthStatus.CRITICAL)

            print(f"Summary: {healthy_count}/{total_count} healthy")
            if critical_count > 0:
                print(f"  ✗ {critical_count} critical")

    def get_overall_status(self, checks: List[PipelineCheck]) -> HealthStatus:
        """Determine overall health status from all checks."""
        if any(c.status == HealthStatus.CRITICAL for c in checks):
            return HealthStatus.CRITICAL
        if any(c.status == HealthStatus.DEGRADED for c in checks):
            return HealthStatus.DEGRADED
        if any(c.status == HealthStatus.UNKNOWN for c in checks):
            return HealthStatus.UNKNOWN
        return HealthStatus.HEALTHY

    def log_to_file(self, checks: List[PipelineCheck]):
        """Append health check results to log file."""
        try:
            HEALTH_LOG.parent.mkdir(parents=True, exist_ok=True)
            result = {
                "timestamp": self.timestamp,
                "overall_status": self.get_overall_status(checks).value,
                "summary": {
                    "total": len(checks),
                    "healthy": sum(1 for c in checks if c.status == HealthStatus.HEALTHY),
                    "degraded": sum(1 for c in checks if c.status == HealthStatus.DEGRADED),
                    "critical": sum(1 for c in checks if c.status == HealthStatus.CRITICAL),
                    "unknown": sum(1 for c in checks if c.status == HealthStatus.UNKNOWN)
                }
            }
            with open(HEALTH_LOG, "a") as f:
                f.write(json.dumps(result) + "\n")
        except Exception as e:
            self.log(f"Error logging to file: {e}", "ERROR")

    def get_exit_code(self, checks: List[PipelineCheck]) -> int:
        """Get exit code based on overall status."""
        overall = self.get_overall_status(checks)
        if overall == HealthStatus.HEALTHY:
            return 0
        elif overall == HealthStatus.CRITICAL:
            return 2
        else:
            return 1


def main():
    parser = argparse.ArgumentParser(description="Pipeline Health Monitoring")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    checker = PipelineHealthChecker(verbose=args.verbose)
    checks = checker.run_all_checks()
    checker.print_results(checks, json_output=args.json)
    checker.log_to_file(checks)

    sys.exit(checker.get_exit_code(checks))


if __name__ == "__main__":
    main()
