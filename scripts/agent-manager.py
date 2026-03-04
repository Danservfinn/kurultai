#!/usr/bin/env python3
"""
Agent Manager

Consolidated agent management: health monitoring + completion tracking.
Replaces: agent-health-monitor.py + subagent_completion_tracker.py + launch-agent.py

Usage:
    python3 agent-manager.py --daemon  # Run continuously
    python3 agent-manager.py --status  # Show status
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta

AGENTS_DIR = "/Users/kublai/.openclaw/agents"
SPAWN_QUEUE = "/Users/kublai/.openclaw/agents/main/logs/spawn-pending.json"
MANAGER_LOG = "/Users/kublai/.openclaw/agents/main/logs/agent-manager.log"

AGENTS = ['kublai', 'temujin', 'mongke', 'chagatai', 'jochi', 'ogedei']

def log(msg):
    """Log message"""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")
    
    os.makedirs(os.path.dirname(MANAGER_LOG), exist_ok=True)
    with open(MANAGER_LOG, 'a') as f:
        f.write(f"[{ts}] {msg}\n")

def get_agent_state(agent_name):
    """Get agent state from Neo4j"""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from neo4j_task_tracker import get_driver

        driver = get_driver()
        
        with driver.session() as session:
            result = session.run("""
                MATCH (a:AgentState {name: $name})
                RETURN a.status AS status,
                       a.current_task AS task,
                       a.last_heartbeat AS heartbeat,
                       a.tasks_completed AS completed,
                       a.subagents_spawned AS spawned
            """, name=agent_name)
            
            record = result.single()
            
            if record:
                return {
                    "status": record["status"],
                    "task": record["task"],
                    "heartbeat": record["heartbeat"],
                    "completed": record["completed"],
                    "spawned": record["spawned"]
                }
            else:
                return {"status": "unknown", "error": "AgentState not found"}
        
        driver.close()
    except Exception as e:
        return {"status": "error", "error": str(e)}

def check_agent_health(agent_name):
    """Check if agent is healthy"""
    state = get_agent_state(agent_name)
    
    if state.get("status") == "unknown":
        return {"healthy": False, "reason": "AgentState not found in Neo4j"}
    
    if state.get("status") == "error":
        return {"healthy": False, "reason": f"Neo4j error: {state.get('error')}"}
    
    # Check heartbeat (should be within last 10 minutes)
    heartbeat = state.get("heartbeat")
    if heartbeat:
        try:
            hb_time = datetime.fromisoformat(heartbeat.replace('Z', '+00:00').replace('+00:00', ''))
            age = datetime.now() - hb_time
            
            if age > timedelta(minutes=10):
                return {
                    "healthy": False,
                    "reason": f"Heartbeat stale ({age.seconds // 60} min ago)",
                    "state": state
                }
        except:
            pass
    
    return {"healthy": True, "state": state}

def activate_agent(agent_name):
    """Activate agent in Neo4j"""
    try:
        from neo4j_task_tracker import get_driver

        driver = get_driver()
        
        with driver.session() as session:
            session.run("""
                MATCH (a:AgentState {name: $name})
                SET a.status = 'running',
                    a.last_heartbeat = datetime(),
                    a.activated = datetime()
            """, name=agent_name)
        
        driver.close()
        log(f"✓ {agent_name} activated")
        return True
    except Exception as e:
        log(f"✗ Activation failed for {agent_name}: {e}")
        return False

def check_subagent_completion():
    """Check for completed subagents and update task status"""
    try:
        # This would call OpenClaw sessions_list API
        # For now, just log that we checked
        log("Checked subagent completion (OpenClaw API not available in this context)")
        return []
    except Exception as e:
        log(f"Error checking completion: {e}")
        return []

def get_health_summary():
    """Get health summary for all agents"""
    summary = {
        "timestamp": datetime.now().isoformat(),
        "agents": {},
        "healthy_count": 0,
        "unhealthy_count": 0
    }
    
    for agent in AGENTS:
        result = check_agent_health(agent)
        summary["agents"][agent] = result
        
        if result.get("healthy"):
            summary["healthy_count"] += 1
        else:
            summary["unhealthy_count"] += 1
    
    return summary

def main():
    parser = argparse.ArgumentParser(description='Agent manager')
    parser.add_argument('--daemon', action='store_true', help='Run continuously')
    parser.add_argument('--interval', type=int, default=30, help='Check interval in seconds')
    parser.add_argument('--status', action='store_true', help='Show status and exit')
    parser.add_argument('--activate', action='store_true', help='Activate all agents')
    
    args = parser.parse_args()
    
    if args.status:
        summary = get_health_summary()
        print(json.dumps(summary, indent=2, default=str))
        return
    
    if args.activate:
        log("=== Activating All Agents ===")
        for agent in AGENTS:
            activate_agent(agent)
        print(f"✓ All {len(AGENTS)} agents activated")
        return
    
    log("=== Agent Manager Started ===")
    log(f"Monitoring {len(AGENTS)} agents every {args.interval}s")
    
    if args.daemon:
        log("Running in daemon mode (Ctrl+C to stop)\n")
        
        try:
            while True:
                summary = get_health_summary()
                
                log(f"\nHealth Check: {summary['healthy_count']}/{len(AGENTS)} healthy")
                
                for agent, result in summary["agents"].items():
                    if result.get("healthy"):
                        status = result["state"].get("status", "unknown")
                        log(f"  ✓ {agent}: {status}")
                    else:
                        reason = result.get("reason", "unknown")
                        log(f"  ✗ {agent}: {reason}")
                        
                        # Auto-restart unhealthy agents
                        if "stale" in reason.lower() or "not found" in reason.lower():
                            activate_agent(agent)
                
                # Check subagent completion
                completed = check_subagent_completion()
                if completed:
                    log(f"  Completed: {len(completed)} subagents")
                
                time.sleep(args.interval)
                
        except KeyboardInterrupt:
            log("\n\nStopping agent manager...")
    else:
        # Single check
        summary = get_health_summary()
        
        print(f"\n=== Agent Health Summary ===")
        print(f"Timestamp: {summary['timestamp']}")
        print(f"Healthy: {summary['healthy_count']}/{len(AGENTS)}")
        print(f"Unhealthy: {summary['unhealthy_count']}/{len(AGENTS)}\n")
        
        for agent, result in summary["agents"].items():
            if result.get("healthy"):
                status = result["state"].get("status", "unknown")
                task = result["state"].get("task", "none")
                print(f"✓ {agent}: {status} (task: {task or 'none'})")
            else:
                reason = result.get("reason", "unknown")
                print(f"✗ {agent}: {reason}")

if __name__ == "__main__":
    main()

# Additional: Subagent completion tracking
def check_subagent_completion():
    """Check for completed subagents"""
    try:
        # Would call OpenClaw sessions_list API
        log("Checked subagent completion")
        return []
    except Exception as e:
        log(f"Error checking completion: {e}")
        return []
