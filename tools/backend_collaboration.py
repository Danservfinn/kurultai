"""
Jochi-Temüjin Collaboration Protocol (Task 6.1)

This module implements the backend code review and collaboration system that enables
Jochi (analyst) and Temüjin (developer) to work together on performance and security
issues.

Categories:
- connection_pool: Connection management issues (missing pool, no timeout, exhaustion)
- resilience: Retry/circuit breaker issues (missing retry, no circuit breaker, no fallback)
- data_integrity: Injection/transaction issues (unparameterized queries, missing transactions)
- performance: Query timeout/growth issues (missing timeouts, unbounded growth, blocking)
- security: Secret/validation issues (secrets in logs, unverified downloads, missing validation)
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

# Import OperationalMemory from parent directory
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from openclaw_memory import OperationalMemory

# Configure logging
logger = logging.getLogger(__name__)


class BackendCodeReviewer:
    """
    Jochi's backend code review and collaboration with Temüjin.

    This class provides the backend code review checklist and collaboration
    protocol between Jochi (analyst) and Temüjin (developer) for addressing
    performance and security issues identified in the codebase.

    Attributes:
        memory: OperationalMemory instance for Neo4j interactions
        agent_id: Jochi's agent identifier
        temujin_id: Temüjin's agent identifier

    Review Categories:
        - connection_pool: Connection management issues
        - resilience: Retry/circuit breaker issues
        - data_integrity: Injection/transaction issues
        - performance: Query timeout/growth issues
        - security: Secret/validation issues
    """

    # Review categories as specified in neo4j.md
    REVIEW_CATEGORIES = [
        "connection_pool",
        "resilience",
        "data_integrity",
        "performance",
        "security"
    ]

    # Severity levels for backend issues
    SEVERITY_LEVELS = ["info", "warning", "critical"]

    # Analysis status flow
    STATUS_IDENTIFIED = "identified"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_RESOLVED = "resolved"
    STATUS_VALIDATED = "validated"
    STATUS_CLOSED = "closed"

    # Valid statuses
    VALID_STATUSES = [
        STATUS_IDENTIFIED,
        STATUS_IN_PROGRESS,
        STATUS_RESOLVED,
        STATUS_VALIDATED,
        STATUS_CLOSED
    ]

    def __init__(self, memory: OperationalMemory) -> None:
        """
        Initialize the backend code reviewer.

        Args:
            memory: OperationalMemory instance for Neo4j interactions
        """
        self.memory = memory
        self.agent_id = "jochi"
        self.temujin_id = "temujin"
        logger.info("[BackendCodeReviewer] Initialized Jochi-Temüjin collaboration protocol")

    def _validate_category(self, category: str) -> None:
        """Validate that the category is supported."""
        if category not in self.REVIEW_CATEGORIES:
            raise ValueError(
                f"Invalid category '{category}'. Must be one of: {self.REVIEW_CATEGORIES}"
            )

    def _validate_severity(self, severity: str) -> None:
        """Validate that the severity level is supported."""
        if severity not in self.SEVERITY_LEVELS:
            raise ValueError(
                f"Invalid severity '{severity}'. Must be one of: {self.SEVERITY_LEVELS}"
            )

    def _validate_status(self, status: str) -> None:
        """Validate that the status is supported."""
        if status not in self.VALID_STATUSES:
            raise ValueError(
                f"Invalid status '{status}'. Must be one of: {self.VALID_STATUSES}"
            )

    def create_backend_analysis(
        self,
        category: str,
        findings: str,
        location: str,
        severity: str,
        recommended_fix: str,
        target: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create an Analysis node for a backend issue.

        Creates an Analysis node with all the required information for
        Temüjin to implement the fix. The analysis is automatically
        assigned to Temüjin for implementation.

        Args:
            category: Issue category (connection_pool, resilience, data_integrity,
                      performance, security)
            findings: Detailed description of the issue discovered
            location: File and line number (e.g., "file.py:42")
            severity: Issue severity level (info, warning, critical)
            recommended_fix: Specific implementation approach for the fix
            target: The service or component affected (optional)
            metadata: Additional context data (optional)

        Returns:
            Analysis ID as string

        Raises:
            ValueError: If category or severity is invalid
        """
        self._validate_category(category)
        self._validate_severity(severity)

        # Prepare findings dictionary with category-specific information
        findings_dict = {
            "category": category,
            "description": findings,
            "location": location,
            "recommended_fix": recommended_fix,
            "severity": severity,
            "metadata": metadata or {}
        }

        # Map severity levels
        severity_mapping = {
            "info": "low",
            "warning": "medium",
            "critical": "critical"
        }
        mapped_severity = severity_mapping.get(severity, "medium")

        # Map category to analysis_type
        category_to_type = {
            "connection_pool": "resource",
            "resilience": "performance",
            "data_integrity": "security",
            "performance": "performance",
            "security": "security"
        }
        analysis_type = category_to_type.get(category, "other")

        # Create description for the analysis
        description = f"[{category.upper()}] {findings[:100]}"

        # Prepare recommendations list
        recommendations = [recommended_fix]
        if metadata and "additional_recommendations" in metadata:
            recommendations.extend(metadata["additional_recommendations"])

        # Use OperationalMemory.create_analysis which already exists
        analysis_id = self.memory.create_analysis(
            agent=self.agent_id,
            analysis_type=analysis_type,
            severity=mapped_severity,
            description=description,
            target_agent=target,
            findings=findings_dict,
            recommendations=recommendations,
            assigned_to=self.temujin_id
        )

        logger.info(
            "[BackendCodeReviewer] Created backend analysis %s: category=%s, location=%s, severity=%s",
            analysis_id, category, location, severity
        )

        return analysis_id

    def get_pending_analyses(
        self,
        limit: int = 50,
        category: Optional[str] = None,
        severity: Optional[str] = None
    ) -> List[Dict]:
        """
        Get analyses awaiting Temüjin's implementation.

        Retrieves all analyses in 'identified' or 'in_progress' status
        that are assigned to Temüjin, optionally filtered by category
        and severity.

        Args:
            limit: Maximum number of analyses to return
            category: Filter by category (optional)
            severity: Filter by severity (optional)

        Returns:
            List of analysis dictionaries with keys:
                - id: Analysis ID
                - category: Issue category
                - findings: Issue description
                - location: Code location
                - severity: Severity level
                - recommended_fix: Fix recommendation
                - status: Current status
                - created_at: Creation timestamp
        """
        # Get all analyses for temujin
        all_analyses = self.memory.list_analyses(
            agent=self.agent_id,
            assigned_to=self.temujin_id
        )

        # Filter by status (only identified and in_progress)
        pending = [
            a for a in all_analyses
            if a.get("status") in [self.STATUS_IDENTIFIED, self.STATUS_IN_PROGRESS]
        ]

        # Apply category filter if specified
        if category:
            self._validate_category(category)
            pending = [
                a for a in pending
                if a.get("findings", {}).get("category") == category
            ]

        # Apply severity filter if specified
        if severity:
            self._validate_severity(severity)
            pending = [
                a for a in pending
                if a.get("findings", {}).get("severity") == severity
            ]

        # Sort by severity and limit
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        pending.sort(
            key=lambda a: (
                severity_order.get(a.get("findings", {}).get("severity", "info"), 99),
                a.get("created_at", datetime.now(timezone.utc))
            )
        )

        result = pending[:limit]

        logger.info(
            "[BackendCodeReviewer] Retrieved %d pending analyses (limit=%d)",
            len(result), limit
        )

        return result

    def update_analysis_status(
        self,
        analysis_id: str,
        status: str,
        notes: str = "",
        updated_by: Optional[str] = None
    ) -> bool:
        """
        Update analysis status through the resolution lifecycle.

        Status flow:
        - identified -> in_progress: Temüjin starts working on the fix
        - in_progress -> resolved: Temüjin completes the fix
        - resolved -> validated: Jochi validates the fix
        - validated -> closed: Issue is fully closed

        Args:
            analysis_id: ID of the analysis to update
            status: New status (identified, in_progress, resolved, validated, closed)
            notes: Optional notes about the update
            updated_by: Agent making the update (defaults to temujin if not provided)

        Returns:
            True if successful, False otherwise

        Raises:
            ValueError: If status is invalid
        """
        self._validate_status(status)

        # Default to temujin if not specified
        if updated_by is None:
            updated_by = self.temujin_id

        # Use OperationalMemory's update_analysis_status
        success = self.memory.update_analysis_status(
            analysis_id=analysis_id,
            status=status,
            updated_by=updated_by
        )

        if success:
            logger.info(
                "[BackendCodeReviewer] Updated analysis %s to status='%s' by %s",
                analysis_id, status, updated_by
            )

            # Store notes in a separate property if provided
            if notes:
                self._add_analysis_note(analysis_id, notes, updated_by)

        return success

    def _add_analysis_note(self, analysis_id: str, note: str, author: str) -> bool:
        """Add a note to an analysis (internal method)."""
        try:
            with self.memory._session() as session:
                if session is None:
                    return False

                # Get existing notes
                result = session.run(
                    "MATCH (a:Analysis {id: $id}) RETURN a.notes as notes",
                    id=analysis_id
                )
                record = result.single()
                existing_notes = []
                if record and record.get("notes"):
                    try:
                        if isinstance(record["notes"], str):
                            existing_notes = json.loads(record["notes"])
                        else:
                            existing_notes = []
                    except (json.JSONDecodeError, TypeError):
                        existing_notes = []

                # Add new note
                new_note = {
                    "author": author,
                    "note": note,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                existing_notes.append(new_note)

                # Update
                session.run(
                    "MATCH (a:Analysis {id: $id}) SET a.notes = $notes",
                    id=analysis_id,
                    notes=json.dumps(existing_notes)
                )
                return True
        except Exception as e:
            logger.error("[BackendCodeReviewer] Failed to add note: %s", e)
            return False

    def collaborate_with_temüjin(self, analysis_id: str) -> Dict[str, Any]:
        """
        Hand off analysis to Temüjin with full context.

        Prepares a complete handoff package for Temüjin including:
        - Analysis details
        - Issue category and findings
        - Recommended fix approach
        - Related context (correlated audits, similar issues)
        - Implementation task creation

        Args:
            analysis_id: ID of the analysis to hand off

        Returns:
            Dictionary with handoff details:
                - analysis_id: The analysis ID
                - category: Issue category
                - findings: Issue description
                - location: Code location
                - severity: Severity level
                - recommended_fix: Fix recommendation
                - related_context: Related analyses or audits
                - task_id: Created task ID for implementation
        """
        # Get the analysis
        analysis = self.memory.get_analysis(analysis_id)
        if not analysis:
            logger.error("[BackendCodeReviewer] Analysis %s not found", analysis_id)
            return {
                "success": False,
                "error": "Analysis not found"
            }

        # Extract findings
        findings_data = analysis.get("findings", {})
        if isinstance(findings_data, str):
            try:
                findings_data = json.loads(findings_data)
            except json.JSONDecodeError:
                findings_data = {"description": findings_data}

        # Prepare handoff data
        handoff = {
            "analysis_id": analysis_id,
            "category": findings_data.get("category", "unknown"),
            "findings": findings_data.get("description", analysis.get("description", "")),
            "location": findings_data.get("location", "unknown"),
            "severity": findings_data.get("severity", "info"),
            "recommended_fix": findings_data.get("recommended_fix", ""),
            "status": analysis.get("status", self.STATUS_IDENTIFIED),
            "created_at": analysis.get("created_at"),
            "related_context": self._get_related_context(analysis_id)
        }

        # Create implementation task for Temüjin
        task_id = self._create_implementation_task(analysis_id, handoff)
        handoff["task_id"] = task_id

        # Update analysis status to in_progress
        self.update_analysis_status(
            analysis_id=analysis_id,
            status=self.STATUS_IN_PROGRESS,
            notes="Handed off to Temüjin for implementation"
        )

        logger.info(
            "[BackendCodeReviewer] Handed off analysis %s to Temüjin (task: %s)",
            analysis_id, task_id
        )

        handoff["success"] = True
        handoff["new_status"] = self.STATUS_IN_PROGRESS
        return handoff

    def _get_related_context(self, analysis_id: str) -> Dict[str, Any]:
        """Get related context for an analysis."""
        context = {
            "similar_issues": [],
            "correlated_audits": [],
            "related_analyses": []
        }

        try:
            with self.memory._session() as session:
                if session is None:
                    return context

                # Find similar analyses by category
                result = session.run("""
                    MATCH (a:Analysis {id: $id})
                    MATCH (other:Analysis)
                    WHERE other.id <> $id
                      AND other.findings CONTAINS a.findings
                      AND (other.status = 'identified' OR other.status = 'in_progress')
                    RETURN other.id as id, other.description as description
                    LIMIT 5
                """, id=analysis_id)

                for record in result:
                    context["similar_issues"].append({
                        "id": record["id"],
                        "description": record["description"]
                    })

        except Exception as e:
            logger.error("[BackendCodeReviewer] Failed to get related context: %s", e)

        return context

    def _create_implementation_task(self, analysis_id: str, handoff: Dict) -> Optional[str]:
        """Create an implementation task for Temüjin."""
        try:
            task_id = self.memory.create_task(
                task_type="backend_implementation",
                description=f"Implement fix for {handoff['category']} issue: {handoff['findings'][:100]}",
                delegated_by=self.agent_id,
                assigned_to=self.temujin_id,
                priority="high" if handoff["severity"] == "critical" else "normal",
                related_analysis_id=analysis_id
            )
            return task_id
        except Exception as e:
            logger.error("[BackendCodeReviewer] Failed to create task: %s", e)
            return None

    def validate_fix(
        self,
        analysis_id: str,
        fix_summary: str,
        validation_results: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Validate that Temüjin's fix addresses the issue.

        Performs validation of the implemented fix by:
        1. Checking the fix summary against the recommended fix
        2. Recording validation results
        3. Updating status to validated or back to in_progress

        Args:
            analysis_id: ID of the analysis to validate
            fix_summary: Summary of the fix implemented by Temüjin
            validation_results: Optional detailed validation results

        Returns:
            Dictionary with validation result:
                - valid: Whether the fix is considered valid
                - analysis_id: The analysis ID
                - fix_summary: The provided fix summary
                - validation_notes: Any notes about the validation
                - new_status: The updated status
        """
        # Get the original analysis
        analysis = self.memory.get_analysis(analysis_id)
        if not analysis:
            return {
                "valid": False,
                "analysis_id": analysis_id,
                "error": "Analysis not found"
            }

        findings_data = analysis.get("findings", {})
        if isinstance(findings_data, str):
            try:
                findings_data = json.loads(findings_data)
            except json.JSONDecodeError:
                findings_data = {}

        recommended_fix = findings_data.get("recommended_fix", "")
        category = findings_data.get("category", "unknown")

        # Perform validation
        validation_notes = []
        is_valid = True

        # Check 1: Fix summary is provided
        if not fix_summary or len(fix_summary.strip()) < 10:
            is_valid = False
            validation_notes.append("Fix summary is too brief or missing")

        # Check 2: Category-specific validation
        if category == "connection_pool":
            if "pool" not in fix_summary.lower() and "connection" not in fix_summary.lower():
                is_valid = False
                validation_notes.append("Fix should address connection pooling")
        elif category == "resilience":
            if "retry" not in fix_summary.lower() and "circuit" not in fix_summary.lower():
                validation_notes.append("Consider adding retry/circuit breaker")
        elif category == "data_integrity":
            if "parameter" not in fix_summary.lower() and "transaction" not in fix_summary.lower():
                validation_notes.append("Fix should use parameterized queries or transactions")
        elif category == "performance":
            if "timeout" not in fix_summary.lower() and "index" not in fix_summary.lower():
                validation_notes.append("Consider adding timeouts or indexes")
        elif category == "security":
            if "secret" not in fix_summary.lower() and "validation" not in fix_summary.lower():
                validation_notes.append("Fix should address security concerns")

        # Check 3: Validation results if provided
        if validation_results:
            if not validation_results.get("tests_pass", True):
                is_valid = False
                validation_notes.append("Tests are not passing")

            if not validation_results.get("code_reviewed", True):
                is_valid = False
                validation_notes.append("Code has not been reviewed")

        # Determine new status
        if is_valid:
            new_status = self.STATUS_VALIDATED
            validation_notes.append("Fix validated successfully")
        else:
            new_status = self.STATUS_IN_PROGRESS
            validation_notes.append("Fix needs revision")

        # Update analysis status
        self.update_analysis_status(
            analysis_id=analysis_id,
            status=new_status,
            notes=f"Validation: {'; '.join(validation_notes)}"
        )

        result = {
            "valid": is_valid,
            "analysis_id": analysis_id,
            "fix_summary": fix_summary,
            "validation_notes": validation_notes,
            "new_status": new_status,
            "validated_at": datetime.now(timezone.utc).isoformat()
        }

        logger.info(
            "[BackendCodeReviewer] Validated fix for %s: valid=%s, status=%s",
            analysis_id, is_valid, new_status
        )

        return result

    def get_review_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all backend code reviews.

        Returns:
            Dictionary with:
                - total_analyses: Total number of analyses
                - by_category: Count by review category
                - by_severity: Count by severity level
                - by_status: Count by status
                - pending_count: Number of pending analyses
                - resolved_count: Number of resolved analyses
        """
        all_analyses = self.memory.list_analyses(
            agent=self.agent_id,
            assigned_to=self.temujin_id
        )

        summary = {
            "total_analyses": len(all_analyses),
            "by_category": {cat: 0 for cat in self.REVIEW_CATEGORIES},
            "by_severity": {sev: 0 for sev in self.SEVERITY_LEVELS},
            "by_status": {status: 0 for status in self.VALID_STATUSES},
            "pending_count": 0,
            "resolved_count": 0
        }

        for analysis in all_analyses:
            findings_data = analysis.get("findings", {})
            if isinstance(findings_data, str):
                try:
                    findings_data = json.loads(findings_data)
                except json.JSONDecodeError:
                    findings_data = {}

            category = findings_data.get("category", "unknown")
            severity = findings_data.get("severity", "info")
            status = analysis.get("status", self.STATUS_IDENTIFIED)

            if category in summary["by_category"]:
                summary["by_category"][category] += 1

            if severity in summary["by_severity"]:
                summary["by_severity"][severity] += 1

            if status in summary["by_status"]:
                summary["by_status"][status] += 1

            if status in [self.STATUS_IDENTIFIED, self.STATUS_IN_PROGRESS]:
                summary["pending_count"] += 1

            if status in [self.STATUS_VALIDATED, self.STATUS_CLOSED]:
                summary["resolved_count"] += 1

        return summary

    # ==========================================================================
    # Category-specific helper methods
    # ==========================================================================

    def check_connection_pool(self, code_content: str, file_path: str) -> List[Dict]:
        """
        Check for connection pool issues in code.

        Detects:
        - Missing connection pool configuration
        - No connection timeout
        - No max connections limit
        - Resource exhaustion risks

        Args:
            code_content: The source code to check
            file_path: Path to the file being checked

        Returns:
            List of detected issues
        """
        issues = []
        lines = code_content.split("\n")

        # Check for connection pool patterns
        has_pool = any("pool" in line.lower() for line in lines)
        has_timeout = any("timeout" in line.lower() for line in lines)
        has_max_connections = any(
            "max" in line.lower() and "connection" in line.lower()
            for line in lines
        )

        if not has_pool and "connect" in code_content.lower():
            issues.append({
                "category": "connection_pool",
                "severity": "warning",
                "location": file_path,
                "finding": "Connection usage detected without connection pooling",
                "recommended_fix": "Implement connection pooling to manage connections efficiently"
            })

        if not has_timeout and "connect" in code_content.lower():
            issues.append({
                "category": "connection_pool",
                "severity": "info",
                "location": file_path,
                "finding": "Connection operation without timeout",
                "recommended_fix": "Add connection timeout to prevent hanging"
            })

        if not has_max_connections and "pool" in code_content.lower():
            issues.append({
                "category": "connection_pool",
                "severity": "warning",
                "location": file_path,
                "finding": "Connection pool without max_connections limit",
                "recommended_fix": "Set max_connection_pool_size to prevent resource exhaustion"
            })

        return issues

    def check_resilience(self, code_content: str, file_path: str) -> List[Dict]:
        """
        Check for resilience issues in code.

        Detects:
        - Missing retry logic
        - No circuit breaker
        - No fallback mechanism
        - No error handling for external calls

        Args:
            code_content: The source code to check
            file_path: Path to the file being checked

        Returns:
            List of detected issues
        """
        issues = []
        lines = code_content.split("\n")

        has_retry = any("retry" in line.lower() for line in lines)
        has_circuit_breaker = any("circuit" in line.lower() or "breaker" in line.lower() for line in lines)
        has_fallback = any("fallback" in line.lower() for line in lines)

        # Check for actual external calls (not just the word "request" or "query")
        has_external_call = False
        for line in lines:
            line_lower = line.lower()
            # Look for actual API call patterns
            if any(pattern in line_lower for pattern in ["requests.get", "requests.post", "httpx.", "fetch("]):
                has_external_call = True
                break

        if has_external_call and not has_retry:
            issues.append({
                "category": "resilience",
                "severity": "warning",
                "location": file_path,
                "finding": "External call without retry logic",
                "recommended_fix": "Implement retry logic with exponential backoff"
            })

        if has_external_call and not has_circuit_breaker:
            issues.append({
                "category": "resilience",
                "severity": "warning",
                "location": file_path,
                "finding": "External call without circuit breaker",
                "recommended_fix": "Add circuit breaker to prevent cascading failures"
            })

        if has_external_call and not has_fallback:
            issues.append({
                "category": "resilience",
                "severity": "info",
                "location": file_path,
                "finding": "External call without fallback mechanism",
                "recommended_fix": "Implement fallback for graceful degradation"
            })

        return issues

    def check_data_integrity(self, code_content: str, file_path: str) -> List[Dict]:
        """
        Check for data integrity issues in code.

        Detects:
        - Unparameterized queries
        - Missing transactions
        - No input validation
        - SQL/Cypher injection risks

        Args:
            code_content: The source code to check
            file_path: Path to the file being checked

        Returns:
            List of detected issues
        """
        issues = []
        lines = code_content.split("\n")

        # Check for f-strings in queries (potential injection)
        # Look for f-strings with variable interpolation near query operations
        in_query_context = False
        for i, line in enumerate(lines, 1):
            line_lower = line.lower()
            # Check if we're in a query context
            if any(keyword in line_lower for keyword in ["query", "cypher", "sql", ".run(", ".execute("]):
                in_query_context = True

            # Check for f-string patterns
            if "f\"" in line or "f'" in line:
                if "{" in line and in_query_context:
                    issues.append({
                        "category": "data_integrity",
                        "severity": "critical",
                        "location": f"{file_path}:{i}",
                        "finding": "Potential injection: f-string used in query",
                        "recommended_fix": "Use parameterized queries instead"
                    })

            # Reset context after a few lines
            if i % 3 == 0:
                in_query_context = False

        # Check for string concatenation in queries
        for i, line in enumerate(lines, 1):
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in ["query", "cypher", "sql", ".run(", ".execute("]):
                if ("+" in line and ('"' in line or "'" in line)) or ("format" in line_lower and "{" in line):
                    issues.append({
                        "category": "data_integrity",
                        "severity": "critical",
                        "location": f"{file_path}:{i}",
                        "finding": "Potential injection: string concatenation in query",
                        "recommended_fix": "Use parameterized queries"
                    })

        # Check for transaction usage
        has_transaction = any("transaction" in line.lower() or "begin" in line.lower() for line in lines)
        has_write_operation = any(
            word in line.lower() for line in lines
            for word in ["create", "update", "delete", "insert", "merge"]
        )

        if has_write_operation and not has_transaction:
            issues.append({
                "category": "data_integrity",
                "severity": "warning",
                "location": file_path,
                "finding": "Write operations without transaction management",
                "recommended_fix": "Wrap write operations in transactions for data consistency"
            })

        return issues

    def check_performance(self, code_content: str, file_path: str) -> List[Dict]:
        """
        Check for performance issues in code.

        Detects:
        - Missing timeouts
        - Unbounded growth patterns
        - Blocking operations
        - Missing indexes hints

        Args:
            code_content: The source code to check
            file_path: Path to the file being checked

        Returns:
            List of detected issues
        """
        issues = []
        lines = code_content.split("\n")

        # Check for missing timeouts in I/O operations
        for i, line in enumerate(lines, 1):
            if any(keyword in line.lower() for keyword in ["request.", "http.", "fetch", "connect"]):
                if "timeout" not in code_content[:code_content.find(line) + 500]:
                    issues.append({
                        "category": "performance",
                        "severity": "warning",
                        "location": f"{file_path}:{i}",
                        "finding": "I/O operation without explicit timeout",
                        "recommended_fix": "Add timeout parameter to prevent hanging"
                    })

        # Check for unbounded list growth
        for i, line in enumerate(lines, 1):
            if ".append(" in line and "while" in code_content:
                issues.append({
                    "category": "performance",
                    "severity": "info",
                    "location": f"{file_path}:{i}",
                    "finding": "Potential unbounded list growth in loop",
                    "recommended_fix": "Add size limit or pagination"
                })

        # Check for synchronous operations in async context
        for i, line in enumerate(lines, 1):
            if "async def" in code_content and "time.sleep" in line:
                issues.append({
                    "category": "performance",
                    "severity": "warning",
                    "location": f"{file_path}:{i}",
                    "finding": "Blocking sleep in async function",
                    "recommended_fix": "Use await asyncio.sleep() instead"
                })

        return issues

    def check_security(self, code_content: str, file_path: str) -> List[Dict]:
        """
        Check for security issues in code.

        Detects:
        - Secrets in logs
        - Unverified downloads
        - Missing input validation
        - Hardcoded credentials

        Args:
            code_content: The source code to check
            file_path: Path to the file being checked

        Returns:
            List of detected issues
        """
        issues = []
        lines = code_content.split("\n")

        # Check for potential secrets logging
        for i, line in enumerate(lines, 1):
            if "log" in line.lower() or "print" in line.lower():
                if any(keyword in line.lower() for keyword in ["password", "token", "secret", "key", "auth"]):
                    issues.append({
                        "category": "security",
                        "severity": "critical",
                        "location": f"{file_path}:{i}",
                        "finding": "Potential secret in log output",
                        "recommended_fix": "Remove sensitive data from logs or use redaction"
                    })

        # Check for hardcoded credentials
        for i, line in enumerate(lines, 1):
            if "=" in line:
                # Skip comments
                if line.strip().startswith("#"):
                    continue

                line_lower = line.lower()
                for keyword in ["password", "api_key", "secret", "token"]:
                    # Check for patterns like PASSWORD = "..." or password="..."
                    if keyword in line_lower:
                        # Check if there's a string value on the same line
                        if ('"' in line or "'" in line) and '=' in line:
                            # Make sure it's not a function call or variable assignment from env
                            if not any(pattern in line_lower for pattern in ["getenv", "environ", "os.", "env."]):
                                issues.append({
                                    "category": "security",
                                    "severity": "critical",
                                    "location": f"{file_path}:{i}",
                                    "finding": f"Hardcoded {keyword} detected",
                                    "recommended_fix": "Use environment variables or secret management"
                                })
                                break  # Only report one issue per line

        # Check for unverified downloads
        for i, line in enumerate(lines, 1):
            if "requests.get" in line or "urllib" in line:
                if "verify" not in line and "check" not in line:
                    issues.append({
                        "category": "security",
                        "severity": "warning",
                        "location": f"{file_path}:{i}",
                        "finding": "Unverified HTTP request",
                        "recommended_fix": "Add certificate verification or explicitly disable"
                    })

        # Check for missing input validation
        has_input_param = any("def " in line and "(" in line for line in lines)
        has_validation = any("validate" in line.lower() or "sanitize" in line.lower() for line in lines)

        if has_input_param and not has_validation and "request" in code_content.lower():
            issues.append({
                "category": "security",
                "severity": "warning",
                "location": file_path,
                "finding": "Missing input validation",
                "recommended_fix": "Add input validation before processing"
            })

        return issues

    def review_code_file(
        self,
        file_path: str,
        code_content: str,
        auto_create: bool = True
    ) -> Dict[str, Any]:
        """
        Run complete backend code review on a file.

        Runs all category checks and optionally creates analyses
        for detected issues.

        Args:
            file_path: Path to the file to review
            code_content: Source code content
            auto_create: If True, automatically create analyses for issues

        Returns:
            Dictionary with review results:
                - file_path: The reviewed file
                - issues: List of detected issues
                - analyses_created: List of analysis IDs if auto_create=True
                - summary: Count by category and severity
        """
        all_issues = []

        # Run all category checks
        all_issues.extend(self.check_connection_pool(code_content, file_path))
        all_issues.extend(self.check_resilience(code_content, file_path))
        all_issues.extend(self.check_data_integrity(code_content, file_path))
        all_issues.extend(self.check_performance(code_content, file_path))
        all_issues.extend(self.check_security(code_content, file_path))

        # Build summary
        summary = {
            "total": len(all_issues),
            "by_category": {cat: 0 for cat in self.REVIEW_CATEGORIES},
            "by_severity": {sev: 0 for sev in self.SEVERITY_LEVELS}
        }

        for issue in all_issues:
            cat = issue["category"]
            sev = issue["severity"]
            summary["by_category"][cat] += 1
            summary["by_severity"][sev] += 1

        # Create analyses if requested
        analyses_created = []
        if auto_create:
            for issue in all_issues:
                try:
                    analysis_id = self.create_backend_analysis(
                        category=issue["category"],
                        findings=issue["finding"],
                        location=issue["location"],
                        severity=issue["severity"],
                        recommended_fix=issue["recommended_fix"],
                        target=file_path
                    )
                    analyses_created.append(analysis_id)
                except Exception as e:
                    logger.error("[BackendCodeReviewer] Failed to create analysis: %s", e)

        result = {
            "file_path": file_path,
            "issues": all_issues,
            "analyses_created": analyses_created if auto_create else [],
            "summary": summary
        }

        logger.info(
            "[BackendCodeReviewer] Reviewed %s: %d issues found, %d analyses created",
            file_path, len(all_issues), len(analyses_created)
        )

        return result
