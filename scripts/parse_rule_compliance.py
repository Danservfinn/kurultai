#!/usr/bin/env python3
from __future__ import annotations
"""
parse_rule_compliance.py — Parse reflection outputs for rule compliance and update rule_registry.

Closes the feedback loop: reflections ask agents "did you follow rule X? YES or NO",
agents answer in structured format, but nobody was parsing the answers back into
rule_registry.py's follow_count/violate_count. This script does that.

Also auto-deprecates rules that are consistently violated (>3 evals, <25% follow rate).

Usage:
    python3 parse_rule_compliance.py                  # Parse all agents' latest reflections
    python3 parse_rule_compliance.py --agent mongke   # Parse one agent
    python3 parse_rule_compliance.py --dry-run        # Show what would change without writing
    python3 parse_rule_compliance.py --auto-deprecate  # Also deprecate ineffective rules
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kurultai_paths import AGENTS_DIR, VALID_AGENTS
from rule_registry import load_rules, record_evaluation, deprecate_rule, save_rules

# Thresholds for auto-deprecation
MIN_EVALS_FOR_DEPRECATION = 3
MAX_VIOLATE_RATE_FOR_DEPRECATION = 0.25  # Deprecate if followed < 25% of the time

REFLECTIONS_DIR = Path(__file__).parent.parent / "logs" / "reflections"
STATE_FILE = Path(__file__).parent.parent / "logs" / "rule-compliance-state.json"


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _save_state(state: dict):
    import json as _json
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(_json.dumps(state, indent=2))


def _already_parsed(agent: str, filepath: Path) -> bool:
    """Check if we already parsed this exact file (by path + mtime)."""
    state = _load_state()
    key = f"{agent}:{filepath.name}"
    mtime = str(filepath.stat().st_mtime)
    return state.get(key) == mtime


def _mark_parsed(agent: str, filepath: Path):
    state = _load_state()
    key = f"{agent}:{filepath.name}"
    state[key] = str(filepath.stat().st_mtime)
    _save_state(state)


def find_latest_reflection(agent: str) -> Path | None:
    """Find the most recent reflection file for an agent.

    Compares per-agent hourly files and today's daily memory file by mtime,
    returning whichever was modified most recently. This prevents stale
    per-agent files from shadowing fresh daily memory reflections.
    """
    candidates = []

    # Per-agent reflection files (e.g., mongke-2026-03-06-1502-hourly.md)
    candidates.extend(REFLECTIONS_DIR.glob(f"{agent}-*-hourly.md"))

    # Today's memory file (reflections are appended here by hourly_reflection.sh)
    today = datetime.now().strftime("%Y-%m-%d")
    memory_file = AGENTS_DIR / agent / "memory" / f"{today}.md"
    if memory_file.exists():
        candidates.append(memory_file)

    if not candidates:
        return None

    # Return the most recently modified file
    return max(candidates, key=lambda p: p.stat().st_mtime)


def extract_rule_compliance(content: str) -> list[dict]:
    """Extract rule compliance YES/NO from reflection output.

    Handles four formats:
    1. Table format: | WHEN x THEN y | **YES** — reason |
    2. Checkbox format: - [ ] Rule N: WHEN x THEN y — **YES** or **NO**
    3. List format:  - WHEN x THEN y — **NO** reason
    4. Inline pattern: WHEN x THEN y — **YES**
    """
    results = []

    # Pattern 1: Checkbox format (NEW - matches template added in prepare_reflection_context.py)
    # e.g., "- [ ] Rule 1: WHEN task fails THEN escalate — **YES** or **NO**"
    # Uses exact match for duplicate detection since format is structured
    checkbox_pattern = re.compile(
        r"^[-*]\s*\[[ xX]\]\s*Rule\s+\d+:\s*(.+?WHEN\b.+?THEN\b.+?)\s*[\u2014—-]+\s*\*{0,2}(YES|NO)\*{0,2}\b",
        re.IGNORECASE | re.MULTILINE,
    )
    for m in checkbox_pattern.finditer(content):
        rule_text = m.group(1).strip()
        followed = m.group(2).upper() == "YES"
        # Use exact match for structured format (less false positives than fuzzy)
        if not any(_is_exact_match(rule_text, r["rule_snippet"]) for r in results):
            results.append({"rule_snippet": rule_text, "followed": followed})

    # Pattern 2: Markdown table rows with rule text and YES/NO
    # e.g., "| WHEN research task assigned THEN validate... | **NO** — not enforced |"
    table_pattern = re.compile(
        r"\|\s*(.+?WHEN\b.+?THEN\b.+?)\s*\|\s*\*{0,2}(YES|NO)\*{0,2}\b",
        re.IGNORECASE,
    )
    for m in table_pattern.finditer(content):
        rule_text = m.group(1).strip().rstrip("|").strip()
        followed = m.group(2).upper() == "YES"
        if not any(_fuzzy_match(rule_text, r["rule_snippet"]) for r in results):
            results.append({"rule_snippet": rule_text, "followed": followed})

    # Pattern 3: List items with rule and YES/NO
    # e.g., "- Rule R1: WHEN x THEN y — YES, followed consistently"
    # e.g., "1. WHEN x THEN y — **NO** (reason)"
    list_pattern = re.compile(
        r"(?:^[-*]\s*|^\d+\.\s*)(?:Rule\s+\w+:\s*)?(.+?WHEN\b.+?THEN\b.+?)\s*[\u2014—-]+\s*\*{0,2}(YES|NO)\*{0,2}\b",
        re.IGNORECASE | re.MULTILINE,
    )
    for m in list_pattern.finditer(content):
        rule_text = m.group(1).strip()
        followed = m.group(2).upper() == "YES"
        # Avoid duplicates
        if not any(_fuzzy_match(rule_text, r["rule_snippet"]) for r in results):
            results.append({"rule_snippet": rule_text, "followed": followed})

    # Pattern 4: Section-based (## 5. PREVIOUS RULES COMPLIANCE) with inline YES/NO
    # Catch any remaining WHEN...THEN with YES/NO on the same line
    inline_pattern = re.compile(
        r"(WHEN\b.+?THEN\b[^|]*?)\s*\|\s*\*{0,2}(YES|NO)\*{0,2}\b",
        re.IGNORECASE,
    )
    for m in inline_pattern.finditer(content):
        rule_text = m.group(1).strip()
        followed = m.group(2).upper() == "YES"
        if not any(_fuzzy_match(rule_text, r["rule_snippet"]) for r in results):
            results.append({"rule_snippet": rule_text, "followed": followed})

    return results


def _fuzzy_match(snippet: str, registry_text: str) -> bool:
    """Check if a snippet from a reflection matches a registry rule text.

    Uses normalized word overlap since reflections may abbreviate rules.
    Requires 70% overlap with stricter common-word filtering.
    """
    def normalize(s):
        return set(re.sub(r"[^a-z0-9\s]", "", s.lower()).split())

    words_a = normalize(snippet)
    words_b = normalize(registry_text)
    if not words_a or not words_b:
        return False
    overlap = len(words_a & words_b)
    smaller = min(len(words_a), len(words_b))

    # Require 70% overlap for duplicate detection (stricter than original 50%)
    if overlap / smaller < 0.7:
        return False

    # Expanded common words to prevent generic verb matches
    common_words = {
        "when", "then", "instead", "of", "and", "or", "to", "the", "a", "an",
        "fails", "failed", "check", "task", "agent", "use", "using", "not",
        "for", "with", "from", "into", "by", "on", "in", "at", "is", "are"
    }
    unique_a = words_a - common_words
    unique_b = words_b - common_words

    # Require unique keyword overlap unless one rule has no unique words
    if unique_a and unique_b and not (unique_a & unique_b):
        return False

    return True


def _is_exact_match(snippet: str, registry_text: str) -> bool:
    """Check if two rule texts are exact matches after normalization.

    Used for structured formats like checkbox where fuzzy match is too aggressive.
    """
    def normalize(s):
        return re.sub(r"[^a-z0-9\s]", "", s.lower()).strip()

    return normalize(snippet) == normalize(registry_text)


def match_to_registry(agent: str, compliance: list[dict]) -> list[dict]:
    """Match extracted compliance entries to registry rules by fuzzy text match."""
    data = load_rules(agent)
    active_rules = [r for r in data["rules"] if r.get("status") == "active"]
    matched = []

    for entry in compliance:
        best_match = None
        best_score = 0.0

        for rule in active_rules:
            if _fuzzy_match(entry["rule_snippet"], rule["text"]):
                # Calculate overlap score for ranking
                words_a = set(re.sub(r"[^a-z0-9\s]", "", entry["rule_snippet"].lower()).split())
                words_b = set(re.sub(r"[^a-z0-9\s]", "", rule["text"].lower()).split())
                score = len(words_a & words_b) / max(len(words_a | words_b), 1)
                if score > best_score:
                    best_score = score
                    best_match = rule

        if best_match:
            matched.append({
                "rule_id": best_match["id"],
                "rule_text": best_match["text"],
                "followed": entry["followed"],
                "match_score": round(best_score, 2),
            })

    return matched


def process_agent(agent: str, dry_run: bool = False, auto_deprecate: bool = False) -> dict:
    """Process a single agent's latest reflection for rule compliance."""
    result = {"agent": agent, "file": None, "matched": 0, "updated": 0, "deprecated": 0}

    reflection_file = find_latest_reflection(agent)
    if not reflection_file:
        return result

    result["file"] = str(reflection_file)

    # Skip if already parsed this exact file (prevent double-counting)
    if not dry_run and _already_parsed(agent, reflection_file):
        return result

    content = reflection_file.read_text(encoding="utf-8", errors="replace")

    # Extract compliance from reflection
    compliance = extract_rule_compliance(content)
    if not compliance:
        return result

    # Match to registry
    matches = match_to_registry(agent, compliance)
    result["matched"] = len(matches)

    if dry_run:
        for m in matches:
            status = "FOLLOWED" if m["followed"] else "VIOLATED"
            print(f"  [DRY-RUN] {agent}/{m['rule_id']}: {status} (score={m['match_score']})")
        return result

    # Update registry
    for m in matches:
        if record_evaluation(agent, m["rule_id"], m["followed"]):
            result["updated"] += 1

    # Mark as parsed to prevent double-counting
    _mark_parsed(agent, reflection_file)

    # Auto-deprecate ineffective rules
    if auto_deprecate:
        data = load_rules(agent)
        for rule in data["rules"]:
            if rule.get("status") != "active":
                continue
            follow = rule.get("follow_count", 0)
            violate = rule.get("violate_count", 0)
            total = follow + violate
            if total >= MIN_EVALS_FOR_DEPRECATION:
                follow_rate = follow / total
                if follow_rate < MAX_VIOLATE_RATE_FOR_DEPRECATION:
                    if deprecate_rule(agent, rule["id"],
                                      reason=f"auto: follow rate {follow_rate:.0%} < {MAX_VIOLATE_RATE_FOR_DEPRECATION:.0%} over {total} evals"):
                        result["deprecated"] += 1
                        print(f"  AUTO-DEPRECATED {agent}/{rule['id']}: "
                              f"follow rate {follow_rate:.0%} ({follow}/{total})")

    return result


def main():
    parser = argparse.ArgumentParser(description="Parse reflection rule compliance into registry")
    parser.add_argument("--agent", help="Process single agent")
    parser.add_argument("--dry-run", action="store_true", help="Show matches without writing")
    parser.add_argument("--auto-deprecate", action="store_true",
                        help="Auto-deprecate rules with low follow rate")
    args = parser.parse_args()

    agents = [args.agent] if args.agent else sorted(VALID_AGENTS)
    total_updated = 0
    total_deprecated = 0

    for agent in agents:
        result = process_agent(agent, dry_run=args.dry_run, auto_deprecate=args.auto_deprecate)
        if result["matched"] > 0 or result["file"]:
            status = f"matched={result['matched']} updated={result['updated']}"
            if result["deprecated"]:
                status += f" deprecated={result['deprecated']}"
            print(f"{agent}: {status} (from {result.get('file', 'N/A')})")
            total_updated += result["updated"]
            total_deprecated += result["deprecated"]
        else:
            print(f"{agent}: no reflection data or no rule compliance found")

    print(f"\nTotal: {total_updated} evaluation(s) recorded, {total_deprecated} rule(s) deprecated")


if __name__ == "__main__":
    main()
