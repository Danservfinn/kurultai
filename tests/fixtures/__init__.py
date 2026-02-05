"""
Test fixtures package for Kublai Testing Suite.

This package provides standardized test data fixtures for:
- Sample task data (pending, in_progress, completed, failed, blocked)
- Agent configurations (all 6 agents: kublai, jochi, temüjin, ögedei, chagatai, tolui)
- Neo4j query results and node structures
- Notification data
- DAG structures (linear, parallel, complex, cyclic)
- PII samples for privacy testing

Usage:
    from tests.fixtures import sample_task, agent_configs, dag_linear
    from tests.fixtures.test_data import SAMPLE_TASKS, AGENT_STATES

    # Or load from JSON files
    import json
    with open('tests/fixtures/neo4j_data.json') as f:
        neo4j_data = json.load(f)
"""

import json
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

# =============================================================================
# Package-level imports for convenience
# =============================================================================

# These will be populated after test_data.py is imported
# to avoid circular import issues

# =============================================================================
# JSON File Loaders
# =============================================================================

FIXTURES_DIR = Path(__file__).parent


def load_json_fixture(filename: str) -> Dict[str, Any]:
    """Load a JSON fixture file.

    Args:
        filename: Name of the JSON file (e.g., 'agents.json')

    Returns:
        Parsed JSON data as dictionary

    Raises:
        FileNotFoundError: If the fixture file doesn't exist
        json.JSONDecodeError: If the file contains invalid JSON
    """
    filepath = FIXTURES_DIR / filename
    with open(filepath, 'r') as f:
        return json.load(f)


def load_agent_configs() -> Dict[str, Any]:
    """Load agent configurations from JSON.

    Returns:
        Dictionary with 'agents', 'agent_states', and 'agent_routing' keys
    """
    return load_json_fixture('agent_configs.json')


def load_neo4j_data() -> Dict[str, Any]:
    """Load Neo4j test data from JSON.

    Returns:
        Dictionary with 'nodes', 'relationships', and 'query_results' keys
    """
    return load_json_fixture('neo4j_data.json')


def load_dag_scenarios() -> Dict[str, Any]:
    """Load DAG scenarios from JSON.

    Returns:
        Dictionary of named DAG scenarios
    """
    return load_json_fixture('dag_scenarios.json')


def load_pii_samples() -> Dict[str, Any]:
    """Load PII samples from JSON.

    Returns:
        Dictionary with PII samples for privacy testing
    """
    return load_json_fixture('pii_samples.json')


def load_tasks() -> Dict[str, Any]:
    """Load task fixtures from JSON.

    Returns:
        Dictionary with tasks by status category
    """
    return load_json_fixture('tasks.json')


# =============================================================================
# Fixture Constants
# =============================================================================

# Standard UUIDs for testing (deterministic)
TEST_UUIDS = {
    'task_1': '550e8400-e29b-41d4-a716-446655440001',
    'task_2': '550e8400-e29b-41d4-a716-446655440002',
    'task_3': '550e8400-e29b-41d4-a716-446655440003',
    'task_4': '550e8400-e29b-41d4-a716-446655440004',
    'task_5': '550e8400-e29b-41d4-a716-446655440005',
    'task_6': '550e8400-e29b-41d4-a716-446655440006',
    'task_7': '550e8400-e29b-41d4-a716-446655440007',
    'notification_1': '550e8400-e29b-41d4-a716-446655440008',
    'user_1': '550e8400-e29b-41d4-a716-446655440009',
}

# Standard timestamps for testing
TEST_TIMESTAMPS = {
    'iso_2025_01_01': '2025-01-01T12:00:00.000Z',
    'iso_2025_01_02': '2025-01-02T12:00:00.000Z',
    'iso_2025_01_03': '2025-01-03T12:00:00.000Z',
}

# Agent IDs
AGENT_IDS = ['kublai', 'jochi', 'temüjin', 'ögedei', 'chagatai', 'tolui']

# Task statuses
TASK_STATUSES = ['pending', 'in_progress', 'completed', 'failed', 'blocked', 'cancelled']

# Task priorities
TASK_PRIORITIES = ['low', 'normal', 'high', 'critical']

# Task types
TASK_TYPES = ['research', 'code', 'analysis', 'security', 'writing', 'synthesis', 'ops']


# =============================================================================
# Helper Functions
# =============================================================================

def generate_test_task(
    task_id: Optional[str] = None,
    task_type: str = 'generic',
    status: str = 'pending',
    priority: str = 'normal',
    assigned_to: str = 'jochi',
    delegated_by: str = 'kublai',
    **kwargs
) -> Dict[str, Any]:
    """Generate a test task with sensible defaults.

    Args:
        task_id: Optional task ID (generated if not provided)
        task_type: Type of task
        status: Task status
        priority: Task priority
        assigned_to: Agent ID assigned to the task
        delegated_by: Agent ID that delegated the task
        **kwargs: Additional fields to include

    Returns:
        Task dictionary
    """
    now = datetime.now(timezone.utc)
    task = {
        'task_id': task_id or str(uuid.uuid4()),
        'task_type': task_type,
        'description': f'Test {task_type} task',
        'status': status,
        'priority': priority,
        'assigned_to': assigned_to,
        'delegated_by': delegated_by,
        'created_at': now.isoformat(),
        **kwargs
    }

    if status == 'completed':
        task['completed_at'] = now.isoformat()
        task['result'] = 'Test task completed successfully'
    elif status == 'failed':
        task['failed_at'] = now.isoformat()
        task['error_message'] = 'Test failure'
    elif status == 'in_progress':
        task['claimed_at'] = now.isoformat()
    elif status == 'blocked':
        task['blocked_by'] = kwargs.get('blocked_by', [TEST_UUIDS['task_1']])

    return task


def generate_test_notification(
    notification_id: Optional[str] = None,
    target_agent: str = 'jochi',
    source_agent: str = 'kublai',
    notification_type: str = 'task_delegated',
    **kwargs
) -> Dict[str, Any]:
    """Generate a test notification with sensible defaults.

    Args:
        notification_id: Optional notification ID
        target_agent: Agent receiving the notification
        source_agent: Agent sending the notification
        notification_type: Type of notification
        **kwargs: Additional fields

    Returns:
        Notification dictionary
    """
    return {
        'notification_id': notification_id or str(uuid.uuid4()),
        'target_agent': target_agent,
        'source_agent': source_agent,
        'type': notification_type,
        'message': kwargs.get('message', f'New {notification_type}'),
        'task_id': kwargs.get('task_id', TEST_UUIDS['task_1']),
        'read': kwargs.get('read', False),
        'created_at': kwargs.get('created_at', datetime.now(timezone.utc).isoformat()),
        **kwargs
    }


def generate_neo4j_node(
    node_id: Optional[str] = None,
    labels: Optional[List[str]] = None,
    properties: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Generate a Neo4j node structure for testing.

    Args:
        node_id: Optional node ID
        labels: Node labels (e.g., ['Task', 'Pending'])
        properties: Node properties

    Returns:
        Neo4j node dictionary
    """
    return {
        'id': node_id or str(uuid.uuid4()),
        'labels': labels or ['Task'],
        'properties': properties or {
            'task_id': str(uuid.uuid4()),
            'status': 'pending',
            'created_at': datetime.now(timezone.utc).isoformat()
        }
    }


def generate_neo4j_relationship(
    rel_id: Optional[str] = None,
    rel_type: str = 'BLOCKS',
    start_node: Optional[str] = None,
    end_node: Optional[str] = None,
    properties: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Generate a Neo4j relationship structure for testing.

    Args:
        rel_id: Optional relationship ID
        rel_type: Relationship type (e.g., 'BLOCKS', 'DEPENDS_ON')
        start_node: ID of start node
        end_node: ID of end node
        properties: Relationship properties

    Returns:
        Neo4j relationship dictionary
    """
    return {
        'id': rel_id or str(uuid.uuid4()),
        'type': rel_type,
        'start_node': start_node or TEST_UUIDS['task_1'],
        'end_node': end_node or TEST_UUIDS['task_2'],
        'properties': properties or {
            'created_at': datetime.now(timezone.utc).isoformat()
        }
    }


# =============================================================================
# Version
# =============================================================================

__version__ = '1.0.0'
__all__ = [
    # Constants
    'TEST_UUIDS',
    'TEST_TIMESTAMPS',
    'AGENT_IDS',
    'TASK_STATUSES',
    'TASK_PRIORITIES',
    'TASK_TYPES',
    # Functions
    'load_json_fixture',
    'load_agent_configs',
    'load_neo4j_data',
    'load_dag_scenarios',
    'load_pii_samples',
    'load_tasks',
    'generate_test_task',
    'generate_test_notification',
    'generate_neo4j_node',
    'generate_neo4j_relationship',
]
