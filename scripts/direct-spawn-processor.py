#!/usr/bin/env python3
"""
Direct Spawn Processor - Reads pending spawns and executes them via sessions_spawn
This runs in Kublai's main session context every 60 seconds via cron.

Handoffs: Heartbeat → Queue File → sessions_spawn → Agent (2 handoffs)
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

SPAWN_QUEUE = "/Users/kublai/.openclaw/agents/main/logs/spawn-pending.json"
SPAWN_LOG = "/Users/kublai/.openclaw/agents/main/logs/spawn-direct.log"
MAX_RETRIES = 3
RETRY_DELAY_MINUTES = 5

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")
    os.makedirs(os.path.dirname(SPAWN_LOG), exist_ok=True)
    with open(SPAWN_LOG, 'a') as f:
        f.write(f"[{timestamp}] {msg}\n")

def load_queue():
    """Load pending spawn requests"""
    if not os.path.exists(SPAWN_QUEUE):
        return []
    
    try:
        with open(SPAWN_QUEUE, 'r') as f:
            data = json.load(f)
            return data.get('spawns', [])
    except Exception as e:
        log(f"Error loading queue: {e}")
        return []

def save_queue(spawns):
    """Save updated queue"""
    os.makedirs(os.path.dirname(SPAWN_QUEUE), exist_ok=True)
    with open(SPAWN_QUEUE, 'w') as f:
        json.dump({'spawns': spawns, 'updated': datetime.now().isoformat()}, f, indent=2)

def process_spawns():
    """Process pending spawn requests"""
    log("=== Direct Spawn Processor ===")
    
    spawns = load_queue()
    
    if not spawns:
        log("No pending spawns")
        return
    
    log(f"Found {len(spawns)} pending spawn(s)")
    
    remaining = []
    spawned_count = 0
    
    for spawn in spawns:
        # Check if already spawned
        if spawn.get('status') == 'spawned':
            continue
        
        # Check retry count
        retries = spawn.get('retries', 0)
        if retries >= MAX_RETRIES:
            log(f"Max retries reached for: {spawn.get('label', 'unknown')}")
            spawn['status'] = 'failed'
            remaining.append(spawn)
            continue
        
        # Check if retry delay has passed
        if spawn.get('retry_after'):
            retry_time = datetime.fromisoformat(spawn['retry_after'])
            if datetime.now() < retry_time:
                remaining.append(spawn)
                continue
        
        # Execute spawn
        agent = spawn.get('agent', '')
        task = spawn.get('task', '')
        model = spawn.get('model', 'qwen3.5-plus')
        label = spawn.get('label', f"spawn-{datetime.now().strftime('%Y%m%d%H%M%S')}")
        priority = spawn.get('priority', 'normal')
        
        if not agent or not task:
            log(f"Invalid spawn request: {spawn}")
            spawn['status'] = 'invalid'
            remaining.append(spawn)
            continue
        
        log(f"Spawning {agent} ({model}, {priority}) - {task[:60]}...")
        
        # Output spawn command for cron to execute
        # Format: SPAWN|agent|model|label|task
        print(f"SPAWN|{agent}|{model}|{label}|{task}")
        
        # Mark as spawned
        spawn['status'] = 'spawned'
        spawn['spawned_at'] = datetime.now().isoformat()
        spawned_count += 1
        
        # Don't add to remaining (will be cleaned up)
    
    # Keep failed/invalid spawns for review, remove spawned ones
    remaining = [s for s in remaining if s.get('status') not in ['spawned']]
    
    # Clean old completed spawns (>1 hour)
    cutoff = datetime.now() - timedelta(hours=1)
    remaining = [s for s in remaining if 
                 s.get('status') not in ['spawned', 'failed', 'invalid'] or
                 datetime.fromisoformat(s.get('spawned_at', '2000-01-01')) > cutoff]
    
    save_queue(remaining)
    
    log(f"Spawned {spawned_count} agent(s), {len(remaining)} remaining in queue")
    log("=== Complete ===")

if __name__ == "__main__":
    process_spawns()
