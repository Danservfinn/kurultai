#!/usr/bin/env python3
"""
post_completion_hook.py — Post-completion hook for automatic follow-up task creation.

This module implements a fire-and-forget hook that runs after task completion.
It parses YAML follow-up declarations from task output, invokes horde-prompt
to generate optimized task bodies, and queues new tasks via task_intake.

Key design:
- Opt-in via YAML blocks in task output
- Fire-and-forget (asyncio.create_task) — never blocks executor
- Never raises — all errors logged and fall back to minimal bodies
- Uses claude-agent -p for prompt generation
- Integrates with existing task_intake.py

See docs/plans/2026-03-23-task-completion-followup-hook.md for full spec.
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

logger = logging.getLogger("post_completion_hook")

# Constants
MAX_FOLLOWUPS = 5
VALID_AGENTS = frozenset({"temujin", "mongke", "chagatai", "jochi", "ogedei"})
VALID_PRIORITIES = frozenset({"critical", "high", "normal", "low"})
CLAUDE_AGENT = Path("/Users/kublai/.local/bin/claude-agent")
HORDE_PROMPT_TIMEOUT = 120  # 2 minutes max for prompt generation

# Scripts dir — task_intake imported lazily inside _create_task_sync
_SCRIPTS_DIR = Path(__file__).parent

# ============================================================================
# Task 2.1: FollowUpDeclaration dataclass + parse_followups()
# ============================================================================

@dataclass
class FollowUpDeclaration:
    """Structured declaration of a follow-up task from agent output."""
    title: str
    agent: str
    priority: str = "normal"
    skill_hint: str = ""
    context: str = ""


def parse_followups(content: str) -> list[FollowUpDeclaration]:
    """
    Parse follow_ups YAML blocks from task output content.

    Finds all ```yaml blocks containing 'follow_ups:' key.
    Returns up to MAX_FOLLOWUPS validated declarations.

    Args:
        content: Task result/output text to parse

    Returns:
        List of validated FollowUpDeclaration objects (max MAX_FOLLOWUPS)

    Rules:
    - Skips items with missing title or invalid agent
    - Normalizes priority to 'normal' if invalid
    - Caps at MAX_FOLLOWUPS (excess silently dropped)
    - Never raises (parse errors caught and logged)
    """
    results = []

    # Find all fenced yaml blocks
    for match in re.finditer(r'```ya?ml\n(.*?)```', content, re.DOTALL):
        block = match.group(1)
        if 'follow_ups' not in block:
            continue

        if yaml is None:
            logger.warning("pyyaml not installed — cannot parse follow_ups blocks")
            return results

        try:
            data = yaml.safe_load(block)
            if not isinstance(data, dict):
                continue

            for item in (data.get('follow_ups') or []):
                if not isinstance(item, dict):
                    continue

                title = str(item.get('title', '')).strip()
                agent = str(item.get('agent', '')).strip().lower()

                # Validation: title and agent are required
                if not title or agent not in VALID_AGENTS:
                    logger.warning("Skipping follow-up: title=%r agent=%r", title, agent)
                    continue

                # Normalize priority
                priority = str(item.get('priority', 'normal')).lower()
                if priority not in VALID_PRIORITIES:
                    priority = 'normal'

                results.append(FollowUpDeclaration(
                    title=title,
                    agent=agent,
                    priority=priority,
                    skill_hint=str(item.get('skill_hint', '')),
                    context=str(item.get('context', '')).strip(),
                ))

        except Exception as e:
            logger.warning("Failed to parse follow_ups block: %s", e)
            # Continue to next block

    return results[:MAX_FOLLOWUPS]


# ============================================================================
# Task 2.2: invoke_horde_prompt() — claude-agent subprocess
# ============================================================================

async def invoke_horde_prompt(
    followup: FollowUpDeclaration,
    parent_task_id: str,
    parent_title: str,
) -> str:
    """
    Spawn claude-agent -p to invoke /horde-prompt for the follow-up task.

    Returns the generated task body text, or a minimal fallback on failure.
    Times out after HORDE_PROMPT_TIMEOUT seconds.

    Args:
        followup: Follow-up declaration to generate prompt for
        parent_task_id: ID of parent task that declared the follow-up
        parent_title: Title of parent task

    Returns:
        Generated task body text (never empty, falls back on error)
    """
    meta_prompt = (
        f"/horde-prompt\n\n"
        f"Generate an optimized task body for a follow-up task that was declared "
        f"by a completing agent.\n\n"
        f"**Follow-up title:** {followup.title}\n"
        f"**Target agent:** {followup.agent}\n"
        f"**Priority:** {followup.priority}\n"
        f"**Context from completing task:** {followup.context or '(none provided)'}\n\n"
        f"**Parent task:** {parent_title} (id: {parent_task_id})\n\n"
        f"Produce a complete task body that the target agent can execute. "
        f"Include the goal, relevant context from the parent task, and "
        f"acceptance criteria. Keep it under 500 words."
    )

    agent_dir = Path.home() / ".openclaw" / "agents" / "kublai"
    cmd = [
        str(CLAUDE_AGENT),
        "--print",
        "--no-session-persistence",
        "--workdir", str(agent_dir),
        meta_prompt,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(
            proc.communicate(),
            timeout=HORDE_PROMPT_TIMEOUT
        )
        body = stdout.decode("utf-8", errors="replace").strip()

        # Validate output
        if len(body) < 50:
            raise ValueError(f"horde-prompt output too short: {len(body)} chars")

        return body

    except asyncio.TimeoutError:
        logger.warning("invoke_horde_prompt timed out after %ds", HORDE_PROMPT_TIMEOUT)
    except Exception as e:
        logger.warning("invoke_horde_prompt failed (%s); using fallback body", e)

    # Minimal fallback — still creates the task
    return (
        f"# Task: {followup.title}\n\n"
        f"**Context:** {followup.context or 'See parent task.'}\n\n"
        f"**Parent task:** {parent_task_id}\n\n"
        f"*(Prompt generation via horde-prompt failed; task created with minimal body.)*"
    )


# ============================================================================
# Task 2.3: create_followup_task() — task_intake integration
# ============================================================================

async def create_followup_task(
    followup: FollowUpDeclaration,
    body: str,
    parent_task_id: str,
) -> str:
    """
    Create a new task in Neo4j linked to the parent task.

    Uses task_intake.create_task to queue the follow-up task.
    Runs the sync DB call in an executor to avoid blocking the event loop.

    Args:
        followup: Follow-up declaration
        body: Generated task body (from horde-prompt or fallback)
        parent_task_id: ID of parent task

    Returns:
        New task_id

    Raises:
        Logs errors but never raises (task_intake errors caught)
    """
    follow_task_id = f"{followup.priority}-followup-{uuid.uuid4().hex[:8]}"

    def _create_sync() -> Optional[str]:
        if str(_SCRIPTS_DIR) not in sys.path:
            sys.path.insert(0, str(_SCRIPTS_DIR))
        try:
            from task_intake import create_task  # noqa: PLC0415
            result = create_task(
                title=followup.title,
                body=body,
                priority=followup.priority,
                source="post-completion-hook",
                depth=1,
                agent=followup.agent,
                parent_id=parent_task_id,
                skip_duplicate_check=False,
                skill_hint=followup.skill_hint or None,
                origin_type="agent",
                origin_source="post-completion-hook",
            )
            return result
        except Exception as exc:
            logger.error("task_intake.create_task failed for %r: %s", followup.title, exc)
            return None

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _create_sync)
    if result:
        logger.info(
            "Created follow-up task %s for agent=%s title=%r",
            result, followup.agent, followup.title
        )
    return result or follow_task_id


# ============================================================================
# Task 2.4: run_post_completion_hook() — main entry point
# ============================================================================

async def run_post_completion_hook(
    task_id: str,
    task_title: str,
    result_content: str,
) -> None:
    """
    Main entry point. Called fire-and-forget from task_executor.py.

    Parses follow-ups from result content, invokes horde-prompt for each,
    and queues new tasks. Never raises — all errors are logged.

    Args:
        task_id: ID of completed task
        task_title: Title of completed task
        result_content: Full task output content to parse for follow-ups

    Returns:
        None

    Behavior:
    - Returns immediately if no follow-ups parsed
    - Processes each follow-up independently (one failure doesn't block others)
    - Logs counts and IDs throughout
    - Never raises (all exceptions caught and logged)
    """
    try:
        followups = parse_followups(result_content)
        if not followups:
            return

        logger.info(
            "post_completion_hook: %d follow-up(s) declared in task %s",
            len(followups), task_id
        )

        for followup in followups:
            try:
                body = await invoke_horde_prompt(followup, task_id, task_title)
                new_id = await create_followup_task(followup, body, task_id)
                logger.info("Queued follow-up %s → task %s", followup.title, new_id)
            except Exception as e:
                logger.error(
                    "Failed to queue follow-up %r: %s", followup.title, e
                )

    except Exception as e:
        logger.error("post_completion_hook crashed for task %s: %s", task_id, e)
