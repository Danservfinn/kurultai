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
from __future__ import annotations

import os
import sys
import logging
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
KUBLAI_REPO = "/Users/kublai/kurultai/kublai-repo"
if KUBLAI_REPO not in sys.path:
    sys.path.insert(0, KUBLAI_REPO)

from neo4j_v2_core import TaskStore
from agents_config import AGENTS
from kublai.brain_service_client import call as brain_service_call

logger = logging.getLogger(__name__)


def _knowledge_dual_write_enabled() -> bool:
    return os.getenv("KUBLAI_KNOWLEDGE_DUAL_WRITE", "").lower() in {"1", "true", "yes"}


def _body_without_frontmatter(text: str) -> str:
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end >= 0:
            return text[end + 5:]
    return text


def _append_dual_write_log(record: dict) -> None:
    log_path = os.getenv("BRAIN_DUAL_WRITE_LOG", "/Users/kublai/.brain-index/dual-write-reconciliation.jsonl")
    target = Path(log_path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _dual_write_reflection(
    *,
    agent: str,
    reflection_id: str,
    summary: str,
    insight: str,
    tasks_completed: int,
    tasks_failed: int,
    failure_rate: float,
    avg_score: float,
    period_hours: int,
    recorded_at: str,
) -> None:
    if not _knowledge_dual_write_enabled():
        return
    body = (
        f"# Reflection {reflection_id}\n\n"
        f"## Summary\n\n{summary}\n\n"
        f"## Insight\n\n{insight}\n\n"
        f"## Metrics\n\n"
        f"- tasks_completed: {tasks_completed}\n"
        f"- tasks_failed: {tasks_failed}\n"
        f"- failure_rate: {round(failure_rate, 3)}\n"
        f"- avg_score: {round(avg_score, 3)}\n"
        f"- period_hours: {period_hours}\n"
    )
    socket_path = os.getenv("BRAIN_SERVICE_SOCKET", "/Users/kublai/.kublai/brain-service.sock")
    response = brain_service_call(
        socket_path,
        "knowledge.record_reflection",
        {
            "agent": agent,
            "reflection_id": reflection_id,
            "body": body,
            "tags": ["kublai", "reflection", "dual-write"],
        },
    )
    if not response.get("ok"):
        raise RuntimeError(response.get("message") or response.get("error") or "brain-service reflection write failed")

    wiki_root = Path(os.getenv("BRAIN_WIKI_ROOT", "/Users/kublai/brain")).resolve()
    path = Path(response["result"]).resolve()
    body_hash = hashlib.sha256(_body_without_frontmatter(path.read_text(encoding="utf-8")).encode("utf-8")).hexdigest()
    _append_dual_write_log(
        {
            "operation_id": str(uuid.uuid4()),
            "kind": "reflection",
            "idempotency_key": f"reflection:{reflection_id}",
            "wiki_path": path.relative_to(wiki_root).as_posix(),
            "body_hash": body_hash,
            "neo4j_label": "Reflection",
            "recorded_at": recorded_at,
        }
    )


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
            reflection_seed = f"{agent}|{now}|{summary}|{insight}"
            reflection_id = f"{agent}-{now.replace(':', '').replace('+', 'Z')}-{hashlib.sha256(reflection_seed.encode('utf-8')).hexdigest()[:12]}"
            try:
                _dual_write_reflection(
                    agent=agent,
                    reflection_id=reflection_id,
                    summary=summary,
                    insight=insight,
                    tasks_completed=tasks_completed,
                    tasks_failed=tasks_failed,
                    failure_rate=failure_rate,
                    avg_score=avg_score,
                    period_hours=period_hours,
                    recorded_at=now,
                )
            except Exception as exc:
                logger.exception(f"Knowledge dual-write failed for {agent}: {exc}")
        return ok


def prepare_all_reflections(store: TaskStore, hours: int = 1) -> dict[str, str]:
    """Prepare reflection context for all agents."""
    contexts = {}
    for agent in AGENTS:
        contexts[agent] = prepare_reflection(store, agent, hours)
    return contexts


# ---------------------------------------------------------------------------
# Conversational Health Queries (for review stage only — NOT self-reflection)
# ---------------------------------------------------------------------------

def _get_curiosity_funnel(session, days: int = 7) -> dict:
    """PendingQuestion status funnel over last N days.
    System-wide (no agent field on PendingQuestion).
    Statuses: PENDING, ANSWERED, SKIPPED, EXPIRED.
    """
    result = session.run("""
        MATCH (pq:PendingQuestion)
        WHERE pq.createdAt > datetime() - duration({days: toInteger($days)})
        RETURN pq.status AS status, count(pq) AS count
    """, days=days)
    funnel = {}
    for rec in result:
        funnel[rec["status"]] = rec["count"]
    total = sum(funnel.values())
    answered = funnel.get("ANSWERED", 0)
    return {
        "total": total,
        "funnel": funnel,
        "answer_rate": round(answered / total, 3) if total > 0 else 0.0,
    }


def _get_reciprocity_ratio(session, days: int = 7) -> list:
    """Inbound vs outbound DM message ratio per human.
    Filters scope='dm' (excludes group messages).
    """
    result = session.run("""
        MATCH (h:Human)
        MATCH (m:Message {humanId: h.id, scope: 'dm'})
        WHERE m.timestamp > datetime() - duration({days: toInteger($days)})
          AND m.direction IN ['inbound', 'outbound']
        WITH h,
             count(CASE WHEN m.direction = 'inbound' THEN 1 END) AS inbound,
             count(CASE WHEN m.direction = 'outbound' THEN 1 END) AS outbound
        WHERE inbound + outbound > 0
        RETURN coalesce(h.displayName, left(h.id, 8)) AS name,
               h.id AS human_id,
               inbound, outbound,
               CASE WHEN outbound > 0
                    THEN round(toFloat(inbound) / outbound * 100) / 100.0
                    ELSE -1.0
               END AS ratio
        ORDER BY inbound + outbound DESC
        LIMIT 10
    """, days=days)
    return [dict(rec) for rec in result]


def _get_stale_action_items(session, stale_days: int = 7) -> list:
    """ActionItems with status='OPEN' older than N days.
    Uses epoch millis for age calculation.
    """
    result = session.run("""
        MATCH (ai:ActionItem {status: 'OPEN'})
        WHERE ai.createdAt < datetime() - duration({days: toInteger($days)})
        OPTIONAL MATCH (h:Human {id: ai.humanId})
        RETURN ai.description AS description,
               ai.assignee AS assignee,
               ai.priority AS priority,
               toString(ai.deadline) AS deadline,
               toString(ai.createdAt) AS created_at,
               coalesce(h.displayName, 'unknown') AS human_name,
               (datetime().epochMillis - ai.createdAt.epochMillis) / 86400000 AS age_days
        ORDER BY ai.createdAt ASC
        LIMIT 15
    """, days=stale_days)
    return [dict(rec) for rec in result]


def prepare_conversational_context(store: TaskStore) -> str:
    """Build conversational health context for the REVIEW stage only.

    NOT embedded in prepare_reflection() — prevents Goodhart's Law.
    Each query independently catches Neo4j exceptions.
    Callers: review-with-fallback.py, generate_hourly_report.py.
    """
    from neo4j.exceptions import ServiceUnavailable, SessionExpired

    parts = ["## Conversational Health (Last 7 Days)"]

    with store.driver.session() as session:
        # Query 1: Curiosity funnel
        try:
            funnel = _get_curiosity_funnel(session, days=7)
            parts.append("\n### Curiosity Engine")
            parts.append(f"Questions: {funnel['total']} total, "
                         f"answer rate: {funnel['answer_rate']:.0%}")
            for status, count in sorted(funnel['funnel'].items()):
                parts.append(f"  {status}: {count}")
            if funnel['total'] > 0 and funnel['answer_rate'] < 0.3:
                parts.append("  WARNING: Answer rate below 30% — questions may be poorly timed or irrelevant")
        except (ServiceUnavailable, SessionExpired) as e:
            parts.append(f"\n### Curiosity Engine\n*Neo4j unavailable: {str(e)[:60]}*")
            logger.warning(f"Curiosity funnel: Neo4j unavailable: {e}")
        except Exception as e:
            parts.append(f"\n### Curiosity Engine\n*Error: {str(e)[:80]}*")
            logger.error(f"Curiosity funnel query error: {e}", exc_info=True)

        # Query 2: Reciprocity ratio
        try:
            ratios = _get_reciprocity_ratio(session, days=7)
            parts.append(f"\n### DM Reciprocity ({len(ratios)} humans)")
            if ratios:
                for r in ratios[:5]:
                    ratio_str = f"{r['ratio']:.2f}" if r['ratio'] >= 0 else "outbound-only"
                    parts.append(f"  {r['name']}: {r['inbound']}in/{r['outbound']}out "
                                 f"(ratio={ratio_str})")
                    if r['ratio'] >= 0 and r['ratio'] < 0.2 and r['outbound'] > 5:
                        parts.append(f"    WARNING: Very low reciprocity — possible over-messaging")
                if len(ratios) > 5:
                    parts.append(f"  ... and {len(ratios) - 5} more")
            else:
                parts.append("  No DM conversations in period")
        except (ServiceUnavailable, SessionExpired) as e:
            parts.append(f"\n### DM Reciprocity\n*Neo4j unavailable*")
            logger.warning(f"Reciprocity ratio: Neo4j unavailable: {e}")
        except Exception as e:
            parts.append(f"\n### DM Reciprocity\n*Error: {str(e)[:80]}*")
            logger.error(f"Reciprocity ratio query error: {e}", exc_info=True)

        # Query 3: Stale action items
        try:
            stale = _get_stale_action_items(session, stale_days=7)
            parts.append(f"\n### Stale Promises ({len(stale)} items >7d)")
            if stale:
                for item in stale[:5]:
                    age = int(item.get('age_days', 0))
                    desc = (item.get('description') or 'no description')[:60]
                    parts.append(f"  [{age}d] {desc} (for {item['human_name']})")
                if len(stale) > 5:
                    parts.append(f"  ... and {len(stale) - 5} more")
                if len(stale) > 20:
                    parts.append("  WARNING: >20 stale action items — action item lifecycle may need attention")
            else:
                parts.append("  No stale action items")
        except (ServiceUnavailable, SessionExpired) as e:
            parts.append(f"\n### Stale Promises\n*Neo4j unavailable*")
        except Exception as e:
            parts.append(f"\n### Stale Promises\n*Error: {str(e)[:80]}*")
            logger.error(f"Stale action items query error: {e}", exc_info=True)

    # ResponseGuard activation count (from JSONL, not Neo4j)
    try:
        from pathlib import Path
        guard_log = Path("/Users/kublai/.openclaw/logs/response-guard-activations.jsonl")
        if guard_log.exists():
            import json
            from datetime import datetime as dt, timedelta
            cutoff = dt.now() - timedelta(days=7)
            activations = fallbacks = 0
            content = guard_log.read_text().strip()
            lines = content.split("\n") if content else []
            for line in lines[-200:]:
                try:
                    entry = json.loads(line)
                    if entry.get("event") == "group_send":
                        continue
                    if dt.fromisoformat(entry["timestamp"]) > cutoff:
                        activations += 1
                        if entry.get("is_fallback"):
                            fallbacks += 1
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
            parts.append(f"\n### Privacy (ResponseGuard, 7d)")
            parts.append(f"  Activations: {activations} ({fallbacks} high-redaction fallbacks)")
            if fallbacks > 5:
                parts.append("  WARNING: >5 fallback activations — response generation may need review")
        else:
            parts.append(f"\n### Privacy (ResponseGuard)")
            parts.append("  No activation log found (file created on first group interaction)")
    except Exception as e:
        parts.append(f"\n### Privacy\n*Error: {str(e)[:60]}*")

    return "\n".join(parts)


def _run_conversational_self_test(store: TaskStore):
    """Create test data, run queries, verify, clean up."""
    import uuid
    test_tag = f"conv-selftest-{uuid.uuid4().hex[:8]}"
    human_id = f"test-human-{test_tag}"
    print(f"  Self-test: {test_tag}")

    # Phase 1: Create test data and run direct queries in one session
    with store.driver.session() as s:
        s.run("""
            CREATE (h:Human {id: $hid, displayName: 'Test Human', status: 'active',
                             source: 'test', _test_tag: $tag})

            CREATE (pq1:PendingQuestion {id: randomUUID(), humanId: $hid,
                    status: 'PENDING', createdAt: datetime(), expiresAt: datetime() + duration('PT30M'),
                    type: 'event_field', question: 'Test?', _test_tag: $tag})
            CREATE (pq2:PendingQuestion {id: randomUUID(), humanId: $hid,
                    status: 'ANSWERED', createdAt: datetime() - duration('PT1H'),
                    answeredAt: datetime(), type: 'profile_curiosity', question: 'Test answered',
                    _test_tag: $tag})
            CREATE (pq3:PendingQuestion {id: randomUUID(), humanId: $hid,
                    status: 'EXPIRED', createdAt: datetime() - duration('PT2H'),
                    type: 'event_field', question: 'Test expired', _test_tag: $tag})

            CREATE (m1:Message {id: randomUUID(), humanId: $hid, direction: 'inbound',
                    scope: 'dm', timestamp: datetime(), contentScrubbed: 'test in',
                    _test_tag: $tag})
            CREATE (m2:Message {id: randomUUID(), humanId: $hid, direction: 'outbound',
                    scope: 'dm', timestamp: datetime(), contentScrubbed: 'test out',
                    _test_tag: $tag})

            CREATE (ai:ActionItem {id: randomUUID(), humanId: $hid, status: 'OPEN',
                    description: 'Test stale item', priority: 'low',
                    createdAt: datetime() - duration('P30D'),
                    updatedAt: datetime() - duration('P30D'),
                    _test_tag: $tag})
        """, hid=human_id, tag=test_tag)
        print("  [OK] Test data created")

        # Run direct queries within the same session
        try:
            funnel = _get_curiosity_funnel(s, days=1)
            assert funnel['total'] >= 3, f"Expected >= 3 questions, got {funnel['total']}"
            print(f"  [OK] Curiosity funnel: {funnel['total']} questions, {funnel['answer_rate']:.0%} answer rate")
        except Exception as e:
            print(f"  [FAIL] Curiosity funnel: {e}")

        try:
            ratios = _get_reciprocity_ratio(s, days=1)
            assert len(ratios) >= 1, f"Expected >= 1 human, got {len(ratios)}"
            print(f"  [OK] Reciprocity: {len(ratios)} humans, first ratio={ratios[0].get('ratio')}")
        except Exception as e:
            print(f"  [FAIL] Reciprocity: {e}")

        try:
            stale = _get_stale_action_items(s, stale_days=1)
            assert len(stale) >= 1, f"Expected >= 1 stale item, got {len(stale)}"
            print(f"  [OK] Stale items: {len(stale)}, age={stale[0].get('age_days')}d")
        except Exception as e:
            print(f"  [FAIL] Stale items: {e}")

    # Phase 2: Test full context wrapper in a separate session (avoids nested session deadlock)
    try:
        ctx = prepare_conversational_context(store)
        assert len(ctx) > 50, f"Context too short: {len(ctx)} chars"
        print(f"  [OK] Full context: {len(ctx)} chars")
    except Exception as e:
        print(f"  [FAIL] Full context: {e}")

    # Phase 3: Cleanup
    with store.driver.session() as s:
        r = s.run("""
            MATCH (n) WHERE n._test_tag = $tag
            DETACH DELETE n
            RETURN count(n) AS deleted
        """, tag=test_tag).single()
        print(f"  [OK] Cleaned up {r['deleted']} test nodes")

    print("\n  Self-test complete.")


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
    parser.add_argument("--conversational", action="store_true",
                        help="Show conversational health context")
    parser.add_argument("--self-test", action="store_true",
                        help="Run conversational query self-test")
    args = parser.parse_args()

    store = TaskStore()
    try:
        if args.self_test:
            _run_conversational_self_test(store)
        elif args.conversational:
            ctx = prepare_conversational_context(store)
            print(ctx if ctx else "(empty)")
        elif args.save_test and args.agent:
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
