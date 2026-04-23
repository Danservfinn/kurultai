#!/usr/bin/env python3
"""
Daily Goal Progress Summary
Query Neo4j for all active goals and generate progress report
"""

from datetime import datetime, timedelta
from neo4j import GraphDatabase
import os

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

def get_goal_progress(driver):
    """Query Neo4j for goal progress metrics"""
    query = """
    MATCH (g:Goal {status: 'active'})-[:HAS_TASK]->(t:Task)
    WITH g, COUNT(t) as total_tasks,
         SUM(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) as completed,
         SUM(CASE WHEN t.status = 'in_progress' THEN 1 ELSE 0 END) as in_progress,
         SUM(CASE WHEN t.status = 'blocked' THEN 1 ELSE 0 END) as blocked
    RETURN g.name as goal_name,
           g.deadline as deadline,
           g.revenue_target as revenue_target,
           total_tasks,
           completed,
           in_progress,
           blocked,
           100.0 * completed / total_tasks as percent_complete
    ORDER BY g.created_at DESC
    """
    with driver.session() as session:
        result = session.run(query)
        return [record for record in result]

def get_recent_wins(driver, goal_name, days=7):
    """Get recent completed tasks for a goal"""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    query = """
    MATCH (g:Goal {name: $goal_name})-[:HAS_TASK]->(t:Task)
    WHERE t.status = 'completed'
      AND t.completed_at > $cutoff
    RETURN t.title as win
    ORDER BY t.completed_at DESC
    LIMIT 5
    """
    with driver.session() as session:
        result = session.run(query, goal_name=goal_name, cutoff=cutoff)
        return [record["win"] for record in result]

def get_blockers(driver, goal_name):
    """Get blocked tasks for a goal"""
    query = """
    MATCH (g:Goal {name: $goal_name})-[:HAS_TASK]->(t:Task)
    WHERE t.status = 'blocked'
      AND (t.blocked_at IS NULL OR t.blocked_at < datetime() - duration('P2D'))
    RETURN t.title as blocker, t.blocker_reason as reason
    ORDER BY t.blocked_at DESC
    LIMIT 3
    """
    with driver.session() as session:
        result = session.run(query, goal_name=goal_name)
        return [(record["blocker"], record["reason"]) for record in result]

def get_next_milestones(driver, goal_name):
    """Get upcoming milestones for a goal"""
    query = """
    MATCH (g:Goal {name: $goal_name})-[:HAS_MILESTONE]->(m:Milestone)
    WHERE m.status = 'pending'
    RETURN m.title as milestone, m.target_date as target_date
    ORDER BY m.target_date ASC
    LIMIT 2
    """
    with driver.session() as session:
        result = session.run(query, goal_name=goal_name)
        return [(record["milestone"], record["target_date"]) for record in result]

def get_parse_metrics(driver):
    """Get revenue metrics for Parse goal"""
    query = """
    MATCH (g:Goal {name: 'Parse'})-[r:HAS_METRIC]->(m:Metric)
    WHERE m.name IN ['MRR', 'paying_users', 'conversion_rate']
    RETURN m.name as name, m.value as value, m.updated_at as updated_at
    """
    with driver.session() as session:
        result = session.run(query)
        return {record["name"]: record["value"] for record in result}

def format_progress_report():
    """Generate daily progress summary"""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    try:
        goals = get_goal_progress(driver)
        if not goals:
            return "📊 Daily Progress Report\n\nNo active goals found."

        report_lines = [f"📊 Daily Progress {datetime.now().strftime('%Y-%m-%d')}\n"]

        for goal in goals:
            goal_name = goal["goal_name"]
            total = goal["total_tasks"]
            completed = goal["completed"]
            in_progress = goal["in_progress"]
            blocked = goal["blocked"]
            percent = goal["percent_complete"]
            deadline = goal["deadline"]

            # Calculate days remaining
            if deadline:
                deadline_date = datetime.fromisoformat(deadline.replace('Z', '+00:00'))
                days_remaining = (deadline_date - datetime.now()).days
            else:
                days_remaining = "No deadline"

            # Get wins, blockers, milestones
            wins = get_recent_wins(driver, goal_name)
            blockers = get_blockers(driver, goal_name)
            milestones = get_next_milestones(driver, goal_name)

            # Build goal section
            report_lines.append(f"\n## {goal_name}")
            report_lines.append(f"- Progress: {percent:.1f}% complete ({completed}/{total} tasks, {in_progress} in progress, {blocked} blocked)")
            report_lines.append(f"- Deadline: {days_remaining} days remaining")

            # Wins
            if wins:
                report_lines.append(f"- ✅ Wins: {', '.join(wins[:3])}")
            else:
                report_lines.append("- ✅ Wins: No recent wins")

            # Blockers
            if blockers:
                blocker_text = ", ".join([f"{b} ({r})" for b, r in blockers])
                report_lines.append(f"- ⚠️ Blockers: {blocker_text}")
            else:
                report_lines.append("- ⚠️ Blockers: None")

            # Next milestones
            if milestones:
                milestone_text = ", ".join([f"{m} ({d})" for m, d in milestones])
                report_lines.append(f"- 📍 Next: {milestone_text}")
            else:
                report_lines.append("- 📍 Next: No pending milestones")

            # Parse revenue metrics
            if goal_name == "Parse":
                metrics = get_parse_metrics(driver)
                if metrics:
                    report_lines.append(f"- 💰 Metrics: MRR ${metrics.get('MRR', 0)}, {metrics.get('paying_users', 0)} paying users, {metrics.get('conversion_rate', 0)}% conversion")

        return "\n".join(report_lines)

    finally:
        driver.close()

if __name__ == "__main__":
    print(format_progress_report())
