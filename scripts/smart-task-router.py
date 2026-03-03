#!/usr/bin/env python3
"""
Smart Task Router

Routes tasks to appropriate destination based on complexity and type:
- Simple tasks → subagent (one-shot)
- Code tasks → Temujin (full agent)
- Research tasks → Mongke (full agent)
- Writing tasks → Chagatai (full agent)
- Testing tasks → Jochi (full agent)
- Ops tasks → Ogedei (full agent)

Usage:
    python3 smart-task-router.py --task "Build a login feature"
    python3 smart-task-router.py --classify "Research competitor pricing"
"""

import argparse
import json
import os
import sys
from datetime import datetime

SPAWN_QUEUE = "/Users/kublai/.openclaw/agents/main/logs/spawn-pending.json"
AGENT_QUEUES = {
    "temujin": "/Users/kublai/.openclaw/agents/temujin/tasks",
    "mongke": "/Users/kublai/.openclaw/agents/mongke/tasks",
    "chagatai": "/Users/kublai/.openclaw/agents/chagatai/tasks",
    "jochi": "/Users/kublai/.openclaw/agents/jochi/tasks",
    "ogedei": "/Users/kublai/.openclaw/agents/ogedei/tasks",
    "kublai": "/Users/kublai/.openclaw/agents/kublai/tasks"
}

# Keyword-based routing
ROUTING_KEYWORDS = {
    "temujin": ["code", "build", "implement", "fix", "bug", "feature", "deploy", "api", "database", "typescript", "python", "script", "infrastructure"],
    "mongke": ["research", "analyze", "investigate", "discover", "competitor", "market", "trend", "data", "intelligence", "survey"],
    "chagatai": ["write", "document", "blog", "post", "content", "article", "creative", "copy", "marketing", "social", "twitter", "thread"],
    "jochi": ["test", "security", "audit", "review", "verify", "validate", "pattern", "scan", "vulnerability", "check"],
    "ogedei": ["monitor", "health", "alert", "failover", "ops", "uptime", "status", "dashboard", "cron", "infrastructure"]
}

def classify_task(task_text):
    """Classify task and determine routing destination"""
    task_lower = task_text.lower()
    
    # Score each agent based on keyword matches
    scores = {}
    for agent, keywords in ROUTING_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in task_lower)
        
        # Boost for action verbs at start
        if any(task_lower.startswith(verb) for verb in ["build", "create", "implement", "fix", "research", "write", "test"]):
            score += 2
        
        scores[agent] = score
    
    # Find best match
    best_agent = max(scores, key=scores.get)
    best_score = scores[best_agent]
    
    # Determine complexity
    complexity = "simple"
    if len(task_text.split()) > 20:
        complexity = "complex"
    if any(word in task_lower for word in ["multi-step", "pipeline", "workflow", "system", "architecture"]):
        complexity = "complex"
    
    # Determine routing
    if best_score == 0:
        destination = "subagent"  # No match, use simple subagent
    elif complexity == "simple" and best_score < 2:
        destination = "subagent"  # Simple task, use subagent
    else:
        destination = best_agent  # Route to full agent
    
    return {
        "task": task_text[:100],
        "best_agent": best_agent,
        "best_score": best_score,
        "complexity": complexity,
        "destination": destination,
        "scores": scores,
        "classified_at": datetime.now().isoformat()
    }

def route_to_agent(agent, task, priority="normal"):
    """Route task to agent's queue"""
    queue_path = AGENT_QUEUES.get(agent)
    if not queue_path:
        return {"success": False, "error": f"Unknown agent: {agent}"}
    
    # Create task file
    timestamp = int(datetime.now().timestamp())
    task_file = f"{queue_path}/{priority}-{timestamp}.md"
    
    os.makedirs(queue_path, exist_ok=True)
    
    with open(task_file, 'w') as f:
        f.write(f"""---
agent: {agent}
priority: {priority}
created: {datetime.now().isoformat()}
source: smart_router
---

# Task: {task}

Routed by smart-task-router.py
""")
    
    print(f"✓ Task routed to {agent}: {task_file}")
    
    return {
        "success": True,
        "agent": agent,
        "task_file": task_file,
        "priority": priority
    }

def route_to_subagent(task, priority="normal"):
    """Route task to subagent spawn queue"""
    os.makedirs(os.path.dirname(SPAWN_QUEUE), exist_ok=True)
    
    existing = []
    if os.path.exists(SPAWN_QUEUE):
        try:
            with open(SPAWN_QUEUE, 'r') as f:
                data = json.load(f)
                existing = data.get('spawns', [])
        except:
            pass
    
    spawn_request = {
        "agent": "subagent",
        "model": "qwen3.5-plus",
        "task": task,
        "priority": priority,
        "label": f"sub-{int(datetime.now().timestamp())}",
        "source": "smart_router",
        "destination": "subagent"
    }
    
    existing.append(spawn_request)
    
    with open(SPAWN_QUEUE, 'w') as f:
        json.dump({'spawns': existing, 'updated': datetime.now().timestamp()}, f, indent=2)
    
    print(f"✓ Task routed to subagent queue: {spawn_request['label']}")
    
    return {
        "success": True,
        "destination": "subagent",
        "spawn_label": spawn_request['label']
    }

def main():
    parser = argparse.ArgumentParser(description='Smart task router')
    parser.add_argument('--task', help='Task text to route')
    parser.add_argument('--classify', help='Classify task without routing')
    parser.add_argument('--priority', default='normal', choices=['high', 'normal', 'low'])
    parser.add_argument('--log', action='store_true', help='Log routing decision to Neo4j')
    
    args = parser.parse_args()
    
    if not args.task and not args.classify:
        print("Usage: python3 smart-task-router.py --task <text> OR --classify <text>")
        sys.exit(1)
    
    task_text = args.task or args.classify
    
    # Classify
    classification = classify_task(task_text)
    
    if args.classify:
        # Just classify, don't route
        print(json.dumps(classification, indent=2))
        return
    
    # Route
    print(f"=== Smart Task Router ===")
    print(f"Task: {task_text[:80]}...")
    print(f"Classification: {classification['complexity']} ({classification['best_agent']}, score={classification['best_score']})")
    print(f"Destination: {classification['destination']}")
    print()
    
    if classification['destination'] == 'subagent':
        result = route_to_subagent(task_text, args.priority)
    else:
        result = route_to_agent(classification['destination'], task_text, args.priority)
    
    # Log to Neo4j if requested
    if args.log:
        try:
            from neo4j import GraphDatabase
            driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "myStrongPassword123"))
            
            with driver.session() as session:
                session.run("""
                    CREATE (r:TaskRouting {
                        task: $task,
                        destination: $destination,
                        complexity: $complexity,
                        agent: $agent,
                        score: $score,
                        priority: $priority,
                        routed_at: datetime()
                    })
                """,
                task=task_text[:200],
                destination=classification['destination'],
                complexity=classification['complexity'],
                agent=classification['best_agent'],
                score=classification['best_score'],
                priority=args.priority)
            
            driver.close()
            print("✓ Routing decision logged to Neo4j")
        except Exception as e:
            print(f"⚠ Neo4j logging failed: {e}")
    
    print(f"\n✓ Routing complete")

if __name__ == "__main__":
    main()
