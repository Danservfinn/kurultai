#!/usr/bin/env python3
"""
Monitoring Utilities - Shared queue depth and health check functions.

Consolidates duplicate monitoring functions from:
- agent-dashboard.py
- health_dashboard.py
- pipeline_health.py
- gate-metrics.py

Usage:
    from monitoring_utils import get_queue_depths, get_all_queue_depths

    depths = get_queue_depths("temujin")
    all_depths = get_all_queue_depths()
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kurultai_paths import AGENTS_DIR, VALID_AGENTS


def get_queue_depths(agent: str) -> Dict[str, int]:
    """Get pending, executing, done counts for an agent.

    Args:
        agent: Agent name (e.g., "temujin", "mongke")

    Returns:
        Dict with 'pending', 'executing', 'done' counts

    Example:
        depths = get_queue_depths("temujin")
        # {'pending': 5, 'executing': 1, 'done': 23}
    """
    tasks_dir = AGENTS_DIR / agent / "tasks"
    if not tasks_dir.exists():
        return {'pending': 0, 'executing': 0, 'done': 0}

    # Pending: .md files that aren't executing or done
    pending = len([
        f for f in tasks_dir.glob("*.md")
        if not f.name.endswith(('.executing.md', '.done.md', '.failed.md'))
    ])

    # Executing: .executing.md files
    executing = len(list(tasks_dir.glob("*.executing.md")))

    # Done: .done.md files (includes .failed.done.md)
    done = len(list(tasks_dir.glob("*.done.md")))

    return {'pending': pending, 'executing': executing, 'done': done}


def get_all_queue_depths() -> Dict[str, Dict[str, int]]:
    """Get queue depths for all dispatch agents.

    Returns:
        Dict mapping agent name to queue depth dict

    Example:
        all_depths = get_all_queue_depths()
        # {'temujin': {'pending': 5, 'executing': 1, 'done': 23}, ...}
    """
    depths = {}
    for agent in VALID_AGENTS:
        if agent != 'kublai':  # kublai is router, not a worker
            depths[agent] = get_queue_depths(agent)
    return depths


def get_total_queue_depth() -> Dict[str, int]:
    """Get total queue depths across all agents.

    Returns:
        Dict with total 'pending', 'executing', 'done' counts
    """
    all_depths = get_all_queue_depths()

    totals = {'pending': 0, 'executing': 0, 'done': 0}
    for depths in all_depths.values():
        for key in totals:
            totals[key] += depths.get(key, 0)

    return totals


def get_stale_tasks(agent: str, max_age_hours: int = 2) -> List[Dict[str, any]]:
    """Find tasks that have been executing for too long.

    Args:
        agent: Agent name
        max_age_hours: Maximum allowed execution time

    Returns:
        List of stale task info dicts
    """
    tasks_dir = AGENTS_DIR / agent / "tasks"
    if not tasks_dir.exists():
        return []

    cutoff = datetime.now() - timedelta(hours=max_age_hours)
    stale = []

    for task_file in tasks_dir.glob("*.executing.md"):
        stat = task_file.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime)

        if mtime < cutoff:
            stale.append({
                'file': str(task_file),
                'agent': agent,
                'age_hours': (datetime.now() - mtime).total_seconds() / 3600,
                'modified': mtime.isoformat()
            })

    return stale


def get_all_stale_tasks(max_age_hours: int = 2) -> List[Dict[str, any]]:
    """Find all stale executing tasks across agents.

    Args:
        max_age_hours: Maximum allowed execution time

    Returns:
        List of stale task info dicts
    """
    all_stale = []
    for agent in VALID_AGENTS:
        if agent != 'kublai':
            all_stale.extend(get_stale_tasks(agent, max_age_hours))
    return all_stale


def get_agent_health(agent: str) -> Dict[str, any]:
    """Get health status for a single agent.

    Args:
        agent: Agent name

    Returns:
        Dict with health info
    """
    depths = get_queue_depths(agent)
    stale = get_stale_tasks(agent)

    # Determine health status
    status = 'healthy'
    if depths['executing'] > 3:
        status = 'overloaded'
    elif len(stale) > 0:
        status = 'stale_tasks'
    elif depths['pending'] > 20:
        status = 'backlog'

    return {
        'agent': agent,
        'status': status,
        'queue': depths,
        'stale_count': len(stale),
        'last_checked': datetime.now().isoformat()
    }


def get_system_health() -> Dict[str, any]:
    """Get overall system health summary.

    Returns:
        Dict with system health info
    """
    all_depths = get_all_queue_depths()
    all_stale = get_all_stale_tasks()
    totals = get_total_queue_depth()

    # Determine overall status
    status = 'healthy'
    if len(all_stale) > 3:
        status = 'degraded'
    elif totals['pending'] > 50:
        status = 'backlog'
    elif totals['executing'] > 4:
        status = 'busy'

    # Get individual agent statuses
    agent_health = {}
    for agent, depths in all_depths.items():
        agent_health[agent] = get_agent_health(agent)['status']

    return {
        'status': status,
        'queue_totals': totals,
        'stale_count': len(all_stale),
        'agents': agent_health,
        'last_checked': datetime.now().isoformat()
    }


def format_queue_summary(depths: Dict[str, int], width: int = 20) -> str:
    """Format queue depths as a summary string.

    Args:
        depths: Queue depth dict
        width: Total width for formatting

    Returns:
        Formatted string
    """
    pending = depths.get('pending', 0)
    executing = depths.get('executing', 0)
    done = depths.get('done', 0)

    return f"P:{pending:3d} E:{executing:2d} D:{done:4d}"


def get_recent_completions(hours: int = 24) -> Dict[str, int]:
    """Get task completion counts by agent for recent period.

    Args:
        hours: Hours to look back

    Returns:
        Dict mapping agent to completion count
    """
    cutoff = datetime.now() - timedelta(hours=hours)
    completions = {}

    for agent in VALID_AGENTS:
        if agent == 'kublai':
            continue

        tasks_dir = AGENTS_DIR / agent / "tasks"
        if not tasks_dir.exists():
            completions[agent] = 0
            continue

        count = 0
        for task_file in tasks_dir.glob("*.done.md"):
            stat = task_file.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime)
            if mtime >= cutoff:
                count += 1

        completions[agent] = count

    return completions
