"""
Test Suite for Jochi-Temüjin Collaboration Protocol (Task 6.1)

Tests the backend code review and collaboration system including:
- BackendCodeReviewer class initialization
- Analysis creation for all 5 categories
- Severity level handling
- Status tracking through resolution lifecycle
- Handoff protocol from Jochi to Temüjin
- Fix validation
- Category-specific code review checks
- Full code review workflow
"""

import pytest
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, MagicMock, patch
from contextlib import contextmanager

import sys
sys.path.insert(0, '/Users/kurultai/molt')

from openclaw_memory import OperationalMemory
from tools.backend_collaboration import BackendCodeReviewer


# =============================================================================
# Helper Classes
# =============================================================================

@contextmanager
def mock_session(return_value=None, run_result=None):
    """Context manager for mocking Neo4j sessions."""
    mock_session = MagicMock()
    if run_result:
        mock_result = MagicMock()
        if isinstance(run_result, list):
            mock_result.__iter__ = Mock(return_value=iter(run_result))
            mock_session.run.return_value = mock_result
        else:
            mock_session.run.return_value = run_result
    else:
        mock_session.run.return_value = MagicMock()
    yield mock_session


class MockMemory:
    """Helper mock class for OperationalMemory."""

    def __init__(self):
        self._analyses = {}
        self._tasks = {}
        self._analysis_counter = 0
        self._task_counter = 0
        self.fallback_mode = False

    @contextmanager
    def _session(self):
        mock_session = MagicMock()
        mock_session.run.return_value = MagicMock()
        yield mock_session

    def _generate_id(self):
        self._analysis_counter += 1
        return f"analysis-{self._analysis_counter}"

    def create_analysis(self, agent, analysis_type, severity, description,
                       target_agent=None, findings=None, recommendations=None,
                       assigned_to=None):
        analysis_id = self._generate_id()
        self._analyses[analysis_id] = {
            "id": analysis_id,
            "agent": agent,
            "analysis_type": analysis_type,
            "severity": severity,
            "description": description,
            "target_agent": target_agent,
            "findings": findings,
            "recommendations": recommendations,
            "assigned_to": assigned_to,
            "status": "identified",
            "created_at": datetime.now(timezone.utc)
        }
        return analysis_id

    def list_analyses(self, agent=None, analysis_type=None, severity=None,
                     status=None, assigned_to=None):
        results = []
        for analysis in self._analyses.values():
            if agent and analysis.get("agent") != agent:
                continue
            if assigned_to and analysis.get("assigned_to") != assigned_to:
                continue
            if status and analysis.get("status") != status:
                continue
            results.append(analysis.copy())
        return results

    def get_analysis(self, analysis_id):
        return self._analyses.get(analysis_id)

    def update_analysis_status(self, analysis_id, status, updated_by):
        if analysis_id in self._analyses:
            self._analyses[analysis_id]["status"] = status
            self._analyses[analysis_id]["updated_by"] = updated_by
            return True
        return False

    def create_task(self, task_type, description, delegated_by, assigned_to,
                   priority="normal", **kwargs):
        self._task_counter += 1
        task_id = f"task-{self._task_counter}"
        self._tasks[task_id] = {
            "id": task_id,
            "type": task_type,
            "description": description,
            "delegated_by": delegated_by,
            "assigned_to": assigned_to,
            "priority": priority,
            **kwargs
        }
        return task_id


# =============================================================================
# Test Class Initialization
# =============================================================================

class TestBackendCodeReviewerInit:
    """Tests for BackendCodeReviewer initialization."""

    def test_init_with_memory(self):
        """Test initialization with OperationalMemory."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        assert reviewer.memory is memory
        assert reviewer.agent_id == "jochi"
        assert reviewer.temujin_id == "temujin"

    def test_review_categories(self):
        """Test that all 5 review categories are defined."""
        assert "connection_pool" in BackendCodeReviewer.REVIEW_CATEGORIES
        assert "resilience" in BackendCodeReviewer.REVIEW_CATEGORIES
        assert "data_integrity" in BackendCodeReviewer.REVIEW_CATEGORIES
        assert "performance" in BackendCodeReviewer.REVIEW_CATEGORIES
        assert "security" in BackendCodeReviewer.REVIEW_CATEGORIES
        assert len(BackendCodeReviewer.REVIEW_CATEGORIES) == 5

    def test_severity_levels(self):
        """Test that all 3 severity levels are defined."""
        assert "info" in BackendCodeReviewer.SEVERITY_LEVELS
        assert "warning" in BackendCodeReviewer.SEVERITY_LEVELS
        assert "critical" in BackendCodeReviewer.SEVERITY_LEVELS
        assert len(BackendCodeReviewer.SEVERITY_LEVELS) == 3


# =============================================================================
# Test Analysis Creation
# =============================================================================

class TestCreateBackendAnalysis:
    """Tests for creating backend analyses."""

    def test_create_analysis_all_categories(self):
        """Test creating analyses for all 5 categories."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        categories = [
            "connection_pool",
            "resilience",
            "data_integrity",
            "performance",
            "security"
        ]

        for category in categories:
            analysis_id = reviewer.create_backend_analysis(
                category=category,
                findings=f"Test finding for {category}",
                location=f"{category}_file.py:42",
                severity="warning",
                recommended_fix=f"Fix for {category}"
            )
            assert analysis_id is not None
            assert analysis_id.startswith("analysis-")

            # Verify the analysis was stored
            analysis = memory.get_analysis(analysis_id)
            assert analysis is not None
            assert analysis["findings"]["category"] == category
            assert analysis["assigned_to"] == "temujin"

    def test_create_analysis_all_severities(self):
        """Test creating analyses with all severity levels."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        severities = ["info", "warning", "critical"]

        for severity in severities:
            analysis_id = reviewer.create_backend_analysis(
                category="performance",
                findings=f"Test finding for {severity}",
                location="file.py:42",
                severity=severity,
                recommended_fix="Fix it"
            )
            assert analysis_id is not None

            analysis = memory.get_analysis(analysis_id)
            assert analysis["findings"]["severity"] == severity

    def test_create_analysis_invalid_category(self):
        """Test that invalid category raises ValueError."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        with pytest.raises(ValueError, match="Invalid category"):
            reviewer.create_backend_analysis(
                category="invalid_category",
                findings="Test",
                location="file.py:42",
                severity="warning",
                recommended_fix="Fix"
            )

    def test_create_analysis_invalid_severity(self):
        """Test that invalid severity raises ValueError."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        with pytest.raises(ValueError, match="Invalid severity"):
            reviewer.create_backend_analysis(
                category="performance",
                findings="Test",
                location="file.py:42",
                severity="invalid",
                recommended_fix="Fix"
            )

    def test_create_analysis_with_metadata(self):
        """Test creating analysis with additional metadata."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        metadata = {
            "additional_recommendations": ["Also check X", "Consider Y"],
            "context": "This is important context"
        }

        analysis_id = reviewer.create_backend_analysis(
            category="security",
            findings="Secret found in logs",
            location="log_handler.py:15",
            severity="critical",
            recommended_fix="Use redaction",
            metadata=metadata
        )

        analysis = memory.get_analysis(analysis_id)
        assert analysis is not None
        assert len(analysis["recommendations"]) == 3  # 1 main + 2 additional


# =============================================================================
# Test Get Pending Analyses
# =============================================================================

class TestGetPendingAnalyses:
    """Tests for retrieving pending analyses."""

    def test_get_pending_empty(self):
        """Test getting pending analyses when none exist."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        pending = reviewer.get_pending_analyses()
        assert pending == []

    def test_get_pending_with_analyses(self):
        """Test getting pending analyses."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        # Create some analyses
        reviewer.create_backend_analysis(
            category="performance",
            findings="Slow query",
            location="db.py:42",
            severity="warning",
            recommended_fix="Add index"
        )
        reviewer.create_backend_analysis(
            category="security",
            findings="Secret in logs",
            location="log.py:15",
            severity="critical",
            recommended_fix="Redact"
        )

        pending = reviewer.get_pending_analyses()
        assert len(pending) == 2

    def test_get_pending_filter_by_category(self):
        """Test filtering pending analyses by category."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        reviewer.create_backend_analysis(
            category="performance",
            findings="Slow query",
            location="db.py:42",
            severity="warning",
            recommended_fix="Add index"
        )
        reviewer.create_backend_analysis(
            category="security",
            findings="Secret in logs",
            location="log.py:15",
            severity="critical",
            recommended_fix="Redact"
        )

        pending = reviewer.get_pending_analyses(category="security")
        assert len(pending) == 1
        assert pending[0]["findings"]["category"] == "security"

    def test_get_pending_filter_by_severity(self):
        """Test filtering pending analyses by severity."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        reviewer.create_backend_analysis(
            category="performance",
            findings="Slow query",
            location="db.py:42",
            severity="warning",
            recommended_fix="Add index"
        )
        reviewer.create_backend_analysis(
            category="security",
            findings="Secret in logs",
            location="log.py:15",
            severity="critical",
            recommended_fix="Redact"
        )

        pending = reviewer.get_pending_analyses(severity="critical")
        assert len(pending) == 1
        assert pending[0]["findings"]["severity"] == "critical"

    def test_get_pending_respects_limit(self):
        """Test that limit parameter is respected."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        # Create more analyses than the limit
        for i in range(10):
            reviewer.create_backend_analysis(
                category="performance",
                findings=f"Issue {i}",
                location=f"file.py:{i}",
                severity="warning",
                recommended_fix=f"Fix {i}"
            )

        pending = reviewer.get_pending_analyses(limit=5)
        assert len(pending) == 5


# =============================================================================
# Test Update Analysis Status
# =============================================================================

class TestUpdateAnalysisStatus:
    """Tests for updating analysis status."""

    def test_update_status_identified_to_in_progress(self):
        """Test updating status from identified to in_progress."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        analysis_id = reviewer.create_backend_analysis(
            category="performance",
            findings="Slow query",
            location="db.py:42",
            severity="warning",
            recommended_fix="Add index"
        )

        success = reviewer.update_analysis_status(
            analysis_id=analysis_id,
            status="in_progress",
            notes="Started working on fix"
        )

        assert success is True

        analysis = memory.get_analysis(analysis_id)
        assert analysis["status"] == "in_progress"

    def test_update_status_to_resolved(self):
        """Test updating status to resolved."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        analysis_id = reviewer.create_backend_analysis(
            category="performance",
            findings="Slow query",
            location="db.py:42",
            severity="warning",
            recommended_fix="Add index"
        )

        success = reviewer.update_analysis_status(
            analysis_id=analysis_id,
            status="resolved",
            notes="Fix implemented"
        )

        assert success is True
        analysis = memory.get_analysis(analysis_id)
        assert analysis["status"] == "resolved"

    def test_update_status_to_validated(self):
        """Test updating status to validated."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        analysis_id = reviewer.create_backend_analysis(
            category="security",
            findings="Secret in logs",
            location="log.py:15",
            severity="critical",
            recommended_fix="Redact"
        )

        success = reviewer.update_analysis_status(
            analysis_id=analysis_id,
            status="validated",
            notes="Fix validated by Jochi"
        )

        assert success is True
        analysis = memory.get_analysis(analysis_id)
        assert analysis["status"] == "validated"

    def test_update_status_invalid(self):
        """Test that invalid status raises ValueError."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        with pytest.raises(ValueError, match="Invalid status"):
            reviewer.update_analysis_status(
                analysis_id="any-id",
                status="invalid_status"
            )

    def test_update_status_all_valid_statuses(self):
        """Test that all valid statuses are accepted."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        valid_statuses = [
            "identified",
            "in_progress",
            "resolved",
            "validated",
            "closed"
        ]

        for status in valid_statuses:
            memory = MockMemory()
            reviewer = BackendCodeReviewer(memory)

            analysis_id = reviewer.create_backend_analysis(
                category="performance",
                findings="Test",
                location="file.py:1",
                severity="info",
                recommended_fix="Fix"
            )

            success = reviewer.update_analysis_status(
                analysis_id=analysis_id,
                status=status
            )
            assert success is True, f"Failed for status: {status}"


# =============================================================================
# Test Collaborate with Temüjin
# =============================================================================

class TestCollaborateWithTemüjin:
    """Tests for handoff protocol to Temüjin."""

    def test_collaborate_success(self):
        """Test successful handoff to Temüjin."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        analysis_id = reviewer.create_backend_analysis(
            category="performance",
            findings="Slow query detected",
            location="db.py:42",
            severity="warning",
            recommended_fix="Add index on Task.status"
        )

        handoff = reviewer.collaborate_with_temüjin(analysis_id)

        assert handoff["success"] is True
        assert handoff["analysis_id"] == analysis_id
        assert handoff["category"] == "performance"
        assert handoff["location"] == "db.py:42"
        assert handoff["severity"] == "warning"
        assert "task_id" in handoff
        assert "related_context" in handoff

    def test_collaborate_not_found(self):
        """Test handoff with non-existent analysis."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        handoff = reviewer.collaborate_with_temüjin("non-existent-id")

        assert handoff["success"] is False
        assert "error" in handoff

    def test_collaborate_updates_status(self):
        """Test that handoff updates status to in_progress."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        analysis_id = reviewer.create_backend_analysis(
            category="security",
            findings="Secret exposed",
            location="auth.py:25",
            severity="critical",
            recommended_fix="Use environment variable"
        )

        # Status should be identified initially
        analysis = memory.get_analysis(analysis_id)
        assert analysis["status"] == "identified"

        # After handoff, should be in_progress
        handoff = reviewer.collaborate_with_temüjin(analysis_id)
        assert handoff["new_status"] == "in_progress"

    def test_collaborate_creates_task(self):
        """Test that handoff creates implementation task."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        analysis_id = reviewer.create_backend_analysis(
            category="connection_pool",
            findings="No connection pooling",
            location="db.py:10",
            severity="warning",
            recommended_fix="Implement connection pool"
        )

        handoff = reviewer.collaborate_with_temüjin(analysis_id)

        assert handoff["task_id"] is not None
        assert handoff["task_id"].startswith("task-")


# =============================================================================
# Test Fix Validation
# =============================================================================

class TestValidateFix:
    """Tests for fix validation."""

    def test_validate_fix_success(self):
        """Test successful fix validation."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        analysis_id = reviewer.create_backend_analysis(
            category="performance",
            findings="Slow query",
            location="db.py:42",
            severity="warning",
            recommended_fix="Add index"
        )

        result = reviewer.validate_fix(
            analysis_id=analysis_id,
            fix_summary="Added index on Task.status column",
            validation_results={"tests_pass": True, "code_reviewed": True}
        )

        assert result["valid"] is True
        assert result["analysis_id"] == analysis_id
        assert result["new_status"] == "validated"

    def test_validate_fix_too_brief(self):
        """Test validation rejects too brief fix summary."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        analysis_id = reviewer.create_backend_analysis(
            category="performance",
            findings="Slow query",
            location="db.py:42",
            severity="warning",
            recommended_fix="Add index"
        )

        result = reviewer.validate_fix(
            analysis_id=analysis_id,
            fix_summary="Fixed"
        )

        assert result["valid"] is False
        assert result["new_status"] == "in_progress"

    def test_validate_fix_category_specific_connection_pool(self):
        """Test validation for connection_pool category."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        analysis_id = reviewer.create_backend_analysis(
            category="connection_pool",
            findings="No pooling",
            location="db.py:10",
            severity="warning",
            recommended_fix="Add connection pool"
        )

        # Valid fix
        result = reviewer.validate_fix(
            analysis_id=analysis_id,
            fix_summary="Implemented connection pooling with max_connections=50"
        )
        assert result["valid"] is True

        # Invalid fix - doesn't address pooling
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)
        analysis_id = reviewer.create_backend_analysis(
            category="connection_pool",
            findings="No pooling",
            location="db.py:10",
            severity="warning",
            recommended_fix="Add connection pool"
        )

        result = reviewer.validate_fix(
            analysis_id=analysis_id,
            fix_summary="Updated the configuration file"
        )
        assert result["valid"] is False

    def test_validate_fix_category_specific_resilience(self):
        """Test validation for resilience category."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        analysis_id = reviewer.create_backend_analysis(
            category="resilience",
            findings="No retry logic",
            location="api.py:30",
            severity="warning",
            recommended_fix="Add retry with exponential backoff"
        )

        # Valid fix - mentions retry
        result = reviewer.validate_fix(
            analysis_id=analysis_id,
            fix_summary="Added retry logic with exponential backoff and circuit breaker"
        )
        assert result["valid"] is True

    def test_validate_fix_category_specific_data_integrity(self):
        """Test validation for data_integrity category."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        analysis_id = reviewer.create_backend_analysis(
            category="data_integrity",
            findings="SQL injection risk",
            location="query.py:15",
            severity="critical",
            recommended_fix="Use parameterized queries"
        )

        # Valid fix - mentions parameterized
        result = reviewer.validate_fix(
            analysis_id=analysis_id,
            fix_summary="Converted to parameterized query with proper escaping"
        )
        assert result["valid"] is True

    def test_validate_fix_category_specific_performance(self):
        """Test validation for performance category."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        analysis_id = reviewer.create_backend_analysis(
            category="performance",
            findings="No timeout on HTTP request",
            location="client.py:45",
            severity="warning",
            recommended_fix="Add timeout"
        )

        # Valid fix - mentions timeout
        result = reviewer.validate_fix(
            analysis_id=analysis_id,
            fix_summary="Added 30 second timeout to all HTTP requests"
        )
        assert result["valid"] is True

    def test_validate_fix_category_specific_security(self):
        """Test validation for security category."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        analysis_id = reviewer.create_backend_analysis(
            category="security",
            findings="Secret in logs",
            location="logger.py:20",
            severity="critical",
            recommended_fix="Redact sensitive data"
        )

        # Valid fix - mentions secret/redaction
        result = reviewer.validate_fix(
            analysis_id=analysis_id,
            fix_summary="Implemented redaction for secrets and tokens in log output"
        )
        assert result["valid"] is True

    def test_validate_fix_with_failing_tests(self):
        """Test validation with failing tests."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        analysis_id = reviewer.create_backend_analysis(
            category="performance",
            findings="Slow query",
            location="db.py:42",
            severity="warning",
            recommended_fix="Add index"
        )

        result = reviewer.validate_fix(
            analysis_id=analysis_id,
            fix_summary="Added index on Task.status column",
            validation_results={"tests_pass": False, "code_reviewed": True}
        )

        assert result["valid"] is False
        assert result["new_status"] == "in_progress"

    def test_validate_fix_not_found(self):
        """Test validation with non-existent analysis."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        result = reviewer.validate_fix(
            analysis_id="non-existent",
            fix_summary="Some fix"
        )

        assert result["valid"] is False
        assert "error" in result


# =============================================================================
# Test Review Summary
# =============================================================================

class TestReviewSummary:
    """Tests for review summary functionality."""

    def test_get_review_summary_empty(self):
        """Test getting summary when no analyses exist."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        summary = reviewer.get_review_summary()

        assert summary["total_analyses"] == 0
        assert summary["pending_count"] == 0
        assert summary["resolved_count"] == 0

    def test_get_review_summary_with_data(self):
        """Test getting summary with analyses."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        # Create various analyses
        reviewer.create_backend_analysis(
            category="performance",
            findings="Slow query",
            location="db.py:42",
            severity="warning",
            recommended_fix="Add index"
        )
        reviewer.create_backend_analysis(
            category="security",
            findings="Secret in logs",
            location="log.py:15",
            severity="critical",
            recommended_fix="Redact"
        )
        reviewer.create_backend_analysis(
            category="connection_pool",
            findings="No pool",
            location="db.py:10",
            severity="warning",
            recommended_fix="Add pool"
        )

        summary = reviewer.get_review_summary()

        assert summary["total_analyses"] == 3
        assert summary["by_category"]["performance"] == 1
        assert summary["by_category"]["security"] == 1
        assert summary["by_category"]["connection_pool"] == 1
        assert summary["by_severity"]["warning"] == 2
        assert summary["by_severity"]["critical"] == 1


# =============================================================================
# Test Category-Specific Checks
# =============================================================================

class TestCheckConnectionPool:
    """Tests for connection pool checking."""

    def test_check_connection_pool_no_issues(self):
        """Test code with proper connection pooling."""
        reviewer = BackendCodeReviewer(MockMemory())

        code = """
def get_db_connection():
    pool = ConnectionPool(max_connections=50, timeout=30)
    return pool.get_connection()
"""
        issues = reviewer.check_connection_pool(code, "db.py")
        assert len(issues) == 0

    def test_check_connection_pool_no_pool(self):
        """Test code without connection pooling."""
        reviewer = BackendCodeReviewer(MockMemory())

        code = """
def connect_to_db():
    return psycopg2.connect(dsn=dsn)
"""
        issues = reviewer.check_connection_pool(code, "db.py")
        assert len(issues) > 0
        assert any(i["category"] == "connection_pool" for i in issues)

    def test_check_connection_pool_no_timeout(self):
        """Test code without timeout."""
        reviewer = BackendCodeReviewer(MockMemory())

        code = """
pool = ConnectionPool(max_connections=50)
"""
        issues = reviewer.check_connection_pool(code, "db.py")
        assert len(issues) > 0
        assert any("timeout" in i["finding"].lower() for i in issues if i["category"] == "connection_pool")


class TestCheckResilience:
    """Tests for resilience checking."""

    def test_check_resilience_no_issues(self):
        """Test code with proper resilience patterns."""
        reviewer = BackendCodeReviewer(MockMemory())

        code = """
@retry(max_attempts=3, backoff=exponential)
@circuit_breaker
def fetch_data(url):
    return requests.get(url, timeout=30)
"""
        issues = reviewer.check_resilience(code, "api.py")
        # Should only report fallback missing, since we have retry and circuit breaker
        assert len(issues) <= 1
        if issues:
            assert issues[0]["finding"] == "External call without fallback mechanism"

    def test_check_resilience_no_retry(self):
        """Test code without retry logic."""
        reviewer = BackendCodeReviewer(MockMemory())

        code = """
def fetch_data(url):
    return requests.get(url)
"""
        issues = reviewer.check_resilience(code, "api.py")
        assert len(issues) > 0
        assert any(i["category"] == "resilience" for i in issues)

    def test_check_resilience_no_circuit_breaker(self):
        """Test code without circuit breaker."""
        reviewer = BackendCodeReviewer(MockMemory())

        code = """
@retry(max_attempts=3)
def fetch_data(url):
    return requests.get(url, timeout=30)
"""
        issues = reviewer.check_resilience(code, "api.py")
        assert len(issues) > 0
        assert any("circuit" in i["finding"].lower() for i in issues)


class TestCheckDataIntegrity:
    """Tests for data integrity checking."""

    def test_check_data_integrity_no_issues(self):
        """Test code with proper data integrity."""
        reviewer = BackendCodeReviewer(MockMemory())

        code = """
session.run(
    "MATCH (u:User {id: $id}) RETURN u",
    id=user_id
)
"""
        issues = reviewer.check_data_integrity(code, "query.py")
        assert len(issues) == 0

    def test_check_data_integrity_f_string_injection(self):
        """Test detection of f-string injection risk."""
        reviewer = BackendCodeReviewer(MockMemory())

        code = """
def get_user(name):
    query = f"MATCH (u:User {name: '{name}'}) RETURN u"
    return session.run(query)
"""
        issues = reviewer.check_data_integrity(code, "query.py")
        assert len(issues) > 0
        assert any(i["severity"] == "critical" for i in issues)

    def test_check_data_integrity_string_concat(self):
        """Test detection of string concatenation injection risk."""
        reviewer = BackendCodeReviewer(MockMemory())

        code = '''
def get_user(name):
    query = "MATCH (u:User {name: '" + name + "'}) RETURN u"
    return session.run(query)
'''
        issues = reviewer.check_data_integrity(code, "query.py")
        assert len(issues) > 0
        assert any(i["severity"] == "critical" for i in issues)

    def test_check_data_integrity_no_transaction(self):
        """Test detection of missing transaction."""
        reviewer = BackendCodeReviewer(MockMemory())

        code = """
session.run("CREATE (u:User {name: $name})", name=name)
session.run("CREATE (p:Post {title: $title})", title=title)
"""
        issues = reviewer.check_data_integrity(code, "data.py")
        assert len(issues) > 0
        assert any("transaction" in i["finding"].lower() for i in issues)


class TestCheckPerformance:
    """Tests for performance checking."""

    def test_check_performance_no_issues(self):
        """Test code with proper performance patterns."""
        reviewer = BackendCodeReviewer(MockMemory())

        code = """
async def fetch_data():
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=30) as response:
            return await response.json()
"""
        issues = reviewer.check_performance(code, "api.py")
        assert len(issues) == 0

    def test_check_performance_no_timeout(self):
        """Test detection of missing timeout."""
        reviewer = BackendCodeReviewer(MockMemory())

        code = """
def fetch_data():
    response = requests.get(url)
    return response.json()
"""
        issues = reviewer.check_performance(code, "api.py")
        assert len(issues) > 0
        assert any("timeout" in i["finding"].lower() for i in issues)

    def test_check_performance_blocking_sleep(self):
        """Test detection of blocking sleep in async context."""
        reviewer = BackendCodeReviewer(MockMemory())

        code = """
async def process():
    time.sleep(1)  # Bad!
    return result
"""
        issues = reviewer.check_performance(code, "async.py")
        assert len(issues) > 0
        assert any("blocking" in i["finding"].lower() for i in issues)


class TestCheckSecurity:
    """Tests for security checking."""

    def test_check_security_no_issues(self):
        """Test code with proper security practices."""
        reviewer = BackendCodeReviewer(MockMemory())

        code = """
import os

def get_db_connection():
    password = os.getenv("DB_PASSWORD")
    return connect(password=password)

def log_event(event):
    logger.info(f"Event: {event.id}")
"""
        issues = reviewer.check_security(code, "secure.py")
        assert len(issues) == 0

    def test_check_security_password_in_log(self):
        """Test detection of password in logs."""
        reviewer = BackendCodeReviewer(MockMemory())

        code = """
logger.info(f"User logged in: {username}, password: {password}")
"""
        issues = reviewer.check_security(code, "auth.py")
        assert len(issues) > 0
        assert any(i["severity"] == "critical" for i in issues)

    def test_check_security_hardcoded_password(self):
        """Test detection of hardcoded password."""
        reviewer = BackendCodeReviewer(MockMemory())

        code = """
DB_PASSWORD = "secret123"
"""
        issues = reviewer.check_security(code, "config.py")
        assert len(issues) > 0
        assert any(i["severity"] == "critical" for i in issues)
        assert any("password" in i["finding"].lower() for i in issues)

    def test_check_security_unverified_request(self):
        """Test detection of unverified HTTP request."""
        reviewer = BackendCodeReviewer(MockMemory())

        code = """
response = requests.get("https://example.com/api")
"""
        issues = reviewer.check_security(code, "client.py")
        assert len(issues) > 0
        assert any("unverified" in i["finding"].lower() for i in issues)


# =============================================================================
# Test Full Code Review
# =============================================================================

class TestReviewCodeFile:
    """Tests for complete code review workflow."""

    def test_review_code_file_no_issues(self):
        """Test reviewing a clean file."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        code = """
import os
from dataclasses import dataclass

@dataclass
class Config:
    db_host: str = os.getenv("DB_HOST", "localhost")

def get_connection():
    pool = ConnectionPool(max_connections=50, timeout=30)
    return pool.get_connection()
"""

        result = reviewer.review_code_file("config.py", code, auto_create=False)

        assert result["file_path"] == "config.py"
        assert result["summary"]["total"] == len(result["issues"])

    def test_review_code_file_with_issues(self):
        """Test reviewing a file with multiple issues."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        code = """
def connect():
    return psycopg2.connect(dsn=dsn)

def query(name):
    query = "SELECT * FROM users WHERE name = '" + name + "'"
    return execute(query)

def log_login(username, password):
    logger.info(f"Login: {username}, {password}")
"""

        result = reviewer.review_code_file("bad_code.py", code, auto_create=False)

        assert result["file_path"] == "bad_code.py"
        assert result["summary"]["total"] > 0
        # Should have at least connection_pool, data_integrity, and security issues

    def test_review_code_file_auto_create(self):
        """Test reviewing with auto_create=True."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        code = """
password = "hardcoded"
logger.info(password)
"""

        result = reviewer.review_code_file("insecure.py", code, auto_create=True)

        assert len(result["analyses_created"]) > 0
        assert result["summary"]["total"] == len(result["analyses_created"])

    def test_review_code_file_all_categories(self):
        """Test that all 5 categories can be detected."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        code = """
# Bad code with issues in all categories

def bad_function(password):
    # connection_pool: no pool
    conn = psycopg2.connect(dsn)

    # resilience: no retry
    response = requests.get(url)

    # data_integrity: injection
    query = f"SELECT * FROM users WHERE id = {user_id}"
    conn.execute(query)

    # performance: no timeout
    data = fetch_slow_data()

    # security: secret in logs
    logger.info(f"Processing user: {password}")
    return data
"""

        result = reviewer.review_code_file("all_bad.py", code, auto_create=False)

        categories_found = set(i["category"] for i in result["issues"])
        assert len(categories_found) >= 3  # At least 3 categories should be found


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegrationWorkflows:
    """Integration tests for complete workflows."""

    def test_jochi_to_temujin_full_workflow(self):
        """Test complete workflow from Jochi identification to Temüjin resolution."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        # Step 1: Jochi identifies an issue
        analysis_id = reviewer.create_backend_analysis(
            category="connection_pool",
            findings="Database connections not pooled, causing resource exhaustion",
            location="db.py:25",
            severity="critical",
            recommended_fix="Implement connection pool with max_connections=50"
        )

        # Step 2: Get pending analyses
        pending = reviewer.get_pending_analyses()
        assert len(pending) == 1
        assert pending[0]["id"] == analysis_id

        # Step 3: Hand off to Temüjin
        handoff = reviewer.collaborate_with_temüjin(analysis_id)
        assert handoff["success"] is True
        assert handoff["new_status"] == "in_progress"

        # Step 4: Temüjin implements fix and Jochi validates
        validation = reviewer.validate_fix(
            analysis_id=analysis_id,
            fix_summary="Implemented ConnectionPool class with max_connections=50, timeout=30",
            validation_results={"tests_pass": True, "code_reviewed": True}
        )

        assert validation["valid"] is True
        assert validation["new_status"] == "validated"

        # Step 5: Close the analysis
        reviewer.update_analysis_status(analysis_id, "closed", "Fix validated and deployed")

        analysis = memory.get_analysis(analysis_id)
        assert analysis["status"] == "closed"

    def test_multiple_categories_workflow(self):
        """Test workflow with multiple issues in different categories."""
        memory = MockMemory()
        reviewer = BackendCodeReviewer(memory)

        # Create issues in all 5 categories
        categories = [
            ("connection_pool", "No pooling", "critical"),
            ("resilience", "No retry", "warning"),
            ("data_integrity", "SQL injection", "critical"),
            ("performance", "No timeout", "warning"),
            ("security", "Secret in logs", "critical")
        ]

        analysis_ids = []
        for category, finding, severity in categories:
            aid = reviewer.create_backend_analysis(
                category=category,
                findings=finding,
                location=f"{category}_module.py:1",
                severity=severity,
                recommended_fix=f"Fix {category}"
            )
            analysis_ids.append(aid)

        # Get summary
        summary = reviewer.get_review_summary()
        assert summary["total_analyses"] == 5
        assert summary["by_category"]["connection_pool"] == 1
        assert summary["by_category"]["resilience"] == 1
        assert summary["by_category"]["data_integrity"] == 1
        assert summary["by_category"]["performance"] == 1
        assert summary["by_category"]["security"] == 1

        # Get pending sorted by severity
        pending = reviewer.get_pending_analyses(limit=10)
        # Critical issues should come first
        assert pending[0]["findings"]["severity"] == "critical"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
