#!/usr/bin/env python3
"""
Hourly Reflection Data - Neo4j-powered metrics for Kurultai reflections

Usage in hourly_reflection.sh:
    python3 reflection_data.py --agent temujin --hours 1
    
Output: JSON with metrics for reflection template
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from neo4j_task_tracker import get_tracker

def get_agent_reflection(agent, hours=1):
    """Get reflection data for specific agent"""
    tracker = get_tracker()
    
    # Get task metrics
    task_data = tracker.get_reflection_data(agent, hours)
    
    # Get recent tasks
    try:
        recent_tasks = tracker.get_tasks_by_agent(agent, limit=5)
    except:
        recent_tasks = []
    
    # Get completion rate
    try:
        completion = tracker.get_completion_rate(hours * 24)
    except:
        completion = {}
    
    # Get continuous tasks
    try:
        continuous = tracker.get_continuous_tasks()
        agent_continuous = [t for t in continuous if t.get('agent') == agent]
    except:
        agent_continuous = []
    
    total = task_data.get('total_tasks', 0) or 0
    completed = task_data.get('completed', 0) or 0
    failed = task_data.get('failed', 0) or 0
    retries = task_data.get('total_retries', 0) or 0
    
    # Safe success rate calculation
    if total > 0:
        success_rate = f"{100 * completed / total:.1f}%"
    else:
        success_rate = "N/A (no tasks)"
    
    return {
        "agent": agent,
        "period_hours": hours,
        "tasks": {
            "total": total,
            "completed": completed,
            "failed": failed,
            "retries": retries,
            "avg_duration_seconds": task_data.get('avg_duration'),
            "success_rate": success_rate
        },
        "completion_rate_overall": completion,
        "continuous_tasks": len(agent_continuous),
        "recent_tasks": [
            {
                "label": t.get('label', 'unknown'),
                "status": t.get('status', 'unknown'),
                "task": t.get('task', '')[:50] if t.get('task') else 'No description',
                "duration": "completed" if t.get('completed') else "running"
            }
            for t in (recent_tasks or [])[:5]
        ]
    }

def get_kurultai_summary(hours=1, include_trends=False):
    """Get summary for all 6 agents"""
    tracker = get_tracker()
    
    # Get hourly summary by agent
    hourly = tracker.get_hourly_summary(hours)
    
    # Get overall completion rate
    try:
        completion = tracker.get_completion_rate(hours * 24)
    except:
        completion = {}
    
    # Get continuous tasks
    try:
        continuous = tracker.get_continuous_tasks()
    except:
        continuous = []
    
    result = {
        "period_hours": hours,
        "agents": hourly,
        "completion_rate": completion,
        "continuous_tasks_running": len(continuous),
        "total_tasks": sum(a.get('total', 0) for a in hourly),
        "total_completed": sum(a.get('completed', 0) for a in hourly),
        "total_failed": sum(a.get('failed', 0) for a in hourly)
    }
    
    # Add historical trends if requested
    if include_trends:
        try:
            result["trends"] = {
                "daily": tracker.get_historical_trends(7),
                "workload": tracker.get_agent_workload(7),
                "peak_hours": tracker.get_peak_hours(7),
                "bottlenecks": tracker.get_bottlenecks(24)
            }
        except Exception as e:
            result["trends_error"] = str(e)
    
    return result

def main():
    parser = argparse.ArgumentParser(description='Get reflection data')
    parser.add_argument('--agent', help='Specific agent (optional)')
    parser.add_argument('--hours', type=int, default=1, help='Hours to look back')
    parser.add_argument('--kurultai', action='store_true', help='Get all 6 agents summary')
    parser.add_argument('--trends', action='store_true', help='Include historical trends (7 days)')
    
    args = parser.parse_args()
    
    try:
        if args.kurultai:
            data = get_kurultai_summary(args.hours, include_trends=args.trends)
        elif args.agent:
            data = get_agent_reflection(args.agent, args.hours)
        else:
            data = get_kurultai_summary(args.hours, include_trends=args.trends)
        
        print(json.dumps(data, indent=2, default=str))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()
