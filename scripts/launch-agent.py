#!/usr/bin/env python3
"""
Persistent Agent Launcher

Launches Kurultai agents as persistent sessions with workspace initialization.

Usage:
    python3 launch-agent.py --agent temujin
    python3 launch-agent.py --all-agents
"""

import argparse
import json
import os
import sys
import subprocess
from datetime import datetime

AGENTS_DIR = "/Users/kublai/.openclaw/agents"

def load_agent_config(agent_name):
    """Load agent configuration"""
    config_path = f"{AGENTS_DIR}/{agent_name}/config.json"
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config not found: {config_path}")
    
    with open(config_path, 'r') as f:
        return json.load(f)

def initialize_workspace(agent_name, config):
    """Initialize agent workspace"""
    workspace_path = config.get('workspace_path', f"{AGENTS_DIR}/{agent_name}/workspace")
    memory_path = config.get('memory_path', f"{AGENTS_DIR}/{agent_name}/memory")
    
    # Create directories if they don't exist
    os.makedirs(workspace_path, exist_ok=True)
    os.makedirs(memory_path, exist_ok=True)
    
    # Create initial context file
    context_file = f"{memory_path}/context.md"
    if not os.path.exists(context_file):
        with open(context_file, 'w') as f:
            f.write(f"""# {agent_name.capitalize()} - Agent Context

**Role:** {config.get('agent_role', 'Agent')}
**Model:** {config.get('model', 'qwen3.5-plus')}
**Capabilities:** {', '.join(config.get('capabilities', []))}
**Created:** {datetime.now().isoformat()}

---

## Current Task

*No active task*

## Recent Work

*No recent work*

## Notes

*Agent workspace initialized*
""")
    
    print(f"✓ Workspace initialized: {workspace_path}")
    return True

def register_agent_state(agent_name, config):
    """Register agent in Neo4j"""
    try:
        from neo4j import GraphDatabase
        
        uri = "bolt://localhost:7687"
        user = "neo4j"
        password = "myStrongPassword123"
        
        driver = GraphDatabase.driver(uri, auth=(user, password))
        
        with driver.session() as session:
            session.run("""
                MATCH (a:AgentState {name: $name})
                SET a.status = 'starting',
                    a.last_heartbeat = datetime(),
                    a.started = datetime()
            """, name=agent_name)
        
        driver.close()
        print(f"✓ Agent registered in Neo4j: {agent_name}")
        return True
    except Exception as e:
        print(f"⚠ Neo4j registration failed: {e}")
        return False

def launch_agent(agent_name, config, mode="session"):
    """Launch agent as persistent session via sessions_spawn"""
    print(f"🚀 Launching {agent_name} ({config.get('model', 'qwen3.5-plus')})...")
    
    try:
        # Import OpenClaw sessions_spawn
        sys.path.insert(0, '/opt/homebrew/lib/node_modules/openclaw')
        from openclaw.tools import sessions_spawn
        
        # Prepare initial context
        initial_task = f"""You are {agent_name.capitalize()}, {config.get('agent_role', 'an AI agent')}.

**Capabilities:** {', '.join(config.get('capabilities', []))}

**Workspace:** {config.get('workspace_path')}
**Memory:** {config.get('memory_path')}
**Task Queue:** {config.get('task_queue_path')}

You are now running as a persistent agent. You will:
1. Monitor your task queue at {config.get('task_queue_path')}
2. Process tasks autonomously using agent-task-handler.py
3. Spawn subagents when needed for parallel work
4. Update your state in Neo4j (AgentState node)
5. Report completion status

Begin by acknowledging your role and checking for pending tasks."""
        
        # Actually call sessions_spawn
        result = sessions_spawn(
            task=initial_task,
            runtime="acp",
            mode=mode,
            label=f"{agent_name}-persistent",
            timeoutSeconds=0  # No timeout for persistent agents
        )
        
        print(f"✓ Agent launched successfully")
        print(f"  Session: {result.get('childSessionKey', 'unknown')}")
        print(f"  Run ID: {result.get('runId', 'unknown')}")
        
        # Update Neo4j state
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "myStrongPassword123"))
        
        with driver.session() as session:
            session.run("""
                MATCH (a:AgentState {name: $name})
                SET a.status = 'running',
                    a.session_key = $session_key,
                    a.run_id = $run_id,
                    a.last_heartbeat = datetime(),
                    a.started = datetime()
            """, name=agent_name, 
                session_key=result.get('childSessionKey'),
                run_id=result.get('runId'))
        
        driver.close()
        
        return {
            "agent": agent_name,
            "model": config.get('model'),
            "mode": mode,
            "status": "launched",
            "session_key": result.get('childSessionKey'),
            "run_id": result.get('runId'),
            "workspace": config.get('workspace_path'),
            "launched_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"✗ Launch failed: {e}")
        return {
            "agent": agent_name,
            "status": "failed",
            "error": str(e)
        }

def main():
    parser = argparse.ArgumentParser(description='Launch persistent Kurultai agents')
    parser.add_argument('--agent', help='Specific agent to launch')
    parser.add_argument('--all-agents', action='store_true', help='Launch all 6 agents')
    parser.add_argument('--mode', default='session', choices=['session', 'run'], 
                       help='Agent mode (session=persistent, run=one-shot)')
    
    args = parser.parse_args()
    
    if args.all_agents:
        agents = ['kublai', 'temujin', 'mongke', 'chagatai', 'jochi', 'ogedei']
    elif args.agent:
        agents = [args.agent]
    else:
        print("Usage: python3 launch-agent.py --agent <name> OR --all-agents")
        sys.exit(1)
    
    print(f"=== Launching {len(agents)} Agent(s) ===\n")
    
    launched = []
    for agent_name in agents:
        try:
            print(f"\n--- {agent_name.capitalize()} ---")
            
            # Load config
            config = load_agent_config(agent_name)
            
            # Initialize workspace
            initialize_workspace(agent_name, config)
            
            # Register in Neo4j
            register_agent_state(agent_name, config)
            
            # Launch agent
            result = launch_agent(agent_name, config, args.mode)
            launched.append(result)
            
        except Exception as e:
            print(f"✗ Failed to launch {agent_name}: {e}")
    
    print(f"\n=== Launch Summary ===")
    print(f"Launched: {len(launched)}/{len(agents)} agents")
    for agent in launched:
        print(f"  ✓ {agent['agent']} ({agent['model']}) - {agent['status']}")

if __name__ == "__main__":
    main()
