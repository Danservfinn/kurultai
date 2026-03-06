#!/usr/bin/env python3
"""
Unified Task Router

Classifies and routes tasks to appropriate agents using Claude (Kublai's LLM).
Falls back to keyword scoring if Claude is unavailable.

Usage:
    python3 task-router.py --task "Build a login feature"
    python3 task-router.py --classify "Research competitors"
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from json_state import locked_json_update

ROUTING_LOG = "/Users/kublai/.openclaw/agents/main/logs/routing-decisions.jsonl"
TASK_LEDGER = "/Users/kublai/.openclaw/tasks/task-ledger.jsonl"

# ============================================================
# CLAUDE ROUTER — Primary routing via Kublai's LLM
# ============================================================
CLAUDE_BIN = "/Users/kublai/.local/bin/claude"
CLAUDE_ROUTE_TIMEOUT = 30  # seconds for routing classification

LLM_SYSTEM_PROMPT = """You are Kublai, Squad Lead of the Kurultai. You are routing a task to the right agent. Respond with ONLY the agent name — one word, lowercase, nothing else.

Your agents:
- temujin: Developer — coding, building features, fixing bugs, APIs, database, deployment, scripts, automation, infrastructure code, system design, architecture, technical planning, brainstorming features, payment systems, billing logic, protocol design, SDK development, integrations
- mongke: Researcher — market research, competitor analysis, data exploration, trend investigation, ecosystem discovery, fact-finding, sourcing information
- chagatai: Writer — blog posts, documentation, marketing copy, changelogs, social media, creative writing, strategic briefs
- jochi: Analyst — testing, security audits, vulnerability scanning, code review, error investigation, data analysis, pattern recognition
- ogedei: Operations — monitoring, alerting, restarting services, backups, uptime, health checks, infrastructure ops, incident response
- kublai: Yourself — ONLY for triage decisions, cross-agent coordination, routing review, system-wide assessment. NEVER for design, implementation, research, writing, or analysis.

Judgment calls:
- "Design/architect/plan/spec a system or feature" → temujin (he designs and builds)
- "Brainstorm ideas for X" → temujin (he uses /horde-brainstorming)
- "Payment/billing/pricing system or protocol" → temujin (he implements)
- "x402/SDK/protocol/integration" → temujin (he builds integrations)
- "Investigate errors/failures/spikes" → jochi (he investigates), NOT ogedei
- "Fix code/script/cron" → temujin (he writes code), NOT ogedei
- "Restart service" or "service down" → ogedei (he keeps things running)
- "Build/add/create feature" → temujin (he builds)
- "Research/analyze market/competitors" → mongke (he researches)
- "Write docs/blog/content" → chagatai (he writes)
- "Triage stalled agent" or "system assessment" → kublai (you decide)
- "Kurultai architecture/OpenClaw design/agent system design" → kublai (you own the system architecture)"""

VALID_AGENTS = {"temujin", "mongke", "chagatai", "jochi", "ogedei", "subagent", "kublai"}


def _claude_classify(task_text):
    """Route task via Claude — Kublai's LLM. Returns (agent_name, None) or (None, error_reason)."""
    prompt = f"{LLM_SYSTEM_PROMPT}\n\nRoute this task: {task_text}"

    env = os.environ.copy()
    env.pop('CLAUDECODE', None)
    env['PATH'] = "/Users/kublai/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

    try:
        result = subprocess.run(
            [CLAUDE_BIN, "-p", "--model", "opus", "--dangerously-skip-permissions", prompt],
            capture_output=True,
            text=True,
            timeout=CLAUDE_ROUTE_TIMEOUT,
            env=env,
        )
        raw = result.stdout.strip().lower()
        # Extract just the agent name — Claude might add explanation
        for agent in VALID_AGENTS:
            if raw == agent or raw.startswith(agent + "\n") or raw.startswith(agent + " "):
                return agent, None
        # Try to find agent name anywhere in first line
        first_line = raw.split('\n')[0].strip().strip('.*,')
        if first_line in VALID_AGENTS:
            return first_line, None
        return None, f"invalid_response:{raw[:50]}"
    except subprocess.TimeoutExpired:
        return None, f"timeout:{CLAUDE_ROUTE_TIMEOUT}s"
    except Exception as e:
        return None, f"{type(e).__name__}:{str(e)[:50]}"


# Keep ollama as secondary fallback if Claude is down
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen3.5:9b"
OLLAMA_TIMEOUT = 10

def _ollama_classify(task_text):
    """Fallback: route via local ollama if Claude is unavailable."""
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
        if agent in VALID_AGENTS:
            return agent, None
        return None, f"invalid_response:{agent[:30]}"
    except Exception as e:
        return None, f"ollama_error:{str(e)[:50]}"

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
        "design", "architect", "architecture", "plan", "spec", "brainstorm",
        "prototype", "payment", "billing", "pricing", "x402", "protocol",
        "sdk", "webhook", "wallet",
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
    # Design/plan tasks go to temujin even when "research" appears
    ({"design", "research"}, "temujin"),
    ({"plan", "research"}, "temujin"),
    ({"brainstorm", "research"}, "temujin"),
    ({"payment", "research"}, "temujin"),
    ({"protocol", "research"}, "temujin"),
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
    if any(word in task_lower for word in ["multi-step", "pipeline", "workflow", "system", "architecture", "sandbox", "injection", "design", "protocol", "x402", "brainstorm"]):
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


def _prevent_self_routing(task_text, destination):
    """Prevent routing triage/assessment tasks to the agent they're about.

    Detects patterns like "Triage stalled agent: X" or "assessment: ... X backlog"
    and redirects to a different agent. Primary redirect: jochi (analyst).
    If jochi is the stalled agent, redirect to kublai (squad lead).
    This prevents deadlocks where a stalled agent receives its own triage task.
    """
    task_lower = task_text.lower()

    def _safe_redirect(stalled_agent):
        """Pick a redirect target that isn't the stalled agent."""
        if stalled_agent != "jochi":
            return "jochi"
        return "kublai"

    # Pattern 1: "triage stalled agent: <agent_name>"
    if "triage stalled agent:" in task_lower or "triage stalled agent " in task_lower:
        for agent in VALID_AGENTS - {"subagent"}:
            if agent in task_lower and destination == agent:
                return _safe_redirect(agent)

    # Pattern 2: "assessment: ... <agent_name> backlog" or similar
    if "assessment" in task_lower:
        for agent in VALID_AGENTS - {"subagent"}:
            if agent in task_lower and destination == agent:
                return _safe_redirect(agent)

    # Pattern 3: "tock assessment" routed to kublai — kublai is often idle when
    # this fires, causing circular deadlock (see bug 2026-03-05)
    if "tock assessment" in task_lower and destination == "kublai":
        return "jochi"

    return destination


def _estimate_complexity(task_text):
    """Lightweight complexity estimate (no keyword scoring)."""
    words = task_text.split()
    if len(words) > 15:
        return "complex"
    task_lower = task_text.lower()
    if any(w in task_lower for w in ["design", "architect", "system", "pipeline", "workflow", "protocol", "brainstorm", "multi-step"]):
        return "complex"
    return "simple"


def classify_task(task_text):
    """Classify task and determine routing destination.

    Primary: Claude Code — full intelligence for routing decisions.
    Secondary: ollama (local) — if Claude is unavailable.
    Last resort: keyword scoring (emergency only).
    """
    task_id = str(uuid.uuid4())
    method = "claude"
    destination, claude_error = _claude_classify(task_text)
    llm_error = claude_error

    if destination is None:
        # Claude unavailable — try ollama
        method = "ollama_fallback"
        destination, ollama_error = _ollama_classify(task_text)
        if ollama_error:
            llm_error = f"claude:{claude_error}|ollama:{ollama_error}"

    if destination is None:
        # Both LLMs down — keyword emergency fallback
        method = "keyword_fallback"
        destination, scores, complexity = _keyword_classify(task_text)
    else:
        scores = {}
        complexity = _estimate_complexity(task_text)

    # Guard: prevent routing triage tasks to the agent they're about
    destination = _prevent_self_routing(task_text, destination)

    # Auto-detect skill_hint based on task content and destination
    skill_hint = _detect_skill_hint(task_text, destination)

    result = {
        "task_id": task_id,
        "task": task_text[:100],
        "destination": destination,
        "method": method,
        "complexity": complexity,
        "classified_at": datetime.now().isoformat(),
    }
    if scores:
        result["scores"] = scores
    if skill_hint:
        result["skill_hint"] = skill_hint
    if llm_error:
        result["llm_error"] = llm_error

    # Log routing decision for audit trail
    _log_routing_decision(result)

    return result


def _detect_skill_hint(task_text, destination):
    """Auto-detect appropriate skill_hint based on task content."""
    task_lower = task_text.lower()
    if destination == "temujin":
        if any(w in task_lower for w in ["design", "architect", "brainstorm", "plan", "protocol", "payment"]):
            return "/horde-brainstorming"
        if any(w in task_lower for w in ["debug", "failing", "broken", "error", "crash"]):
            return "/systematic-debugging"
    if destination == "mongke":
        if any(w in task_lower for w in ["scrape", "extract", "crawl"]):
            return "/scrapling-research"
        if any(w in task_lower for w in ["research", "investigate", "discover", "explore"]):
            return "/horde-learn"
    if destination == "chagatai":
        if any(w in task_lower for w in ["blog", "article", "long-form", "content"]):
            return "/content-research-writer"
        if any(w in task_lower for w in ["changelog", "release notes"]):
            return "/changelog-generator"
    if destination == "jochi":
        if any(w in task_lower for w in ["debug", "bug", "failure", "error", "crash"]):
            return "/systematic-debugging"
        if any(w in task_lower for w in ["review", "audit", "security"]):
            return "/code-reviewer"
    if destination == "ogedei":
        if any(w in task_lower for w in ["health", "diagnostic", "system check"]):
            return "/kurultai-health"
        if any(w in task_lower for w in ["deploy", "railway", "production"]):
            return "/dev-deploy"
    return None


def _append_ledger(entry):
    """Append an event to the unified task-ledger.jsonl."""
    try:
        os.makedirs(os.path.dirname(TASK_LEDGER), exist_ok=True)
        with open(TASK_LEDGER, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Never let ledger writes break task flow


def _log_routing_decision(decision):
    """Append routing decision to JSONL log for hourly audit."""
    try:
        os.makedirs(os.path.dirname(ROUTING_LOG), exist_ok=True)
        entry = {
            "task_id": decision.get("task_id"),
            "ts": decision["classified_at"],
            "task": decision["task"],
            "dest": decision["destination"],
            "method": decision["method"],
            "complexity": decision.get("complexity"),
        }
        scores = decision.get("scores", {})
        if scores:
            entry["top_scores"] = {k: v for k, v in scores.items() if v > 0}
        if decision.get("skill_hint"):
            entry["skill_hint"] = decision["skill_hint"]
        if decision.get("llm_error"):
            entry["llm_error"] = decision["llm_error"]
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

def route_to_agent(agent, task, priority="normal", task_id=None, skill_hint=None):
    """Route task to agent's queue"""
    queue_path = AGENT_QUEUES.get(agent)
    if not queue_path:
        return {"success": False, "error": f"Unknown agent: {agent}"}

    task_id = task_id or str(uuid.uuid4())

    # Create task file
    timestamp = int(datetime.now().timestamp())
    task_file = f"{queue_path}/{priority}-{timestamp}.md"

    os.makedirs(queue_path, exist_ok=True)

    # Build frontmatter
    frontmatter_lines = [
        "---",
        f"task_id: {task_id}",
        f"agent: {agent}",
        f"priority: {priority}",
        f"created: {datetime.now().isoformat()}",
        f"source: task_router",
    ]
    if skill_hint:
        frontmatter_lines.append(f"skill_hint: {skill_hint}")
    frontmatter_lines.append("---")

    with open(task_file, 'w') as f:
        f.write("\n".join(frontmatter_lines))
        f.write(f"\n\n# Task: {task}\n\nRouted by task-router.py\n")

    print(f"✓ Task routed to {agent}: {task_file}")

    # Emit QUEUED event to task ledger
    _append_ledger({
        "task_id": task_id,
        "event": "QUEUED",
        "ts": datetime.now().isoformat(),
        "agent": agent,
        "priority": priority,
        "task_summary": task[:200],
        "skill_hint": skill_hint,
        "task_file": task_file,
    })

    return {
        "success": True,
        "agent": agent,
        "task_id": task_id,
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
        return route_to_agent(
            destination, message, priority,
            task_id=classification.get("task_id"),
            skill_hint=classification.get("skill_hint"),
        )

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
        result = route_to_agent(
            classification['destination'], task_text, args.priority,
            task_id=classification.get("task_id"),
            skill_hint=classification.get("skill_hint"),
        )
    
    print(f"\n✓ Routing complete")

if __name__ == "__main__":
    main()
