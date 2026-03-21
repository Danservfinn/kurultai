#!/usr/bin/env python3
"""
Add MODEL_CHANGE_PROHIBITED rule to all agent rules.json files.

This rule explicitly prohibits agents from proposing model changes.
Only the human operator can change models.
"""

import json
from pathlib import Path
from datetime import datetime

AGENTS_DIR = Path.home() / ".openclaw" / "agents"
AGENTS = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei"]

MODEL_LOCK_RULE = {
    "id": "MODEL_CHANGE_PROHIBITED",
    "text": "NEVER propose, suggest, or consider changing the agent model configuration (ANTHROPIC_MODEL, config.json model key, .claude/settings.json), provider routing (mode.json, claude-agent wrapper, provider.env), or backup/fallback settings. Model and routing changes are exclusively a human operator decision via the.kurult.ai dashboard. During reflections, reviews, or any analysis, DO NOT include model configuration, provider routing, or fallback chain as potential improvements, fixes, or optimizations. If you detect a mismatch, log it but DO NOT create tasks to fix it — only humans can change these. (Rule MODEL_LOCK)",
    "status": "active",
    "created_at": datetime.now().isoformat(),
    "source": "human-mandate:2026-03-08",
    "last_evaluated": None,
    "follow_count": 0,
    "violate_count": 0,
    "deprecated_reason": None,
    "priority": "CRITICAL",
    "category": "configuration-lock"
}

def add_rule_to_agent(agent_name):
    """Add the model lock rule to an agent's rules.json."""
    rules_path = AGENTS_DIR / agent_name / "memory" / "rules.json"
    
    if not rules_path.exists():
        print(f"  {agent_name}: No rules.json found, skipping")
        return False
    
    try:
        with open(rules_path, 'r') as f:
            data = json.load(f)
        
        rules = data.get("rules", [])
        
        # Check if rule already exists
        existing = [r for r in rules if r.get("id") == "MODEL_CHANGE_PROHIBITED"]
        if existing:
            print(f"  {agent_name}: Rule already exists")
            return False
        
        # Add rule at the beginning (highest priority)
        rules.insert(0, MODEL_LOCK_RULE)
        data["rules"] = rules
        
        # Write back
        with open(rules_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"  {agent_name}: Rule added")
        return True
        
    except Exception as e:
        print(f"  {agent_name}: Error - {e}")
        return False

def main():
    print("Adding MODEL_CHANGE_PROHIBITED rule to all agents...\n")
    
    added = 0
    for agent in AGENTS:
        if add_rule_to_agent(agent):
            added += 1
    
    print(f"\nComplete: {added}/{len(AGENTS)} agents updated")
    print("\nRule text:")
    print(f"  {MODEL_LOCK_RULE['text'][:200]}...")

if __name__ == "__main__":
    main()
