#!/usr/bin/env python3
"""
Kublai Task Router - Inline function for Kublai to classify and spawn agents

Usage in Kublai's message handler:
    from kublai_task_router import route_and_spawn
    result = route_and_spawn("Build a login feature")
    # Returns: {"agent": "temujin", "spawned": True, ...}
"""

import json
import os
import time
import subprocess
from datetime import datetime

SPAWN_QUEUE = "/Users/kublai/.openclaw/agents/main/logs/spawn-pending.json"
AGENT_ROUTING = {
    "temujin": {"keywords": ["build", "code", "implement", "fix", "bug", "feature", "deploy", "api", "database", "typescript", "python", "script"], "model": "qwen3.5-plus"},
    "mongke": {"keywords": ["research", "analyze", "investigate", "discover", "competitor", "market", "trend", "data"], "model": "qwen3.5-plus"},
    "chagatai": {"keywords": ["write", "document", "blog", "post", "content", "article", "creative", "copy", "marketing", "twitter"], "model": "qwen3.5-plus"},
    "jochi": {"keywords": ["test", "security", "audit", "review", "verify", "validate", "pattern", "scan"], "model": "MiniMax-M2.5"},
    "ogedei": {"keywords": ["monitor", "health", "alert", "failover", "ops", "uptime", "status", "dashboard", "cron"], "model": "qwen3.5-plus"}
}

def classify(message):
    """Classify message to agent"""
    msg_lower = message.lower()
    scores = {agent: sum(1 for kw in cfg["keywords"] if kw in msg_lower) for agent, cfg in AGENT_ROUTING.items()}
    
    # Boost action verbs
    for verb in ["build", "create", "implement", "fix", "research", "write", "test"]:
        if msg_lower.startswith(verb):
            scores[max(scores, key=scores.get)] = scores.get(max(scores, key=scores.get), 0) + 2
    
    best = max(scores, key=scores.get)
    return {
        "agent": best,
        "model": AGENT_ROUTING[best]["model"],
        "confidence": scores[best] / max(sum(scores.values()), 1)
    }

def route_and_spawn(message, priority="normal"):
    """
    Route message to agent and spawn immediately.
    
    Returns dict with agent, label, spawned status
    """
    # Classify
    classification = classify(message)
    label = f"{classification['agent']}-{int(time.time())}"
    
    # Write to queue
    os.makedirs(os.path.dirname(SPAWN_QUEUE), exist_ok=True)
    existing = []
    if os.path.exists(SPAWN_QUEUE):
        try:
            with open(SPAWN_QUEUE, 'r') as f:
                existing = json.load(f).get('spawns', [])
        except:
            pass
    
    spawn_request = {
        "agent": classification["agent"],
        "model": classification["model"],
        "task": message.strip()[:200],
        "priority": priority,
        "label": label,
        "source": "chat_direct",
        "created": datetime.now().isoformat(),
        "status": "pending"
    }
    existing.append(spawn_request)
    
    with open(SPAWN_QUEUE, 'w') as f:
        json.dump({'spawns': existing, 'updated': time.time()}, f, indent=2)
    
    # Call spawn handler to process immediately
    result = subprocess.run(
        ["python3", "/Users/kublai/.openclaw/agents/main/scripts/handle-spawns.py"],
        capture_output=True,
        text=True,
        timeout=30
    )
    
    return {
        "agent": classification["agent"],
        "model": classification["model"],
        "label": label,
        "task": message.strip()[:100],
        "priority": priority,
        "confidence": round(classification["confidence"], 2),
        "queued": True,
        "spawn_output": result.stdout.strip() if result.stdout else None
    }

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: kublai-task-router.py <message>")
        sys.exit(1)
    
    result = route_and_spawn(" ".join(sys.argv[1:]))
    print(json.dumps(result, indent=2))
