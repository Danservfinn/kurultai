"""
Tests for NotionIntegration class.

This module contains comprehensive tests for the Notion integration system
including polling, task creation, status sync, checkpoints, error classification,
failure tracking, and reliability metrics.
"""

import json
import os
import pytest
import threading
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, MagicMock, patch, call

# Import the module under test
import sys
sys.path.insert(0, '/Users/kurultai/molt')

from tools.notion_integration import (
    NotionIntegration,
    NotionClient,
    NotionTask,
    Checkpoint,
    AgentFailure,
    ErrorClassification,
    TrainingRecommendation,
    NotionIntegrationError,
    NotionAPIError,
    NotionAuthError,
    NotionRateLimitError,
    NotionConfigError,
    STATUS_MAPPING,
    NEO4J_TO_NOTION_STATUS,
    PRIORITY_MAPPING,
    NOTION_TO_NEO4J_PRIORITY,
    ERROR_CLASSIFICATION,
    ERROR_KEYWORDS,
    DEFAULT_POLL_INTERVAL,
    CHECKPOINT_EXPIRY_HOURS,
    KUBLAI_AGENT_ID,
    OGEDEI_AGENT_ID,
    create_notion_integration,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_memory():
    """Create a mock OperationalMemory."""
    memory = Mock()
    memory._generate_id.return_value = "test-task-id"
    memory._now.return_value = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Mock session context manager
    mock_session = Mock()
    mock_context = MagicMock()
    mock_context.__enter__ = Mock(return_value=mock_session)
    mock_context.__exit__ = Mock(return_value=False)
    memory._session.return_value = mock_context

    return memory, mock_session


@pytest.fixture
def sample_notion_page_data():
    """Sample Notion API page data."""
    return {
        "id": "page-123",
        "created_time": "2025-01-01T12:00:00.000Z",
        "properties": {
            "Name": {
                "title": [
                    {
                        "text": {
                            "content": "Test Task"
                        }
                    }
                ]
            },
            "Status": {
                "select": {
                    "name": "To Do"
                }
            },
            "Priority": {
                "select": {
                    "name": "P1"
                }
            },
            "Agent": {
                "select": {
                    "name": "developer"
                }
            },
            "Neo4j Task ID": {
                "rich_text": []
            },
            "Requester": {
                "rich_text": [
                    {
                        "text": {
                            "content": "user@example.com"
                        }
                    }
                ]
            },
            "Created From": {
                "select": {
                    "name": "Notion"
                }
            }
        }
    }


@pytest.fixture
def notion_client():
    """Create a NotionClient with test credentials."""
    with patch.dict(os.environ, {
        "NOTION_TOKEN": "test_token",
        "NOTION_TASK_DATABASE_ID": "test_db_id"
    }):
        return NotionClient()


# =============================================================================
# NotionClient Tests
# =============================================================================

class TestNotionClient:
    """Test cases for NotionClient class."""

    def test_initialization_with_params(self):
        """Test initialization with explicit parameters."""
        client = NotionClient(api_key="key123", database_id="db456")

        assert client.api_key == "key123"
        assert client.database_id == "db456"
        assert "Authorization" in client._headers
        assert client._headers["Authorization"] == "Bearer key123"

    def test_initialization_from_env(self):
        """Test initialization from environment variables."""
        with patch.dict(os.environ, {
            "NOTION_TOKEN": "env_token",
            "NOTION_TASK_DATABASE_ID": "env_db"
        }):
            client = NotionClient()

            assert client.api_key == "env_token"
            assert client.database_id == "env_db"

    def test_initialization_no_api_key_raises_error(self):
        """Test that missing API key raises NotionConfigError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(NotionConfigError, match="API key"):
                NotionClient(database_id="db123")

    def test_initialization_no_database_id_raises_error(self):
        """Test that missing database ID raises NotionConfigError."""
        with patch.dict(os.environ, {"NOTION_TOKEN": "token"}, clear=True):
            with pytest.raises(NotionConfigError, match="database ID"):
                NotionClient()

    def test_make_request_success(self, notion_client):
        """Test successful API request."""
        mock_response = {
            "results": [
                {"id": "page-1", "properties": {"Name": {"title": [{"text": {"content": "Task"}}]}}}
            ]
        }

        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_response_obj = Mock()
            mock_response_obj.read.return_value = json.dumps(mock_response).encode("utf-8")
            mock_urlopen.return_value.__enter__.return_value = mock_response_obj

            result = notion_client._make_request("POST", "/databases/test_db/query", {})

            assert result == mock_response

    def test_make_request_401_raises_auth_error(self, notion_client):
        """Test that 401 raises NotionAuthError."""
        from urllib.error import HTTPError

        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_urlopen.side_effect = HTTPError(
                "url", 401, "Unauthorized", {}, None
            )

            with pytest.raises(NotionAuthError):
                notion_client._make_request("GET", "/pages/test")

    def test_make_request_429_raises_rate_limit_error(self, notion_client):
        """Test that 429 raises NotionRateLimitError."""
        from urllib.error import HTTPError

        mock_headers = {"Retry-After": "60"}

        with patch('urllib.request.urlopen') as mock_urlopen:
            error = HTTPError("url", 429, "Too Many Requests", mock_headers, None)
            error.read = Mock(return_value=b"")
            mock_urlopen.side_effect = error

            with pytest.raises(NotionRateLimitError, match="60"):
                notion_client._make_request("GET", "/pages/test")

    def test_make_request_500_raises_api_error(self, notion_client):
        """Test that 500 raises NotionAPIError."""
        from urllib.error import HTTPError

        with patch('urllib.request.urlopen') as mock_urlopen:
            error = HTTPError("url", 500, "Internal Server Error", {}, None)
            error.read = Mock(return_value=b"")
            mock_urlopen.side_effect = error

            with pytest.raises(NotionAPIError, match="server error"):
                notion_client._make_request("GET", "/pages/test")

    def test_query_database(self, notion_client):
        """Test database query."""
        mock_response = {"results": []}

        with patch.object(notion_client, '_make_request', return_value=mock_response):
            result = notion_client.query_database(filter={"test": "value"})

            assert result == mock_response

    def test_get_page(self, notion_client):
        """Test getting a page."""
        mock_response = {"id": "page-123", "properties": {}}

        with patch.object(notion_client, '_make_request', return_value=mock_response):
            result = notion_client.get_page("page-123")

            assert result == mock_response

    def test_update_page(self, notion_client):
        """Test updating a page."""
        mock_response = {"id": "page-123", "properties": {"Status": "Done"}}
        properties = {"Status": {"select": {"name": "Done"}}}

        with patch.object(notion_client, '_make_request', return_value=mock_response):
            result = notion_client.update_page("page-123", properties)

            assert result == mock_response

    def test_create_page(self, notion_client):
        """Test creating a page."""
        mock_response = {"id": "new-page", "properties": {}}
        properties = {"Name": {"title": [{"text": {"content": "New Task"}}]}}

        with patch.object(notion_client, '_make_request', return_value=mock_response):
            result = notion_client.create_page("db-123", properties)

            assert result == mock_response

    def test_append_blocks(self, notion_client):
        """Test appending blocks to a page."""
        mock_response = {"results": []}
        blocks = [{"object": "block", "type": "paragraph"}]

        with patch.object(notion_client, '_make_request', return_value=mock_response):
            result = notion_client.append_blocks("page-123", blocks)

            assert result == mock_response


# =============================================================================
# NotionIntegration Tests
# =============================================================================

class TestNotionIntegration:
    """Test cases for NotionIntegration class."""

    @pytest.fixture
    def integration(self, mock_memory):
        """Create NotionIntegration with mocked dependencies."""
        memory, _ = mock_memory
        with patch.dict(os.environ, {
            "NOTION_TOKEN": "test_token",
            "NOTION_TASK_DATABASE_ID": "test_db"
        }):
            return NotionIntegration(memory)

    def test_initialization(self, mock_memory):
        """Test NotionIntegration initialization."""
        memory, _ = mock_memory
        with patch.dict(os.environ, {
            "NOTION_TOKEN": "test_token",
            "NOTION_TASK_DATABASE_ID": "test_db",
            "NOTION_POLL_INTERVAL_SECONDS": "120"
        }):
            integration = NotionIntegration(memory)

            assert integration.memory == memory
            assert integration.poll_interval == 120
            assert integration._polling is False
            assert integration._poll_thread is None

    def test_initialization_default_poll_interval(self, mock_memory):
        """Test default poll interval is used when not specified."""
        memory, _ = mock_memory
        with patch.dict(os.environ, {
            "NOTION_TOKEN": "test_token",
            "NOTION_TASK_DATABASE_ID": "test_db"
        }, clear=True):
            integration = NotionIntegration(memory)

            assert integration.poll_interval == DEFAULT_POLL_INTERVAL

    # -------------------------------------------------------------------------
    # Task Polling Tests
    # -------------------------------------------------------------------------

    def test_poll_new_tasks_empty(self, integration):
        """Test polling when no new tasks exist."""
        with patch.object(integration.client, 'query_database', return_value={"results": []}):
            tasks = integration.poll_new_tasks()

            assert tasks == []

    def test_poll_new_tasks_found(self, integration, sample_notion_page_data):
        """Test polling finds new tasks."""
        mock_response = {"results": [sample_notion_page_data]}

        with patch.object(integration.client, 'query_database', return_value=mock_response):
            tasks = integration.poll_new_tasks()

            assert len(tasks) == 1
            assert tasks[0].title == "Test Task"
            assert tasks[0].status == "To Do"
            assert tasks[0].priority == "P1"

    def test_poll_new_tasks_rate_limit(self, integration):
        """Test polling handles rate limiting gracefully."""
        with patch.object(integration.client, 'query_database',
                         side_effect=NotionRateLimitError("Rate limited")):
            tasks = integration.poll_new_tasks()

            assert tasks == []

    def test_poll_new_tasks_api_error(self, integration):
        """Test polling handles API errors gracefully."""
        with patch.object(integration.client, 'query_database',
                         side_effect=NotionAPIError("API error")):
            tasks = integration.poll_new_tasks()

            assert tasks == []

    def test_poll_status_changes(self, integration, mock_memory):
        """Test polling for status changes."""
        memory, mock_session = mock_memory

        # Create task with different statuses
        page_data = {
            "id": "page-123",
            "properties": {
                "Name": {"title": [{"text": {"content": "Task"}}]},
                "Status": {"select": {"name": "In Progress"}},
                "Neo4j Task ID": {"rich_text": [{"text": {"content": "task-123"}}]},
                "Priority": {"select": {"name": "P2"}},
                "Agent": {"select": {}},
                "Requester": {"rich_text": []},
                "Created From": {"select": {}}
            }
        }

        # Mock Neo4j task with different status - create a proper node dict
        task_node = {
            "id": "task-123",
            "status": "pending",  # Should be "To Do" in Notion
            "description": "Test"
        }
        mock_result = Mock()
        mock_result.single.return_value = task_node
        mock_session.run.return_value = mock_result

        with patch.object(integration.client, 'query_database', return_value={"results": [page_data]}):
            with patch.object(integration.memory, 'get_task', return_value=task_node):
                changes = integration.poll_status_changes()

                assert len(changes) == 1
                task, old_status, new_status = changes[0]
                assert old_status == "To Do"
                assert new_status == "In Progress"

    # -------------------------------------------------------------------------
    # Task Creation Tests
    # -------------------------------------------------------------------------

    def test_create_neo4j_task_from_notion(self, integration, mock_memory, sample_notion_page_data):
        """Test creating Neo4j task from Notion task."""
        memory, mock_session = mock_memory

        # Parse the notion task
        notion_task = integration._parse_notion_page(sample_notion_page_data)
        assert notion_task is not None

        # Mock task creation
        memory.create_task.return_value = "neo4j-task-id"

        # Mock Notion update
        with patch.object(integration.client, 'update_page', return_value={}):
            task_id = integration.create_neo4j_task_from_notion(notion_task)

            assert task_id == "neo4j-task-id"
            memory.create_task.assert_called_once()

            # Verify task creation parameters
            call_kwargs = memory.create_task.call_args[1]
            assert call_kwargs["task_type"] == "notion_task"
            assert call_kwargs["description"] == "Test Task"
            assert call_kwargs["assigned_to"] == "developer"  # From Agent field
            assert call_kwargs["priority"] == "high"  # P1 maps to high

    def test_create_neo4j_task_without_agent(self, integration, sample_notion_page_data):
        """Test creating task without specific agent assigns to 'any'."""
        sample_notion_page_data["properties"]["Agent"]["select"] = {}

        notion_task = integration._parse_notion_page(sample_notion_page_data)
        assert notion_task is not None
        assert notion_task.agent is None

        integration.memory.create_task.return_value = "task-id"

        with patch.object(integration.client, 'update_page', return_value={}):
            integration.create_neo4j_task_from_notion(notion_task)

            call_kwargs = integration.memory.create_task.call_args[1]
            assert call_kwargs["assigned_to"] == "any"

    def test_create_notion_task_link(self, integration, mock_memory):
        """Test creating NotionTask link in Neo4j."""
        memory, mock_session = mock_memory

        notion_task = NotionTask(
            id="page-123",
            title="Test",
            status="To Do",
            priority="P1"
        )

        integration._create_notion_task_link("task-456", notion_task)

        # Verify Cypher query was executed
        mock_session.run.assert_called()

        call_args = mock_session.run.call_args
        query = call_args[0][0]
        assert "MERGE (nt:NotionTask" in query
        assert "MERGE (t:Task" in query

    # -------------------------------------------------------------------------
    # Status Sync Tests
    # -------------------------------------------------------------------------

    def test_update_notion_task_status(self, integration):
        """Test updating Notion task status."""
        with patch.object(integration.client, 'update_page', return_value={}):
            result = integration.update_notion_task_status("page-123", "In Progress")

            assert result is True

            integration.client.update_page.assert_called_once()
            call_args = integration.client.update_page.call_args
            assert call_args[0][0] == "page-123"
            assert "Status" in call_args[0][1]

    def test_update_notion_task_status_api_error(self, integration):
        """Test handling API error when updating status."""
        with patch.object(integration.client, 'update_page',
                         side_effect=NotionAPIError("API error")):
            result = integration.update_notion_task_status("page-123", "In Progress")

            assert result is False

    def test_sync_neo4j_status_to_notion(self, integration, mock_memory):
        """Test syncing Neo4j status to Notion."""
        memory, mock_session = mock_memory

        # Mock get_task
        memory.get_task.return_value = {
            "id": "task-123",
            "status": "in_progress",
            "description": "Test task"
        }

        # Mock get_notion_page_id
        with patch.object(integration, '_get_notion_page_id', return_value="page-123"):
            with patch.object(integration, 'update_notion_task_status', return_value=True):
                result = integration.sync_neo4j_status_to_notion("task-123")

                assert result is True
                integration.update_notion_task_status.assert_called_once_with(
                    "page-123", "In Progress"
                )

    def test_sync_neo4j_status_task_not_found(self, integration):
        """Test syncing when task not found."""
        integration.memory.get_task.return_value = None

        result = integration.sync_neo4j_status_to_notion("task-123")

        assert result is False

    def test_get_notion_page_id(self, integration, mock_memory):
        """Test getting Notion page ID for a task."""
        memory, mock_session = mock_memory

        mock_result = Mock()
        mock_result.single.return_value = {"page_id": "page-123"}
        mock_session.run.return_value = mock_result

        page_id = integration._get_notion_page_id("task-456")

        assert page_id == "page-123"

    def test_handle_column_change_interrupt(self, integration):
        """Test handling interruption when moving from In Progress to Backlog."""
        notion_task = NotionTask(
            id="page-123",
            title="Test Task",
            status="Backlog",
            priority="P1",
            neo4j_task_id="task-123"
        )

        with patch.object(integration, 'create_checkpoint', return_value=None):
            with patch.object(integration, '_update_neo4j_task_status', return_value=True):
                result = integration.handle_column_change(notion_task, "In Progress", "Backlog")

                assert result["action"] == "interrupted"
                assert "checkpoint" in result

    def test_handle_column_change_resume(self, integration):
        """Test handling resume when moving from To Do to In Progress."""
        notion_task = NotionTask(
            id="page-123",
            title="Test Task",
            status="In Progress",
            priority="P1",
            neo4j_task_id="task-123"
        )

        mock_checkpoint = Checkpoint(
            id="cp-1",
            task_id="task-123",
            agent="developer",
            created_at=datetime.now(timezone.utc),
            context_json='{}',
            progress_percent=50.0,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
        )

        with patch.object(integration, 'get_latest_checkpoint', return_value=mock_checkpoint):
            with patch.object(integration, '_update_neo4j_task_status', return_value=True):
                result = integration.handle_column_change(notion_task, "To Do", "In Progress")

                assert result["action"] == "resumed"

    def test_handle_column_change_completed(self, integration):
        """Test handling completion when moving to Done."""
        notion_task = NotionTask(
            id="page-123",
            title="Test Task",
            status="Done",
            priority="P1",
            neo4j_task_id="task-123"
        )

        with patch.object(integration, '_update_neo4j_task_status', return_value=True):
            result = integration.handle_column_change(notion_task, "In Progress", "Done")

            assert result["action"] == "completed"

    # -------------------------------------------------------------------------
    # Checkpoint Tests
    # -------------------------------------------------------------------------

    def test_create_checkpoint(self, integration, mock_memory):
        """Test creating a checkpoint."""
        memory, mock_session = mock_memory

        mock_result = Mock()
        mock_checkpoint = Mock()
        mock_checkpoint.id = "cp-123"
        mock_result.single.return_value = mock_checkpoint
        mock_session.run.return_value = mock_result

        checkpoint = integration.create_checkpoint(
            agent="developer",
            task_id="task-123",
            context={"file": "test.py", "line": 42},
            progress_percent=25.0
        )

        assert checkpoint is not None
        assert checkpoint.agent == "developer"
        assert checkpoint.task_id == "task-123"

    def test_create_checkpoint_fallback_mode(self, integration):
        """Test creating checkpoint in fallback mode."""
        mock_session = Mock()
        mock_context = MagicMock()
        mock_context.__enter__ = Mock(return_value=None)
        mock_context.__exit__ = Mock(return_value=False)
        integration.memory._session.return_value = mock_context

        checkpoint = integration.create_checkpoint(
            agent="developer",
            task_id="task-123"
        )

        assert checkpoint is None

    def test_get_checkpoint(self, integration, mock_memory):
        """Test getting a checkpoint by ID."""
        memory, mock_session = mock_memory

        mock_node = {
            "id": "cp-123",
            "task_id": "task-123",
            "agent": "developer",
            "created_at": datetime.now(timezone.utc),
            "context_json": '{"file": "test.py"}',
            "progress_percent": 50.0,
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=1)
        }
        # Create a mock result that returns a dict-like object for record["c"]
        mock_record = Mock()
        mock_record.__getitem__ = Mock(side_effect=lambda key: mock_node)
        mock_result = Mock()
        mock_result.single.return_value = mock_record
        mock_session.run.return_value = mock_result

        checkpoint = integration.get_checkpoint("cp-123")

        assert checkpoint is not None
        assert checkpoint.id == "cp-123"
        assert checkpoint.progress_percent == 50.0

    def test_get_latest_checkpoint(self, integration, mock_memory):
        """Test getting latest checkpoint for a task."""
        memory, mock_session = mock_memory

        mock_node = {
            "id": "cp-latest",
            "task_id": "task-123",
            "agent": "developer",
            "created_at": datetime.now(timezone.utc),
            "context_json": '{}',
            "progress_percent": 75.0,
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
            "notes": "Latest checkpoint"
        }
        # Create a mock result that returns a dict-like object for record["c"]
        mock_record = Mock()
        mock_record.__getitem__ = Mock(side_effect=lambda key: mock_node)
        mock_result = Mock()
        mock_result.single.return_value = mock_record
        mock_session.run.return_value = mock_result

        checkpoint = integration.get_latest_checkpoint("task-123")

        assert checkpoint is not None
        assert checkpoint.id == "cp-latest"
        assert checkpoint.progress_percent == 75.0

    def test_load_checkpoint(self, integration):
        """Test loading checkpoint context."""
        mock_checkpoint = Checkpoint(
            id="cp-123",
            task_id="task-123",
            agent="developer",
            created_at=datetime.now(timezone.utc),
            context_json='{"file": "test.py", "line": 42}',
            progress_percent=50.0,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
        )

        with patch.object(integration, 'get_checkpoint', return_value=mock_checkpoint):
            context = integration.load_checkpoint("cp-123")

            assert context == {"file": "test.py", "line": 42}

    def test_load_checkpoint_invalid_json(self, integration):
        """Test loading checkpoint with invalid JSON."""
        mock_checkpoint = Checkpoint(
            id="cp-123",
            task_id="task-123",
            agent="developer",
            created_at=datetime.now(timezone.utc),
            context_json='{invalid json}',
            progress_percent=50.0,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
        )

        with patch.object(integration, 'get_checkpoint', return_value=mock_checkpoint):
            context = integration.load_checkpoint("cp-123")

            assert context is None

    def test_cleanup_expired_checkpoints(self, integration, mock_memory):
        """Test cleaning up expired checkpoints."""
        memory, mock_session = mock_memory

        mock_result = Mock()
        mock_result.single.return_value = {"deleted_count": 5}
        mock_session.run.return_value = mock_result

        count = integration.cleanup_expired_checkpoints()

        assert count == 5

    # -------------------------------------------------------------------------
    # Error Classification Tests
    # -------------------------------------------------------------------------

    def test_classify_error_syntax_error(self, integration):
        """Test classifying syntax error."""
        result = integration.classify_error("SyntaxError: invalid syntax")

        assert result.error_type == "syntax_error"
        assert result.recommended_agent == "developer"
        assert result.confidence >= 0.9

    def test_classify_error_api_error(self, integration):
        """Test classifying API error."""
        result = integration.classify_error("API request failed: endpoint not found")

        assert result.error_type == "api_error"
        assert result.recommended_agent == "developer"

    def test_classify_error_performance_issue(self, integration):
        """Test classifying performance issue."""
        result = integration.classify_error("Function too slow, needs optimization")

        assert result.error_type == "performance_issue"
        assert result.recommended_agent == "analyst"

    def test_classify_error_race_condition(self, integration):
        """Test classifying race condition."""
        result = integration.classify_error("Race condition detected in concurrent access")

        assert result.error_type == "race_condition"
        assert result.recommended_agent == "analyst"

    def test_classify_error_tone_issue(self, integration):
        """Test classifying tone issue."""
        result = integration.classify_error("The tone is inappropriate for the audience")

        assert result.error_type == "tone_issue"
        assert result.recommended_agent == "writer"

    def test_classify_error_unknown(self, integration):
        """Test classifying unknown error defaults to developer."""
        result = integration.classify_error("Something went wrong")

        assert result.recommended_agent == "developer"
        assert result.confidence == 0.5

    def test_route_error_task(self, integration):
        """Test routing failed task to appropriate agent."""
        integration.memory.get_task.return_value = {
            "id": "task-123",
            "type": "code_implement",
            "priority": "high"
        }
        integration.memory.create_task.return_value = "new-task-456"

        with patch.object(integration, 'track_agent_failure'):
            new_task_id = integration.route_error_task(
                "task-123",
                "SyntaxError: invalid syntax",
                "developer"
            )

            assert new_task_id == "new-task-456"
            integration.memory.create_task.assert_called_once()

    # -------------------------------------------------------------------------
    # Agent Failure Tracking Tests
    # -------------------------------------------------------------------------

    def test_track_agent_failure(self, integration, mock_memory):
        """Test tracking agent failure."""
        memory, mock_session = mock_memory

        mock_result = Mock()
        mock_result.single.return_value = {"id": "failure-123"}
        mock_session.run.return_value = mock_result

        result = integration.track_agent_failure(
            agent="developer",
            task_type="code_review",
            error_type="syntax_error",
            fix_successful=True,
            fix_agent="developer"
        )

        assert result is True

    def test_get_agent_reliability(self, integration, mock_memory):
        """Test getting agent reliability metrics."""
        memory, mock_session = mock_memory

        mock_node = {
            "agent": "developer",
            "task_type": "code_review",
            "success_rate": 0.85,
            "total_attempts": 20,
            "recent_failures": 3
        }
        mock_result = Mock()
        mock_result.__iter__ = Mock(return_value=iter([{"r": mock_node}]))
        mock_session.run.return_value = mock_result

        metrics = integration.get_agent_reliability("developer")

        assert len(metrics) == 1
        assert metrics[0]["success_rate"] == 0.85
        assert metrics[0]["recent_failures"] == 3

    def test_detect_training_needs(self, integration, mock_memory):
        """Test detecting when agent needs training."""
        memory, mock_session = mock_memory

        # Mock reliability query result - agent has low success rate
        mock_reliability_result = Mock()
        mock_reliability_result.single.return_value = {
            "error_type": "syntax_error",
            "failures": 5,
            "fix_rate": 0.4
        }

        # Mock failures query result - return iterable with proper structure
        mock_failure_node = {
            "id": "f-1",
            "agent": "developer",
            "task_type": "code_review",
            "error_type": "syntax_error",
            "fix_successful": False,
            "fix_agent": "developer",
            "created_at": datetime.now(timezone.utc),
            "error_message": "SyntaxError"
        }
        mock_failures_result = Mock()
        mock_failures_result.__iter__ = Mock(return_value=iter([{"f": mock_failure_node}]))

        mock_session.run.side_effect = [mock_reliability_result, mock_failures_result]

        recommendation = integration.detect_training_needs("developer")

        assert recommendation is not None
        assert recommendation.agent == "developer"
        assert recommendation.error_type == "syntax_error"
        assert recommendation.priority == "high"

    def test_detect_training_needs_none(self, integration, mock_memory):
        """Test detecting training needs when agent is performing well."""
        memory, mock_session = mock_memory

        # No low success rate found
        mock_result = Mock()
        mock_result.single.return_value = None
        mock_session.run.return_value = mock_result

        recommendation = integration.detect_training_needs("developer")

        assert recommendation is None

    # -------------------------------------------------------------------------
    # Background Polling Tests
    # -------------------------------------------------------------------------

    def test_start_polling(self, integration):
        """Test starting background polling."""
        with patch.object(integration, 'poll_new_tasks', return_value=[]):
            with patch.object(integration, 'poll_status_changes', return_value=[]):
                integration.start_polling()

                assert integration.is_polling() is True
                assert integration._poll_thread is not None

                integration.stop_polling()

    def test_stop_polling(self, integration):
        """Test stopping background polling."""
        integration.start_polling()
        assert integration.is_polling() is True

        integration.stop_polling()

        assert integration.is_polling() is False
        assert integration._stop_polling.is_set()

    def test_start_polling_already_running(self, integration):
        """Test starting polling when already running."""
        with patch.object(integration, 'poll_new_tasks', return_value=[]):
            with patch.object(integration, 'poll_status_changes', return_value=[]):
                integration.start_polling()
                first_thread = integration._poll_thread

                integration.start_polling()

                # Should reuse the same thread
                assert integration._poll_thread == first_thread

                integration.stop_polling()

    def test_poll_loop_processes_new_tasks(self, integration):
        """Test that poll loop processes new tasks."""
        new_task = NotionTask(
            id="page-new",
            title="New Task",
            status="To Do",
            priority="P2"
        )

        # Set polling to active for the test
        integration._polling = True

        poll_call_count = [0]

        # Mock poll_new_tasks to track calls and stop after first
        def mock_poll(*args, **kwargs):
            poll_call_count[0] += 1
            if poll_call_count[0] == 1:
                return [new_task]
            integration._stop_polling.set()
            return []

        with patch.object(integration, 'poll_new_tasks', side_effect=mock_poll):
            with patch.object(integration, 'poll_status_changes', return_value=[]):
                with patch.object(integration, 'create_neo4j_task_from_notion', return_value="task-id") as mock_create:
                    # Set a very short interval for quick test
                    integration.poll_interval = 0.001

                    # Run poll loop - it will process tasks and then exit
                    integration._poll_loop()

                    # Verify create_neo4j_task_from_notion was called for the new task
                    assert mock_create.call_count >= 1

                    # Reset state
                    integration._polling = False

    def test_poll_loop_handles_exceptions(self, integration):
        """Test that poll loop handles exceptions gracefully."""
        with patch.object(integration, 'poll_new_tasks',
                         side_effect=NotionAPIError("API error")):
            # Run one iteration - should not raise
            integration._stop_polling.set()
            integration._poll_loop()

            # Should complete without crashing
            assert True

    def test_get_polling_status(self, integration):
        """Test getting polling status."""
        status = integration.get_polling_status()

        assert status["active"] is False
        assert status["interval"] == DEFAULT_POLL_INTERVAL

        integration.start_polling()
        status = integration.get_polling_status()
        integration.stop_polling()

        # Last poll might still be None if no poll completed yet
        assert "last_poll" in status

    # -------------------------------------------------------------------------
    # Utility Method Tests
    # -------------------------------------------------------------------------

    def test_parse_notion_page(self, integration, sample_notion_page_data):
        """Test parsing Notion page data."""
        task = integration._parse_notion_page(sample_notion_page_data)

        assert task is not None
        assert task.id == "page-123"
        assert task.title == "Test Task"
        assert task.status == "To Do"
        assert task.priority == "P1"
        assert task.agent == "developer"
        assert task.requester == "user@example.com"
        assert task.created_from == "Notion"
        assert task.neo4j_task_id is None

    def test_parse_notion_page_with_neo4j_id(self, integration):
        """Test parsing Notion page with existing Neo4j ID."""
        page_data = {
            "id": "page-123",
            "created_time": "2025-01-01T12:00:00.000Z",
            "properties": {
                "Name": {"title": [{"text": {"content": "Task"}}]},
                "Status": {"select": {"name": "To Do"}},
                "Priority": {"select": {"name": "P2"}},
                "Agent": {"select": {}},
                "Neo4j Task ID": {"rich_text": [{"text": {"content": "neo4j-123"}}]},
                "Requester": {"rich_text": []},
                "Created From": {"select": {}}
            }
        }

        task = integration._parse_notion_page(page_data)

        assert task is not None
        assert task.neo4j_task_id == "neo4j-123"

    def test_parse_notion_page_untitled(self, integration):
        """Test parsing page without title."""
        page_data = {
            "id": "page-123",
            "created_time": "2025-01-01T12:00:00.000Z",
            "properties": {
                "Name": {"title": []},
                "Status": {"select": {"name": "Backlog"}},
                "Priority": {"select": {"name": "P3"}},
                "Agent": {"select": {}},
                "Neo4j Task ID": {"rich_text": []},
                "Requester": {"rich_text": []},
                "Created From": {"select": {}}
            }
        }

        task = integration._parse_notion_page(page_data)

        assert task is not None
        assert task.title == "Untitled"

    def test_health_check_healthy(self, integration):
        """Test health check when everything is healthy."""
        with patch.object(integration.client, 'query_database', return_value={"results": []}):
            with patch.object(integration.memory, 'health_check', return_value={"status": "ok"}):
                health = integration.health_check()

                assert health["status"] == "healthy"
                assert health["notion_api"] is True
                assert health["database_accessible"] is True

    def test_health_check_notion_error(self, integration):
        """Test health check with Notion API error."""
        with patch.object(integration.client, 'query_database',
                         side_effect=NotionAuthError("Invalid token")):
            health = integration.health_check()

            assert health["status"] == "error"
            assert "authentication" in str(health["errors"]).lower()

    def test_create_indexes(self, integration, mock_memory):
        """Test creating indexes."""
        memory, mock_session = mock_memory

        mock_result = Mock()
        mock_session.run.return_value = mock_result

        indexes = integration.create_indexes()

        assert len(indexes) == 7
        assert "notion_task_page_id" in indexes
        assert "checkpoint_task_id" in indexes
        assert "agent_failure_agent" in indexes

    # -------------------------------------------------------------------------
    # Context Manager Tests
    # -------------------------------------------------------------------------

    def test_context_manager(self, integration):
        """Test using NotionIntegration as context manager."""
        with patch.object(integration, 'close'):
            with integration:
                pass

            integration.close.assert_called_once()


# =============================================================================
# Constants Tests
# =============================================================================

class TestConstants:
    """Test module constants."""

    def test_status_mapping(self):
        """Test status mapping has expected values."""
        assert STATUS_MAPPING["To Do"] == "pending"
        assert STATUS_MAPPING["In Progress"] == "in_progress"
        assert STATUS_MAPPING["Done"] == "completed"
        assert STATUS_MAPPING["Blocked"] == "blocked"

    def test_neo4j_to_notion_status(self):
        """Test reverse status mapping."""
        assert NEO4J_TO_NOTION_STATUS["pending"] == "To Do"
        assert NEO4J_TO_NOTION_STATUS["in_progress"] == "In Progress"
        assert NEO4J_TO_NOTION_STATUS["completed"] == "Done"

    def test_priority_mapping(self):
        """Test priority mapping."""
        assert PRIORITY_MAPPING["P0"] == "urgent"
        assert PRIORITY_MAPPING["P1"] == "high"
        assert PRIORITY_MAPPING["P2"] == "medium"
        assert PRIORITY_MAPPING["P3"] == "low"

    def test_notion_to_neo4j_priority(self):
        """Test Notion to Neo4j priority mapping."""
        assert NOTION_TO_NEO4J_PRIORITY["P0"] == "critical"
        assert NOTION_TO_NEO4J_PRIORITY["P1"] == "high"
        assert NOTION_TO_NEO4J_PRIORITY["P2"] == "normal"

    def test_error_classification(self):
        """Test error classification has expected agents."""
        assert ERROR_CLASSIFICATION["syntax_error"][0] == "developer"
        assert ERROR_CLASSIFICATION["api_error"][0] == "developer"
        assert ERROR_CLASSIFICATION["performance_issue"][0] == "analyst"
        assert ERROR_CLASSIFICATION["tone_issue"][0] == "writer"
        assert ERROR_CLASSIFICATION["sync_failure"][0] == "ops"

    def test_error_keywords(self):
        """Test error keywords for classification."""
        assert "syntax" in ERROR_KEYWORDS["syntax_error"]
        assert "api" in ERROR_KEYWORDS["api_error"]
        assert "slow" in ERROR_KEYWORDS["performance_issue"]

    def test_agent_ids(self):
        """Test agent ID constants."""
        assert KUBLAI_AGENT_ID == "main"
        assert OGEDEI_AGENT_ID == "ops"


# =============================================================================
# Convenience Functions Tests
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_create_notion_integration(self, mock_memory):
        """Test create_notion_integration convenience function."""
        memory, _ = mock_memory

        with patch.dict(os.environ, {
            "NOTION_TOKEN": "test_token",
            "NOTION_TASK_DATABASE_ID": "test_db"
        }):
            integration = create_notion_integration(memory)

            assert isinstance(integration, NotionIntegration)
            assert integration.memory == memory


# =============================================================================
# Data Class Tests
# =============================================================================

class TestDataClasses:
    """Test data class instantiation."""

    def test_notion_task(self):
        """Test NotionTask dataclass."""
        task = NotionTask(
            id="page-123",
            title="Test Task",
            status="To Do",
            priority="P1"
        )

        assert task.id == "page-123"
        assert task.title == "Test Task"
        assert task.status == "To Do"
        assert task.priority == "P1"
        assert task.neo4j_task_id is None

    def test_checkpoint(self):
        """Test Checkpoint dataclass."""
        now = datetime.now(timezone.utc)
        checkpoint = Checkpoint(
            id="cp-123",
            task_id="task-123",
            agent="developer",
            created_at=now,
            context_json='{"file": "test.py"}',
            progress_percent=50.0,
            expires_at=now + timedelta(hours=24)
        )

        assert checkpoint.id == "cp-123"
        assert checkpoint.agent == "developer"
        assert checkpoint.progress_percent == 50.0

    def test_agent_failure(self):
        """Test AgentFailure dataclass."""
        now = datetime.now(timezone.utc)
        failure = AgentFailure(
            id="f-123",
            agent="developer",
            task_type="code_review",
            error_type="syntax_error",
            fix_successful=True,
            fix_agent="developer",
            created_at=now
        )

        assert failure.id == "f-123"
        assert failure.agent == "developer"
        assert failure.error_type == "syntax_error"

    def test_error_classification(self):
        """Test ErrorClassification dataclass."""
        classification = ErrorClassification(
            error_type="syntax_error",
            recommended_agent="developer",
            confidence=0.95,
            reasoning="Matched keyword 'syntax'"
        )

        assert classification.error_type == "syntax_error"
        assert classification.confidence == 0.95

    def test_training_recommendation(self):
        """Test TrainingRecommendation dataclass."""
        recommendation = TrainingRecommendation(
            agent="developer",
            error_type="syntax_error",
            reason="Low success rate",
            priority="high",
            recent_failures=[]
        )

        assert recommendation.agent == "developer"
        assert recommendation.priority == "high"


# =============================================================================
# Integration Tests
# =============================================================================

class TestNotionIntegrationIntegration:
    """End-to-end integration tests."""

    def test_full_sync_cycle(self, mock_memory):
        """Test complete sync cycle from Notion to Neo4j and back."""
        memory, mock_session = mock_memory

        sample_notion_page = {
            "id": "page-123",
            "created_time": "2025-01-01T12:00:00.000Z",
            "properties": {
                "Name": {"title": [{"text": {"content": "Sync Test"}}]},
                "Status": {"select": {"name": "To Do"}},
                "Priority": {"select": {"name": "P1"}},
                "Agent": {"select": {"name": "developer"}},
                "Neo4j Task ID": {"rich_text": []},
                "Requester": {"rich_text": []},
                "Created From": {"select": {"name": "Notion"}}
            }
        }

        with patch.dict(os.environ, {
            "NOTION_TOKEN": "test_token",
            "NOTION_TASK_DATABASE_ID": "test_db"
        }):
            integration = NotionIntegration(memory)

            # 1. Poll for new tasks
            with patch.object(integration.client, 'query_database',
                             return_value={"results": [sample_notion_page]}):
                new_tasks = integration.poll_new_tasks()

                assert len(new_tasks) == 1
                notion_task = new_tasks[0]

                # 2. Create Neo4j task
                memory.create_task.return_value = "neo4j-task-id"
                with patch.object(integration.client, 'update_page'):
                    task_id = integration.create_neo4j_task_from_notion(notion_task)

                    assert task_id == "neo4j-task-id"

                    # 3. Sync status back to Notion
                    memory.get_task.return_value = {
                        "id": "neo4j-task-id",
                        "status": "completed"
                    }

                    with patch.object(integration, '_get_notion_page_id', return_value="page-123"):
                        with patch.object(integration, 'update_notion_task_status', return_value=True) as mock_update:
                            integration.sync_neo4j_status_to_notion("neo4j-task-id")

                            mock_update.assert_called_once_with("page-123", "Done")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
