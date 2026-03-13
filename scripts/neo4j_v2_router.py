#!/usr/bin/env python3
"""
neo4j_v2_router.py — Graph-based task routing with single Cypher traversal.

Replaces keyword-table routing in task_intake.py with graph-native scoring:

Score = (domain_match + skill_bonus + recency_bonus) * quality_rate - load_penalty

  domain_match:  OWNS_DOMAIN = 1.0, CAN_HANDLE = rel.weight
  skill_bonus:   PROFICIENT_IN weight * 0.3
  quality_rate:  7-day EXECUTED outcome ratio (default 0.8 for sparse agents)
  load_penalty:  live COUNT(PENDING|WORKING tasks) brackets [0-2: 0, 3-5: 0.2, 6+: 0.5]
  recency_bonus: heartbeat < 10min = 0.1
  anti_affinity: if child task, parent's agent gets -0.5 penalty

Usage:
    from neo4j_v2_router import route_task
    agent = route_task(store, "Research competitor pricing for LLM APIs", "normal")
"""

import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_v2_core import TaskStore
from kurultai_paths import DISPATCH_AGENTS

logger = logging.getLogger(__name__)


def route_task(store: TaskStore, task_text: str, priority: str = "normal",
               domain: str = None, skill_hint: str = None,
               exclude_agent: str = None) -> str:
    """Route a task to the best agent using graph traversal.

    Args:
        store: TaskStore instance
        task_text: Task title or body for domain classification
        priority: Task priority
        domain: Pre-classified domain (if None, classify from text)
        skill_hint: Skill hint for bonus scoring
        exclude_agent: Agent to penalize (anti-affinity for delegation)

    Returns:
        Agent name string.
    """
    # Classify domain if not provided
    if domain is None:
        try:
            from task_intake import classify_task_domain
            domain = classify_task_domain(task_text, skill_hint)
        except Exception:
            domain = "implementation"

    with store.driver.session() as session:
        result = session.run("""
            // Find all dispatchable agents
            MATCH (a:Agent)
            WHERE a.dispatchable = true

            // Domain match score
            OPTIONAL MATCH (a)-[owns:OWNS_DOMAIN]->(d:Domain {name: $domain})
            OPTIONAL MATCH (a)-[handles:CAN_HANDLE]->(d2:Domain {name: $domain})
            WITH a,
                 CASE
                     WHEN owns IS NOT NULL THEN 1.0
                     WHEN handles IS NOT NULL THEN handles.weight
                     ELSE 0.0
                 END AS domain_match

            // Skill bonus
            OPTIONAL MATCH (a)-[prof:PROFICIENT_IN]->(s:Skill {name: $skill})
            WITH a, domain_match,
                 CASE WHEN prof IS NOT NULL THEN prof.weight * 0.3 ELSE 0.0 END AS skill_bonus

            // Quality rate (7-day success ratio, v2 tasks only)
            OPTIONAL MATCH (a)-[:EXECUTED]->(t:Task)
                WHERE t.completed_at > datetime() - duration({days: 7})
                  AND t.status IN ['COMPLETED', 'FAILED']
                  AND t.score IS NOT NULL
            WITH a, domain_match, skill_bonus,
                 CASE
                     WHEN count(t) >= 3 THEN
                         toFloat(count(CASE WHEN t.status = 'COMPLETED' THEN 1 END)) / count(t)
                     ELSE 0.8  // Default for sparse or pre-v2 agents
                 END AS quality_rate

            // Load penalty (live queue depth)
            OPTIONAL MATCH (pending:Task {assigned_to: a.name})
                WHERE pending.status IN ['PENDING', 'WORKING']
            WITH a, domain_match, skill_bonus, quality_rate,
                 count(pending) AS load,
                 CASE
                     WHEN count(pending) <= 2 THEN 0.0
                     WHEN count(pending) <= 5 THEN 0.2
                     ELSE 0.5
                 END AS load_penalty

            // Recency bonus (heartbeat < 10 min)
            WITH a, domain_match, skill_bonus, quality_rate, load, load_penalty,
                 CASE
                     WHEN a.last_heartbeat > datetime() - duration({minutes: 10})
                     THEN 0.1
                     ELSE 0.0
                 END AS recency_bonus

            // Anti-affinity penalty for delegation
            WITH a, domain_match, skill_bonus, quality_rate, load, load_penalty, recency_bonus,
                 CASE
                     WHEN a.name = $exclude_agent THEN 0.5
                     ELSE 0.0
                 END AS anti_affinity

            // Final score
            WITH a,
                 domain_match, skill_bonus, recency_bonus, quality_rate,
                 load, load_penalty, anti_affinity,
                 round(((domain_match + skill_bonus + recency_bonus)
                       * quality_rate - load_penalty - anti_affinity) * 1000) / 1000.0
                 AS score

            RETURN a.name AS agent, score,
                   domain_match, skill_bonus, recency_bonus,
                   quality_rate, load, load_penalty, anti_affinity
            ORDER BY score DESC
            LIMIT 5
        """, domain=domain, skill=skill_hint or "",
            exclude_agent=exclude_agent or "")

        candidates = [dict(rec) for rec in result]

        if not candidates:
            logger.warning(f"No candidates for domain={domain}, fallback to temujin")
            return "temujin"

        best = candidates[0]
        logger.info(
            f"Routed to {best['agent']} (score={best['score']}, "
            f"domain={best['domain_match']}, skill={best['skill_bonus']}, "
            f"quality={best['quality_rate']}, load={best['load']})"
        )

        return best["agent"]


def route_task_with_details(store: TaskStore, task_text: str,
                             priority: str = "normal",
                             domain: str = None,
                             skill_hint: str = None,
                             exclude_agent: str = None) -> dict:
    """Route task and return full scoring details.

    Returns dict with agent, score, and breakdown.
    """
    if domain is None:
        try:
            from task_intake import classify_task_domain
            domain = classify_task_domain(task_text, skill_hint)
        except Exception:
            domain = "implementation"

    agent = route_task(store, task_text, priority, domain, skill_hint, exclude_agent)

    # Get detailed scoring for all candidates
    with store.driver.session() as session:
        result = session.run("""
            MATCH (a:Agent)
            WHERE a.dispatchable = true
            OPTIONAL MATCH (pending:Task {assigned_to: a.name})
                WHERE pending.status IN ['PENDING', 'WORKING']
            RETURN a.name AS agent, a.score AS rolling_score,
                   count(pending) AS queue_depth
            ORDER BY a.name
        """)
        all_agents = {rec["agent"]: dict(rec) for rec in result}

    return {
        "selected": agent,
        "domain": domain,
        "skill_hint": skill_hint,
        "candidates": all_agents,
    }


# ---------------------------------------------------------------------------
# Comparison tool: old routing vs new routing
# ---------------------------------------------------------------------------

def compare_routing(store: TaskStore, task_text: str, priority: str = "normal",
                     old_agent: str = None) -> dict:
    """Compare new graph routing vs old keyword routing.

    Useful for Phase 3 verification: must agree >= 85%.
    """
    # New routing
    new_agent = route_task(store, task_text, priority)

    # Old routing (keyword-based)
    try:
        from task_intake import classify_task_domain
        from kurultai_paths import AGENT_KEYWORDS

        domain = classify_task_domain(task_text)
        task_lower = task_text.lower()

        # Simple keyword scoring (mimics old router)
        scores = {}
        for agent, keywords in AGENT_KEYWORDS.items():
            if agent not in DISPATCH_AGENTS:
                continue
            score = sum(1 for kw in keywords if kw in task_lower)
            if score > 0:
                scores[agent] = score

        if scores:
            old_agent_computed = max(scores, key=scores.get)
        else:
            old_agent_computed = "temujin"

        if old_agent is None:
            old_agent = old_agent_computed
    except Exception:
        old_agent = old_agent or "unknown"

    agree = new_agent == old_agent
    return {
        "task_text": task_text[:100],
        "new_agent": new_agent,
        "old_agent": old_agent,
        "agree": agree,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Neo4j v2 task router")
    parser.add_argument("task_text", nargs="?", default="",
                        help="Task text to route")
    parser.add_argument("--domain", default=None)
    parser.add_argument("--skill", default=None)
    parser.add_argument("--exclude", default=None,
                        help="Agent to penalize (anti-affinity)")
    parser.add_argument("--compare", action="store_true",
                        help="Compare old vs new routing")
    parser.add_argument("--details", action="store_true",
                        help="Show full scoring details")
    args = parser.parse_args()

    if not args.task_text:
        parser.print_help()
        return

    store = TaskStore()
    try:
        if args.compare:
            result = compare_routing(store, args.task_text)
            print(f"New: {result['new_agent']}")
            print(f"Old: {result['old_agent']}")
            print(f"Agree: {result['agree']}")
        elif args.details:
            result = route_task_with_details(
                store, args.task_text,
                domain=args.domain, skill_hint=args.skill,
                exclude_agent=args.exclude,
            )
            print(f"Selected: {result['selected']}")
            print(f"Domain: {result['domain']}")
            for name, info in result['candidates'].items():
                print(f"  {name}: score={info.get('rolling_score', '?')} "
                      f"queue={info.get('queue_depth', '?')}")
        else:
            agent = route_task(
                store, args.task_text,
                domain=args.domain, skill_hint=args.skill,
                exclude_agent=args.exclude,
            )
            print(agent)
    finally:
        store.close()


if __name__ == "__main__":
    main()
