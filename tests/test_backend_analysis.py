"""
Test Suite for Jochi Backend Issue Identification Protocol

Tests the analysis functionality in OperationalMemory including:
- Analysis node creation for backend issues
- Performance bottleneck detection and categorization
- Issue labeling with severity and assigned agent
- Resource leak detection for Neo4j connections
- Integration with existing agent workflow
"""

import pytest
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock

import sys
sys.path.insert(0, '/Users/kurultai/molt')

from openclaw_memory import OperationalMemory


class MockContextManager:
    """Helper class to mock context managers properly."""
    def __init__(self, return_value):
        self.return_value = return_value

    def __enter__(self):
        return self.return_value

    def __exit__(self, *args):
        pass


class TestAnalysisCreation:
    """Tests for creating analyses."""

    def test_create_analysis_success(self):
        """Test successful creation of an analysis."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._generate_id = Mock(return_value="test-analysis-id")
        memory._now = Mock(return_value=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc))

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"analysis_id": "test-analysis-id"}
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        analysis_id = memory.create_analysis(
            agent="jochi",
            analysis_type="performance",
            severity="high",
            description="Slow query detected in task retrieval",
            target_agent="developer",
            findings={"query_time_ms": 1500, "table": "Task"},
            recommendations=["Add index on Task.status", "Optimize query"],
            assigned_to="temujin"
        )

        assert analysis_id == "test-analysis-id"
        mock_session.run.assert_called_once()

    def test_create_analysis_invalid_type(self):
        """Test that invalid analysis_type raises ValueError."""
        memory = OperationalMemory.__new__(OperationalMemory)

        with pytest.raises(ValueError, match="Invalid analysis_type"):
            memory.create_analysis(
                agent="jochi",
                analysis_type="invalid_type",
                severity="high",
                description="Test",
                target_agent="developer"
            )

    def test_create_analysis_invalid_severity(self):
        """Test that invalid severity raises ValueError."""
        memory = OperationalMemory.__new__(OperationalMemory)

        with pytest.raises(ValueError, match="Invalid severity"):
            memory.create_analysis(
                agent="jochi",
                analysis_type="performance",
                severity="invalid",
                description="Test",
                target_agent="developer"
            )

    def test_create_analysis_all_valid_types(self):
        """Test that all valid analysis types are accepted."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._generate_id = Mock(return_value="test-id")
        memory._now = Mock(return_value=datetime.now(timezone.utc))

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"analysis_id": "test-id"}
        mock_session.run.return_value = mock_result

        valid_types = ['performance', 'resource', 'error', 'security', 'other']

        for analysis_type in valid_types:
            mock_session.reset_mock()
            memory._session = Mock(return_value=MockContextManager(mock_session))

            analysis_id = memory.create_analysis(
                agent="jochi",
                analysis_type=analysis_type,
                severity="medium",
                description=f"Test {analysis_type}",
                target_agent="developer"
            )
            assert analysis_id == "test-id", f"Failed for analysis_type: {analysis_type}"

    def test_create_analysis_all_valid_severities(self):
        """Test that all valid severities are accepted."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._generate_id = Mock(return_value="test-id")
        memory._now = Mock(return_value=datetime.now(timezone.utc))

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"analysis_id": "test-id"}
        mock_session.run.return_value = mock_result

        valid_severities = ['low', 'medium', 'high', 'critical']

        for severity in valid_severities:
            mock_session.reset_mock()
            memory._session = Mock(return_value=MockContextManager(mock_session))

            analysis_id = memory.create_analysis(
                agent="jochi",
                analysis_type="performance",
                severity=severity,
                description=f"Test {severity}",
                target_agent="developer"
            )
            assert analysis_id == "test-id", f"Failed for severity: {severity}"

    def test_create_analysis_fallback_mode(self):
        """Test that fallback mode returns analysis ID without database."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._generate_id = Mock(return_value="fallback-analysis-id")
        memory._now = Mock(return_value=datetime.now(timezone.utc))

        memory._session = Mock(return_value=MockContextManager(None))

        analysis_id = memory.create_analysis(
            agent="jochi",
            analysis_type="resource",
            severity="critical",
            description="Connection pool exhausted",
            target_agent="ops",
            assigned_to="temujin"
        )

        assert analysis_id == "fallback-analysis-id"

    def test_create_analysis_for_temujin_assignment(self):
        """Test creating an analysis specifically assigned to Temüjin."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._generate_id = Mock(return_value="temujin-analysis-id")
        memory._now = Mock(return_value=datetime.now(timezone.utc))

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"analysis_id": "temujin-analysis-id"}
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        analysis_id = memory.create_analysis(
            agent="jochi",
            analysis_type="performance",
            severity="high",
            description="Memory leak detected in connection handling",
            target_agent="developer",
            findings={"memory_usage_mb": 2048, "growth_rate": "100MB/hour"},
            recommendations=["Review connection cleanup", "Add memory profiling"],
            assigned_to="temujin"
        )

        assert analysis_id == "temujin-analysis-id"
        # Verify assigned_to was passed correctly
        call_args = mock_session.run.call_args
        assert call_args[1]["assigned_to"] == "temujin"


class TestAnalysisQueries:
    """Tests for querying analyses."""

    def test_list_analyses_no_filters(self):
        """Test listing all analyses without filters."""
        memory = OperationalMemory.__new__(OperationalMemory)

        mock_session = MagicMock()
        mock_record = {
            "a": {
                "id": "analysis-1",
                "agent": "jochi",
                "analysis_type": "performance",
                "severity": "high",
                "status": "open"
            }
        }
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([mock_record]))
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        analyses = memory.list_analyses()

        assert len(analyses) == 1
        assert analyses[0]["id"] == "analysis-1"

    def test_list_analyses_with_filters(self):
        """Test listing analyses with filters."""
        memory = OperationalMemory.__new__(OperationalMemory)

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([]))
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        analyses = memory.list_analyses(
            agent="jochi",
            analysis_type="performance",
            severity="critical",
            status="open",
            assigned_to="temujin"
        )

        assert analyses == []
        # Verify the query was called with correct parameters
        call_args = mock_session.run.call_args
        assert call_args[1]["agent"] == "jochi"
        assert call_args[1]["analysis_type"] == "performance"
        assert call_args[1]["severity"] == "critical"
        assert call_args[1]["status"] == "open"
        assert call_args[1]["assigned_to"] == "temujin"

    def test_list_analyses_fallback_mode(self):
        """Test that fallback mode returns empty list."""
        memory = OperationalMemory.__new__(OperationalMemory)

        memory._session = Mock(return_value=MockContextManager(None))

        analyses = memory.list_analyses()

        assert analyses == []

    def test_get_analysis_by_id(self):
        """Test getting a specific analysis by ID."""
        memory = OperationalMemory.__new__(OperationalMemory)

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {
            "a": {
                "id": "analysis-1",
                "agent": "jochi",
                "analysis_type": "performance",
                "severity": "high",
                "description": "Test issue",
                "findings": "{'metric': 100}",
                "recommendations": "['fix1', 'fix2']"
            }
        }
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        analysis = memory.get_analysis("analysis-1")

        assert analysis is not None
        assert analysis["id"] == "analysis-1"
        assert analysis["severity"] == "high"

    def test_get_analysis_not_found(self):
        """Test getting a non-existent analysis."""
        memory = OperationalMemory.__new__(OperationalMemory)

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = None
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        analysis = memory.get_analysis("non-existent")

        assert analysis is None


class TestAnalysisStatusUpdate:
    """Tests for updating analysis status."""

    def test_update_analysis_status_success(self):
        """Test successfully updating analysis status."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._now = Mock(return_value=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc))

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"analysis_id": "analysis-1"}
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        result = memory.update_analysis_status(
            analysis_id="analysis-1",
            status="in_progress",
            updated_by="temujin"
        )

        assert result is True

    def test_update_analysis_status_to_resolved(self):
        """Test marking analysis as resolved."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._now = Mock(return_value=datetime.now(timezone.utc))

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"analysis_id": "analysis-1"}
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        result = memory.update_analysis_status(
            analysis_id="analysis-1",
            status="resolved",
            updated_by="temujin"
        )

        assert result is True
        # Verify resolved_at would be set (check cypher includes resolved_at)
        call_args = mock_session.run.call_args
        assert "resolved_at" in call_args[0][0] or "resolved_at" in str(call_args)

    def test_update_analysis_status_not_found(self):
        """Test updating a non-existent analysis."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._now = Mock(return_value=datetime.now(timezone.utc))

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = None
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        result = memory.update_analysis_status(
            analysis_id="non-existent",
            status="in_progress",
            updated_by="temujin"
        )

        assert result is False

    def test_update_analysis_status_invalid_status(self):
        """Test that invalid status raises ValueError."""
        memory = OperationalMemory.__new__(OperationalMemory)

        with pytest.raises(ValueError, match="Invalid status"):
            memory.update_analysis_status(
                analysis_id="analysis-1",
                status="invalid_status",
                updated_by="temujin"
            )

    def test_update_analysis_status_all_valid_statuses(self):
        """Test that all valid statuses are accepted."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._now = Mock(return_value=datetime.now(timezone.utc))

        valid_statuses = ['open', 'in_progress', 'resolved', 'closed']

        for status in valid_statuses:
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_result.single.return_value = {"analysis_id": "analysis-1"}
            mock_session.run.return_value = mock_result

            memory._session = Mock(return_value=MockContextManager(mock_session))

            result = memory.update_analysis_status(
                analysis_id="analysis-1",
                status=status,
                updated_by="temujin"
            )
            assert result is True, f"Failed for status: {status}"


class TestAnalysisAssignment:
    """Tests for assigning analyses."""

    def test_assign_analysis_success(self):
        """Test successfully assigning an analysis."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._now = Mock(return_value=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc))

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"analysis_id": "analysis-1"}
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        result = memory.assign_analysis(
            analysis_id="analysis-1",
            assigned_to="temujin",
            assigned_by="jochi"
        )

        assert result is True
        # Verify assigned_to was passed correctly
        call_args = mock_session.run.call_args
        assert call_args[1]["assigned_to"] == "temujin"

    def test_assign_analysis_not_found(self):
        """Test assigning a non-existent analysis."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._now = Mock(return_value=datetime.now(timezone.utc))

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = None
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        result = memory.assign_analysis(
            analysis_id="non-existent",
            assigned_to="temujin",
            assigned_by="jochi"
        )

        assert result is False

    def test_assign_analysis_fallback_mode(self):
        """Test that fallback mode returns True."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._now = Mock(return_value=datetime.now(timezone.utc))

        memory._session = Mock(return_value=MockContextManager(None))

        result = memory.assign_analysis(
            analysis_id="analysis-1",
            assigned_to="temujin",
            assigned_by="jochi"
        )

        assert result is True


class TestAnalysisSummary:
    """Tests for analysis summary functionality."""

    def test_get_analysis_summary_empty(self):
        """Test getting summary when no analyses exist."""
        memory = OperationalMemory.__new__(OperationalMemory)

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([]))
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        summary = memory.get_analysis_summary()

        assert summary["total"] == 0
        assert summary["by_severity"] == {"critical": 0, "high": 0, "medium": 0, "low": 0}
        assert summary["by_status"] == {"open": 0, "in_progress": 0, "resolved": 0, "closed": 0}
        assert summary["by_type"] == {"performance": 0, "resource": 0, "error": 0, "security": 0, "other": 0}
        assert summary["open_by_severity"] == {"critical": 0, "high": 0, "medium": 0, "low": 0}

    def test_get_analysis_summary_with_data(self):
        """Test getting summary with analysis data."""
        memory = OperationalMemory.__new__(OperationalMemory)

        mock_session = MagicMock()
        mock_records = [
            {"severity": "critical", "status": "open", "analysis_type": "performance", "count": 2},
            {"severity": "high", "status": "open", "analysis_type": "resource", "count": 5},
            {"severity": "high", "status": "in_progress", "analysis_type": "error", "count": 3},
            {"severity": "medium", "status": "open", "analysis_type": "performance", "count": 10},
            {"severity": "low", "status": "resolved", "analysis_type": "other", "count": 1},
        ]
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter(mock_records))
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        summary = memory.get_analysis_summary()

        assert summary["total"] == 21  # Sum of all counts
        assert summary["by_severity"]["critical"] == 2
        assert summary["by_severity"]["high"] == 8  # 5 open + 3 in_progress
        assert summary["by_status"]["open"] == 17  # 2 + 5 + 10
        assert summary["by_status"]["in_progress"] == 3
        assert summary["by_type"]["performance"] == 12  # 2 + 10
        assert summary["open_by_severity"]["high"] == 5

    def test_get_analysis_summary_for_target_agent(self):
        """Test getting summary filtered by target_agent."""
        memory = OperationalMemory.__new__(OperationalMemory)

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([]))
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        summary = memory.get_analysis_summary(target_agent="developer")

        # Verify target_agent filter was passed
        call_args = mock_session.run.call_args
        assert call_args[1]["target_agent"] == "developer"

    def test_get_analysis_summary_fallback_mode(self):
        """Test that fallback mode returns zeroed summary."""
        memory = OperationalMemory.__new__(OperationalMemory)

        memory._session = Mock(return_value=MockContextManager(None))

        summary = memory.get_analysis_summary()

        assert summary["total"] == 0
        assert summary["by_severity"] == {"critical": 0, "high": 0, "medium": 0, "low": 0}
        assert summary["by_status"] == {"open": 0, "in_progress": 0, "resolved": 0, "closed": 0}


class TestPerformanceIssueDetection:
    """Tests for performance issue detection."""

    def test_detect_performance_issues_connection_pool_critical(self):
        """Test detection of critical connection pool exhaustion."""
        memory = OperationalMemory.__new__(OperationalMemory)

        metrics = {"connection_pool_usage": 97}
        issues = memory.detect_performance_issues(metrics)

        assert len(issues) == 1
        assert issues[0]["issue_type"] == "connection_pool_exhaustion"
        assert issues[0]["severity"] == "critical"
        assert "Increase max_connection_pool_size" in issues[0]["recommendations"][0]

    def test_detect_performance_issues_connection_pool_high(self):
        """Test detection of high connection pool usage."""
        memory = OperationalMemory.__new__(OperationalMemory)

        metrics = {"connection_pool_usage": 85}
        issues = memory.detect_performance_issues(metrics)

        assert len(issues) == 1
        assert issues[0]["issue_type"] == "connection_pool_high_usage"
        assert issues[0]["severity"] == "high"

    def test_detect_performance_issues_connection_pool_medium(self):
        """Test detection of medium connection pool usage."""
        memory = OperationalMemory.__new__(OperationalMemory)

        metrics = {"connection_pool_usage": 65}
        issues = memory.detect_performance_issues(metrics)

        assert len(issues) == 1
        assert issues[0]["issue_type"] == "connection_pool_elevated_usage"
        assert issues[0]["severity"] == "medium"

    def test_detect_performance_issues_slow_query_critical(self):
        """Test detection of critical slow queries."""
        memory = OperationalMemory.__new__(OperationalMemory)

        metrics = {"query_time_ms": 6000}
        issues = memory.detect_performance_issues(metrics)

        assert len(issues) == 1
        assert issues[0]["issue_type"] == "slow_query_critical"
        assert issues[0]["severity"] == "critical"
        assert "Add missing indexes" in issues[0]["recommendations"][0]

    def test_detect_performance_issues_error_rate_critical(self):
        """Test detection of critical error rate."""
        memory = OperationalMemory.__new__(OperationalMemory)

        metrics = {"error_rate": 15}
        issues = memory.detect_performance_issues(metrics)

        assert len(issues) == 1
        assert issues[0]["issue_type"] == "high_error_rate"
        assert issues[0]["severity"] == "critical"

    def test_detect_performance_issues_multiple_issues(self):
        """Test detection of multiple simultaneous issues."""
        memory = OperationalMemory.__new__(OperationalMemory)

        metrics = {
            "connection_pool_usage": 95,
            "query_time_ms": 3000,
            "error_rate": 8,
            "memory_usage_mb": 2500,
            "circuit_breaker_trips": 6
        }
        issues = memory.detect_performance_issues(metrics)

        assert len(issues) == 5
        severities = [issue["severity"] for issue in issues]
        assert "critical" in severities
        assert "high" in severities

    def test_detect_performance_issues_no_issues(self):
        """Test detection with healthy metrics."""
        memory = OperationalMemory.__new__(OperationalMemory)

        metrics = {
            "connection_pool_usage": 30,
            "query_time_ms": 100,
            "error_rate": 0.1
        }
        issues = memory.detect_performance_issues(metrics)

        assert len(issues) == 0

    def test_detect_performance_issues_circuit_breaker(self):
        """Test detection of circuit breaker trips."""
        memory = OperationalMemory.__new__(OperationalMemory)

        metrics = {"circuit_breaker_trips": 5}
        issues = memory.detect_performance_issues(metrics)

        assert len(issues) == 1
        assert issues[0]["issue_type"] == "circuit_breaker_frequent_trips"
        assert issues[0]["severity"] == "critical"

    def test_detect_performance_issues_memory_leak(self):
        """Test detection of potential memory leak."""
        memory = OperationalMemory.__new__(OperationalMemory)

        metrics = {"memory_usage_mb": 2048}
        issues = memory.detect_performance_issues(metrics)

        assert len(issues) == 1
        assert issues[0]["issue_type"] == "high_memory_usage"
        assert issues[0]["severity"] == "high"


class TestCreateAnalysisFromIssues:
    """Tests for creating analyses from detected issues."""

    def test_create_analysis_from_issues_success(self):
        """Test creating analyses from detected issues."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._generate_id = Mock(return_value="auto-analysis-id")
        memory._now = Mock(return_value=datetime.now(timezone.utc))

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"analysis_id": "auto-analysis-id"}
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        issues = [
            {
                "issue_type": "connection_pool_exhaustion",
                "severity": "critical",
                "description": "Connection pool nearly exhausted",
                "metric_value": 97,
                "threshold": 95,
                "recommendations": ["Increase pool size"]
            }
        ]

        analysis_ids = memory.create_analysis_from_issues(
            agent="jochi",
            issues=issues,
            target_agent="ops"
        )

        assert len(analysis_ids) == 1
        assert analysis_ids[0] == "auto-analysis-id"

    def test_create_analysis_from_issues_default_assignee(self):
        """Test that default assignee is temujin."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._generate_id = Mock(return_value="auto-analysis-id")
        memory._now = Mock(return_value=datetime.now(timezone.utc))

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"analysis_id": "auto-analysis-id"}
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        issues = [
            {
                "issue_type": "slow_query",
                "severity": "high",
                "description": "Slow query detected",
                "recommendations": ["Add index"]
            }
        ]

        memory.create_analysis_from_issues(agent="jochi", issues=issues)

        # Verify default assigned_to is temujin
        call_args = mock_session.run.call_args
        assert call_args[1]["assigned_to"] == "temujin"

    def test_create_analysis_from_issues_empty_list(self):
        """Test creating analyses with empty issues list."""
        memory = OperationalMemory.__new__(OperationalMemory)

        analysis_ids = memory.create_analysis_from_issues(
            agent="jochi",
            issues=[]
        )

        assert analysis_ids == []

    def test_create_analysis_from_issues_multiple(self):
        """Test creating multiple analyses from multiple issues."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._generate_id = Mock(side_effect=["id-1", "id-2", "id-3"])
        memory._now = Mock(return_value=datetime.now(timezone.utc))

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"analysis_id": "id-1"}
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        issues = [
            {"issue_type": "connection_pool_high", "severity": "high", "description": "Pool high", "recommendations": []},
            {"issue_type": "slow_query", "severity": "medium", "description": "Slow query", "recommendations": []},
            {"issue_type": "memory_leak", "severity": "high", "description": "Memory leak", "recommendations": []}
        ]

        analysis_ids = memory.create_analysis_from_issues(agent="jochi", issues=issues)

        assert len(analysis_ids) == 3


class TestAnalysisIndexes:
    """Tests for analysis indexes."""

    def test_create_indexes_includes_analysis(self):
        """Test that create_indexes includes Analysis indexes."""
        memory = OperationalMemory.__new__(OperationalMemory)

        mock_session = MagicMock()
        mock_session.run.return_value = None

        memory._session = Mock(return_value=MockContextManager(mock_session))

        created = memory.create_indexes()

        # Check that Analysis indexes are included
        analysis_indexes = [name for name in created if 'analysis' in name.lower()]
        assert len(analysis_indexes) >= 8  # Should have multiple indexes
        assert "analysis_id_idx" in analysis_indexes
        assert "analysis_agent_idx" in analysis_indexes
        assert "analysis_severity_idx" in analysis_indexes
        assert "analysis_status_idx" in analysis_indexes
        assert "analysis_assigned_to_idx" in analysis_indexes


class TestAnalysisIntegration:
    """Integration-style tests for analysis workflows."""

    def test_full_analysis_lifecycle(self):
        """Test the full lifecycle of an analysis."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._generate_id = Mock(return_value="lifecycle-analysis-id")
        memory._now = Mock(return_value=datetime.now(timezone.utc))

        # Mock session that returns appropriate results for each call
        mock_session = MagicMock()

        # First call: create analysis
        create_result = MagicMock()
        create_result.single.return_value = {"analysis_id": "lifecycle-analysis-id"}

        # Second call: get analysis
        get_result = MagicMock()
        get_result.single.return_value = {
            "a": {
                "id": "lifecycle-analysis-id",
                "agent": "jochi",
                "analysis_type": "performance",
                "severity": "high",
                "status": "open",
                "assigned_to": None
            }
        }

        # Third call: assign analysis
        assign_result = MagicMock()
        assign_result.single.return_value = {"analysis_id": "lifecycle-analysis-id"}

        # Fourth call: update status
        update_result = MagicMock()
        update_result.single.return_value = {"analysis_id": "lifecycle-analysis-id"}

        mock_session.run.side_effect = [create_result, get_result, assign_result, update_result]

        memory._session = Mock(return_value=MockContextManager(mock_session))

        # 1. Create analysis
        analysis_id = memory.create_analysis(
            agent="jochi",
            analysis_type="performance",
            severity="high",
            description="Slow query in task retrieval",
            target_agent="developer",
            findings={"query_time_ms": 1500},
            recommendations=["Add index"]
        )
        assert analysis_id == "lifecycle-analysis-id"

        # 2. Get analysis
        analysis = memory.get_analysis(analysis_id)
        assert analysis["analysis_type"] == "performance"
        assert analysis["status"] == "open"

        # 3. Assign to temujin
        result = memory.assign_analysis(analysis_id, assigned_to="temujin", assigned_by="jochi")
        assert result is True

        # 4. Update status to in_progress
        result = memory.update_analysis_status(analysis_id, status="in_progress", updated_by="temujin")
        assert result is True

    def test_jochi_to_temujin_workflow(self):
        """Test the Jochi -> Temüjin workflow for backend issues."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._generate_id = Mock(return_value="jochi-analysis-id")
        memory._now = Mock(return_value=datetime.now(timezone.utc))

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"analysis_id": "jochi-analysis-id"}
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        # Jochi detects a performance issue and creates an analysis
        analysis_id = memory.create_analysis(
            agent="jochi",
            analysis_type="performance",
            severity="critical",
            description="Connection pool exhaustion detected - 97% usage",
            target_agent="ops",
            findings={"connection_pool_usage": 97, "active_connections": 48, "max_connections": 50},
            recommendations=[
                "Increase max_connection_pool_size",
                "Check for connection leaks",
                "Implement connection timeout"
            ],
            assigned_to="temujin"
        )

        assert analysis_id == "jochi-analysis-id"

        # Verify it was assigned to temujin
        call_args = mock_session.run.call_args
        assert call_args[1]["assigned_to"] == "temujin"
        assert call_args[1]["agent"] == "jochi"

    def test_performance_detection_to_analysis_workflow(self):
        """Test full workflow from metrics detection to analysis creation."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._generate_id = Mock(return_value="perf-analysis-id")
        memory._now = Mock(return_value=datetime.now(timezone.utc))

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"analysis_id": "perf-analysis-id"}
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        # Step 1: Detect performance issues from metrics
        metrics = {
            "connection_pool_usage": 85,
            "query_time_ms": 1200,
            "error_rate": 0.5
        }
        issues = memory.detect_performance_issues(metrics)

        assert len(issues) == 2  # connection_pool_high and slow_query

        # Step 2: Create analyses from detected issues
        analysis_ids = memory.create_analysis_from_issues(
            agent="jochi",
            issues=issues,
            target_agent="developer"
        )

        assert len(analysis_ids) == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
