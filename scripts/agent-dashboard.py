#!/usr/bin/env python3
"""
Agent Dashboard

Shows real-time status, workload, and performance metrics for all 6 Kurultai agents.

Usage:
    python3 agent-dashboard.py
    python3 agent-dashboard.py --watch  # Auto-refresh every 5s
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agents_config import AGENTS, AGENT_ROLES
from kurultai_paths import AGENTS_DIR as _AGENTS_DIR, LOGS_DIR

AGENTS_DIR = str(_AGENTS_DIR)
METRICS_FILE = str(LOGS_DIR / "heartbeat_metrics.jsonl")

def get_agent_state(agent_name):
    """Get agent state from Neo4j"""
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from neo4j_task_tracker import neo4j_session

        with neo4j_session() as session:
            result = session.run("""
                MATCH (a:AgentState {name: $name})
                RETURN a.status AS status,
                       a.current_task AS task,
                       a.last_heartbeat AS heartbeat,
                       a.tasks_completed AS completed,
                       a.subagents_spawned AS spawned,
                       a.created AS created
            """, name=agent_name)
            
            record = result.single()
            
            if record:
                return {
                    "status": record["status"] or "unknown",
                    "task": record["task"],
                    "heartbeat": record["heartbeat"],
                    "completed": record["completed"] or 0,
                    "spawned": record["spawned"] or 0,
                    "created": record["created"]
                }
            else:
                return {"status": "not_found"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

def get_pending_tasks(agent_name):
    """Get count of pending tasks for agent"""
    task_queue_path = f"{AGENTS_DIR}/{agent_name}/tasks"
    
    if not os.path.exists(task_queue_path):
        return 0
    
    count = 0
    for f in os.listdir(task_queue_path):
        if f.endswith('.md') and not f.endswith('.executing.md') and not f.endswith('.done.md'):
            count += 1
    
    return count

def get_metrics_summary(hours=24):
    """Get metrics summary from heartbeat_metrics.jsonl"""
    if not os.path.exists(METRICS_FILE):
        return {"total_executions": 0, "local_count": 0, "cloud_count": 0}
    
    cutoff = datetime.now() - timedelta(hours=hours)
    
    total = 0
    local = 0
    cloud = 0
    local_success = 0
    cloud_success = 0
    
    try:
        with open(METRICS_FILE, 'r') as f:
            for line in f:
                try:
                    m = json.loads(line)
                    metric_time = datetime.fromisoformat(m.get('timestamp', '2000-01-01'))
                    
                    if metric_time >= cutoff:
                        total += 1
                        
                        if m.get('is_local'):
                            local += 1
                            if m.get('success'):
                                local_success += 1
                        else:
                            cloud += 1
                            if m.get('success'):
                                cloud_success += 1
                except:
                    pass
    except:
        pass
    
    return {
        "period_hours": hours,
        "total_executions": total,
        "local": {
            "count": local,
            "success_rate": f"{100 * local_success / max(local, 1):.1f}%"
        },
        "cloud": {
            "count": cloud,
            "success_rate": f"{100 * cloud_success / max(cloud, 1):.1f}%"
        }
    }

def render_dashboard():
    """Render agent dashboard"""
    print("\n" + "="*70)
    print("  KURULTAI AGENT DASHBOARD")
    print("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("="*70 + "\n")
    
    # Agent status table
    print("AGENT STATUS")
    print("-"*70)
    print(f"{'Agent':<12} {'Role':<20} {'Status':<10} {'Task':<25} {'Pending'}")
    print("-"*70)
    
    for agent in AGENTS:
        state = get_agent_state(agent)
        pending = get_pending_tasks(agent)
        
        role = AGENT_ROLES.get(agent, 'Agent')[:20]
        status = state.get('status', 'unknown')[:10]
        task = (state.get('task') or 'none')[:25]
        
        status_icon = "✓" if status == "idle" else "●" if status == "busy" else "✗"
        
        print(f"{status_icon} {agent:<10} {role:<20} {status:<10} {task:<25} {pending}")
    
    print()
    
    # Metrics summary
    metrics = get_metrics_summary(24)
    print("METRICS (Last 24 Hours)")
    print("-"*70)
    print(f"Total Executions: {metrics['total_executions']}")
    print(f"Local LLM: {metrics['local']['count']} ({metrics['local']['success_rate']} success)")
    print(f"Cloud LLM: {metrics['cloud']['count']} ({metrics['cloud']['success_rate']} success)")
    print()

def main():
    parser = argparse.ArgumentParser(description='Agent dashboard')
    parser.add_argument('--watch', action='store_true', help='Auto-refresh every 5s')
    
    args = parser.parse_args()
    
    if args.watch:
        import time
        print("Watching (Ctrl+C to stop)...\n")
        try:
            while True:
                os.system('clear' if os.name != 'nt' else 'cls')
                render_dashboard()
                time.sleep(5)
        except KeyboardInterrupt:
            print("\n\nStopping watch...")
    else:
        render_dashboard()

if __name__ == "__main__":
    main()
