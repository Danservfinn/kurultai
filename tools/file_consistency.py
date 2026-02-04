"""
Ögedei File Consistency Protocol - File monitoring and conflict detection for OpenClaw.

This module provides the FileConsistencyChecker class for monitoring memory files
(heartbeat.md, memory.md, etc.) and detecting conflicts in the multi-agent system.

The protocol is named after Ögedei, the operations agent who monitors file consistency
and detects conflicts in the 6-agent OpenClaw system.
"""

import hashlib
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
from dataclasses import dataclass, field

from neo4j.exceptions import Neo4jError

# Configure logging
logger = logging.getLogger(__name__)


class FileConsistencyError(Exception):
    """Raised when a file consistency violation is detected."""
    pass


class ConflictNotFoundError(Exception):
    """Raised when a conflict ID is not found."""
    pass


@dataclass
class FileVersion:
    """Represents a version of a file."""
    id: str
    file_path: str
    agent: str
    checksum: str
    content_preview: str
    created_at: datetime


@dataclass
class FileConflict:
    """Represents a detected file conflict."""
    id: str
    file_path: str
    agents_involved: List[str]
    severity: str  # low/medium/high/critical
    status: str  # detected/escalated/resolved
    created_at: datetime
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    reason: Optional[str] = None


class FileConsistencyChecker:
    """
    File consistency monitoring and conflict detection for the OpenClaw system.

    Monitors specified files for changes, computes checksums, detects conflicts
    when multiple agents modify the same file, and escalates unresolved conflicts
to Kublai (the squad lead).

    Attributes:
        memory: OperationalMemory instance for persistence
        monitored_files: List of file paths to monitor
        escalation_threshold: Number of conflicts before escalation (default: 3)
        escalation_window_seconds: Time window for counting conflicts (default: 300)
        content_preview_length: Number of characters for content preview (default: 200)
    """

    # Default files to monitor
    DEFAULT_MONITORED_FILES = [
        "/data/workspace/memory/heartbeat.md",
        "/data/workspace/memory/memory.md",
        "/data/workspace/memory/state.json",
    ]

    # Valid severity levels
    VALID_SEVERITIES = ["low", "medium", "high", "critical"]

    # Valid conflict statuses
    VALID_STATUSES = ["detected", "escalated", "resolved"]

    def __init__(
        self,
        memory: Any,  # OperationalMemory
        monitored_files: Optional[List[str]] = None,
        escalation_threshold: int = 3,
        escalation_window_seconds: int = 300,
        content_preview_length: int = 200
    ):
        """
        Initialize the FileConsistencyChecker.

        Args:
            memory: OperationalMemory instance for Neo4j persistence
            monitored_files: List of file paths to monitor (uses default if None)
            escalation_threshold: Number of conflicts before escalating to Kublai
            escalation_window_seconds: Time window for counting conflicts
            content_preview_length: Number of characters for content preview
        """
        self.memory = memory
        self.monitored_files = monitored_files or self.DEFAULT_MONITORED_FILES.copy()
        self.escalation_threshold = escalation_threshold
        self.escalation_window_seconds = escalation_window_seconds
        self.content_preview_length = content_preview_length

        # In-memory cache of file checksums (path -> {agent: checksum})
        self._checksum_cache: Dict[str, Dict[str, str]] = {}

        logger.info(
            f"FileConsistencyChecker initialized with {len(self.monitored_files)} files, "
            f"escalation_threshold={escalation_threshold}"
        )

    def _generate_id(self) -> str:
        """Generate a unique ID using the memory's method or fallback to uuid."""
        if hasattr(self.memory, '_generate_id'):
            return self.memory._generate_id()
        import uuid
        return str(uuid.uuid4())

    def _now(self) -> datetime:
        """Get current UTC datetime using the memory's method or fallback."""
        if hasattr(self.memory, '_now'):
            return self.memory._now()
        return datetime.now(timezone.utc)

    def _session(self):
        """Get Neo4j session context manager from memory."""
        if hasattr(self.memory, '_session'):
            return self.memory._session()
        # Fallback - return a no-op context manager
        from contextlib import nullcontext
        return nullcontext(None)

    def compute_checksum(self, file_path: str) -> Optional[str]:
        """
        Compute SHA-256 checksum of file contents.

        Args:
            file_path: Path to the file

        Returns:
            Hex digest of SHA-256 hash, or None if file doesn't exist
        """
        try:
            if not os.path.exists(file_path):
                logger.debug(f"File not found for checksum: {file_path}")
                return None

            sha256_hash = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha256_hash.update(chunk)

            checksum = sha256_hash.hexdigest()
            logger.debug(f"Computed checksum for {file_path}: {checksum[:16]}...")
            return checksum

        except (IOError, OSError) as e:
            logger.error(f"Failed to compute checksum for {file_path}: {e}")
            return None

    def _read_content_preview(self, file_path: str) -> str:
        """
        Read first N characters of file content for preview.

        Args:
            file_path: Path to the file

        Returns:
            First N characters of content, or empty string if file doesn't exist
        """
        try:
            if not os.path.exists(file_path):
                return ""

            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(self.content_preview_length)
                return content

        except (IOError, OSError) as e:
            logger.error(f"Failed to read content preview for {file_path}: {e}")
            return ""

    def record_version(self, file_path: str, agent: str) -> Optional[str]:
        """
        Record a new file version in Neo4j.

        Args:
            file_path: Path to the file
            agent: Agent who made the modification

        Returns:
            Version ID if successful, None otherwise
        """
        checksum = self.compute_checksum(file_path)
        if checksum is None:
            logger.warning(f"Cannot record version: file not found {file_path}")
            return None

        version_id = self._generate_id()
        created_at = self._now()
        content_preview = self._read_content_preview(file_path)

        # Update cache
        if file_path not in self._checksum_cache:
            self._checksum_cache[file_path] = {}
        self._checksum_cache[file_path][agent] = checksum

        cypher = """
        CREATE (v:FileVersion {
            id: $version_id,
            file_path: $file_path,
            agent: $agent,
            checksum: $checksum,
            content_preview: $content_preview,
            created_at: $created_at
        })
        RETURN v.id as version_id
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: File version recording simulated for {file_path}")
                return version_id

            try:
                result = session.run(
                    cypher,
                    version_id=version_id,
                    file_path=file_path,
                    agent=agent,
                    checksum=checksum,
                    content_preview=content_preview,
                    created_at=created_at
                )
                record = result.single()
                if record:
                    logger.info(f"File version recorded: {version_id} for {file_path} by {agent}")
                    return record["version_id"]
                else:
                    raise RuntimeError("File version recording failed: no record returned")
            except Neo4jError as e:
                logger.error(f"Failed to record file version: {e}")
                raise

    def check_consistency(self, file_path: str) -> Optional[Dict]:
        """
        Check for conflicts in a specific file.

        Compares checksums from different agents to detect conflicts.

        Args:
            file_path: Path to the file to check

        Returns:
            Conflict dict if conflict detected, None otherwise
        """
        # Get recent versions from Neo4j
        versions = self.get_file_history(file_path, limit=20)

        if len(versions) < 2:
            return None

        # Group by checksum to find divergent versions
        checksums: Dict[str, List[str]] = {}
        for version in versions:
            checksum = version["checksum"]
            if checksum not in checksums:
                checksums[checksum] = []
            if version["agent"] not in checksums[checksum]:
                checksums[checksum].append(version["agent"])

        # If multiple checksums exist, we have a conflict
        if len(checksums) > 1:
            # Get the most recent version to determine "current" state
            latest_version = versions[0]

            # Collect all agents involved
            all_agents = list(set(v["agent"] for v in versions))

            # Determine severity based on number of agents and recency
            severity = self._calculate_conflict_severity(len(all_agents), versions)

            conflict = {
                "file_path": file_path,
                "agents_involved": all_agents,
                "checksums": list(checksums.keys()),
                "severity": severity,
                "latest_version": latest_version["id"],
                "detected_at": self._now().isoformat()
            }

            logger.warning(
                f"File conflict detected: {file_path} - "
                f"agents: {all_agents}, severity: {severity}"
            )
            return conflict

        return None

    def _calculate_conflict_severity(
        self,
        num_agents: int,
        versions: List[Dict]
    ) -> str:
        """
        Calculate conflict severity based on agents involved and timing.

        Args:
            num_agents: Number of agents involved
            versions: List of file versions

        Returns:
            Severity level (low/medium/high/critical)
        """
        # Critical: 4+ agents or very recent conflicting changes
        if num_agents >= 4:
            return "critical"

        # Check recency of conflicts
        now = self._now()
        recent_versions = [
            v for v in versions
            if (now - v["created_at"]).total_seconds() < 60
        ]

        if len(recent_versions) >= 3:
            return "critical"

        # High: 3 agents or recent conflicts
        if num_agents == 3 or len(recent_versions) >= 2:
            return "high"

        # Medium: 2 agents
        if num_agents == 2:
            return "medium"

        return "low"

    def detect_conflicts(self) -> List[Dict]:
        """
        Scan all monitored files for conflicts.

        Returns:
            List of conflict dicts for files with detected conflicts
        """
        conflicts = []

        for file_path in self.monitored_files:
            # Expand wildcards for agent memory files
            if "*" in file_path:
                expanded_paths = self._expand_wildcard_path(file_path)
                for expanded_path in expanded_paths:
                    conflict = self.check_consistency(expanded_path)
                    if conflict:
                        # Create conflict record in Neo4j
                        conflict_id = self._create_conflict_record(conflict)
                        conflict["id"] = conflict_id
                        conflicts.append(conflict)
            else:
                conflict = self.check_consistency(file_path)
                if conflict:
                    conflict_id = self._create_conflict_record(conflict)
                    conflict["id"] = conflict_id
                    conflicts.append(conflict)

        if conflicts:
            logger.warning(f"Detected {len(conflicts)} file conflicts")

        return conflicts

    def _expand_wildcard_path(self, pattern: str) -> List[str]:
        """
        Expand wildcard patterns in file paths.

        Args:
            pattern: File path pattern with wildcards

        Returns:
            List of matching file paths
        """
        import glob
        return glob.glob(pattern)

    def _create_conflict_record(self, conflict: Dict) -> str:
        """
        Create a FileConflict node in Neo4j.

        Args:
            conflict: Conflict dictionary

        Returns:
            Conflict ID
        """
        conflict_id = self._generate_id()
        created_at = self._now()

        cypher = """
        CREATE (c:FileConflict {
            id: $conflict_id,
            file_path: $file_path,
            agents_involved: $agents_involved,
            severity: $severity,
            status: 'detected',
            created_at: $created_at,
            resolved_at: null,
            resolved_by: null
        })
        RETURN c.id as conflict_id
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: Conflict recording simulated for {conflict['file_path']}")
                return conflict_id

            try:
                result = session.run(
                    cypher,
                    conflict_id=conflict_id,
                    file_path=conflict["file_path"],
                    agents_involved=conflict["agents_involved"],
                    severity=conflict["severity"],
                    created_at=created_at
                )
                record = result.single()
                if record:
                    logger.info(f"Conflict record created: {conflict_id}")
                    return record["conflict_id"]
                else:
                    raise RuntimeError("Conflict record creation failed")
            except Neo4jError as e:
                logger.error(f"Failed to create conflict record: {e}")
                raise

    def escalate_conflict(self, conflict_id: str, reason: str) -> bool:
        """
        Escalate a conflict to Kublai (squad lead).

        Args:
            conflict_id: ID of the conflict to escalate
            reason: Reason for escalation

        Returns:
            True if escalation successful

        Raises:
            ConflictNotFoundError: If conflict ID not found
        """
        # First check if conflict exists
        conflict = self.get_conflict(conflict_id)
        if conflict is None:
            raise ConflictNotFoundError(f"Conflict not found: {conflict_id}")

        # Update conflict status to escalated
        cypher = """
        MATCH (c:FileConflict {id: $conflict_id})
        SET c.status = 'escalated',
            c.escalation_reason = $reason,
            c.escalated_at = $escalated_at
        RETURN c.id as conflict_id
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: Conflict escalation simulated for {conflict_id}")
                return True

            try:
                result = session.run(
                    cypher,
                    conflict_id=conflict_id,
                    reason=reason,
                    escalated_at=self._now()
                )
                record = result.single()

                if record is None:
                    raise ConflictNotFoundError(f"Conflict not found: {conflict_id}")

                # Create notification for Kublai
                if hasattr(self.memory, 'create_notification'):
                    self.memory.create_notification(
                        agent="main",  # Kublai
                        type="file_conflict_escalated",
                        summary=f"File conflict escalated: {conflict['file_path']} - {reason}",
                        task_id=None
                    )

                logger.warning(f"Conflict escalated to Kublai: {conflict_id} - {reason}")
                return True

            except Neo4jError as e:
                logger.error(f"Failed to escalate conflict: {e}")
                raise

    def check_and_escalate_threshold(self) -> List[str]:
        """
        Check if conflict count exceeds threshold and escalate if needed.

        Returns:
            List of escalated conflict IDs
        """
        escalated = []

        # Count recent conflicts
        recent_conflicts = self.get_recent_conflicts(
            window_seconds=self.escalation_window_seconds
        )

        if len(recent_conflicts) >= self.escalation_threshold:
            logger.warning(
                f"Conflict threshold exceeded: {len(recent_conflicts)} conflicts "
                f"in last {self.escalation_window_seconds}s"
            )

            # Escalate all unresolved detected conflicts
            for conflict in recent_conflicts:
                if conflict["status"] == "detected":
                    try:
                        self.escalate_conflict(
                            conflict["id"],
                            f"Threshold exceeded: {len(recent_conflicts)} conflicts in window"
                        )
                        escalated.append(conflict["id"])
                    except ConflictNotFoundError:
                        pass

        return escalated

    def get_recent_conflicts(self, window_seconds: int = 300) -> List[Dict]:
        """
        Get conflicts within a time window.

        Args:
            window_seconds: Time window in seconds

        Returns:
            List of conflict dicts
        """
        since = self._now() - timedelta(seconds=window_seconds)

        cypher = """
        MATCH (c:FileConflict)
        WHERE c.created_at >= $since
        RETURN c
        ORDER BY c.created_at DESC
        """

        with self._session() as session:
            if session is None:
                return []

            try:
                result = session.run(cypher, since=since)
                return [dict(record["c"]) for record in result]
            except Neo4jError as e:
                logger.error(f"Failed to get recent conflicts: {e}")
                return []

    def resolve_conflict(
        self,
        conflict_id: str,
        resolved_by: str,
        resolution_notes: Optional[str] = None
    ) -> bool:
        """
        Mark a conflict as resolved.

        Args:
            conflict_id: ID of the conflict to resolve
            resolved_by: Agent who resolved the conflict
            resolution_notes: Optional notes about the resolution

        Returns:
            True if resolution successful

        Raises:
            ConflictNotFoundError: If conflict ID not found
        """
        resolved_at = self._now()

        cypher = """
        MATCH (c:FileConflict {id: $conflict_id})
        WHERE c.status IN ['detected', 'escalated']
        SET c.status = 'resolved',
            c.resolved_by = $resolved_by,
            c.resolved_at = $resolved_at,
            c.resolution_notes = $resolution_notes
        RETURN c.id as conflict_id
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: Conflict resolution simulated for {conflict_id}")
                return True

            try:
                result = session.run(
                    cypher,
                    conflict_id=conflict_id,
                    resolved_by=resolved_by,
                    resolved_at=resolved_at,
                    resolution_notes=resolution_notes or ""
                )
                record = result.single()

                if record is None:
                    raise ConflictNotFoundError(
                        f"Conflict not found or already resolved: {conflict_id}"
                    )

                logger.info(f"Conflict resolved: {conflict_id} by {resolved_by}")
                return True

            except Neo4jError as e:
                logger.error(f"Failed to resolve conflict: {e}")
                raise

    def get_file_history(self, file_path: str, limit: int = 10) -> List[Dict]:
        """
        Get version history for a file.

        Args:
            file_path: Path to the file
            limit: Maximum number of versions to return

        Returns:
            List of version dicts, most recent first
        """
        cypher = """
        MATCH (v:FileVersion {file_path: $file_path})
        RETURN v
        ORDER BY v.created_at DESC
        LIMIT $limit
        """

        with self._session() as session:
            if session is None:
                return []

            try:
                result = session.run(cypher, file_path=file_path, limit=limit)
                return [dict(record["v"]) for record in result]
            except Neo4jError as e:
                logger.error(f"Failed to get file history: {e}")
                return []

    def get_conflict(self, conflict_id: str) -> Optional[Dict]:
        """
        Get a conflict by ID.

        Args:
            conflict_id: Conflict ID to retrieve

        Returns:
            Conflict dict if found, None otherwise
        """
        cypher = """
        MATCH (c:FileConflict {id: $conflict_id})
        RETURN c
        """

        with self._session() as session:
            if session is None:
                return None

            try:
                result = session.run(cypher, conflict_id=conflict_id)
                record = result.single()
                return dict(record["c"]) if record else None
            except Neo4jError as e:
                logger.error(f"Failed to get conflict: {e}")
                return None

    def list_conflicts(
        self,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        file_path: Optional[str] = None
    ) -> List[Dict]:
        """
        List file conflicts with optional filters.

        Args:
            status: Filter by status ('detected', 'escalated', 'resolved')
            severity: Filter by severity ('low', 'medium', 'high', 'critical')
            file_path: Filter by file path

        Returns:
            List of conflict dicts
        """
        conditions = []
        params = {}

        if status is not None:
            conditions.append("c.status = $status")
            params["status"] = status

        if severity is not None:
            conditions.append("c.severity = $severity")
            params["severity"] = severity

        if file_path is not None:
            conditions.append("c.file_path = $file_path")
            params["file_path"] = file_path

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        cypher = f"""
        MATCH (c:FileConflict)
        {where_clause}
        RETURN c
        ORDER BY
            CASE c.severity
                WHEN 'critical' THEN 4
                WHEN 'high' THEN 3
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 1
                ELSE 0
            END DESC,
            c.created_at DESC
        """

        with self._session() as session:
            if session is None:
                return []

            try:
                result = session.run(cypher, **params)
                return [dict(record["c"]) for record in result]
            except Neo4jError as e:
                logger.error(f"Failed to list conflicts: {e}")
                return []

    def add_monitored_file(self, file_path: str) -> None:
        """
        Add a file to the monitored list.

        Args:
            file_path: Path to add
        """
        if file_path not in self.monitored_files:
            self.monitored_files.append(file_path)
            logger.info(f"Added monitored file: {file_path}")

    def remove_monitored_file(self, file_path: str) -> bool:
        """
        Remove a file from the monitored list.

        Args:
            file_path: Path to remove

        Returns:
            True if removed, False if not in list
        """
        if file_path in self.monitored_files:
            self.monitored_files.remove(file_path)
            logger.info(f"Removed monitored file: {file_path}")
            return True
        return False

    def get_monitored_files(self) -> List[str]:
        """
        Get list of monitored files (with wildcards expanded).

        Returns:
            List of file paths
        """
        expanded = []
        for file_path in self.monitored_files:
            if "*" in file_path:
                expanded.extend(self._expand_wildcard_path(file_path))
            else:
                expanded.append(file_path)
        return expanded

    def get_conflict_summary(self) -> Dict:
        """
        Get summary of conflicts by status and severity.

        Returns:
            Dict with conflict counts
        """
        cypher = """
        MATCH (c:FileConflict)
        RETURN c.status as status, c.severity as severity, count(c) as count
        """

        with self._session() as session:
            if session is None:
                return {
                    "total": 0,
                    "by_status": {"detected": 0, "escalated": 0, "resolved": 0},
                    "by_severity": {"low": 0, "medium": 0, "high": 0, "critical": 0}
                }

            try:
                result = session.run(cypher)

                by_status = {"detected": 0, "escalated": 0, "resolved": 0}
                by_severity = {"low": 0, "medium": 0, "high": 0, "critical": 0}
                total = 0

                for record in result:
                    status = record["status"]
                    severity = record["severity"]
                    count = record["count"]

                    total += count
                    if status in by_status:
                        by_status[status] += count
                    if severity in by_severity:
                        by_severity[severity] += count

                return {
                    "total": total,
                    "by_status": by_status,
                    "by_severity": by_severity
                }

            except Neo4jError as e:
                logger.error(f"Failed to get conflict summary: {e}")
                return {
                    "total": 0,
                    "by_status": {"detected": 0, "escalated": 0, "resolved": 0},
                    "by_severity": {"low": 0, "medium": 0, "high": 0, "critical": 0}
                }

    def create_indexes(self) -> List[str]:
        """
        Create recommended indexes for file consistency tracking.

        Returns:
            List of created index names
        """
        indexes = [
            ("CREATE INDEX fileversion_id_idx IF NOT EXISTS FOR (v:FileVersion) ON (v.id)", "fileversion_id_idx"),
            ("CREATE INDEX fileversion_path_idx IF NOT EXISTS FOR (v:FileVersion) ON (v.file_path)", "fileversion_path_idx"),
            ("CREATE INDEX fileversion_agent_idx IF NOT EXISTS FOR (v:FileVersion) ON (v.agent)", "fileversion_agent_idx"),
            ("CREATE INDEX fileversion_created_idx IF NOT EXISTS FOR (v:FileVersion) ON (v.created_at)", "fileversion_created_idx"),
            ("CREATE INDEX fileconflict_id_idx IF NOT EXISTS FOR (c:FileConflict) ON (c.id)", "fileconflict_id_idx"),
            ("CREATE INDEX fileconflict_path_idx IF NOT EXISTS FOR (c:FileConflict) ON (c.file_path)", "fileconflict_path_idx"),
            ("CREATE INDEX fileconflict_status_idx IF NOT EXISTS FOR (c:FileConflict) ON (c.status)", "fileconflict_status_idx"),
            ("CREATE INDEX fileconflict_severity_idx IF NOT EXISTS FOR (c:FileConflict) ON (c.severity)", "fileconflict_severity_idx"),
            ("CREATE INDEX fileconflict_created_idx IF NOT EXISTS FOR (c:FileConflict) ON (c.created_at)", "fileconflict_created_idx"),
        ]

        created = []

        with self._session() as session:
            if session is None:
                logger.warning("Cannot create indexes: Neo4j unavailable")
                return created

            for cypher, name in indexes:
                try:
                    session.run(cypher)
                    created.append(name)
                    logger.info(f"Created index: {name}")
                except Neo4jError as e:
                    if "already exists" not in str(e).lower():
                        logger.error(f"Failed to create index {name}: {e}")

        return created


# =============================================================================
# Convenience Functions
# =============================================================================

def create_file_consistency_checker(
    memory: Any,
    monitored_files: Optional[List[str]] = None,
    **kwargs
) -> FileConsistencyChecker:
    """
    Create a FileConsistencyChecker instance.

    Args:
        memory: OperationalMemory instance
        monitored_files: List of files to monitor
        **kwargs: Additional arguments for FileConsistencyChecker

    Returns:
        FileConsistencyChecker instance
    """
    return FileConsistencyChecker(
        memory=memory,
        monitored_files=monitored_files,
        **kwargs
    )


def record_file_version(
    checker: FileConsistencyChecker,
    file_path: str,
    agent: str
) -> Optional[str]:
    """
    Record a file version using the checker.

    Args:
        checker: FileConsistencyChecker instance
        file_path: Path to the file
        agent: Agent who made the modification

    Returns:
        Version ID if successful
    """
    return checker.record_version(file_path, agent)


def detect_and_escalate(checker: FileConsistencyChecker) -> Dict:
    """
    Detect conflicts and escalate if threshold exceeded.

    Args:
        checker: FileConsistencyChecker instance

    Returns:
        Dict with detection and escalation results
    """
    conflicts = checker.detect_conflicts()
    escalated = checker.check_and_escalate_threshold()

    return {
        "conflicts_detected": len(conflicts),
        "conflict_ids": [c["id"] for c in conflicts],
        "escalated_ids": escalated,
        "threshold_exceeded": len(escalated) > 0
    }


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    # Configure logging for example
    logging.basicConfig(level=logging.INFO)

    # Example usage (requires OperationalMemory)
    print("FileConsistencyChecker - Example Usage")
    print("=" * 50)

    # This would normally use a real OperationalMemory instance
    print("""
    from openclaw_memory import OperationalMemory
    from tools.file_consistency import FileConsistencyChecker

    # Initialize
    with OperationalMemory(
        uri="bolt://localhost:7687",
        username="neo4j",
        password="password"
    ) as memory:

        # Create checker
        checker = FileConsistencyChecker(
            memory=memory,
            monitored_files=[
                "/data/workspace/memory/heartbeat.md",
                "/data/workspace/memory/memory.md",
            ],
            escalation_threshold=3
        )

        # Create indexes
        checker.create_indexes()

        # Record a file version
        version_id = checker.record_version(
            file_path="/data/workspace/memory/heartbeat.md",
            agent="developer"
        )

        # Check for conflicts
        conflicts = checker.detect_conflicts()

        # If threshold exceeded, escalate
        escalated = checker.check_and_escalate_threshold()

        # Resolve a conflict
        checker.resolve_conflict(
            conflict_id="some-conflict-id",
            resolved_by="ops",
            resolution_notes="Merged changes manually"
        )
    """)
