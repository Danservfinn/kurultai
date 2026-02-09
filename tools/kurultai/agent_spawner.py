#!/usr/bin/env python3
"""
Agent Spawner for Kurultai

Spawns dormant agents via Signal messages or direct OpenClaw API calls.
Used by Railway cron to wake agents periodically to check for pending tasks.
"""

import os
import sys
import argparse
import subprocess
from neo4j import GraphDatabase

# Agent ID mapping
AGENT_MAP = {
    'researcher': {'name': 'Möngke', 'phone': None},
    'writer': {'name': 'Chagatai', 'phone': None},
    'developer': {'name': 'Temüjin', 'phone': None},
    'analyst': {'name': 'Jochi', 'phone': None},
    'ops': {'name': 'Ögedei', 'phone': None}
}

def get_neo4j_driver():
    """Get Neo4j driver from environment."""
    uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
    password = os.environ.get('NEO4J_PASSWORD')
    if not password:
        raise ValueError("NEO4J_PASSWORD not set")
    return GraphDatabase.driver(uri, auth=('neo4j', password))

def has_pending_tasks(driver, agent_name):
    """Check if agent has pending tasks."""
    with driver.session() as session:
        result = session.run('''
            MATCH (t:Task {status: "pending", assigned_to: $agent})
            RETURN count(t) as count
        ''', agent=agent_name)
        return result.single()['count'] > 0

def has_pending_messages(driver, agent_name):
    """Check if agent has pending AgentMessage nodes."""
    with driver.session() as session:
        result = session.run('''
            MATCH (m:AgentMessage {to_agent: $agent, status: "pending"})
            RETURN count(m) as count
        ''', agent=agent_name)
        return result.single()['count'] > 0

def spawn_via_signal(agent_id, message="Check your pending tasks"):
    """Spawn agent by sending Signal message."""
    signal_account = os.environ.get('SIGNAL_ACCOUNT')
    if not signal_account:
        print(f"  ⚠️  SIGNAL_ACCOUNT not set, cannot send Signal message")
        return False
    
    # Send message via signal-cli
    try:
        cmd = [
            'signal-cli', 
            '-a', signal_account,
            'send',
            '-m', f"@{agent_id} {message}",
            signal_account  # Send to self, mentioning agent
        ]
        subprocess.run(cmd, timeout=30, capture_output=True)
        print(f"  ✅ Sent Signal message to trigger {agent_id}")
        return True
    except Exception as e:
        print(f"  ⚠️  Signal send failed: {e}")
        return False

def spawn_via_openclaw_api(agent_id):
    """Try to spawn agent via OpenClaw API."""
    import urllib.request
    import urllib.error
    import json
    
    gateway_url = os.environ.get('OPENCLAW_GATEWAY_URL', 'http://localhost:18789')
    token = os.environ.get('OPENCLAW_GATEWAY_TOKEN')
    
    if not token:
        print(f"  ⚠️  OPENCLAW_GATEWAY_TOKEN not set")
        return False
    
    # Try various endpoints
    endpoints = [
        f"{gateway_url}/api/agents/{agent_id}/spawn",
        f"{gateway_url}/api/sessions",
    ]
    
    for endpoint in endpoints:
        try:
            req = urllib.request.Request(
                endpoint,
                data=json.dumps({'agentId': agent_id, 'context': 'check_pending_tasks'}).encode(),
                headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type': 'application/json'
                },
                method='POST'
            )
            
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status in [200, 201, 202]:
                    print(f"  ✅ Spawned {agent_id} via API")
                    return True
        except Exception:
            continue
    
    print(f"  ⚠️  Could not spawn {agent_id} via API")
    return False

def spawn_agent(agent_id, check_tasks=False):
    """Main spawn logic."""
    agent_info = AGENT_MAP.get(agent_id)
    if not agent_info:
        print(f"❌ Unknown agent: {agent_id}")
        return False
    
    agent_name = agent_info['name']
    print(f"🚀 Spawning {agent_name} ({agent_id})...")
    
    # Check if spawning is needed
    if check_tasks:
        try:
            driver = get_neo4j_driver()
            needs_spawn = has_pending_tasks(driver, agent_name) or has_pending_messages(driver, agent_name)
            driver.close()
            
            if not needs_spawn:
                print(f"  ⏭️  No pending tasks/messages for {agent_name}, skipping spawn")
                return True
            
            print(f"  📋 Pending work found for {agent_name}")
        except Exception as e:
            print(f"  ⚠️  Could not check tasks: {e}")
            # Spawn anyway if we can't check
    
    # Try spawn methods in order of preference
    if spawn_via_openclaw_api(agent_id):
        return True
    
    if spawn_via_signal(agent_id):
        return True
    
    print(f"  ❌ All spawn methods failed for {agent_id}")
    return False

def main():
    parser = argparse.ArgumentParser(description='Spawn Kurultai agents')
    parser.add_argument('--agent', '-a', required=True, 
                       choices=['researcher', 'writer', 'developer', 'analyst', 'ops'],
                       help='Agent ID to spawn')
    parser.add_argument('--check-tasks', '-c', action='store_true',
                       help='Only spawn if pending tasks exist')
    parser.add_argument('--all', action='store_true',
                       help='Spawn all agents')
    
    args = parser.parse_args()
    
    if args.all:
        success = True
        for agent_id in AGENT_MAP.keys():
            if not spawn_agent(agent_id, args.check_tasks):
                success = False
        sys.exit(0 if success else 1)
    else:
        success = spawn_agent(args.agent, args.check_tasks)
        sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
