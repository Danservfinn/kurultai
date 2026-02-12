#!/usr/bin/env python3
"""
Update Kurultai task status in Neo4j.

Usage:
    python update_task_status.py <task_id> <status>
    python update_task_status.py 0563b4da-26f3-4d5b-89a1-7309d134dd00 completed
"""

import os
import sys
import json
from datetime import datetime
from typing import Optional
from neo4j import GraphDatabase


def get_driver():
    """Get Neo4j driver from environment."""
    uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
    password = os.environ.get('NEO4J_PASSWORD')
    if not password:
        # Try to read from .env file
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith('NEO4J_PASSWORD='):
                        password = line.strip().split('=', 1)[1]
                        break
    if not password:
        raise ValueError("NEO4J_PASSWORD not set in environment or .env file")
    return GraphDatabase.driver(uri, auth=('neo4j', password))


def update_task_status(task_id: str, status: str, notes: Optional[str] = None) -> bool:
    """
    Update task status in Neo4j.
    
    Args:
        task_id: The task ID to update
        status: New status (pending, in_progress, completed, failed, blocked)
        notes: Optional completion notes
        
    Returns:
        True if successful
    """
    driver = get_driver()
    
    with driver.session() as session:
        # Check if task exists
        result = session.run(
            "MATCH (t:Task {id: $task_id}) RETURN t",
            task_id=task_id
        )
        record = result.single()
        
        if not record:
            print(f"❌ Task not found: {task_id}")
            return False
        
        task = dict(record["t"])
        old_status = task.get("status", "unknown")
        
        # Update task status
        query = """
        MATCH (t:Task {id: $task_id})
        SET t.status = $status,
            t.updated_at = datetime(),
            t.completed_at = CASE WHEN $status = 'completed' THEN datetime() ELSE t.completed_at END
        """
        
        if notes:
            query += ", t.completion_notes = $notes"
        
        query += " RETURN t"
        
        result = session.run(
            query,
            task_id=task_id,
            status=status,
            notes=notes
        )
        
        if result.single():
            print(f"✅ Task {task_id[:8]}... updated: {old_status} → {status}")
            
            # Log status change event
            session.run(
                """
                MATCH (t:Task {id: $task_id})
                CREATE (e:StatusChangeEvent {
                    id: randomUUID(),
                    old_status: $old_status,
                    new_status: $new_status,
                    changed_at: datetime(),
                    notes: $notes
                })
                CREATE (t)-[:HAS_STATUS_CHANGE]->(e)
                """,
                task_id=task_id,
                old_status=old_status,
                new_status=status,
                notes=notes or ""
            )
            
            return True
        
        return False


def get_task_info(task_id: str) -> dict:
    """Get task information from Neo4j."""
    driver = get_driver()
    
    with driver.session() as session:
        result = session.run(
            """
            MATCH (t:Task {id: $task_id})
            OPTIONAL MATCH (t)-[:ASSIGNED_TO]->(a:Agent)
            OPTIONAL MATCH (t)-[:DELEGATED_BY]->(d:Agent)
            RETURN t, a.name as assigned_to, d.name as delegated_by
            """,
            task_id=task_id
        )
        record = result.single()
        
        if record:
            task = dict(record["t"])
            task["assigned_to"] = record["assigned_to"]
            task["delegated_by"] = record["delegated_by"]
            return task
        
        return {}


def list_pending_tasks(limit: int = 10) -> list:
    """List pending tasks from Neo4j."""
    driver = get_driver()
    
    with driver.session() as session:
        result = session.run(
            """
            MATCH (t:Task)
            WHERE t.status IN ['pending', 'in_progress', 'ready']
            RETURN t
            ORDER BY t.created_at DESC
            LIMIT $limit
            """,
            limit=limit
        )
        
        tasks = []
        for record in result:
            task = dict(record["t"])
            tasks.append(task)
        
        return tasks


def main():
    """Main entry point."""
    print("=" * 60)
    print("📝 Kurultai Task Status Updater")
    print("=" * 60)
    
    # Get task ID from command line or use the current task
    if len(sys.argv) >= 2:
        task_id = sys.argv[1]
    else:
        # Use the task ID from the assignment
        task_id = "0563b4da-26f3-4d5b-89a1-7309d134dd00"
    
    if len(sys.argv) >= 3:
        new_status = sys.argv[2]
    else:
        new_status = "completed"
    
    notes = sys.argv[3] if len(sys.argv) > 3 else None
    
    print(f"\n🆔 Task ID: {task_id}")
    print(f"📊 New Status: {new_status}")
    if notes:
        print(f"📝 Notes: {notes}")
    
    # Get current task info
    print("\n🔍 Fetching current task info...")
    task_info = get_task_info(task_id)
    
    if task_info:
        print(f"   Current Status: {task_info.get('status', 'unknown')}")
        print(f"   Type: {task_info.get('type', 'unknown')}")
        print(f"   Description: {task_info.get('description', 'No description')[:50]}...")
        if task_info.get('assigned_to'):
            print(f"   Assigned To: {task_info['assigned_to']}")
    else:
        print(f"   ⚠️ Task not found, will attempt to create status update anyway")
    
    # Update status
    print(f"\n🔄 Updating status...")
    success = update_task_status(task_id, new_status, notes)
    
    if success:
        print(f"\n✅ Task status updated successfully!")
        
        # Show updated info
        updated_info = get_task_info(task_id)
        if updated_info:
            print(f"\n📋 Updated Task Info:")
            print(f"   Status: {updated_info.get('status')}")
            print(f"   Updated At: {updated_info.get('updated_at')}")
            if updated_info.get('completed_at'):
                print(f"   Completed At: {updated_info['completed_at']}")
        
        return 0
    else:
        print(f"\n❌ Failed to update task status")
        return 1


if __name__ == "__main__":
    sys.exit(main())
