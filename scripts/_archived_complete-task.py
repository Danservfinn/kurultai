#!/usr/bin/env python3
"""
Task Completion Handler - Called by agents when they finish

Usage:
    python3 complete-task.py <label> <status> [error_message]
    
Status: completed, failed, killed
"""

import json
import os
import sys
from datetime import datetime

SPAWN_QUEUE = "/Users/kublai/.openclaw/agents/main/logs/spawn-pending.json"
COMPLETION_LOG = "/Users/kublai/.openclaw/agents/main/logs/task-completions.jsonl"

def log_completion(label, status, error=None, session_key=None):
    """Log task completion"""
    os.makedirs(os.path.dirname(COMPLETION_LOG), exist_ok=True)
    entry = {
        "label": label,
        "status": status,
        "error": error,
        "session_key": session_key,
        "completed_at": datetime.now().isoformat()
    }
    with open(COMPLETION_LOG, 'a') as f:
        f.write(json.dumps(entry) + '\n')

def update_queue(label, status, error=None):
    """Update spawn queue with completion status"""
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from neo4j_task_tracker import get_tracker
    
    # Update Neo4j
    try:
        tracker = get_tracker()
        tracker.update_status(label, status, error)
        print(f"Neo4j: {label} → {status}")
    except Exception as e:
        print(f"Neo4j error: {e}")
    
    # Update JSON queue (fallback)
    if not os.path.exists(SPAWN_QUEUE):
        return False
    
    try:
        with open(SPAWN_QUEUE, 'r') as f:
            data = json.load(f)
    except:
        return False
    
    spawns = data.get('spawns', [])
    updated = False
    
    for s in spawns:
        if s.get('label') == label:
            # Skip continuous tasks (they never complete)
            if s.get('continuous'):
                print(f"Task {label} is continuous - not marking complete")
                return False
            
            s['status'] = status
            s['completed_at'] = datetime.now().isoformat()
            if error:
                s['error'] = error
            
            updated = True
            print(f"JSON: {label} → {status}")
            break
    
    if updated:
        with open(SPAWN_QUEUE, 'w') as f:
            json.dump({'spawns': spawns, 'updated': datetime.now().timestamp()}, f, indent=2)
    
    return updated

def main():
    if len(sys.argv) < 3:
        print("Usage: complete-task.py <label> <status> [error_message]")
        print("Status: completed, failed, killed")
        sys.exit(1)
    
    label = sys.argv[1]
    status = sys.argv[2]
    error = sys.argv[3] if len(sys.argv) > 3 else None
    
    # Validate status
    if status not in ['completed', 'failed', 'killed']:
        print(f"Invalid status: {status}")
        print("Valid: completed, failed, killed")
        sys.exit(1)
    
    # Update queue
    queue_updated = update_queue(label, status, error)
    
    # Log completion
    log_completion(label, status, error)
    
    if queue_updated:
        print(f"✓ Task {label} marked as {status}")
    else:
        print(f"⚠ Task {label} not found in queue (may already be cleaned up)")

if __name__ == "__main__":
    main()
