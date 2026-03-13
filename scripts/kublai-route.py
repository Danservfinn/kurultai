#!/usr/bin/env python3
"""
Kublai Task Router

Kublai intelligently routes tasks to appropriate agents based on:
- Task type and complexity
- Agent capabilities
- Current workload
- Priority
- Paused status (tasks marked as paused in Neo4j are not routed)

Usage:
    python3 kublai-route.py "Research prompt injection sandbox"
"""

import sys
import json
from datetime import datetime

sys.path.insert(0, '/Users/kublai/.openclaw/agents/main/scripts')

from kurultai_paths import AGENT_KEYWORDS

# Paused task patterns (tasks that should not be routed)
PAUSED_TASK_PATTERNS = [
    "llm.survivor",
    "llmsurvivor",
    "LLM Survivor",
    "llm-survivor"
]

# Paused agents (no tasks will be routed to these agents)
PAUSED_AGENTS = []

# Neo4j paused status check
def is_task_paused_in_neo4j(task_id):
    """Check if task is marked as PAUSED in Neo4j."""
    try:
        from neo4j_task_tracker import get_driver
        driver = get_driver()
        with driver.session() as session:
            result = session.run("""
                MATCH (t:Task {task_id: $task_id})
                RETURN t.status as status
            """, task_id=task_id)
            record = result.single()
            if record:
                status = record.get("status")
                return status == "PAUSED"
    except Exception:
        pass
    return False


def mark_task_paused_in_neo4j(task_id, agent, reason):
    """Mark a task as PAUSED in Neo4j."""
    try:
        from neo4j_task_tracker import get_driver
        driver = get_driver()
        with driver.session() as session:
            session.run("""
                MERGE (t:Task {task_id: $task_id})
                SET t.status = 'PAUSED',
                    t.paused_reason = $reason,
                    t.paused_at = datetime(),
                    t.agent = $agent
            """, task_id=task_id, reason=reason, agent=agent)
            return True
    except Exception as e:
        print(f"Warning: Could not mark task as paused in Neo4j: {e}", file=sys.stderr)
    return False


def should_pause_task(task_text, task_id=None):
    """Check if task should be paused based on content patterns."""
    task_lower = task_text.lower()
    
    # Check for paused patterns
    for pattern in PAUSED_TASK_PATTERNS:
        if pattern.lower() in task_lower:
            return True, f"Matches paused pattern: {pattern}"
    
    # Check Neo4j if task_id provided
    if task_id and is_task_paused_in_neo4j(task_id):
        return True, "Task marked as PAUSED in Neo4j"
    
    return False, None

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

# Task type indicators — imported from canonical source to prevent drift
# Previously had a local copy that diverged from kurultai_paths.AGENT_KEYWORDS
TASK_INDICATORS = {k: v for k, v in AGENT_KEYWORDS.items() if k not in ("kublai", "tolui")}

def kublai_route_task(task_text, priority="normal", task_id=None):
    """
    Kublai intelligently routes task to best agent.
    
    Decision factors:
    1. Check if task is paused (skip routing)
    2. Keyword matching (base score)
    3. Task complexity (simple → subagent, complex → full agent)
    4. Agent specialization
    5. Priority (high priority → most capable agent)
    """
    task_lower = task_text.lower()
    
    # RULE: Check if task should be paused
    should_pause, pause_reason = should_pause_task(task_text, task_id)
    if should_pause:
        # Mark as paused in Neo4j if task_id provided
        if task_id:
            mark_task_paused_in_neo4j(task_id, "NONE", pause_reason)
        
        return {
            "task": task_text[:100],
            "routed_by": "kublai",
            "destination": "PAUSED",
            "best_agent": "NONE",
            "best_score": 0,
            "complexity": "N/A",
            "scores": {},
            "reasoning": f"Task PAUSED: {pause_reason}",
            "priority": priority,
            "routed_at": datetime.now().isoformat(),
            "paused": True,
            "pause_reason": pause_reason
        }
    
    # RULE: Check if destination agent is paused
    for agent in PAUSED_AGENTS:
        if agent in task_lower:
            return {
                "task": task_text[:100],
                "routed_by": "kublai",
                "destination": "PAUSED",
                "best_agent": agent,
                "best_score": 0,
                "complexity": "N/A",
                "scores": {},
                "reasoning": f"Task PAUSED: Agent {agent} is currently paused",
                "priority": priority,
                "routed_at": datetime.now().isoformat(),
                "paused": True,
                "pause_reason": f"Agent {agent} paused"
            }
    
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

def pause_task_by_id(task_id, reason="Manual pause"):
    """Mark a task as paused by ID."""
    return mark_task_paused_in_neo4j(task_id, "NONE", reason)


def unpause_task_by_id(task_id):
    """Unpause a task by setting status back to PENDING."""
    try:
        from neo4j_task_tracker import get_driver
        driver = get_driver()
        with driver.session() as session:
            result = session.run("""
                MATCH (t:Task {task_id: $task_id})
                WHERE t.status = 'PAUSED'
                SET t.status = 'PENDING',
                    t.unpaused_at = datetime()
                REMOVE t.paused_reason, t.paused_at
                RETURN count(t) as count
            """, task_id=task_id)
            record = result.single()
            return record.get("count", 0) > 0
    except Exception as e:
        print(f"Error unpausing task: {e}", file=sys.stderr)
    return False


def list_paused_tasks():
    """List all paused tasks in Neo4j."""
    try:
        from neo4j_task_tracker import get_driver
        driver = get_driver()
        with driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.status = 'PAUSED'
                RETURN t.task_id as task_id, t.paused_reason as reason, 
                       t.paused_at as paused_at, t.agent as agent
                ORDER BY t.paused_at DESC
            """)
            paused = []
            for record in result:
                paused.append({
                    "task_id": record.get("task_id"),
                    "reason": record.get("reason"),
                    "paused_at": str(record.get("paused_at")),
                    "agent": record.get("agent")
                })
            return paused
    except Exception as e:
        print(f"Error listing paused tasks: {e}", file=sys.stderr)
    return []


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Kublai Task Router")
    parser.add_argument("task", nargs="?", help="Task text to route")
    parser.add_argument("--pause", metavar="TASK_ID", help="Pause a task by ID")
    parser.add_argument("--unpause", metavar="TASK_ID", help="Unpause a task by ID")
    parser.add_argument("--list-paused", action="store_true", help="List all paused tasks")
    parser.add_argument("--task-id", help="Task ID for routing (to check Neo4j pause status)")
    
    args = parser.parse_args()
    
    # Handle pause/unpause commands
    if args.pause:
        if pause_task_by_id(args.pause):
            print(f"Task {args.pause} marked as PAUSED")
        else:
            print(f"Failed to pause task {args.pause}")
        return
    
    if args.unpause:
        if unpause_task_by_id(args.unpause):
            print(f"Task {args.unpause} unpaused")
        else:
            print(f"Task {args.unpause} not found or not paused")
        return
    
    if args.list_paused:
        paused = list_paused_tasks()
        if paused:
            print("=== Paused Tasks ===")
            for t in paused:
                print(f"  {t['task_id']}: {t['reason']} (paused at {t['paused_at']})")
        else:
            print("No paused tasks")
        return
    
    # Route task
    if not args.task:
        parser.print_help()
        sys.exit(1)
    
    task = args.task
    
    print("=== Kublai Task Router ===")
    print(f"Task: {task[:80]}...")
    print()
    
    # Kublai routes the task
    routing = kublai_route_task(task, task_id=args.task_id)
    
    # Check if task was paused
    if routing.get("paused"):
        print("🚫 TASK PAUSED - Not routing")
        print(f"  Reason: {routing['pause_reason']}")
        print()
    
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
