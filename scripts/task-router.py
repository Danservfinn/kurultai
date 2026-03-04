#!/usr/bin/env python3
"""
Unified Task Router

Classifies and routes tasks to appropriate agents using a local LLM (ollama).
Falls back to keyword scoring if the LLM is unavailable.

Usage:
    python3 task-router.py --task "Build a login feature"
    python3 task-router.py --classify "Research competitors"
"""

import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from json_state import locked_json_update

ROUTING_LOG = "/Users/kublai/.openclaw/agents/main/logs/routing-decisions.jsonl"

# ============================================================
# LLM ROUTER — Primary routing via local ollama
# ============================================================
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen3.5:9b"
OLLAMA_TIMEOUT = 5  # seconds — fail fast to fallback

LLM_SYSTEM_PROMPT = """You are a task router for a 6-agent AI team. Given a task, respond with ONLY the agent name — one word, lowercase, nothing else.

Agents:
- temujin: Software development — coding, building features, fixing bugs, APIs, database, deployment, scripts, automation
- mongke: Research & analysis — market research, competitor analysis, data exploration, trend investigation, ecosystem discovery
- chagatai: Writing & content — blog posts, documentation, marketing copy, changelogs, social media, creative writing
- jochi: Testing & security — QA testing, security audits, vulnerability scanning, code review, validation, compliance
- ogedei: DevOps & operations — monitoring, alerting, cron jobs, backups, uptime, health checks, infrastructure ops
- subagent: Simple one-off tasks that need no specialist"""

VALID_AGENTS = {"temujin", "mongke", "chagatai", "jochi", "ogedei", "subagent", "kublai"}


def _llm_classify(task_text):
    """Route task via local LLM. Returns agent name or None on failure."""
    try:
        payload = json.dumps({
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": LLM_SYSTEM_PROMPT},
                {"role": "user", "content": f"Route: {task_text}"},
            ],
            "stream": False,
            "think": False,
            "options": {"temperature": 0, "num_predict": 10},
        }).encode()
        req = urllib.request.Request(
            OLLAMA_URL, data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = json.loads(urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT).read())
        agent = resp.get("message", {}).get("content", "").strip().lower()
        # Validate — LLM must return a known agent name
        if agent in VALID_AGENTS:
            return agent
        return None
    except Exception:
        return None

SPAWN_QUEUE = "/Users/kublai/.openclaw/agents/main/logs/spawn-pending.json"
AGENT_QUEUES = {
    "temujin": "/Users/kublai/.openclaw/agents/temujin/tasks",
    "mongke": "/Users/kublai/.openclaw/agents/mongke/tasks",
    "chagatai": "/Users/kublai/.openclaw/agents/chagatai/tasks",
    "jochi": "/Users/kublai/.openclaw/agents/jochi/tasks",
    "ogedei": "/Users/kublai/.openclaw/agents/ogedei/tasks",
    "kublai": "/Users/kublai/.openclaw/agents/kublai/tasks"
}

# ============================================================
# CANONICAL ROUTING TABLE — Single source of truth
# All other routing dicts (kublai-actions.py, kublai-initiative.py,
# classify-task.py, kublai-route.py) are ARCHIVED or import from here.
# ============================================================
ROUTING_KEYWORDS = {
    "temujin": [
        "code", "build", "implement", "fix", "bug", "feature", "deploy",
        "api", "database", "typescript", "python", "script", "javascript",
        "infrastructure", "login", "oauth", "automation", "integration",
        "sandbox", "llm", "model",
    ],
    "mongke": [
        "research", "analyze", "investigate", "discover", "find", "study",
        "competitor", "market", "trend", "data", "intelligence", "survey",
        "how to", "explore", "api discovery", "ecosystem",
    ],
    "chagatai": [
        "write", "document", "blog", "post", "content", "article",
        "creative", "copy", "marketing", "social", "twitter", "thread",
        "readme", "describe", "description", "changelog",
    ],
    "jochi": [
        "test", "verify", "validate", "check",
        "security", "audit", "vulnerability", "scan", "prompt injection", "safety",
        "review", "pattern", "analysis", "analyze",
    ],
    "ogedei": [
        "monitor", "health", "alert", "uptime", "status", "dashboard",
        "failover", "ops", "cron", "restart", "backup",
        "watch", "track",
    ],
}

# Category-to-agent mapping (used by route_by_category)
CATEGORY_ROUTING = {
    "infrastructure": "ogedei",
    "code_fix": "temujin",
    "code": "temujin",
    "investigation": "jochi",
    "documentation": "chagatai",
    "research": "mongke",
    "coordination": "kublai",
    "monitoring": "ogedei",
    "security": "jochi",
    "writing": "chagatai",
    "ops": "ogedei",
}

# Disambiguation rules for multi-keyword matches
_DISAMBIGUATION = [
    ({"research", "security"}, "jochi"),
    ({"research", "vulnerabilit"}, "jochi"),  # matches vulnerability/vulnerabilities
    ({"research", "prompt injection"}, "jochi"),
    ({"research", "safety"}, "jochi"),
    ({"research", "audit"}, "jochi"),
    ({"build", "infrastructure"}, "temujin"),
    ({"implement", "infrastructure"}, "temujin"),
    ({"monitor", "infrastructure"}, "ogedei"),
    ({"fix", "cron"}, "ogedei"),
    ({"fix", "backup"}, "ogedei"),
    ({"fix", "monitor"}, "ogedei"),
    ({"write", "test"}, "jochi"),
    ({"document", "api"}, "chagatai"),
    ({"marketing", "copy"}, "chagatai"),
    ({"marketing", "content"}, "chagatai"),
    ({"validat", "deploy"}, "jochi"),  # matches validate/validation + deploy/deployment
]


def _keyword_classify(task_text):
    """Fallback: classify task via keyword scoring."""
    task_lower = task_text.lower()

    scores = {}
    for agent, keywords in ROUTING_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in task_lower)
        primary_verbs = {
            "temujin": ["build", "create", "implement", "fix"],
            "mongke": ["research", "investigate", "analyze", "explore"],
            "chagatai": ["write", "document", "describe"],
            "jochi": ["test", "verify", "audit", "review"],
            "ogedei": ["monitor", "watch", "track", "restart"],
        }
        if any(task_lower.startswith(verb) for verb in primary_verbs.get(agent, [])):
            score += 3
        scores[agent] = score

    best_agent = max(scores, key=scores.get)
    disambiguated = False
    for keywords_set, target_agent in _DISAMBIGUATION:
        if all(kw in task_lower for kw in keywords_set):
            best_agent = target_agent
            disambiguated = True
            break

    best_score = scores[best_agent]

    complexity = "simple"
    if len(task_text.split()) > 20:
        complexity = "complex"
    if any(word in task_lower for word in ["multi-step", "pipeline", "workflow", "system", "architecture", "sandbox", "injection"]):
        complexity = "complex"

    if disambiguated:
        destination = best_agent
    elif best_score == 0:
        destination = "subagent"
    elif complexity == "simple" and best_score < 2:
        destination = "subagent"
    else:
        destination = best_agent

    return destination, scores, complexity


def classify_task(task_text):
    """Classify task and determine routing destination.

    Primary: local LLM (ollama qwen3.5:9b) — understands context and nuance.
    Fallback: keyword scoring — used when LLM is unavailable.
    """
    method = "llm"
    destination = _llm_classify(task_text)

    if destination is None:
        method = "keyword_fallback"
        destination, scores, complexity = _keyword_classify(task_text)
    else:
        # LLM succeeded — still compute scores for metadata
        _, scores, complexity = _keyword_classify(task_text)

    result = {
        "task": task_text[:100],
        "destination": destination,
        "method": method,
        "complexity": complexity,
        "scores": scores,
        "classified_at": datetime.now().isoformat(),
    }

    # Log routing decision for audit trail
    _log_routing_decision(result)

    return result


def _log_routing_decision(decision):
    """Append routing decision to JSONL log for hourly audit."""
    try:
        os.makedirs(os.path.dirname(ROUTING_LOG), exist_ok=True)
        entry = {
            "ts": decision["classified_at"],
            "task": decision["task"],
            "dest": decision["destination"],
            "method": decision["method"],
            "complexity": decision["complexity"],
            "top_scores": {k: v for k, v in decision.get("scores", {}).items() if v > 0},
        }
        with open(ROUTING_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Never let logging break routing


def route_by_category(category):
    """Route by pre-classified category string. Returns agent name."""
    return CATEGORY_ROUTING.get(category.lower(), "kublai")


def route_by_text(text):
    """Convenience: classify text and return just the destination agent name."""
    result = classify_task(text)
    return result["destination"]

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
source: task_router
---

# Task: {task}

Routed by task-router.py
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
    spawn_request = {
        "agent": "subagent",
        "model": "qwen3.5-plus",
        "task": task,
        "priority": priority,
        "label": f"sub-{int(datetime.now().timestamp())}",
        "source": "task_router",
        "destination": "subagent"
    }

    os.makedirs(os.path.dirname(SPAWN_QUEUE), exist_ok=True)
    with locked_json_update(SPAWN_QUEUE, default={'spawns': [], 'updated': 0}) as data:
        if 'spawns' not in data:
            data['spawns'] = []
        data['spawns'].append(spawn_request)
        data['updated'] = datetime.now().timestamp()
    
    print(f"✓ Task routed to subagent queue: {spawn_request['label']}")
    
    return {
        "success": True,
        "destination": "subagent",
        "spawn_label": spawn_request['label']
    }

def route_task(message, priority="normal"):
    """Classify and route in one call"""
    classification = classify_task(message)
    destination = classification['destination']
    
    if destination == 'subagent':
        return route_to_subagent(message, priority)
    else:
        return route_to_agent(destination, message, priority)

def main():
    parser = argparse.ArgumentParser(description='Unified task router')
    parser.add_argument('--task', help='Task text to route')
    parser.add_argument('--classify', help='Classify task without routing')
    parser.add_argument('--priority', default='normal', choices=['high', 'normal', 'low'])
    
    args = parser.parse_args()
    
    if not args.task and not args.classify:
        print("Usage: python3 task-router.py --task <text> OR --classify <text>")
        sys.exit(1)
    
    task_text = args.task or args.classify
    
    # Classify
    classification = classify_task(task_text)
    
    if args.classify:
        # Just classify, don't route
        print(json.dumps(classification, indent=2))
        return
    
    # Route
    print(f"=== Task Router ===")
    print(f"Task: {task_text[:80]}...")
    print(f"Method: {classification['method']}")
    print(f"Destination: {classification['destination']} ({classification['complexity']})")
    print()
    
    if classification['destination'] == 'subagent':
        result = route_to_subagent(task_text, args.priority)
    else:
        result = route_to_agent(classification['destination'], task_text, args.priority)
    
    print(f"\n✓ Routing complete")

if __name__ == "__main__":
    main()
