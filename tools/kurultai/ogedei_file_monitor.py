"""
Ögedei File Monitor - Continuous file consistency monitoring for Kurultai multi-agent system.

This module provides the OgedeiFileMonitor class that runs periodic scans of agent workspace
directories using the FileConsistencyChecker to detect conflicts and file changes.

The monitor is named after Ögedei, the operations agent in the 6-agent OpenClaw system.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from pathlib import Path

# Import FileConsistencyChecker
from tools.file_consistency import FileConsistencyChecker

# Configure logging
logger = logging.getLogger(__name__)


class OgedeiFileMonitor:
    """
    Continuous file consistency monitor for Kurultai multi-agent system.

    Runs periodic scans of agent workspace directories to detect file conflicts
    and changes. Records results to Neo4j and escalates high-severity issues.

    Attributes:
        checker: FileConsistencyChecker instance
        interval: Scan interval in seconds
        enabled: Whether monitoring is enabled
        running: Whether monitor is currently running
        last_scan_time: Timestamp of last scan
        last_severity: Highest severity from last scan
        scan_count: Total number of scans performed
        use_neo4j: Whether Neo4j storage is available
    """

    # Agent workspace directories
    AGENT_WORKSPACES = {
        "main": "data/workspace/souls/main/",          # Kublai (squad lead)
        "developer": "data/workspace/souls/developer/",  # Temujin
        "researcher": "data/workspace/souls/researcher/", # Mongke
        "analyst": "data/workspace/souls/analyst/",      # Jochi
        "writer": "data/workspace/souls/writer/",        # Chagatai
        "ops": "data/workspace/souls/ops/",              # Ogedei
    }

    # Files to monitor in each workspace
    MONITORED_FILES = [
        "heartbeat.md",
        "memory.md",
        "state.json",
        "tasks.json",
        "*.md",  # All markdown files
    ]

    def __init__(
        self,
        memory: Optional[Any] = None,
        interval: Optional[int] = None,
        enabled: Optional[bool] = None,
        base_path: str = "/Users/kurultai/molt"
    ):
        """
        Initialize the OgedeiFileMonitor.

        Args:
            memory: OperationalMemory instance (if None, will attempt to create from env)
            interval: Scan interval in seconds (default: from FILE_MONITOR_INTERVAL env or 300)
            enabled: Whether monitoring is enabled (default: from FILE_MONITOR_ENABLED env or True)
            base_path: Base path for resolving workspace directories
        """
        # Load configuration from environment
        self.interval = interval or int(os.environ.get("FILE_MONITOR_INTERVAL", "300"))
        self.enabled = enabled if enabled is not None else os.environ.get("FILE_MONITOR_ENABLED", "true").lower() == "true"
        self.base_path = base_path

        # Initialize state
        self.running = False
        self.last_scan_time: Optional[datetime] = None
        self.last_severity: str = "none"
        self.scan_count = 0
        self._stop_event = asyncio.Event()

        # Initialize memory and Neo4j connection
        self.memory = memory
        self.use_neo4j = False

        if self.memory is None:
            self.memory = self._init_memory_from_env()

        # Check if Neo4j is available
        if self.memory is not None:
            self.use_neo4j = self._check_neo4j_available()

        # Build monitored file list
        monitored_paths = self._build_monitored_paths()

        # Initialize FileConsistencyChecker
        self.checker = FileConsistencyChecker(
            memory=self.memory if self.use_neo4j else self._create_fallback_memory(),
            monitored_files=monitored_paths,
            escalation_threshold=3,
            escalation_window_seconds=self.interval * 2  # 2 scan intervals
        )

        logger.info(
            f"OgedeiFileMonitor initialized: enabled={self.enabled}, "
            f"interval={self.interval}s, neo4j={self.use_neo4j}, "
            f"monitoring {len(monitored_paths)} paths"
        )

    def _init_memory_from_env(self) -> Optional[Any]:
        """
        Initialize OperationalMemory from environment variables.

        Returns:
            OperationalMemory instance or None if not available
        """
        neo4j_uri = os.environ.get("NEO4J_URI")
        neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
        neo4j_password = os.environ.get("NEO4J_PASSWORD")

        if not neo4j_uri or not neo4j_password:
            logger.info("Neo4j credentials not found in environment - running in fallback mode")
            return None

        try:
            from openclaw_memory import OperationalMemory
            memory = OperationalMemory(
                uri=neo4j_uri,
                username=neo4j_user,
                password=neo4j_password
            )
            logger.info(f"Connected to Neo4j at {neo4j_uri}")
            return memory
        except Exception as e:
            logger.warning(f"Failed to initialize OperationalMemory: {e}")
            return None

    def _check_neo4j_available(self) -> bool:
        """
        Check if Neo4j connection is available.

        Returns:
            True if Neo4j is available
        """
        if self.memory is None:
            return False

        try:
            # Try to get a session to verify connection
            with self.memory._session() as session:
                if session is None:
                    return False
                # Run a simple query to test connection
                result = session.run("RETURN 1 as test")
                record = result.single()
                return record is not None and record["test"] == 1
        except Exception as e:
            logger.warning(f"Neo4j not available: {e}")
            return False

    def _create_fallback_memory(self) -> Any:
        """
        Create a minimal fallback memory object for FileConsistencyChecker.

        Returns:
            Fallback memory object with required methods
        """
        import uuid
        from contextlib import nullcontext

        class FallbackMemory:
            """Minimal memory object for fallback mode."""

            def _generate_id(self) -> str:
                return str(uuid.uuid4())

            def _now(self) -> datetime:
                return datetime.now(timezone.utc)

            def _session(self):
                return nullcontext(None)

        return FallbackMemory()

    def _build_monitored_paths(self) -> List[str]:
        """
        Build list of absolute file paths to monitor across all agent workspaces.

        Returns:
            List of absolute file paths (may include wildcards)
        """
        monitored = []

        for agent, workspace in self.AGENT_WORKSPACES.items():
            workspace_path = Path(self.base_path) / workspace

            for file_pattern in self.MONITORED_FILES:
                file_path = workspace_path / file_pattern
                monitored.append(str(file_path))

        return monitored

    async def scan_once(self) -> Dict[str, Any]:
        """
        Perform a single scan of all monitored files.

        Returns:
            Dict with scan results including conflicts detected and highest severity
        """
        scan_start = datetime.now(timezone.utc)
        logger.info(f"Starting file consistency scan #{self.scan_count + 1}")

        try:
            # Detect conflicts using FileConsistencyChecker
            conflicts = self.checker.detect_conflicts()

            # Calculate highest severity
            severity_levels = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
            highest_severity = "none"

            for conflict in conflicts:
                conflict_severity = conflict.get("severity", "low")
                if severity_levels.get(conflict_severity, 0) > severity_levels.get(highest_severity, 0):
                    highest_severity = conflict_severity

            # Escalate high-severity conflicts
            escalated_count = 0
            for conflict in conflicts:
                if severity_levels.get(conflict.get("severity", "low"), 0) >= severity_levels["high"]:
                    logger.warning(
                        f"HIGH-SEVERITY CONFLICT: {conflict['file_path']} - "
                        f"agents: {conflict['agents_involved']}, severity: {conflict['severity']}"
                    )
                    escalated_count += 1

            # Check and escalate threshold
            threshold_escalated = self.checker.check_and_escalate_threshold()

            # Record results to Neo4j if available
            if self.use_neo4j:
                self._record_scan_report(
                    scan_start=scan_start,
                    conflicts_detected=len(conflicts),
                    highest_severity=highest_severity,
                    escalated_count=escalated_count + len(threshold_escalated)
                )

            # Update state
            self.last_scan_time = scan_start
            self.last_severity = highest_severity
            self.scan_count += 1

            scan_duration = (datetime.now(timezone.utc) - scan_start).total_seconds()

            # Write status file for health endpoint integration
            self._write_status_file()

            logger.info(
                f"Scan #{self.scan_count} complete: {len(conflicts)} conflicts detected, "
                f"highest severity: {highest_severity}, duration: {scan_duration:.2f}s"
            )

            return {
                "scan_time": scan_start.isoformat(),
                "conflicts_detected": len(conflicts),
                "conflict_ids": [c.get("id") for c in conflicts if c.get("id")],
                "highest_severity": highest_severity,
                "escalated_count": escalated_count + len(threshold_escalated),
                "duration_seconds": scan_duration
            }

        except Exception as e:
            logger.error(f"Scan failed: {e}", exc_info=True)
            return {
                "scan_time": scan_start.isoformat(),
                "error": str(e),
                "conflicts_detected": 0,
                "highest_severity": "error"
            }

    def _record_scan_report(
        self,
        scan_start: datetime,
        conflicts_detected: int,
        highest_severity: str,
        escalated_count: int
    ) -> Optional[str]:
        """
        Record scan report to Neo4j as FileConsistencyReport node.

        Args:
            scan_start: Scan start timestamp
            conflicts_detected: Number of conflicts detected
            highest_severity: Highest severity level detected
            escalated_count: Number of escalated conflicts

        Returns:
            Report ID if successful, None otherwise
        """
        if not self.use_neo4j or self.memory is None:
            return None

        try:
            report_id = self.memory._generate_id() if hasattr(self.memory, '_generate_id') else str(__import__('uuid').uuid4())

            cypher = """
            CREATE (r:FileConsistencyReport {
                id: $report_id,
                scan_time: $scan_time,
                conflicts_detected: $conflicts_detected,
                highest_severity: $highest_severity,
                escalated_count: $escalated_count,
                scan_number: $scan_number
            })
            RETURN r.id as report_id
            """

            with self.memory._session() as session:
                if session is None:
                    return None

                result = session.run(
                    cypher,
                    report_id=report_id,
                    scan_time=scan_start,
                    conflicts_detected=conflicts_detected,
                    highest_severity=highest_severity,
                    escalated_count=escalated_count,
                    scan_number=self.scan_count + 1
                )
                record = result.single()

                if record:
                    logger.debug(f"Recorded scan report: {report_id}")
                    return record["report_id"]
                else:
                    logger.warning("Failed to record scan report: no record returned")
                    return None

        except Exception as e:
            logger.error(f"Failed to record scan report: {e}")
            return None

    async def start(self) -> None:
        """
        Start the monitoring loop.

        Runs periodic scans until stop() is called.
        """
        if not self.enabled:
            logger.info("File monitoring is disabled")
            return

        if self.running:
            logger.warning("Monitor is already running")
            return

        self.running = True
        self._stop_event.clear()

        logger.info(f"Starting file monitor with {self.interval}s interval")

        try:
            while self.running:
                # Perform scan
                await self.scan_once()

                # Wait for interval or stop signal
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self.interval
                    )
                    # Stop event was set
                    break
                except asyncio.TimeoutError:
                    # Normal timeout - continue to next scan
                    pass

        except Exception as e:
            logger.error(f"Monitor loop failed: {e}", exc_info=True)
        finally:
            self.running = False
            logger.info("File monitor stopped")

    async def stop(self) -> None:
        """
        Stop the monitoring loop gracefully.
        """
        if not self.running:
            logger.info("Monitor is not running")
            return

        logger.info("Stopping file monitor...")
        self.running = False
        self._stop_event.set()

    def _write_status_file(self):
        """Write status to /data/file-monitor-status.json for health endpoint integration."""
        import json
        status_path = os.environ.get("FILE_MONITOR_STATUS_PATH", "/data/file-monitor-status.json")
        try:
            status = self.get_status()
            tmp_path = status_path + ".tmp"
            with open(tmp_path, "w") as f:
                json.dump(status, f)
            os.replace(tmp_path, status_path)
        except Exception as e:
            logger.debug(f"Could not write status file: {e}")

    def get_status(self) -> Dict[str, Any]:
        """
        Get current monitor status.

        Returns:
            Dict with status information
        """
        return {
            "enabled": self.enabled,
            "running": self.running,
            "interval_seconds": self.interval,
            "last_scan_time": self.last_scan_time.isoformat() if self.last_scan_time else None,
            "last_severity": self.last_severity,
            "scan_count": self.scan_count,
            "neo4j_available": self.use_neo4j,
            "monitored_files_count": len(self.checker.monitored_files)
        }


# =============================================================================
# Convenience Functions
# =============================================================================

async def run_monitor(
    interval: Optional[int] = None,
    duration: Optional[int] = None
) -> None:
    """
    Run the file monitor for a specified duration or indefinitely.

    Args:
        interval: Scan interval in seconds (default: from env or 300)
        duration: Run duration in seconds (default: None = indefinite)
    """
    monitor = OgedeiFileMonitor(interval=interval)

    try:
        if duration:
            logger.info(f"Running monitor for {duration} seconds")
            await asyncio.wait_for(monitor.start(), timeout=duration)
        else:
            logger.info("Running monitor indefinitely (Ctrl+C to stop)")
            await monitor.start()
    except asyncio.TimeoutError:
        logger.info("Monitor duration expired")
    except KeyboardInterrupt:
        logger.info("Monitor interrupted by user")
    finally:
        await monitor.stop()


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    import sys

    # Configure logging for standalone execution
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Create monitor
    monitor = OgedeiFileMonitor()

    # Check command line args
    if len(sys.argv) > 1 and sys.argv[1] == "--status":
        # Show status
        status = monitor.get_status()
        print("\nOgedei File Monitor Status:")
        print("=" * 50)
        for key, value in status.items():
            print(f"  {key}: {value}")
        print()
    else:
        # Run single scan
        print("\nRunning single file consistency scan...")
        print("=" * 50)

        result = asyncio.run(monitor.scan_once())

        print("\nScan Results:")
        print("=" * 50)
        for key, value in result.items():
            print(f"  {key}: {value}")
        print()

        # Show conflict summary if Neo4j available
        if monitor.use_neo4j:
            summary = monitor.checker.get_conflict_summary()
            print("\nConflict Summary:")
            print("=" * 50)
            print(f"  Total conflicts: {summary['total']}")
            print(f"  By status: {summary['by_status']}")
            print(f"  By severity: {summary['by_severity']}")
            print()
