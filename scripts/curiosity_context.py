#!/usr/bin/env python3
"""
curiosity_context.py -- Context assembly module for the General Curiosity Engine.

Assembles a CuriosityContext dataclass from Neo4j that gets serialized
into the LLM prompt for question generation.

Usage:
    from curiosity_context import assemble_context, summarize_for_prompt
    ctx = assemble_context()
    prompt_text = summarize_for_prompt(ctx)
"""

import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import neo4j_session
from curiosity_budget import get_category_quota_remaining, get_budget_stage, CATEGORIES

logger = logging.getLogger(__name__)

LOCAL_TZ = ZoneInfo("America/New_York")


@dataclass
class CuriosityContext:
    humans: List[Dict]              # active humans with known/unknown fields
    recent_conversations: List[Dict]  # last 48h inbound messages (humanId, topics, timestamp)
    task_stats: Dict                # 7d: completed, failed, avg_score, by_agent
    human_interests: List[str]      # top topics from conversations
    recently_asked: List[Dict]      # last 20 ResearchQuestion nodes
    category_quotas: Dict           # remaining budget per category
    current_time: str               # ISO timestamp


def assemble_context() -> CuriosityContext:
    """Assemble full context from Neo4j for LLM question generation."""
    return CuriosityContext(
        humans=_get_active_humans(),
        recent_conversations=_get_recent_conversations(hours=48),
        task_stats=_get_task_stats(days=7),
        human_interests=_get_human_interests(days=14, limit=20),
        recently_asked=_get_recently_asked(days=30, limit=20),
        category_quotas=_get_category_quotas(),
        current_time=datetime.now(LOCAL_TZ).isoformat(),
    )


def _get_active_humans() -> List[Dict]:
    """Fetch active humans with their profile completeness.

    Returns list of:
        {id, displayName, timezone, phone,
         has_displayName: bool, has_timezone: bool, message_count_30d: int}
    """
    query = """
        MATCH (h:Human {status: 'active'})
        OPTIONAL MATCH (m:Message {humanId: h.id, direction: 'inbound'})
            WHERE m.timestamp >= datetime() - duration({days: 30})
        WITH h, count(m) AS msg_count
        RETURN h.id AS id,
               h.displayName AS displayName,
               h.timezone AS timezone,
               h.phone AS phone,
               msg_count
        ORDER BY msg_count DESC
    """
    try:
        with neo4j_session() as session:
            result = session.run(query)
            humans = []
            for r in result:
                humans.append({
                    "id": r["id"],
                    "displayName": r["displayName"],
                    "timezone": r["timezone"],
                    "phone": r["phone"],
                    "has_displayName": r["displayName"] is not None and r["displayName"] != "",
                    "has_timezone": r["timezone"] is not None and r["timezone"] != "",
                    "message_count_30d": r["msg_count"],
                })
            return humans
    except Exception as e:
        logger.warning("Failed to fetch active humans: %s", e)
        return []


def _get_recent_conversations(hours: int = 48) -> List[Dict]:
    """Last N hours of inbound messages grouped by human.

    Returns: [{humanId, displayName, message_count, latest_timestamp}]
    """
    query = """
        MATCH (m:Message {direction: 'inbound'})
        WHERE m.timestamp >= datetime() - duration({hours: $hours})
        MATCH (h:Human {id: m.humanId})
        WITH h, count(m) AS msg_count,
             max(toString(m.timestamp)) AS latest_ts
        RETURN h.id AS humanId,
               h.displayName AS displayName,
               msg_count AS message_count,
               latest_ts AS latest_timestamp
        ORDER BY msg_count DESC
    """
    try:
        with neo4j_session() as session:
            result = session.run(query, hours=hours)
            return [dict(r) for r in result]
    except Exception as e:
        logger.warning("Failed to fetch recent conversations: %s", e)
        return []


def _get_task_stats(days: int = 7) -> Dict:
    """Task performance stats for self-reflection.

    Returns:
        {total, completed, failed, avg_score, failure_rate, by_agent: {agent: {completed, failed}}}
    """
    query = """
        MATCH (t:Task)
        WHERE t.created_at >= datetime() - duration({days: $days})
        WITH t,
             CASE WHEN t.status = 'COMPLETED' THEN 1 ELSE 0 END AS is_completed,
             CASE WHEN t.status = 'FAILED' THEN 1 ELSE 0 END AS is_failed
        RETURN count(t) AS total,
               sum(is_completed) AS completed,
               sum(is_failed) AS failed,
               t.assigned_to AS agent
        ORDER BY agent
    """
    try:
        with neo4j_session() as session:
            result = session.run(query, days=days)
            total = 0
            completed = 0
            failed = 0
            by_agent = {}
            for r in result:
                agent = r["agent"] or "unknown"
                agent_completed = r["completed"]
                agent_failed = r["failed"]
                agent_total = r["total"]
                total += agent_total
                completed += agent_completed
                failed += agent_failed
                by_agent[agent] = {
                    "completed": agent_completed,
                    "failed": agent_failed,
                }

            failure_rate = (failed / total * 100) if total > 0 else 0.0
            return {
                "total": total,
                "completed": completed,
                "failed": failed,
                "avg_score": None,  # score not tracked on Task nodes currently
                "failure_rate": round(failure_rate, 1),
                "by_agent": by_agent,
            }
    except Exception as e:
        logger.warning("Failed to fetch task stats: %s", e)
        return {
            "total": 0, "completed": 0, "failed": 0,
            "avg_score": None, "failure_rate": 0.0, "by_agent": {},
        }


def _get_human_interests(days: int = 14, limit: int = 20) -> List[str]:
    """Top topics discussed by humans.

    Returns: list of topic strings sorted by frequency.
    """
    query = """
        MATCH (h:Human {status: 'active'})-[:DISCUSSED]->(t:Topic)
        WHERE EXISTS {
            MATCH (m:Message {humanId: h.id})-[:HAS_TOPIC]->(t)
            WHERE m.timestamp >= datetime() - duration({days: $days})
        }
        RETURN t.label AS label, count(*) AS freq
        ORDER BY freq DESC
        LIMIT $limit
    """
    try:
        with neo4j_session() as session:
            result = session.run(query, days=days, limit=limit)
            return [r["label"] for r in result if r["label"]]
    except Exception as e:
        logger.warning("Failed to fetch human interests: %s", e)
        return []


def _get_recently_asked(days: int = 30, limit: int = 20) -> List[Dict]:
    """Recent ResearchQuestion nodes for dedup context.

    Returns: [{question_text, category, status, created_at}]
    """
    query = """
        MATCH (rq:ResearchQuestion)
        WHERE rq.created_at >= datetime() - duration({days: $days})
        RETURN rq.question_text AS question_text,
               rq.category AS category,
               rq.status AS status,
               toString(rq.created_at) AS created_at
        ORDER BY rq.created_at DESC
        LIMIT $limit
    """
    try:
        with neo4j_session() as session:
            result = session.run(query, days=days, limit=limit)
            return [dict(r) for r in result]
    except Exception as e:
        logger.warning("Failed to fetch recently asked questions: %s", e)
        return []


def _get_category_quotas() -> Dict:
    """Remaining questions per category from budget system.

    Returns: {human: N, self: N, world: N, contextual: N}
    """
    quotas = {}
    for cat in CATEGORIES:
        try:
            quotas[cat] = get_category_quota_remaining(cat)
        except Exception as e:
            logger.warning("Failed to get quota for %s: %s", cat, e)
            quotas[cat] = 0
    return quotas


def summarize_for_prompt(ctx: CuriosityContext, max_tokens: int = 2000) -> str:
    """Serialize context into a compact text summary for the LLM prompt.

    Builds sections incrementally and truncates to stay within the
    approximate max_tokens budget (estimated at ~4 chars per token).
    """
    max_chars = max_tokens * 4
    sections = []

    # -- Humans --
    human_lines = [f"## Humans ({len(ctx.humans)} active)"]
    for h in ctx.humans:
        name = h.get("displayName") or "Unknown"
        tz = h.get("timezone") or "unknown"
        msgs = h.get("message_count_30d", 0)
        tz_display = tz if h.get("has_timezone") else "unknown"
        human_lines.append(f"- {name} (timezone: {tz_display}, {msgs} messages/30d)")
    sections.append("\n".join(human_lines))

    # -- Recent Conversations --
    conv_lines = [f"## Recent Conversations (48h)"]
    if ctx.recent_conversations:
        for c in ctx.recent_conversations:
            name = c.get("displayName") or c.get("humanId", "Unknown")
            count = c.get("message_count", 0)
            conv_lines.append(f"- {name}: {count} messages")
    else:
        conv_lines.append("- No recent conversations")
    sections.append("\n".join(conv_lines))

    # -- Task Performance --
    ts = ctx.task_stats
    task_lines = [f"## Task Performance (7d)"]
    total = ts.get("total", 0)
    completed = ts.get("completed", 0)
    failed = ts.get("failed", 0)
    rate = ts.get("failure_rate", 0.0)
    task_lines.append(f"- Total: {total}, Completed: {completed}, Failed: {failed} ({rate}% failure rate)")
    by_agent = ts.get("by_agent", {})
    if by_agent:
        agent_parts = []
        for agent, stats in sorted(by_agent.items()):
            agent_parts.append(f"{agent}: {stats.get('completed', 0)}ok/{stats.get('failed', 0)}fail")
        task_lines.append(f"- By agent: {', '.join(agent_parts)}")
    sections.append("\n".join(task_lines))

    # -- Human Interests --
    interest_lines = ["## Human Interests"]
    if ctx.human_interests:
        interest_lines.append(", ".join(ctx.human_interests))
    else:
        interest_lines.append("No topics tracked yet")
    sections.append("\n".join(interest_lines))

    # -- Recently Asked --
    asked_lines = ["## Recently Asked (don't repeat)"]
    if ctx.recently_asked:
        for q in ctx.recently_asked:
            text = q.get("question_text", "")
            cat = q.get("category", "?")
            status = q.get("status", "?")
            asked_lines.append(f'- "{text}" ({cat}, {status})')
    else:
        asked_lines.append("- No recent questions")
    sections.append("\n".join(asked_lines))

    # -- Quotas --
    quota_lines = ["## Quotas Remaining Today"]
    parts = []
    for cat in CATEGORIES:
        remaining = ctx.category_quotas.get(cat, 0)
        parts.append(f"{cat}: {remaining}")
    quota_lines.append(f"- {', '.join(parts)}")
    sections.append("\n".join(quota_lines))

    # Assemble and truncate
    full_text = "\n\n".join(sections)
    if len(full_text) > max_chars:
        # Truncate the recently_asked section first (largest variable section)
        # by reducing the number of entries shown
        truncated = full_text[:max_chars]
        last_newline = truncated.rfind("\n")
        if last_newline > 0:
            truncated = truncated[:last_newline]
        full_text = truncated + "\n[...truncated]"

    return full_text


if __name__ == "__main__":
    import json

    print("=== Curiosity Context Assembly ===\n")

    try:
        ctx = assemble_context()
    except Exception as e:
        print(f"[ERROR] Failed to assemble context: {e}")
        sys.exit(1)

    print(f"[1] Humans: {len(ctx.humans)} active")
    for h in ctx.humans:
        name = h.get("displayName") or "Unknown"
        print(f"    - {name} ({h.get('message_count_30d', 0)} msgs/30d)")

    print(f"\n[2] Recent conversations: {len(ctx.recent_conversations)} humans active in 48h")

    ts = ctx.task_stats
    print(f"\n[3] Task stats (7d): {ts.get('total', 0)} total, "
          f"{ts.get('completed', 0)} completed, {ts.get('failed', 0)} failed")

    print(f"\n[4] Human interests: {len(ctx.human_interests)} topics")
    if ctx.human_interests:
        print(f"    Top: {', '.join(ctx.human_interests[:5])}")

    print(f"\n[5] Recently asked: {len(ctx.recently_asked)} questions")

    print(f"\n[6] Category quotas: {json.dumps(ctx.category_quotas)}")

    print(f"\n[7] Current time: {ctx.current_time}")

    print("\n" + "=" * 50)
    print("=== Prompt Summary ===\n")
    summary = summarize_for_prompt(ctx)
    print(summary)
    print(f"\n[Summary length: {len(summary)} chars]")

    print("\n=== Done ===")
