#!/usr/bin/env python3
"""
neo4j_v2_events.py — Event emission for task lifecycle tracking.

Append-only Event nodes in Neo4j with [:ABOUT]->Task relationships.
Incrementally updates AgentMetrics nodes for dashboard queries.

Non-blocking: all exceptions are caught and logged. Observability
never blocks task execution.

Usage:
    from neo4j_v2_events import emit_event

    emit_event(driver, "TASK_COMPLETED", "task-123", "mongke",
               executor_id="exec-abc", duration_s=120.5)
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

EVENT_TYPES = frozenset({
    "TASK_CLAIMED",
    "TASK_EXECUTING",
    "TASK_COMPLETED",
    "TASK_FAILED",
    "TASK_FAILED_PERMANENT",
    "SESSION_RESET",
    "MODEL_FALLBACK",
    "MODEL_FALLBACK_SUCCESS",
    "MODEL_FALLBACK_FAILED",
    "STALL_DETECTED",
    "LEASE_RENEWED",
    "ORPHAN_RECOVERED",
    "FALSE_COMPLETION_BLOCKED",
    "EXECUTOR_STARTED",
    "EXECUTOR_STOPPED",
    # Deploy pipeline events
    "WORKTREE_CREATED",
    "WORKTREE_CLEANED",
    "PR_CREATED",
    "PR_MERGED",
    "PR_FAILED",
    "DEPLOY_BLOCKED",
    "DEPLOY_STARTED",
    "DEPLOY_COMPLETED",
    "DEPLOY_FAILED",
    "HEALTH_CHECK_PASSED",
    "HEALTH_CHECK_FAILED",
    # Continuation events
    "TASK_CONTINUATION",
    # Delivery verification events
    "DELIVERY_VERIFIED",
    "DELIVERY_UNVERIFIED",
})

# Event types that update AgentMetrics counters
_COMPLETION_EVENTS = {"TASK_COMPLETED", "TASK_FAILED_PERMANENT"}
_FAILURE_EVENTS = {"TASK_FAILED", "TASK_FAILED_PERMANENT"}


def emit_event(
    driver,
    event_type: str,
    task_id: str,
    agent: str,
    executor_id: str = "",
    **kwargs,
) -> Optional[str]:
    """Emit an event to Neo4j. Non-blocking, swallows all exceptions.

    Creates:
      1. Event node with metadata
      2. [:ABOUT]->Task relationship (if task_id is non-empty)
      3. Incremental AgentMetrics update (for completion/failure events)

    Args:
        driver: Neo4j driver instance
        event_type: One of EVENT_TYPES
        task_id: Task this event relates to (empty string for system events)
        agent: Agent name (e.g. "mongke")
        executor_id: Executor instance ID
        **kwargs: Additional event metadata (duration_s, error_category, etc.)

    Returns:
        event_id on success, None on failure
    """
    if event_type not in EVENT_TYPES:
        logger.warning(f"Unknown event type: {event_type}")
        return None

    event_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat() + "Z"

    try:
        with driver.session() as session:
            session.execute_write(
                _write_event, event_id, event_type, task_id, agent,
                executor_id, now, kwargs
            )
        return event_id
    except Exception as e:
        logger.warning(f"emit_event failed ({event_type}, {task_id}): {e}")
        return None


def _write_event(tx, event_id, event_type, task_id, agent, executor_id, ts, extra):
    """Transaction function: create Event + relationship + update metrics."""

    # Build dynamic properties from kwargs
    extra_props = ""
    params = {
        "event_id": event_id,
        "event_type": event_type,
        "task_id": task_id,
        "agent": agent,
        "executor_id": executor_id,
        "ts": ts,
    }

    # Add known optional fields
    for key in ("duration_s", "error_category", "error_msg", "model",
                "fallback_model", "session_action", "reason",
                "claim_token", "claim_epoch", "output_lines",
                "bloat_reset", "drift_archived",
                "channel", "recipient"):
        if key in extra:
            params[key] = extra[key]
            extra_props += f", e.{key} = ${key}"

    # Create Event node
    cypher = f"""
    CREATE (e:Event {{
        event_id: $event_id,
        event_type: $event_type,
        task_id: $task_id,
        agent: $agent,
        executor_id: $executor_id,
        ts: datetime($ts)
    }})
    {extra_props.replace('e.', 'SET e.') if extra_props else ''}
    """

    # If we have a task_id, also create the [:ABOUT] relationship
    if task_id:
        cypher = f"""
        CREATE (e:Event {{
            event_id: $event_id,
            event_type: $event_type,
            task_id: $task_id,
            agent: $agent,
            executor_id: $executor_id,
            ts: datetime($ts)
        }})
        WITH e
        OPTIONAL MATCH (t:Task {{task_id: $task_id}})
        FOREACH (_ IN CASE WHEN t IS NOT NULL THEN [1] ELSE [] END |
            CREATE (e)-[:ABOUT]->(t)
        )
        """
        if extra_props:
            # Insert SET clause before WITH
            cypher = cypher.replace(
                "WITH e",
                f"SET {extra_props.lstrip(', ').replace('e.', 'e.')}\nWITH e"
            )

    tx.run(cypher, **params)

    # Update AgentMetrics for completion/failure events
    if agent and event_type in _COMPLETION_EVENTS:
        duration_s = extra.get("duration_s", 0)
        _update_metrics(tx, agent, event_type, duration_s)


def _update_metrics(tx, agent, event_type, duration_s):
    """Incrementally update AgentMetrics node."""
    if event_type == "TASK_COMPLETED":
        tx.run("""
        MERGE (m:AgentMetrics {agent: $agent})
        ON CREATE SET
            m.tasks_completed_24h = 1,
            m.tasks_failed_24h = 0,
            m.success_rate_24h = 1.0,
            m.avg_duration_s_24h = $duration_s,
            m.session_resets_24h = 0,
            m.last_updated = datetime()
        ON MATCH SET
            m.tasks_completed_24h = m.tasks_completed_24h + 1,
            m.avg_duration_s_24h = CASE WHEN m.tasks_completed_24h > 0
                THEN (m.avg_duration_s_24h * (m.tasks_completed_24h - 1) + $duration_s) / m.tasks_completed_24h
                ELSE $duration_s END,
            m.success_rate_24h = toFloat(m.tasks_completed_24h) / CASE WHEN m.tasks_completed_24h + m.tasks_failed_24h > 0 THEN m.tasks_completed_24h + m.tasks_failed_24h ELSE 1 END,
            m.last_updated = datetime()
        """, agent=agent, duration_s=duration_s)
    elif event_type == "TASK_FAILED_PERMANENT":
        tx.run("""
        MERGE (m:AgentMetrics {agent: $agent})
        ON CREATE SET
            m.tasks_completed_24h = 0,
            m.tasks_failed_24h = 1,
            m.success_rate_24h = 0.0,
            m.avg_duration_s_24h = 0,
            m.session_resets_24h = 0,
            m.last_updated = datetime()
        ON MATCH SET
            m.tasks_failed_24h = m.tasks_failed_24h + 1,
            m.success_rate_24h = toFloat(m.tasks_completed_24h) / CASE WHEN m.tasks_completed_24h + m.tasks_failed_24h > 0 THEN m.tasks_completed_24h + m.tasks_failed_24h ELSE 1 END,
            m.last_updated = datetime()
        """, agent=agent)


def emit_session_reset(driver, task_id, agent, executor_id="", **kwargs):
    """Convenience: emit SESSION_RESET and update session reset counter."""
    event_id = emit_event(driver, "SESSION_RESET", task_id, agent,
                          executor_id=executor_id, **kwargs)
    if event_id:
        try:
            with driver.session() as session:
                session.run("""
                MERGE (m:AgentMetrics {agent: $agent})
                ON CREATE SET m.session_resets_24h = 1, m.tasks_completed_24h = 0,
                    m.tasks_failed_24h = 0, m.success_rate_24h = 0.0,
                    m.avg_duration_s_24h = 0, m.last_updated = datetime()
                ON MATCH SET m.session_resets_24h = m.session_resets_24h + 1,
                    m.last_updated = datetime()
                """, agent=agent)
        except Exception as e:
            logger.warning(f"session_reset metrics update failed: {e}")
    return event_id
