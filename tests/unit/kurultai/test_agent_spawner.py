"""
Unit Tests for Agent Spawner Module

Tests agent spawning via Signal messages and OpenClaw API.
"""

import pytest
import os
import sys
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../tools/kurultai'))

from agent_spawner import (
    AgentSpawner, AGENT_MAP,
    has_pending_tasks, has_pending_messages,
    spawn_via_signal, spawn_via_openclaw_api, spawn_agent
)


class TestAgentMap:
    """Tests for AGENT_MAP configuration."""

    def test_all_agents_defined(self):
        """Verify all 5 specialist agents are defined."""
        expected_agents = ['researcher', 'writer', 'developer', 'analyst', 'ops']
        
        for agent in expected_agents:
            assert agent in AGENT_MAP, f"Agent {agent} not in AGENT_MAP"
            assert 'name' in AGENT_MAP[agent]

    def test_agent_names(self):
        """Verify agent names are correct."""
        assert AGENT_MAP['researcher']['name'] == 'Möngke'
        assert AGENT_MAP['writer']['name'] == 'Chagatai'
        assert AGENT_MAP['developer']['name'] == 'Temüjin'
        assert AGENT_MAP['analyst']['name'] == 'Jochi'
        assert AGENT_MAP['ops']['name'] == 'Ögedei'


class TestPendingTasksCheck:
    """Tests for has_pending_tasks function."""

    @pytest.fixture
    def mock_driver(self):
        """Create a mock Neo4j driver."""
        driver = Mock()
        session = Mock()
        driver.session.return_value = session
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        return driver, session

    def test_has_pending_tasks_true(self, mock_driver):
        """Test when agent has pending tasks."""
        driver, session = mock_driver
        
        result = Mock()
        result.single.return_value = {'count': 5}
        session.run.return_value = result
        
        has_tasks = has_pending_tasks(driver, 'Jochi')
        
        assert has_tasks is True
        session.run.assert_called_once()

    def test_has_pending_tasks_false(self, mock_driver):
        """Test when agent has no pending tasks."""
        driver, session = mock_driver
        
        result = Mock()
        result.single.return_value = {'count': 0}
        session.run.return_value = result
        
        has_tasks = has_pending_tasks(driver, 'Jochi')
        
        assert has_tasks is False

    def test_has_pending_tasks_query(self, mock_driver):
        """Test that correct Cypher query is used."""
        driver, session = mock_driver
        
        result = Mock()
        result.single.return_value = {'count': 0}
        session.run.return_value = result
        
        has_pending_tasks(driver, 'Jochi')
        
        call_args = session.run.call_args
        assert 'pending' in call_args[0][0].lower()
        assert call_args[1]['agent'] == 'Jochi'


class TestPendingMessagesCheck:
    """Tests for has_pending_messages function."""

    @pytest.fixture
    def mock_driver(self):
        """Create a mock Neo4j driver."""
        driver = Mock()
        session = Mock()
        driver.session.return_value = session
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        return driver, session

    def test_has_pending_messages_true(self, mock_driver):
        """Test when agent has pending messages."""
        driver, session = mock_driver
        
        result = Mock()
        result.single.return_value = {'count': 3}
        session.run.return_value = result
        
        has_msgs = has_pending_messages(driver, 'Jochi')
        
        assert has_msgs is True

    def test_has_pending_messages_false(self, mock_driver):
        """Test when agent has no pending messages."""
        driver, session = mock_driver
        
        result = Mock()
        result.single.return_value = {'count': 0}
        session.run.return_value = result
        
        has_msgs = has_pending_messages(driver, 'Jochi')
        
        assert has_msgs is False


class TestSpawnViaSignal:
    """Tests for spawn_via_signal function."""

    def test_spawn_signal_no_account(self):
        """Test when SIGNAL_ACCOUNT not set."""
        with patch.dict(os.environ, {}, clear=True):
            result = spawn_via_signal('jochi')
        
        assert result is False

    @patch('subprocess.run')
    def test_spawn_signal_success(self, mock_run):
        """Test successful Signal message send."""
        mock_run.return_value = Mock(returncode=0)
        
        with patch.dict(os.environ, {'SIGNAL_ACCOUNT': '+1234567890'}):
            result = spawn_via_signal('jochi', 'Test message')
        
        assert result is True
        mock_run.assert_called_once()

    @patch('subprocess.run')
    def test_spawn_signal_failure(self, mock_run):
        """Test failed Signal message send."""
        mock_run.side_effect = Exception("signal-cli not found")
        
        with patch.dict(os.environ, {'SIGNAL_ACCOUNT': '+1234567890'}):
            result = spawn_via_signal('jochi')
        
        assert result is False

    @patch('subprocess.run')
    def test_spawn_signal_command_format(self, mock_run):
        """Test that correct signal-cli command is constructed."""
        mock_run.return_value = Mock(returncode=0)
        
        with patch.dict(os.environ, {'SIGNAL_ACCOUNT': '+1234567890'}):
            spawn_via_signal('jochi', 'Check tasks')
        
        args = mock_run.call_args[0][0]
        assert 'signal-cli' in args
        assert '-a' in args
        assert '+1234567890' in args
        assert 'send' in args
        assert '@jochi' in str(args)


class TestSpawnViaOpenClawAPI:
    """Tests for spawn_via_openclaw_api function."""

    @patch('urllib.request.urlopen')
    @patch('urllib.request.Request')
    def test_spawn_api_success(self, mock_request, mock_urlopen):
        """Test successful API spawn."""
        mock_response = Mock()
        mock_response.status = 200
        mock_urlopen.return_value.__enter__ = Mock(return_value=mock_response)
        mock_urlopen.return_value.__exit__ = Mock(return_value=False)
        
        with patch.dict(os.environ, {
            'OPENCLAW_GATEWAY_URL': 'http://test:8080',
            'OPENCLAW_GATEWAY_TOKEN': 'test_token'
        }):
            result = spawn_via_openclaw_api('jochi')
        
        assert result is True

    @patch('urllib.request.urlopen')
    def test_spawn_api_no_token(self, mock_urlopen):
        """Test when OPENCLAW_GATEWAY_TOKEN not set."""
        with patch.dict(os.environ, {}, clear=True):
            result = spawn_via_openclaw_api('jochi')
        
        assert result is False
        mock_urlopen.assert_not_called()

    @patch('urllib.request.urlopen')
    def test_spawn_api_404_response(self, mock_urlopen):
        """Test API returning 404."""
        mock_response = Mock()
        mock_response.status = 404
        mock_urlopen.return_value.__enter__ = Mock(return_value=mock_response)
        mock_urlopen.return_value.__exit__ = Mock(return_value=False)
        
        with patch.dict(os.environ, {
            'OPENCLAW_GATEWAY_URL': 'http://test:8080',
            'OPENCLAW_GATEWAY_TOKEN': 'test_token'
        }):
            result = spawn_via_openclaw_api('jochi')
        
        # Should try multiple endpoints before giving up
        assert result is False

    @patch('urllib.request.urlopen')
    def test_spawn_api_timeout(self, mock_urlopen):
        """Test API timeout."""
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("Connection timed out")
        
        with patch.dict(os.environ, {
            'OPENCLAW_GATEWAY_URL': 'http://test:8080',
            'OPENCLAW_GATEWAY_TOKEN': 'test_token'
        }):
            result = spawn_via_openclaw_api('jochi')
        
        assert result is False


class TestSpawnAgent:
    """Tests for main spawn_agent function."""

    def test_spawn_unknown_agent(self):
        """Test spawning unknown agent."""
        result = spawn_agent('unknown_agent')
        
        assert result is False

    @patch('agent_spawner.spawn_via_openclaw_api')
    def test_spawn_success(self, mock_api):
        """Test successful spawn."""
        mock_api.return_value = True
        
        result = spawn_agent('jochi')
        
        assert result is True

    @patch('agent_spawner.spawn_via_openclaw_api')
    @patch('agent_spawner.spawn_via_signal')
    def test_spawn_fallback_to_signal(self, mock_signal, mock_api):
        """Test fallback to Signal when API fails."""
        mock_api.return_value = False
        mock_signal.return_value = True
        
        result = spawn_agent('jochi')
        
        assert result is True
        mock_api.assert_called_once()
        mock_signal.assert_called_once()

    @patch('agent_spawner.spawn_via_openclaw_api')
    @patch('agent_spawner.spawn_via_signal')
    def test_spawn_all_methods_fail(self, mock_signal, mock_api):
        """Test when all spawn methods fail."""
        mock_api.return_value = False
        mock_signal.return_value = False
        
        result = spawn_agent('jochi')
        
        assert result is False

    @patch('agent_spawner.has_pending_tasks')
    @patch('agent_spawner.has_pending_messages')
    @patch('agent_spawner.spawn_via_openclaw_api')
    def test_spawn_with_check_tasks_no_work(self, mock_api, mock_msgs, mock_tasks):
        """Test spawn with check_tasks when no work pending."""
        mock_tasks.return_value = False
        mock_msgs.return_value = False
        
        result = spawn_agent('jochi', check_tasks=True)
        
        assert result is True  # Returns True when no spawn needed
        mock_api.assert_not_called()

    @patch('agent_spawner.has_pending_tasks')
    @patch('agent_spawner.has_pending_messages')
    @patch('agent_spawner.spawn_via_openclaw_api')
    def test_spawn_with_check_tasks_has_work(self, mock_api, mock_msgs, mock_tasks):
        """Test spawn with check_tasks when work is pending."""
        mock_tasks.return_value = True
        mock_msgs.return_value = False
        mock_api.return_value = True
        
        result = spawn_agent('jochi', check_tasks=True)
        
        assert result is True
        mock_api.assert_called_once()


class TestAgentSpawnerClass:
    """Tests for AgentSpawner class."""

    @pytest.fixture
    def spawner(self):
        """Create an AgentSpawner instance."""
        return AgentSpawner()

    def test_spawner_initialization(self, spawner):
        """Test that spawner initializes correctly."""
        assert spawner is not None

    def test_spawner_spawn_method(self, spawner):
        """Test spawner's spawn method."""
        # This would test the class-based spawner if it exists
        pass


class TestIntegration:
    """Integration-style tests for spawner."""

    @patch('agent_spawner.get_neo4j_driver')
    @patch('agent_spawner.spawn_via_openclaw_api')
    def test_end_to_end_spawn_workflow(self, mock_api, mock_get_driver):
        """Test complete spawn workflow."""
        # Setup mocks
        driver = Mock()
        session = Mock()
        driver.session.return_value = session
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        
        result = Mock()
        result.single.return_value = {'count': 1}
        session.run.return_value = result
        
        mock_get_driver.return_value = driver
        mock_api.return_value = True
        
        # Execute
        result = spawn_agent('jochi', check_tasks=True)
        
        # Verify
        assert result is True
        mock_get_driver.assert_called_once()
        mock_api.assert_called_once()
