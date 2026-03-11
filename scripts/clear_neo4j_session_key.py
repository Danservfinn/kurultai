#!/usr/bin/env python3
"""Clear Neo4j session_key for completed/failed tasks.

This module provides a function to clear the session_key in Neo4j
when tasks complete or fail, preventing stale claim accumulation.
"""

import os
import sys
from pathlib import Path


def clear_session_key_for_task(task_file_path: str) -> bool:
    """Clear the session_key in Neo4j for a completed/failed task.
    
    Args:
        task_file_path: Path to the task file (can be .executing.md or .done.md)
        
    Returns:
        True if session_key was cleared or didn't exist, False on error
    """
    try:
        # Import Neo4j driver
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from neo4j_atomic_transitions import get_driver
        
        # Extract task_id from file
        task_id = None
        agent = "unknown"
        
        # Try to read task_id from file
        try:
            with open(task_file_path, 'r') as f:
                content = f.read(2000)
                import re
                task_match = re.search(r'task_id:\s*(\S+)', content)
                if task_match:
                    task_id = task_match.group(1)
        except Exception:
            pass
        
        # Extract agent from path
        path_parts = Path(task_file_path).parts
        if 'agents' in path_parts:
            agent_idx = path_parts.index('agents')
            if agent_idx + 1 < len(path_parts):
                agent = path_parts[agent_idx + 1]
        
        if not task_id:
            # Try to extract from filename
            basename = os.path.basename(task_file_path)
            # Remove extensions like .executing.md, .completed.done.md, etc.
            for suffix in ['.executing.md', '.completed.done.md', '.failed.done.md', 
                          '.no_output.done.md', '.credential_failed.done.md']:
                if basename.endswith(suffix):
                    task_id = basename[:-len(suffix)]
                    break
        
        if not task_id:
            print(f"[clear_session_key] Could not extract task_id from: {task_file_path}")
            return False
        
        # Clear session_key in Neo4j
        driver = get_driver()
        with driver.session() as session:
            result = session.run("""
                MATCH (t:Task {task_id: $task_id})
                WHERE t.session_key IS NOT NULL
                SET t.session_key = null,
                    t.updated = datetime()
                RETURN count(t) as cleared
            """, task_id=task_id)
            
            record = result.single()
            cleared = record["cleared"] if record else 0
            
            if cleared > 0:
                print(f"[clear_session_key] Cleared session_key for {task_id} ({agent})")
            else:
                print(f"[clear_session_key] No session_key to clear for {task_id} ({agent})")
            
            return True
            
    except Exception as e:
        print(f"[clear_session_key] Error clearing session_key: {e}")
        # Return True so we don't block task completion
        return True


if __name__ == "__main__":
    # Allow command-line usage
    if len(sys.argv) > 1:
        task_file = sys.argv[1]
        success = clear_session_key_for_task(task_file)
        sys.exit(0 if success else 1)
    else:
        print("Usage: python3 clear_neo4j_session_key.py <task_file_path>")
        sys.exit(1)
