#!/usr/bin/env python3
"""
Autonomous Task Delegation System for Kublai

Automatically delegates pending tasks to specialist agents via Neo4j AgentMessage nodes.
Run as part of Kublai's 5-minute heartbeat cycle.
"""

import os
import sys
import json
import uuid
from datetime import datetime
from neo4j import GraphDatabase

# Agent ID mapping for OpenClaw
AGENT_ID_MAP = {
    'Möngke': 'researcher',
    'Chagatai': 'writer',
    'Temüjin': 'developer',
    'Jochi': 'analyst',
    'Ögedei': 'ops'
}

def get_neo4j_driver():
    """Get Neo4j driver from environment."""
    uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
    user = os.environ.get('NEO4J_USER', 'neo4j')
    password = os.environ.get('NEO4J_PASSWORD')
    if not password:
        raise ValueError("NEO4J_PASSWORD not set")
    return GraphDatabase.driver(uri, auth=(user, password))

def get_pending_tasks(driver):
    """Get pending tasks for specialist agents that haven't been delegated."""
    with driver.session() as session:
        result = session.run('''
            MATCH (t:Task)
            WHERE t.status = 'pending'
              AND t.assigned_to IN ['Möngke', 'Chagatai', 'Temüjin', 'Jochi', 'Ögedei']
              AND (t.delegated_by IS NULL OR t.delegated_by = '')
            RETURN t.id as task_id, t.assigned_to as agent, t.description as desc,
                   t.priority as priority, t.task_type as task_type
        ''')
        return [dict(r) for r in result]

def check_existing_delegation(driver, task_id):
    """Check if a delegation message already exists for this task."""
    with driver.session() as session:
        result = session.run('''
            MATCH (m:AgentMessage)
            WHERE m.message_type = 'task_assignment'
              AND m.payload CONTAINS $task_id
              AND m.status = 'pending'
            RETURN count(m) as count
        ''', task_id=task_id)
        return result.single()['count'] > 0

def delegate_task(driver, task):
    """Create delegation message for a task."""
    agent_name = task['agent']
    agent_id = AGENT_ID_MAP.get(agent_name)
    task_id = task['task_id']
    
    if not agent_id:
        print(f"  ⚠️  Unknown agent: {agent_name}")
        return False
    
    # Check if already delegated
    if check_existing_delegation(driver, task_id):
        print(f"  ⏭️  Task {task_id[:8]}... already delegated, skipping")
        return False
    
    # Create delegation message
    message_payload = {
        "task_id": task_id,
        "description": task['desc'],
        "priority": task['priority'],
        "task_type": task['task_type'],
        "context": f"You have been assigned a {task['priority']} priority {task['task_type']} task by Kublai. Please claim and complete it via the Neo4j Task system. Report back when done."
    }
    
    with driver.session() as session:
        # Create AgentMessage
        session.run('''
            CREATE (m:AgentMessage {
                id: $msg_id,
                from_agent: 'Kublai',
                to_agent: $to_agent,
                message_type: 'task_assignment',
                payload: $payload,
                status: 'pending',
                created_at: datetime()
            })
        ''', 
            msg_id=str(uuid.uuid4()),
            to_agent=agent_name,
            payload=json.dumps(message_payload)
        )
        
        # Mark task as delegated
        session.run('''
            MATCH (t:Task {id: $task_id})
            SET t.delegated_by = 'Kublai',
                t.delegated_at = datetime()
        ''', task_id=task_id)
    
    return True

def main():
    """Main delegation loop."""
    print("🤖 Autonomous Task Delegation")
    print("=" * 50)
    
    try:
        driver = get_neo4j_driver()
    except Exception as e:
        print(f"❌ Failed to connect to Neo4j: {e}")
        sys.exit(1)
    
    try:
        # Get pending tasks
        tasks = get_pending_tasks(driver)
        
        if not tasks:
            print("✅ No pending tasks to delegate")
            return
        
        print(f"📋 Found {len(tasks)} pending tasks\n")
        
        delegated_count = 0
        for task in tasks:
            agent_name = task['agent']
            desc = task['desc'][:40] + "..." if len(task['desc']) > 40 else task['desc']
            
            print(f"📤 {agent_name:10} | {task['task_type']:12} | {desc}")
            
            if delegate_task(driver, task):
                print(f"   ✅ Delegated successfully")
                delegated_count += 1
            else:
                print(f"   ⏭️  Skipped (already delegated)")
            print()
        
        print("=" * 50)
        print(f"✅ Delegated {delegated_count}/{len(tasks)} tasks")
        
    except Exception as e:
        print(f"❌ Error during delegation: {e}")
        import traceback
        traceback.print_exc()
    finally:
        driver.close()

if __name__ == "__main__":
    main()
