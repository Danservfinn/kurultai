#!/usr/bin/env python3
"""Read-only Cypher helpers for the Hermes task_custodian sweep.

All mutation lives in TaskStore (mark_obsolete, rewrite_prompt, reassign).
These helpers only identify candidates for the custodian to act on:

    find_repeat_failures     — tasks failing >= N times in a window
    find_duplicate_pending   — near-identical PENDING tasks for same agent
    find_chronic_orphans     — tasks that keep hitting ORPHAN_RECOVERED
    get_recent_pending_prompts — for optional LLM harm-classification pass
"""
from __future__ import annotations

from typing import Any


def find_repeat_failures(session, threshold: int = 3,
                         window_hours: int = 24) -> list[dict]:
    """Tasks with >= threshold TASK_FAILED events in the last window_hours.

    Returns a list of dicts with keys:
        task_id, agent, source, status, fail_count,
        last_error_msg, last_error_category, last_failed_at
    """
    result = session.run("""
        MATCH (e:Event)-[:ABOUT]->(t:Task)
        WHERE e.event_type = 'TASK_FAILED'
          AND e.ts >= datetime() - duration({hours: $window})
        WITH t, count(e) AS fail_count,
             collect(e) AS failures
        WHERE fail_count >= $threshold
        WITH t, fail_count, failures,
             [f IN failures | f] AS all_f
        UNWIND all_f AS f
        WITH t, fail_count,
             f ORDER BY f.ts DESC
        WITH t, fail_count, collect(f)[0] AS latest
        RETURN t.task_id AS task_id,
               t.assigned_to AS agent,
               t.source AS source,
               t.status AS status,
               fail_count,
               latest.error_msg AS last_error_msg,
               latest.error_category AS last_error_category,
               latest.ts AS last_failed_at
        ORDER BY fail_count DESC, latest.ts DESC
        LIMIT 50
    """, threshold=threshold, window=window_hours)
    return [dict(r) for r in result]


def find_duplicate_pending(session, prompt_prefix_chars: int = 200,
                            max_groups: int = 20) -> list[list[dict]]:
    """Groups of PENDING tasks with identical (assigned_to, prompt_prefix).

    Returns a list of groups. Each group is a list of 2+ task dicts,
    oldest first (the "keeper" is group[0]; everything else is a
    duplicate the custodian will flag for delete).

    Only compares the first `prompt_prefix_chars` of the prompt to stay
    cheap — semantic dedup is a non-goal for v1.
    """
    result = session.run("""
        MATCH (t:Task {status: 'PENDING'})
        WHERE t.prompt IS NOT NULL AND size(t.prompt) > 10
        WITH t.assigned_to AS agent,
             substring(t.prompt, 0, $prefix) AS prompt_prefix,
             t
        ORDER BY t.created_at ASC
        WITH agent, prompt_prefix, collect(t) AS group
        WHERE size(group) >= 2
        RETURN agent, prompt_prefix,
               [g IN group | {
                   task_id: g.task_id,
                   agent: g.assigned_to,
                   source: g.source,
                   status: g.status,
                   created_at: g.created_at,
                   prompt: g.prompt
               }] AS tasks
        ORDER BY size(group) DESC
        LIMIT $max_groups
    """, prefix=prompt_prefix_chars, max_groups=max_groups)
    groups = []
    for record in result:
        tasks = [dict(t) for t in record["tasks"]]
        groups.append(tasks)
    return groups


def find_chronic_orphans(session, min_bounces: int = 2,
                          window_days: int = 7) -> list[dict]:
    """Tasks that have emitted >= min_bounces ORPHAN_RECOVERED events
    in the last window_days. Indicates a structural problem (wrong agent,
    prompt too long for context, missing tool access, etc.).

    Returns {task_id, agent, source, status, bounces, last_bounce_at}.
    """
    result = session.run("""
        MATCH (e:Event)-[:ABOUT]->(t:Task)
        WHERE e.event_type = 'ORPHAN_RECOVERED'
          AND e.ts >= datetime() - duration({days: $window})
        WITH t, count(e) AS bounces, max(e.ts) AS last_bounce
        WHERE bounces >= $min_bounces
        RETURN t.task_id AS task_id,
               t.assigned_to AS agent,
               t.source AS source,
               t.status AS status,
               bounces,
               last_bounce AS last_bounce_at
        ORDER BY bounces DESC, last_bounce DESC
        LIMIT 20
    """, min_bounces=min_bounces, window=window_days)
    return [dict(r) for r in result]


def get_recent_pending_prompts(session, limit: int = 20) -> list[dict]:
    """Most recently created PENDING task prompts, for optional LLM
    harm-classification pass. Returns {task_id, agent, source, prompt}."""
    result = session.run("""
        MATCH (t:Task {status: 'PENDING'})
        WHERE t.prompt IS NOT NULL
        RETURN t.task_id AS task_id,
               t.assigned_to AS agent,
               t.source AS source,
               t.prompt AS prompt
        ORDER BY t.created_at DESC
        LIMIT $limit
    """, limit=limit)
    return [dict(r) for r in result]
