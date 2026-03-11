#!/usr/bin/env python3
"""
Memory Rules Lifecycle Management for Kurultai Agents

Manages WHEN/THEN rules across all agents:
- Extracts rules from MEMORY.md into structured format
- Tracks rule lifecycle (proposed -> active -> deprecated -> pruned)
- Provides cross-agent visibility
- Enables pruning of outdated rules

Usage:
    python3 memory_rules_lifecycle.py extract [--agent AGENT]
    python3 memory_rules_lifecycle.py list [--status STATUS]
    python3 memory_rules_lifecycle.py promote RULE_ID
    python3 memory_rules_lifecycle.py deactivate RULE_ID [--reason REASON]
    python3 memory_rules_lifecycle.py prune --days DAYS
"""

import json
import re
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

# Configuration
AGENTS_DIR = Path("/Users/kublai/.openclaw/agents")
MAIN_SCRIPTS = AGENTS_DIR / "main" / "scripts"
RULES_REGISTRY = MAIN_SCRIPTS / "memory_rules_registry.json"

# Rule lifecycle states
STATUS_PROPOSED = "proposed"
STATUS_ACTIVE = "active"
STATUS_DEPRECATED = "deprecated"
STATUS_PRUNED = "pruned"

# WHEN/THEN rule patterns
# Pattern 1: O1: WHEN x THEN y (agent-specific rules)
RULE_PATTERN_AGENT = re.compile(
    r'-\s+(?P<rule_id>[A-Z]\d+|ogedei-\d+|kublai-\d+|temujin-\d+|mongke-\d+|chagatai-\d+|jochi-\d+|tolui-\d+):\s*'
    r'WHEN\s+(?P<when_clause>[^:]+?)\s+THEN\s+(?P<then_clause>[^\n]+)',
    re.IGNORECASE
)

# Pattern 2: **WHEN** x **THEN** y (main MEMORY.md style)
RULE_PATTERN_MAIN = re.compile(
    r'-\s+\*?\*?WHEN\*?\*?\s+(?P<when_clause>[^*]+?)\s+\*?\*?THEN\*?\*?\s+(?P<then_clause>[^\n]+)',
    re.IGNORECASE
)


class Rule:
    """Structured representation of a WHEN/THEN rule."""

    def __init__(
        self,
        rule_id: str,
        agent: str,
        when_clause: str,
        then_clause: str,
        status: str = STATUS_PROPOSED,
        created_at: Optional[str] = None,
        source_file: Optional[str] = None,
        category: str = "general"
    ):
        self.rule_id = rule_id
        self.agent = agent
        self.when_clause = when_clause.strip()
        self.then_clause = then_clause.strip()
        self.status = status
        self.created_at = created_at or datetime.now().isoformat()
        self.source_file = source_file
        self.category = category
        self.last_verified = None
        self.deprecation_reason = None

    def to_dict(self) -> Dict:
        return {
            "rule_id": self.rule_id,
            "agent": self.agent,
            "when": self.when_clause,
            "then": self.then_clause,
            "status": self.status,
            "created_at": self.created_at,
            "last_verified": self.last_verified,
            "source_file": self.source_file,
            "category": self.category,
            "deprecation_reason": self.deprecation_reason
        }


class RulesRegistry:
    """Manages the cross-agent rules registry."""

    def __init__(self):
        self.registry_path = RULES_REGISTRY
        self.rules: Dict[str, Dict] = {}
        self._load()

    def _load(self):
        """Load existing registry or create new."""
        if self.registry_path.exists():
            try:
                with open(self.registry_path, 'r') as f:
                    data = json.load(f)
                    self.rules = data.get("rules", {})
            except (json.JSONDecodeError, KeyError):
                self.rules = {}
        else:
            self.rules = {}

    def _save(self):
        """Persist registry to disk."""
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.registry_path, 'w') as f:
            json.dump({
                "rules": self.rules,
                "last_updated": datetime.now().isoformat(),
                "total_count": len(self.rules)
            }, f, indent=2)

    def add_rule(self, rule: Rule) -> bool:
        """Add or update a rule in the registry."""
        key = f"{rule.agent}:{rule.rule_id}"
        if key in self.rules and self.rules[key]["status"] != STATUS_PROPOSED:
            # Don't overwrite active rules without explicit promote
            return False
        self.rules[key] = rule.to_dict()
        self._save()
        return True

    def get_rule(self, rule_id: str, agent: str) -> Optional[Dict]:
        """Get a specific rule."""
        key = f"{agent}:{rule_id}"
        return self.rules.get(key)

    def list_rules(
        self,
        agent: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Dict]:
        """List rules with optional filters."""
        rules = list(self.rules.values())
        if agent:
            rules = [r for r in rules if r["agent"] == agent]
        if status:
            rules = [r for r in rules if r["status"] == status]
        return sorted(rules, key=lambda x: x.get("created_at", ""))

    def promote_rule(self, rule_id: str, agent: str) -> bool:
        """Promote a proposed rule to active."""
        key = f"{agent}:{rule_id}"
        if key not in self.rules:
            return False
        self.rules[key]["status"] = STATUS_ACTIVE
        self.rules[key]["last_verified"] = datetime.now().isoformat()
        self._save()
        return True

    def deactivate_rule(
        self,
        rule_id: str,
        agent: str,
        reason: str
    ) -> bool:
        """Deactivate a rule (mark as deprecated)."""
        key = f"{agent}:{rule_id}"
        if key not in self.rules:
            return False
        self.rules[key]["status"] = STATUS_DEPRECATED
        self.rules[key]["deprecation_reason"] = reason
        self.rules[key]["last_verified"] = datetime.now().isoformat()
        self._save()
        return True

    def prune_rules(self, days: int = 30) -> List[Dict]:
        """Prune deprecated rules older than N days."""
        cutoff = datetime.now() - timedelta(days=days)
        pruned = []
        for key, rule in list(self.rules.items()):
            if rule.get("status") == STATUS_DEPRECATED:
                last_verified = rule.get("last_verified", rule.get("created_at"))
                if last_verified:
                    verified_date = datetime.fromisoformat(last_verified)
                    if verified_date < cutoff:
                        rule["status"] = STATUS_PRUNED
                        pruned.append(rule)
        if pruned:
            self._save()
        return pruned

    def get_stats(self) -> Dict:
        """Get registry statistics."""
        stats = {
            "total": len(self.rules),
            "by_agent": {},
            "by_status": {}
        }
        for rule in self.rules.values():
            agent = rule["agent"]
            status = rule["status"]
            stats["by_agent"][agent] = stats["by_agent"].get(agent, 0) + 1
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
        return stats


def extract_rules_from_memory(agent: str) -> List[Rule]:
    """Extract WHEN/THEN rules from an agent's MEMORY.md file."""
    # kublai uses the "main" directory
    if agent == "kublai":
        memory_file = AGENTS_DIR / "main" / "memory" / "MEMORY.md"
    else:
        memory_file = AGENTS_DIR / agent / "memory" / "MEMORY.md"

    if not memory_file.exists():
        return []

    rules = []
    content = memory_file.read_text()

    # Find the "## Rules" or similar section
    rules_section = None
    for header in ["## Rules", "## WHEN/THEN Rules", "### WHEN/THEN Rules",
                   "### Routing Accuracy Rules", "### System Health Rules"]:
        if header in content:
            parts = content.split(header)
            if len(parts) > 1:
                # Get everything until the next top-level ## header
                # (but not ### which is a subsection)
                remaining = parts[1]
                lines = []
                for line in remaining.split('\n'):
                    if line.startswith('## ') and not line.startswith('### '):
                        break
                    lines.append(line)
                rules_section = '\n'.join(lines)
                break

    if not rules_section:
        rules_section = content  # Search entire file if no section found

    rule_counter = 1

    # First try agent-specific pattern (O1: WHEN x THEN y)
    for match in RULE_PATTERN_AGENT.finditer(rules_section):
        rule = Rule(
            rule_id=match.group("rule_id"),
            agent=agent,
            when_clause=match.group("when_clause"),
            then_clause=match.group("then_clause"),
            source_file=str(memory_file),
            category="memory"
        )
        rules.append(rule)
        rule_counter += 1

    # Then try main format (**WHEN** x **THEN** y)
    for match in RULE_PATTERN_MAIN.finditer(rules_section):
        # Generate rule ID for unnamed rules
        rule_id = f"{agent}-{rule_counter:02d}"
        rule = Rule(
            rule_id=rule_id,
            agent=agent,
            when_clause=match.group("when_clause"),
            then_clause=match.group("then_clause"),
            source_file=str(memory_file),
            category="memory"
        )
        rules.append(rule)
        rule_counter += 1

    return rules


def extract_all_agents() -> Dict[str, List[Rule]]:
    """Extract rules from all agent MEMORY.md files."""
    agents = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei", "tolui"]
    all_rules = {}
    for agent in agents:
        rules = extract_rules_from_memory(agent)
        if rules:
            all_rules[agent] = rules
    return all_rules


def cmd_extract(args):
    """Extract rules from MEMORY.md into registry."""
    registry = RulesRegistry()

    if args.agent:
        agents = [args.agent]
    else:
        agents = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei", "tolui"]

    total_added = 0
    for agent in agents:
        rules = extract_rules_from_memory(agent)
        for rule in rules:
            if registry.add_rule(rule):
                total_added += 1
                print(f"Added: {agent}:{rule.rule_id}")

    print(f"\nExtracted {total_added} rules for {len(agents)} agent(s)")


def cmd_list(args):
    """List rules from registry."""
    registry = RulesRegistry()

    rules = registry.list_rules(agent=args.agent, status=args.status)

    if not rules:
        print("No rules found.")
        return

    print(f"\n{'Agent':<10} {'ID':<15} {'Status':<12} {'WHEN clause'}")
    print("-" * 80)
    for rule in rules:
        when_short = rule["when"][:40] + "..." if len(rule["when"]) > 40 else rule["when"]
        print(f"{rule['agent']:<10} {rule['rule_id']:<15} {rule['status']:<12} {when_short}")

    print(f"\nTotal: {len(rules)} rule(s)")

    if args.stats:
        stats = registry.get_stats()
        print(f"\nStats: {json.dumps(stats, indent=2)}")


def cmd_promote(args):
    """Promote a proposed rule to active."""
    registry = RulesRegistry()

    # Auto-detect agent if not specified
    if not args.agent:
        for rule_id, rule in registry.rules.items():
            if rule["rule_id"] == args.rule_id:
                args.agent = rule["agent"]
                break
        else:
            print(f"Error: Rule '{args.rule_id}' not found. Specify --agent")
            return

    if registry.promote_rule(args.rule_id, args.agent):
        print(f"Promoted {args.agent}:{args.rule_id} to ACTIVE")
    else:
        print(f"Error: Rule '{args.agent}:{args.rule_id}' not found")


def cmd_deactivate(args):
    """Deactivate a rule."""
    registry = RulesRegistry()

    if not args.agent:
        print("Error: Specify --agent")
        return

    reason = args.reason or "Manual deactivation"
    if registry.deactivate_rule(args.rule_id, args.agent, reason):
        print(f"Deactivated {args.agent}:{args.rule_id}: {reason}")
    else:
        print(f"Error: Rule '{args.agent}:{args.rule_id}' not found")


def cmd_prune(args):
    """Prune old deprecated rules."""
    registry = RulesRegistry()
    days = args.days or 30

    pruned = registry.prune_rules(days)
    if pruned:
        print(f"Pruned {len(pruned)} rule(s) deprecated >{days} days ago:")
        for rule in pruned:
            print(f"  - {rule['agent']}:{rule['rule_id']}")
    else:
        print(f"No rules to prune (cutoff: {days} days)")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Memory Rules Lifecycle Management")
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # Extract command
    extract_parser = subparsers.add_parser("extract", help="Extract rules from MEMORY.md")
    extract_parser.add_argument("--agent", help="Specific agent (default: all)")

    # List command
    list_parser = subparsers.add_parser("list", help="List rules")
    list_parser.add_argument("--agent", help="Filter by agent")
    list_parser.add_argument("--status", help="Filter by status")
    list_parser.add_argument("--stats", action="store_true", help="Show statistics")

    # Promote command
    promote_parser = subparsers.add_parser("promote", help="Promote rule to active")
    promote_parser.add_argument("rule_id", help="Rule ID (e.g., O1)")
    promote_parser.add_argument("--agent", help="Agent (optional if rule exists)")

    # Deactivate command
    deactivate_parser = subparsers.add_parser("deactivate", help="Deactivate a rule")
    deactivate_parser.add_argument("rule_id", help="Rule ID")
    deactivate_parser.add_argument("--agent", required=True, help="Agent")
    deactivate_parser.add_argument("--reason", help="Deactivation reason")

    # Prune command
    prune_parser = subparsers.add_parser("prune", help="Prune old deprecated rules")
    prune_parser.add_argument("--days", type=int, default=30, help="Days threshold (default: 30)")

    args = parser.parse_args()

    if args.command == "extract":
        cmd_extract(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "promote":
        cmd_promote(args)
    elif args.command == "deactivate":
        cmd_deactivate(args)
    elif args.command == "prune":
        cmd_prune(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
