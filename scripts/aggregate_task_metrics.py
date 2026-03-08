#!/usr/bin/env python3
"""
Aggregate task metrics into TaskMetric nodes for reflection queries.

Creates hourly and daily rollups to reduce query overhead during reflections.
Gracefully degrades when TaskOutcome nodes don't exist yet (Phase 1 incomplete).

Usage:
    python3 aggregate_task_metrics.py --period hourly --hours 1
    python3 aggregate_task_metrics.py --period daily --days 1
    python3 aggregate_task_metrics.py --dry-run
"""

import argparse
import sys
import os
import uuid
import json
from datetime import datetime, timedelta

# Add scripts dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_task_tracker import get_driver


AGENTS = ["kublai", "mongke", "chagatai", "temujin", "jochi", "ogedei"]


def create_constraints(driver):
    """Create Neo4j constraints and indexes for TaskMetric nodes."""
    try:
        with driver.session() as session:
            # Create unique constraint on metric_id
            session.run("""
                CREATE CONSTRAINT task_metric_id_unique IF NOT EXISTS
                FOR (m:TaskMetric) REQUIRE m.metric_id IS UNIQUE
            """)

            # Create index for agent+time lookups
            session.run("""
                CREATE INDEX task_metric_agent_time_idx IF NOT EXISTS
                FOR (m:TaskMetric) ON (m.agent, m.period_start)
            """)

            print("Constraints and indexes verified/created")
            return True
    except Exception as e:
        print(f"Constraint creation failed: {e}", file=sys.stderr)
        return False


def aggregate_metrics(period="hourly", hours=1, days=None, dry_run=False):
    """Create TaskMetric nodes for the specified period.

    Args:
        period: "hourly" or "daily"
        hours: Number of hours for hourly aggregation
        days: Number of days for daily aggregation
        dry_run: If True, print what would be done without executing

    Returns:
        Dict with aggregation results per agent
    """
    driver = get_driver()
    results = {}

    # Calculate time window
    now = datetime.now()
    if period == "daily" and days:
        period_start = now - timedelta(days=days)
        time_filter = f"P{days}D"
    elif period == "hourly":
        period_start = now - timedelta(hours=hours)
        time_filter = f"PT{hours}H"
    else:
        period_start = now - timedelta(hours=1)
        time_filter = "PT1H"

    print(f"Aggregating {period} metrics for period: {period_start} to {now}")

    with driver.session() as session:
        for agent in AGENTS:
            # Query tasks in period with optional outcome data
            query = f"""
                MATCH (t:Task {{agent: $agent}})
                WHERE t.completed > datetime() - duration('{time_filter}')
                  AND toUpper(t.status) IN ['COMPLETED', 'FAILED']

                // Collect string error categories only (filter out MAP types)
                WITH t,
                     CASE
                         WHEN t.error_category IS NULL THEN NULL
                         WHEN t.error_category = 'NULL' THEN NULL
                         WHEN toString(t.error_category) CONTAINS '{{' THEN NULL  // MAP type, skip
                         ELSE toString(t.error_category)
                     END AS error_cat_str

                // Count metrics (always available from Task nodes)
                WITH count(t) AS total,
                     sum(CASE WHEN toUpper(t.status) = 'COMPLETED' THEN 1 ELSE 0 END) AS completed,
                     sum(CASE WHEN toUpper(t.status) = 'FAILED' THEN 1 ELSE 0 END) AS failed,
                     sum(CASE WHEN t.rework_required = true THEN 1 ELSE 0 END) AS partial,
                     coalesce(sum(t.retry_count), 0) AS total_retries,

                     // Collect distributions
                     collect(DISTINCT error_cat_str) AS error_cats_raw,
                     collect(DISTINCT t.skill_hint) AS skills_raw,
                     collect(DISTINCT t.model) AS models_raw

                // Filter out null/empty/map values
                WITH total, completed, failed, partial, total_retries,
                     [ec IN error_cats_raw WHERE ec IS NOT NULL AND ec <> '' AND ec <> 'NULL'] AS error_cats,
                     [sk IN skills_raw WHERE sk IS NOT NULL AND sk <> ''] AS skills,
                     [md IN models_raw WHERE md IS NOT NULL AND md <> ''] AS models

                // Optional: Join with TaskOutcome if exists (Phase 1+)
                OPTIONAL MATCH (t)-[:HAS_OUTCOME]->(o:TaskOutcome)

                WITH total, completed, failed, partial, total_retries,
                     error_cats, skills, models,
                     avg(o.output_quality_score) AS avg_quality,
                     avg(o.efficiency_score) AS avg_efficiency,
                     avg(o.difficulty_score) AS avg_difficulty,
                     avg(o.clarity_score) AS avg_clarity

                // Calculate rates
                WITH total, completed, failed, partial, total_retries,
                     error_cats, skills, models,
                     avg_quality, avg_efficiency, avg_difficulty, avg_clarity,
                     CASE WHEN total > 0 THEN toFloat(completed) / toFloat(total) ELSE 0.0 END AS success_rate,
                     CASE WHEN completed > 0 THEN toFloat(partial) / toFloat(completed) ELSE 0.0 END AS rework_rate,
                     CASE WHEN total > 0 THEN toFloat(total_retries) / toFloat(total) ELSE 0.0 END AS retry_rate

                RETURN total, completed, failed, partial, success_rate, rework_rate, retry_rate,
                       avg_quality, avg_efficiency, avg_difficulty, avg_clarity,
                       error_cats, skills, models
            """

            result = session.run(query, agent=agent)
            record = result.single()

            if not record or record["total"] == 0:
                results[agent] = {"status": "no_tasks", "total": 0}
                continue

            # Build distribution maps
            error_cats_raw = record["error_cats"]
            skills_raw = record["skills"]
            models_raw = record["models"]

            error_dist = _build_distribution(error_cats_raw)
            skill_dist = _build_distribution(skills_raw)
            model_dist = _build_distribution(models_raw)

            metric_data = {
                "agent": agent,
                "period_start": period_start.isoformat(),
                "period_end": now.isoformat(),
                "period_type": period,
                "tasks_total": record["total"],
                "tasks_completed": record["completed"],
                "tasks_failed": record["failed"],
                "tasks_partial": record["partial"],
                "success_rate": round(record["success_rate"], 4),
                "rework_rate": round(record["rework_rate"], 4),
                "retry_rate": round(record["retry_rate"], 4),
                "avg_quality_score": round(record["avg_quality"] or 0, 2),
                "avg_efficiency_score": round(record["avg_efficiency"] or 0, 2),
                "avg_difficulty": round(record["avg_difficulty"] or 0, 2),
                "avg_clarity": round(record["avg_clarity"] or 0, 2),
                "error_distribution": error_dist,
                "skill_distribution": skill_dist,
                "model_distribution": model_dist,
            }

            if dry_run:
                print(f"\n[DRY RUN] Would create TaskMetric for {agent}:")
                for k, v in metric_data.items():
                    print(f"  {k}: {v}")
                results[agent] = {"status": "dry_run", "data": metric_data}
            else:
                # Create TaskMetric node - store distributions as JSON strings
                metric_id = str(uuid.uuid4())[:12]
                create_query = """
                    MERGE (a:Agent {name: $agent})
                    CREATE (a)-[:HAS_METRIC]->(m:TaskMetric {
                        metric_id: $metric_id,
                        agent: $agent,
                        period_start: datetime($period_start),
                        period_end: datetime($period_end),
                        period_type: $period_type,
                        tasks_total: $tasks_total,
                        tasks_completed: $tasks_completed,
                        tasks_failed: $tasks_failed,
                        tasks_partial: $tasks_partial,
                        success_rate: $success_rate,
                        rework_rate: $rework_rate,
                        retry_rate: $retry_rate,
                        avg_quality_score: $avg_quality_score,
                        avg_efficiency_score: $avg_efficiency_score,
                        avg_difficulty: $avg_difficulty,
                        avg_clarity: $avg_clarity,
                        error_distribution: $error_distribution,
                        skill_distribution: $skill_distribution,
                        model_distribution: $model_distribution,
                        created_at: datetime()
                    })
                """
                # Convert distribution dicts to JSON strings for Neo4j storage
                create_params = {
                    "metric_id": metric_id,
                    **metric_data,
                    "error_distribution": json.dumps(error_dist),
                    "skill_distribution": json.dumps(skill_dist),
                    "model_distribution": json.dumps(model_dist),
                }
                session.run(create_query, **create_params)
                results[agent] = {"status": "created", "metric_id": metric_id, **metric_data}
                print(f"Created TaskMetric {metric_id} for {agent}: {record['completed']}/{record['total']} tasks completed")

    return results


def _build_distribution(items):
    """Build a distribution map from a list of items.

    Args:
        items: List of strings (may contain None/empty)

    Returns:
        Dict mapping each unique non-empty item to its count
    """
    dist = {}
    for item in items:
        # Skip None, non-string types (dict, list), and empty values
        if item is None:
            continue
        if isinstance(item, (dict, list)):
            continue
        if not isinstance(item, str):
            item = str(item)
        if item.strip() and item.lower() not in ("none", "null", "n/a"):
            dist[item] = dist.get(item, 0) + 1
    return dist


def prune_old_metrics(driver, days=30):
    """Remove TaskMetric nodes older than specified days."""
    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (m:TaskMetric)
                WHERE m.period_start < datetime() - duration({days: $days})
                DELETE m
                RETURN count(m) AS pruned
            """, days=days)
            record = result.single()
            count = record["pruned"] if record else 0
            print(f"Pruned {count} old TaskMetric nodes (older than {days} days)")
            return count
    except Exception as e:
        print(f"Prune failed: {e}", file=sys.stderr)
        return 0


def verify_metrics(driver, hours=24):
    """Verify TaskMetric nodes exist and return summary."""
    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (a:Agent)-[:HAS_METRIC]->(m:TaskMetric)
                WHERE m.period_start > datetime() - duration({hours: $hours})
                RETURN a.name AS agent, m.period_type, m.period_start,
                       m.tasks_completed, m.tasks_failed, m.tasks_total,
                       round(m.success_rate, 2) AS success_rate,
                       round(m.avg_quality_score, 2) AS avg_quality
                ORDER BY m.period_start DESC
                LIMIT 20
            """, hours=hours)

            metrics = [dict(r) for r in result]
            print(f"\nVerification: Found {len(metrics)} TaskMetric nodes in last {hours}h")
            for m in metrics[:5]:  # Show first 5
                print(f"  {m['agent']} ({m['period_type']}): {m['tasks_completed']}/{m['tasks_total']} tasks, "
                      f"success={m['success_rate']}, quality={m['avg_quality']}")

            return metrics
    except Exception as e:
        print(f"Verification failed: {e}", file=sys.stderr)
        return []


def main():
    parser = argparse.ArgumentParser(description="Aggregate task metrics into TaskMetric nodes")
    parser.add_argument("--period", choices=["hourly", "daily"], default="hourly",
                        help="Aggregation period")
    parser.add_argument("--hours", type=int, default=1,
                        help="Number of hours for hourly aggregation")
    parser.add_argument("--days", type=int,
                        help="Number of days for daily aggregation")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be done without executing")
    parser.add_argument("--verify", action="store_true",
                        help="Verify existing TaskMetric nodes after aggregation")
    parser.add_argument("--prune", type=int, metavar="DAYS",
                        help="Prune metrics older than N days")
    parser.add_argument("--setup", action="store_true",
                        help="Create constraints and indexes only")

    args = parser.parse_args()
    driver = get_driver()

    try:
        # Setup: create constraints
        if args.setup or not args.dry_run:
            create_constraints(driver)

        # Prune old metrics if requested
        if args.prune:
            prune_old_metrics(driver, args.prune)

        # Run aggregation
        if not args.setup:
            results = aggregate_metrics(
                period=args.period,
                hours=args.hours,
                days=args.days,
                dry_run=args.dry_run
            )

            # Summary
            total_created = sum(1 for r in results.values() if r.get("status") in ["created", "dry_run"])
            total_tasks = sum(r.get("data", r).get("tasks_total", 0) for r in results.values())
            print(f"\nAggregation complete: {total_created} agents, {total_tasks} total tasks processed")

            # Verify if requested
            if args.verify and not args.dry_run:
                verify_metrics(driver, hours=24)

    finally:
        driver.close()


if __name__ == "__main__":
    main()
