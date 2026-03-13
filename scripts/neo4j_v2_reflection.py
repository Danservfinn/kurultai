#!/usr/bin/env python3
"""
neo4j_v2_reflection.py — Reflection context from 3 Cypher queries.

Replaces the ~1,200-line prepare_reflection_context.py with graph-native queries:
  1. Last hour's tasks per agent
  2. 7-day failure patterns
  3. Last 3 reflections per agent

Also handles writing Reflection nodes back to the graph.

Usage:
    from neo4j_v2_reflection import prepare_reflection, save_reflection
    context = prepare_reflection(store, "temujin")
    save_reflection(store, "temujin", summary="...", insight="...")
"""

import os
import sys
import logging
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_v2_core import TaskStore
from agents_config import AGENTS

logger = logging.getLogger(__name__)


def _get_recent_tasks(session, agent: str, hours: int = 1) -> list[dict]:
    """Query 1: Tasks completed/failed in the last N hours."""
    result = session.run("""
        MATCH (a:Agent {name: $agent})-[:EXECUTED]->(t:Task)
        WHERE t.completed_at > datetime() - duration({hours: $hours})
           OR (t.status = 'FAILED' AND t.updated_at > datetime() - duration({hours: $hours}))
        OPTIONAL MATCH (t)-[:HAS_OUTPUT]->(o:TaskOutput)
        OPTIONAL MATCH (t)-[:HAS_FAILURE]->(f:FailureReport)
        WITH t, o, collect(f {.error_class, .error_msg, .is_transient, .attempt}) AS failures
        RETURN t {
            .task_id, .title, .status, .domain, .priority, .score,
            .retry_count, .skill_hint,
            output_summary: left(coalesce(o.text, ''), 200),
            problem: o.problem,
            solution: left(coalesce(o.solution, ''), 300),
            failures: failures
        } AS task
        ORDER BY t.completed_at DESC
        LIMIT 20
    """, agent=agent, hours=hours)
    return [dict(rec["task"]) for rec in result]


def _get_failure_patterns(session, agent: str, days: int = 7) -> list[dict]:
    """Query 2: Failure patterns over the last N days."""
    result = session.run("""
        MATCH (a:Agent {name: $agent})-[:EXECUTED]->(t:Task)-[:HAS_FAILURE]->(f:FailureReport)
        WHERE f.created_at > datetime() - duration({days: $days})
        WITH f.error_class AS error_class,
             f.is_transient AS transient,
             count(f) AS count,
             collect(DISTINCT t.domain)[..3] AS domains,
             collect(DISTINCT left(f.error_msg, 100))[..2] AS examples
        RETURN error_class, transient, count, domains, examples
        ORDER BY count DESC
        LIMIT 10
    """, agent=agent, days=days)
    return [dict(rec) for rec in result]


def _get_recent_reflections(session, agent: str, limit: int = 3) -> list[dict]:
    """Query 3: Last N reflection summaries."""
    result = session.run("""
        MATCH (a:Agent {name: $agent})-[:REFLECTS]->(r:Reflection)
        RETURN r {
            .summary, .insight, .tasks_completed, .tasks_failed,
            .failure_rate, .avg_score, .period_start, .period_end
        } AS reflection
        ORDER BY r.period_end DESC
        LIMIT $limit
    """, agent=agent, limit=limit)
    return [dict(rec["reflection"]) for rec in result]


def _get_agent_stats(session, agent: str) -> dict:
    """Agent-level stats for reflection context."""
    result = session.run("""
        MATCH (a:Agent {name: $agent})
        OPTIONAL MATCH (a)-[:EXECUTED]->(t:Task)
            WHERE t.completed_at > datetime() - duration({hours: 24})
        WITH a,
             count(CASE WHEN t.status = 'COMPLETED' THEN 1 END) AS completed_24h,
             count(CASE WHEN t.status = 'FAILED' THEN 1 END) AS failed_24h,
             avg(t.score) AS avg_score_24h
        OPTIONAL MATCH (pending:Task {assigned_to: a.name, status: 'PENDING'})
        WITH a, completed_24h, failed_24h, avg_score_24h,
             count(DISTINCT pending) AS pending_count
        OPTIONAL MATCH (working:Task {assigned_to: a.name, status: 'WORKING'})
        WITH a, completed_24h, failed_24h, avg_score_24h, pending_count,
             count(DISTINCT working) AS working_count
        RETURN a.score AS rolling_score,
               a.role AS role,
               completed_24h, failed_24h,
               round(coalesce(avg_score_24h, 0) * 1000) / 1000.0 AS avg_score_24h,
               pending_count, working_count
    """, agent=agent)
    record = result.single()
    return dict(record) if record else {}


def prepare_reflection(store: TaskStore, agent: str,
                        hours: int = 1) -> str:
    """Build reflection context from graph queries.

    Returns a formatted text block suitable for the reflection prompt.
    """
    with store.driver.session() as session:
        tasks = _get_recent_tasks(session, agent, hours)
        failures = _get_failure_patterns(session, agent, days=7)
        reflections = _get_recent_reflections(session, agent, limit=3)
        stats = _get_agent_stats(session, agent)

    # Build context
    parts = []
    parts.append(f"# Reflection Context: {agent}")
    parts.append(f"Role: {stats.get('role', 'unknown')}")
    parts.append(f"Rolling Score (7d): {stats.get('rolling_score', 'N/A')}")
    parts.append(f"24h: {stats.get('completed_24h', 0)} completed, "
                 f"{stats.get('failed_24h', 0)} failed, "
                 f"avg score {stats.get('avg_score_24h', 0)}")
    parts.append(f"Queue: {stats.get('pending_count', 0)} pending, "
                 f"{stats.get('working_count', 0)} working")
    parts.append("")

    # Recent tasks
    parts.append(f"## Last {hours}h Tasks ({len(tasks)} total)")
    for t in tasks:
        score_str = f" score={t.get('score', '?')}" if t.get('score') else ""
        parts.append(f"- [{t['status']}] {t.get('title', 'untitled')}"
                     f" ({t.get('domain', '?')}/{t.get('priority', '?')}){score_str}")
        if t.get('problem'):
            parts.append(f"  Problem: {t['problem'][:100]}")
        if t.get('solution'):
            parts.append(f"  Solution: {t['solution'][:150]}")
        if t.get('failures'):
            for f in t['failures'][:2]:
                parts.append(f"  Failure #{f.get('attempt', '?')}: "
                             f"{f.get('error_class', '?')} — {f.get('error_msg', '')[:80]}")
    parts.append("")

    # Failure patterns
    if failures:
        parts.append("## 7-Day Failure Patterns")
        for f in failures:
            trans = "transient" if f.get("transient") else "permanent"
            parts.append(f"- {f['error_class']}: {f['count']}x ({trans}) "
                         f"domains={f.get('domains', [])}")
            for ex in f.get("examples", []):
                parts.append(f"  e.g. {ex}")
        parts.append("")

    # Recent reflections
    if reflections:
        parts.append("## Recent Reflections")
        for r in reflections:
            period = f"{r.get('period_start', '?')} to {r.get('period_end', '?')}"
            parts.append(f"- [{period}] {r.get('tasks_completed', 0)} completed, "
                         f"{r.get('tasks_failed', 0)} failed, "
                         f"rate={r.get('failure_rate', '?')}, "
                         f"avg={r.get('avg_score', '?')}")
            if r.get('insight'):
                parts.append(f"  Insight: {r['insight'][:200]}")
        parts.append("")

    context = "\n".join(parts)

    # Truncate to stay within embedding API limits (250KB)
    if len(context) > 250_000:
        context = context[:250_000] + "\n\n[TRUNCATED]"

    return context


def save_reflection(store: TaskStore, agent: str,
                     summary: str, insight: str = "",
                     tasks_completed: int = 0, tasks_failed: int = 0,
                     failure_rate: float = 0.0, avg_score: float = 0.0,
                     period_hours: int = 1) -> bool:
    """Save a Reflection node and link it to the agent and covered tasks.

    Returns True on success.
    """
    now = datetime.now(timezone.utc).isoformat()
    with store.driver.session() as session:
        result = session.run("""
            MATCH (a:Agent {name: $agent})
            CREATE (a)-[:REFLECTS]->(r:Reflection {
                agent: $agent,
                summary: $summary,
                insight: $insight,
                tasks_completed: $completed,
                tasks_failed: $failed,
                failure_rate: $failure_rate,
                avg_score: $avg_score,
                period_start: datetime() - duration({hours: $hours}),
                period_end: datetime(),
                created_at: datetime()
            })
            WITH r
            // Link to tasks covered by this reflection period
            OPTIONAL MATCH (t:Task {assigned_to: $agent})
                WHERE t.completed_at > datetime() - duration({hours: $hours})
                   OR (t.status = 'FAILED' AND t.updated_at > datetime() - duration({hours: $hours}))
            FOREACH (task IN CASE WHEN t IS NOT NULL THEN [t] ELSE [] END |
                CREATE (r)-[:COVERS]->(task)
            )
            RETURN r.agent AS agent
        """, agent=agent, summary=summary[:5000], insight=insight[:1000],
            completed=tasks_completed, failed=tasks_failed,
            failure_rate=round(failure_rate, 3), avg_score=round(avg_score, 3),
            hours=period_hours)

        ok = result.single() is not None
        if ok:
            logger.info(f"Saved reflection for {agent}: "
                        f"{tasks_completed} completed, {tasks_failed} failed")
        return ok


def prepare_all_reflections(store: TaskStore, hours: int = 1) -> dict[str, str]:
    """Prepare reflection context for all agents."""
    contexts = {}
    for agent in AGENTS:
        contexts[agent] = prepare_reflection(store, agent, hours)
    return contexts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Neo4j v2 reflection context")
    parser.add_argument("--agent", default=None, help="Agent name (all if omitted)")
    parser.add_argument("--hours", type=int, default=1)
    parser.add_argument("--save-test", action="store_true",
                        help="Save a test reflection")
    args = parser.parse_args()

    store = TaskStore()
    try:
        if args.save_test and args.agent:
            ok = save_reflection(
                store, args.agent,
                summary="Test reflection from CLI",
                insight="This is a test insight",
            )
            print(f"Saved: {ok}")
        elif args.agent:
            ctx = prepare_reflection(store, args.agent, args.hours)
            print(ctx)
        else:
            contexts = prepare_all_reflections(store, args.hours)
            for agent, ctx in contexts.items():
                print(f"\n{'='*60}\n{agent}\n{'='*60}")
                print(ctx[:500])
                if len(ctx) > 500:
                    print(f"\n... ({len(ctx)} chars total)")
    finally:
        store.close()


if __name__ == "__main__":
    main()
