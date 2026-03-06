#!/usr/bin/env python3
"""
Load-Balancing Patch for task-router.py

This module provides queue-depth-aware load balancing for the task router.
Drop this into task-router.py or import it as a separate module.

Usage:
    from load_balancer import get_agent_queue_depth, should_rebalance, _log_rebalance_decision
"""

import os
import json
from datetime import datetime

# ============================================================
# AGENT CAPABILITY MATRIX
# ============================================================
AGENT_CAPABILITIES = {
    "temujin": {
        "primary": ["code", "build", "fix", "deploy", "apis"],
        "secondary": ["infrastructure", "automation"],
        "can_accept_from": [],  # No overflow TO temujin
        "max_queue_depth": 5,   # Trigger rebalancing at 5+ pending
    },

    "mongke": {
        "primary": ["research", "analysis", "discovery"],
        "secondary": [],
        "can_accept_from": ["temujin"],  # Can help with discovery tasks
        "max_queue_depth": 10,
    },

    "chagatai": {
        "primary": ["writing", "documentation", "content"],
        "secondary": [],
        "can_accept_from": [],
        "max_queue_depth": 8,
    },

    "jochi": {
        "primary": ["testing", "security", "validation", "review"],
        "secondary": ["code review"],  # Can review code that temujin wrote
        "can_accept_from": ["temujin"],
        "max_queue_depth": 8,
    },

    "ogedei": {
        "primary": ["ops", "monitoring", "infrastructure"],
        "secondary": ["automation"],
        "can_accept_from": ["temujin"],  # Can handle infrastructure/deployment
        "max_queue_depth": 6,
    },

    "kublai": {
        "primary": ["coordination", "triage", "system-wide"],
        "secondary": [],
        "can_accept_from": [],  # Lead — doesn't take overflow
        "max_queue_depth": 3,
    },
}

# Overflow routing rules: (primary_agent, task_keywords) -> (overflow_agent, fallback_agent)
OVERFLOW_ROUTING = {
    ("temujin", "infrastructure"): ("ogedei", "jochi"),  # Build infrastructure → ogedei, fallback jochi
    ("temujin", "code review"): ("jochi", None),         # Code review → jochi, no fallback
    ("temujin", "api discover"): ("mongke", None),       # API discovery → mongke
    ("temujin", "testing"): ("jochi", None),             # Testing tasks → jochi
    ("temujin", "deploy"): ("ogedei", None),             # Deployment → ogedei
}

REBALANCE_LOG = "/Users/kublai/.openclaw/agents/main/logs/routing-rebalanced.jsonl"

# ============================================================
# QUEUE DEPTH CHECKER
# ============================================================

def get_agent_queue_depth(agent, check_neo4j=True):
    """
    Count pending tasks for an agent (filesystem + optionally Neo4j).

    Args:
        agent: Agent name (temujin, mongke, etc.)
        check_neo4j: If True, include Neo4j PENDING count

    Returns:
        {"agent": agent, "filesystem": int, "neo4j": int, "total": int}
    """
    base = "/Users/kublai/.openclaw/agents"
    task_dir = f"{base}/{agent}/tasks"
    fs_count = 0

    # Count filesystem tasks
    if os.path.isdir(task_dir):
        for fname in os.listdir(task_dir):
            # Skip completed/executing files
            if not any(suffix in fname for suffix in [".executing", ".completed", ".done"]):
                fs_count += 1

    neo4j_count = 0
    if check_neo4j:
        try:
            from neo4j_task_tracker import get_tracker
            tracker = get_tracker()
            # Count PENDING tasks in Neo4j for this agent
            with tracker.driver.session() as session:
                result = session.run(
                    "MATCH (t:Task {agent: $agent, status: 'PENDING'}) RETURN count(t) AS cnt",
                    agent=agent
                )
                record = result.single()
                neo4j_count = record["cnt"] if record else 0
        except Exception:
            neo4j_count = 0  # Graceful degradation if Neo4j unavailable

    return {
        "agent": agent,
        "filesystem": fs_count,
        "neo4j": neo4j_count,
        "total": max(fs_count, neo4j_count)  # Use max to avoid double-counting
    }


# ============================================================
# REBALANCING LOGIC
# ============================================================

def should_rebalance(primary_agent, task_keywords):
    """
    Check if primary agent is overloaded + task can be handled elsewhere.

    Args:
        primary_agent: Result from LLM classification (e.g., "temujin")
        task_keywords: Task text (to match against OVERFLOW_ROUTING)

    Returns:
        (should_rebalance: bool, target_agent: str or None, reason: str)
    """
    if primary_agent not in AGENT_CAPABILITIES:
        return False, None, "unknown agent"

    # Check if primary agent is overloaded
    depth = get_agent_queue_depth(primary_agent, check_neo4j=False)
    max_allowed = AGENT_CAPABILITIES[primary_agent]["max_queue_depth"]

    if depth["total"] < max_allowed:
        return False, None, "primary has capacity"

    # Primary is overloaded — check if this task can overflow
    task_lower = task_keywords.lower()

    for (primary, keywords_pattern), (overflow_agent, fallback_agent) in OVERFLOW_ROUTING.items():
        if primary == primary_agent and keywords_pattern in task_lower:
            # Found overflow rule — check if overflow agent has capacity
            overflow_depth = get_agent_queue_depth(overflow_agent, check_neo4j=False)
            overflow_max = AGENT_CAPABILITIES[overflow_agent]["max_queue_depth"]

            if overflow_depth["total"] < overflow_max:
                return True, overflow_agent, f"overflow: {primary} ({depth['total']}/{max_allowed}) → {overflow_agent} ({overflow_depth['total']}/{overflow_max})"

            # Overflow agent also full, try fallback
            if fallback_agent:
                fallback_depth = get_agent_queue_depth(fallback_agent, check_neo4j=False)
                fallback_max = AGENT_CAPABILITIES[fallback_agent]["max_queue_depth"]
                if fallback_depth["total"] < fallback_max:
                    return True, fallback_agent, f"cascade: {overflow_agent} full ({overflow_depth['total']}/{overflow_max}) → {fallback_agent} ({fallback_depth['total']}/{fallback_max})"

    return False, None, "no overflow route available"


# ============================================================
# LOGGING
# ============================================================

def _log_rebalance_decision(rebalance_decision, classification, result):
    """
    Log load-balanced routing decision to routing-rebalanced.jsonl.

    Entry format:
    {
        "ts": "2026-03-04T18:30:00.123456",
        "task": "Build API endpoint",
        "primary_agent": "temujin",
        "overflow_to": "jochi",
        "reason": "overflow: temujin full (8/5) → jochi",
        "primary_queue_depth": 8,
        "overflow_queue_depth": 2,
        "task_file": "path/to/task.md",
        "classification_method": "llm"
    }
    """
    try:
        primary = rebalance_decision["original"]
        overflow = rebalance_decision["overflow_to"]

        primary_depth = get_agent_queue_depth(primary, check_neo4j=False)
        overflow_depth = get_agent_queue_depth(overflow, check_neo4j=False)

        entry = {
            "ts": datetime.now().isoformat(),
            "task": classification.get("task", "")[:100],
            "primary_agent": primary,
            "overflow_to": overflow,
            "reason": rebalance_decision["reason"],
            "primary_queue_depth": primary_depth["total"],
            "overflow_queue_depth": overflow_depth["total"],
            "task_file": result.get("task_file", ""),
            "classification_method": classification.get("method", "unknown"),
        }

        os.makedirs(os.path.dirname(REBALANCE_LOG), exist_ok=True)
        with open(REBALANCE_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Never let logging break routing


# ============================================================
# INTEGRATION EXAMPLE
# ============================================================

def route_task_with_load_balancing(message, priority="normal", classify_fn=None, route_fn=None):
    """
    Example integration of load balancing into route_task().

    Args:
        message: Task text
        priority: Task priority (high/normal/low)
        classify_fn: Callable that takes message and returns classification dict
        route_fn: Callable that takes (agent, message, priority) and returns result

    This is a reference implementation. In practice, add this logic to task-router.py's
    route_task() function directly.
    """
    if not classify_fn or not route_fn:
        raise ValueError("classify_fn and route_fn must be provided")

    # Step 1: Classify task
    classification = classify_fn(message)
    destination = classification['destination']
    rebalance_decision = None

    # Step 2: Check load balance (only if not going to subagent)
    if destination != 'subagent':
        should_rebalance_flag, overflow_agent, reason = should_rebalance(destination, message)
        if should_rebalance_flag:
            rebalance_decision = {
                "original": destination,
                "overflow_to": overflow_agent,
                "reason": reason,
            }
            destination = overflow_agent  # Update routing target
            classification['rebalanced'] = True

    # Step 3: Route
    if destination == 'subagent':
        result = route_fn(destination, message, priority)
    else:
        result = route_fn(destination, message, priority)

    # Step 4: Log rebalance decision (if happened)
    if rebalance_decision:
        _log_rebalance_decision(rebalance_decision, classification, result)

    return result, rebalance_decision


if __name__ == "__main__":
    # Quick test
    print("=== Load Balancer Module ===\n")

    # Check queue depths
    for agent in ["temujin", "mongke", "jochi", "ogedei", "chagatai", "kublai"]:
        depth = get_agent_queue_depth(agent, check_neo4j=False)
        max_depth = AGENT_CAPABILITIES[agent]["max_queue_depth"]
        status = "OVERLOADED" if depth["total"] >= max_depth else "OK"
        print(f"{agent:10} {depth['total']:2}/{max_depth} {status}")

    print("\n=== Testing should_rebalance() ===\n")

    # Test rebalancing
    test_cases = [
        ("temujin", "Build REST API"),
        ("temujin", "Build infrastructure for auth"),
        ("temujin", "Write code review"),
        ("mongke", "Research competitors"),
    ]

    for agent, task in test_cases:
        should, target, reason = should_rebalance(agent, task)
        print(f"{agent} + '{task[:40]}' → {should}")
        if should:
            print(f"   Overflow to: {target} ({reason})")
