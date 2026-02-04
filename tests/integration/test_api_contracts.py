"""
Integration tests for API Contracts.

Tests cover:
- Agent-to-agent message contract
- Task delegation message format
- Task claimed notification format
- Task complete notification format
- Authentication header required
- Authorization agent allowlist

Location: /Users/kurultai/molt/tests/integration/test_api_contracts.py
"""

import os
import sys
import json
from datetime import datetime, timezone
from typing import Dict, Any, List
from unittest.mock import Mock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# API Contract Definitions
# =============================================================================

class APIContracts:
    """Definitions for API message contracts."""

    # Agent-to-agent message contract
    AGENT_TO_AGENT_MESSAGE = {
        "required_fields": ["from_agent", "to_agent", "message_type", "timestamp"],
        "message_types": ["task_delegation", "notification", "query", "response"],
        "from_agent_format": "^[a-z]+$",
        "to_agent_format": "^[a-z]+$"
    }

    # Task delegation message format
    TASK_DELEGATION = {
        "required_fields": [
            "task_id", "task_type", "description",
            "delegated_by", "assigned_to", "priority"
        ],
        "valid_priorities": ["low", "normal", "high", "critical"],
        "valid_types": ["research", "code", "analysis", "test", "documentation", "generic"]
    }

    # Task claimed notification format
    TASK_CLAIMED_NOTIFICATION = {
        "required_fields": ["notification_id", "task_id", "claimed_by", "claimed_at"],
        "timestamp_format": "ISO8601"
    }

    # Task complete notification format
    TASK_COMPLETE_NOTIFICATION = {
        "required_fields": [
            "notification_id", "task_id", "completed_by",
            "completed_at", "result"
        ],
        "timestamp_format": "ISO8601"
    }

    # Authentication requirements
    AUTH_HEADERS = {
        "required": ["X-Agent-ID", "X-Agent-Secret"],
        "optional": ["X-Request-ID"]
    }

    # Agent allowlist
    AGENT_ALLOWLIST = [
        "kublai", "jochi", "temüjin", "ögedei", "chagatai", "tolui"
    ]


# =============================================================================
# Contract Validator
# =============================================================================

class ContractValidator:
    """Validates API contracts."""

    def __init__(self):
        self.contracts = APIContracts()

    def validate_agent_to_agent_message(self, message: Dict) -> tuple[bool, List[str]]:
        """Validate agent-to-agent message contract."""
        errors = []

        # Check required fields
        for field in self.contracts.AGENT_TO_AGENT_MESSAGE["required_fields"]:
            if field not in message:
                errors.append(f"Missing required field: {field}")

        # Validate message type
        if "message_type" in message:
            if message["message_type"] not in self.contracts.AGENT_TO_AGENT_MESSAGE["message_types"]:
                errors.append(f"Invalid message_type: {message['message_type']}")

        # Validate agent format
        import re
        if "from_agent" in message and message["from_agent"] is not None:
            if not re.match(self.contracts.AGENT_TO_AGENT_MESSAGE["from_agent_format"], message["from_agent"]):
                errors.append(f"Invalid from_agent format: {message['from_agent']}")

        if "to_agent" in message and message["to_agent"] is not None:
            if not re.match(self.contracts.AGENT_TO_AGENT_MESSAGE["to_agent_format"], message["to_agent"]):
                errors.append(f"Invalid to_agent format: {message['to_agent']}")

        return len(errors) == 0, errors

    def validate_task_delegation(self, delegation: Dict) -> tuple[bool, List[str]]:
        """Validate task delegation message format."""
        errors = []

        for field in self.contracts.TASK_DELEGATION["required_fields"]:
            if field not in delegation:
                errors.append(f"Missing required field: {field}")

        # Validate priority
        if "priority" in delegation:
            if delegation["priority"] not in self.contracts.TASK_DELEGATION["valid_priorities"]:
                errors.append(f"Invalid priority: {delegation['priority']}")

        # Validate task type
        if "task_type" in delegation:
            if delegation["task_type"] not in self.contracts.TASK_DELEGATION["valid_types"]:
                errors.append(f"Invalid task_type: {delegation['task_type']}")

        return len(errors) == 0, errors

    def validate_task_claimed_notification(self, notification: Dict) -> tuple[bool, List[str]]:
        """Validate task claimed notification format."""
        errors = []

        for field in self.contracts.TASK_CLAIMED_NOTIFICATION["required_fields"]:
            if field not in notification:
                errors.append(f"Missing required field: {field}")

        return len(errors) == 0, errors

    def validate_task_complete_notification(self, notification: Dict) -> tuple[bool, List[str]]:
        """Validate task complete notification format."""
        errors = []

        for field in self.contracts.TASK_COMPLETE_NOTIFICATION["required_fields"]:
            if field not in notification:
                errors.append(f"Missing required field: {field}")

        return len(errors) == 0, errors

    def validate_auth_header(self, headers: Dict) -> tuple[bool, List[str]]:
        """Validate authentication header."""
        errors = []

        for field in self.contracts.AUTH_HEADERS["required"]:
            if field not in headers:
                errors.append(f"Missing required auth header: {field}")

        return len(errors) == 0, errors

    def validate_agent_allowlist(self, agent_id: str) -> bool:
        """Validate agent ID against allowlist."""
        return agent_id in self.contracts.AGENT_ALLOWLIST


# =============================================================================
# TestAPIContracts
# =============================================================================

class TestAPIContracts:
    """Tests for API contract validation."""

    @pytest.fixture
    def validator(self):
        return ContractValidator()

    def test_agent_to_agent_message_contract(self, validator):
        """Test agent-to-agent message contract validation."""
        valid_message = {
            "from_agent": "kublai",
            "to_agent": "jochi",
            "message_type": "task_delegation",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        is_valid, errors = validator.validate_agent_to_agent_message(valid_message)

        assert is_valid is True
        assert len(errors) == 0

    def test_agent_to_agent_message_missing_fields(self, validator):
        """Test validation fails with missing required fields."""
        invalid_message = {
            "from_agent": "kublai"
            # Missing to_agent, message_type, timestamp
        }

        is_valid, errors = validator.validate_agent_to_agent_message(invalid_message)

        assert is_valid is False
        assert len(errors) > 0

    def test_task_delegation_message_format(self, validator):
        """Test task delegation message format validation."""
        valid_delegation = {
            "task_id": "task-123",
            "task_type": "research",
            "description": "Investigate OAuth options",
            "delegated_by": "kublai",
            "assigned_to": "jochi",
            "priority": "high"
        }

        is_valid, errors = validator.validate_task_delegation(valid_delegation)

        assert is_valid is True
        assert len(errors) == 0

    def test_task_delegation_invalid_priority(self, validator):
        """Test validation with invalid priority."""
        invalid_delegation = {
            "task_id": "task-123",
            "task_type": "research",
            "description": "Test",
            "delegated_by": "kublai",
            "assigned_to": "jochi",
            "priority": "urgent"  # Invalid priority
        }

        is_valid, errors = validator.validate_task_delegation(invalid_delegation)

        assert is_valid is False
        assert any("priority" in e for e in errors)

    def test_task_claimed_notification_format(self, validator):
        """Test task claimed notification format validation."""
        valid_notification = {
            "notification_id": "notif-123",
            "task_id": "task-456",
            "claimed_by": "jochi",
            "claimed_at": datetime.now(timezone.utc).isoformat()
        }

        is_valid, errors = validator.validate_task_claimed_notification(valid_notification)

        assert is_valid is True

    def test_task_complete_notification_format(self, validator):
        """Test task complete notification format validation."""
        valid_notification = {
            "notification_id": "notif-789",
            "task_id": "task-456",
            "completed_by": "jochi",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "result": {"output": "Task completed successfully"}
        }

        is_valid, errors = validator.validate_task_complete_notification(valid_notification)

        assert is_valid is True

    def test_authentication_header_required(self, validator):
        """Test that authentication headers are required."""
        # Missing auth headers
        headers = {}

        is_valid, errors = validator.validate_auth_header(headers)

        assert is_valid is False
        assert len(errors) > 0

    def test_authentication_header_valid(self, validator):
        """Test valid authentication headers."""
        headers = {
            "X-Agent-ID": "jochi",
            "X-Agent-Secret": "secret-key-123"
        }

        is_valid, errors = validator.validate_auth_header(headers)

        assert is_valid is True

    def test_authorization_agent_allowlist(self, validator):
        """Test agent allowlist validation."""
        # Valid agents
        for agent in ["kublai", "jochi", "temüjin"]:
            assert validator.validate_agent_allowlist(agent) is True

        # Invalid agent
        assert validator.validate_agent_allowlist("unknown_agent") is False


# =============================================================================
# TestAPIContractEdgeCases
# =============================================================================

class TestAPIContractEdgeCases:
    """Edge case tests for API contracts."""

    @pytest.fixture
    def validator(self):
        return ContractValidator()

    def test_empty_message_validation(self, validator):
        """Test validation of empty message."""
        is_valid, errors = validator.validate_agent_to_agent_message({})

        assert is_valid is False
        assert len(errors) > 0

    def test_null_field_handling(self, validator):
        """Test handling of null field values."""
        message = {
            "from_agent": None,
            "to_agent": "jochi",
            "message_type": "notification",
            "timestamp": None
        }

        is_valid, errors = validator.validate_agent_to_agent_message(message)

        # Should fail due to null required fields
        assert is_valid is False

    def test_extra_fields_allowed(self, validator):
        """Test that extra fields don't break validation."""
        message = {
            "from_agent": "kublai",
            "to_agent": "jochi",
            "message_type": "notification",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "extra_field": "should be allowed"
        }

        is_valid, errors = validator.validate_agent_to_agent_message(message)

        assert is_valid is True

    def test_invalid_agent_format(self, validator):
        """Test invalid agent ID format."""
        message = {
            "from_agent": "Kublai-Khan",  # Invalid: uppercase and hyphen
            "to_agent": "jochi",
            "message_type": "notification",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        is_valid, errors = validator.validate_agent_to_agent_message(message)

        assert is_valid is False
        assert any("from_agent" in e for e in errors)


# =============================================================================
# TestAPIContractIntegration
# =============================================================================

class TestAPIContractIntegration:
    """Integration tests for API contracts."""

    @pytest.fixture
    def validator(self):
        return ContractValidator()

    def test_full_delegation_flow_contracts(self, validator):
        """Test contracts throughout full delegation flow."""
        # 1. Initial delegation message
        delegation = {
            "task_id": "task-123",
            "task_type": "code",
            "description": "Implement feature",
            "delegated_by": "kublai",
            "assigned_to": "jochi",
            "priority": "normal"
        }

        is_valid, _ = validator.validate_task_delegation(delegation)
        assert is_valid

        # 2. Claim notification
        claim = {
            "notification_id": "notif-claim",
            "task_id": "task-123",
            "claimed_by": "jochi",
            "claimed_at": datetime.now(timezone.utc).isoformat()
        }

        is_valid, _ = validator.validate_task_claimed_notification(claim)
        assert is_valid

        # 3. Complete notification
        complete = {
            "notification_id": "notif-complete",
            "task_id": "task-123",
            "completed_by": "jochi",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "result": {"status": "done"}
        }

        is_valid, _ = validator.validate_task_complete_notification(complete)
        assert is_valid

    def test_cross_agent_communication_contracts(self, validator):
        """Test contracts for cross-agent communication."""
        agents = ["kublai", "jochi", "temüjin"]

        for from_agent in agents:
            for to_agent in agents:
                if from_agent != to_agent:
                    message = {
                        "from_agent": from_agent,
                        "to_agent": to_agent,
                        "message_type": "query",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }

                    is_valid, _ = validator.validate_agent_to_agent_message(message)
                    assert is_valid
