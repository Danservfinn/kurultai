#!/usr/bin/env python3
"""
Squad Chat Events - System event definitions for agent lifecycle.

These events are automatically emitted by the task execution system
and can be subscribed to by other agents for coordination.

Usage:
    from squad_chat_events import emit_event, Events

    # Emit a lifecycle event
    await emit_event(agent_name, Events.AGENT_SPAWNED, {"task_id": "..."})
"""

from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime


class Events(str, Enum):
    """System event types for Squad Chat."""

    # Agent lifecycle
    AGENT_SPAWNED = "agent.spawned"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"
    AGENT_STALLED = "agent.stalled"
    AGENT_JOINED = "agent.joined"
    AGENT_LEFT = "agent.left"

    # Task lifecycle
    TASK_STARTED = "task.started"
    TASK_PROGRESS = "task.progress"
    TASK_CHECKPOINT = "task.checkpoint"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_BLOCKED = "task.blocked"
    TASK_ESCALATED = "task.escalated"

    # Communication
    MENTION = "mention"
    MESSAGE = "message"

    # System
    SYSTEM_ALERT = "system.alert"
    SYSTEM_HEALTH = "system.health"


# Event templates with required fields
EVENT_TEMPLATES = {
    Events.AGENT_SPAWNED: {
        "required": ["task_id"],
        "optional": ["skill_hint", "priority", "model"]
    },
    Events.AGENT_COMPLETED: {
        "required": ["task_id"],
        "optional": ["duration_s", "output_lines", "model"]
    },
    Events.AGENT_FAILED: {
        "required": ["task_id"],
        "optional": ["error", "retry_count", "model"]
    },
    Events.AGENT_STALLED: {
        "required": ["task_id"],
        "optional": ["stall_time_s", "last_activity"]
    },
    Events.TASK_STARTED: {
        "required": ["task_id"],
        "optional": ["skill_hint", "priority"]
    },
    Events.TASK_PROGRESS: {
        "required": ["task_id"],
        "optional": ["progress_pct", "stage", "message"]
    },
    Events.TASK_CHECKPOINT: {
        "required": ["task_id"],
        "optional": ["checkpoint_id", "stage"]
    },
    Events.TASK_COMPLETED: {
        "required": ["task_id"],
        "optional": ["duration_s", "output_lines", "deliverables"]
    },
    Events.TASK_FAILED: {
        "required": ["task_id"],
        "optional": ["error", "retry_count", "will_retry"]
    },
    Events.TASK_BLOCKED: {
        "required": ["task_id"],
        "optional": ["reason", "blocked_by", "gate_name"]
    },
    Events.TASK_ESCALATED: {
        "required": ["task_id"],
        "optional": ["reason", "escalated_to"]
    },
    Events.MENTION: {
        "required": ["mentioned_agent", "mentioner"],
        "optional": ["channel", "context"]
    },
    Events.SYSTEM_ALERT: {
        "required": ["alert_type", "message"],
        "optional": ["severity", "affected_agents"]
    },
    Events.SYSTEM_HEALTH: {
        "required": ["status"],
        "optional": ["metrics", "issues"]
    },
}


def format_event(
    event_type: Events,
    agent_name: str,
    data: Dict[str, Any],
    channel: str = "system"
) -> dict:
    """Format an event for Squad Chat transmission.

    Args:
        event_type: The event type from Events enum
        agent_name: The agent emitting the event
        data: Event data dictionary
        channel: Target channel (default: system)

    Returns:
        Formatted event dictionary
    """
    template = EVENT_TEMPLATES.get(event_type, {"required": [], "optional": []})

    # Validate required fields
    missing = [f for f in template["required"] if f not in data]
    if missing:
        raise ValueError(f"Missing required fields for {event_type}: {missing}")

    # Build event payload
    event = {
        "type": "message",
        "event_type": event_type.value,
        "sender": agent_name,
        "channel": channel,
        "content": format_event_message(event_type, data),
        "timestamp": datetime.now().isoformat(),
        "data": {k: v for k, v in data.items() if k in template["required"] + template["optional"]}
    }

    return event


def format_event_message(event_type: Events, data: Dict[str, Any]) -> str:
    """Format a human-readable message for an event."""

    task_id = data.get("task_id", "unknown")

    if event_type == Events.AGENT_SPAWNED:
        skill = data.get("skill_hint", "unknown")
        return f"Agent spawned for task {task_id[:8]} (skill: {skill})"

    elif event_type == Events.AGENT_COMPLETED:
        duration = data.get("duration_s", "?")
        lines = data.get("output_lines", "?")
        return f"Agent completed task {task_id[:8]} ({duration}s, {lines} lines)"

    elif event_type == Events.AGENT_FAILED:
        error = data.get("error", "unknown error")[:50]
        return f"Agent failed task {task_id[:8]}: {error}"

    elif event_type == Events.AGENT_STALLED:
        stall_time = data.get("stall_time_s", "?")
        return f"Agent stalled on task {task_id[:8]} ({stall_time}s)"

    elif event_type == Events.TASK_STARTED:
        skill = data.get("skill_hint", "")
        return f"Task {task_id[:8]} started{f' ({skill})' if skill else ''}"

    elif event_type == Events.TASK_PROGRESS:
        pct = data.get("progress_pct", "?")
        stage = data.get("stage", "")
        return f"Task {task_id[:8]} progress: {pct}%{f' ({stage})' if stage else ''}"

    elif event_type == Events.TASK_CHECKPOINT:
        return f"Task {task_id[:8]} checkpoint saved"

    elif event_type == Events.TASK_COMPLETED:
        duration = data.get("duration_s", "?")
        return f"Task {task_id[:8]} completed ({duration}s)"

    elif event_type == Events.TASK_FAILED:
        retry = data.get("will_retry", False)
        return f"Task {task_id[:8]} failed{' (will retry)' if retry else ''}"

    elif event_type == Events.TASK_BLOCKED:
        reason = data.get("reason", "unknown")[:50]
        return f"Task {task_id[:8]} blocked: {reason}"

    elif event_type == Events.TASK_ESCALATED:
        escalated_to = data.get("escalated_to", "?")
        return f"Task {task_id[:8]} escalated to {escalated_to}"

    elif event_type == Events.MENTION:
        mentioned = data.get("mentioned_agent", "?")
        mentioner = data.get("mentioner", "?")
        return f"@{mentioned} mentioned by {mentioner}"

    elif event_type == Events.SYSTEM_ALERT:
        msg = data.get("message", "")[:100]
        return f"ALERT: {msg}"

    elif event_type == Events.SYSTEM_HEALTH:
        status = data.get("status", "?")
        return f"System health: {status}"

    else:
        return f"Event: {event_type.value}"


# Sync wrapper for convenience
def emit_event_sync(agent_name: str, event_type: Events, data: Dict[str, Any], channel: str = "system"):
    """Synchronously emit an event to Squad Chat.

    This is a fire-and-forget function that starts an async task
    to send the event without blocking.
    """
    import asyncio

    async def _emit():
        try:
            from squad_chat_client import SquadChatClient
            async with SquadChatClient(agent_name) as client:
                event = format_event(event_type, agent_name, data, channel)
                await client.send_message(
                    content=event["content"],
                    channel=channel,
                    event_type=event_type.value
                )
        except Exception as e:
            # Don't fail the parent task if squad chat is unavailable
            print(f"[squad-chat] Failed to emit event: {e}")

    try:
        loop = asyncio.get_running_loop()
        asyncio.create_task(_emit())
    except RuntimeError:
        # No running loop, start one
        asyncio.run(_emit())


async def emit_event(agent_name: str, event_type: Events, data: Dict[str, Any], channel: str = "system"):
    """Async emit an event to Squad Chat."""
    from squad_chat_client import SquadChatClient

    try:
        async with SquadChatClient(agent_name) as client:
            event = format_event(event_type, agent_name, data, channel)
            await client.send_message(
                content=event["content"],
                channel=channel,
                event_type=event_type.value
            )
    except Exception as e:
        print(f"[squad-chat] Failed to emit event: {e}")


if __name__ == "__main__":
    # Demo event formatting
    for event in Events:
        sample_data = {"task_id": "test-123-456", "duration_s": 120, "error": "test error"}
        try:
            msg = format_event_message(event, sample_data)
            print(f"{event.value}: {msg}")
        except Exception as e:
            print(f"{event.value}: (requires specific data)")
