"""
Shared pytest configuration and fixtures for Kublai Testing Suite.

This module provides common fixtures for:
- Neo4j mocking (driver, session, result)
- OperationalMemory mock factory
- Test data factories (tasks, agents, notifications)
- DAG test fixtures for orchestration tests
- PII test data fixtures for privacy tests
- Configuration helpers
"""

import os
import sys
import uuid
import json
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Generator
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from dataclasses import dataclass, field

import pytest
import pytest_asyncio

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# =============================================================================
# Test Configuration
# =============================================================================

def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "slow: Slow-running tests")
    config.addinivalue_line("markers", "security: Security tests")
    config.addinivalue_line("markers", "performance: Performance tests")
    config.addinivalue_line("markers", "chaos: Chaos engineering tests")
    config.addinivalue_line("markers", "asyncio: Async tests")


# =============================================================================
# Neo4j Mock Fixtures
# =============================================================================

@pytest.fixture
def mock_neo4j_driver():
    """Create a mock Neo4j driver."""
    driver = MagicMock()
    driver.verify_connectivity.return_value = None
    return driver


@pytest.fixture
def mock_neo4j_session():
    """Create a mock Neo4j session."""
    session = MagicMock()

    def mock_run(cypher: str, **kwargs):
        """Mock run that returns an empty result by default."""
        result = MagicMock()
        result.single.return_value = None
        result.data.return_value = []
        result.__iter__ = lambda self: iter([])
        result.peek.return_value = []
        return result

    session.run = mock_run
    session.close = Mock()
    return session


@pytest.fixture
def mock_neo4j_result():
    """Create a mock Neo4j result with configurable data."""
    def _create_result(data: List[Dict] = None, single: Dict = None):
        result = MagicMock()
        result.data.return_value = data or []
        result.single.return_value = single
        result.__iter__ = lambda self: iter(data or [])
        result.peek.return_value = data or []
        result.values.return_value = [list(d.values()) for d in (data or [])]
        return result

    return _create_result


def create_mock_session(data: List[Dict] = None, single_result: Dict = None):
    """Create a mock Neo4j session with data."""
    session = MagicMock()

    result = MagicMock()
    result.data.return_value = data or []
    result.single.return_value = single_result
    result.__iter__ = lambda self: iter(data or [])
    result.peek.return_value = data or []
    result.values.return_value = [list(d.values()) for d in (data or [])]

    session.run = Mock(return_value=result)
    session.close = Mock()
    return session, result


@pytest.fixture
def mock_session_context():
    """Create a mock session context manager for _session()."""
    session = MagicMock()

    def mock_run(cypher: str, **kwargs):
        result = MagicMock()
        result.single.return_value = None
        result.data.return_value = []
        result.__iter__ = lambda self: iter([])
        return result

    session.run = mock_run
    session.close = Mock()

    context = MagicMock()
    context.__enter__ = Mock(return_value=session)
    context.__exit__ = Mock(return_value=False)
    return context, session


# =============================================================================
# OperationalMemory Mock Factory
# =============================================================================

@pytest.fixture
def mock_operational_memory():
    """Create a mock OperationalMemory with configured session."""
    from openclaw_memory import OperationalMemory

    with patch('openclaw_memory._get_graph_database') as mock_get_graph_db:
        mock_graph_db = MagicMock()
        driver = MagicMock()
        mock_graph_db.driver.return_value = driver
        mock_get_graph_db.return_value = mock_graph_db

        # Create actual instance with fallback mode
        memory = OperationalMemory(
            uri="bolt://localhost:7687",
            username="neo4j",
            password="test_password",
            database="neo4j",
            fallback_mode=True
        )

        # Configure mock session for Neo4j operations
        mock_session = MagicMock()

        # Create a default result that tests can override
        default_result = MagicMock()
        default_result.single.return_value = None
        default_result.data.return_value = []
        default_result.__iter__ = lambda self: iter([])
        default_result.peek.return_value = []

        # Make run() return the default result - tests can override with mock_session.run.return_value
        mock_session.run.return_value = default_result
        mock_session.close = MagicMock()

        # Mock the _session context manager
        session_ctx = MagicMock()
        session_ctx.__enter__ = MagicMock(return_value=mock_session)
        session_ctx.__exit__ = MagicMock(return_value=False)
        memory._session = MagicMock(return_value=session_ctx)

        yield memory, mock_session


@pytest.fixture
def operational_memory_with_fallback():
    """Create OperationalMemory in fallback mode for testing."""
    from openclaw_memory import OperationalMemory

    with patch('openclaw_memory._get_graph_database') as mock_get_graph_db:
        mock_graph_db = MagicMock()
        driver = MagicMock()
        mock_graph_db.driver.return_value = driver
        mock_get_graph_db.return_value = mock_graph_db

        memory = OperationalMemory(
            uri="bolt://localhost:7687",
            username="neo4j",
            password="test_password",
            database="neo4j",
            fallback_mode=True
        )

        yield memory


# =============================================================================
# Test Data Fixtures
# =============================================================================

@pytest.fixture
def sample_task_data():
    """Sample task data for testing."""
    return {
        "task_id": str(uuid.uuid4()),
        "task_type": "research",
        "description": "Test task for research",
        "delegated_by": "kublai",
        "assigned_to": "jochi",
        "priority": "normal",
        "status": "pending",
        "created_at": datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
        "metadata": {"test": True}
    }


@pytest.fixture
def sample_completed_task(sample_task_data):
    """Sample completed task data."""
    data = sample_task_data.copy()
    data["status"] = "completed"
    data["result"] = "Test result"
    data["completed_at"] = datetime(2025, 1, 1, 13, 0, 0, tzinfo=timezone.utc).isoformat()
    return data


@pytest.fixture
def sample_failed_task(sample_task_data):
    """Sample failed task data."""
    data = sample_task_data.copy()
    data["status"] = "failed"
    data["error_message"] = "Test error"
    data["failed_at"] = datetime(2025, 1, 1, 13, 0, 0, tzinfo=timezone.utc).isoformat()
    return data


@pytest.fixture
def sample_blocked_task(sample_task_data):
    """Sample blocked task data."""
    data = sample_task_data.copy()
    data["status"] = "blocked"
    data["blocked_by"] = [str(uuid.uuid4())]
    return data


@pytest.fixture
def agent_states():
    """Sample agent states for all 6 agents."""
    return {
        "kublai": {"id": "kublai", "role": "orchestrator", "status": "active"},
        "jochi": {"id": "jochi", "role": "backend_analyst", "status": "active"},
        "temüjin": {"id": "temüjin", "role": "security_auditor", "status": "active"},
        "ögedei": {"id": "ögedei", "role": "file_consistency", "status": "active"},
        "chagatai": {"id": "chagatai", "role": "background_synthesis", "status": "active"},
        "tolui": {"id": "tolui", "role": "frontend_specialist", "status": "active"},
    }


@pytest.fixture
def sample_notification():
    """Sample notification data."""
    return {
        "notification_id": str(uuid.uuid4()),
        "target_agent": "jochi",
        "source_agent": "kublai",
        "type": "task_delegated",
        "message": "New task assigned",
        "task_id": str(uuid.uuid4()),
        "read": False,
        "created_at": datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat()
    }


@pytest.fixture
def heartbeat_data():
    """Sample heartbeat data for agents."""
    now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    return [
        {
            "agent": "kublai",
            "last_seen": now.isoformat(),
            "status": "healthy"
        },
        {
            "agent": "jochi",
            "last_seen": (now - timedelta(seconds=30)).isoformat(),
            "status": "healthy"
        },
        {
            "agent": "temüjin",
            "last_seen": (now - timedelta(minutes=5)).isoformat(),
            "status": "stale"
        }
    ]


# =============================================================================
# PII Test Data Fixtures
# =============================================================================

@pytest.fixture
def pii_samples():
    """PII samples for privacy testing."""
    return {
        "emails": [
            "user@example.com",
            "john.doe@company.co.uk",
            "test+tag@gmail.com",
            "admin@test-domain.org"
        ],
        "phone_numbers": [
            "+1 (555) 123-4567",
            "555-123-4567",
            "1.555.123.4567",
            "+44 20 7123 4567"
        ],
        "ssns": [
            "123-45-6789",
            "987-65-4321",
            "123 45 6789"
        ],
        "api_keys": [
            "sk_live_51HvXjbK2NXdJv5QRYG3xYjL3mQZLNpHkL3kJT3G",
            "AKIAIOSFODNN7EXAMPLE",
            "sa_9876543210abcdefghijklmnopqrstuvwxyz"
        ],
        "names": [
            "John Doe",
            "Jane A. Smith",
            "Dr. Robert Johnson Jr."
        ],
        "addresses": [
            "123 Main St, Springfield, IL 62701",
            "456 Oak Avenue, Apt 7B, New York, NY 10001"
        ],
        "credit_cards": [
            "4111-1111-1111-1111",
            "5500 0000 0000 0004",
            "378282246310005"
        ],
        "ip_addresses": [
            "192.168.1.1",
            "10.0.0.1",
            "203.0.113.42"
        ]
    }


@pytest.fixture
def pii_preservation_contexts():
    """Contexts where PII should be preserved (allowed patterns)."""
    return {
        "allowed_emails": [
            "support@company.com",  # Generic company email
            "noreply@service.com"
        ],
        "example_domains": [
            "user@example.com",  # RFC 2606 example domain
            "test@test.com"
        ],
        "false_positives": [
            "Send to john.doe@",  # Incomplete email
            "Call 555-",          # Incomplete phone
            "Key: ABC123"         # Not an API key
        ]
    }


# =============================================================================
# DAG Test Fixtures
# =============================================================================

@pytest.fixture
def dag_linear_nodes():
    """Linear DAG: A -> B -> C -> D"""
    return [
        {"id": "A", "title": "First Task", "blocks": ["B"]},
        {"id": "B", "title": "Second Task", "blocks": ["C"], "blocked_by": ["A"]},
        {"id": "C", "title": "Third Task", "blocks": ["D"], "blocked_by": ["B"]},
        {"id": "D", "title": "Fourth Task", "blocked_by": ["C"]}
    ]


@pytest.fixture
def dag_parallel_nodes():
    """Parallel DAG: A -> [B, C, D] -> E"""
    return [
        {"id": "A", "title": "Start Task", "blocks": ["B", "C", "D"]},
        {"id": "B", "title": "Parallel Task 1", "blocks": ["E"], "blocked_by": ["A"]},
        {"id": "C", "title": "Parallel Task 2", "blocks": ["E"], "blocked_by": ["A"]},
        {"id": "D", "title": "Parallel Task 3", "blocks": ["E"], "blocked_by": ["A"]},
        {"id": "E", "title": "End Task", "blocked_by": ["B", "C", "D"]}
    ]


@pytest.fixture
def dag_complex_nodes():
    """Complex DAG with multiple levels."""
    return [
        {"id": "A", "title": "Research Goal", "blocks": ["B", "C"]},
        {"id": "B", "title": "Backend Analysis", "blocks": ["D"], "blocked_by": ["A"]},
        {"id": "C", "title": "Security Review", "blocks": ["E"], "blocked_by": ["A"]},
        {"id": "D", "title": "Implementation", "blocks": ["F"], "blocked_by": ["B"]},
        {"id": "E", "title": "Documentation", "blocks": ["F"], "blocked_by": ["C"]},
        {"id": "F", "title": "Final Review", "blocked_by": ["D", "E"]}
    ]


@pytest.fixture
def dag_with_cycle():
    """DAG containing a cycle (invalid)."""
    return [
        {"id": "A", "title": "Task A", "blocks": ["B"], "blocked_by": ["C"]},  # Creates cycle
        {"id": "B", "title": "Task B", "blocks": ["C"], "blocked_by": ["A"]},
        {"id": "C", "title": "Task C", "blocks": ["A"], "blocked_by": ["B"]}
    ]


@pytest.fixture
def semantic_similarity_vectors():
    """Vector pairs for similarity testing."""
    return {
        "identical": ([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]),
        "orthogonal": ([1.0, 0.0, 0.0], [0.0, 1.0, 0.0]),
        "similar": ([1.0, 0.0, 0.0], [0.9, 0.1, 0.0]),
        "opposite": ([1.0, 0.0, 0.0], [-1.0, 0.0, 0.0]),
        "high_similarity": ([0.8, 0.2, 0.0], [0.7, 0.3, 0.0]),
        "low_similarity": ([0.9, 0.1, 0.0], [0.1, 0.9, 0.0])
    }


# =============================================================================
# Intent Window Fixtures
# =============================================================================

@pytest.fixture
def intent_window_messages():
    """Sample messages for intent window testing."""
    return [
        {"content": "Fix the authentication bug", "timestamp": 1.0},
        {"content": "Update the API documentation", "timestamp": 2.0},
        {"content": "Add unit tests for the new feature", "timestamp": 3.0},
        {"content": "Review pull request #123", "timestamp": 4.0},
        {"content": "Deploy to staging", "timestamp": 5.0}
    ]


@pytest.fixture
def intent_window_config():
    """Configuration for intent window testing."""
    return {
        "window_duration_ms": 2000,  # 2 seconds
        "max_batch_size": 10,
        "enable_threading": True
    }


# =============================================================================
# Priority Command Fixtures
# =============================================================================

@pytest.fixture
def priority_command_samples():
    """Sample priority commands for testing."""
    return {
        "do_X_before_Y": "do the authentication work before the UI design",
        "do_X_first": "do the backend API first",
        "whats_the_plan": "what's the plan for the user authentication feature?",
        "sync_from_notion": "sync tasks from notion",
        "priority_override": "make this critical priority"
    }


# =============================================================================
# Notion Sync Fixtures
# =============================================================================

@pytest.fixture
def notion_task_data():
    """Sample Notion task data."""
    return {
        "id": "abc-123-def",
        "properties": {
            "Name": {
                "title": [
                    {"plain_text": "Implement OAuth flow"}
                ]
            },
            "Status": {
                "select": {"name": "Not Started"}
            },
            "Priority": {
                "select": {"name": "High"}
            }
        },
        "created_time": "2025-01-01T12:00:00.000Z",
        "last_edited_time": "2025-01-01T12:00:00.000Z"
    }


@pytest.fixture
def notion_database_response():
    """Sample Notion database query response."""
    return {
        "object": "list",
        "results": [],
        "next_cursor": None,
        "has_more": False
    }


# =============================================================================
# Rate Limiting Fixtures
# =============================================================================

@pytest.fixture
def rate_limit_data():
    """Sample rate limit data."""
    now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    return {
        "agent": "jochi",
        "operation": "claim_task",
        "count": 10,
        "hour": now.hour,
        "date": now.date().isoformat(),
        "max_limit": 100
    }


# =============================================================================
# Health Check Fixtures
# =============================================================================

@pytest.fixture
def health_check_responses():
    """Sample health check responses."""
    return {
        "healthy": {
            "status": "healthy",
            "neo4j_connected": True,
            "server_time": datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
            "rate_limit_ok": True
        },
        "unavailable": {
            "status": "unavailable",
            "neo4j_connected": False,
            "error": "Connection refused"
        },
        "read_only": {
            "status": "read_only",
            "neo4j_connected": True,
            "read_only_mode": True,
            "server_time": datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat()
        }
    }


# =============================================================================
# Failover Fixtures
# =============================================================================

@pytest.fixture
def failover_scenarios():
    """Sample failover scenarios."""
    return {
        "kublai_heartbeat_missed": {
            "agent": "kublai",
            "missed_heartbeats": 3,
            "threshold": 3,
            "should_activate": True
        },
        "kublai_recovered": {
            "agent": "kublai",
            "was_active": True,
            "heartbeat_restored": True,
            "should_deactivate": True
        },
        "failover_routing": {
            "delegating_agent": "ögedei",
            "original_target": "jochi",
            "routing_map": {
                "jochi": "jochi",  # Direct routing
                "temüjin": "temüjin"
            }
        }
    }


# =============================================================================
# Performance Test Fixtures
# =============================================================================

@pytest.fixture
def performance_targets():
    """Performance targets for load testing."""
    return {
        "p50_latency_ms": 100,
        "p95_latency_ms": 500,
        "p99_latency_ms": 1000,
        "max_concurrent_operations": 100,
        "throughput_per_second": 50
    }


@pytest.fixture
def large_dag_config():
    """Configuration for large DAG scalability testing."""
    return {
        "task_counts": [10, 50, 100, 500],
        "branching_factors": [1, 2, 3, 5],
        "dependency_density": [0.1, 0.3, 0.5]
    }


# =============================================================================
# Chaos Test Fixtures
# =============================================================================

@pytest.fixture
def chaos_scenarios():
    """Chaos test scenarios."""
    return {
        "neo4j_connection_drops": {
            "frequency": "random",
            "duration_ms": [100, 500, 1000],
            "operations": ["create_task", "claim_task", "complete_task"]
        },
        "gateway_timeouts": {
            "timeout_ms": 30,
            "retry_attempts": 3
        },
        "network_partitions": {
            "partitioned_agents": ["jochi", "temüjin"],
            "duration_seconds": 5
        }
    }


@pytest.fixture
def corruption_scenarios():
    """Data corruption scenarios for testing."""
    return {
        "invalid_status": {
            "task_id": str(uuid.uuid4()),
            "status": "invalid_status_value"
        },
        "orphaned_dependencies": {
            "task_id": str(uuid.uuid4()),
            "blocked_by": [str(uuid.uuid4()), str(uuid.uuid4())],
            "blocking_tasks_exist": False
        },
        "duplicate_ids": {
            "id": str(uuid.uuid4()),
            "duplicate_count": 3
        }
    }


# =============================================================================
# Delegation Protocol Fixtures
# =============================================================================

@pytest.fixture
def delegation_context():
    """Sample delegation context."""
    return {
        "user_message": "Implement OAuth authentication",
        "user_id": "user-123",
        "personal_memory": {
            "preferences": {"language": "python"},
            "history": ["previous task 1", "previous task 2"]
        },
        "available_agents": ["jochi", "temüjin", "ögedei", "chagatai", "tolui"]
    }


@pytest.fixture
def delegation_result():
    """Sample delegation result."""
    return {
        "task_id": str(uuid.uuid4()),
        "assigned_to": "jochi",
        "task_type": "code",
        "estimated_duration_seconds": 300,
        "status": "delegated"
    }


# =============================================================================
# Async Test Fixtures
# =============================================================================

@pytest.fixture
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    # Cleanup: cancel pending tasks before closing
    pending = asyncio.all_tasks(loop)
    for task in pending:
        task.cancel()
    if pending:
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    loop.close()


@pytest_asyncio.fixture
async def async_memory_with_session():
    """Async fixture for OperationalMemory with active session."""
    from openclaw_memory import OperationalMemory

    with patch('openclaw_memory._get_graph_database') as mock_get_graph_db:
        mock_graph_db = MagicMock()
        driver = MagicMock()
        mock_graph_db.driver.return_value = driver
        mock_get_graph_db.return_value = mock_graph_db

        memory = OperationalMemory(
            uri="bolt://localhost:7687",
            username="neo4j",
            password="test_password",
            database="neo4j",
            fallback_mode=True
        )

        # Mock async session
        mock_session, _ = create_mock_session()

        async def get_session():
            return mock_session

        memory.get_async_session = get_session

        yield memory, mock_session


# =============================================================================
# Test Helper Functions
# =============================================================================

@pytest.fixture
def task_factory():
    """Factory function for creating test tasks."""
    def _create(
        task_type: str = "generic",
        status: str = "pending",
        priority: str = "normal",
        assigned_to: str = "jochi",
        **kwargs
    ) -> Dict[str, Any]:
        return {
            "task_id": str(uuid.uuid4()),
            "task_type": task_type,
            "description": f"Test {task_type} task",
            "status": status,
            "priority": priority,
            "assigned_to": assigned_to,
            "delegated_by": "kublai",
            "created_at": datetime.now(timezone.utc).isoformat(),
            **kwargs
        }

    return _create


@pytest.fixture
def agent_factory():
    """Factory function for creating test agents."""
    def _create(
        agent_id: str = "test-agent",
        role: str = "specialist",
        status: str = "active",
        **kwargs
    ) -> Dict[str, Any]:
        return {
            "id": agent_id,
            "role": role,
            "status": status,
            "capabilities": kwargs.get("capabilities", ["generic"]),
            "last_heartbeat": datetime.now(timezone.utc).isoformat(),
            **kwargs
        }

    return _create


@pytest.fixture
def notification_factory():
    """Factory function for creating test notifications."""
    def _create(
        target_agent: str = "jochi",
        source_agent: str = "kublai",
        notification_type: str = "task_delegated",
        **kwargs
    ) -> Dict[str, Any]:
        return {
            "notification_id": str(uuid.uuid4()),
            "target_agent": target_agent,
            "source_agent": source_agent,
            "type": notification_type,
            "message": kwargs.get("message", f"New {notification_type}"),
            "read": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            **kwargs
        }

    return _create


@pytest.fixture
def dag_node_factory():
    """Factory function for creating DAG nodes."""
    def _create(
        node_id: str = None,
        title: str = "Test Node",
        blocks: List[str] = None,
        blocked_by: List[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        return {
            "id": node_id or str(uuid.uuid4()),
            "title": title,
            "blocks": blocks or [],
            "blocked_by": blocked_by or [],
            "status": "pending",
            "priority": "normal",
            **kwargs
        }

    return _create


# =============================================================================
# Environment Fixtures
# =============================================================================

@pytest.fixture
def test_env_vars():
    """Return expected test environment variable values.

    Note: Environment variables are set by the reset_environment autouse fixture.
    This fixture just returns the expected values for assertions.
    """
    return {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USERNAME": "neo4j",
        "NEO4J_PASSWORD": "test_password",
        "NEO4J_DATABASE": "neo4j",
        "FALLBACK_MODE": "true",
        "LOG_LEVEL": "DEBUG"
    }


@pytest.fixture
def temp_test_dir(tmp_path):
    """Create a temporary directory for test artifacts."""
    test_dir = tmp_path / "test_artifacts"
    test_dir.mkdir()
    return test_dir


# =============================================================================
# Coverage Helpers
# =============================================================================

@pytest.fixture
def coverage_exclusions():
    """Return list of paths to exclude from coverage."""
    return [
        "*/tests/*",
        "*/test_*.py",
        "*/__pycache__/*",
        "*/site-packages/*",
        "*/dist-packages/*"
    ]


# =============================================================================
# Markers for pytest
# =============================================================================

def pytest_collection_modifyitems(items):
    """Add markers to tests based on their location/type."""
    for item in items:
        # Mark based on file location
        if "integration/" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "security/" in str(item.fspath):
            item.add_marker(pytest.mark.security)
        elif "performance/" in str(item.fspath):
            item.add_marker(pytest.mark.performance)
            item.add_marker(pytest.mark.slow)
        elif "chaos/" in str(item.fspath):
            item.add_marker(pytest.mark.chaos)
            item.add_marker(pytest.mark.slow)
        else:
            item.add_marker(pytest.mark.unit)

        # Mark async tests
        if asyncio.iscoroutinefunction(item.function):
            item.add_marker(pytest.mark.asyncio)


# =============================================================================
# Test Isolation Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def reset_global_state():
    """
    Reset global state before each test to ensure test isolation.

    This fixture runs automatically before each test and clears any
    global state that could cause test ordering dependencies.
    """
    # Clear MemoryManagerFactory singleton instances
    # Use sys.modules to check if already imported to avoid triggering imports
    # which can cause issues with C-extension modules like numpy
    if 'memory_manager' in sys.modules:
        try:
            memory_module = sys.modules['memory_manager']
            if hasattr(memory_module, 'MemoryManagerFactory'):
                factory = memory_module.MemoryManagerFactory
                if hasattr(factory, '_instances'):
                    factory._instances.clear()
        except (ImportError, AttributeError, Exception):
            pass

    yield

    # Cleanup after test
    if 'memory_manager' in sys.modules:
        try:
            memory_module = sys.modules['memory_manager']
            if hasattr(memory_module, 'MemoryManagerFactory'):
                factory = memory_module.MemoryManagerFactory
                if hasattr(factory, '_instances'):
                    factory._instances.clear()
        except (ImportError, AttributeError, Exception):
            pass


@pytest.fixture(autouse=True)
def reset_environment(monkeypatch):
    """
    Reset environment variables to known defaults before each test.

    This ensures tests don't depend on external environment state.
    """
    # Set default test environment variables
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("NEO4J_USERNAME", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "test_password")
    monkeypatch.setenv("NEO4J_DATABASE", "neo4j")
    monkeypatch.setenv("FALLBACK_MODE", "true")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    yield


@pytest.fixture(autouse=True)
def reset_mock_objects():
    """
    Reset any mock objects that might retain state between tests.

    This fixture ensures that mock call history and side effects
    don't leak between tests.
    """
    # Store original state if needed
    yield
    # Mocks are recreated per test via other fixtures, so no cleanup needed here


@pytest.fixture(autouse=True)
def isolate_asyncio():
    """
    Ensure proper asyncio isolation between tests.

    This prevents event loop state from leaking between tests.
    Uses new_event_loop() and set_event_loop() to avoid deprecated get_event_loop().
    """
    # Create a new event loop for this test
    old_loop = None
    try:
        old_loop = asyncio.get_event_loop()
    except RuntimeError:
        pass  # No event loop exists yet

    # Create and set new loop
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)

    yield

    # Cleanup: close and reset event loop
    try:
        current_loop = asyncio.get_event_loop()
        if current_loop is new_loop and not current_loop.is_closed():
            # Cancel any pending tasks
            try:
                pending = asyncio.all_tasks(current_loop)
                for task in pending:
                    task.cancel()
                if pending:
                    current_loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            except Exception:
                pass  # Ignore errors during cleanup
            current_loop.close()
    except RuntimeError:
        pass  # No event loop

    # Restore old loop if it existed and wasn't closed
    if old_loop is not None and not old_loop.is_closed():
        asyncio.set_event_loop(old_loop)
    else:
        # Create fresh loop for next test
        try:
            asyncio.set_event_loop(asyncio.new_event_loop())
        except Exception:
            pass


@pytest.fixture(autouse=True)
def cleanup_file_handles():
    """
    Cleanup any open file handles after each test.

    This prevents file descriptor leaks between tests.
    """
    yield

    # Cleanup: close any remaining mock file handles
    import gc
    import warnings

    # Suppress resource warnings during gc.collect() - these are from
    # mock objects and test fixtures, not actual leaks
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)
        gc.collect()


@pytest.fixture(autouse=True)
def reset_import_cache():
    """
    Reset module-level caches that might persist between tests.

    This ensures that module-level state doesn't leak between tests.
    Note: This fixture is currently a no-op to avoid issues with numpy
    and other C-extension modules being reloaded. Individual tests
    should clean up their own module-level state.
    """
    yield
    # Note: We intentionally do NOT remove modules from sys.modules here
    # as reloading C-extension modules like numpy can cause issues.
    # Instead, tests should use proper mocking and cleanup.
