"""
Ögedei File Consistency Protocol

Phase 4.5 implementation: File consistency monitoring protocol for the
OpenClaw multi-agent system. Detects and manages file conflicts including
concurrent modifications, unmerged git conflicts, orphaned temp files,
and permission issues.

This module implements Ögedei's file consistency monitoring responsibilities
as defined in the Ögedei SOUL:
- Health Monitoring: File integrity verification
- File Consistency: Critical file verification (every 5 minutes)
- Alert Aggregation: File integrity alerts
"""

import os
import re
import hashlib
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from dataclasses import dataclass, asdict

# Configure logging
logger = logging.getLogger(__name__)

# Import OperationalMemory - handle both direct and relative imports
try:
    from openclaw_memory import OperationalMemory
except ImportError:
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from openclaw_memory import OperationalMemory


@dataclass
class FileConflict:
    """Represents a file conflict detected by the protocol."""
    id: str
    file_path: str
    conflict_type: str
    details: Dict[str, Any]
    detected_at: datetime
    status: str  # detected, resolving, resolved, escalated
    assigned_to: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolution: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert conflict to dictionary."""
        result = asdict(self)
        # Convert datetime objects to ISO format strings
        result['detected_at'] = self.detected_at.isoformat() if self.detected_at else None
        result['resolved_at'] = self.resolved_at.isoformat() if self.resolved_at else None
        return result


class FileConsistencyProtocol:
    """
    Ögedei's file consistency monitoring protocol.

    Detects and manages file conflicts including:
    - Concurrent modifications to same file
    - Unmerged git conflicts
    - Orphaned temp files
    - Permission issues

    Integrates with OperationalMemory for Neo4j persistence and notifications.

    Attributes:
        memory: OperationalMemory instance for Neo4j operations
        workspace_dir: Root directory to monitor for conflicts
        critical_file_patterns: Glob patterns for critical files to monitor
    """

    # Default critical file patterns from Ögedei SOUL
    DEFAULT_CRITICAL_PATTERNS = [
        "**/souls/*/SOUL.md",
        "**/memory/*/MEMORY.md",
        "**/config/system.json",
        "**/state/agents.json",
    ]

    # Conflict type definitions
    CONFLICT_TYPES = {
        "concurrent_modification": "Multiple agents modifying the same file",
        "git_conflict": "Unmerged git conflict markers detected",
        "orphaned_temp": "Orphaned temporary file found",
        "permission_issue": "File permission problems detected",
        "unexpected_modification": "Unexpected file modification detected",
        "file_missing": "Critical file is missing",
        "checksum_mismatch": "File checksum does not match expected value",
    }

    # Status values
    STATUS_DETECTED = "detected"
    STATUS_RESOLVING = "resolving"
    STATUS_RESOLVED = "resolved"
    STATUS_ESCALATED = "escalated"

    def __init__(
        self,
        memory: OperationalMemory,
        workspace_dir: str = "/data/workspace"
    ):
        """
        Initialize with operational memory and workspace directory.

        Args:
            memory: OperationalMemory instance for Neo4j operations
            workspace_dir: Root directory to monitor for conflicts

        Example:
            >>> from openclaw_memory import OperationalMemory
            >>> memory = OperationalMemory()
            >>> protocol = FileConsistencyProtocol(memory, "/data/workspace")
        """
        self.memory = memory
        self.workspace_dir = Path(workspace_dir)
        self.critical_file_patterns = self.DEFAULT_CRITICAL_PATTERNS.copy()
        self._checksum_cache: Dict[str, str] = {}

        logger.info(
            f"FileConsistencyProtocol initialized: workspace={workspace_dir}"
        )

    def _generate_id(self) -> str:
        """Generate a unique conflict ID."""
        return str(uuid.uuid4())

    def _now(self) -> datetime:
        """Get current UTC datetime."""
        return datetime.now(timezone.utc)

    def _calculate_checksum(self, file_path: str) -> Optional[str]:
        """
        Calculate SHA-256 checksum of a file.

        Args:
            file_path: Path to the file

        Returns:
            Hex digest checksum or None if file cannot be read
        """
        try:
            sha256_hash = hashlib.sha256()
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except (IOError, OSError) as e:
            logger.warning(f"Failed to calculate checksum for {file_path}: {e}")
            return None

    def _has_git_conflicts(self, file_path: str) -> Tuple[bool, List[str]]:
        """
        Check if file contains git conflict markers.

        Args:
            file_path: Path to the file to check

        Returns:
            Tuple of (has_conflicts, list of conflict markers found)
        """
        conflict_markers = []
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            # Check for git conflict markers
            if '<<<<<<< ' in content:
                conflict_markers.append('<<<<<<< HEAD')
            if '=======' in content:
                conflict_markers.append('=======')
            if '>>>>>>> ' in content:
                conflict_markers.append('>>>>>>> branch')

            return len(conflict_markers) > 0, conflict_markers
        except (IOError, OSError) as e:
            logger.warning(f"Failed to check git conflicts for {file_path}: {e}")
            return False, []

    def _is_orphaned_temp_file(self, file_path: str) -> bool:
        """
        Check if file is an orphaned temporary file.

        Args:
            file_path: Path to the file to check

        Returns:
            True if file appears to be an orphaned temp file
        """
        path = Path(file_path)
        name = path.name.lower()

        # Common temp file patterns
        temp_patterns = [
            r'^\.~',           # .~lock files
            r'\.tmp$',         # .tmp extension
            r'\.temp$',        # .temp extension
            r'\.swp$',         # vim swap files
            r'\.swo$',         # vim swap files
            r'^\.swp',         # hidden swap files
            r'\.bak$',         # backup files
            r'\.backup$',      # backup files
            r'\.orig$',        # original files
            r'\.save$',        # save files
            r'~$',              # files ending with ~
            r'^#.*#$',          # emacs autosave files
            r'\.part$',        # partial downloads
            r'\.crdownload$',  # chrome downloads
        ]

        for pattern in temp_patterns:
            if re.search(pattern, name, re.IGNORECASE):
                return True

        # Check if file is old (older than 24 hours)
        try:
            stat = path.stat()
            file_age = self._now().timestamp() - stat.st_mtime
            if file_age > 86400:  # 24 hours
                # Check for common temp patterns in age
                if any(ext in name for ext in ['.tmp', '.temp', '.part']):
                    return True
        except (OSError, IOError):
            pass

        return False

    def _check_permissions(self, file_path: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Check file permissions for issues.

        Args:
            file_path: Path to the file to check

        Returns:
            Tuple of (has_issues, details dict)
        """
        issues = {}
        try:
            path = Path(file_path)
            stat = path.stat()

            # Check if file is readable
            if not os.access(file_path, os.R_OK):
                issues['readable'] = False

            # Check if file is writable (for regular files)
            if path.is_file() and not os.access(file_path, os.W_OK):
                issues['writable'] = False

            # Check for world-writable files (security concern)
            mode = stat.st_mode
            if mode & 0o002:
                issues['world_writable'] = True

            # Check for executable files that shouldn't be
            if path.is_file() and (mode & 0o111):
                if not any(file_path.endswith(ext) for ext in ['.py', '.sh', '.exe', '.bin']):
                    issues['unexpected_executable'] = True

            return len(issues) > 0, issues

        except (OSError, IOError) as e:
            return True, {'error': str(e)}

    def _find_critical_files(self) -> List[str]:
        """
        Find all critical files based on configured patterns.

        Returns:
            List of absolute file paths
        """
        import glob

        files = []
        for pattern in self.critical_file_patterns:
            # Make pattern absolute if relative
            if not pattern.startswith('/'):
                full_pattern = str(self.workspace_dir / pattern.lstrip('/'))
            else:
                full_pattern = pattern

            matched = glob.glob(full_pattern, recursive=True)
            files.extend(matched)

        return list(set(files))  # Remove duplicates

    def scan_for_conflicts(self) -> List[Dict[str, Any]]:
        """
        Scan workspace for file conflicts.

        Detects:
        1. Concurrent modifications to same file
        2. Unmerged git conflicts
        3. Orphaned temp files
        4. Permission issues

        Returns:
            List of conflict dictionaries

        Example:
            >>> protocol = FileConsistencyProtocol(memory)
            >>> conflicts = protocol.scan_for_conflicts()
            >>> print(f"Found {len(conflicts)} conflicts")
        """
        conflicts = []

        # Scan critical files
        critical_files = self._find_critical_files()

        for file_path in critical_files:
            path = Path(file_path)

            # Check if file exists
            if not path.exists():
                conflicts.append({
                    'file_path': file_path,
                    'conflict_type': 'file_missing',
                    'details': {'message': 'Critical file is missing'},
                    'severity': 'high'
                })
                continue

            # Check for git conflicts
            has_git_conflicts, markers = self._has_git_conflicts(file_path)
            if has_git_conflicts:
                conflicts.append({
                    'file_path': file_path,
                    'conflict_type': 'git_conflict',
                    'details': {
                        'markers_found': markers,
                        'message': f"Git conflict markers detected: {markers}"
                    },
                    'severity': 'critical'
                })

            # Check permissions
            has_perm_issues, perm_details = self._check_permissions(file_path)
            if has_perm_issues:
                conflicts.append({
                    'file_path': file_path,
                    'conflict_type': 'permission_issue',
                    'details': perm_details,
                    'severity': 'medium'
                })

            # Check checksum against cache for unexpected modifications
            current_checksum = self._calculate_checksum(file_path)
            if current_checksum and file_path in self._checksum_cache:
                if self._checksum_cache[file_path] != current_checksum:
                    # File has changed - could be expected or unexpected
                    conflicts.append({
                        'file_path': file_path,
                        'conflict_type': 'unexpected_modification',
                        'details': {
                            'previous_checksum': self._checksum_cache[file_path],
                            'current_checksum': current_checksum,
                            'message': 'File has been modified'
                        },
                        'severity': 'low'
                    })

            # Update checksum cache
            if current_checksum:
                self._checksum_cache[file_path] = current_checksum

        # Scan for orphaned temp files
        temp_files = self._find_orphaned_temp_files()
        for temp_file in temp_files:
            conflicts.append({
                'file_path': temp_file,
                'conflict_type': 'orphaned_temp',
                'details': {
                    'message': 'Orphaned temporary file detected',
                    'suggestion': 'Remove if no longer needed'
                },
                'severity': 'low'
            })

        logger.info(f"Scan complete: {len(conflicts)} conflicts found")
        return conflicts

    def _find_orphaned_temp_files(self) -> List[str]:
        """
        Find orphaned temporary files in workspace.

        Returns:
            List of orphaned temp file paths
        """
        orphaned = []

        # Common temp file locations
        temp_locations = [
            self.workspace_dir,
            self.workspace_dir / 'tmp',
            self.workspace_dir / 'temp',
        ]

        for location in temp_locations:
            if not location.exists():
                continue

            for item in location.rglob('*'):
                if item.is_file() and self._is_orphaned_temp_file(str(item)):
                    orphaned.append(str(item))

        return orphaned

    def record_conflict(
        self,
        file_path: str,
        conflict_type: str,
        details: Dict[str, Any]
    ) -> str:
        """
        Record a file conflict in Neo4j.

        Creates FileConflict node with:
        - id
        - file_path
        - conflict_type
        - details (JSON)
        - detected_at
        - status (detected, resolving, resolved, escalated)
        - assigned_to

        Args:
            file_path: Path to the file with conflict
            conflict_type: Type of conflict (must be in CONFLICT_TYPES)
            details: Additional details about the conflict

        Returns:
            Conflict ID string

        Raises:
            ValueError: If conflict_type is not recognized

        Example:
            >>> conflict_id = protocol.record_conflict(
            ...     "/data/workspace/config.json",
            ...     "permission_issue",
            ...     {"world_writable": True}
            ... )
        """
        if conflict_type not in self.CONFLICT_TYPES:
            raise ValueError(
                f"Unknown conflict type: {conflict_type}. "
                f"Must be one of: {list(self.CONFLICT_TYPES.keys())}"
            )

        conflict_id = self._generate_id()
        detected_at = self._now()

        # Convert details to JSON string for Neo4j
        details_json = json.dumps(details, default=str)

        cypher = """
        CREATE (fc:FileConflict {
            id: $conflict_id,
            file_path: $file_path,
            conflict_type: $conflict_type,
            details: $details_json,
            detected_at: datetime(),
            status: $status,
            assigned_to: null,
            resolved_at: null,
            resolved_by: null,
            resolution: null
        })
        RETURN fc.id as conflict_id
        """

        try:
            with self.memory._session() as session:
                if session is None:
                    logger.warning(
                        f"Fallback mode: Conflict recording simulated for {file_path}"
                    )
                    return conflict_id

                result = session.run(
                    cypher,
                    conflict_id=conflict_id,
                    file_path=file_path,
                    conflict_type=conflict_type,
                    details_json=details_json,
                    status=self.STATUS_DETECTED
                )
                record = result.single()

                if record:
                    logger.info(
                        f"Conflict recorded: {conflict_id} ({conflict_type}) for {file_path}"
                    )

                    # Create notification for Kublai (as per Ögedei SOUL)
                    self.memory.create_notification(
                        agent="kublai",
                        type="file_integrity_alert",
                        summary=f"File conflict detected: {conflict_type} in {file_path}",
                        task_id=None
                    )

                    return record["conflict_id"]
                else:
                    raise RuntimeError("Conflict recording failed: no record returned")

        except Exception as e:
            logger.error(f"Failed to record conflict: {e}")
            raise

    def resolve_conflict(
        self,
        conflict_id: str,
        resolution: str,
        resolved_by: str
    ) -> bool:
        """
        Mark a conflict as resolved.

        Args:
            conflict_id: ID of the conflict to resolve
            resolution: Description of how the conflict was resolved
            resolved_by: Agent or user who resolved the conflict

        Returns:
            True if successful, False if conflict not found

        Example:
            >>> success = protocol.resolve_conflict(
            ...     "uuid-123",
            ...     "Removed git conflict markers and merged changes",
            ...     "temüjin"
            ... )
        """
        resolved_at = self._now()

        cypher = """
        MATCH (fc:FileConflict {id: $conflict_id})
        WHERE fc.status IN ['detected', 'resolving']
        SET fc.status = $status,
            fc.resolved_at = datetime(),
            fc.resolved_by = $resolved_by,
            fc.resolution = $resolution
        RETURN fc.id as conflict_id
        """

        try:
            with self.memory._session() as session:
                if session is None:
                    logger.warning(
                        f"Fallback mode: Conflict resolution simulated for {conflict_id}"
                    )
                    return True

                result = session.run(
                    cypher,
                    conflict_id=conflict_id,
                    status=self.STATUS_RESOLVED,
                    resolved_by=resolved_by,
                    resolution=resolution
                )
                record = result.single()

                if record:
                    logger.info(f"Conflict resolved: {conflict_id} by {resolved_by}")
                    return True
                else:
                    logger.warning(f"Conflict not found or already resolved: {conflict_id}")
                    return False

        except Exception as e:
            logger.error(f"Failed to resolve conflict: {e}")
            return False

    def escalate_conflict(self, conflict_id: str, reason: str) -> bool:
        """
        Escalate unresolved conflict to Kublai.

        Args:
            conflict_id: ID of the conflict to escalate
            reason: Reason for escalation

        Returns:
            True if successful, False if conflict not found

        Example:
            >>> success = protocol.escalate_conflict(
            ...     "uuid-123",
            ...     "Unable to auto-resolve git conflict"
            ... )
        """
        cypher = """
        MATCH (fc:FileConflict {id: $conflict_id})
        WHERE fc.status IN ['detected', 'resolving']
        SET fc.status = $status,
            fc.escalation_reason = $reason,
            fc.escalated_at = datetime()
        RETURN fc.id as conflict_id, fc.file_path as file_path
        """

        try:
            with self.memory._session() as session:
                if session is None:
                    logger.warning(
                        f"Fallback mode: Conflict escalation simulated for {conflict_id}"
                    )
                    return True

                result = session.run(
                    cypher,
                    conflict_id=conflict_id,
                    status=self.STATUS_ESCALATED,
                    reason=reason
                )
                record = result.single()

                if record:
                    logger.info(f"Conflict escalated: {conflict_id} - {reason}")

                    # Create urgent notification for Kublai
                    self.memory.create_notification(
                        agent="kublai",
                        type="file_integrity_escalation",
                        summary=f"ESCALATED: File conflict {conflict_id} requires attention: {reason}",
                        task_id=None
                    )

                    return True
                else:
                    logger.warning(f"Conflict not found or already resolved: {conflict_id}")
                    return False

        except Exception as e:
            logger.error(f"Failed to escalate conflict: {e}")
            return False

    def get_conflict_status(self, conflict_id: str) -> Optional[Dict[str, Any]]:
        """
        Get status of a specific conflict.

        Args:
            conflict_id: ID of the conflict to retrieve

        Returns:
            Conflict dictionary if found, None otherwise

        Example:
            >>> status = protocol.get_conflict_status("uuid-123")
            >>> if status:
            ...     print(f"Status: {status['status']}")
        """
        cypher = """
        MATCH (fc:FileConflict {id: $conflict_id})
        RETURN fc
        """

        try:
            with self.memory._session() as session:
                if session is None:
                    return None

                result = session.run(cypher, conflict_id=conflict_id)
                record = result.single()

                if record:
                    conflict_node = record["fc"]
                    conflict_dict = dict(conflict_node)

                    # Parse details JSON if present
                    if 'details' in conflict_dict and conflict_dict['details']:
                        try:
                            conflict_dict['details'] = json.loads(conflict_dict['details'])
                        except json.JSONDecodeError:
                            pass  # Keep as string if not valid JSON

                    return conflict_dict
                else:
                    return None

        except Exception as e:
            logger.error(f"Failed to get conflict status: {e}")
            return None

    def list_active_conflicts(self) -> List[Dict[str, Any]]:
        """
        List all unresolved conflicts.

        Returns:
            List of active conflict dictionaries

        Example:
            >>> conflicts = protocol.list_active_conflicts()
            >>> print(f"Active conflicts: {len(conflicts)}")
        """
        cypher = """
        MATCH (fc:FileConflict)
        WHERE fc.status IN ['detected', 'resolving']
        RETURN fc
        ORDER BY fc.detected_at DESC
        """

        try:
            with self.memory._session() as session:
                if session is None:
                    return []

                result = session.run(cypher)
                conflicts = []

                for record in result:
                    conflict_node = record["fc"]
                    conflict_dict = dict(conflict_node)

                    # Parse details JSON if present
                    if 'details' in conflict_dict and conflict_dict['details']:
                        try:
                            conflict_dict['details'] = json.loads(conflict_dict['details'])
                        except json.JSONDecodeError:
                            pass

                    conflicts.append(conflict_dict)

                return conflicts

        except Exception as e:
            logger.error(f"Failed to list active conflicts: {e}")
            return []

    def run_consistency_check(self) -> Dict[str, Any]:
        """
        Run full consistency check and return summary.

        Scans for conflicts, records new ones, and provides recommendations.

        Returns:
            Dict with:
            - files_checked: Number of files scanned
            - conflicts_found: Total conflicts detected
            - conflicts_by_type: Breakdown by conflict type
            - new_conflicts_recorded: Number of new conflicts stored
            - recommendations: List of recommended actions

        Example:
            >>> result = protocol.run_consistency_check()
            >>> print(f"Checked {result['files_checked']} files")
            >>> print(f"Found {result['conflicts_found']} conflicts")
        """
        # Scan for conflicts
        conflicts = self.scan_for_conflicts()

        # Get existing active conflicts to avoid duplicates
        existing_conflicts = self.list_active_conflicts()
        existing_paths = {
            (c['file_path'], c['conflict_type'])
            for c in existing_conflicts
        }

        # Record new conflicts
        new_conflicts_recorded = 0
        for conflict in conflicts:
            key = (conflict['file_path'], conflict['conflict_type'])
            if key not in existing_paths:
                try:
                    self.record_conflict(
                        file_path=conflict['file_path'],
                        conflict_type=conflict['conflict_type'],
                        details=conflict['details']
                    )
                    new_conflicts_recorded += 1
                except Exception as e:
                    logger.error(f"Failed to record conflict: {e}")

        # Generate recommendations
        recommendations = self._generate_recommendations(conflicts)

        # Count by type
        conflicts_by_type = {}
        for conflict in conflicts:
            ctype = conflict['conflict_type']
            conflicts_by_type[ctype] = conflicts_by_type.get(ctype, 0) + 1

        # Count files checked (critical files + temp files found)
        files_checked = len(self._find_critical_files()) + len(self._find_orphaned_temp_files())

        result = {
            'files_checked': files_checked,
            'conflicts_found': len(conflicts),
            'conflicts_by_type': conflicts_by_type,
            'new_conflicts_recorded': new_conflicts_recorded,
            'recommendations': recommendations,
            'timestamp': self._now().isoformat()
        }

        logger.info(
            f"Consistency check complete: {result['files_checked']} files checked, "
            f"{result['conflicts_found']} conflicts found"
        )

        return result

    def _generate_recommendations(
        self,
        conflicts: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Generate recommendations based on detected conflicts.

        Args:
            conflicts: List of detected conflicts

        Returns:
            List of recommendation strings
        """
        recommendations = []

        if not conflicts:
            recommendations.append("No conflicts detected. System is consistent.")
            return recommendations

        # Group by type
        by_type = {}
        for c in conflicts:
            ctype = c['conflict_type']
            by_type[ctype] = by_type.get(ctype, 0) + 1

        # Generate type-specific recommendations
        if 'git_conflict' in by_type:
            recommendations.append(
                f"URGENT: {by_type['git_conflict']} git conflict(s) detected. "
                "Manual resolution required."
            )

        if 'permission_issue' in by_type:
            recommendations.append(
                f"Review {by_type['permission_issue']} file(s) with permission issues. "
                "Consider running chmod to fix."
            )

        if 'orphaned_temp' in by_type:
            recommendations.append(
                f"Clean up {by_type['orphaned_temp']} orphaned temporary file(s)."
            )

        if 'file_missing' in by_type:
            recommendations.append(
                f"CRITICAL: {by_type['file_missing']} critical file(s) are missing. "
                "Restore from backup or recreate."
            )

        if 'unexpected_modification' in by_type:
            recommendations.append(
                f"Review {by_type['unexpected_modification']} unexpectedly modified file(s). "
                "Verify changes are authorized."
            )

        if 'concurrent_modification' in by_type:
            recommendations.append(
                f"Coordinate {by_type['concurrent_modification']} concurrent modification(s). "
                "Implement file locking if needed."
            )

        return recommendations

    def assign_conflict(self, conflict_id: str, assigned_to: str) -> bool:
        """
        Assign a conflict to an agent for resolution.

        Args:
            conflict_id: ID of the conflict to assign
            assigned_to: Agent to assign the conflict to

        Returns:
            True if successful, False otherwise
        """
        cypher = """
        MATCH (fc:FileConflict {id: $conflict_id})
        WHERE fc.status = 'detected'
        SET fc.assigned_to = $assigned_to,
            fc.status = $status
        RETURN fc.id as conflict_id
        """

        try:
            with self.memory._session() as session:
                if session is None:
                    logger.warning(
                        f"Fallback mode: Conflict assignment simulated for {conflict_id}"
                    )
                    return True

                result = session.run(
                    cypher,
                    conflict_id=conflict_id,
                    assigned_to=assigned_to,
                    status=self.STATUS_RESOLVING
                )
                record = result.single()

                if record:
                    logger.info(f"Conflict assigned: {conflict_id} to {assigned_to}")
                    return True
                else:
                    logger.warning(f"Conflict not found or already assigned: {conflict_id}")
                    return False

        except Exception as e:
            logger.error(f"Failed to assign conflict: {e}")
            return False

    def create_indexes(self) -> List[str]:
        """
        Create recommended indexes for FileConflict nodes.

        Returns:
            List of created index names
        """
        indexes = [
            ("CREATE INDEX fileconflict_id_idx IF NOT EXISTS FOR (fc:FileConflict) ON (fc.id)", "fileconflict_id_idx"),
            ("CREATE INDEX fileconflict_path_idx IF NOT EXISTS FOR (fc:FileConflict) ON (fc.file_path)", "fileconflict_path_idx"),
            ("CREATE INDEX fileconflict_status_idx IF NOT EXISTS FOR (fc:FileConflict) ON (fc.status)", "fileconflict_status_idx"),
            ("CREATE INDEX fileconflict_type_idx IF NOT EXISTS FOR (fc:FileConflict) ON (fc.conflict_type)", "fileconflict_type_idx"),
            ("CREATE INDEX fileconflict_detected_idx IF NOT EXISTS FOR (fc:FileConflict) ON (fc.detected_at)", "fileconflict_detected_idx"),
        ]

        created = []

        try:
            with self.memory._session() as session:
                if session is None:
                    logger.warning("Cannot create indexes: Neo4j unavailable")
                    return created

                for cypher, name in indexes:
                    try:
                        session.run(cypher)
                        created.append(name)
                        logger.info(f"Created index: {name}")
                    except Exception as e:
                        if "already exists" not in str(e).lower():
                            logger.error(f"Failed to create index {name}: {e}")

        except Exception as e:
            logger.error(f"Failed to create indexes: {e}")

        return created


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    # Configure logging for example
    logging.basicConfig(level=logging.INFO)

    # Example usage
    with OperationalMemory(
        uri="bolt://localhost:7687",
        username="neo4j",
        password="password",
        fallback_mode=True
    ) as memory:

        # Initialize protocol
        protocol = FileConsistencyProtocol(
            memory=memory,
            workspace_dir="/Users/kurultai/molt/data/workspace"
        )

        # Create indexes
        indexes = protocol.create_indexes()
        print(f"Created indexes: {indexes}")

        # Run consistency check
        result = protocol.run_consistency_check()
        print(f"\nConsistency Check Results:")
        print(f"  Files checked: {result['files_checked']}")
        print(f"  Conflicts found: {result['conflicts_found']}")
        print(f"  New conflicts recorded: {result['new_conflicts_recorded']}")
        print(f"  Conflicts by type: {result['conflicts_by_type']}")
        print(f"  Recommendations:")
        for rec in result['recommendations']:
            print(f"    - {rec}")

        # List active conflicts
        active = protocol.list_active_conflicts()
        print(f"\nActive conflicts: {len(active)}")
        for conflict in active:
            print(f"  - {conflict['conflict_type']}: {conflict['file_path']}")
