#!/usr/bin/env python3
"""
Spawn Request Processor - Reads pending spawn requests and outputs them for execution
This is called by Kublai's cron job which then calls sessions_spawn
"""

import os
import json
import glob
from datetime import datetime

SPAWN_DIR = "/Users/kublai/.openclaw/agents/main/spawn-requests"
LOG_FILE = "/Users/kublai/.openclaw/agents/main/logs/spawn-executor.log"

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, 'a') as f:
        f.write(f"[{timestamp}] {msg}\n")

def parse_request_file(filepath):
    """Parse a spawn request markdown file"""
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Parse frontmatter
    request = {}
    lines = content.split('\n')
    in_frontmatter = False
    
    for line in lines:
        if line.startswith('---'):
            in_frontmatter = not in_frontmatter
            continue
        
        if in_frontmatter and ':' in line:
            key, value = line.split(':', 1)
            request[key.strip()] = value.strip()
        
        if line.startswith('# Task:'):
            request['task'] = line.replace('# Task:', '').strip()
    
    return request

def process_pending():
    """Process all pending spawn requests"""
    log("=== Spawn Executor Cycle ===")
    
    if not os.path.exists(SPAWN_DIR):
        log("No spawn requests directory found")
        return []
    
    # Find pending requests
    pending = glob.glob(f"{SPAWN_DIR}/*.md")
    pending = [f for f in pending if not f.endswith('.processed.md') and not f.endswith('.executing.md')]
    
    if not pending:
        log("No pending spawn requests")
        return []
    
    log(f"Found {len(pending)} pending spawn request(s)")
    
    spawn_requests = []
    
    for request_file in pending:
        try:
            request = parse_request_file(request_file)
            
            agent = request.get('agent', '')
            model = request.get('model', 'qwen3.5-plus')
            label = request.get('label', '')
            task = request.get('task', '')
            
            if not agent or not task:
                log(f"Invalid request file: {request_file}")
                continue
            
            log(f"Spawning: {agent} ({model}) - {task[:50]}...")
            
            # Mark as executing
            executing_file = request_file.replace('.md', '.executing.md')
            os.rename(request_file, executing_file)
            
            spawn_requests.append({
                'agent': agent,
                'model': model,
                'label': label,
                'task': task,
                'file': executing_file
            })
            
        except Exception as e:
            log(f"Error processing {request_file}: {e}")
    
    log(f"=== Cycle Complete: {len(spawn_requests)} requests ===")
    return spawn_requests

if __name__ == "__main__":
    requests = process_pending()
    
    # Output JSON for cron job to parse
    if requests:
        print(json.dumps({'spawn_requests': requests}, indent=2))
    else:
        print(json.dumps({'spawn_requests': []}))
