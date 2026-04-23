#!/usr/bin/env python3
"""
memory_audit.py — Audit agent memory files for health issues.

Checks for:
  1. Cross-agent contamination in Claude project MEMORY.md files
  2. WHEN/THEN rule bloat (>MAX_RULES per agent)
  3. File size bloat (daily logs >SIZE_WARN_KB)
  4. Stale markers (entries tagged STALE/RESOLVED but not removed)

Usage:
    python3 memory_audit.py           # Full audit, human-readable
    python3 memory_audit.py --json    # Machine-readable output
    python3 memory_audit.py --fix     # Auto-fix ALL issues (contamination, bloat, stale entries, old logs)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agents_config import AGENTS

# Thresholds
MAX_RULES = 7
SIZE_WARN_KB = 50  # Daily log files above this are bloated
SIZE_CRIT_KB = 500
INTRADAY_WARN_KB = 15  # Current-day file growing too fast
INTRADAY_MAX_SECTIONS = 4  # Keep only last N reflection sections when compacting
CONTEXT_WARN_KB = 4  # context.md above this gets flagged
CONTEXT_MAX_RECENT_ITEMS = 3  # Keep only last N "Latest Work" items when compacting
DEPRECATED_PRUNE_AGE_HOURS = 48  # Deprecated rules older than this are pruned entirely
CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
AGENTS_DIR = Path.home() / ".openclaw" / "agents"

# Map Claude project directory names to expected agent owners
PROJECT_AGENT_MAP = {
    "-Users-kublai--openclaw-agents-main": "kublai",
    "-Users-kublai--openclaw-agents-main-scripts": "kublai",
    "-Users-kublai--openclaw-agents-kublai": "kublai",
    "-Users-kublai--openclaw-agents-kublai-workspace": "kublai",
    "-Users-kublai--openclaw-agents-temujin": "temujin",
    "-Users-kublai--openclaw-agents-temujin-workspace": "temujin",
    "-Users-kublai--openclaw-agents-mongke": "mongke",
    "-Users-kublai--openclaw-agents-mongke-workspace": "mongke",
    "-Users-kublai--openclaw-agents-chagatai": "chagatai",
    "-Users-kublai--openclaw-agents-jochi": "jochi",
    "-Users-kublai--openclaw-agents-jochi-workspace": "jochi",
    "-Users-kublai--openclaw-agents-ogedei": "ogedei",
    "-Users-kublai--openclaw-agents-ogedei-workspace": "ogedei",
}

# Daily logs older than this many days are archived/deleted by --fix
DAILY_LOG_MAX_AGE_DAYS = 3

# Agent name patterns for contamination detection
AGENT_MARKERS = {
    agent: re.compile(
        rf"\b{agent}\b.*(?:memory|agent|developer|researcher|writer|analyst|ops|squad)",
        re.IGNORECASE,
    )
    for agent in AGENTS
}


def check_contamination(results: list):
    """Check Claude project MEMORY.md files for cross-agent contamination."""
    for proj_dir, expected_owner in PROJECT_AGENT_MAP.items():
        mem_file = CLAUDE_PROJECTS_DIR / proj_dir / "memory" / "MEMORY.md"
        if not mem_file.exists():
            continue

        content = mem_file.read_text(errors="replace")
        first_line = content.split("\n", 1)[0].lower()

        # Check if the header mentions a different agent
        for agent in AGENTS:
            if agent == expected_owner:
                continue
            if agent in first_line:
                results.append({
                    "type": "contamination",
                    "severity": "critical",
                    "file": str(mem_file),
                    "expected_owner": expected_owner,
                    "found_agent": agent,
                    "message": f"MEMORY.md in {proj_dir} belongs to {agent}, expected {expected_owner}",
                })
                break


def count_rules(content: str) -> int:
    """Count WHEN/THEN rules in memory content."""
    # Match lines starting with numbered items containing WHEN...THEN
    pattern = re.compile(r"^\s*\d+\.\s*WHEN\b", re.MULTILINE | re.IGNORECASE)
    return len(pattern.findall(content))


def check_rule_bloat(results: list):
    """Check for excessive WHEN/THEN rules in agent memory files."""
    for agent in AGENTS:
        # Check Claude project MEMORY.md
        for proj_dir, owner in PROJECT_AGENT_MAP.items():
            if owner != agent:
                continue
            mem_file = CLAUDE_PROJECTS_DIR / proj_dir / "memory" / "MEMORY.md"
            if not mem_file.exists():
                continue
            content = mem_file.read_text(errors="replace")
            rule_count = count_rules(content)
            if rule_count > MAX_RULES:
                results.append({
                    "type": "rule_bloat",
                    "severity": "warning",
                    "agent": agent,
                    "file": str(mem_file),
                    "rule_count": rule_count,
                    "max_rules": MAX_RULES,
                    "message": f"{agent} has {rule_count} WHEN/THEN rules (max {MAX_RULES})",
                })

        # Check filesystem MEMORY.md
        fs_mem = AGENTS_DIR / agent / "memory" / "MEMORY.md"
        if fs_mem.exists():
            content = fs_mem.read_text(errors="replace")
            rule_count = count_rules(content)
            if rule_count > MAX_RULES:
                results.append({
                    "type": "rule_bloat",
                    "severity": "warning",
                    "agent": agent,
                    "file": str(fs_mem),
                    "rule_count": rule_count,
                    "max_rules": MAX_RULES,
                    "message": f"{agent} has {rule_count} WHEN/THEN rules in fs memory (max {MAX_RULES})",
                })


def check_size_bloat(results: list):
    """Check for oversized daily memory log files."""
    for agent in AGENTS + ["main"]:
        mem_dir = AGENTS_DIR / agent / "memory"
        if not mem_dir.exists():
            continue
        for f in sorted(mem_dir.glob("*.md")):
            size_kb = f.stat().st_size / 1024
            if size_kb > SIZE_CRIT_KB:
                results.append({
                    "type": "size_bloat",
                    "severity": "critical",
                    "agent": agent,
                    "file": str(f),
                    "size_kb": round(size_kb, 1),
                    "message": f"{f.name} is {size_kb:.0f}KB (critical threshold: {SIZE_CRIT_KB}KB)",
                })
            elif size_kb > SIZE_WARN_KB:
                results.append({
                    "type": "size_bloat",
                    "severity": "warning",
                    "agent": agent,
                    "file": str(f),
                    "size_kb": round(size_kb, 1),
                    "message": f"{f.name} is {size_kb:.0f}KB (warn threshold: {SIZE_WARN_KB}KB)",
                })


def check_intraday_bloat(results: list):
    """Check if today's daily log files are growing too fast."""
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    today_filename = f"{today}.md"

    for agent in AGENTS + ["main"]:
        mem_dir = AGENTS_DIR / agent / "memory"
        today_file = mem_dir / today_filename
        if not today_file.exists():
            continue
        size_kb = today_file.stat().st_size / 1024
        if size_kb > INTRADAY_WARN_KB:
            results.append({
                "type": "intraday_bloat",
                "severity": "warning",
                "agent": agent,
                "file": str(today_file),
                "size_kb": round(size_kb, 1),
                "message": f"{agent} today's log {today_filename} is {size_kb:.1f}KB "
                           f"(intraday threshold: {INTRADAY_WARN_KB}KB)",
            })


def check_rules_json(results: list):
    """Check rules.json files for lifecycle issues: dead rules, count overflow."""
    from datetime import datetime, timedelta
    DEAD_RULE_AGE_HOURS = 24  # Rules active >24h with 0 evaluations are dead

    for agent in AGENTS:
        rules_file = AGENTS_DIR / agent / "memory" / "rules.json"
        if not rules_file.exists():
            continue

        try:
            data = json.loads(rules_file.read_text(errors="replace"))
        except (json.JSONDecodeError, KeyError):
            results.append({
                "type": "rules_json_corrupt",
                "severity": "critical",
                "agent": agent,
                "file": str(rules_file),
                "message": f"{agent} rules.json is corrupt or unreadable",
            })
            continue

        rules = data.get("rules", [])
        max_active = data.get("max_active", MAX_RULES)
        active_rules = [r for r in rules if r.get("status") == "active"]

        # Check count overflow
        if len(active_rules) > max_active:
            results.append({
                "type": "rules_overflow",
                "severity": "warning",
                "agent": agent,
                "file": str(rules_file),
                "active_count": len(active_rules),
                "max_active": max_active,
                "message": f"{agent} rules.json has {len(active_rules)} active rules (max {max_active})",
            })

        # Check for dead rules (active but never evaluated after DEAD_RULE_AGE_HOURS)
        now = datetime.now(timezone.utc)
        for rule in active_rules:
            created_str = rule.get("created_at", "")
            last_eval = rule.get("last_evaluated")
            follow = rule.get("follow_count", 0)
            violate = rule.get("violate_count", 0)

            if last_eval is not None or follow > 0 or violate > 0:
                continue  # Rule has been evaluated at least once

            try:
                created = datetime.fromisoformat(created_str)
                # Make timezone-aware if naive (assume UTC)
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue

            age_hours = (now - created).total_seconds() / 3600
            if age_hours > DEAD_RULE_AGE_HOURS:
                results.append({
                    "type": "dead_rule",
                    "severity": "warning",
                    "agent": agent,
                    "file": str(rules_file),
                    "rule_id": rule.get("id", "?"),
                    "rule_text": rule.get("text", "")[:80],
                    "age_hours": round(age_hours, 1),
                    "message": (
                        f"{agent} rule {rule.get('id','?')} is {age_hours:.0f}h old "
                        f"but never evaluated — candidate for deprecation"
                    ),
                })


def check_duplicate_rules(results: list):
    """Check for semantically duplicate rules in rules.json files."""
    import difflib

    for agent in AGENTS:
        rules_file = AGENTS_DIR / agent / "memory" / "rules.json"
        if not rules_file.exists():
            continue

        try:
            data = json.loads(rules_file.read_text(errors="replace"))
        except (json.JSONDecodeError, KeyError):
            continue

        active_rules = [r for r in data.get("rules", []) if r.get("status") == "active"]
        seen_pairs = set()

        for i, r1 in enumerate(active_rules):
            for j, r2 in enumerate(active_rules):
                if j <= i:
                    continue
                pair_key = (r1.get("id", i), r2.get("id", j))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                # Normalize text for comparison: lowercase, strip whitespace/punctuation
                t1 = re.sub(r"[^a-z0-9\s]", "", r1.get("text", "").lower()).split()
                t2 = re.sub(r"[^a-z0-9\s]", "", r2.get("text", "").lower()).split()

                # Use SequenceMatcher for word-level similarity
                ratio = difflib.SequenceMatcher(None, t1, t2).ratio()
                if ratio >= 0.6:
                    results.append({
                        "type": "duplicate_rule",
                        "severity": "warning",
                        "agent": agent,
                        "file": str(rules_file),
                        "rule_ids": [r1.get("id", "?"), r2.get("id", "?")],
                        "similarity": round(ratio, 2),
                        "message": (
                            f"{agent} rules {r1.get('id','?')} and {r2.get('id','?')} "
                            f"are {ratio:.0%} similar — candidate for dedup"
                        ),
                    })


def check_cross_agent_duplicates(results: list):
    """Check for duplicate rules ACROSS different agents.

    Cross-agent duplicates waste rule slots (max 7 per agent). When two agents
    share the same rule, the non-owner should deprecate it to free a slot.
    """
    import difflib

    # Collect all active rules across agents: [(agent, rule_id, text), ...]
    all_rules = []
    for agent in AGENTS:
        rules_file = AGENTS_DIR / agent / "memory" / "rules.json"
        if not rules_file.exists():
            continue
        try:
            data = json.loads(rules_file.read_text(errors="replace"))
        except (json.JSONDecodeError, KeyError):
            continue
        for r in data.get("rules", []):
            if r.get("status") == "active":
                all_rules.append((agent, r.get("id", "?"), r.get("text", "")))

    # Compare every pair across different agents
    seen_pairs = set()
    for i, (agent1, id1, text1) in enumerate(all_rules):
        for j, (agent2, id2, text2) in enumerate(all_rules):
            if j <= i or agent1 == agent2:
                continue
            pair_key = tuple(sorted([(agent1, id1), (agent2, id2)]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            t1 = re.sub(r"[^a-z0-9\s]", "", text1.lower()).split()
            t2 = re.sub(r"[^a-z0-9\s]", "", text2.lower()).split()
            ratio = difflib.SequenceMatcher(None, t1, t2).ratio()

            if ratio >= 0.7:
                results.append({
                    "type": "cross_agent_duplicate",
                    "severity": "warning",
                    "agents": [agent1, agent2],
                    "rule_ids": [id1, id2],
                    "similarity": round(ratio, 2),
                    "texts": [text1[:80], text2[:80]],
                    "message": (
                        f"Cross-agent duplicate: {agent1}/{id1} and {agent2}/{id2} "
                        f"are {ratio:.0%} similar"
                    ),
                })


def check_pruneable_deprecated(results: list):
    """Check for deprecated rules old enough to prune entirely from rules.json."""
    from datetime import datetime

    for agent in AGENTS:
        rules_file = AGENTS_DIR / agent / "memory" / "rules.json"
        if not rules_file.exists():
            continue

        try:
            data = json.loads(rules_file.read_text(errors="replace"))
        except (json.JSONDecodeError, KeyError):
            continue

        now = datetime.now()
        for rule in data.get("rules", []):
            if rule.get("status") != "deprecated":
                continue

            # Use deprecated_at if available, else fall back to created_at
            ts_str = rule.get("deprecated_at") or rule.get("created_at", "")
            try:
                ts = datetime.fromisoformat(ts_str)
            except (ValueError, TypeError):
                # No parseable timestamp — flag for pruning anyway
                ts = now - __import__("datetime").timedelta(hours=DEPRECATED_PRUNE_AGE_HOURS + 1)

            age_hours = (now - ts).total_seconds() / 3600
            if age_hours >= DEPRECATED_PRUNE_AGE_HOURS:
                results.append({
                    "type": "pruneable_deprecated",
                    "severity": "info",
                    "agent": agent,
                    "file": str(rules_file),
                    "rule_id": rule.get("id", "?"),
                    "rule_text": rule.get("text", "")[:80],
                    "age_hours": round(age_hours, 1),
                    "message": (
                        f"{agent} deprecated rule {rule.get('id','?')} is {age_hours:.0f}h old "
                        f"— ready for pruning"
                    ),
                })


def check_stale_markers(results: list):
    """Check for STALE/RESOLVED entries that should be pruned."""
    stale_re = re.compile(r"\*\*.*?\(STALE\).*?\*\*|\(STALE\)|~~.*?~~", re.IGNORECASE)
    for agent in AGENTS:
        for proj_dir, owner in PROJECT_AGENT_MAP.items():
            if owner != agent:
                continue
            mem_file = CLAUDE_PROJECTS_DIR / proj_dir / "memory" / "MEMORY.md"
            if not mem_file.exists():
                continue
            content = mem_file.read_text(errors="replace")
            stale_count = len(stale_re.findall(content))
            if stale_count > 2:
                results.append({
                    "type": "stale_entries",
                    "severity": "info",
                    "agent": agent,
                    "file": str(mem_file),
                    "stale_count": stale_count,
                    "message": f"{agent} MEMORY.md has {stale_count} stale/struck entries — consider pruning",
                })


def check_context_bloat(results: list):
    """Check for oversized context.md files that slow task execution."""
    for agent in AGENTS:
        ctx_file = AGENTS_DIR / agent / "memory" / "context.md"
        if not ctx_file.exists():
            continue
        size_kb = ctx_file.stat().st_size / 1024
        if size_kb > CONTEXT_WARN_KB:
            results.append({
                "type": "context_bloat",
                "severity": "warning",
                "agent": agent,
                "file": str(ctx_file),
                "size_kb": round(size_kb, 1),
                "message": f"{agent} context.md is {size_kb:.1f}KB "
                           f"(threshold: {CONTEXT_WARN_KB}KB) — loaded into every task execution",
            })


def _parse_md_rule_table(content: str) -> list:
    """Parse a markdown pipe-table of rules into a list of row dicts.

    Handles tables with columns like: ID | WHEN condition | THEN action | Category | Created | Status
    Returns list of dicts with lowercased, underscored keys.
    """
    rows = []
    in_table = False
    header_keys = []

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            if in_table:
                break
            continue
        # Skip separator rows (e.g. |---|---|)
        if re.match(r"^\|[\s\-|]+\|$", stripped):
            in_table = True
            continue

        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not header_keys:
            header_keys = [c.lower().replace(" ", "_") for c in cells]
            in_table = True
            continue

        row = dict(zip(header_keys, cells))
        # Skip placeholder rows
        if all(v in ("_", "", "-") for v in row.values()):
            continue
        rows.append(row)

    return rows


def check_system_rules_registry(results: list):
    """Check system-level when_then_rules.md and agent behavioral rule files for capacity violations.

    Detects:
    - Over-capacity in the system registry (active count > stated max)
    - Over-capacity in per-agent behavioral rule files
    - System rules that are already captured in agent behavioral files (deprecation candidates)
    """
    main_mem = AGENTS_DIR / "main" / "memory"

    # --- System-level registry ---
    registry_path = main_mem / "when_then_rules.md"
    if registry_path.exists():
        content = registry_path.read_text(errors="replace")

        # Parse stated capacity from header: "## Active Rules (N/M capacity...)"
        cap_match = re.search(r"## Active Rules\s*\((\d+)/(\d+)", content)
        if cap_match:
            current = int(cap_match.group(1))
            maximum = int(cap_match.group(2))
            if current > maximum:
                results.append({
                    "type": "registry_overcapacity",
                    "severity": "warning",
                    "file": str(registry_path),
                    "current_count": current,
                    "max_count": maximum,
                    "message": (
                        f"when_then_rules.md: {current} active rules vs max {maximum} "
                        f"({current - maximum} over) — deprecate low-impact rules or move to agent registries"
                    ),
                })

        # Find rules that also appear in agent behavioral rule files → deprecation candidates
        # Collect rule IDs referenced inside all *-behavioral-rules.md
        behavioral_rule_refs: set = set()
        for f in main_mem.glob("*-behavioral-rules.md"):
            beh = f.read_text(errors="replace")
            # Match explicit back-refs like "(R003)" or "### K001 (R009)"
            behavioral_rule_refs.update(re.findall(r"\b(R\d{3})\b", beh))

        # Parse the active rules table
        active_section = re.search(
            r"## Active Rules.*?\n(.*?)(?=\n## |\Z)", content, re.DOTALL
        )
        if active_section and behavioral_rule_refs:
            rows = _parse_md_rule_table(active_section.group(1))
            for row in rows:
                rule_id = row.get("id", "").strip()
                if rule_id in behavioral_rule_refs:
                    results.append({
                        "type": "registry_rule_in_agent_file",
                        "severity": "info",
                        "file": str(registry_path),
                        "rule_id": rule_id,
                        "message": (
                            f"System rule {rule_id} is already captured in an agent behavioral "
                            f"rules file — candidate for system registry deprecation"
                        ),
                    })

    # --- Per-agent behavioral rule files ---
    for f in sorted(main_mem.glob("*-behavioral-rules.md")):
        content = f.read_text(errors="replace")
        cap_match = re.search(r"## Active Rules\s*\((\d+)/(\d+)", content)
        if not cap_match:
            continue
        current = int(cap_match.group(1))
        maximum = int(cap_match.group(2))
        if current > maximum:
            agent_name = f.name.replace("-behavioral-rules.md", "")
            results.append({
                "type": "agent_rules_overcapacity",
                "severity": "warning",
                "agent": agent_name,
                "file": str(f),
                "current_count": current,
                "max_count": maximum,
                "message": (
                    f"{f.name}: {current} active rules vs max {maximum} "
                    f"({current - maximum} over) — prune or consolidate low-priority rules"
                ),
            })


def run_audit() -> list:
    """Run all audit checks and return results."""
    results = []
    check_contamination(results)
    check_rule_bloat(results)
    check_rules_json(results)
    check_duplicate_rules(results)
    check_cross_agent_duplicates(results)
    check_pruneable_deprecated(results)
    check_size_bloat(results)
    check_intraday_bloat(results)
    check_context_bloat(results)
    check_stale_markers(results)
    check_system_rules_registry(results)
    return results


def format_human(results: list) -> str:
    """Format results for human reading."""
    if not results:
        return "Memory audit: ALL CLEAR — no issues found."

    lines = [f"Memory Audit — {len(results)} issue(s) found\n"]

    by_severity = {"critical": [], "warning": [], "info": []}
    for r in results:
        by_severity.get(r["severity"], by_severity["info"]).append(r)

    for sev in ("critical", "warning", "info"):
        items = by_severity[sev]
        if not items:
            continue
        lines.append(f"## {sev.upper()} ({len(items)})")
        for r in items:
            lines.append(f"  [{r['type']}] {r['message']}")
        lines.append("")

    return "\n".join(lines)


def fix_contamination(results: list) -> int:
    """Fix cross-agent contamination by clearing affected files."""
    fixed = 0
    for r in results:
        if r["type"] != "contamination":
            continue
        p = Path(r["file"])
        owner = r["expected_owner"]
        p.write_text(f"# {owner.title()} Memory ({p.parent.parent.name})\n\n"
                     f"(Cleared by memory_audit.py — was contaminated with {r['found_agent']} data)\n")
        print(f"  FIX [contamination]: Cleared {p.name} (was {r['found_agent']}, expected {owner})")
        fixed += 1
    return fixed


def fix_size_bloat(results: list) -> int:
    """Fix size bloat by deleting old daily log files."""
    from datetime import datetime, timedelta
    cutoff = datetime.now() - timedelta(days=DAILY_LOG_MAX_AGE_DAYS)
    fixed = 0
    seen = set()

    for r in results:
        if r["type"] != "size_bloat":
            continue
        p = Path(r["file"])
        if str(p) in seen:
            continue
        seen.add(str(p))

        # Only delete dated daily logs (YYYY-MM-DD.md), never MEMORY.md or context.md
        if not re.match(r"\d{4}-\d{2}-\d{2}\.md$", p.name):
            continue

        # Parse date from filename
        try:
            file_date = datetime.strptime(p.stem, "%Y-%m-%d")
        except ValueError:
            continue

        if file_date < cutoff:
            size_kb = p.stat().st_size / 1024
            p.unlink()
            print(f"  FIX [size_bloat]: Deleted {p} ({size_kb:.0f}KB, date {p.stem})")
            fixed += 1
        else:
            print(f"  SKIP [size_bloat]: {p.name} is recent (within {DAILY_LOG_MAX_AGE_DAYS} days)")

    return fixed


def fix_stale_entries(results: list) -> int:
    """Fix stale entries by removing lines marked (STALE) or ~~struck~~."""
    stale_re = re.compile(r"^.*(?:\(STALE\)|~~.+~~.*(?:RESOLVED|resolved)).*$", re.MULTILINE)
    fixed = 0

    for r in results:
        if r["type"] != "stale_entries":
            continue
        p = Path(r["file"])
        content = p.read_text(errors="replace")
        cleaned = stale_re.sub("", content)
        # Remove resulting blank lines (max 2 consecutive)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        if cleaned != content:
            p.write_text(cleaned)
            removed = len(content.split("\n")) - len(cleaned.split("\n"))
            print(f"  FIX [stale_entries]: Pruned {removed} stale lines from {p.name}")
            fixed += 1

    return fixed


def fix_intraday_bloat(results: list) -> int:
    """Compact today's bloated daily logs by keeping only the last N sections."""
    fixed = 0
    for r in results:
        if r["type"] != "intraday_bloat":
            continue
        p = Path(r["file"])
        content = p.read_text(errors="replace")

        # Split on section dividers (--- on its own line)
        sections = re.split(r"\n---\n", content)
        if len(sections) <= INTRADAY_MAX_SECTIONS:
            continue

        # Keep a compact header + the last N sections
        kept = sections[-INTRADAY_MAX_SECTIONS:]
        compacted = (
            f"# Daily Log (compacted by memory_audit.py — "
            f"{len(sections) - INTRADAY_MAX_SECTIONS} older sections removed)\n\n---\n"
            + "\n---\n".join(kept)
        )

        original_kb = len(content) / 1024
        new_kb = len(compacted) / 1024
        p.write_text(compacted)
        print(f"  FIX [intraday_bloat]: Compacted {p.name} for {r.get('agent','?')} "
              f"({original_kb:.1f}KB -> {new_kb:.1f}KB, kept last {INTRADAY_MAX_SECTIONS} sections)")
        fixed += 1
    return fixed


def _compact_section_items(section: str, max_items: int) -> tuple[str, int]:
    """Compact a section by keeping only the last max_items entries.

    Returns (compacted_text, trimmed_count). Entries start with '- **'.
    """
    lines = section.split("\n")
    header_lines = []
    items = []  # each item is a list of lines (item + continuation)
    current_item = []

    for line in lines:
        if re.match(r"^- \*\*", line):
            if current_item:
                items.append(current_item)
            current_item = [line]
        elif current_item:
            current_item.append(line)
        else:
            header_lines.append(line)

    if current_item:
        items.append(current_item)

    # Keep only the most recent items
    kept_items = items[:max_items]
    trimmed = len(items) - len(kept_items)

    rebuilt = "\n".join(header_lines)
    if trimmed > 0:
        rebuilt += f"\n*(compacted: {trimmed} older entries removed by memory_audit.py)*\n"
    for item in kept_items:
        rebuilt += "\n".join(item) + "\n"

    return rebuilt, trimmed


# Max entries to keep in "Current Task" section (typically longer entries)
CURRENT_TASK_MAX_ITEMS = 3


def fix_context_bloat(results: list) -> int:
    """Compact oversized context.md by trimming old work history entries.

    Preserves: header (role/model/capabilities), Notes sections.
    Trims: Current Task / Latest Work / Recent Work to only recent entries.
    Also deduplicates repeated section headers (e.g. two '## Latest Work').
    """
    fixed = 0
    for r in results:
        if r["type"] != "context_bloat":
            continue
        p = Path(r["file"])
        content = p.read_text(errors="replace")
        original_kb = len(content) / 1024

        # Split into sections by ## headers
        sections = re.split(r"(?=^## )", content, flags=re.MULTILINE)

        new_sections = []
        seen_headers = set()
        for section in sections:
            header_match = re.match(r"^## (Latest Work|Recent Work|Current Task)\b", section)
            if header_match:
                header_name = header_match.group(1)
                # Skip duplicate section headers (keep only the first occurrence)
                if header_name in seen_headers:
                    continue
                seen_headers.add(header_name)

                # Current Task keeps fewer items (they tend to be longer)
                if header_name == "Current Task":
                    max_items = CURRENT_TASK_MAX_ITEMS
                else:
                    max_items = CONTEXT_MAX_RECENT_ITEMS

                compacted_section, _ = _compact_section_items(section, max_items)
                new_sections.append(compacted_section)
            else:
                new_sections.append(section)

        compacted = "".join(new_sections)
        # Clean up excessive blank lines
        compacted = re.sub(r"\n{3,}", "\n\n", compacted)

        if len(compacted) < len(content):
            p.write_text(compacted)
            new_kb = len(compacted) / 1024
            print(f"  FIX [context_bloat]: Compacted {r.get('agent','?')} context.md "
                  f"({original_kb:.1f}KB -> {new_kb:.1f}KB)")
            fixed += 1

    return fixed


def fix_dead_rules(results: list) -> int:
    """Deprecate rules that have been active but never evaluated after threshold."""
    from datetime import datetime
    fixed = 0
    # Group dead rules by file to batch writes
    by_file = {}
    for r in results:
        if r["type"] != "dead_rule":
            continue
        by_file.setdefault(r["file"], []).append(r["rule_id"])

    for filepath, rule_ids in by_file.items():
        p = Path(filepath)
        try:
            data = json.loads(p.read_text(errors="replace"))
        except (json.JSONDecodeError, KeyError):
            continue

        changed = False
        for rule in data.get("rules", []):
            if rule.get("id") in rule_ids and rule.get("status") == "active":
                rule["status"] = "deprecated"
                rule["deprecated_reason"] = (
                    f"auto-deprecated by memory_audit: never evaluated after "
                    f"{rule.get('created_at', 'unknown')} (0 follow, 0 violate)"
                )
                changed = True
                print(f"  FIX [dead_rule]: Deprecated {rule['id']} in {p.name} "
                      f"({rule.get('text', '')[:60]}...)")
                fixed += 1

        if changed:
            data["last_updated"] = datetime.now().isoformat()
            p.write_text(json.dumps(data, indent=2) + "\n")

    return fixed


def fix_duplicate_rules(results: list) -> int:
    """Deprecate the lower-scoring rule in each duplicate pair."""
    from datetime import datetime
    fixed = 0
    # Group by file to batch writes
    by_file = {}
    for r in results:
        if r["type"] != "duplicate_rule":
            continue
        by_file.setdefault(r["file"], []).append(r["rule_ids"])

    for filepath, pairs in by_file.items():
        p = Path(filepath)
        try:
            data = json.loads(p.read_text(errors="replace"))
        except (json.JSONDecodeError, KeyError):
            continue

        rules_by_id = {r.get("id"): r for r in data.get("rules", [])}
        changed = False
        deprecated_ids = set()

        for id1, id2 in pairs:
            r1 = rules_by_id.get(id1)
            r2 = rules_by_id.get(id2)
            if not r1 or not r2:
                continue
            if r1.get("status") != "active" or r2.get("status") != "active":
                continue
            if id1 in deprecated_ids or id2 in deprecated_ids:
                continue

            # Keep the rule with more evaluations; break ties by keeping the newer one
            score1 = r1.get("follow_count", 0) + r1.get("violate_count", 0)
            score2 = r2.get("follow_count", 0) + r2.get("violate_count", 0)
            if score1 > score2:
                loser = r2
            elif score2 > score1:
                loser = r1
            else:
                # Same score — deprecate the older one
                loser = r1 if r1.get("created_at", "") <= r2.get("created_at", "") else r2

            loser["status"] = "deprecated"
            loser["deprecated_reason"] = (
                f"auto-deprecated by memory_audit: duplicate of "
                f"{id1 if loser is r2 else id2}"
            )
            deprecated_ids.add(loser.get("id"))
            changed = True
            print(f"  FIX [duplicate_rule]: Deprecated {loser['id']} in {p.name} "
                  f"(duplicate of {id1 if loser is r2 else id2})")
            fixed += 1

        if changed:
            data["last_updated"] = datetime.now().isoformat()
            p.write_text(json.dumps(data, indent=2) + "\n")

    return fixed


def fix_cross_agent_duplicates(results: list) -> int:
    """Deprecate the lower-priority agent's rule in cross-agent duplicate pairs.

    Priority order (higher keeps the rule): kublai > temujin > ogedei > jochi > mongke > chagatai.
    If both have evaluations, keep the one with more follow_count.
    """
    from datetime import datetime

    # Agent priority for rule ownership (router/lead keeps rules by default)
    AGENT_PRIORITY = {"kublai": 6, "temujin": 5, "ogedei": 4, "jochi": 3, "mongke": 2, "chagatai": 1}

    fixed = 0
    # Cache loaded rules data per agent to batch writes
    agent_data_cache = {}

    for r in results:
        if r["type"] != "cross_agent_duplicate":
            continue

        agent1, agent2 = r["agents"]
        id1, id2 = r["rule_ids"]

        # Load rules data for both agents
        for agent in (agent1, agent2):
            if agent not in agent_data_cache:
                rules_file = AGENTS_DIR / agent / "memory" / "rules.json"
                try:
                    agent_data_cache[agent] = json.loads(rules_file.read_text(errors="replace"))
                except (json.JSONDecodeError, IOError):
                    agent_data_cache[agent] = None

        d1, d2 = agent_data_cache.get(agent1), agent_data_cache.get(agent2)
        if not d1 or not d2:
            continue

        rule1 = next((x for x in d1.get("rules", []) if x.get("id") == id1 and x.get("status") == "active"), None)
        rule2 = next((x for x in d2.get("rules", []) if x.get("id") == id2 and x.get("status") == "active"), None)
        if not rule1 or not rule2:
            continue

        # Decide which to deprecate: prefer keeping the one with more follows
        f1 = rule1.get("follow_count", 0)
        f2 = rule2.get("follow_count", 0)
        if f1 != f2:
            loser_agent, loser_rule = (agent2, rule2) if f1 > f2 else (agent1, rule1)
            winner_agent = agent1 if loser_agent == agent2 else agent2
        else:
            # Tie: use agent priority
            if AGENT_PRIORITY.get(agent1, 0) >= AGENT_PRIORITY.get(agent2, 0):
                loser_agent, loser_rule, winner_agent = agent2, rule2, agent1
            else:
                loser_agent, loser_rule, winner_agent = agent1, rule1, agent2

        loser_rule["status"] = "deprecated"
        loser_rule["deprecated_reason"] = (
            f"auto-deprecated by memory_audit: cross-agent duplicate of "
            f"{winner_agent}/{id1 if loser_agent == agent2 else id2}"
        )
        loser_rule["deprecated_at"] = datetime.now().isoformat()
        print(f"  FIX [cross_agent_dup]: Deprecated {loser_agent}/{loser_rule.get('id','?')} "
              f"(duplicate of {winner_agent}'s rule)")
        fixed += 1

    # Write back all modified agent data
    for agent, data in agent_data_cache.items():
        if data:
            rules_file = AGENTS_DIR / agent / "memory" / "rules.json"
            data["last_updated"] = datetime.now().isoformat()
            rules_file.write_text(json.dumps(data, indent=2) + "\n")

    return fixed


def fix_pruneable_deprecated(results: list) -> int:
    """Remove deprecated rules older than DEPRECATED_PRUNE_AGE_HOURS from rules.json entirely."""
    from datetime import datetime
    fixed = 0
    # Group by file to batch writes
    by_file = {}
    for r in results:
        if r["type"] != "pruneable_deprecated":
            continue
        by_file.setdefault(r["file"], []).append(r["rule_id"])

    for filepath, rule_ids in by_file.items():
        p = Path(filepath)
        try:
            data = json.loads(p.read_text(errors="replace"))
        except (json.JSONDecodeError, KeyError):
            continue

        original_count = len(data.get("rules", []))
        data["rules"] = [
            r for r in data.get("rules", [])
            if not (r.get("id") in rule_ids and r.get("status") == "deprecated")
        ]
        pruned = original_count - len(data["rules"])

        if pruned > 0:
            data["last_updated"] = datetime.now().isoformat()
            data["last_pruned"] = datetime.now().isoformat()
            p.write_text(json.dumps(data, indent=2) + "\n")
            agent = p.parent.parent.name
            print(f"  FIX [prune_deprecated]: Removed {pruned} deprecated rule(s) "
                  f"from {agent}/rules.json (IDs: {', '.join(rule_ids)})")
            fixed += pruned

    return fixed


def fix_old_daily_logs() -> int:
    """Proactively delete daily logs older than DAILY_LOG_MAX_AGE_DAYS across all agents."""
    from datetime import datetime, timedelta
    cutoff = datetime.now() - timedelta(days=DAILY_LOG_MAX_AGE_DAYS)
    fixed = 0

    for agent_dir in sorted(AGENTS_DIR.iterdir()):
        mem_dir = agent_dir / "memory"
        if not mem_dir.is_dir():
            continue
        for f in sorted(mem_dir.glob("????-??-??.md")):
            try:
                file_date = datetime.strptime(f.stem, "%Y-%m-%d")
            except ValueError:
                continue
            if file_date < cutoff:
                size_kb = f.stat().st_size / 1024
                f.unlink()
                print(f"  FIX [old_log]: Deleted {f} ({size_kb:.0f}KB)")
                fixed += 1

    # Also check nested misplaced directories
    nested = AGENTS_DIR / "main" / ".openclaw"
    if nested.exists():
        import shutil
        size = sum(f.stat().st_size for f in nested.rglob("*") if f.is_file()) / 1024
        shutil.rmtree(nested)
        print(f"  FIX [misplaced]: Removed nested {nested} ({size:.0f}KB)")
        fixed += 1

    # Check legacy memory/memory/ dir
    legacy = AGENTS_DIR.parent / "memory" / "memory"
    if legacy.exists():
        for f in sorted(legacy.glob("????-??-??.md")):
            try:
                file_date = datetime.strptime(f.stem, "%Y-%m-%d")
            except ValueError:
                continue
            if file_date < cutoff:
                size_kb = f.stat().st_size / 1024
                f.unlink()
                print(f"  FIX [legacy_log]: Deleted {f} ({size_kb:.0f}KB)")
                fixed += 1

    return fixed


def sync_rules_from_memory() -> int:
    """Sync WHEN/THEN rules from daily memory files into rules.json registries.

    Runs seed_from_memory() for all agents so that rules generated during
    reflections (written to daily .md files) are persisted in rules.json
    before those daily files are rotated out (3-day retention).

    Must run BEFORE fix_dead_rules() to avoid immediately deprecating
    freshly synced rules.
    """
    from rule_registry import seed_from_memory

    synced = 0
    for agent in AGENTS:
        count = seed_from_memory(agent)
        if count > 0:
            print(f"  FIX [rule_sync]: Synced {count} new rule(s) from memory files for {agent}")
            synced += count
    return synced


def main():
    parser = argparse.ArgumentParser(description="Audit agent memory files")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--fix", action="store_true", help="Auto-fix all detected issues")
    args = parser.parse_args()

    results = run_audit()

    if args.fix:
        print("--- Applying fixes ---")
        total_fixed = 0
        total_fixed += fix_contamination(results)
        # Sync rules from daily memory files BEFORE dead-rule check
        total_fixed += sync_rules_from_memory()
        total_fixed += fix_dead_rules(results)
        total_fixed += fix_duplicate_rules(results)
        total_fixed += fix_cross_agent_duplicates(results)
        total_fixed += fix_pruneable_deprecated(results)
        total_fixed += fix_size_bloat(results)
        total_fixed += fix_intraday_bloat(results)
        total_fixed += fix_context_bloat(results)
        total_fixed += fix_stale_entries(results)
        total_fixed += fix_old_daily_logs()
        print(f"--- Fixed {total_fixed} issue(s) ---\n")

        # Re-run audit to show remaining issues
        results = run_audit()

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(format_human(results))

    # Exit code: 1 if critical issues, 0 otherwise
    has_critical = any(r["severity"] == "critical" for r in results)
    sys.exit(1 if has_critical else 0)


if __name__ == "__main__":
    main()
