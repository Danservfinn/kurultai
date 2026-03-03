"""
Kublai Chat-to-Task Integration

Usage in Kublai's message handler:
    from chat_to_task import handle_chat_task
    result = handle_chat_task(user_message)
    # result = {"agent": "temujin", "spawned": True, "session": "..."}
"""

import json
import os
import time
from datetime import datetime

SPAWN_QUEUE = "/Users/kublai/.openclaw/agents/main/logs/spawn-pending.json"

AGENT_ROUTING = {
    "temujin": {"keywords": ["build", "code", "implement", "fix", "bug", "feature", "deploy", "api", "database", "typescript", "python", "script", "automation"], "model": "qwen3.5-plus"},
    "mongke": {"keywords": ["research", "analyze", "investigate", "discover", "competitor", "market", "trend", "data", "intelligence"], "model": "qwen3.5-plus"},
    "chagatai": {"keywords": ["write", "document", "blog", "post", "content", "article", "creative", "copy", "marketing", "twitter", "thread"], "model": "qwen3.5-plus"},
    "jochi": {"keywords": ["test", "security", "audit", "review", "verify", "validate", "pattern", "scan", "vulnerability"], "model": "MiniMax-M2.5"},
    "ogedei": {"keywords": ["monitor", "health", "alert", "failover", "ops", "uptime", "status", "dashboard", "cron"], "model": "qwen3.5-plus"}
}

def classify(message):
    msg_lower = message.lower()
    scores = {agent: sum(1 for kw in cfg["keywords"] if kw in msg_lower) for agent, cfg in AGENT_ROUTING.items()}
    
    # Boost action verbs at start
    for verb in ["build", "create", "implement", "fix", "research", "write", "test"]:
        if msg_lower.startswith(verb):
            scores[max(scores, key=scores.get)] = scores.get(max(scores, key=scores.get), 0) + 2
    
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        best = "kublai"  # Default to Kublai for unclear tasks
    
    return {
        "agent": best,
        "model": AGENT_ROUTING.get(best, {"model": "qwen3.5-plus"})["model"],
        "confidence": scores[best] / max(sum(scores.values()), 1)
    }

def queue_spawn(classification, message, priority="normal"):
    """Write to spawn queue and return spawn params"""
    label = f"{classification['agent']}-{int(time.time())}"
    
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
        "status": "ready"
    }
    existing.append(spawn_request)
    
    with open(SPAWN_QUEUE, 'w') as f:
        json.dump({'spawns': existing, 'updated': time.time()}, f, indent=2)
    
    return {
        **spawn_request,
        "queued": True
    }

def handle_chat_task(message, priority="normal"):
    """
    Full chat-to-task flow:
    1. Classify message
    2. Queue spawn request
    3. Return params for sessions_spawn
    
    Kublai calls this, then calls sessions_spawn with returned params.
    """
    classification = classify(message)
    spawn_params = queue_spawn(classification, message, priority)
    
    return {
        "classified": True,
        "agent": classification["agent"],
        "model": classification["model"],
        "label": spawn_params["label"],
        "task": message.strip()[:200],
        "priority": priority,
        "confidence": round(classification["confidence"], 2),
        "queued": True,
        "ready_to_spawn": True,
        "sessions_spawn_params": {
            "task": message.strip(),
            "runtime": "subagent",
            "label": spawn_params["label"],
            "model": classification["model"],
            "timeoutSeconds": 300
        }
    }

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python chat_to_task.py <message>")
        sys.exit(1)
    
    result = handle_chat_task(" ".join(sys.argv[1:]))
    print(json.dumps(result, indent=2))
