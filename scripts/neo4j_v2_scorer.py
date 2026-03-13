#!/usr/bin/env python3
"""
neo4j_v2_scorer.py — Graph-native task and skill scoring.

Replaces score_tasks.py + score_skills.py with inline scoring:
  - Task score computed on completion (no batch job needed)
  - Agent rolling score updated after each task
  - Skill proficiency updated from EXECUTED relationships

Scoring formula (0.0 - 1.0):
  completion_score: COMPLETED=0.5, FAILED=0.0
  retry_efficiency: (1 - retry_count / (max_retries + 1)) * 0.3
  domain_match:     agent OWNS_DOMAIN for task domain = 0.2, else 0.0

Usage:
    from neo4j_v2_scorer import score_task, update_agent_score, update_skill_proficiency
    score_task(store, task_id)  # inline on completion
"""

import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_v2_core import TaskStore

logger = logging.getLogger(__name__)


def score_task(store: TaskStore, task_id: str) -> float:
    """Compute and persist task score in Neo4j.

    Called inline after task completion or failure.
    Returns the computed score.
    """
    with store.driver.session() as session:
        result = session.run("""
            MATCH (t:Task {task_id: $id})
            OPTIONAL MATCH (a:Agent {name: t.assigned_to})-[:OWNS_DOMAIN]->(d:Domain {name: t.domain})
            WITH t,
                 CASE WHEN t.status = 'COMPLETED' THEN 0.5 ELSE 0.0 END AS completion,
                 (1.0 - toFloat(coalesce(t.retry_count, 0)) / (coalesce(t.max_retries, 3) + 1)) * 0.3 AS retry_eff,
                 CASE WHEN d IS NOT NULL THEN 0.2 ELSE 0.0 END AS domain_bonus
            SET t.score = round((completion + retry_eff + domain_bonus) * 1000) / 1000.0
            RETURN t.score AS score
        """, id=task_id)

        record = result.single()
        if record:
            score = record["score"]
            logger.info(f"Task {task_id} scored: {score}")
            return score
        return 0.0


def update_agent_score(store: TaskStore, agent: str) -> float:
    """Update agent's rolling 7-day average score.

    Called after each task completion.
    Returns the new rolling score.
    """
    with store.driver.session() as session:
        result = session.run("""
            MATCH (a:Agent {name: $agent})-[:EXECUTED]->(t:Task)
            WHERE t.completed_at > datetime() - duration({days: 7})
              AND t.score IS NOT NULL
            WITH a, avg(t.score) AS rolling, count(t) AS task_count
            SET a.score = round(rolling * 1000) / 1000.0,
                a.tasks_7d = task_count
            RETURN a.score AS score, task_count
        """, agent=agent)

        record = result.single()
        if record:
            logger.info(f"Agent {agent} rolling score: {record['score']} "
                        f"({record['task_count']} tasks in 7d)")
            return record["score"]
        return 0.0


def update_skill_proficiency(store: TaskStore, agent: str, skill: str,
                              outcome: str) -> None:
    """Update PROFICIENT_IN relationship after skill use.

    Adjusts success_rate and use_count on the relationship.
    """
    is_success = outcome in ("completed", "COMPLETED")
    with store.driver.session() as session:
        session.run("""
            MATCH (a:Agent {name: $agent})-[r:PROFICIENT_IN]->(s:Skill {name: $skill})
            SET r.use_count = coalesce(r.use_count, 0) + 1,
                r.success_rate = CASE
                    WHEN coalesce(r.use_count, 0) = 0 THEN
                        CASE WHEN $success THEN 1.0 ELSE 0.0 END
                    ELSE
                        round(((coalesce(r.success_rate, 0.8) * coalesce(r.use_count, 0))
                            + CASE WHEN $success THEN 1.0 ELSE 0.0 END)
                            / (coalesce(r.use_count, 0) + 1) * 1000) / 1000.0
                    END
        """, agent=agent, skill=skill, success=is_success)


def score_completed_task(store: TaskStore, task_id: str, agent: str,
                          skill_hint: str = "") -> float:
    """Convenience: score task + update agent + update skill in one call.

    Called by executor after successful completion.
    """
    score = score_task(store, task_id)
    update_agent_score(store, agent)
    if skill_hint:
        update_skill_proficiency(store, agent, skill_hint, "completed")
    return score


def score_failed_task(store: TaskStore, task_id: str, agent: str,
                       skill_hint: str = "") -> float:
    """Score a failed task and update agent metrics."""
    score = score_task(store, task_id)
    update_agent_score(store, agent)
    if skill_hint:
        update_skill_proficiency(store, agent, skill_hint, "failed")
    return score


# ---------------------------------------------------------------------------
# Batch scoring (for migration / backfill)
# ---------------------------------------------------------------------------

def backfill_scores(store: TaskStore, limit: int = 100) -> int:
    """Score unscored completed/failed tasks."""
    with store.driver.session() as session:
        result = session.run("""
            MATCH (t:Task)
            WHERE t.status IN ['COMPLETED', 'FAILED']
              AND t.score IS NULL
            RETURN t.task_id AS tid
            ORDER BY t.completed_at DESC
            LIMIT $limit
        """, limit=limit)

        count = 0
        for record in result:
            score_task(store, record["tid"])
            count += 1

        if count > 0:
            logger.info(f"Backfilled {count} task scores")

            # Update all agent scores
            for rec in session.run("MATCH (a:Agent) RETURN a.name AS name"):
                update_agent_score(store, rec["name"])

        return count


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Neo4j v2 task/skill scoring")
    parser.add_argument("--backfill", type=int, metavar="N",
                        help="Score N unscored tasks")
    parser.add_argument("--task", metavar="TASK_ID",
                        help="Score a specific task")
    parser.add_argument("--agent-scores", action="store_true",
                        help="Recompute all agent rolling scores")
    parser.add_argument("--update-all", action="store_true",
                        help="Backfill unscored + update all agent scores")
    args = parser.parse_args()

    store = TaskStore()
    try:
        if args.backfill:
            count = backfill_scores(store, args.backfill)
            print(f"Backfilled {count} scores")
        elif args.task:
            score = score_task(store, args.task)
            print(f"Score: {score}")
        elif args.update_all:
            count = backfill_scores(store, 100)
            print(f"Backfilled {count} scores")
            with store.driver.session() as session:
                for rec in session.run("MATCH (a:Agent) RETURN a.name AS name"):
                    s = update_agent_score(store, rec["name"])
                    print(f"  {rec['name']}: {s}")
        elif args.agent_scores:
            with store.driver.session() as session:
                for rec in session.run("MATCH (a:Agent) RETURN a.name AS name"):
                    s = update_agent_score(store, rec["name"])
                    print(f"  {rec['name']}: {s}")
        else:
            parser.print_help()
    finally:
        store.close()


if __name__ == "__main__":
    main()
