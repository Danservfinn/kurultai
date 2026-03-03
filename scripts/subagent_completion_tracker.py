#!/usr/bin/env python3
"""
Subagent Completion Tracker

Monitors subagent sessions and updates task status on completion.
Runs continuously, polling OpenClaw session status.

Usage:
    python3 subagent_completion_tracker.py
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add OpenClaw to path
sys.path.insert(0, '/opt/homebrew/lib/node_modules/openclaw')

SPAWN_QUEUE = "/Users/kublai/.openclaw/agents/main/logs/spawn-pending.json"
COMPLETION_LOG = "/Users/kublai/.openclaw/agents/main/logs/task-completions.jsonl"
METRICS_FILE = "/Users/kublai/.openclaw/agents/main/logs/heartbeat_metrics.jsonl"
POLL_INTERVAL = 30  # seconds

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")

def get_sessions_list():
    """Get list of all sessions from OpenClaw"""
    try:
        # Use OpenClaw sessions_list via subprocess
        import subprocess
        result = subprocess.run(
            ['python3', '-c', '''
import sys
try:
    from openclaw.tools import sessions_list
    result = sessions_list(action="list", messageLimit=0, limit=100)
    import json
    print(json.dumps(result))
except Exception as e:
    print(json.dumps({"error": str(e), "sessions": []}))
'''],
            capture_output=True,
            text=True,
            timeout=10
        )
        data = json.loads(result.stdout)
        return data.get('sessions', [])
    except Exception as e:
        log(f"Error getting sessions: {e}")
        return []

def find_task_by_session(session_key):
    """Find task in queue by session_key"""
    if not os.path.exists(SPAWN_QUEUE):
        return None
    
    try:
        with open(SPAWN_QUEUE, 'r') as f:
            data = json.load(f)
        
        spawns = data.get('spawns', [])
        for s in spawns:
            if s.get('session_key') == session_key:
                return s
    except:
        pass
    
    return None

def complete_task(label, status, session_key=None):
    """Mark task as completed"""
    if not os.path.exists(SPAWN_QUEUE):
        return False
    
    try:
        with open(SPAWN_QUEUE, 'r') as f:
            data = json.load(f)
        
        spawns = data.get('spawns', [])
        updated = False
        
        for s in spawns:
            if s.get('label') == label:
                # Skip continuous tasks
                if s.get('continuous'):
                    log(f"SKIP: {label} (continuous task)")
                    return False
                
                s['status'] = status
                s['completed_at'] = datetime.now().isoformat()
                if session_key:
                    s['session_key'] = session_key
                updated = True
                log(f"COMPLETE: {label} → {status}")
                break
        
        if updated:
            with open(SPAWN_QUEUE, 'w') as f:
                json.dump({'spawns': spawns, 'updated': time.time()}, f, indent=2)
            
            # Log completion
            log_completion(label, status, session_key)
            return True
    except Exception as e:
        log(f"Error completing task: {e}")
    
    return False

def log_completion(label, status, session_key=None):
    """Log task completion"""
    os.makedirs(os.path.dirname(COMPLETION_LOG), exist_ok=True)
    entry = {
        "label": label,
        "status": status,
        "session_key": session_key,
        "completed_at": datetime.now().isoformat(),
        "source": "completion_tracker"
    }
    with open(COMPLETION_LOG, 'a') as f:
        f.write(json.dumps(entry) + '\n')

def log_metric(task_name, status, latency_ms=0):
    """Log execution metric"""
    os.makedirs(os.path.dirname(METRICS_FILE), exist_ok=True)
    metric = {
        "timestamp": datetime.now().isoformat(),
        "task": task_name,
        "status": status,
        "latency_ms": latency_ms,
        "source": "completion_tracker"
    }
    with open(METRICS_FILE, 'a') as f:
        f.write(json.dumps(metric) + '\n')

def check_sessions():
    """Check all sessions for completed subagents"""
    sessions = get_sessions_list()
    
    completed_count = 0
    
    for session in sessions:
        session_key = session.get('sessionKey', '')
        session_id = session.get('sessionId', '')
        status = session.get('status', 'unknown')
        label = session.get('displayName', 'unknown')
        
        # Check if this is a subagent (has subagent in key or id)
        if 'subagent' not in session_key.lower() and 'subagent' not in session_id.lower():
            continue
        
        # Check if task exists in queue
        task = find_task_by_session(session_key)
        if not task:
            # Try to find by label match
            continue
        
        # Check session status
        if status in ['done', 'completed', 'failed', 'error']:
            # Task is complete
            final_status = 'completed' if status in ['done', 'completed'] else 'failed'
            if complete_task(task['label'], final_status, session_key):
                completed_count += 1
                log_metric(task['label'], final_status)
    
    return completed_count

def main():
    log("=== Subagent Completion Tracker Started ===")
    log(f"Polling every {POLL_INTERVAL} seconds")
    
    last_check = time.time()
    
    while True:
        try:
            completed = check_sessions()
            if completed > 0:
                log(f"Updated {completed} completed task(s)")
            
            # Sleep until next poll
            time.sleep(POLL_INTERVAL)
            
        except KeyboardInterrupt:
            log("Stopping...")
            break
        except Exception as e:
            log(f"Error: {e}")
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
