"""
Test data fixtures for Kublai Testing Suite.

This module provides Python-native test data structures for use in tests.
For JSON fixtures, see the individual .json files in this directory.

Usage:
    from tests.fixtures.test_data import (
        SAMPLE_TASKS,
        AGENT_CONFIGS,
        NEO4J_QUERY_RESULTS,
        SAMPLE_NOTIFICATIONS,
        DAG_STRUCTURES
    )
"""

import random
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

# =============================================================================
# Sample Task Data
# =============================================================================

SAMPLE_TASK_DATA = {
    "task_id": "550e8400-e29b-41d4-a716-446655440001",
    "task_type": "research",
    "description": "Test task for research",
    "delegated_by": "kublai",
    "assigned_to": "jochi",
    "priority": "normal",
    "status": "pending",
    "created_at": "2025-01-01T12:00:00.000Z",
    "metadata": {"test": True, "complexity": "medium"}
}

SAMPLE_TASKS = {
    "pending": {
        "task_id": "550e8400-e29b-41d4-a716-446655440001",
        "task_type": "research",
        "description": "Investigate OAuth 2.0 implementation options",
        "delegated_by": "kublai",
        "assigned_to": "jochi",
        "priority": "normal",
        "status": "pending",
        "created_at": "2025-01-01T12:00:00.000Z",
        "metadata": {"complexity": "medium", "estimated_hours": 4}
    },
    "in_progress": {
        "task_id": "550e8400-e29b-41d4-a716-446655440002",
        "task_type": "code",
        "description": "Implement JWT token validation middleware",
        "delegated_by": "kublai",
        "assigned_to": "jochi",
        "priority": "high",
        "status": "in_progress",
        "claimed_at": "2025-01-01T12:15:00.000Z",
        "created_at": "2025-01-01T12:05:00.000Z",
        "metadata": {"complexity": "high", "estimated_hours": 6}
    },
    "completed": {
        "task_id": "550e8400-e29b-41d4-a716-446655440003",
        "task_type": "code",
        "description": "Set up project structure for auth module",
        "delegated_by": "kublai",
        "assigned_to": "jochi",
        "priority": "high",
        "status": "completed",
        "result": "Created auth module with __init__.py, models.py, and handlers.py",
        "completed_at": "2025-01-01T13:00:00.000Z",
        "created_at": "2025-01-01T11:00:00.000Z",
        "metadata": {"complexity": "low", "estimated_hours": 1}
    },
    "failed": {
        "task_id": "550e8400-e29b-41d4-a716-446655440004",
        "task_type": "code",
        "description": "Integrate with external OAuth provider",
        "delegated_by": "kublai",
        "assigned_to": "jochi",
        "priority": "normal",
        "status": "failed",
        "error_message": "API rate limit exceeded after 100 requests",
        "failed_at": "2025-01-01T14:00:00.000Z",
        "created_at": "2025-01-01T12:30:00.000Z",
        "retry_count": 2,
        "metadata": {"complexity": "high", "estimated_hours": 4}
    },
    "blocked": {
        "task_id": "550e8400-e29b-41d4-a716-446655440005",
        "task_type": "code",
        "description": "Implement refresh token rotation",
        "delegated_by": "kublai",
        "assigned_to": "jochi",
        "priority": "high",
        "status": "blocked",
        "blocked_by": ["550e8400-e29b-41d4-a716-446655440002"],
        "created_at": "2025-01-01T12:20:00.000Z",
        "metadata": {"complexity": "medium", "estimated_hours": 3}
    },
    "cancelled": {
        "task_id": "550e8400-e29b-41d4-a716-446655440006",
        "task_type": "research",
        "description": "Research legacy authentication methods",
        "delegated_by": "kublai",
        "assigned_to": "jochi",
        "priority": "low",
        "status": "cancelled",
        "cancelled_at": "2025-01-01T13:30:00.000Z",
        "cancellation_reason": "No longer needed",
        "created_at": "2025-01-01T12:00:00.000Z",
        "metadata": {"complexity": "low", "estimated_hours": 2}
    }
}

# Task lists by status for bulk operations
PENDING_TASKS = [
    SAMPLE_TASKS["pending"],
    {
        "task_id": "550e8400-e29b-41d4-a716-446655440007",
        "task_type": "analysis",
        "description": "Analyze authentication flow for security vulnerabilities",
        "delegated_by": "kublai",
        "assigned_to": "temüjin",
        "priority": "critical",
        "status": "pending",
        "created_at": "2025-01-01T12:10:00.000Z",
        "metadata": {"complexity": "high", "estimated_hours": 3}
    }
]

IN_PROGRESS_TASKS = [SAMPLE_TASKS["in_progress"]]
COMPLETED_TASKS = [SAMPLE_TASKS["completed"]]
FAILED_TASKS = [SAMPLE_TASKS["failed"]]
BLOCKED_TASKS = [SAMPLE_TASKS["blocked"]]

# =============================================================================
# Agent Configurations
# =============================================================================

AGENT_CONFIGS = {
    "kublai": {
        "id": "kublai",
        "name": "Kublai Khan",
        "role": "orchestrator",
        "description": "Multi-agent orchestrator and delegation coordinator",
        "capabilities": [
            "delegation",
            "coordination",
            "synthesis",
            "monitoring",
            "routing"
        ],
        "status": "active",
        "last_heartbeat": "2025-01-01T12:00:00.000Z",
        "tasks_completed": 156,
        "tasks_failed": 3,
        "average_response_time_ms": 250,
        "max_concurrent_tasks": 10,
        "priority": 1,
        "can_delegate_to": ["jochi", "temüjin", "ögedei", "chagatai", "tolui"],
        "fallback_for": []
    },
    "jochi": {
        "id": "jochi",
        "name": "Jochi",
        "role": "backend_analyst",
        "description": "Backend code analysis and issue identification specialist",
        "capabilities": [
            "code_analysis",
            "backend_review",
            "api_analysis",
            "database_review",
            "performance_analysis"
        ],
        "status": "active",
        "last_heartbeat": "2025-01-01T12:00:30.000Z",
        "tasks_completed": 89,
        "tasks_failed": 5,
        "average_response_time_ms": 1800,
        "max_concurrent_tasks": 5,
        "priority": 2,
        "can_delegate_to": [],
        "fallback_for": []
    },
    "temüjin": {
        "id": "temüjin",
        "name": "Temüjin",
        "role": "security_auditor",
        "description": "Security audit and vulnerability assessment specialist",
        "capabilities": [
            "security_audit",
            "vulnerability_scan",
            "owasp_analysis",
            "penetration_testing",
            "compliance_check"
        ],
        "status": "active",
        "last_heartbeat": "2025-01-01T11:58:00.000Z",
        "tasks_completed": 67,
        "tasks_failed": 1,
        "average_response_time_ms": 2200,
        "max_concurrent_tasks": 3,
        "priority": 2,
        "can_delegate_to": [],
        "fallback_for": []
    },
    "ögedei": {
        "id": "ögedei",
        "name": "Ögedei",
        "role": "file_consistency_manager",
        "description": "File consistency and emergency routing specialist",
        "capabilities": [
            "file_consistency",
            "emergency_routing",
            "improvement_detection",
            "refactoring",
            "conflict_resolution"
        ],
        "status": "active",
        "last_heartbeat": "2025-01-01T12:00:15.000Z",
        "tasks_completed": 45,
        "tasks_failed": 2,
        "average_response_time_ms": 1200,
        "max_concurrent_tasks": 4,
        "priority": 2,
        "can_delegate_to": [],
        "fallback_for": ["kublai"]
    },
    "chagatai": {
        "id": "chagatai",
        "name": "Chagatai",
        "role": "background_synthesizer",
        "description": "Background synthesis and continuous improvement specialist",
        "capabilities": [
            "background_synthesis",
            "meta_learning",
            "pattern_recognition",
            "knowledge_extraction",
            "documentation"
        ],
        "status": "active",
        "last_heartbeat": "2025-01-01T11:59:45.000Z",
        "tasks_completed": 234,
        "tasks_failed": 8,
        "average_response_time_ms": 3500,
        "max_concurrent_tasks": 8,
        "priority": 2,
        "can_delegate_to": [],
        "fallback_for": []
    },
    "tolui": {
        "id": "tolui",
        "name": "Tolui",
        "role": "frontend_specialist",
        "description": "Frontend code and UI/UX review specialist",
        "capabilities": [
            "frontend_review",
            "accessibility_audit",
            "ux_analysis",
            "component_review",
            "responsive_design"
        ],
        "status": "active",
        "last_heartbeat": "2025-01-01T12:00:00.000Z",
        "tasks_completed": 78,
        "tasks_failed": 4,
        "average_response_time_ms": 1500,
        "max_concurrent_tasks": 5,
        "priority": 2,
        "can_delegate_to": [],
        "fallback_for": []
    }
}

# Agent states for different scenarios
AGENT_STATES = {
    "all_active": {
        "kublai": "active",
        "jochi": "active",
        "temüjin": "active",
        "ögedei": "active",
        "chagatai": "active",
        "tolui": "active"
    },
    "one_stale": {
        "kublai": "active",
        "jochi": "active",
        "temüjin": "stale",
        "ögedei": "active",
        "chagatai": "active",
        "tolui": "active"
    },
    "one_unavailable": {
        "kublai": "active",
        "jochi": "active",
        "temüjin": "unavailable",
        "ögedei": "active",
        "chagatai": "active",
        "tolui": "active"
    },
    "failover_active": {
        "kublai": "unavailable",
        "jochi": "active",
        "temüjin": "active",
        "ögedei": "emergency_router",
        "chagatai": "active",
        "tolui": "active"
    },
    "degraded": {
        "kublai": "active",
        "jochi": "stale",
        "temüjin": "unavailable",
        "ögedei": "active",
        "chagatai": "stale",
        "tolui": "active"
    }
}

# Agent routing map for task types
AGENT_ROUTING = {
    "code": ["jochi", "tolui"],
    "security": ["temüjin"],
    "backend": ["jochi"],
    "frontend": ["tolui"],
    "analysis": ["jochi", "temüjin"],
    "synthesis": ["chagatai"],
    "improvement": ["ögedei", "chagatai"],
    "file_consistency": ["ögedei"],
    "delegation": ["kublai"],
    "research": ["jochi", "chagatai"],
    "writing": ["chagatai"],
    "ops": ["ögedei"]
}

# =============================================================================
# Neo4j Query Results
# =============================================================================

NEO4J_QUERY_RESULTS = {
    "empty_result": {
        "data": [],
        "single": None,
        "values": []
    },
    "single_task": {
        "data": [
            {
                "t": {
                    "task_id": "550e8400-e29b-41d4-a716-446655440001",
                    "status": "pending",
                    "priority": "normal",
                    "created_at": "2025-01-01T12:00:00.000Z"
                }
            }
        ],
        "single": {
            "t": {
                "task_id": "550e8400-e29b-41d4-a716-446655440001",
                "status": "pending",
                "priority": "normal",
                "created_at": "2025-01-01T12:00:00.000Z"
            }
        },
        "values": [[{
            "task_id": "550e8400-e29b-41d4-a716-446655440001",
            "status": "pending",
            "priority": "normal",
            "created_at": "2025-01-01T12:00:00.000Z"
        }]]
    },
    "multiple_tasks": {
        "data": [
            {"t": {"task_id": "550e8400-e29b-41d4-a716-446655440001", "status": "pending"}},
            {"t": {"task_id": "550e8400-e29b-41d4-a716-446655440002", "status": "in_progress"}},
            {"t": {"task_id": "550e8400-e29b-41d4-a716-446655440003", "status": "completed"}}
        ],
        "single": {"t": {"task_id": "550e8400-e29b-41d4-a716-446655440001", "status": "pending"}},
        "values": [
            [{"task_id": "550e8400-e29b-41d4-a716-446655440001", "status": "pending"}],
            [{"task_id": "550e8400-e29b-41d4-a716-446655440002", "status": "in_progress"}],
            [{"task_id": "550e8400-e29b-41d4-a716-446655440003", "status": "completed"}]
        ]
    },
    "agent_heartbeat": {
        "data": [
            {
                "a": {
                    "id": "kublai",
                    "status": "active",
                    "last_heartbeat": "2025-01-01T12:00:00.000Z"
                },
                "last_seen": "2025-01-01T12:00:00.000Z"
            }
        ],
        "single": {
            "a": {
                "id": "kublai",
                "status": "active",
                "last_heartbeat": "2025-01-01T12:00:00.000Z"
            },
            "last_seen": "2025-01-01T12:00:00.000Z"
        },
        "values": [[{
            "id": "kublai",
            "status": "active",
            "last_heartbeat": "2025-01-01T12:00:00.000Z"
        }, "2025-01-01T12:00:00.000Z"]]
    },
    "task_with_dependencies": {
        "data": [
            {
                "t": {
                    "task_id": "550e8400-e29b-41d4-a716-446655440002",
                    "status": "in_progress"
                },
                "dependencies": [
                    {"task_id": "550e8400-e29b-41d4-a716-446655440001", "status": "completed"}
                ],
                "dependents": [
                    {"task_id": "550e8400-e29b-41d4-a716-446655440003", "status": "pending"}
                ]
            }
        ],
        "single": {
            "t": {
                "task_id": "550e8400-e29b-41d4-a716-446655440002",
                "status": "in_progress"
            },
            "dependencies": [
                {"task_id": "550e8400-e29b-41d4-a716-446655440001", "status": "completed"}
            ],
            "dependents": [
                {"task_id": "550e8400-e29b-41d4-a716-446655440003", "status": "pending"}
            ]
        },
        "values": [[{
            "task_id": "550e8400-e29b-41d4-a716-446655440002",
            "status": "in_progress"
        }]]
    },
    "count_result": {
        "data": [{"count": 42}],
        "single": {"count": 42},
        "values": [[42]]
    },
    "notification_result": {
        "data": [
            {
                "n": {
                    "notification_id": "550e8400-e29b-41d4-a716-446655440008",
                    "target_agent": "jochi",
                    "type": "task_delegated",
                    "read": False
                }
            }
        ],
        "single": {
            "n": {
                "notification_id": "550e8400-e29b-41d4-a716-446655440008",
                "target_agent": "jochi",
                "type": "task_delegated",
                "read": False
            }
        },
        "values": [[{
            "notification_id": "550e8400-e29b-41d4-a716-446655440008",
            "target_agent": "jochi",
            "type": "task_delegated",
            "read": False
        }]]
    }
}

# Neo4j node structures
NEO4J_NODES = {
    "task_node": {
        "id": "node-1",
        "labels": ["Task", "Pending"],
        "properties": {
            "task_id": "550e8400-e29b-41d4-a716-446655440001",
            "task_type": "research",
            "description": "Investigate OAuth 2.0 implementation options",
            "status": "pending",
            "priority": "normal",
            "assigned_to": "jochi",
            "delegated_by": "kublai",
            "created_at": "2025-01-01T12:00:00.000Z",
            "updated_at": "2025-01-01T12:00:00.000Z"
        }
    },
    "agent_node": {
        "id": "node-2",
        "labels": ["Agent"],
        "properties": {
            "id": "jochi",
            "role": "backend_analyst",
            "status": "active",
            "last_heartbeat": "2025-01-01T12:00:30.000Z",
            "capabilities": ["code_analysis", "backend_review", "api_analysis"]
        }
    },
    "goal_node": {
        "id": "node-3",
        "labels": ["Goal", "Active"],
        "properties": {
            "goal_id": "goal-auth-001",
            "title": "Authentication Goal",
            "description": "Implement secure authentication system",
            "status": "active",
            "priority": "critical",
            "created_at": "2025-01-01T12:00:00.000Z"
        }
    },
    "notification_node": {
        "id": "node-4",
        "labels": ["Notification", "Unread"],
        "properties": {
            "notification_id": "550e8400-e29b-41d4-a716-446655440008",
            "target_agent": "jochi",
            "source_agent": "kublai",
            "type": "task_delegated",
            "message": "New task assigned",
            "read": False,
            "created_at": "2025-01-01T12:00:00.000Z"
        }
    }
}

# Neo4j relationship structures
NEO4J_RELATIONSHIPS = {
    "blocks": {
        "id": "rel-1",
        "type": "BLOCKS",
        "start_node": "node-1",
        "end_node": "node-2",
        "properties": {
            "created_at": "2025-01-01T12:00:00.000Z",
            "reason": "Dependency"
        }
    },
    "depends_on": {
        "id": "rel-2",
        "type": "DEPENDS_ON",
        "start_node": "node-2",
        "end_node": "node-1",
        "properties": {
            "created_at": "2025-01-01T12:00:00.000Z"
        }
    },
    "assigned_to": {
        "id": "rel-3",
        "type": "ASSIGNED_TO",
        "start_node": "node-1",
        "end_node": "node-2",
        "properties": {
            "assigned_at": "2025-01-01T12:00:00.000Z",
            "delegated_by": "kublai"
        }
    },
    "part_of": {
        "id": "rel-4",
        "type": "PART_OF",
        "start_node": "node-1",
        "end_node": "node-3",
        "properties": {
            "added_at": "2025-01-01T12:00:00.000Z"
        }
    },
    "notifies": {
        "id": "rel-5",
        "type": "NOTIFIES",
        "start_node": "node-4",
        "end_node": "node-2",
        "properties": {
            "created_at": "2025-01-01T12:00:00.000Z"
        }
    }
}

# =============================================================================
# Sample Notification Data
# =============================================================================

SAMPLE_NOTIFICATIONS = {
    "task_delegated": {
        "notification_id": "550e8400-e29b-41d4-a716-446655440008",
        "target_agent": "jochi",
        "source_agent": "kublai",
        "type": "task_delegated",
        "message": "New task assigned: Implement OAuth flow",
        "task_id": "550e8400-e29b-41d4-a716-446655440001",
        "read": False,
        "created_at": "2025-01-01T12:00:00.000Z"
    },
    "task_completed": {
        "notification_id": "550e8400-e29b-41d4-a716-446655440009",
        "target_agent": "kublai",
        "source_agent": "jochi",
        "type": "task_completed",
        "message": "Task completed: JWT middleware implementation",
        "task_id": "550e8400-e29b-41d4-a716-446655440002",
        "read": False,
        "created_at": "2025-01-01T13:00:00.000Z",
        "result_summary": "Successfully implemented JWT validation"
    },
    "task_failed": {
        "notification_id": "550e8400-e29b-41d4-a716-446655440010",
        "target_agent": "kublai",
        "source_agent": "jochi",
        "type": "task_failed",
        "message": "Task failed: OAuth provider integration",
        "task_id": "550e8400-e29b-41d4-a716-446655440004",
        "read": False,
        "created_at": "2025-01-01T14:00:00.000Z",
        "error_summary": "API rate limit exceeded"
    },
    "agent_status_change": {
        "notification_id": "550e8400-e29b-41d4-a716-446655440011",
        "target_agent": "kublai",
        "source_agent": "system",
        "type": "agent_status_change",
        "message": "Agent temüjin is now unavailable",
        "agent_id": "temüjin",
        "previous_status": "active",
        "new_status": "unavailable",
        "read": False,
        "created_at": "2025-01-01T12:05:00.000Z"
    },
    "heartbeat_missed": {
        "notification_id": "550e8400-e29b-41d4-a716-446655440012",
        "target_agent": "ögedei",
        "source_agent": "system",
        "type": "heartbeat_missed",
        "message": "Kublai heartbeat missed - failover activated",
        "agent_id": "kublai",
        "missed_count": 3,
        "read": False,
        "created_at": "2025-01-01T12:10:00.000Z"
    }
}

NOTIFICATION_LIST = list(SAMPLE_NOTIFICATIONS.values())

# =============================================================================
# DAG Structures
# =============================================================================

DAG_STRUCTURES = {
    "linear": {
        "description": "Simple linear chain of tasks: A -> B -> C -> D",
        "nodes": [
            {"id": "A", "title": "First Task", "blocks": ["B"], "status": "pending"},
            {"id": "B", "title": "Second Task", "blocks": ["C"], "blocked_by": ["A"], "status": "pending"},
            {"id": "C", "title": "Third Task", "blocks": ["D"], "blocked_by": ["B"], "status": "pending"},
            {"id": "D", "title": "Fourth Task", "blocked_by": ["C"], "status": "pending"}
        ],
        "execution_order": ["A", "B", "C", "D"],
        "parallel_sets": []
    },
    "parallel": {
        "description": "Multiple independent tasks: A -> [B, C, D] -> E",
        "nodes": [
            {"id": "A", "title": "Start Task", "blocks": ["B", "C", "D"], "status": "pending"},
            {"id": "B", "title": "Parallel Task 1", "blocks": ["E"], "blocked_by": ["A"], "status": "pending"},
            {"id": "C", "title": "Parallel Task 2", "blocks": ["E"], "blocked_by": ["A"], "status": "pending"},
            {"id": "D", "title": "Parallel Task 3", "blocks": ["E"], "blocked_by": ["A"], "status": "pending"},
            {"id": "E", "title": "End Task", "blocked_by": ["B", "C", "D"], "status": "pending"}
        ],
        "execution_order": ["A", ["B", "C", "D"], "E"],
        "parallel_sets": [["B", "C", "D"]]
    },
    "complex": {
        "description": "Complex multi-goal orchestration",
        "nodes": [
            {"id": "A", "title": "Research Goal", "blocks": ["B", "C"], "status": "pending"},
            {"id": "B", "title": "Backend Analysis", "blocks": ["D"], "blocked_by": ["A"], "status": "pending"},
            {"id": "C", "title": "Security Review", "blocks": ["E"], "blocked_by": ["A"], "status": "pending"},
            {"id": "D", "title": "Implementation", "blocks": ["F"], "blocked_by": ["B"], "status": "pending"},
            {"id": "E", "title": "Documentation", "blocks": ["F"], "blocked_by": ["C"], "status": "pending"},
            {"id": "F", "title": "Final Review", "blocked_by": ["D", "E"], "status": "pending"}
        ],
        "execution_order": ["A", ["B", "C"], ["D", "E"], "F"],
        "parallel_sets": [["B", "C"], ["D", "E"]]
    },
    "diamond": {
        "description": "Diamond pattern: A -> [B, C] -> D",
        "nodes": [
            {"id": "A", "title": "Start", "blocks": ["B", "C"], "status": "pending"},
            {"id": "B", "title": "Left Branch", "blocks": ["D"], "blocked_by": ["A"], "status": "pending"},
            {"id": "C", "title": "Right Branch", "blocks": ["D"], "blocked_by": ["A"], "status": "pending"},
            {"id": "D", "title": "Merge", "blocked_by": ["B", "C"], "status": "pending"}
        ],
        "execution_order": ["A", ["B", "C"], "D"],
        "parallel_sets": [["B", "C"]]
    },
    "cycle": {
        "description": "Invalid DAG containing a cycle (A -> B -> C -> A)",
        "nodes": [
            {"id": "A", "title": "Task A", "blocks": ["B"], "blocked_by": ["C"], "status": "pending"},
            {"id": "B", "title": "Task B", "blocks": ["C"], "blocked_by": ["A"], "status": "pending"},
            {"id": "C", "title": "Task C", "blocks": ["A"], "blocked_by": ["B"], "status": "pending"}
        ],
        "cycle": ["A", "B", "C", "A"],
        "is_valid": False
    },
    "multi_goal": {
        "description": "Multiple independent goals with synergistic relationships",
        "goals": [
            {
                "id": "goal-performance",
                "title": "Performance Optimization Goal",
                "priority": "high",
                "relationship_to": "goal-security",
                "relationship_type": "synergistic"
            },
            {
                "id": "goal-security",
                "title": "Security Hardening Goal",
                "priority": "critical",
                "relationship_to": "goal-performance",
                "relationship_type": "synergistic"
            },
            {
                "id": "goal-monitoring",
                "title": "Monitoring Setup Goal",
                "priority": "normal",
                "relationship_to": "goal-performance",
                "relationship_type": "reinforces"
            }
        ],
        "tasks": [
            {"id": "profiling", "goal_id": "goal-performance", "title": "Profile application bottlenecks", "blocked_by": []},
            {"id": "caching", "goal_id": "goal-performance", "title": "Implement caching layer", "blocked_by": ["profiling"]},
            {"id": "security-audit", "goal_id": "goal-security", "title": "Conduct security audit", "blocked_by": []},
            {"id": "rate-limiting", "goal_id": "goal-security", "title": "Add rate limiting", "blocked_by": ["security-audit"]},
            {"id": "metrics", "goal_id": "goal-monitoring", "title": "Add metrics collection", "blocked_by": []},
            {"id": "alerts", "goal_id": "goal-monitoring", "title": "Configure alerting", "blocked_by": ["metrics"]}
        ]
    },
    "priority_override": {
        "description": "DAG with priority override commands",
        "initial_order": [
            {"id": "task-a", "priority": "normal"},
            {"id": "task-b", "priority": "normal"},
            {"id": "task-c", "priority": "normal"}
        ],
        "override_commands": [
            "do task-a before task-b",
            "make task-c critical priority"
        ],
        "final_order": ["task-c", "task-a", "task-b"]
    }
}

# =============================================================================
# PII Test Data (supplement to pii_samples.json)
# =============================================================================

PII_TEST_DATA = {
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

# =============================================================================
# Delegation Context Data
# =============================================================================

DELEGATION_CONTEXT = {
    "sample_context": {
        "user_message": "Implement OAuth authentication",
        "user_id": "user-123",
        "personal_memory": {
            "preferences": {"language": "python", "framework": "fastapi"},
            "history": ["previous task 1", "previous task 2"]
        },
        "available_agents": ["jochi", "temüjin", "ögedei", "chagatai", "tolui"]
    },
    "sample_result": {
        "task_id": "550e8400-e29b-41d4-a716-446655440001",
        "assigned_to": "jochi",
        "task_type": "code",
        "estimated_duration_seconds": 300,
        "status": "delegated"
    }
}

# =============================================================================
# Health Check Data
# =============================================================================

HEALTH_CHECK_DATA = {
    "healthy": {
        "status": "healthy",
        "neo4j_connected": True,
        "server_time": "2025-01-01T12:00:00.000Z",
        "rate_limit_ok": True,
        "agents": {
            "kublai": "active",
            "jochi": "active",
            "temüjin": "active"
        }
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
        "server_time": "2025-01-01T12:00:00.000Z"
    },
    "degraded": {
        "status": "degraded",
        "neo4j_connected": True,
        "server_time": "2025-01-01T12:00:00.000Z",
        "issues": ["Agent temüjin is stale"]
    }
}

# =============================================================================
# Failover Scenarios
# =============================================================================

FAILOVER_SCENARIOS = {
    "kublai_heartbeat_missed": {
        "agent": "kublai",
        "missed_heartbeats": 3,
        "threshold": 3,
        "should_activate": True,
        "failover_agent": "ögedei"
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
            "jochi": "jochi",
            "temüjin": "temüjin"
        }
    }
}

# =============================================================================
# Rate Limiting Data
# =============================================================================

RATE_LIMIT_DATA = {
    "agent": "jochi",
    "operation": "claim_task",
    "count": 10,
    "hour": 12,
    "date": "2025-01-01",
    "max_limit": 100,
    "window_seconds": 3600
}

# =============================================================================
# Intent Window Data
# =============================================================================

INTENT_WINDOW_MESSAGES = [
    {"content": "Fix the authentication bug", "timestamp": 1.0},
    {"content": "Update the API documentation", "timestamp": 2.0},
    {"content": "Add unit tests for the new feature", "timestamp": 3.0},
    {"content": "Review pull request #123", "timestamp": 4.0},
    {"content": "Deploy to staging", "timestamp": 5.0}
]

INTENT_WINDOW_CONFIG = {
    "window_duration_ms": 2000,
    "max_batch_size": 10,
    "enable_threading": True
}

# =============================================================================
# Priority Command Samples
# =============================================================================

PRIORITY_COMMAND_SAMPLES = {
    "do_X_before_Y": "do the authentication work before the UI design",
    "do_X_first": "do the backend API first",
    "whats_the_plan": "what's the plan for the user authentication feature?",
    "sync_from_notion": "sync tasks from notion",
    "priority_override": "make this critical priority",
    "add_dependency": "add dependency between task-a and task-b",
    "remove_dependency": "remove the dependency on task-c"
}

# =============================================================================
# Notion Sync Data
# =============================================================================

NOTION_TASK_DATA = {
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

NOTION_DATABASE_RESPONSE = {
    "object": "list",
    "results": [],
    "next_cursor": None,
    "has_more": False
}

# =============================================================================
# Performance Targets
# =============================================================================

PERFORMANCE_TARGETS = {
    "p50_latency_ms": 100,
    "p95_latency_ms": 500,
    "p99_latency_ms": 1000,
    "max_concurrent_operations": 100,
    "throughput_per_second": 50
}

LARGE_DAG_CONFIG = {
    "task_counts": [10, 50, 100, 500],
    "branching_factors": [1, 2, 3, 5],
    "dependency_density": [0.1, 0.3, 0.5]
}

# =============================================================================
# Chaos Test Scenarios
# =============================================================================

CHAOS_SCENARIOS = {
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

CORRUPTION_SCENARIOS = {
    "invalid_status": {
        "task_id": "550e8400-e29b-41d4-a716-446655440001",
        "status": "invalid_status_value"
    },
    "orphaned_dependencies": {
        "task_id": "550e8400-e29b-41d4-a716-446655440001",
        "blocked_by": ["550e8400-e29b-41d4-a716-446655440999"],
        "blocking_tasks_exist": False
    },
    "duplicate_ids": {
        "id": "550e8400-e29b-41d4-a716-446655440001",
        "duplicate_count": 3
    }
}

# =============================================================================
# Semantic Similarity Vectors
# =============================================================================

SEMANTIC_SIMILARITY_VECTORS = {
    "identical": ([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]),
    "orthogonal": ([1.0, 0.0, 0.0], [0.0, 1.0, 0.0]),
    "similar": ([1.0, 0.0, 0.0], [0.9, 0.1, 0.0]),
    "opposite": ([1.0, 0.0, 0.0], [-1.0, 0.0, 0.0]),
    "high_similarity": ([0.8, 0.2, 0.0], [0.7, 0.3, 0.0]),
    "low_similarity": ([0.9, 0.1, 0.0], [0.1, 0.9, 0.0])
}

# =============================================================================
# Export All
# =============================================================================

# =============================================================================
# Faker-Based Test Data Generators
# =============================================================================

try:
    from faker import Faker

    fake = Faker()

    class TestDataGenerator:
        """Generates realistic test data for Kurultai scenarios."""

        TASK_TYPES = ["code", "research", "writing", "analysis", "security", "ops"]
        TASK_STATUSES = ["pending", "in_progress", "completed", "failed", "blocked"]
        TASK_PRIORITIES = ["low", "normal", "high", "critical"]
        AGENT_IDS = ["kublai", "mongke", "chagatai", "temujin", "jochi", "ogedei"]

        @staticmethod
        def simple_task() -> Dict[str, Any]:
            """Single task with no dependencies."""
            return {
                "id": fake.uuid4(),
                "title": fake.sentence(),
                "description": fake.paragraph(),
                "type": random.choice(TestDataGenerator.TASK_TYPES),
                "complexity": random.uniform(0.1, 0.4),
                "status": "pending",
                "priority": random.choice(TestDataGenerator.TASK_PRIORITIES),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

        @staticmethod
        def complex_dag(
            num_tasks: int = 50, dependency_ratio: float = 0.3
        ) -> List[Dict[str, Any]]:
            """Generate tasks with dependencies forming a valid DAG.

            Args:
                num_tasks: Number of tasks to generate
                dependency_ratio: Ratio of dependencies per task (0.0 to 1.0)

            Returns:
                List of task dictionaries with valid DAG structure (no cycles)
            """
            import random

            tasks = [TestDataGenerator.simple_task() for _ in range(num_tasks)]

            # Add dependencies ensuring no cycles
            for i in range(num_tasks):
                # Can only depend on tasks with lower index
                if i > 0:
                    max_deps = min(int(i * dependency_ratio), i)
                    num_deps = random.randint(0, max_deps)
                    if num_deps > 0:
                        # Select random tasks from earlier in the list
                        dep_indices = random.sample(range(i), min(num_deps, i))
                        tasks[i]["dependencies"] = [
                            tasks[idx]["id"] for idx in dep_indices
                        ]
                        tasks[i]["blocked_by"] = tasks[i].get("dependencies", [])

            return tasks

        @staticmethod
        def multi_agent_scenario() -> Dict[str, Any]:
            """Scenario requiring 3+ agents."""
            return {
                "title": "Build a REST API with documentation",
                "phases": [
                    {"agent": "temujin", "task": "Implement API endpoints"},
                    {"agent": "chagatai", "task": "Write API documentation"},
                    {"agent": "jochi", "task": "Security review"},
                ],
                "expected_duration_seconds": random.randint(60, 300),
            }

        @staticmethod
        def user_message() -> str:
            """Generate a realistic user message."""
            templates = [
                f"{fake.sentence()} Please {fake.verb()} the {fake.noun()}.",
                f"Can you help me {fake.verb()} {fake.word()}?",
                f"I need to {fake.verb()} {fake.sentence()}",
                f"Implement {fake.word()} with {fake.word()}",
            ]
            return random.choice(templates)

        @staticmethod
        def agent_heartbeat(agent_id: Optional[str] = None) -> Dict[str, Any]:
            """Generate agent heartbeat data."""
            return {
                "agent_id": agent_id or random.choice(TestDataGenerator.AGENT_IDS),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": random.choice(["healthy", "stale", "unavailable"]),
                "tasks_completed": random.randint(0, 100),
                "tasks_failed": random.randint(0, 10),
            }

        @staticmethod
        def notification(
            target_agent: Optional[str] = None, source_agent: Optional[str] = None
        ) -> Dict[str, Any]:
            """Generate a notification."""
            return {
                "notification_id": fake.uuid4(),
                "target_agent": target_agent or random.choice(
                    TestDataGenerator.AGENT_IDS[1:]  # Not kublai
                ),
                "source_agent": source_agent or random.choice(TestDataGenerator.AGENT_IDS),
                "type": random.choice(
                    ["task_delegated", "task_completed", "task_failed", "agent_status_change"]
                ),
                "message": fake.sentence(),
                "read": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

        @staticmethod
        def batch_tasks(count: int = 10) -> List[Dict[str, Any]]:
            """Generate a batch of tasks."""
            return [TestDataGenerator.simple_task() for _ in range(count)]

        @staticmethod
        def workflow_trace(steps: int = 5) -> List[Dict[str, Any]]:
            """Generate a workflow trace with multiple steps."""
            trace = []
            for i in range(steps):
                trace.append(
                    {
                        "step": i + 1,
                        "agent": random.choice(TestDataGenerator.AGENT_IDS),
                        "action": random.choice(
                            ["received", "processed", "delegated", "completed"]
                        ),
                        "timestamp": (
                            datetime.now(timezone.utc) + timedelta(seconds=i * 5)
                        ).isoformat(),
                        "details": fake.sentence(),
                    }
                )
            return trace

except ImportError:
    # Faker not installed, provide stub
    class TestDataGenerator:
        """Stub when faker is not installed."""

        @staticmethod
        def simple_task() -> Dict[str, Any]:
            return {"id": "stub-id", "title": "Stub task"}

    import warnings

    warnings.warn(
        "faker not installed. Install with: pip install faker. "
        "Using stub TestDataGenerator."
    )


__all__ = [
    # Task data
    'SAMPLE_TASK_DATA',
    'SAMPLE_TASKS',
    'PENDING_TASKS',
    'IN_PROGRESS_TASKS',
    'COMPLETED_TASKS',
    'FAILED_TASKS',
    'BLOCKED_TASKS',
    # Agent data
    'AGENT_CONFIGS',
    'AGENT_STATES',
    'AGENT_ROUTING',
    # Neo4j data
    'NEO4J_QUERY_RESULTS',
    'NEO4J_NODES',
    'NEO4J_RELATIONSHIPS',
    # Notification data
    'SAMPLE_NOTIFICATIONS',
    'NOTIFICATION_LIST',
    # DAG structures
    'DAG_STRUCTURES',
    # PII data
    'PII_TEST_DATA',
    # Context data
    'DELEGATION_CONTEXT',
    'HEALTH_CHECK_DATA',
    'FAILOVER_SCENARIOS',
    'RATE_LIMIT_DATA',
    'INTENT_WINDOW_MESSAGES',
    'INTENT_WINDOW_CONFIG',
    'PRIORITY_COMMAND_SAMPLES',
    'NOTION_TASK_DATA',
    'NOTION_DATABASE_RESPONSE',
    'PERFORMANCE_TARGETS',
    'LARGE_DAG_CONFIG',
    'CHAOS_SCENARIOS',
    'CORRUPTION_SCENARIOS',
    'SEMANTIC_SIMILARITY_VECTORS',
    # Faker-based generators
    'TestDataGenerator',
    'fake',
]
