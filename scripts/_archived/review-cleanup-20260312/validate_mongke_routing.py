#!/usr/bin/env python3
"""
validate_mongke_routing.py — Verify mongke research routing protection

Tests that non-research tasks do NOT route to mongke, preventing
EXECUTING_NO_OUTPUT issues from domain misalignment.

Run: python3 validate_mongke_routing.py
"""

import sys
sys.path.insert(0, '/Users/kublai/.openclaw/agents/main/scripts')

from kurultai_paths import AGENT_KEYWORDS
import re

# Disambiguation rules from task_intake.py (simplified version for testing)
# These should match the rules in task_intake.py _DISAMBIGUATION
MONGKE_PROTECTION_RULES = [
    ({"investigate", "calendar"}, "ogedei"),
    ({"investigate", "cron"}, "ogedei"),
    ({"investigate", "backup"}, "ogedei"),
    ({"investigate", "notification"}, "ogedei"),
    ({"enhance", "config"}, "jochi"),
    ({"enhance", "agent", "config"}, "jochi"),
    ({"fix", "config"}, "ogedei"),
    ({"calendar", "notification"}, "ogedei"),
    ({"agent", "config", "enhancement"}, "jochi"),
    ({"bidirectional", "linking"}, "temujin"),
    ({"test", "linking"}, "jochi"),
    ({"verify", "linking"}, "jochi"),
]

def test_should_not_route_to_mongke(task_text):
    """Test if a task should be blocked from routing to mongke."""
    text_lower = task_text.lower()
    words = set(text_lower.split())

    # Check protection rules
    for rule_keywords, target_agent in MONGKE_PROTECTION_RULES:
        if rule_keywords.issubset(words):
            return False, target_agent  # Should NOT route to mongke

    return True, None  # OK to route to mongke

# Test cases: non-research tasks that should NOT route to mongke
NON_RESEARCH_TASKS = [
    "investigate calendar notification config",
    "enhance agent config files",
    "fix cron notification settings",
    "bidirectional linking test",
    "verify linking functionality",
    "calendar notification gap analysis",
    "agent config enhancement plan",
    "investigate cron failure",
    "fix backup configuration",
]

# Test cases: research tasks that SHOULD route to mongke
RESEARCH_TASKS = [
    "research competitor pricing strategies",
    "market analysis for SaaS platforms",
    "competitive intelligence on API authentication",
    "investigate competitor market share",
    "benchmark pricing against alternatives",
    "research trend analysis for AI agents",
    "feature comparison for deployment platforms",
    "api discovery for authentication providers",
]

def main():
    print("=" * 60)
    print("MONGKE ROUTING VALIDATION")
    print("=" * 60)

    failures = []

    # Test 1: Non-research tasks should NOT route to mongke
    print("\n[TEST 1] Non-research tasks should NOT route to mongke:")
    print("-" * 60)
    for task in NON_RESEARCH_TASKS:
        should_route, target = test_should_not_route_to_mongke(task)
        if should_route:
            # This task slipped through - check keyword scoring
            mongke_score = sum(1 for kw in AGENT_KEYWORDS.get("mongke", [])
                             if kw in task.lower())
            if mongke_score > 0:
                print(f"  ❌ FAIL: '{task}'")
                print(f"     Would route to mongke (score: {mongke_score})")
                failures.append(f"{task} -> mongke (should be {target or 'other'})")
            else:
                print(f"  ✓ PASS: '{task}' (no mongke keywords)")
        else:
            print(f"  ✓ PASS: '{task}' -> {target}")

    # Test 2: Research tasks SHOULD route to mongke
    print("\n[TEST 2] Research tasks SHOULD route to mongke:")
    print("-" * 60)
    for task in RESEARCH_TASKS:
        mongke_score = sum(1 for kw in AGENT_KEYWORDS.get("mongke", [])
                         if kw in task.lower())
        if mongke_score > 0:
            print(f"  ✓ PASS: '{task}' (score: {mongke_score})")
        else:
            print(f"  ❌ FAIL: '{task}' (score: 0)")
            failures.append(f"{task} -> NOT mongke (should be research)")

    # Summary
    print("\n" + "=" * 60)
    if failures:
        print(f"FAILED: {len(failures)} test(s)")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    else:
        print("SUCCESS: All routing tests passed")
        return 0

if __name__ == "__main__":
    sys.exit(main())
