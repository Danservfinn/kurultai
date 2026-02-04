"""
Test Suite for Ögedei Proactive Improvement Protocol

Tests the improvement tracking functionality including:
- Improvement creation with ROI calculation
- Approval workflow (Kublai approval required)
- Rejection workflow
- Implementation tracking
- Summary statistics
- Notifications
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock

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


class TestCreateImprovement:
    """Tests for create_improvement method."""

    def test_create_improvement_success(self):
        """Test successful improvement creation."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._generate_id = Mock(return_value="improvement-123")
        memory._now = Mock(return_value=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc))
        memory.create_notification = Mock()

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"improvement_id": "improvement-123"}
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        improvement_id = memory.create_improvement(
            submitted_by="ogedei",
            title="Optimize query performance",
            description="Add indexes to improve query speed",
            category="performance",
            expected_benefit="50% faster queries",
            effort_hours=4.0,
            improvement_value=10.0
        )

        assert improvement_id == "improvement-123"
        mock_session.run.assert_called_once()

        # Verify value_score calculation (10.0 / 4.0 = 2.5)
        call_args = mock_session.run.call_args
        assert call_args.kwargs["value_score"] == 2.5

        # Verify Kublai was notified
        memory.create_notification.assert_called_once()
        notif_args = memory.create_notification.call_args
        assert notif_args.kwargs["agent"] == "kublai"
        assert "improvement_pending_approval" == notif_args.kwargs["type"]

    def test_create_improvement_invalid_category(self):
        """Test improvement creation with invalid category."""
        memory = OperationalMemory.__new__(OperationalMemory)

        with pytest.raises(ValueError, match="Invalid category"):
            memory.create_improvement(
                submitted_by="ogedei",
                title="Test improvement",
                description="Test description",
                category="invalid_category",
                expected_benefit="Some benefit",
                effort_hours=2.0,
                improvement_value=5.0
            )

    def test_create_improvement_zero_effort(self):
        """Test improvement creation with zero effort hours."""
        memory = OperationalMemory.__new__(OperationalMemory)

        with pytest.raises(ValueError, match="effort_hours must be greater than 0"):
            memory.create_improvement(
                submitted_by="ogedei",
                title="Test improvement",
                description="Test description",
                category="workflow",
                expected_benefit="Some benefit",
                effort_hours=0.0,
                improvement_value=5.0
            )

    def test_create_improvement_negative_effort(self):
        """Test improvement creation with negative effort hours."""
        memory = OperationalMemory.__new__(OperationalMemory)

        with pytest.raises(ValueError, match="effort_hours must be greater than 0"):
            memory.create_improvement(
                submitted_by="ogedei",
                title="Test improvement",
                description="Test description",
                category="workflow",
                expected_benefit="Some benefit",
                effort_hours=-1.0,
                improvement_value=5.0
            )

    def test_create_improvement_fallback_mode(self):
        """Test improvement creation in fallback mode."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._generate_id = Mock(return_value="fallback-improvement-id")
        memory._now = Mock(return_value=datetime.now(timezone.utc))
        memory._session = Mock(return_value=MockContextManager(None))

        improvement_id = memory.create_improvement(
            submitted_by="ogedei",
            title="Fallback improvement",
            description="Test description",
            category="documentation",
            expected_benefit="Better docs",
            effort_hours=2.0,
            improvement_value=3.0
        )

        assert improvement_id == "fallback-improvement-id"

    def test_create_improvement_all_categories(self):
        """Test improvement creation with all valid categories."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._generate_id = Mock(return_value="improvement-id")
        memory._now = Mock(return_value=datetime.now(timezone.utc))
        memory.create_notification = Mock()

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"improvement_id": "improvement-id"}
        mock_session.run.return_value = mock_result
        memory._session = Mock(return_value=MockContextManager(mock_session))

        valid_categories = ['workflow', 'performance', 'security', 'documentation', 'other']

        for category in valid_categories:
            memory.create_improvement(
                submitted_by="ogedei",
                title=f"{category} improvement",
                description=f"Test {category} improvement",
                category=category,
                expected_benefit=f"Benefit of {category}",
                effort_hours=2.0,
                improvement_value=5.0
            )


class TestListImprovements:
    """Tests for list_improvements method."""

    def test_list_improvements_no_filters(self):
        """Test listing all improvements."""
        memory = OperationalMemory.__new__(OperationalMemory)

        mock_session = MagicMock()
        mock_result = [
            {"i": {"id": "i1", "title": "Improvement 1", "value_score": 2.5}},
            {"i": {"id": "i2", "title": "Improvement 2", "value_score": 3.0}}
        ]
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        improvements = memory.list_improvements()

        assert len(improvements) == 2
        assert improvements[0]["id"] == "i1"
        assert improvements[1]["id"] == "i2"

    def test_list_improvements_with_status_filter(self):
        """Test listing improvements with status filter."""
        memory = OperationalMemory.__new__(OperationalMemory)

        mock_session = MagicMock()
        mock_result = [{"i": {"id": "i1", "status": "proposed"}}]
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        improvements = memory.list_improvements(status="proposed")

        assert len(improvements) == 1
        call_args = mock_session.run.call_args
        assert "status" in str(call_args)

    def test_list_improvements_with_category_filter(self):
        """Test listing improvements with category filter."""
        memory = OperationalMemory.__new__(OperationalMemory)

        mock_session = MagicMock()
        mock_result = [{"i": {"id": "i1", "category": "performance"}}]
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        improvements = memory.list_improvements(category="performance")

        assert len(improvements) == 1
        call_args = mock_session.run.call_args
        assert "category" in str(call_args)

    def test_list_improvements_with_submitted_by_filter(self):
        """Test listing improvements with submitted_by filter."""
        memory = OperationalMemory.__new__(OperationalMemory)

        mock_session = MagicMock()
        mock_result = [{"i": {"id": "i1", "submitted_by": "ogedei"}}]
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        improvements = memory.list_improvements(submitted_by="ogedei")

        assert len(improvements) == 1
        call_args = mock_session.run.call_args
        assert "submitted_by" in str(call_args)

    def test_list_improvements_invalid_status(self):
        """Test listing improvements with invalid status."""
        memory = OperationalMemory.__new__(OperationalMemory)

        with pytest.raises(ValueError, match="Invalid status"):
            memory.list_improvements(status="invalid_status")

    def test_list_improvements_invalid_category(self):
        """Test listing improvements with invalid category."""
        memory = OperationalMemory.__new__(OperationalMemory)

        with pytest.raises(ValueError, match="Invalid category"):
            memory.list_improvements(category="invalid_category")

    def test_list_improvements_fallback_mode(self):
        """Test listing improvements in fallback mode."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._session = Mock(return_value=MockContextManager(None))

        improvements = memory.list_improvements()

        assert improvements == []


class TestApproveImprovement:
    """Tests for approve_improvement method."""

    def test_approve_improvement_success(self):
        """Test successful improvement approval."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._now = Mock(return_value=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc))
        memory.create_notification = Mock()

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {
            "submitted_by": "ogedei",
            "title": "Test Improvement"
        }
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        result = memory.approve_improvement("improvement-123", "kublai")

        assert result is True
        mock_session.run.assert_called_once()

        # Verify submitter was notified
        memory.create_notification.assert_called_once()
        notif_args = memory.create_notification.call_args
        assert notif_args.kwargs["agent"] == "ogedei"
        assert "improvement_approved" == notif_args.kwargs["type"]

    def test_approve_improvement_not_found(self):
        """Test approval for non-existent improvement."""
        memory = OperationalMemory.__new__(OperationalMemory)

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = None
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        result = memory.approve_improvement("nonexistent-id", "kublai")

        assert result is False

    def test_approve_improvement_fallback_mode(self):
        """Test approval in fallback mode."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._session = Mock(return_value=MockContextManager(None))

        result = memory.approve_improvement("improvement-123", "kublai")

        assert result is True


class TestRejectImprovement:
    """Tests for reject_improvement method."""

    def test_reject_improvement_success(self):
        """Test successful improvement rejection."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._now = Mock(return_value=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc))
        memory.create_notification = Mock()

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {
            "submitted_by": "ogedei",
            "title": "Test Improvement"
        }
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        result = memory.reject_improvement("improvement-123", "kublai", "Not aligned with priorities")

        assert result is True
        mock_session.run.assert_called_once()

        # Verify submitter was notified
        memory.create_notification.assert_called_once()
        notif_args = memory.create_notification.call_args
        assert notif_args.kwargs["agent"] == "ogedei"
        assert "improvement_rejected" == notif_args.kwargs["type"]
        assert "Not aligned with priorities" in notif_args.kwargs["summary"]

    def test_reject_improvement_not_found(self):
        """Test rejection for non-existent improvement."""
        memory = OperationalMemory.__new__(OperationalMemory)

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = None
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        result = memory.reject_improvement("nonexistent-id", "kublai", "Reason")

        assert result is False

    def test_reject_improvement_fallback_mode(self):
        """Test rejection in fallback mode."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._session = Mock(return_value=MockContextManager(None))

        result = memory.reject_improvement("improvement-123", "kublai", "Reason")

        assert result is True


class TestImplementImprovement:
    """Tests for implement_improvement method."""

    def test_implement_improvement_success(self):
        """Test successful improvement implementation."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._now = Mock(return_value=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc))
        memory.create_notification = Mock()

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {
            "submitted_by": "ogedei",
            "title": "Test Improvement",
            "approved_by": "kublai"
        }
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        result = memory.implement_improvement("improvement-123", "developer")

        assert result is True
        mock_session.run.assert_called_once()

        # Verify submitter was notified
        memory.create_notification.assert_called()
        notif_calls = memory.create_notification.call_args_list
        assert any("ogedei" == call.kwargs["agent"] for call in notif_calls)

    def test_implement_improvement_not_found(self):
        """Test implementation for non-existent improvement."""
        memory = OperationalMemory.__new__(OperationalMemory)

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = None
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        result = memory.implement_improvement("nonexistent-id", "developer")

        assert result is False

    def test_implement_improvement_fallback_mode(self):
        """Test implementation in fallback mode."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._session = Mock(return_value=MockContextManager(None))

        result = memory.implement_improvement("improvement-123", "developer")

        assert result is True


class TestGetImprovement:
    """Tests for get_improvement method."""

    def test_get_improvement_success(self):
        """Test successful improvement retrieval."""
        memory = OperationalMemory.__new__(OperationalMemory)

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"i": {"id": "i1", "title": "Test Improvement"}}
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        improvement = memory.get_improvement("improvement-123")

        assert improvement is not None
        assert improvement["id"] == "i1"
        assert improvement["title"] == "Test Improvement"

    def test_get_improvement_not_found(self):
        """Test getting non-existent improvement."""
        memory = OperationalMemory.__new__(OperationalMemory)

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = None
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        improvement = memory.get_improvement("nonexistent-id")

        assert improvement is None

    def test_get_improvement_fallback_mode(self):
        """Test getting improvement in fallback mode."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._session = Mock(return_value=MockContextManager(None))

        improvement = memory.get_improvement("improvement-123")

        assert improvement is None


class TestGetImprovementSummary:
    """Tests for get_improvement_summary method."""

    def test_get_improvement_summary_success(self):
        """Test successful summary retrieval."""
        memory = OperationalMemory.__new__(OperationalMemory)

        mock_session = MagicMock()

        # First query result (counts) - iterable
        count_result = [
            {"status": "proposed", "category": "performance", "count": 2},
            {"status": "approved", "category": "workflow", "count": 1},
            {"status": "implemented", "category": "security", "count": 3}
        ]

        # Second query result (high value pending) - iterable
        high_value_result = [
            {"id": "i1", "title": "High Value 1", "value_score": 5.0, "category": "performance"},
            {"id": "i2", "title": "High Value 2", "value_score": 4.0, "category": "workflow"}
        ]

        # Third query result (avg value score) - needs to be a mock with single() method
        avg_result_mock = MagicMock()
        avg_result_mock.single.return_value = {"avg_value_score": 3.5}

        # Use a list of returns that gets popped
        returns = [count_result, high_value_result, avg_result_mock]

        def side_effect(cypher, **kwargs):
            return returns.pop(0)

        mock_session.run = MagicMock(side_effect=side_effect)
        memory._session = Mock(return_value=MockContextManager(mock_session))

        summary = memory.get_improvement_summary()

        assert summary["total"] == 6
        assert summary["by_status"]["proposed"] == 2
        assert summary["by_status"]["approved"] == 1
        assert summary["by_status"]["implemented"] == 3
        assert summary["by_category"]["performance"] == 2
        assert summary["by_category"]["workflow"] == 1
        assert summary["by_category"]["security"] == 3
        assert len(summary["high_value_pending"]) == 2
        assert summary["avg_value_score"] == 3.5

    def test_get_improvement_summary_fallback_mode(self):
        """Test summary in fallback mode."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._session = Mock(return_value=MockContextManager(None))

        summary = memory.get_improvement_summary()

        assert summary["total"] == 0
        assert summary["by_status"]["proposed"] == 0
        assert summary["by_status"]["approved"] == 0
        assert summary["by_status"]["rejected"] == 0
        assert summary["by_status"]["implemented"] == 0
        assert summary["by_category"]["workflow"] == 0
        assert summary["by_category"]["performance"] == 0
        assert summary["by_category"]["security"] == 0
        assert summary["by_category"]["documentation"] == 0
        assert summary["by_category"]["other"] == 0
        assert summary["high_value_pending"] == []
        assert summary["avg_value_score"] == 0.0


class TestValueScoreCalculation:
    """Tests for value_score calculation."""

    def test_value_score_calculation(self):
        """Test that value_score is calculated correctly."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._generate_id = Mock(return_value="improvement-id")
        memory._now = Mock(return_value=datetime.now(timezone.utc))
        memory.create_notification = Mock()

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"improvement_id": "improvement-id"}
        mock_session.run.return_value = mock_result
        memory._session = Mock(return_value=MockContextManager(mock_session))

        # Test case: improvement_value=10, effort_hours=2, expected value_score=5.0
        memory.create_improvement(
            submitted_by="ogedei",
            title="Test",
            description="Test",
            category="workflow",
            expected_benefit="Test",
            effort_hours=2.0,
            improvement_value=10.0
        )

        call_args = mock_session.run.call_args
        assert call_args.kwargs["value_score"] == 5.0

    def test_value_score_fractional(self):
        """Test value_score with fractional values."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._generate_id = Mock(return_value="improvement-id")
        memory._now = Mock(return_value=datetime.now(timezone.utc))
        memory.create_notification = Mock()

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"improvement_id": "improvement-id"}
        mock_session.run.return_value = mock_result
        memory._session = Mock(return_value=MockContextManager(mock_session))

        # Test case: improvement_value=5, effort_hours=3, expected value_score=1.666...
        memory.create_improvement(
            submitted_by="ogedei",
            title="Test",
            description="Test",
            category="workflow",
            expected_benefit="Test",
            effort_hours=3.0,
            improvement_value=5.0
        )

        call_args = mock_session.run.call_args
        assert abs(call_args.kwargs["value_score"] - 1.6667) < 0.001


class TestWorkflowIntegration:
    """Integration tests for the full improvement workflow."""

    def test_full_workflow_success(self):
        """Test the full improvement workflow from creation to implementation."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._generate_id = Mock(return_value="workflow-improvement-123")
        memory._now = Mock(return_value=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc))
        memory.create_notification = Mock()

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {
            "improvement_id": "workflow-improvement-123",
            "submitted_by": "ogedei",
            "title": "Workflow Optimization"
        }
        mock_session.run.return_value = mock_result
        memory._session = Mock(return_value=MockContextManager(mock_session))

        # Step 1: Create improvement
        improvement_id = memory.create_improvement(
            submitted_by="ogedei",
            title="Workflow Optimization",
            description="Automate repetitive tasks",
            category="workflow",
            expected_benefit="Save 2 hours per day",
            effort_hours=8.0,
            improvement_value=20.0
        )
        assert improvement_id == "workflow-improvement-123"

        # Verify Kublai was notified of pending approval
        assert memory.create_notification.call_count == 1

    def test_rejection_workflow(self):
        """Test the rejection workflow."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._now = Mock(return_value=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc))
        memory.create_notification = Mock()

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {
            "submitted_by": "ogedei",
            "title": "Rejected Improvement"
        }
        mock_session.run.return_value = mock_result
        memory._session = Mock(return_value=MockContextManager(mock_session))

        result = memory.reject_improvement(
            "improvement-123",
            "kublai",
            "Insufficient ROI - effort exceeds expected benefit"
        )

        assert result is True

        # Verify submitter was notified
        memory.create_notification.assert_called_once()
        notif_args = memory.create_notification.call_args
        assert "rejected" in notif_args.kwargs["type"]
        assert "Insufficient ROI" in notif_args.kwargs["summary"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
