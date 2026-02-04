"""
Test Suite for Temüjin Security Audit Protocol

Tests the security audit functionality in OperationalMemory including:
- SecurityAudit node creation
- Vulnerability tracking with severity levels
- Audit trail querying
- Resolution workflows
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


class TestSecurityAuditCreation:
    """Tests for creating security audits."""

    def test_create_security_audit_success(self):
        """Test successful creation of a security audit."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._generate_id = Mock(return_value="test-audit-id")
        memory._now = Mock(return_value=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc))

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"audit_id": "test-audit-id"}
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        audit_id = memory.create_security_audit(
            agent="developer",
            severity="high",
            category="auth",
            description="Weak password policy detected",
            resource="/app/src/auth.py"
        )

        assert audit_id == "test-audit-id"
        mock_session.run.assert_called_once()

    def test_create_security_audit_invalid_severity(self):
        """Test that invalid severity raises ValueError."""
        memory = OperationalMemory.__new__(OperationalMemory)

        with pytest.raises(ValueError, match="Invalid severity"):
            memory.create_security_audit(
                agent="developer",
                severity="invalid",
                category="auth",
                description="Test",
                resource="/app/test.py"
            )

    def test_create_security_audit_invalid_category(self):
        """Test that invalid category raises ValueError."""
        memory = OperationalMemory.__new__(OperationalMemory)

        with pytest.raises(ValueError, match="Invalid category"):
            memory.create_security_audit(
                agent="developer",
                severity="high",
                category="invalid_category",
                description="Test",
                resource="/app/test.py"
            )

    def test_create_security_audit_all_valid_severities(self):
        """Test that all valid severities are accepted."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._generate_id = Mock(return_value="test-id")
        memory._now = Mock(return_value=datetime.now(timezone.utc))

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"audit_id": "test-id"}
        mock_session.run.return_value = mock_result

        valid_severities = ['low', 'medium', 'high', 'critical']

        for severity in valid_severities:
            mock_session.reset_mock()
            memory._session = Mock(return_value=MockContextManager(mock_session))

            audit_id = memory.create_security_audit(
                agent="developer",
                severity=severity,
                category="auth",
                description=f"Test {severity}",
                resource="/app/test.py"
            )
            assert audit_id == "test-id", f"Failed for severity: {severity}"

    def test_create_security_audit_all_valid_categories(self):
        """Test that all valid categories are accepted."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._generate_id = Mock(return_value="test-id")
        memory._now = Mock(return_value=datetime.now(timezone.utc))

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"audit_id": "test-id"}
        mock_session.run.return_value = mock_result

        valid_categories = ['auth', 'injection', 'secrets', 'config', 'crypto', 'other']

        for category in valid_categories:
            mock_session.reset_mock()
            memory._session = Mock(return_value=MockContextManager(mock_session))

            audit_id = memory.create_security_audit(
                agent="developer",
                severity="medium",
                category=category,
                description=f"Test {category}",
                resource="/app/test.py"
            )
            assert audit_id == "test-id", f"Failed for category: {category}"

    def test_create_security_audit_fallback_mode(self):
        """Test that fallback mode returns audit ID without database."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._generate_id = Mock(return_value="fallback-audit-id")
        memory._now = Mock(return_value=datetime.now(timezone.utc))

        memory._session = Mock(return_value=MockContextManager(None))

        audit_id = memory.create_security_audit(
            agent="developer",
            severity="critical",
            category="secrets",
            description="API key exposed",
            resource="/app/config.py"
        )

        assert audit_id == "fallback-audit-id"


class TestSecurityAuditQueries:
    """Tests for querying security audits."""

    def test_list_security_audits_no_filters(self):
        """Test listing all security audits without filters."""
        memory = OperationalMemory.__new__(OperationalMemory)

        mock_session = MagicMock()
        mock_record = {
            "s": {
                "id": "audit-1",
                "agent": "developer",
                "severity": "high",
                "status": "open"
            }
        }
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([mock_record]))
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        audits = memory.list_security_audits()

        assert len(audits) == 1
        assert audits[0]["id"] == "audit-1"

    def test_list_security_audits_with_filters(self):
        """Test listing security audits with filters."""
        memory = OperationalMemory.__new__(OperationalMemory)

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([]))
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        audits = memory.list_security_audits(
            agent="developer",
            status="open",
            severity="critical",
            category="auth"
        )

        assert audits == []
        # Verify the query was called with correct parameters
        call_args = mock_session.run.call_args
        assert call_args[1]["agent"] == "developer"
        assert call_args[1]["status"] == "open"
        assert call_args[1]["severity"] == "critical"
        assert call_args[1]["category"] == "auth"

    def test_list_security_audits_with_date_range(self):
        """Test listing security audits with date range filters."""
        memory = OperationalMemory.__new__(OperationalMemory)

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([]))
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        date_from = datetime(2025, 1, 1, tzinfo=timezone.utc)
        date_to = datetime(2025, 1, 31, tzinfo=timezone.utc)

        audits = memory.list_security_audits(
            date_from=date_from,
            date_to=date_to
        )

        call_args = mock_session.run.call_args
        assert call_args[1]["date_from"] == date_from
        assert call_args[1]["date_to"] == date_to

    def test_list_security_audits_fallback_mode(self):
        """Test that fallback mode returns empty list."""
        memory = OperationalMemory.__new__(OperationalMemory)

        memory._session = Mock(return_value=MockContextManager(None))

        audits = memory.list_security_audits()

        assert audits == []

    def test_get_security_audit_by_id(self):
        """Test getting a specific security audit by ID."""
        memory = OperationalMemory.__new__(OperationalMemory)

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {
            "s": {
                "id": "audit-1",
                "agent": "developer",
                "severity": "high",
                "description": "Test issue"
            }
        }
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        audit = memory.get_security_audit("audit-1")

        assert audit is not None
        assert audit["id"] == "audit-1"
        assert audit["severity"] == "high"

    def test_get_security_audit_not_found(self):
        """Test getting a non-existent security audit."""
        memory = OperationalMemory.__new__(OperationalMemory)

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = None
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        audit = memory.get_security_audit("non-existent")

        assert audit is None


class TestSecurityAuditResolution:
    """Tests for resolving security audits."""

    def test_resolve_security_audit_success(self):
        """Test successfully resolving a security audit."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._now = Mock(return_value=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc))

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"audit_id": "audit-1"}
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        result = memory.resolve_security_audit(
            audit_id="audit-1",
            resolved_by="ops"
        )

        assert result is True

    def test_resolve_security_audit_not_found(self):
        """Test resolving a non-existent audit."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._now = Mock(return_value=datetime.now(timezone.utc))

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = None
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        result = memory.resolve_security_audit(
            audit_id="non-existent",
            resolved_by="ops"
        )

        assert result is False

    def test_resolve_security_audit_invalid_status(self):
        """Test that invalid status raises ValueError."""
        memory = OperationalMemory.__new__(OperationalMemory)

        with pytest.raises(ValueError, match="Status must be 'resolved' or 'ignored'"):
            memory.resolve_security_audit(
                audit_id="audit-1",
                resolved_by="ops",
                status="invalid"
            )

    def test_resolve_security_audit_as_ignored(self):
        """Test marking a security audit as ignored."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._now = Mock(return_value=datetime.now(timezone.utc))

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"audit_id": "audit-1"}
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        result = memory.resolve_security_audit(
            audit_id="audit-1",
            resolved_by="ops",
            status="ignored"
        )

        assert result is True
        # Verify the status was set to 'ignored'
        call_args = mock_session.run.call_args
        assert call_args[1]["status"] == "ignored"

    def test_resolve_security_audit_fallback_mode(self):
        """Test that fallback mode returns True."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._now = Mock(return_value=datetime.now(timezone.utc))

        memory._session = Mock(return_value=MockContextManager(None))

        result = memory.resolve_security_audit(
            audit_id="audit-1",
            resolved_by="ops"
        )

        assert result is True


class TestSecuritySummary:
    """Tests for security summary functionality."""

    def test_get_security_summary_empty(self):
        """Test getting summary when no audits exist."""
        memory = OperationalMemory.__new__(OperationalMemory)

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([]))
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        summary = memory.get_security_summary()

        assert summary["total"] == 0
        assert summary["by_severity"] == {"critical": 0, "high": 0, "medium": 0, "low": 0}
        assert summary["by_status"] == {"open": 0, "resolved": 0, "ignored": 0}
        assert summary["open_by_severity"] == {"critical": 0, "high": 0, "medium": 0, "low": 0}

    def test_get_security_summary_with_data(self):
        """Test getting summary with audit data."""
        memory = OperationalMemory.__new__(OperationalMemory)

        mock_session = MagicMock()
        mock_records = [
            {"severity": "critical", "status": "open", "count": 2},
            {"severity": "high", "status": "open", "count": 5},
            {"severity": "high", "status": "resolved", "count": 3},
            {"severity": "medium", "status": "open", "count": 10},
            {"severity": "low", "status": "ignored", "count": 1},
        ]
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter(mock_records))
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        summary = memory.get_security_summary()

        assert summary["total"] == 21  # Sum of all counts
        assert summary["by_severity"]["critical"] == 2
        assert summary["by_severity"]["high"] == 8  # 5 open + 3 resolved
        assert summary["by_status"]["open"] == 17  # 2 + 5 + 10
        assert summary["by_status"]["resolved"] == 3
        assert summary["open_by_severity"]["high"] == 5

    def test_get_security_summary_for_agent(self):
        """Test getting summary filtered by agent."""
        memory = OperationalMemory.__new__(OperationalMemory)

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([]))
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        summary = memory.get_security_summary(agent="developer")

        # Verify agent filter was passed
        call_args = mock_session.run.call_args
        assert call_args[1]["agent"] == "developer"

    def test_get_security_summary_fallback_mode(self):
        """Test that fallback mode returns zeroed summary."""
        memory = OperationalMemory.__new__(OperationalMemory)

        memory._session = Mock(return_value=MockContextManager(None))

        summary = memory.get_security_summary()

        assert summary["total"] == 0
        assert summary["by_severity"] == {"critical": 0, "high": 0, "medium": 0, "low": 0}
        assert summary["by_status"] == {"open": 0, "resolved": 0, "ignored": 0}


class TestSecurityAuditTrail:
    """Tests for security audit trail functionality."""

    def test_get_security_audit_trail_no_filters(self):
        """Test getting audit trail without filters."""
        memory = OperationalMemory.__new__(OperationalMemory)

        mock_session = MagicMock()
        mock_record = {
            "s": {"id": "audit-1", "agent": "developer"},
            "action_time": datetime(2025, 1, 10, 12, 0, 0, tzinfo=timezone.utc),
            "action_type": "created"
        }
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([mock_record]))
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        trail = memory.get_security_audit_trail()

        assert len(trail) == 1
        assert trail[0]["id"] == "audit-1"
        assert trail[0]["action_type"] == "created"

    def test_get_security_audit_trail_with_agent_filter(self):
        """Test getting audit trail filtered by agent."""
        memory = OperationalMemory.__new__(OperationalMemory)

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([]))
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        trail = memory.get_security_audit_trail(agent="developer")

        call_args = mock_session.run.call_args
        assert call_args[1]["agent"] == "developer"

    def test_get_security_audit_trail_with_date_range(self):
        """Test getting audit trail with date range."""
        memory = OperationalMemory.__new__(OperationalMemory)

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([]))
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        date_from = datetime(2025, 1, 1, tzinfo=timezone.utc)
        date_to = datetime(2025, 1, 31, tzinfo=timezone.utc)

        trail = memory.get_security_audit_trail(
            date_from=date_from,
            date_to=date_to
        )

        call_args = mock_session.run.call_args
        assert call_args[1]["date_from"] == date_from
        assert call_args[1]["date_to"] == date_to

    def test_get_security_audit_trail_fallback_mode(self):
        """Test that fallback mode returns empty list."""
        memory = OperationalMemory.__new__(OperationalMemory)

        memory._session = Mock(return_value=MockContextManager(None))

        trail = memory.get_security_audit_trail()

        assert trail == []


class TestSecurityAuditIndexes:
    """Tests for security audit indexes."""

    def test_create_indexes_includes_security_audit(self):
        """Test that create_indexes includes SecurityAudit indexes."""
        memory = OperationalMemory.__new__(OperationalMemory)

        mock_session = MagicMock()
        mock_session.run.return_value = None

        memory._session = Mock(return_value=MockContextManager(mock_session))

        created = memory.create_indexes()

        # Check that SecurityAudit indexes are included
        security_indexes = [name for name in created if 'securityaudit' in name.lower()]
        assert len(security_indexes) >= 5  # Should have at least id, agent, status, severity, created_at
        assert "securityaudit_id_idx" in security_indexes
        assert "securityaudit_agent_idx" in security_indexes
        assert "securityaudit_severity_idx" in security_indexes


class TestSecurityAuditIntegration:
    """Integration-style tests for security audit workflows."""

    def test_full_audit_lifecycle(self):
        """Test the full lifecycle of a security audit."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._generate_id = Mock(return_value="lifecycle-audit-id")
        memory._now = Mock(return_value=datetime.now(timezone.utc))

        # Mock session that returns appropriate results for each call
        mock_session = MagicMock()

        # First call: create audit
        create_result = MagicMock()
        create_result.single.return_value = {"audit_id": "lifecycle-audit-id"}

        # Second call: get audit
        get_result = MagicMock()
        get_result.single.return_value = {
            "s": {
                "id": "lifecycle-audit-id",
                "agent": "developer",
                "severity": "high",
                "category": "secrets",
                "status": "open"
            }
        }

        # Third call: resolve audit
        resolve_result = MagicMock()
        resolve_result.single.return_value = {"audit_id": "lifecycle-audit-id"}

        mock_session.run.side_effect = [create_result, get_result, resolve_result]

        memory._session = Mock(return_value=MockContextManager(mock_session))

        # 1. Create audit
        audit_id = memory.create_security_audit(
            agent="developer",
            severity="high",
            category="secrets",
            description="API key exposed in config",
            resource="/app/config.py"
        )
        assert audit_id == "lifecycle-audit-id"

        # 2. Get audit
        audit = memory.get_security_audit(audit_id)
        assert audit["severity"] == "high"
        assert audit["status"] == "open"

        # 3. Resolve audit
        result = memory.resolve_security_audit(audit_id, resolved_by="ops")
        assert result is True

    def test_critical_vulnerability_workflow(self):
        """Test workflow for critical vulnerabilities."""
        memory = OperationalMemory.__new__(OperationalMemory)
        memory._generate_id = Mock(return_value="critical-audit-id")
        memory._now = Mock(return_value=datetime.now(timezone.utc))

        mock_session = MagicMock()
        create_result = MagicMock()
        create_result.single.return_value = {"audit_id": "critical-audit-id"}
        mock_session.run.return_value = create_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        # Create critical vulnerability
        audit_id = memory.create_security_audit(
            agent="developer",
            severity="critical",
            category="injection",
            description="SQL injection vulnerability in user input",
            resource="/app/src/queries.py:45"
        )

        assert audit_id == "critical-audit-id"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
