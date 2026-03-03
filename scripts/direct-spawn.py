#!/usr/bin/env python3
"""
Direct Task Spawner - Classifies chat message and spawns agent immediately
Bypasses file-based task queues for chat-initiated work

Usage:
    python3 direct-spawn.py "Build a login feature for Parse"
    
Flow:
    Message → Classify → spawn-pending.json → sessions_spawn → Agent
    (All in one cycle, <10 seconds)
"""

import json
import os
import sys
import time
import re
from datetime import datetime

SPAWN_QUEUE = "/Users/kublai/.openclaw/agents/main/logs/spawn-pending.json"
SPAWN_LOG = "/Users/kublai/.openclaw/agents/main/logs/direct-spawn.log"

# Agent routing matrix
AGENT_ROUTING = {
    "temujin": {
        "keywords": ["build", "code", "implement", "fix", "bug", "feature", "deploy", 
                     "infrastructure", "api", "endpoint", "database", "typescript", 
                     "javascript", "python", "script", "automation", "integration"],
        "model": "qwen3.5-plus"
    },
    "mongke": {
        "keywords": ["research", "analyze", "investigate", "discover", "find", "study",
                     "competitor", "market", "trend", "data", "intelligence", "survey"],
        "model": "qwen3.5-plus"
    },
    "chagatai": {
        "keywords": ["write", "document", "blog", "post", "content", "article", 
                     "creative", "copy", "marketing", "social", "twitter", "thread"],
        "model": "qwen3.5-plus"
    },
    "jochi": {
        "keywords": ["test", "security", "audit", "review", "verify", "validate",
                     "pattern", "analysis", "check", "scan", "vulnerability"],
        "model": "MiniMax-M2.5"
    },
    "ogedei": {
        "keywords": ["monitor", "health", "alert", "failover", "ops", "deploy",
                     "infrastructure", "uptime", "status", "dashboard", "cron"],
        "model": "qwen3.5-plus"
    }
}

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")
    os.makedirs(os.path.dirname(SPAWN_LOG), exist_ok=True)
    with open(SPAWN_LOG, 'a') as f:
        f.write(f"[{ts}] {msg}\n")

def classify_message(message):
    """Classify message and route to appropriate agent"""
    message_lower = message.lower()
    
    scores = {}
    for agent, config in AGENT_ROUTING.items():
        score = 0
        for keyword in config["keywords"]:
            if keyword in message_lower:
                score += 1
        
        # Boost for action verbs at start
        action_verbs = ["build", "create", "implement", "fix", "research", "write", "test"]
        for verb in action_verbs:
            if message_lower.startswith(verb):
                score += 2
        
        scores[agent] = score
    
    best_agent = max(scores, key=scores.get)
    best_score = scores[best_agent]
    total_matches = sum(scores.values())
    confidence = best_score / max(total_matches, 1)
    
    # Determine priority
    priority = "normal"
    if any(word in message_lower for word in ["urgent", "asap", "critical", "emergency"]):
        priority = "high"
    elif any(word in message_lower for word in ["when you have time", "eventually", "nice to have"]):
        priority = "low"
    
    return {
        "agent": best_agent,
        "model": AGENT_ROUTING[best_agent]["model"],
        "task": message.strip()[:200],
        "priority": priority,
        "confidence": round(confidence, 2),
        "label": f"{best_agent}-{int(time.time())}"
    }

def write_spawn_request(classification):
    """Write to spawn queue"""
    os.makedirs(os.path.dirname(SPAWN_QUEUE), exist_ok=True)
    
    # Load existing
    existing = []
    if os.path.exists(SPAWN_QUEUE):
        try:
            with open(SPAWN_QUEUE, 'r') as f:
                data = json.load(f)
                existing = data.get('spawns', [])
        except:
            pass
    
    # Add new
    spawn_request = {
        **classification,
        "source": "chat_direct",
        "created": datetime.now().isoformat(),
        "status": "pending"
    }
    existing.append(spawn_request)
    
    # Save
    with open(SPAWN_QUEUE, 'w') as f:
        json.dump({'spawns': existing, 'updated': time.time()}, f, indent=2)
    
    return spawn_request

def main():
    if len(sys.argv) < 2:
        print("Usage: direct-spawn.py <message>")
        sys.exit(1)
    
    message = " ".join(sys.argv[1:])
    
    log(f"=== Direct Spawn ===")
    log(f"Message: {message[:80]}...")
    
    # Classify
    classification = classify_message(message)
    log(f"Classified: {classification['agent']} (confidence: {classification['confidence']})")
    
    # Write to queue
    spawn_request = write_spawn_request(classification)
    log(f"Written to spawn queue: {spawn_request['label']}")
    
    # Output for immediate spawn
    print(f"\nREADY_TO_SPAWN:")
    print(f"  agent={classification['agent']}")
    print(f"  model={classification['model']}")
    print(f"  label={classification['label']}")
    print(f"  task={classification['task']}")
    print(f"  priority={classification['priority']}")
    
    log(f"=== Complete ===")

if __name__ == "__main__":
    main()
