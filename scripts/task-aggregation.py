#!/usr/bin/env python3
"""
task-aggregation.py - Aggregate task metrics for reflection analysis

Queries Neo4j for task metrics and generates aggregated reports for:
- Hourly reflections (last 1 hour)
- Daily reflections (last 24 hours)
- Weekly analysis (last 7 days)
- Failure pattern analysis
- Performance trends
- Token usage patterns

Usage:
    python3 task-aggregation.py --hours 1 --agent temujin
    python3 task-aggregation.py --days 7 --output workspace/weekly-analysis.md
    python3 task-aggregation.py --failure-analysis --days 7
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import neo4j_session


def query_tasks(hours: Optional[float] = None, days: Optional[float] = None,
                agent: Optional[str] = None, status: Optional[str] = None) -> List[dict]:
    """Query tasks from Neo4j with filters."""
    time_clause = ""
    if hours:
        time_clause = f"t.created > datetime() - duration({{hours: {hours}}})"
    elif days:
        time_clause = f"t.created > datetime() - duration({{days: {days}}})"

    agent_clause = f"AND t.agent = '{agent}'" if agent else ""
    status_clause = f"AND t.status = '{status}'" if status else ""

    query = f"""
        MATCH (t:Task)
        WHERE {time_clause if time_clause else 'true'}
        {agent_clause}
        {status_clause}
        RETURN t
        ORDER BY t.created DESC
    """

    try:
        with neo4j_session() as session:
            result = session.run(query)
            tasks = []
            for record in result:
                task_data = dict(record['t'])
                tasks.append(task_data)
            return tasks
    except Exception as e:
        print(f"Query failed: {e}", file=sys.stderr)
        return []


def aggregate_basic_metrics(tasks: List[dict]) -> dict:
    """Calculate basic aggregated metrics."""
    if not tasks:
        return {
            'total_tasks': 0,
            'completed': 0,
            'failed': 0,
            'success_rate': 0.0,
            'avg_duration_seconds': 0,
            'total_retries': 0
        }

    total = len(tasks)
    completed = sum(1 for t in tasks if t.get('status') == 'completed')
    failed = sum(1 for t in tasks if t.get('status') in ['failed', 'timeou'])
    total_retries = sum(int(t.get('retry_count', 0)) for t in tasks)

    durations = [t.get('duration_seconds', 0) for t in tasks if t.get('duration_seconds')]
    avg_duration = sum(durations) / len(durations) if durations else 0

    return {
        'total_tasks': total,
        'completed': completed,
        'failed': failed,
        'success_rate': round(completed / total * 100, 2) if total > 0 else 0,
        'avg_duration_seconds': round(avg_duration, 1),
        'total_retries': total_retries,
        'avg_retries_per_task': round(total_retries / total, 2) if total > 0 else 0
    }


def aggregate_token_usage(tasks: List[dict]) -> dict:
    """Aggregate token usage metrics."""
    total_input = sum(int(t.get('input_tokens', 0)) for t in tasks)
    total_output = sum(int(t.get('output_tokens', 0)) for t in tasks)
    total_tokens = total_input + total_output

    tasks_with_tokens = [t for t in tasks if t.get('total_tokens', 0) > 0]

    return {
        'total_input_tokens': total_input,
        'total_output_tokens': total_output,
        'total_tokens': total_tokens,
        'avg_tokens_per_task': round(total_tokens / len(tasks_with_tokens)) if tasks_with_tokens else 0,
        'tasks_with_token_data': len(tasks_with_tokens),
        'token_data_coverage': round(len(tasks_with_tokens) / len(tasks) * 100, 1) if tasks else 0
    }


def aggregate_code_metrics(tasks: List[dict]) -> dict:
    """Aggregate code/content metrics."""
    total_files = sum(int(t.get('files_created', 0)) for t in tasks)
    total_lines = sum(int(t.get('lines_added', 0)) for t in tasks)
    total_functions = sum(int(t.get('functions_count', 0)) for t in tasks)
    total_classes = sum(int(t.get('classes_count', 0)) for t in tasks)
    total_tests = sum(int(t.get('tests_count', 0)) for t in tasks)
    total_docs = sum(int(t.get('docs_count', 0)) for t in tasks)

    tasks_with_code = [t for t in tasks if t.get('files_created', 0) > 0]

    return {
        'total_files_created': total_files,
        'total_lines_added': total_lines,
        'total_functions': total_functions,
        'total_classes': total_classes,
        'total_tests': total_tests,
        'total_docs': total_docs,
        'tasks_with_deliverables': len(tasks_with_code),
        'deliverable_rate': round(len(tasks_with_code) / len(tasks) * 100, 1) if tasks else 0,
        'avg_lines_per_task': round(total_lines / len(tasks_with_code)) if tasks_with_code else 0
    }


def aggregate_error_patterns(tasks: List[dict]) -> dict:
    """Analyze error patterns and categories."""
    failed_tasks = [t for t in tasks if t.get('status') in ['failed', 'timeout']]

    error_categories = defaultdict(int)
    error_hashes = defaultdict(list)

    for task in failed_tasks:
        category = task.get('error_category', 'unknown')
        error_categories[category] += 1

        error_hash = task.get('error_hash')
        if error_hash:
            error_hashes[error_hash].append({
                'task_id': task.get('task_id'),
                'title': task.get('title', '')[:50]
            })

    # Find most common error patterns
    common_errors = sorted(error_hashes.items(), key=lambda x: len(x[1]), reverse=True)[:5]

    return {
        'total_failures': len(failed_tasks),
        'error_categories': dict(error_categories),
        'common_error_patterns': [
            {'hash': h, 'count': len(tasks), 'examples': tasks[:3]}
            for h, tasks in common_errors
        ],
        'unique_errors': len(error_hashes)
    }


def aggregate_agent_performance(tasks: List[dict]) -> dict:
    """Break down performance by agent."""
    agent_metrics = defaultdict(lambda: {
        'total': 0, 'completed': 0, 'failed': 0,
        'total_duration': 0, 'total_tokens': 0, 'total_files': 0
    })

    for task in tasks:
        agent = task.get('agent', 'unknown')
        agent_metrics[agent]['total'] += 1

        if task.get('status') == 'completed':
            agent_metrics[agent]['completed'] += 1
        elif task.get('status') in ['failed', 'timeout']:
            agent_metrics[agent]['failed'] += 1

        agent_metrics[agent]['total_duration'] += task.get('duration_seconds', 0)
        agent_metrics[agent]['total_tokens'] += task.get('total_tokens', 0)
        agent_metrics[agent]['total_files'] += task.get('files_created', 0)

    # Calculate rates
    result = {}
    for agent, metrics in agent_metrics.items():
        result[agent] = {
            'total_tasks': metrics['total'],
            'completed': metrics['completed'],
            'failed': metrics['failed'],
            'success_rate': round(metrics['completed'] / metrics['total'] * 100, 1) if metrics['total'] > 0 else 0,
            'avg_duration_seconds': round(metrics['total_duration'] / metrics['total'], 1) if metrics['total'] > 0 else 0,
            'total_tokens': metrics['total_tokens'],
            'total_files': metrics['total_files']
        }

    return result


def aggregate_hourly_trends(tasks: List[dict]) -> dict:
    """Analyze hourly task distribution."""
    hourly_counts = defaultdict(int)
    hourly_success = defaultdict(int)

    for task in tasks:
        created = task.get('created')
        if created:
            try:
                if hasattr(created, 'hour'):
                    hour = created.hour
                else:
                    hour = int(str(created).split('T')[1].split(':')[0])
                hourly_counts[hour] += 1
                if task.get('status') == 'completed':
                    hourly_success[hour] += 1
            except Exception:
                pass

    return {
        'tasks_by_hour': dict(hourly_counts),
        'success_by_hour': dict(hourly_success),
        'peak_hour': max(hourly_counts, key=hourly_counts.get) if hourly_counts else None,
        'peak_hour_count': max(hourly_counts.values()) if hourly_counts else 0
    }


def aggregate_skill_usage(tasks: List[dict]) -> dict:
    """Analyze skill hint usage and effectiveness."""
    skill_metrics = defaultdict(lambda: {'total': 0, 'completed': 0, 'failed': 0, 'avg_duration': 0, 'durations': []})

    for task in tasks:
        skill = task.get('skill_hint', 'none') or 'none'
        skill_metrics[skill]['total'] += 1

        if task.get('status') == 'completed':
            skill_metrics[skill]['completed'] += 1
        elif task.get('status') in ['failed', 'timeout']:
            skill_metrics[skill]['failed'] += 1

        duration = task.get('duration_seconds', 0)
        if duration > 0:
            skill_metrics[skill]['durations'].append(duration)

    # Calculate averages
    result = {}
    for skill, metrics in skill_metrics.items():
        durations = metrics['durations']
        result[skill] = {
            'total_tasks': metrics['total'],
            'completed': metrics['completed'],
            'failed': metrics['failed'],
            'success_rate': round(metrics['completed'] / metrics['total'] * 100, 1) if metrics['total'] > 0 else 0,
            'avg_duration_seconds': round(sum(durations) / len(durations)) if durations else 0
        }

    return result


def generate_reflection_report(aggregations: dict, period: str, agent: Optional[str] = None) -> str:
    """Generate markdown report for reflection."""
    report = f"""# Task Aggregation Report

**Period:** {period}
**Agent:** {agent or 'all'}
**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Executive Summary

"""

    basic = aggregations.get('basic_metrics', {})
    report += f"""- **Total Tasks:** {basic.get('total_tasks', 0)}
- **Completed:** {basic.get('completed', 0)} ({basic.get('success_rate', 0)}%)
- **Failed:** {basic.get('failed', 0)}
- **Average Duration:** {basic.get('avg_duration_seconds', 0):.0f}s ({basic.get('avg_duration_seconds', 0)/60:.1f}m)
- **Total Retries:** {basic.get('total_retries', 0)}

"""

    # Token usage
    tokens = aggregations.get('token_usage', {})
    if tokens.get('total_tokens', 0) > 0:
        report += f"""## Token Usage

- **Total Tokens:** {tokens.get('total_tokens', 0):,}
- **Input:** {tokens.get('total_input_tokens', 0):,}
- **Output:** {tokens.get('total_output_tokens', 0):,}
- **Avg per Task:** {tokens.get('avg_tokens_per_task', 0):,}
- **Coverage:** {tokens.get('token_data_coverage', 0)}%

"""

    # Code metrics
    code = aggregations.get('code_metrics', {})
    if code.get('total_files_created', 0) > 0:
        report += f"""## Code & Deliverables

- **Files Created:** {code.get('total_files_created', 0)}
- **Lines Added:** {code.get('total_lines_added', 0)}
- **Functions:** {code.get('total_functions', 0)}
- **Classes:** {code.get('total_classes', 0)}
- **Tests:** {code.get('total_tests', 0)}
- **Documentation:** {code.get('total_docs', 0)}
- **Deliverable Rate:** {code.get('deliverable_rate', 0)}%

"""

    # Error patterns
    errors = aggregations.get('error_patterns', {})
    if errors.get('total_failures', 0) > 0:
        report += f"""## Error Analysis

- **Total Failures:** {errors.get('total_failures', 0)}
- **Unique Errors:** {errors.get('unique_errors', 0)}

### Error Categories
"""
        for category, count in errors.get('error_categories', {}).items():
            report += f"- **{category}:** {count}\n"

        if errors.get('common_error_patterns'):
            report += "\n### Common Error Patterns\n"
            for pattern in errors['common_error_patterns'][:3]:
                report += f"- **{pattern['hash']}** ({pattern['count']}x)\n"
                for ex in pattern['examples']:
                    report += f"  - `{ex['task_id']}`: {ex['title']}\n"
        report += "\n"

    # Agent performance
    agent_perf = aggregations.get('agent_performance', {})
    if len(agent_perf) > 1:
        report += """## Performance by Agent

| Agent | Tasks | Success Rate | Avg Duration | Tokens |
|-------|-------|--------------|--------------|--------|
"""
        for agent_name, metrics in sorted(agent_perf.items(), key=lambda x: x[1]['total_tasks'], reverse=True):
            report += f"| {agent_name} | {metrics['total_tasks']} | {metrics['success_rate']}% | {metrics['avg_duration_seconds']:.0f}s | {metrics['total_tokens']:,} |\n"
        report += "\n"

    # Skill usage
    skills = aggregations.get('skill_usage', {})
    if skills:
        report += """## Skill Usage

| Skill | Tasks | Success Rate | Avg Duration |
|-------|-------|--------------|--------------|
"""
        for skill, metrics in sorted(skills.items(), key=lambda x: x[1]['total_tasks'], reverse=True)[:10]:
            report += f"| {skill} | {metrics['total_tasks']} | {metrics['success_rate']}% | {metrics['avg_duration_seconds']:.0f}s |\n"
        report += "\n"

    # Hourly trends
    hourly = aggregations.get('hourly_trends', {})
    if hourly.get('tasks_by_hour'):
        report += """## Hourly Distribution

```
Hour  | Tasks | Success Rate
------+-------+------------
"""
        for hour in range(24):
            count = hourly['tasks_by_hour'].get(hour, 0)
            success = hourly['success_by_hour'].get(hour, 0)
            rate = round(success / count * 100, 1) if count > 0 else 0
            if count > 0:
                report += f"{hour:02d}:00 | {count:5} | {rate}%\n"
        report += "```\n\n"

    # Recommendations
    report += """## Reflection Prompts

1. **Performance:** What factors contributed to the success rate of """ + f"{basic.get('success_rate', 0)}%" + """?
2. **Efficiency:** Are there tasks that took longer than expected? What caused delays?
3. **Errors:** What patterns emerge from the failure analysis? What preventive measures could help?
4. **Token Usage:** Is token efficiency aligned with task complexity?
5. **Deliverables:** Does the deliverable rate meet expectations?

---

*Generated by task-aggregation.py*
"""

    return report


def main():
    parser = argparse.ArgumentParser(description='Aggregate task metrics for reflection')
    parser.add_argument('--hours', type=float, help='Last N hours')
    parser.add_argument('--days', type=float, help='Last N days')
    parser.add_argument('--agent', type=str, help='Filter by agent')
    parser.add_argument('--status', type=str, help='Filter by status')
    parser.add_argument('--output', type=str, help='Output file path')
    parser.add_argument('--failure-analysis', action='store_true', help='Focus on failure analysis')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--period-label', type=str, default='custom', help='Period label for report')

    args = parser.parse_args()

    if not args.hours and not args.days:
        args.hours = 1  # Default to 1 hour

    period = f"{args.hours} hour(s)" if args.hours else f"{args.days} day(s)"
    if args.period_label != 'custom':
        period = args.period_label

    # Query tasks
    tasks = query_tasks(hours=args.hours, days=args.days, agent=args.agent, status=args.status)

    if not tasks:
        print(f"No tasks found for {period}", file=sys.stderr)
        return

    print(f"Aggregating {len(tasks)} tasks from {period}...")

    # Run aggregations
    aggregations = {
        'basic_metrics': aggregate_basic_metrics(tasks),
        'token_usage': aggregate_token_usage(tasks),
        'code_metrics': aggregate_code_metrics(tasks),
        'error_patterns': aggregate_error_patterns(tasks),
        'agent_performance': aggregate_agent_performance(tasks),
        'hourly_trends': aggregate_hourly_trends(tasks),
        'skill_usage': aggregate_skill_usage(tasks),
        'task_count': len(tasks),
        'period': period,
        'generated_at': datetime.now().isoformat()
    }

    # Output
    if args.json:
        output = json.dumps(aggregations, indent=2, default=str)
    else:
        output = generate_reflection_report(aggregations, period, args.agent)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output)
        print(f"Report saved to: {output_path}")
    else:
        print(output)


if __name__ == '__main__':
    main()
