#!/usr/bin/env python3
"""
rule_registry.py — Persistent structured storage for agent WHEN/THEN rules.

Solves the problem of rules being lost when daily memory files are rotated.
Rules are stored in ~/.openclaw/agents/<agent>/memory/rules.json with full
lifecycle tracking: proposed -> active -> deprecated -> pruned.

Usage:
    from rule_registry import get_active_rules, add_rule, seed_from_memory

    # Get rules for reflection injection
    rules = get_active_rules("mongke")

    # Add a new rule from a reflection
    add_rule("mongke", "WHEN research task assigned THEN validate sources <5s")

    # Seed from existing memory files (one-time migration)
    seed_from_memory("mongke")
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kurultai_paths import AGENTS_DIR, VALID_AGENTS

MAX_ACTIVE_RULES = 7
MAX_PRUNED_RETENTION_DAYS = 30


def _rules_path(agent: str) -> Path:
    """Return path to an agent's rules.json file (memory subdirectory)."""
    return AGENTS_DIR / agent / "memory" / "rules.json"


def _behavioral_rules_path(agent: str) -> Path:
    """Return path to an agent's behavioral rules.json file (agent root level).

    This is the behavioral rules format used by R008 enforcement:
    - enabled: true/false
    - when: trigger condition
    - then: action to take
    """
    return AGENTS_DIR / agent / "rules.json"


def load_rules(agent: str) -> dict:
    """Load the rules registry for an agent. Returns empty structure if missing."""
    path = _rules_path(agent)
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            # Ensure structure
            if "rules" not in data:
                data["rules"] = []
            return data
        except (json.JSONDecodeError, IOError):
            pass
    return {"rules": [], "max_active": MAX_ACTIVE_RULES, "last_updated": None}


def save_rules(agent: str, data: dict) -> bool:
    """Persist rules registry to disk with atomic write pattern.
    
    Task 7.2: Uses temp file + validate + atomic rename to prevent corruption.
    """
    path = _rules_path(agent)
    path.parent.mkdir(parents=True, exist_ok=True)
    data["last_updated"] = datetime.now().isoformat()
    
    # Task 7.2: Atomic write pattern - write to temp, validate, then rename
    temp_path = f"{path}.tmp"
    try:
        # Write to temp file first
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        
        # Validate by reading it back
        with open(temp_path, "r", encoding="utf-8") as f:
            json.load(f)  # Will raise JSONDecodeError if corrupt
        
        # Atomic rename (os.replace is atomic on POSIX)
        os.replace(temp_path, path)
        return True
    except (IOError, json.JSONDecodeError) as e:
        # Clean up temp file on failure
        try:
            os.remove(temp_path)
        except OSError:
            pass
        return False


def get_active_rules(agent: str) -> list[str]:
    """Return list of active rule texts for an agent (max MAX_ACTIVE_RULES).

    Checks two sources:
    1. memory/rules.json - rule_registry format (status="active", text="WHEN...THEN...")
    2. rules.json (agent root) - behavioral rules format (enabled, when/then fields)
    """
    rules = []

    # Source 1: rule_registry in memory/ subdirectory
    data = load_rules(agent)
    registry_rules = [
        r["text"] for r in data.get("rules", [])
        if r.get("status") == "active" and "text" in r
    ]
    rules.extend(registry_rules)

    # Source 2: behavioral rules in agent root (created by R008 enforcement)
    behavioral_path = _behavioral_rules_path(agent)
    if behavioral_path.exists():
        try:
            with open(behavioral_path, encoding="utf-8") as f:
                behavioral_data = json.load(f)
            for r in behavioral_data.get("rules", []):
                if r.get("enabled") and "when" in r and "then" in r:
                    rules.append(f"WHEN {r['when']} THEN {r['then']}")
        except (json.JSONDecodeError, IOError):
            pass  # If behavioral rules file is corrupt, skip it

    return rules[:MAX_ACTIVE_RULES]


def add_rule(agent: str, text: str, source: str = "reflection",
             status: str = "active") -> bool:
    """Add a new rule. Deduplicates by normalized text."""
    data = load_rules(agent)
    normalized = text.lower().strip()

    # Check for duplicates
    for r in data["rules"]:
        if r.get("text", "").lower().strip() == normalized:
            # Reactivate if deprecated
            if r["status"] in ("deprecated", "pruned") and status == "active":
                r["status"] = "active"
                r["reactivated_at"] = datetime.now().isoformat()
                save_rules(agent, data)
            return True

    # Enforce max active rules — deprecate oldest if at limit
    active = [r for r in data["rules"] if r.get("status") == "active"]
    if status == "active" and len(active) >= MAX_ACTIVE_RULES:
        oldest_active = min(active, key=lambda r: r.get("created_at", ""))
        oldest_active["status"] = "deprecated"
        oldest_active["deprecated_reason"] = "auto: max rules reached, replaced by newer rule"
        oldest_active["deprecated_at"] = datetime.now().isoformat()

    rule_id = f"r{len(data['rules']) + 1:03d}"
    data["rules"].append({
        "id": rule_id,
        "text": text,
        "status": status,
        "created_at": datetime.now().isoformat(),
        "source": source,
        "last_evaluated": None,
        "follow_count": 0,
        "violate_count": 0,
        "deprecated_reason": None,
    })
    return save_rules(agent, data)


def deprecate_rule(agent: str, rule_id: str, reason: str = "superseded") -> bool:
    """Mark a rule as deprecated."""
    data = load_rules(agent)
    for r in data["rules"]:
        if r["id"] == rule_id and r["status"] == "active":
            r["status"] = "deprecated"
            r["deprecated_reason"] = reason
            r["deprecated_at"] = datetime.now().isoformat()
            return save_rules(agent, data)
    return False


def record_evaluation(agent: str, rule_id: str, followed: bool) -> bool:
    """Record whether a rule was followed during a reflection evaluation."""
    data = load_rules(agent)
    for r in data["rules"]:
        if r["id"] == rule_id:
            r["last_evaluated"] = datetime.now().isoformat()
            if followed:
                r["follow_count"] = r.get("follow_count", 0) + 1
            else:
                r["violate_count"] = r.get("violate_count", 0) + 1
            return save_rules(agent, data)
    return False


def seed_from_memory(agent: str) -> int:
    """Extract rules from existing memory files and add them to the registry.

    Scans:
    1. Agent's daily memory files (e.g., 2026-03-06.md)
    2. Claude project MEMORY.md files

    Returns number of rules seeded.
    """
    import re

    seeded = 0

    # Source 1: Daily memory files
    memory_dir = AGENTS_DIR / agent / "memory"
    if memory_dir.exists():
        for f in sorted(memory_dir.glob("*.md"), reverse=True):
            if f.name == "rules.json" or f.name == "context.md":
                continue
            seeded += _extract_and_add_rules(agent, f)

    # Source 2: Claude project MEMORY.md files
    claude_projects = Path.home() / ".claude" / "projects"
    if claude_projects.exists():
        for proj_dir in claude_projects.iterdir():
            mem_file = proj_dir / "memory" / "MEMORY.md"
            if not mem_file.exists():
                continue
            # Check if this project belongs to this agent
            dirname = proj_dir.name
            if agent in dirname or (agent == "kublai" and "main" in dirname):
                seeded += _extract_and_add_rules(agent, mem_file)

    return seeded


def _extract_and_add_rules(agent: str, filepath: Path) -> int:
    """Extract WHEN/THEN rules from a file and add to registry."""
    import re

    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return 0

    rules_found = []

    # Pattern 1: Lines with WHEN...THEN
    for line in content.split("\n"):
        line = line.strip()
        if re.search(r"\bWHEN\b.+\bTHEN\b", line, re.IGNORECASE):
            # Clean markdown formatting
            cleaned = re.sub(r"^[-*>]\s*", "", line)
            cleaned = re.sub(r"^\d+[\.\)]\s*", "", cleaned)
            cleaned = re.sub(r"^\*{2,}[^*]+\*{2,}[:\s]*", "", cleaned)
            # Remove surrounding quotes
            cleaned = re.sub(r'^["\']|["\']$', "", cleaned)
            cleaned = cleaned.strip()

            # Skip template placeholders
            if re.search(
                r"\[trigger\]|\[action\]|\[old default\]|\[default\]|\[new WHEN",
                cleaned, re.IGNORECASE
            ):
                continue
            # Skip evaluation comments (e.g., "WHEN x THEN y" — NO. reason)
            if re.search(r"\u2014\s*(YES|NO)\b", cleaned):
                continue
            # Skip lines that are just "RULE: [...]"
            if re.match(r"^RULE:\s*\[", cleaned, re.IGNORECASE):
                continue
            # Skip instruction/example lines (contain backtick-wrapped WHEN/THEN)
            if re.search(r'`[^`]*WHEN[^`]*THEN[^`]*`', cleaned, re.IGNORECASE):
                continue
            # Skip lines that don't start with WHEN (they're prose containing WHEN/THEN)
            if not re.match(r"^WHEN\b", cleaned, re.IGNORECASE):
                continue
            if len(cleaned) > 10:
                rules_found.append(cleaned)

    added = 0
    for rule_text in rules_found:
        # Check if already exists
        data = load_rules(agent)
        normalized = rule_text.lower().strip()
        exists = any(r.get("text", "").lower().strip() == normalized for r in data["rules"])
        if not exists:
            add_rule(agent, rule_text, source=f"seeded:{filepath.name}")
            added += 1

    return added


def format_rules_block(agent: str) -> str:
    """Format rules for injection into reflection context.

    Returns markdown block with active rules + lifecycle stats.
    """
    data = load_rules(agent)
    active = [r for r in data["rules"] if r.get("status") == "active"]
    deprecated = [r for r in data["rules"] if r.get("status") == "deprecated"]

    if not active:
        return "(No active rules in registry.)"

    lines = []
    for i, r in enumerate(active[:MAX_ACTIVE_RULES], 1):
        follow = r.get("follow_count", 0)
        violate = r.get("violate_count", 0)
        total = follow + violate
        if total > 0:
            rate = f" [{follow}/{total} followed]"
        else:
            rate = ""
        lines.append(f"  {i}. {r['text']}{rate}")

    if deprecated:
        lines.append(f"  ({len(deprecated)} deprecated rule(s) in history)")

    return "\n".join(lines)



def prune_stale_rules(agent: str, max_age_days: int = 7, dry_run: bool = False, create_backup: bool = True) -> int:
    """Prune deprecated rules with 0 evaluations older than max_age_days.
    
    Args:
        agent: Agent name
        max_age_days: Age threshold for pruning deprecated rules
        dry_run: If True, only report what would be pruned without modifying
        create_backup: If True, create backup before pruning
    
    Returns count of rules pruned.
    """
    from datetime import timedelta
    
    data = load_rules(agent)
    cutoff = datetime.now() - timedelta(days=max_age_days)
    pruned = 0
    kept = []

    # Create backup before pruning (if not dry run)
    if not dry_run and create_backup:
        import shutil
        rules_path = _rules_path(agent)
        if rules_path.exists():
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            backup_path = f"{rules_path}.bak.{timestamp}"
            shutil.copy2(rules_path, backup_path)
            print(f"  Backup created: {backup_path}")
    
    for rule in data["rules"]:
        # Keep active rules
        if rule.get("status") == "active":
            kept.append(rule)
            continue
        
        # Keep deprecated rules with evaluation history
        follow = rule.get("follow_count", 0)
        violate = rule.get("violate_count", 0)
        if follow > 0 or violate > 0:
            kept.append(rule)
            continue
        
        # Check if deprecated rule is old enough to prune
        deprecated_at = rule.get("deprecated_at")
        if deprecated_at:
            try:
                dep_time = datetime.fromisoformat(deprecated_at)
                if dep_time > cutoff:
                    kept.append(rule)  # Not old enough yet
                    continue
            except:
                kept.append(rule)  # Can't parse, keep it
                continue
        
        # Mark as pruned (only if not dry run)
        if not dry_run:
            rule["status"] = "pruned"
            rule["pruned_at"] = datetime.now().isoformat()
            rule["pruned_reason"] = f"stale: 0 evaluations, deprecated > {max_age_days} days"
        kept.append(rule)
        pruned += 1
    
    if pruned > 0 and not dry_run:
        data["rules"] = kept
        data["last_updated"] = datetime.now().isoformat()
        path = _rules_path(agent)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    
    return pruned


def archive_pruned_rules(agent: str, dry_run: bool = False) -> int:
    """Archive pruned rules to separate file after retention period."""
    from datetime import timedelta
    
    data = load_rules(agent)
    cutoff = datetime.now() - timedelta(days=MAX_PRUNED_RETENTION_DAYS)
    archived = 0
    kept = []
    
    archive_path = AGENTS_DIR / agent / "memory" / "rules_archive.json"
    archive_data = {"archived_rules": [], "last_archived": None}
    
    if archive_path.exists():
        try:
            with open(archive_path, "r") as f:
                archive_data = json.load(f)
        except:
            pass
    
    for rule in data["rules"]:
        if rule.get("status") != "pruned":
            kept.append(rule)
            continue
        
        pruned_at = rule.get("pruned_at")
        if pruned_at:
            try:
                if datetime.fromisoformat(pruned_at) > cutoff:
                    kept.append(rule)
                    continue
            except:
                kept.append(rule)
                continue
        
        if not dry_run:
            rule["archived_at"] = datetime.now().isoformat()
            archive_data["archived_rules"].append(rule)
        archived += 1
    
    if archived > 0 and not dry_run:
        archive_data["last_archived"] = datetime.now().isoformat()
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with open(archive_path, "w") as f:
            json.dump(archive_data, f, indent=2)
        
        data["rules"] = kept
        data["last_updated"] = datetime.now().isoformat()
        with open(_rules_path(agent), "w") as f:
            json.dump(data, f, indent=2)
        
        print(f"  Archived {archived} rules to: {archive_path}")
    
    return archived


def archive_all_agents(dry_run: bool = False) -> dict:
    """Archive pruned rules for all agents."""
    results = {}
    total = 0
    for agent in sorted(VALID_AGENTS):
        count = archive_pruned_rules(agent, dry_run=dry_run)
        if count > 0:
            results[agent] = count
            total += count
    if total == 0:
        print("No pruned rules to archive")
    else:
        print(f"Total: {total} rules archived")
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Agent rule registry management")
    parser.add_argument("command", choices=["list", "seed", "seed-all", "stats", "prune-all", "archive", "archive-all"],
                        help="Command to run")
    parser.add_argument("--agent", help="Agent name (required for list/seed)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be pruned without modifying")
    args = parser.parse_args()

    if args.command == "seed-all":
        for agent in sorted(VALID_AGENTS):
            count = seed_from_memory(agent)
            print(f"{agent}: seeded {count} rule(s)")
    elif args.command == "seed":
        if not args.agent:
            print("--agent required for seed")
            sys.exit(1)
        count = seed_from_memory(args.agent)
        print(f"{args.agent}: seeded {count} rule(s)")
    elif args.command == "list":
        if not args.agent:
            print("--agent required for list")
            sys.exit(1)
        rules = get_active_rules(args.agent)
        if rules:
            for i, r in enumerate(rules, 1):
                print(f"  {i}. {r}")
        else:
            print("  (no active rules)")
    elif args.command == "stats":
        for agent in sorted(VALID_AGENTS):
            data = load_rules(agent)
            active = sum(1 for r in data["rules"] if r.get("status") == "active")
            deprecated = sum(1 for r in data["rules"] if r.get("status") == "deprecated")
            total = len(data["rules"])
            print(f"{agent}: {active} active, {deprecated} deprecated, {total} total")
    elif args.command == "archive-all":
        archive_all_agents(dry_run=args.dry_run)

    elif args.command == "archive":
        if not args.agent:
            print("--agent required")
            sys.exit(1)
        count = archive_pruned_rules(args.agent, dry_run=args.dry_run)
        print(f"{args.agent}: archived {count} pruned rules" if count else f"{args.agent}: no rules to archive")

    elif args.command == "prune-all":
        total_pruned = 0
        for agent in sorted(VALID_AGENTS):
            pruned = prune_stale_rules(agent, dry_run=args.dry_run)
            if pruned > 0:
                if args.dry_run:
                    print(f"{agent}: would prune {pruned} stale deprecated rules")
                else:
                    print(f"{agent}: pruned {pruned} stale deprecated rules")
                total_pruned += pruned
        if total_pruned == 0:
            if args.dry_run:
                print("No stale rules found to prune")
            else:
                print("No stale rules to prune")
        else:
            if args.dry_run:
                print(f"Total: {total_pruned} rules would be pruned")
            else:
                print(f"Total: {total_pruned} rules pruned")
