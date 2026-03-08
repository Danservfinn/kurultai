#!/usr/bin/env python3
"""
Task Report Aggregator - Analysis and insights for reflection.

Aggregates task report data from Neo4j to generate insights for:
- Hourly reflections
- Daily system improvements
- Weekly trend analysis
- Error pattern detection
- Performance optimization

Usage:
    python3 task_report_aggregator.py --reflection --hours 1
    python3 task_report_aggregator.py --daily-report
    python3 task_report_aggregator.py --error-patterns --days 7
    python3 task_report_aggregator.py --performance-trends --days 30
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kublai_task_report import TaskReporter
from neo4j_task_tracker import get_tracker


class TaskReportAggregator:
    """Aggregate and analyze task report data for insights."""

    def __init__(self):
        self.reporter = TaskReporter()
        self.tracker = get_tracker()

    def close(self):
        """Close database connections."""
        self.reporter.close()
        self.tracker.close()

    # ============================================================
    # Reflection Analysis
    # ============================================================

    def generate_reflection_data(self, agent: Optional[str] = None, hours: int = 1) -> Dict:
        """Generate comprehensive reflection data for an agent or system-wide.

        Args:
            agent: Specific agent name, or None for system-wide
            hours: Hours to look back

        Returns:
            Dict with reflection-ready data including:
            - Performance metrics
            - Error patterns
            - Quality trends
            - Recommendations
        """
        # Get base summary
        summary = self.reporter.get_reflection_summary(hours)

        if agent:
            # Agent-specific data
            agent_agg = self.reporter.aggregate_by_agent(hours)
            agent_data = next((a for a in agent_agg if a["agent"] == agent), {})
        else:
            agent_data = {}

        # Get error patterns
        error_patterns = self._analyze_error_patterns(hours)

        # Get performance trends
        performance = self._analyze_performance_trends(hours)

        # Get quality signals
        quality = self._analyze_quality_signals(hours)

        # Generate recommendations
        recommendations = self._generate_recommendations(
            summary, error_patterns, performance, quality, agent
        )

        return {
            "period": {
                "hours": hours,
                "generated": datetime.now().isoformat(),
                "scope": agent or "system-wide",
            },
            "summary": summary,
            "agent_metrics": agent_data,
            "error_patterns": error_patterns,
            "performance_trends": performance,
            "quality_analysis": quality,
            "recommendations": recommendations,
        }

    def _analyze_error_patterns(self, hours: int) -> Dict:
        """Analyze recurring error patterns."""
        clusters = self.reporter.get_error_clusters(hours, min_size=1)
        by_category = self.reporter.aggregate_by_error_category(hours)

        # Identify top recurring issues
        recurring = [c for c in clusters if c["occurrences"] >= 2]

        return {
            "total_unique_errors": len(clusters),
            "recurring_errors": len(recurring),
            "by_category": [dict(c) for c in by_category[:5]],
            "top_clusters": [dict(c) for c in clusters[:5]],
            "recurring_details": [dict(c) for c in recurring[:3]],
        }

    def _analyze_performance_trends(self, hours: int) -> Dict:
        """Analyze performance trends."""
        with self.reporter.driver.session() as session:
            # Hourly breakdown
            hourly = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({hours: $hours})
                  AND t.actual_duration_seconds IS NOT NULL
                RETURN
                    t.created.hour AS hour,
                    count(t) AS tasks,
                    avg(t.actual_duration_seconds) AS avg_duration,
                    avg(t.total_tokens) AS avg_tokens,
                    sum(CASE WHEN t.status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed
                ORDER BY hour
            """, hours=hours)

            # Agent comparison
            agent_perf = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({hours: $hours})
                  AND t.actual_duration_seconds IS NOT NULL
                RETURN
                    t.agent AS agent,
                    count(t) AS tasks,
                    avg(t.actual_duration_seconds) AS avg_duration,
                    percentile90(t.actual_duration_seconds) AS p90_duration,
                    avg(t.total_tokens) AS avg_tokens,
                    100.0 * sum(CASE WHEN t.status = 'COMPLETED' THEN 1 ELSE 0 END) / count(t) AS success_rate
                ORDER BY tasks DESC
            """, hours=hours)

            # Skill performance
            skill_perf = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({hours: $hours})
                  AND t.skill_hint IS NOT NULL
                  AND t.actual_duration_seconds IS NOT NULL
                RETURN
                    t.skill_hint AS skill,
                    count(t) AS tasks,
                    avg(t.actual_duration_seconds) AS avg_duration,
                    100.0 * sum(CASE WHEN t.status = 'COMPLETED' THEN 1 ELSE 0 END) / count(t) AS success_rate
                ORDER BY tasks DESC
                LIMIT 10
            """, hours=hours)

        return {
            "hourly_breakdown": [dict(r) for r in hourly],
            "by_agent": [dict(r) for r in agent_perf],
            "by_skill": [dict(r) for r in skill_perf],
        }

    def _analyze_quality_signals(self, hours: int) -> Dict:
        """Analyze quality signals and verification results."""
        with self.reporter.driver.session() as session:
            # Verification score distribution
            vq_scores = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({hours: $hours})
                  AND t.verification_score IS NOT NULL
                RETURN
                    count(t) AS tasks_with_scores,
                    avg(t.verification_score) AS avg_score,
                    min(t.verification_score) AS min_score,
                    max(t.verification_score) AS max_score,
                    percentile90(t.verification_score) AS p90_score
            """, hours=hours)

            # Rework analysis
            rework = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({hours: $hours})
                  AND t.rework_required = true
                RETURN
                    count(t) AS rework_tasks,
                    avg(t.followup_tasks_created) AS avg_followups,
                    collect(DISTINCT t.rework_reason)[..5] AS reasons
            """, hours=hours)

            # High-quality vs low-quality tasks
            quality_split = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({hours: $hours})
                  AND t.verification_score IS NOT NULL
                WITH
                    sum(CASE WHEN t.verification_score >= 80 THEN 1 ELSE 0 END) AS high_quality,
                    sum(CASE WHEN t.verification_score >= 50 AND t.verification_score < 80 THEN 1 ELSE 0 END) AS medium_quality,
                    sum(CASE WHEN t.verification_score < 50 THEN 1 ELSE 0 END) AS low_quality
                RETURN high_quality, medium_quality, low_quality
            """, hours=hours)

        vq_record = dict(vq_scores.single()) if vq_scores.single() else {}
        rework_record = dict(rework.single()) if rework.single() else {}
        split_record = dict(quality_split.single()) if quality_split.single() else {}

        return {
            "verification_scores": vq_record,
            "rework_analysis": rework_record,
            "quality_distribution": split_record,
        }

    def _generate_recommendations(
        self,
        summary: Dict,
        error_patterns: Dict,
        performance: Dict,
        quality: Dict,
        agent: Optional[str] = None
    ) -> List[Dict]:
        """Generate actionable recommendations based on analysis."""
        recommendations = []

        # Error-based recommendations
        for err in error_patterns.get("recurring_details", [])[:2]:
            recommendations.append({
                "type": "error_pattern",
                "priority": "HIGH" if err["occurrences"] >= 3 else "MEDIUM",
                "category": err["category"],
                "description": f"Recurring error pattern: {err['error_msg'][:100]}...",
                "occurrences": err["occurrences"],
                "affected_agents": err.get("affected_agents", []),
                "action": f"Investigate and fix root cause of {err['category']} errors",
            })

        # Performance-based recommendations
        for skill in performance.get("by_skill", [])[:2]:
            if skill.get("success_rate", 100) < 70:
                recommendations.append({
                    "type": "skill_performance",
                    "priority": "MEDIUM",
                    "skill": skill["skill"],
                    "description": f"Low success rate for {skill['skill']}: {skill['success_rate']:.1f}%",
                    "action": f"Review {skill['skill']} implementation and task routing",
                })

        # Quality-based recommendations
        rework_count = quality.get("rework_analysis", {}).get("rework_tasks", 0)
        total_tasks = summary.get("overall", {}).get("total_tasks", 1)
        if rework_count > 0 and rework_count / max(total_tasks, 1) > 0.1:
            recommendations.append({
                "type": "quality",
                "priority": "HIGH",
                "description": f"High rework rate: {rework_count}/{total_tasks} tasks ({100*rework_count/max(total_tasks,1):.1f}%)",
                "action": "Improve task verification and initial quality checks",
            })

        # Agent-specific recommendations
        if agent:
            agent_data = next(
                (a for a in performance.get("by_agent", []) if a["agent"] == agent),
                {}
            )
            if agent_data.get("success_rate", 100) < 80:
                recommendations.append({
                    "type": "agent_performance",
                    "priority": "HIGH",
                    "agent": agent,
                    "description": f"Low success rate for {agent}: {agent_data.get('success_rate', 0):.1f}%",
                    "action": f"Investigate {agent} task failures and improve configuration",
                })

        return recommendations

    # ============================================================
    # Daily Report Generation
    # ============================================================

    def generate_daily_report(self, date: Optional[str] = None) -> Dict:
        """Generate daily system report.

        Args:
            date: Date string (YYYY-MM-DD), or None for today

        Returns:
            Dict with daily summary including:
            - Task statistics
            - Agent performance
            - Error summary
            - Notable events
            - Trends vs previous day
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        # Parse date
        target_date = datetime.strptime(date, "%Y-%m-%d")
        start_dt = target_date.replace(hour=0, minute=0, second=0)
        end_dt = start_dt + timedelta(days=1)
        hours = 24

        # Get current day data
        current = self._get_day_statistics(start_dt, end_dt)

        # Get previous day for comparison
        prev_start = start_dt - timedelta(days=1)
        previous = self._get_day_statistics(prev_start, start_dt)

        # Calculate trends
        trends = self._calculate_trends(current, previous)

        return {
            "report_type": "daily",
            "date": date,
            "generated": datetime.now().isoformat(),
            "statistics": current,
            "trends": trends,
            "top_errors": self.reporter.get_error_clusters(hours=24, min_size=1)[:5],
            "agent_standouts": self._find_agent_standouts(start_dt, end_dt),
        }

    def _get_day_statistics(self, start_dt: datetime, end_dt: datetime) -> Dict:
        """Get statistics for a specific day."""
        with self.reporter.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.created >= datetime($start) AND t.created < datetime($end)
                RETURN
                    count(t) AS total_tasks,
                    sum(CASE WHEN t.status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed,
                    sum(CASE WHEN t.status = 'FAILED' THEN 1 ELSE 0 END) AS failed,
                    avg(t.actual_duration_seconds) AS avg_duration,
                    sum(t.total_tokens) AS total_tokens,
                    avg(t.verification_score) AS avg_quality,
                    sum(t.lines_added) AS total_lines_added
            """, start=start_dt.isoformat(), end=end_dt.isoformat())

            record = result.single()
            if not record:
                return {}

            return {
                "total_tasks": record["total_tasks"] or 0,
                "completed": record["completed"] or 0,
                "failed": record["failed"] or 0,
                "success_rate": (record["completed"] or 0) / max(record["total_tasks"] or 1, 1) * 100,
                "avg_duration_seconds": record["avg_duration"],
                "total_tokens": record["total_tokens"] or 0,
                "avg_quality_score": record["avg_quality"],
                "total_lines_added": record["total_lines_added"] or 0,
            }

    def _calculate_trends(self, current: Dict, previous: Dict) -> Dict:
        """Calculate trends between current and previous period."""
        trends = {}

        for key in ["total_tasks", "completed", "failed", "total_tokens"]:
            curr_val = current.get(key, 0) or 0
            prev_val = previous.get(key, 0) or 0
            if prev_val > 0:
                change = ((curr_val - prev_val) / prev_val) * 100
                trends[f"{key}_change"] = round(change, 1)
            else:
                trends[f"{key}_change"] = "N/A"

        # Success rate trend
        curr_rate = current.get("success_rate", 0) or 0
        prev_rate = previous.get("success_rate", 0) or 0
        trends["success_rate_change"] = round(curr_rate - prev_rate, 1)

        return trends

    def _find_agent_standouts(self, start_dt: datetime, end_dt: datetime) -> Dict:
        """Find best and worst performing agents."""
        with self.reporter.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.created >= datetime($start) AND t.created < datetime($end)
                RETURN
                    t.agent AS agent,
                    count(t) AS tasks,
                    100.0 * sum(CASE WHEN t.status = 'COMPLETED' THEN 1 ELSE 0 END) / count(t) AS success_rate,
                    avg(t.actual_duration_seconds) AS avg_duration
                ORDER BY tasks DESC
            """, start=start_dt.isoformat(), end=end_dt.isoformat())

            agents = [dict(r) for r in result]

            if not agents:
                return {}

            # Sort by success rate
            by_success = sorted(agents, key=lambda x: x.get("success_rate", 0) or 0, reverse=True)

            return {
                "highest_success_rate": by_success[0] if by_success else None,
                "lowest_success_rate": by_success[-1] if by_success else None,
                "most_tasks": max(agents, key=lambda x: x.get("tasks", 0)) if agents else None,
            }

    # ============================================================
    # Weekly Trend Analysis
    # ============================================================

    def generate_weekly_trends(self, days: int = 30) -> Dict:
        """Generate weekly trend analysis."""
        with self.reporter.driver.session() as session:
            # Daily trends
            daily = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({days: $days})
                WITH
                    date(t.created) AS day,
                    count(t) AS total,
                    sum(CASE WHEN t.status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed
                RETURN
                    day AS date,
                    total,
                    completed,
                    100.0 * completed / total AS success_rate
                ORDER BY day DESC
            """, days=days)

            # Weekly aggregation
            weekly = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({days: $days})
                WITH
                    date.truncate('week', t.created) AS week,
                    count(t) AS total,
                    sum(CASE WHEN t.status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed
                RETURN
                    week AS week_start,
                    total,
                    completed,
                    100.0 * completed / total AS success_rate
                ORDER BY week_start DESC
            """, days=days)

            # Error trends
            error_trends = session.run("""
                MATCH (t:Task)
                WHERE t.status = 'FAILED'
                  AND t.created > datetime() - duration({days: $days})
                  AND t.error_category IS NOT NULL
                WITH
                    date(t.created) AS day,
                    t.error_category AS category,
                    count(t) AS errors
                RETURN
                    day AS date,
                    category,
                    errors
                ORDER BY day DESC, errors DESC
            """, days=days)

        return {
            "period_days": days,
            "generated": datetime.now().isoformat(),
            "daily_trends": [dict(r) for r in daily],
            "weekly_aggregates": [dict(r) for r in weekly],
            "error_trends": [dict(r) for r in error_trends][:50],
        }

    # ============================================================
    # Export Functions
    # ============================================================

    def export_to_json(self, data: Dict, filepath: str):
        """Export data to JSON file."""
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        print(f"Exported to {filepath}")

    def export_reflection_csv(self, hours: int = 24, output_dir: str = None):
        """Export reflection data as CSV for external analysis."""
        import csv

        if output_dir is None:
            output_dir = "/Users/kublai/.openclaw/agents/main/logs/reports"

        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        # Get task-level data
        with self.reporter.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({hours: $hours})
                RETURN
                    t.task_id, t.agent, t.status, t.priority, t.skill_hint,
                    t.total_tokens, t.actual_duration_seconds, t.verification_score,
                    t.error_category, t.lines_added, t.created
                ORDER BY t.created DESC
            """, hours=hours)

            # Write CSV
            csv_path = f"{output_dir}/task_report_{timestamp}.csv"
            with open(csv_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "task_id", "agent", "status", "priority", "skill_hint",
                    "total_tokens", "duration_seconds", "verification_score",
                    "error_category", "lines_added", "created"
                ])
                for record in result:
                    writer.writerow([
                        record["t.task_id"],
                        record["t.agent"],
                        record["t.status"],
                        record["t.priority"],
                        record["t.skill_hint"],
                        record["t.total_tokens"],
                        record["t.actual_duration_seconds"],
                        record["t.verification_score"],
                        record["t.error_category"],
                        record["t.lines_added"],
                        record["t.created"],
                    ])

            print(f"Exported CSV to {csv_path}")


# ============================================================
# Main entry point
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Task Report Aggregator")
    parser.add_argument("--reflection", action="store_true", help="Generate reflection data")
    parser.add_argument("--daily-report", action="store_true", help="Generate daily report")
    parser.add_argument("--weekly-trends", action="store_true", help="Generate weekly trends")
    parser.add_argument("--agent", help="Specific agent name")
    parser.add_argument("--hours", type=int, default=1, help="Hours to look back")
    parser.add_argument("--days", type=int, default=30, help="Days to look back")
    parser.add_argument("--export", help="Export to JSON file path")
    parser.add_argument("--export-csv", action="store_true", help="Export data as CSV")

    args = parser.parse_args()

    aggregator = TaskReportAggregator()

    try:
        if args.reflection:
            data = aggregator.generate_reflection_data(args.agent, args.hours)
            if args.export:
                aggregator.export_to_json(data, args.export)
            else:
                print(json.dumps(data, indent=2, default=str))

        elif args.daily_report:
            data = aggregator.generate_daily_report()
            if args.export:
                aggregator.export_to_json(data, args.export)
            else:
                print(json.dumps(data, indent=2, default=str))

        elif args.weekly_trends:
            data = aggregator.generate_weekly_trends(args.days)
            if args.export:
                aggregator.export_to_json(data, args.export)
            else:
                print(json.dumps(data, indent=2, default=str))

        else:
            # Default: show reflection summary
            data = aggregator.generate_reflection_data(args.agent, args.hours)
            print(json.dumps(data, indent=2, default=str))

        if args.export_csv:
            aggregator.export_reflection_csv(args.hours)

    finally:
        aggregator.close()
