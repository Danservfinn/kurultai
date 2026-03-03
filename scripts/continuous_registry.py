#!/usr/bin/env python3
"""
Continuous Task Registry - Separate tracking for never-ending tasks

Usage:
    python3 continuous_registry.py register <label> <agent> <task>
    python3 continuous_registry.py unregister <label>
    python3 continuous_registry.py list
    python3 continuous_registry.py status <label>
"""

import json
import os
import sys
from datetime import datetime

REGISTRY_FILE = "/Users/kublai/.openclaw/agents/main/logs/continuous-tasks.json"
COMPLETION_LOG = "/Users/kublai/.openclaw/agents/main/logs/task-completions.jsonl"

def load_registry():
    """Load continuous task registry"""
    if not os.path.exists(REGISTRY_FILE):
        return {'tasks': []}
    try:
        with open(REGISTRY_FILE, 'r') as f:
            return json.load(f)
    except:
        return {'tasks': []}

def save_registry(data):
    """Save registry"""
    os.makedirs(os.path.dirname(REGISTRY_FILE), exist_ok=True)
    with open(REGISTRY_FILE, 'w') as f:
        json.dump(data, f, indent=2, default=str)

def register(label, agent, task, session_key=None):
    """Register a continuous task"""
    data = load_registry()
    
    # Check if already registered
    for t in data['tasks']:
        if t.get('label') == label:
            print(f"Task {label} already registered")
            return False
    
    task_entry = {
        "label": label,
        "agent": agent,
        "task": task,
        "session_key": session_key,
        "status": "running",
        "started": datetime.now().isoformat(),
        "last_heartbeat": datetime.now().isoformat(),
        "heartbeats": 0
    }
    
    data['tasks'].append(task_entry)
    save_registry(data)
    print(f"✓ Registered continuous task: {label} ({agent})")
    return True

def unregister(label, reason="stopped"):
    """Unregister a continuous task"""
    data = load_registry()
    
    found = False
    for t in data['tasks']:
        if t.get('label') == label:
            t['status'] = 'stopped'
            t['stopped'] = datetime.now().isoformat()
            t['stop_reason'] = reason
            found = True
            
            # Log completion
            log_completion(label, 'completed', None, t.get('session_key'))
            print(f"✓ Unregistered continuous task: {label}")
            break
    
    if not found:
        print(f"Task {label} not found")
        return False
    
    save_registry(data)
    return True

def log_completion(label, status, error=None, session_key=None):
    """Log task completion"""
    entry = {
        "label": label,
        "status": status,
        "error": error,
        "session_key": session_key,
        "completed_at": datetime.now().isoformat(),
        "type": "continuous"
    }
    with open(COMPLETION_LOG, 'a') as f:
        f.write(json.dumps(entry) + '\n')

def update_heartbeat(label):
    """Update heartbeat for continuous task"""
    data = load_registry()
    for t in data['tasks']:
        if t.get('label') == label:
            t['last_heartbeat'] = datetime.now().isoformat()
            t['heartbeats'] = t.get('heartbeats', 0) + 1
            save_registry(data)
            return True
    return False

def list_tasks():
    """List all continuous tasks"""
    data = load_registry()
    running = [t for t in data['tasks'] if t.get('status') == 'running']
    stopped = [t for t in data['tasks'] if t.get('status') == 'stopped']
    
    print(f"Continuous Tasks Registry")
    print(f"=" * 40)
    print(f"Running: {len(running)}")
    for t in running:
        print(f"  - {t.get('label')} ({t.get('agent')})")
        print(f"    Started: {t.get('started', 'N/A')[:19]}")
        print(f"    Heartbeats: {t.get('heartbeats', 0)}")
        session = t.get('session_key') or 'N/A'
        print(f"    Session: {session[:20] if session != 'N/A' else session}...")
    
    if stopped:
        print(f"\nStopped: {len(stopped)}")
        for t in stopped[:5]:  # Show last 5
            print(f"  - {t.get('label')} ({t.get('agent')}) - {t.get('stop_reason', 'N/A')}")

def get_status(label):
    """Get status of specific task"""
    data = load_registry()
    for t in data['tasks']:
        if t.get('label') == label:
            print(json.dumps(t, indent=2, default=str))
            return t
    print(f"Task {label} not found")
    return None

def main():
    if len(sys.argv) < 2:
        print("Usage: continuous_registry.py <command> [args]")
        print("Commands: register, unregister, list, status, heartbeat")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == 'register' and len(sys.argv) >= 4:
        register(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else '', 
                sys.argv[5] if len(sys.argv) > 5 else None)
    elif cmd == 'unregister' and len(sys.argv) >= 3:
        unregister(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else 'manual')
    elif cmd == 'list':
        list_tasks()
    elif cmd == 'status' and len(sys.argv) >= 3:
        get_status(sys.argv[2])
    elif cmd == 'heartbeat' and len(sys.argv) >= 3:
        if update_heartbeat(sys.argv[2]):
            print(f"Heartbeat updated for {sys.argv[2]}")
        else:
            print(f"Task {sys.argv[2]} not found")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)

if __name__ == "__main__":
    main()
