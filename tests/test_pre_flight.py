"""
Tests for Pre-Flight Testing Checklist

Comprehensive test coverage for all pre-flight check modules.
Tests environment validation, Neo4j connectivity, authentication,
and agent operational checks.
"""

import pytest
import json
import os
import tempfile
import hashlib
import hmac
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock, mock_open

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.check_types import (
    CheckResult,
    CheckStatus,
    CheckCategory,
    GoNoGoDecision
)
from scripts.pre_flight_check import PreFlightCheck
from scripts.check_environment import EnvironmentChecker, EnvironmentConfig
from scripts.check_neo4j import Neo4jChecker, Neo4jConfig
from scripts.check_auth import AuthChecker, AuthConfig
from scripts.check_agents import AgentChecker, AgentConfig


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def temp_config_file():
    """Create a temporary moltbot.json config file."""
    config = {
        "gateway": {
            "mode": "local",
            "port": 18789,
            "auth": {
                "mode": "token",
                "token": "test_gateway_token_32_chars_minimum"
            }
        },
        "agents": {
            "defaults": {
                "workspace": "/data/workspace",
                "model": {
                    "primary": "test-model"
                }
            },
            "list": [
                {"id": "main", "name": "Kublai", "default": True, "agentDir": "/data/agents/main"},
                {"id": "researcher", "name": "Mongke", "agentDir": "/data/agents/researcher"},
                {"id": "writer", "name": "Chagatai", "agentDir": "/data/agents/writer"},
                {"id": "developer", "name": "Temujin", "agentDir": "/data/agents/developer"},
                {"id": "analyst", "name": "Jochi", "agentDir": "/data/agents/analyst"},
                {"id": "ops", "name": "Ogedei", "agentDir": "/data/agents/ops", "failoverFor": ["main"]}
            ]
        },
        "channels": {
            "signal": {
                "enabled": True,
                "account": "+15165643945",
                "allowFrom": ["+15165643945", "+19194133445"]
            }
        },
        "session": {
            "scope": "per-sender"
        },
        "tools": {
            "agentToAgent": {
                "enabled": True,
                "allow": ["main", "researcher", "writer", "developer", "analyst", "ops"]
            }
        }
    }

    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(config, f)

    yield path

    # Cleanup
    os.unlink(path)


@pytest.fixture
def temp_env_file():
    """Create a temporary .env file."""
    env_content = """
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=test_password_16_chars
OPENCLAW_GATEWAY_TOKEN=test_gateway_token_32_chars_minimum
AGENTS_HMAC_SECRET=test_hmac_secret_64_chars_long_for_agent_auth_minimumxxxxxxxxxxx
SIGNAL_ACCOUNT_NUMBER=+15165643945
ADMIN_PHONE_1=+15165643945
ADMIN_PHONE_2=+19194133445
AWS_ACCESS_KEY_ID=test_key
AWS_SECRET_ACCESS_KEY=test_secret
BACKUP_ENCRYPTION_KEY=test_encryption_key_16_chars
"""

    fd, path = tempfile.mkstemp(suffix=".env")
    with os.fdopen(fd, "w") as f:
        f.write(env_content)

    yield path

    # Cleanup
    os.unlink(path)


@pytest.fixture
def valid_env_vars():
    """Valid environment variables for testing."""
    return {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "test_password_16_chars",
        "OPENCLAW_GATEWAY_TOKEN": "test_gateway_token_32_chars_minimum",
        "AGENTS_HMAC_SECRET": "test_hmac_secret_64_chars_long_for_agent_auth_min_64_____",
        "SIGNAL_ACCOUNT_NUMBER": "+15165643945",
        "ADMIN_PHONE_1": "+15165643945",
        "ADMIN_PHONE_2": "+19194133445",
        "AWS_ACCESS_KEY_ID": "test_key",
        "AWS_SECRET_ACCESS_KEY": "test_secret",
        "BACKUP_ENCRYPTION_KEY": "test_encryption_key_16_chars"
    }


# =============================================================================
# CheckResult Tests
# =============================================================================

class TestCheckResult:
    """Tests for CheckResult dataclass."""

    def test_check_result_creation(self):
        """Test creating a CheckResult."""
        result = CheckResult(
            check_id="ENV-001",
            category=CheckCategory.ENVIRONMENT,
            description="Test check",
            critical=True,
            status=CheckStatus.PASS,
            expected="Value >= 32",
            actual="64 chars",
            output="PASS (64 chars)"
        )

        assert result.check_id == "ENV-001"
        assert result.category == CheckCategory.ENVIRONMENT
        assert result.description == "Test check"
        assert result.critical is True
        assert result.status == CheckStatus.PASS
        assert result.expected == "Value >= 32"
        assert result.actual == "64 chars"
        assert result.output == "PASS (64 chars)"

    def test_check_result_to_dict(self):
        """Test converting CheckResult to dictionary."""
        result = CheckResult(
            check_id="NEO-001",
            category=CheckCategory.NEO4J,
            description="Neo4j check",
            critical=True,
            status=CheckStatus.PASS
        )

        data = result.to_dict()

        assert data["check_id"] == "NEO-001"
        assert data["category"] == "neo4j"
        assert data["critical"] is True
        assert data["status"] == "pass"

    def test_check_result_from_dict(self):
        """Test creating CheckResult from dictionary."""
        data = {
            "check_id": "AUTH-001",
            "category": "authentication",
            "description": "Auth check",
            "critical": True,
            "status": "pass",
            "expected": "Valid",
            "actual": "Valid",
            "output": "PASS",
            "timestamp": "2024-01-01T00:00:00Z",
            "duration_ms": 10.5,
            "details": {}
        }

        result = CheckResult.from_dict(data)

        assert result.check_id == "AUTH-001"
        assert result.category == CheckCategory.AUTHENTICATION
        assert result.status == CheckStatus.PASS


# =============================================================================
# GoNoGoDecision Tests
# =============================================================================

class TestGoNoGoDecision:
    """Tests for GoNoGoDecision dataclass."""

    def test_go_decision(self):
        """Test a Go decision."""
        decision = GoNoGoDecision(
            decision="GO",
            pass_rate=0.95,
            critical_passed=True,
            total_checks=30,
            passed_checks=28,
            failed_checks=1,
            warning_checks=1,
            skipped_checks=0,
            reasoning="All critical checks passed and 95% pass rate"
        )

        assert decision.decision == "GO"
        assert decision.pass_rate == 0.95
        assert decision.critical_passed is True

    def test_no_go_decision(self):
        """Test a No-Go decision."""
        decision = GoNoGoDecision(
            decision="NO-GO",
            pass_rate=0.80,
            critical_passed=False,
            total_checks=30,
            passed_checks=24,
            failed_checks=6,
            warning_checks=0,
            skipped_checks=0,
            reasoning="3 critical checks failed and pass rate below 90%",
            blockers=["ENV-001: Gateway token too short", "NEO-002: Neo4j not reachable"]
        )

        assert decision.decision == "NO-GO"
        assert decision.pass_rate == 0.80
        assert decision.critical_passed is False
        assert len(decision.blockers) == 2


# =============================================================================
# EnvironmentChecker Tests
# =============================================================================

class TestEnvironmentChecker:
    """Tests for EnvironmentChecker."""

    def test_check_gateway_token_pass(self, temp_env_file):
        """Test gateway token check with valid token."""
        checker = EnvironmentChecker(env_path=temp_env_file)
        result = checker._check_gateway_token()

        assert result["status"] == CheckStatus.PASS
        assert result["details"]["token_length"] >= 32

    def test_check_gateway_token_fail_short(self):
        """Test gateway token check with short token."""
        checker = EnvironmentChecker(env_vars={"OPENCLAW_GATEWAY_TOKEN": "short"})
        result = checker._check_gateway_token()

        assert result["status"] == CheckStatus.FAIL
        assert result["details"]["token_length"] < 32

    def test_check_gateway_token_fail_missing(self):
        """Test gateway token check with missing token."""
        checker = EnvironmentChecker(env_vars={})
        result = checker._check_gateway_token()

        assert result["status"] == CheckStatus.FAIL
        assert result["details"]["token_length"] == 0

    def test_check_neo4j_password_pass(self, temp_env_file):
        """Test Neo4j password check with valid password."""
        checker = EnvironmentChecker(env_path=temp_env_file)
        result = checker._check_neo4j_password()

        assert result["status"] == CheckStatus.PASS
        assert result["details"]["password_length"] >= 16

    def test_check_neo4j_password_fail_short(self):
        """Test Neo4j password check with short password."""
        checker = EnvironmentChecker(env_vars={"NEO4J_PASSWORD": "short"})
        result = checker._check_neo4j_password()

        assert result["status"] == CheckStatus.FAIL
        assert result["details"]["password_length"] < 16

    def test_check_hmac_secret_pass(self, temp_env_file):
        """Test HMAC secret check with valid secret."""
        checker = EnvironmentChecker(env_path=temp_env_file)
        result = checker._check_hmac_secret()

        assert result["status"] == CheckStatus.PASS
        assert result["details"]["secret_length"] >= 64

    def test_check_hmac_secret_fail_short(self):
        """Test HMAC secret check with short secret."""
        checker = EnvironmentChecker(env_vars={"AGENTS_HMAC_SECRET": "short"})
        result = checker._check_hmac_secret()

        assert result["status"] == CheckStatus.FAIL
        assert result["details"]["secret_length"] < 64

    def test_check_signal_account_pass(self, temp_env_file):
        """Test Signal account check with valid account."""
        checker = EnvironmentChecker(env_path=temp_env_file)
        result = checker._check_signal_account()

        assert result["status"] == CheckStatus.PASS

    def test_check_signal_account_warn_invalid_format(self):
        """Test Signal account check with invalid format."""
        checker = EnvironmentChecker(env_vars={"SIGNAL_ACCOUNT_NUMBER": "invalid"})
        result = checker._check_signal_account()

        assert result["status"] == CheckStatus.WARN

    def test_check_admin_phones_pass(self, temp_env_file):
        """Test admin phones check with valid phones."""
        checker = EnvironmentChecker(env_path=temp_env_file)
        result = checker._check_admin_phones()

        assert result["status"] == CheckStatus.PASS
        assert result["details"]["admin_phones"]  # At least one phone

    def test_check_storage_credentials_pass(self, temp_env_file):
        """Test storage credentials check with AWS credentials."""
        checker = EnvironmentChecker(env_path=temp_env_file)
        result = checker._check_storage_credentials()

        assert result["status"] == CheckStatus.PASS
        assert result["details"]["aws"] is True

    def test_check_storage_credentials_warn(self):
        """Test storage credentials check with no credentials."""
        checker = EnvironmentChecker(env_vars={})
        result = checker._check_storage_credentials()

        assert result["status"] == CheckStatus.WARN

    def test_check_backup_key_pass(self, temp_env_file):
        """Test backup encryption key check with valid key."""
        checker = EnvironmentChecker(env_path=temp_env_file)
        result = checker._check_backup_key()

        assert result["status"] == CheckStatus.PASS

    def test_check_workspace_dir_warn_not_found(self):
        """Test workspace directory check when not found."""
        checker = EnvironmentChecker(env_vars={"WORKSPACE_DIR": "/nonexistent/path"})
        result = checker._check_workspace_dir()

        assert result["status"] == CheckStatus.WARN

    def test_check_config_json_pass(self, temp_config_file):
        """Test config JSON check with valid config."""
        checker = EnvironmentChecker(config_path=temp_config_file)
        result = checker._check_config_json()

        assert result["status"] == CheckStatus.PASS
        assert result["details"]["agent_count"] == 6

    def test_check_config_json_fail_invalid(self):
        """Test config JSON check with invalid config."""
        checker = EnvironmentChecker(config_path="/nonexistent/path.json")
        result = checker._check_config_json()

        assert result["status"] == CheckStatus.FAIL

    @patch('os.path.exists')
    def test_check_docker_socket_pass(self, mock_exists):
        """Test Docker socket check when socket exists."""
        mock_exists.return_value = True
        mock_access = patch('os.access', return_value=True)

        with mock_exists, mock_access:
            checker = EnvironmentChecker()
            result = checker._check_docker_socket()

        assert result["status"] == CheckStatus.PASS

    def test_run_all_environment_checks(self, temp_config_file, temp_env_file):
        """Test running all environment checks."""
        checker = EnvironmentChecker(
            config_path=temp_config_file,
            env_path=temp_env_file
        )
        results = checker.run_all_checks()

        assert len(results) == 12  # ENV-001 through ENV-012
        check_ids = [r.check_id for r in results]
        assert "ENV-001" in check_ids
        assert "ENV-012" in check_ids


# =============================================================================
# Neo4jChecker Tests
# =============================================================================

class TestNeo4jChecker:
    """Tests for Neo4jChecker."""

    def test_init(self):
        """Test Neo4jChecker initialization."""
        checker = Neo4jChecker(
            uri="bolt://localhost:7687",
            username="neo4j",
            password="password"
        )

        assert checker.uri == "bolt://localhost:7687"
        assert checker.username == "neo4j"
        assert checker.password == "password"
        assert checker.host == "localhost"
        assert checker.port == 7687

    @patch('socket.socket')
    def test_check_reachable_pass(self, mock_socket_class):
        """Test Neo4j reachable check when reachable."""
        mock_socket = MagicMock()
        mock_socket.connect_ex.return_value = 0
        mock_socket_class.return_value = mock_socket

        checker = Neo4jChecker()
        result = checker._check_reachable()

        assert result["status"] == CheckStatus.PASS
        assert "PASS" in result["output"]

    @patch('socket.socket')
    def test_check_reachable_fail(self, mock_socket_class):
        """Test Neo4j reachable check when not reachable."""
        mock_socket = MagicMock()
        mock_socket.connect_ex.return_value = 1  # Connection failed
        mock_socket_class.return_value = mock_socket

        checker = Neo4jChecker()
        result = checker._check_reachable()

        assert result["status"] == CheckStatus.FAIL
        assert "FAIL" in result["output"]

    @patch('socket.socket')
    def test_check_reachable_fail_dns(self, mock_socket_class):
        """Test Neo4j reachable check with DNS failure."""
        mock_socket = MagicMock()
        mock_socket.connect_ex.side_effect = OSError("Name or service not known")
        mock_socket_class.return_value = mock_socket

        checker = Neo4jChecker(uri="bolt://invalid_host:7687")
        result = checker._check_reachable()

        assert result["status"] == CheckStatus.FAIL

    def test_check_indexes_pass(self):
        """Test index check with sufficient indexes."""
        mock_indexes = [
            {"name": "Task_id"},
            {"name": "Task_status"},
            {"name": "Notification_agent"},
            {"name": "Agent_name"},
            {"name": "RateLimit_composite"},
            {"name": "SignalSession_sender_hash"},
            {"name": "SignalSession_current_agent"},
            {"name": "Task_created_at"},
            {"name": "Task_assigned_to"},
            {"name": "Notification_read"}
        ]

        with patch.object(Neo4jChecker, '_get_driver') as mock_get_driver:
            mock_driver = MagicMock()
            mock_session = MagicMock()

            # Create mock record objects
            mock_records = []
            for idx_data in mock_indexes:
                mock_record = MagicMock()
                mock_record.data.return_value = idx_data
                mock_records.append(mock_record)

            mock_result = MagicMock()
            mock_result.__iter__ = MagicMock(return_value=iter(mock_records))
            mock_session.run.return_value = mock_result
            mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
            mock_get_driver.return_value = mock_driver

            checker = Neo4jChecker()
            result = checker._check_indexes()

        assert result["status"] == CheckStatus.PASS
        assert result["details"]["index_count"] >= 10

    def test_check_constraints_pass(self):
        """Test constraint check with sufficient constraints."""
        mock_constraints = [
            {"name": "Task_id_unique"},
            {"name": "Notification_id_unique"},
            {"name": "Agent_name_unique"},
            {"name": "RateLimit_composite_unique"},
            {"name": "SignalSession_thread_id_unique"}
        ]

        with patch.object(Neo4jChecker, '_get_driver') as mock_get_driver:
            mock_driver = MagicMock()
            mock_session = MagicMock()

            # Create mock record objects
            mock_records = []
            for cons_data in mock_constraints:
                mock_record = MagicMock()
                mock_record.data.return_value = cons_data
                mock_records.append(mock_record)

            mock_result = MagicMock()
            mock_result.__iter__ = MagicMock(return_value=iter(mock_records))
            mock_session.run.return_value = mock_result
            mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
            mock_get_driver.return_value = mock_driver

            checker = Neo4jChecker()
            result = checker._check_constraints()

        assert result["status"] == CheckStatus.PASS
        assert result["details"]["constraint_count"] >= 5

    def test_check_query_performance_pass(self):
        """Test query performance check with fast query."""
        with patch.object(Neo4jChecker, '_get_driver') as mock_get_driver:
            import time
            mock_driver = MagicMock()
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_record = MagicMock()
            mock_record.__getitem__ = lambda self, key: 100  # node count

            mock_result.single.return_value = mock_record
            mock_session.run.return_value = mock_result
            mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
            mock_get_driver.return_value = mock_driver

            # Patch time to make query appear fast
            with patch('time.time', return_value=1000):
                with patch('time.sleep'):  # Avoid actual sleep
                    checker = Neo4jChecker()
                    result = checker._check_query_performance()

        # Should pass since we're mocking a fast query
        assert result["status"] in [CheckStatus.PASS, CheckStatus.WARN]


# =============================================================================
# AuthChecker Tests
# =============================================================================

class TestAuthChecker:
    """Tests for AuthChecker."""

    def test_init(self):
        """Test AuthChecker initialization."""
        checker = AuthChecker(
            gateway_token="test_token_32_chars_minimum",
            hmac_secret="test_hmac_secret_64_chars_long_for_agent_auth_min_64_____"
        )

        assert checker.gateway_token == "test_token_32_chars_minimum"
        assert checker.hmac_secret == "test_hmac_secret_64_chars_long_for_agent_auth_min_64_____"

    def test_generate_hmac(self):
        """Test HMAC generation."""
        checker = AuthChecker(hmac_secret="test_secret")
        signature = checker._generate_hmac("test message", "test_secret_64_chars_long________________________")

        assert len(signature) == 64  # 32 bytes * 2 (hex)
        assert all(c in "0123456789abcdef" for c in signature)

    def test_verify_hmac_valid(self):
        """Test HMAC verification with valid signature."""
        checker = AuthChecker(hmac_secret="test_secret")
        message = "test message"
        secret = "test_secret_64_chars_long________________________"

        signature = checker._generate_hmac(message, secret)
        is_valid = checker._verify_hmac(message, signature, secret)

        assert is_valid is True

    def test_verify_hmac_invalid(self):
        """Test HMAC verification with invalid signature."""
        checker = AuthChecker(hmac_secret="test_secret")
        message = "test message"
        secret = "test_secret_64_chars_long________________________"

        invalid_signature = checker._generate_hmac("different message", secret)
        is_valid = checker._verify_hmac(message, invalid_signature, secret)

        assert is_valid is False

    def test_check_hmac_generation_pass(self):
        """Test HMAC generation check."""
        checker = AuthChecker(
            hmac_secret="test_secret_64_chars_long_for_agent_auth_min_64_____"
        )
        result = checker._check_hmac_generation()

        assert result["status"] == CheckStatus.PASS
        assert result["details"]["length"] == 64
        assert result["details"]["is_hex"] is True

    def test_check_hmac_verification_pass(self):
        """Test HMAC verification check."""
        checker = AuthChecker(
            hmac_secret="test_secret_64_chars_long_for_agent_auth_min_64_____"
        )
        result = checker._check_hmac_verification()

        assert result["status"] == CheckStatus.PASS
        assert result["details"]["verified"] is True

    def test_check_hmac_rejection_pass(self):
        """Test HMAC rejection check."""
        checker = AuthChecker(
            hmac_secret="test_secret_64_chars_long_for_agent_auth_min_64_____"
        )
        result = checker._check_hmac_rejection()

        assert result["status"] == CheckStatus.PASS
        assert result["details"]["verified"] is False  # Invalid signature rejected

    def test_check_gateway_token_pass(self):
        """Test gateway token validation check."""
        checker = AuthChecker(
            gateway_token="test_token_32_chars_minimum_valid"
        )
        result = checker._check_gateway_token()

        assert result["status"] == CheckStatus.PASS
        assert result["details"]["length"] >= 32

    def test_check_gateway_token_warn(self):
        """Test gateway token validation check with short token."""
        checker = AuthChecker(gateway_token="short")
        result = checker._check_gateway_token()

        assert result["status"] == CheckStatus.WARN

    def test_check_agent_to_agent_auth_pass(self):
        """Test agent-to-agent authentication check."""
        checker = AuthChecker(
            hmac_secret="test_secret_64_chars_long_for_agent_auth_min_64_____"
        )
        result = checker._check_agent_to_agent_auth()

        assert result["status"] == CheckStatus.PASS
        assert result["details"]["from"] == "main"

    def test_check_message_signature_pass(self):
        """Test message signature validation check."""
        checker = AuthChecker(
            hmac_secret="test_secret_64_chars_long_for_agent_auth_min_64_____"
        )
        result = checker._check_message_signature()

        assert result["status"] == CheckStatus.PASS
        assert "signature" in result["details"]["fields"]

    def test_run_all_auth_checks(self):
        """Test running all authentication checks."""
        checker = AuthChecker(
            gateway_token="test_token_32_chars_minimum_valid",
            hmac_secret="test_secret_64_chars_long_for_agent_auth_min_64_____"
        )
        results = checker.run_all_checks()

        assert len(results) == 7  # AUTH-001 through AUTH-007
        check_ids = [r.check_id for r in results]
        assert "AUTH-001" in check_ids
        assert "AUTH-007" in check_ids


# =============================================================================
# AgentChecker Tests
# =============================================================================

class TestAgentChecker:
    """Tests for AgentChecker."""

    def test_init(self, temp_config_file):
        """Test AgentChecker initialization."""
        with open(temp_config_file, "r") as f:
            config = json.load(f)

        checker = AgentChecker(config=config)

        assert checker.config == config
        assert len(checker.agents) == 6

    def test_check_agent_count_pass(self, temp_config_file):
        """Test agent count check with sufficient agents."""
        with open(temp_config_file, "r") as f:
            config = json.load(f)

        checker = AgentChecker(config=config)
        result = checker._check_agent_count()

        assert result["status"] == CheckStatus.PASS
        assert result["details"]["agent_count"] >= 6

    def test_check_agent_count_fail(self):
        """Test agent count check with insufficient agents."""
        config = {
            "agents": {
                "list": [
                    {"id": "main"},
                    {"id": "researcher"}
                ]
            }
        }

        checker = AgentChecker(config=config)
        result = checker._check_agent_count()

        assert result["status"] == CheckStatus.FAIL
        assert result["details"]["agent_count"] < 6

    def test_check_agent_directories_pass(self, temp_config_file):
        """Test agent directories check."""
        with open(temp_config_file, "r") as f:
            config = json.load(f)

        # Mock os.path.isdir to return True
        with patch('os.path.exists', return_value=True):
            with patch('os.path.isdir', return_value=True):
                checker = AgentChecker(config=config)
                result = checker._check_agent_directories()

        assert result["status"] == CheckStatus.PASS

    def test_check_agent_models_pass(self, temp_config_file):
        """Test agent models check."""
        with open(temp_config_file, "r") as f:
            config = json.load(f)

        checker = AgentChecker(config=config)
        result = checker._check_agent_models()

        assert result["status"] == CheckStatus.PASS
        assert len(result["details"]["agents"]) == 6

    def test_check_agent_communication_pass(self, temp_config_file):
        """Test agent-to-agent communication check."""
        with open(temp_config_file, "r") as f:
            config = json.load(f)

        checker = AgentChecker(config=config)
        result = checker._check_agent_communication()

        assert result["status"] == CheckStatus.PASS
        assert result["details"]["enabled"] is True

    def test_check_failover_config_pass(self, temp_config_file):
        """Test failover configuration check."""
        with open(temp_config_file, "r") as f:
            config = json.load(f)

        checker = AgentChecker(config=config)
        result = checker._check_failover_config()

        assert result["status"] == CheckStatus.PASS
        assert len(result["details"]["failover_rules"]) > 0

    def test_check_default_agent_pass(self, temp_config_file):
        """Test default agent check."""
        with open(temp_config_file, "r") as f:
            config = json.load(f)

        checker = AgentChecker(config=config)
        result = checker._check_default_agent()

        assert result["status"] == CheckStatus.PASS
        assert result["details"]["default_agent"] == "main"

    def test_check_unique_ids_pass(self, temp_config_file):
        """Test unique agent IDs check."""
        with open(temp_config_file, "r") as f:
            config = json.load(f)

        checker = AgentChecker(config=config)
        result = checker._check_unique_ids()

        assert result["status"] == CheckStatus.PASS
        assert len(result["details"]["agent_ids"]) == 6

    def test_check_unique_ids_fail(self):
        """Test unique agent IDs check with duplicates."""
        config = {
            "agents": {
                "list": [
                    {"id": "main"},
                    {"id": "main"}  # Duplicate
                ]
            }
        }

        checker = AgentChecker(config=config)
        result = checker._check_unique_ids()

        assert result["status"] == CheckStatus.FAIL
        assert "main" in result["details"]["duplicates"]

    def test_run_all_agent_checks(self, temp_config_file):
        """Test running all agent checks."""
        with open(temp_config_file, "r") as f:
            config = json.load(f)

        checker = AgentChecker(config=config)

        # Mock filesystem checks
        with patch('os.path.exists', return_value=True):
            with patch('os.path.isdir', return_value=True):
                with patch('os.access', return_value=True):
                    results = checker.run_all_checks()

        assert len(results) == 8  # AGENT-001 through AGENT-008
        check_ids = [r.check_id for r in results]
        assert "AGENT-001" in check_ids
        assert "AGENT-008" in check_ids


# =============================================================================
# PreFlightCheck Tests
# =============================================================================

class TestPreFlightCheck:
    """Tests for PreFlightCheck orchestration."""

    def test_init(self, temp_config_file, temp_env_file):
        """Test PreFlightCheck initialization."""
        checker = PreFlightCheck(
            config_path=temp_config_file,
            env_path=temp_env_file
        )

        assert checker.config_path == temp_config_file
        assert checker.env_path == temp_env_file
        assert checker.config is not None
        assert checker.env_vars is not None

    def test_run_environment_checks(self, temp_config_file, temp_env_file):
        """Test running environment checks through main checker."""
        checker = PreFlightCheck(
            config_path=temp_config_file,
            env_path=temp_env_file
        )
        results = checker.run_environment_checks()

        assert len(results) == 12  # ENV-001 through ENV-012
        assert all(r.category == CheckCategory.ENVIRONMENT for r in results)

    def test_run_neo4j_checks(self, temp_config_file, temp_env_file):
        """Test running Neo4j checks through main checker."""
        checker = PreFlightCheck(
            config_path=temp_config_file,
            env_path=temp_env_file
        )

        # Mock Neo4j checks to avoid actual connection
        with patch.object(Neo4jChecker, 'run_all_checks') as mock_neo:
            mock_neo.return_value = [
                CheckResult(
                    check_id="NEO-001",
                    category=CheckCategory.NEO4J,
                    description="Test",
                    critical=True,
                    status=CheckStatus.PASS
                )
            ]

            results = checker.run_neo4j_checks()

        assert len(results) > 0
        assert all(r.category == CheckCategory.NEO4J for r in results)

    def test_run_auth_checks(self, temp_config_file, temp_env_file):
        """Test running authentication checks through main checker."""
        checker = PreFlightCheck(
            config_path=temp_config_file,
            env_path=temp_env_file
        )
        results = checker.run_auth_checks()

        assert len(results) == 7  # AUTH-001 through AUTH-007
        assert all(r.category == CheckCategory.AUTHENTICATION for r in results)

    def test_run_agent_checks(self, temp_config_file, temp_env_file):
        """Test running agent checks through main checker."""
        checker = PreFlightCheck(
            config_path=temp_config_file,
            env_path=temp_env_file
        )
        results = checker.run_agent_checks()

        assert len(results) == 8  # AGENT-001 through AGENT-008
        assert all(r.category == CheckCategory.AGENTS for r in results)

    def test_go_no_go_decision_go(self, temp_config_file, temp_env_file):
        """Test Go/No-Go decision with GO result."""
        checker = PreFlightCheck(
            config_path=temp_config_file,
            env_path=temp_env_file
        )

        # Create all passing results
        checker.results = [
            CheckResult(
                check_id=f"TEST-{i:03d}",
                category=CheckCategory.ENVIRONMENT,
                description="Test check",
                critical=True,
                status=CheckStatus.PASS
            )
            for i in range(30)
        ]

        decision = checker.get_go_no_go_decision()

        assert decision.decision == "GO"
        assert decision.critical_passed is True
        assert decision.pass_rate >= 0.90

    def test_go_no_go_decision_no_go_critical_failed(self):
        """Test Go/No-Go decision with critical failures."""
        checker = PreFlightCheck(config_path="dummy", env_path="dummy")

        # Create results with critical failures
        checker.results = [
            CheckResult(
                check_id="CRITICAL-001",
                category=CheckCategory.ENVIRONMENT,
                description="Critical check",
                critical=True,
                status=CheckStatus.FAIL
            ),
            CheckResult(
                check_id="NORMAL-001",
                category=CheckCategory.ENVIRONMENT,
                description="Normal check",
                critical=False,
                status=CheckStatus.PASS
            )
        ]

        decision = checker.get_go_no_go_decision()

        assert decision.decision == "NO-GO"
        assert decision.critical_passed is False
        assert len(decision.blockers) > 0

    def test_go_no_go_decision_no_go_pass_rate(self):
        """Test Go/No-Go decision with low pass rate."""
        checker = PreFlightCheck(config_path="dummy", env_path="dummy")

        # Create results with low pass rate
        checker.results = [
            CheckResult(
                check_id=f"TEST-{i:03d}",
                category=CheckCategory.ENVIRONMENT,
                description="Test check",
                critical=False,
                status=CheckStatus.FAIL
            )
            for i in range(10)
        ] + [
            CheckResult(
                check_id=f"PASS-{i:03d}",
                category=CheckCategory.ENVIRONMENT,
                description="Passing check",
                critical=False,
                status=CheckStatus.PASS
            )
            for i in range(5)
        ]

        decision = checker.get_go_no_go_decision()

        assert decision.decision == "NO-GO"
        assert decision.pass_rate < 0.90

    def test_generate_report(self, temp_config_file, temp_env_file):
        """Test report generation."""
        checker = PreFlightCheck(
            config_path=temp_config_file,
            env_path=temp_env_file
        )

        # Create some results
        checker.results = [
            CheckResult(
                check_id="ENV-001",
                category=CheckCategory.ENVIRONMENT,
                description="Gateway token",
                critical=True,
                status=CheckStatus.PASS,
                expected=">= 32 chars",
                actual="64 chars",
                output="PASS (64 chars)"
            )
        ]

        report = checker.generate_report()

        assert "OPENCLAW PRE-FLIGHT CHECKLIST REPORT" in report
        assert "DECISION:" in report
        assert "SUMMARY" in report
        assert "ENV-001" in report

    def test_save_and_load_results(self, temp_config_file, temp_env_file):
        """Test saving and loading results."""
        checker = PreFlightCheck(
            config_path=temp_config_file,
            env_path=temp_env_file
        )

        # Create some results
        checker.results = [
            CheckResult(
                check_id="TEST-001",
                category=CheckCategory.ENVIRONMENT,
                description="Test",
                critical=True,
                status=CheckStatus.PASS
            )
        ]

        # Save to temp file
        fd, path = tempfile.mkstemp(suffix=".json")
        try:
            os.close(fd)

            checker.save_results(path)

            # Load into new checker
            new_checker = PreFlightCheck()
            new_checker.load_results(path)

            assert len(new_checker.results) == 1
            assert new_checker.results[0].check_id == "TEST-001"
        finally:
            os.unlink(path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
