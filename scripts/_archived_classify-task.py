#!/usr/bin/env python3
"""
Chat-to-Task Classifier - Analyzes messages and routes to appropriate agent queue

Usage:
    python3 classify-task.py "Build a new login feature for Parse"
    
Output:
    JSON with agent, task, priority, confidence
"""

import sys
import json
import re
from datetime import datetime

# Agent routing matrix
AGENT_ROUTING = {
    "temujin": {
        "keywords": ["build", "code", "implement", "fix", "bug", "feature", "deploy", 
                     "infrastructure", "api", "endpoint", "database", "typescript", 
                     "javascript", "python", "script", "automation", "integration"],
        "description": "Code generation, builds, infrastructure"
    },
    "mongke": {
        "keywords": ["research", "analyze", "investigate", "discover", "find", "study",
                     "competitor", "market", "trend", "data", "intelligence", "survey"],
        "description": "Research, API discovery, truth-seeking"
    },
    "chagatai": {
        "keywords": ["write", "document", "blog", "post", "content", "article", 
                     "creative", "copy", "marketing", "social", "twitter", "thread"],
        "description": "Writing, documentation, creative"
    },
    "jochi": {
        "keywords": ["test", "security", "audit", "review", "verify", "validate",
                     "pattern", "analysis", "check", "scan", "vulnerability"],
        "description": "Testing, security, analysis, pattern recognition"
    },
    "ogedei": {
        "keywords": ["monitor", "health", "alert", "failover", "ops", "deploy",
                     "infrastructure", "uptime", "status", "dashboard", "cron"],
        "description": "Monitoring, health checks, failover"
    }
}

def classify_message(message):
    """Classify a message and route to appropriate agent"""
    message_lower = message.lower()
    
    scores = {}
    
    # Score each agent based on keyword matches
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
    
    # Find best match
    best_agent = max(scores, key=scores.get)
    best_score = scores[best_agent]
    
    # Calculate confidence
    total_matches = sum(scores.values())
    confidence = best_score / max(total_matches, 1)
    
    # Determine priority
    priority = "normal"
    if any(word in message_lower for word in ["urgent", "asap", "critical", "emergency"]):
        priority = "high"
    elif any(word in message_lower for word in ["when you have time", "eventually", "nice to have"]):
        priority = "low"
    
    # Extract task description (clean up the message)
    task = message.strip()
    if len(task) > 200:
        task = task[:197] + "..."
    
    result = {
        "agent": best_agent,
        "task": task,
        "priority": priority,
        "confidence": round(confidence, 2),
        "scores": scores,
        "timestamp": datetime.now().isoformat(),
        "source": "chat_message"
    }
    
    return result

def main():
    if len(sys.argv) < 2:
        print("Usage: classify-task.py <message>")
        sys.exit(1)
    
    message = " ".join(sys.argv[1:])
    result = classify_message(message)
    
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
