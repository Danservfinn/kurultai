#!/usr/bin/env python3
"""
Simple Spawn Handler - Called by Kublai's cron to process pending spawns
Reads JSON queue and outputs spawn commands for execution
"""

import json
import os
from datetime import datetime, timedelta

SPAWN_QUEUE = "/Users/kublai/.openclaw/agents/main/logs/spawn-pending.json"
SPAWN_LOG = "/Users/kublai/.openclaw/agents/main/logs/spawn-exec.log"

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")
    os.makedirs(os.path.dirname(SPAWN_LOG), exist_ok=True)
    with open(SPAWN_LOG, 'a') as f:
        f.write(f"[{ts}] {msg}\n")

def process():
    log("=== Spawn Handler ===")
    
    if not os.path.exists(SPAWN_QUEUE):
        log("No spawn queue found")
        return []
    
    try:
        with open(SPAWN_QUEUE, 'r') as f:
            data = json.load(f)
    except:
        log("Error reading queue")
        return []
    
    spawns = data.get('spawns', [])
    if not spawns:
        log("Queue is empty")
        return []
    
    log(f"Found {len(spawns)} pending spawn(s)")
    
    to_spawn = []
    remaining = []
    
    for s in spawns:
        if s.get('status') == 'spawned':
            continue
        
        # Check if pending (not yet spawned)
        if not s.get('spawned_at'):
            to_spawn.append(s)
        else:
            # Keep spawned for 1 hour then cleanup
            spawned = datetime.fromisoformat(s['spawned_at'])
            if datetime.now() - spawned < timedelta(hours=1):
                remaining.append(s)
    
    # Output spawn commands
    for s in to_spawn:
        agent = s.get('agent', 'unknown')
        task = s.get('task', '')
        model = s.get('model', 'qwen3.5-plus')
        label = s.get('label', f"spawn-{datetime.now().strftime('%H%M%S')}")
        priority = s.get('priority', 'normal')
        
        log(f"SPAWN: {agent} ({model}, {priority}) - {task[:50]}...")
        
        # Mark as spawned
        s['status'] = 'spawned'
        s['spawned_at'] = datetime.now().isoformat()
        remaining.append(s)
    
    # Save updated queue
    with open(SPAWN_QUEUE, 'w') as f:
        json.dump({'spawns': remaining, 'updated': datetime.now().isoformat()}, f, indent=2)
    
    log(f"Queued {len(to_spawn)} spawns, {len(remaining)} in queue")
    log("=== Complete ===")
    
    return to_spawn

if __name__ == "__main__":
    spawns = process()
    if spawns:
        print(f"\nREADY_TO_SPAWN: {len(spawns)} agents")
        for s in spawns:
            print(f"  - {s.get('label')}: {s.get('agent')} - {s.get('task', '')[:40]}")
