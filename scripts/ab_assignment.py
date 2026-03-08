#!/usr/bin/env python3
"""
A/B Test Assignment Logic for Kublai Prompt Optimization

Deterministic 50/50 assignment of tasks to control/treatment groups
based on SHA-256 hash of task_id.

Usage:
    from ab_assignment import get_ab_group, assign_ab_group_to_task

    # Get group for a task
    group = get_ab_group("task-12345678")  # Returns 'control' or 'treatment'

    # Assign during task creation
    task_data = {"task_id": "...", "title": "..."}
    assign_ab_group_to_task(task_data)
"""

import hashlib
from typing import Literal, Dict, Any

# Type aliases
ABGroup = Literal['control', 'treatment']


def get_ab_group(task_id: str) -> ABGroup:
    """
    Assign task to A/B test group based on hash of task_id.

    This ensures:
    - Deterministic: Same task_id always maps to same group
    - Even distribution: Expected 50/50 split (with ~1% variance)
    - Persistent: Survives retries and system restarts
    - Audit-able: Assignment is reproducible

    Args:
        task_id: Unique task identifier (UUID or string)

    Returns:
        'control' or 'treatment'

    Example:
        >>> get_ab_group("abc123")
        'treatment'
        >>> get_ab_group("abc123")  # Same input = same output
        'treatment'
        >>> get_ab_group("xyz789")
        'control'
    """
    # SHA-256 hash of task_id
    hash_bytes = hashlib.sha256(task_id.encode('utf-8')).digest()

    # Convert first 8 bytes to integer
    hash_int = int.from_bytes(hash_bytes[:8], byteorder='big')

    # Modulo 2 for 50/50 split
    # Even hash -> treatment, Odd hash -> control
    return 'treatment' if hash_int % 2 == 0 else 'control'


def get_ab_group_with_seed(task_id: str, seed: int = 0) -> ABGroup:
    """
    Alternative assignment with custom seed (for re-running tests).

    Use this for testing or when you need to re-balance groups
    without changing task_id.

    Args:
        task_id: Unique task identifier
        seed: Seed value to modify hash (0 for production)

    Returns:
        'control' or 'treatment'
    """
    combined = f"{task_id}:{seed}".encode('utf-8')
    hash_bytes = hashlib.sha256(combined).digest()
    hash_int = int.from_bytes(hash_bytes[:8], byteorder='big')
    return 'treatment' if hash_int % 2 == 0 else 'control'


def assign_ab_group_to_task(task_data: Dict[str, Any]) -> str:
    """
    Assign A/B test group to a task dictionary.

    Adds 'ab_test_group' key to the task data in-place.

    Args:
        task_data: Dictionary with at least 'task_id' key

    Returns:
        The assigned group ('control' or 'treatment')

    Example:
        >>> task = {"task_id": "abc123", "title": "Test task"}
        >>> group = assign_ab_group_to_task(task)
        >>> print(task["ab_test_group"])
        'treatment'
    """
    task_id = task_data.get('task_id')
    if not task_id:
        raise ValueError("task_data must contain 'task_id' key")

    group = get_ab_group(task_id)
    task_data['ab_test_group'] = group
    return group


def should_apply_optimization(task_id: str, feature_enabled: bool = True) -> bool:
    """
    Determine if optimization should be applied to a task.

    Combines feature flag with A/B group assignment.

    Args:
        task_id: Unique task identifier
        feature_enabled: Master feature flag for optimization

    Returns:
        True if optimization should be applied, False otherwise

    Example:
        >>> should_apply_optimization("task1", feature_enabled=False)
        False
        >>> should_apply_optimization("task2", feature_enabled=True)
        True  # or False, depending on A/B assignment
    """
    if not feature_enabled:
        return False

    return get_ab_group(task_id) == 'treatment'


def get_group_split_percent(task_ids: list[str]) -> Dict[ABGroup, float]:
    """
    Calculate actual group distribution for a list of task IDs.

    Useful for verifying group balance before running a test.

    Args:
        task_ids: List of task identifiers

    Returns:
        Dict with 'control' and 'treatment' percentages

    Example:
        >>> ids = ["task1", "task2", "task3", "task4"]
        >>> get_group_split_percent(ids)
        {'control': 50.0, 'treatment': 50.0}
    """
    if not task_ids:
        return {'control': 0.0, 'treatment': 0.0}

    counts = {'control': 0, 'treatment': 0}
    for tid in task_ids:
        group = get_ab_group(tid)
        counts[group] += 1

    total = len(task_ids)
    return {
        'control': round(counts['control'] * 100.0 / total, 2),
        'treatment': round(counts['treatment'] * 100.0 / total, 2)
    }


# =============================================================================
# Neo4j Integration Helper
# =============================================================================

def create_ab_group_query(task_id: str) -> tuple[str, dict]:
    """
    Generate Neo4j query parameters for setting ab_test_group.

    Returns (query, params) tuple for use with neo4j.TaskTracker.

    Example:
        >>> query, params = create_ab_group_query("task123")
        >>> session.run(query, **params)
    """
    group = get_ab_group(task_id)
    query = """
        MATCH (t:Task {task_id: $task_id})
        SET t.ab_test_group = $ab_test_group
        RETURN t.ab_test_group AS group
    """
    params = {'task_id': task_id, 'ab_test_group': group}
    return query, params


# =============================================================================
# CLI for testing
# =============================================================================

if __name__ == '__main__':
    import sys

    # Test mode: simulate assignment for N tasks
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 1000

        # Generate test task IDs
        test_ids = [f"test-task-{i}" for i in range(n)]

        # Calculate distribution
        counts = {'control': 0, 'treatment': 0}
        for tid in test_ids:
            group = get_ab_group(tid)
            counts[group] += 1

        print(f"A/B Assignment Test (n={n})")
        print(f"  Control:   {counts['control']} ({counts['control']*100.0/n:.2f}%)")
        print(f"  Treatment: {counts['treatment']} ({counts['treatment']*100.0/n:.2f}%)")
        print(f"  Imbalance: {abs(counts['control'] - counts['treatment'])*100.0/n:.2f}%")

        # Verify determinism
        sample_ids = test_ids[:10]
        first_pass = [get_ab_group(tid) for tid in sample_ids]
        second_pass = [get_ab_group(tid) for tid in sample_ids]
        assert first_pass == second_pass, "Determinism check failed!"
        print("  Determinism: OK (same IDs map to same groups)")

    # Individual lookup
    elif len(sys.argv) > 1:
        task_id = sys.argv[1]
        group = get_ab_group(task_id)
        print(f"Task '{task_id}' -> {group}")

    # Show usage
    else:
        print("Usage:")
        print("  python ab_assignment.py test [n]     # Test distribution with n samples")
        print("  python ab_assignment.py <task_id>    # Get group for specific task")
        print("\nExample:")
        print("  python ab_assignment.py test 10000")
        print("  python ab_assignment.py abc-123-def")
