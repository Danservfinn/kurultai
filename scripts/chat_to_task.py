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

def queue_spawn(classification, message, priority="normal", mode="run", continuous=False, retry_count=0):
    """Write to spawn queue and return spawn params"""
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from neo4j_task_tracker import get_tracker
    
    label = f"{classification['agent']}-{int(time.time())}"
    
    # Write to Neo4j
    try:
        tracker = get_tracker()
        tracker.create_task(
            label=label,
            agent=classification["agent"],
            task_desc=message.strip()[:200],
            priority=priority,
            mode=mode,
            continuous=continuous,
            source="chat_direct"
        )
    except Exception as e:
        print(f"Neo4j error: {e}")
    
    # For continuous tasks, register in separate registry (not main queue)
    if continuous:
        try:
            from continuous_registry import register as register_continuous
            register_continuous(
                label=label,
                agent=classification["agent"],
                task=message.strip()[:200]
            )
        except Exception as e:
            print(f"Continuous registry error: {e}")
    
    # Write to JSON queue (only for non-continuous, or initial spawn)
    if not continuous:
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
            "status": "ready",
            "mode": mode,
            "continuous": False,  # Don't set for queue
            "retry_count": retry_count,
            "max_retries": 3,
            "session_key": None,
            "completed_at": None,
            "error": None
        }
        existing.append(spawn_request)
        
        with open(SPAWN_QUEUE, 'w') as f:
            json.dump({'spawns': existing, 'updated': time.time()}, f, indent=2)
        
        return {
            **spawn_request,
            "queued": True
        }
    else:
        # Continuous task - return minimal info
        return {
            "agent": classification["agent"],
            "model": classification["model"],
            "label": label,
            "task": message.strip()[:200],
            "continuous": True,
            "queued": False,  # Not in main queue
            "registered": True  # In continuous registry
        }

def handle_chat_task(message, priority="normal", mode="run", continuous=False):
    """
    Full chat-to-task flow:
    1. Classify message
    2. Queue spawn request
    3. Return params for sessions_spawn
    
    Kublai calls this, then calls sessions_spawn with returned params.
    
    Args:
        mode: "run" (one-shot) or "session" (continuous/never-ending)
        continuous: If True, task never completes (for monitors/watchers)
    """
    classification = classify(message)
    spawn_params = queue_spawn(classification, message, priority, mode, continuous)
    
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
        "mode": mode,
        "continuous": continuous,
        "sessions_spawn_params": {
            "task": message.strip(),
            "runtime": "subagent",
            "label": spawn_params["label"],
            "model": classification["model"],
            "timeoutSeconds": 300 if not continuous else 0,  # 0 = no timeout for continuous
            "mode": mode
        }
    }

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python chat_to_task.py <message>")
        sys.exit(1)
    
    result = handle_chat_task(" ".join(sys.argv[1:]))
    print(json.dumps(result, indent=2))
