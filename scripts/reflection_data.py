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
    recent_tasks = tracker.get_tasks_by_agent(agent, limit=5)
    
    # Get completion rate
    completion = tracker.get_completion_rate(hours * 24)
    
    # Get continuous tasks
    continuous = tracker.get_continuous_tasks()
    agent_continuous = [t for t in continuous if t.get('agent') == agent]
    
    return {
        "agent": agent,
        "period_hours": hours,
        "tasks": {
            "total": task_data.get('total_tasks', 0),
            "completed": task_data.get('completed', 0),
            "failed": task_data.get('failed', 0),
            "retries": task_data.get('total_retries', 0),
            "avg_duration_seconds": task_data.get('avg_duration'),
            "success_rate": f"{100 * task_data.get('completed', 0) / max(task_data.get('total_tasks', 1), 1):.1f}%"
        },
        "completion_rate_overall": completion,
        "continuous_tasks": len(agent_continuous),
        "recent_tasks": [
            {
                "label": t.get('label'),
                "status": t.get('status'),
                "task": t.get('task', '')[:50],
                "duration": t.get('completed') and t.get('created') and "completed" or "running"
            }
            for t in recent_tasks
        ]
    }

def get_kurultai_summary(hours=1):
    """Get summary for all 6 agents"""
    tracker = get_tracker()
    
    # Get hourly summary by agent
    hourly = tracker.get_hourly_summary(hours)
    
    # Get overall completion rate
    completion = tracker.get_completion_rate(hours * 24)
    
    # Get continuous tasks
    continuous = tracker.get_continuous_tasks()
    
    return {
        "period_hours": hours,
        "agents": hourly,
        "completion_rate": completion,
        "continuous_tasks_running": len(continuous),
        "total_tasks": sum(a.get('total', 0) for a in hourly),
        "total_completed": sum(a.get('completed', 0) for a in hourly),
        "total_failed": sum(a.get('failed', 0) for a in hourly)
    }

def main():
    parser = argparse.ArgumentParser(description='Get reflection data')
    parser.add_argument('--agent', help='Specific agent (optional)')
    parser.add_argument('--hours', type=int, default=1, help='Hours to look back')
    parser.add_argument('--kurultai', action='store_true', help='Get all 6 agents summary')
    
    args = parser.parse_args()
    
    try:
        if args.kurultai:
            data = get_kurultai_summary(args.hours)
        elif args.agent:
            data = get_agent_reflection(args.agent, args.hours)
        else:
            data = get_kurultai_summary(args.hours)
        
        print(json.dumps(data, indent=2, default=str))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()
