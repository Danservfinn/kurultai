#!/usr/bin/env python3
"""
Kublai Task Router

Kublai intelligently routes tasks to appropriate agents based on:
- Task type and complexity
- Agent capabilities
- Current workload
- Priority

Usage:
    python3 kublai-route.py "Research prompt injection sandbox"
"""

import sys
import json
from datetime import datetime

sys.path.insert(0, '/Users/kublai/.openclaw/agents/main/scripts')

# Agent capabilities
AGENT_CAPABILITIES = {
    "kublai": {
        "role": "Squad Lead / Router",
        "capabilities": ["task_routing", "synthesis", "oversight", "escalation", "strategic_planning"],
        "model": "claude-opus-4-6"
    },
    "temujin": {
        "role": "Developer",
        "capabilities": ["code_generation", "code_review", "debugging", "deployment", "infrastructure"],
        "model": "claude-opus-4-6"
    },
    "mongke": {
        "role": "Researcher",
        "capabilities": ["web_research", "api_discovery", "truth_seeking", "knowledge_gap_analysis", "ecosystem_intelligence"],
        "model": "claude-opus-4-6"
    },
    "chagatai": {
        "role": "Writer",
        "capabilities": ["writing", "documentation", "creative_content", "blog_posts", "social_media"],
        "model": "claude-opus-4-6"
    },
    "jochi": {
        "role": "Analyst",
        "capabilities": ["testing", "security", "pattern_recognition", "analysis", "validation"],
        "model": "claude-opus-4-6"
    },
    "ogedei": {
        "role": "Operations",
        "capabilities": ["monitoring", "health_checks", "failover", "infrastructure", "alerting"],
        "model": "claude-opus-4-6"
    }
}

# Task type indicators
TASK_INDICATORS = {
    "temujin": ["code", "build", "implement", "fix", "bug", "feature", "deploy", "api", "database", "typescript", "python", "script", "infrastructure", "sandbox", "llm", "integration"],
    "mongke": ["research", "analyze", "investigate", "discover", "competitor", "market", "trend", "data", "intelligence", "survey", "how to", "explore", "study"],
    "chagatai": ["write", "document", "blog", "post", "content", "article", "creative", "copy", "marketing", "social", "twitter", "thread", "description"],
    "jochi": ["test", "security", "audit", "review", "verify", "validate", "pattern", "scan", "vulnerability", "check", "prompt injection", "safety"],
    "ogedei": ["monitor", "health", "alert", "failover", "ops", "uptime", "status", "dashboard", "cron", "watch", "track"]
}

def kublai_route_task(task_text, priority="normal"):
    """
    Kublai intelligently routes task to best agent.
    
    Decision factors:
    1. Keyword matching (base score)
    2. Task complexity (simple → subagent, complex → full agent)
    3. Agent specialization
    4. Priority (high priority → most capable agent)
    """
    task_lower = task_text.lower()
    
    # Score each agent
    scores = {}
    for agent, indicators in TASK_INDICATORS.items():
        score = sum(2 for kw in indicators if kw in task_lower)
        
        # Boost for task starting with agent's primary action
        primary_actions = {
            "temujin": ["build", "create", "implement", "fix"],
            "mongke": ["research", "analyze", "investigate"],
            "chagatai": ["write", "document", "create"],
            "jochi": ["test", "verify", "audit"],
            "ogedei": ["monitor", "watch", "track"]
        }
        if any(task_lower.startswith(action) for action in primary_actions.get(agent, [])):
            score += 3
        
        scores[agent] = score
    
    # Find best match
    best_agent = max(scores, key=scores.get)
    best_score = scores[best_agent]
    
    # Determine complexity
    complexity = "simple"
    if len(task_text.split()) > 15:
        complexity = "complex"
    if any(word in task_lower for word in ["multi-step", "pipeline", "workflow", "system", "architecture", "sandbox", "injection", "security"]):
        complexity = "complex"
    
    # Kublai's decision logic
    destination = best_agent
    
    # Research tasks ALWAYS go to Mongke (highest priority)
    if "research" in task_lower or "how to" in task_lower or "investigate" in task_lower:
        if scores["mongke"] >= 2:
            destination = "mongke"
    
    # Security implementation (not research) goes to Jochi or Temujin
    elif "prompt injection" in task_lower or "security" in task_lower:
        if "test" in task_lower or "sandbox" in task_lower:
            destination = "jochi"  # Security testing
        elif "build" in task_lower or "implement" in task_lower or "create" in task_lower:
            destination = "temujin"  # Implementation
        else:
            destination = "jochi"  # Default security → analyst
    
    # Simple one-shot tasks → subagent
    if complexity == "simple" and best_score < 4:
        destination = "subagent"
    
    return {
        "task": task_text[:100],
        "routed_by": "kublai",
        "destination": destination,
        "best_agent": best_agent,
        "best_score": best_score,
        "complexity": complexity,
        "scores": scores,
        "reasoning": f"Kublai routed to {destination} based on task analysis",
        "priority": priority,
        "routed_at": datetime.now().isoformat()
    }

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 kublai-route.py <task>")
        sys.exit(1)
    
    task = " ".join(sys.argv[1:])
    
    print("=== Kublai Task Router ===")
    print(f"Task: {task[:80]}...")
    print()
    
    # Kublai routes the task
    routing = kublai_route_task(task)
    
    print(f"Kublai's Decision:")
    print(f"  Destination: {routing['destination']}")
    print(f"  Complexity: {routing['complexity']}")
    print(f"  Reasoning: {routing['reasoning']}")
    print()
    print(f"Agent Scores: {routing['scores']}")
    print()
    
    # Output as JSON for programmatic use
    print("Full routing decision:")
    print(json.dumps(routing, indent=2))

if __name__ == "__main__":
    main()
