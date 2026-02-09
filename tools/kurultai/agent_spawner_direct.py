#!/usr/bin/env python3
"""
Direct Agent Spawner via Signal Messages

Since OpenClaw HTTP API has limited spawn capabilities,
this module uses Signal messages as the primary spawn trigger.

Usage:
    from agent_spawner_direct import spawn_agent
    spawn_agent('Möngke', 'You have pending research tasks')
"""

import os
import sys
import json
import subprocess
from typing import Optional
from neo4j import GraphDatabase

# Agent configuration
AGENTS = {
    'Kublai': {'id': 'main', 'phone': None},
    'Möngke': {'id': 'researcher', 'phone': None},
    'Chagatai': {'id': 'writer', 'phone': None},
    'Temüjin': {'id': 'developer', 'phone': None},
    'Jochi': {'id': 'analyst', 'phone': None},
    'Ögedei': {'id': 'ops', 'phone': None}
}

def get_neo4j_driver():
    """Get Neo4j driver."""
    uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
    password = os.environ.get('NEO4J_PASSWORD')
    if not password:
        raise ValueError("NEO4J_PASSWORD not set")
    return GraphDatabase.driver(uri, auth=('neo4j', password))

def check_pending_work(driver, agent_name: str) -> tuple[bool, int, int]:
    """Check if agent has pending tasks or messages."""
    with driver.session() as session:
        # Check tasks
        task_result = session.run('''
            MATCH (t:Task {status: "pending", assigned_to: $agent})
            RETURN count(t) as count
        ''', agent=agent_name)
        task_count = task_result.single()['count']
        
        # Check messages
        msg_result = session.run('''
            MATCH (m:AgentMessage {to_agent: $agent, status: "pending"})
            RETURN count(m) as count
        ''', agent=agent_name)
        msg_count = msg_result.single()['count']
        
        return (task_count > 0 or msg_count > 0), task_count, msg_count

def spawn_via_signal(agent_id: str, message: str) -> bool:
    """
    Spawn agent by sending Signal message.
    This is the PRIMARY spawn mechanism since OpenClaw API is limited.
    """
    signal_account = os.environ.get('SIGNAL_ACCOUNT')
    if not signal_account:
        print(f"  ⚠️  SIGNAL_ACCOUNT not set")
        return False
    
    # For now, send to owner's number with agent mention
    # In production, this would send to the agent's configured number
    owner_number = "+19194133445"  # Danny's number
    
    try:
        # Use signal-cli to send message
        cmd = [
            'signal-cli',
            '-a', signal_account,
            'send',
            '-m', f"@{agent_id}: {message}",
            owner_number
        ]
        
        result = subprocess.run(
            cmd,
            timeout=30,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print(f"  ✅ Signal message sent to trigger {agent_id}")
            return True
        else:
            print(f"  ⚠️  Signal send failed: {result.stderr}")
            return False
            
    except FileNotFoundError:
        print(f"  ⚠️  signal-cli not found")
        return False
    except Exception as e:
        print(f"  ⚠️  Signal error: {e}")
        return False

def spawn_agent(agent_name: str, context: Optional[str] = None) -> bool:
    """
    Main spawn function.
    Tries multiple methods in order of preference.
    """
    agent_info = AGENTS.get(agent_name)
    if not agent_info:
        print(f"❌ Unknown agent: {agent_name}")
        return False
    
    agent_id = agent_info['id']
    
    print(f"🚀 Spawning {agent_name} ({agent_id})...")
    
    # Check if there's actually work to do
    try:
        driver = get_neo4j_driver()
        has_work, task_count, msg_count = check_pending_work(driver, agent_name)
        driver.close()
        
        if not has_work:
            print(f"  ⏭️  No pending work (tasks: {task_count}, messages: {msg_count})")
            return True
        
        print(f"  📋 Found {task_count} tasks, {msg_count} messages")
    except Exception as e:
        print(f"  ⚠️  Could not check work: {e}")
        # Continue anyway
    
    # Primary method: Signal message
    if context:
        message = context
    else:
        message = f"You have {task_count} pending task(s). Check Neo4j and claim them."
    
    if spawn_via_signal(agent_id, message):
        # Log the spawn attempt
        try:
            driver = get_neo4j_driver()
            with driver.session() as session:
                session.run('''
                    CREATE (s:AgentSpawn {
                        id: $spawn_id,
                        agent: $agent,
                        method: 'signal',
                        triggered_at: datetime(),
                        context: $context
                    })
                ''', 
                    spawn_id=f"spawn_{agent_id}_{os.urandom(4).hex()}",
                    agent=agent_name,
                    context=message[:200]
                )
            driver.close()
        except:
            pass  # Don't fail if logging fails
        
        return True
    
    print(f"  ❌ All spawn methods failed for {agent_name}")
    return False

def spawn_all_pending():
    """Spawn all agents that have pending work."""
    print("🤖 Checking all agents for pending work...")
    print("=" * 60)
    
    spawned = 0
    skipped = 0
    failed = 0
    
    driver = get_neo4j_driver()
    
    for agent_name in AGENTS.keys():
        if agent_name == 'Kublai':
            continue  # Kublai is always running
        
        has_work, task_count, msg_count = check_pending_work(driver, agent_name)
        
        if has_work:
            if spawn_agent(agent_name):
                spawned += 1
            else:
                failed += 1
        else:
            print(f"  ⏭️  {agent_name}: No work")
            skipped += 1
    
    driver.close()
    
    print("=" * 60)
    print(f"Results: {spawned} spawned, {skipped} skipped, {failed} failed")
    return spawned, skipped, failed

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Spawn Kurultai agents')
    parser.add_argument('--agent', '-a', help='Specific agent to spawn')
    parser.add_argument('--all', action='store_true', help='Spawn all with pending work')
    parser.add_argument('--context', '-c', help='Context message for agent')
    
    args = parser.parse_args()
    
    if args.all:
        spawn_all_pending()
    elif args.agent:
        success = spawn_agent(args.agent, args.context)
        sys.exit(0 if success else 1)
    else:
        parser.print_help()
        sys.exit(1)
