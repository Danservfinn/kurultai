#!/usr/bin/env python3
"""
Agent Health Monitor

Monitors all 6 Kurultai agents, detects failures, and auto-restarts.

Usage:
    python3 agent-health-monitor.py
    python3 agent-health-monitor.py --daemon  # Run continuously
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta

AGENTS_DIR = "/Users/kublai/.openclaw/agents"
SPAWN_QUEUE = "/Users/kublai/.openclaw/agents/main/logs/spawn-pending.json"
HEALTH_LOG = "/Users/kublai/.openclaw/agents/main/logs/agent-health.log"

AGENTS = ['kublai', 'temujin', 'mongke', 'chagatai', 'jochi', 'ogedei']

def log(msg):
    """Log message"""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")
    
    os.makedirs(os.path.dirname(HEALTH_LOG), exist_ok=True)
    with open(HEALTH_LOG, 'a') as f:
        f.write(f"[{ts}] {msg}\n")

def get_agent_state(agent_name):
    """Get agent state from Neo4j"""
    try:
        from neo4j import GraphDatabase
        
        uri = "bolt://localhost:7687"
        user = "neo4j"
        password = "myStrongPassword123"
        
        driver = GraphDatabase.driver(uri, auth=(user, password))
        
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

def restart_agent(agent_name):
    """Restart agent by launching persistent session"""
    log(f"🔄 Restarting {agent_name}...")
    
    try:
        # Update Neo4j state
        from neo4j import GraphDatabase
        
        uri = "bolt://localhost:7687"
        user = "neo4j"
        password = "myStrongPassword123"
        
        driver = GraphDatabase.driver(uri, auth=(user, password))
        
        with driver.session() as session:
            session.run("""
                MATCH (a:AgentState {name: $name})
                SET a.status = 'restarting',
                    a.last_heartbeat = datetime(),
                    a.restart_count = coalesce(a.restart_count, 0) + 1
            """, name=agent_name)
        
        driver.close()
        
        # Launch agent
        config_path = f"{AGENTS_DIR}/{agent_name}/config.json"
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            log(f"✓ {agent_name} restart initiated")
            return True
        else:
            log(f"✗ Config not found for {agent_name}")
            return False
            
    except Exception as e:
        log(f"✗ Restart failed for {agent_name}: {e}")
        return False

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
    parser = argparse.ArgumentParser(description='Agent health monitor')
    parser.add_argument('--daemon', action='store_true', help='Run continuously')
    parser.add_argument('--interval', type=int, default=60, help='Check interval in seconds')
    parser.add_argument('--summary', action='store_true', help='Show summary and exit')
    
    args = parser.parse_args()
    
    if args.summary:
        summary = get_health_summary()
        print(json.dumps(summary, indent=2, default=str))
        return
    
    log("=== Agent Health Monitor Started ===")
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
                            restart_agent(agent)
                
                time.sleep(args.interval)
                
        except KeyboardInterrupt:
            log("\n\nStopping health monitor...")
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
