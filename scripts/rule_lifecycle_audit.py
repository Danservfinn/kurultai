#!/usr/bin/env python3
"""
Rule Lifecycle Auditor for Kurultai Memory System

Analyzes WHEN/THEN behavioral rules across all agent memories:
- Extracts rules from daily memory files and rules.json
- Detects duplicates, contradictions, and stale rules
- Reports on rule health and lifecycle status

Author: jochi (Analyst)
Created: 2026-03-09
"""

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Set, Tuple


# Configuration
AGENTS_DIR = Path("/Users/kublai/.openclaw/agents")
MAX_ACTIVE_RULES = 7
RULE_STALE_DAYS = 14
SIMILARITY_THRESHOLD = 0.7  # For near-duplicate detection


@dataclass
class Rule:
    """A WHEN/THEN behavioral rule."""
    id: str
    agent: str
    when: str
    then: str
    source: str  # "daily_file" or "rules.json"
    created: str = ""
    file_path: str = ""
    line_number: int = 0

    def __hash__(self):
        return hash((self.agent, self.when.lower(), self.then.lower()))

    def __eq__(self, other):
        if not isinstance(other, Rule):
            return False
        return (
            self.agent == other.agent
            and self.when.lower() == other.when.lower()
            and self.then.lower() == other.then.lower()
        )

    def normalized(self) -> str:
        """Return normalized form for comparison."""
        return f"WHEN {self.when.lower()} THEN {self.then.lower()}"

    def triggers_match(self, other: 'Rule') -> bool:
        """Check if two rules have the same WHEN trigger."""
        w1 = re.sub(r'\s+', ' ', self.when.lower().strip())
        w2 = re.sub(r'\s+', ' ', other.when.lower().strip())
        return w1 == w2

    def contradicts(self, other: 'Rule') -> bool:
        """Detect if two rules have same trigger but different actions."""
        if not self.triggers_match(other):
            return False
        t1 = re.sub(r'\s+', ' ', self.then.lower().strip())
        t2 = re.sub(r'\s+', ' ', other.then.lower().strip())
        # Simple check: if actions share <50% words, likely contradictory
        words1 = set(t1.split())
        words2 = set(t2.split())
        if not words1 or not words2:
            return False
        intersection = words1 & words2
        union = words1 | words2
        similarity = len(intersection) / len(union) if union else 0
        return similarity < 0.5


class RuleExtractor:
    """Extracts rules from agent memory files."""

    WHEN_THEN_PATTERN = re.compile(
        r'\bWHEN\b.+?\bTHEN\b(?:\s+\bINSTEAD OF\b.+?)?(?=\n\n|\n\d+[\.\)]|$|\n\*|\n#)',
        re.IGNORECASE | re.DOTALL
    )

    def __init__(self, agents_dir: Path):
        self.agents_dir = agents_dir

    def extract_from_daily_file(self, file_path: Path, agent: str) -> List[Rule]:
        """Extract rules from a daily memory file."""
        if not file_path.exists():
            return []

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []

        rules = []
        lines = content.split('\n')

        # Scan every line for WHEN/THEN patterns
        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            # Skip headers and empty lines
            if not stripped or stripped.startswith('#'):
                continue

            # Look for WHEN/THEN pattern anywhere in line
            if re.search(r'\bWHEN\b.+?\bTHEN\b', stripped, re.IGNORECASE):
                # Remove leading numbers/bullets
                cleaned = re.sub(r'^[\d\-\*\.]+\s*', '', stripped)
                # Remove parenthetical word counts at end
                cleaned = re.sub(r'\s*\(\d+\s*words\)\s*$', '', cleaned)
                # Remove checkbox markers
                cleaned = re.sub(r'^-\s*\[\s*[xX]?\s*\]\s*', '', cleaned)

                parsed = self._parse_rule_text(cleaned, agent, str(file_path), i)
                if parsed:
                    rules.append(parsed)

        return rules

    def extract_from_rules_json(self, file_path: Path, agent: str) -> List[Rule]:
        """Extract rules from structured rules.json file."""
        if not file_path.exists():
            return []

        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception:
            return []

        rules = []
        rule_list = data.get("rules", data.get("rules", []))

        for i, r in enumerate(rule_list):
            if isinstance(r, dict):
                when = r.get("when", r.get("condition", ""))
                then = r.get("then", r.get("action", ""))
                if when and then:
                    rules.append(Rule(
                        id=r.get("id", f"rule-{i}"),
                        agent=agent,
                        when=when,
                        then=then,
                        source="rules.json",
                        created=r.get("created", ""),
                        file_path=str(file_path)
                    ))

        return rules

    def _parse_rule_text(self, text: str, agent: str, file_path: str, line_num: int) -> Rule | None:
        """Parse rule text into WHEN/THEN components."""
        # Remove markdown formatting
        cleaned = re.sub(r'^[\*\-\d\.\)]+\s*', '', text)
        cleaned = re.sub(r'\*\*([^*]+)\*\*', r'\1', cleaned)
        cleaned = cleaned.strip()

        # Extract WHEN clause
        when_match = re.search(r'\bWHEN\b(.+?)\bTHEN\b', cleaned, re.IGNORECASE)
        if not when_match:
            return None

        when_part = when_match.group(1).strip()
        remainder = cleaned[when_match.end():].strip()

        # Extract THEN clause (may include INSTEAD OF)
        instead_match = re.search(r'\bINSTEAD OF\b(.+)$', remainder, re.IGNORECASE)
        if instead_match:
            then_part = remainder[:instead_match.start()].strip()
            then_part += f" INSTEAD OF {instead_match.group(1).strip()}"
        else:
            then_part = remainder

        if len(when_part) < 5 or len(then_part) < 5:
            return None

        return Rule(
            id=f"{agent}-{line_num}",
            agent=agent,
            when=when_part,
            then=then_part,
            source="daily_file",
            file_path=file_path,
            line_number=line_num
        )

    def get_all_rules(self) -> List[Rule]:
        """Extract all rules from all agent memories."""
        all_rules = []
        agents = [d.name for d in self.agents_dir.iterdir()
                  if d.is_dir() and not d.name.startswith('.')]

        for agent in agents:
            memory_dir = self.agents_dir / agent / "memory"
            if not memory_dir.exists():
                continue

            # Extract from rules.json
            rules_json = memory_dir / "rules.json"
            all_rules.extend(self.extract_from_rules_json(rules_json, agent))

            # Extract from latest daily file
            daily_files = sorted(memory_dir.glob("2026-*.md"), reverse=True)
            if daily_files:
                all_rules.extend(self.extract_from_daily_file(daily_files[0], agent))

        return all_rules


class RuleAnalyzer:
    """Analyzes rules for issues and patterns."""

    def __init__(self, rules: List[Rule]):
        self.rules = rules

    def find_duplicates(self) -> List[Tuple[Rule, List[Rule]]]:
        """Find exact duplicate rules (same rule in different files)."""
        seen = {}
        duplicates = []

        for rule in self.rules:
            # Key includes both rule content AND source file to avoid false positives
            key = (rule.normalized(), rule.file_path)
            if key in seen:
                seen[key].append(rule)
            else:
                seen[key] = [rule]

        # Now check for duplicates across different files
        by_content = defaultdict(list)
        for (content, _), rules_list in seen.items():
            by_content[content].extend(rules_list)

        for content, rules_list in by_content.items():
            if len(rules_list) > 1:
                # Check if they're from different files
                unique_files = set(r.file_path for r in rules_list)
                if len(unique_files) > 1:
                    duplicates.append((rules_list[0], rules_list[1:]))

        return duplicates

    def find_contradictions(self) -> List[Tuple[Rule, Rule]]:
        """Find rules with same trigger but different actions."""
        by_trigger = defaultdict(list)
        for rule in self.rules:
            trigger = re.sub(r'\s+', ' ', rule.when.lower().strip())
            by_trigger[trigger].append(rule)

        contradictions = []
        for trigger, rules in by_trigger.items():
            if len(rules) > 1:
                # Check each pair for contradiction
                for i, r1 in enumerate(rules):
                    for r2 in rules[i+1:]:
                        if r1.contradicts(r2):
                            contradictions.append((r1, r2))

        return contradictions

    def find_stale_rules(self, days: int = RULE_STALE_DAYS) -> List[Rule]:
        """Find rules older than threshold (from daily files only)."""
        cutoff = datetime.now() - timedelta(days=days)
        stale = []

        for rule in self.rules:
            if rule.source == "daily_file":
                # Try to parse date from file path
                match = re.search(r'2026-\d{2}-\d{2}', rule.file_path)
                if match:
                    try:
                        rule_date = datetime.fromisoformat(match.group(0))
                        if rule_date < cutoff:
                            stale.append(rule)
                    except ValueError:
                        pass

        return stale

    def analyze_by_agent(self) -> Dict[str, dict]:
        """Generate per-agent rule statistics."""
        by_agent = defaultdict(list)
        for rule in self.rules:
            by_agent[rule.agent].append(rule)

        report = {}
        for agent, rules in by_agent.items():
            report[agent] = {
                "total": len(rules),
                "from_json": sum(1 for r in rules if r.source == "rules.json"),
                "from_daily": sum(1 for r in rules if r.source == "daily_file"),
                "avg_length": sum(len(r.when) + len(r.then) for r in rules) // max(len(rules), 1),
                "exceeds_limit": len(rules) > MAX_ACTIVE_RULES
            }

        return report


def format_report(rules: List[Rule], analyzer: RuleAnalyzer) -> str:
    """Generate human-readable audit report."""
    lines = [
        "# Rule Lifecycle Audit Report",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"## Summary",
        f"- Total rules found: {len(rules)}",
        f"- Agents scanned: {len(set(r.agent for r in rules))}",
        "",
    ]

    # Duplicates
    duplicates = analyzer.find_duplicates()
    if duplicates:
        lines.extend([
            f"## ⚠️ DUPLICATES FOUND ({len(duplicates)} groups)",
            ""
        ])
        for primary, dups in duplicates[:5]:  # Limit output
            lines.append(f"### {primary.agent}: {primary.when[:50]}...")
            lines.append(f"Primary: {primary.file_path}")
            for dup in dups:
                lines.append(f"Duplicate: {dup.file_path}")
            lines.append("")

    # Contradictions
    contradictions = analyzer.find_contradictions()
    if contradictions:
        lines.extend([
            f"## ⚠️ CONTRADICTIONS FOUND ({len(contradictions)} pairs)",
            ""
        ])
        for r1, r2 in contradictions[:5]:
            lines.append(f"### Trigger: {r1.when[:60]}...")
            lines.append(f"- {r1.agent}: {r1.then[:60]}...")
            lines.append(f"- {r2.agent}: {r2.then[:60]}...")
            lines.append("")

    # Per-agent breakdown
    lines.append("## Per-Agent Rule Counts")
    by_agent = analyzer.analyze_by_agent()
    for agent, stats in sorted(by_agent.items()):
        status = "⚠️ OVER LIMIT" if stats["exceeds_limit"] else "✓"
        lines.append(
            f"- **{agent}**: {stats['total']} rules "
            f"({stats['from_json']} JSON, {stats['from_daily']} daily) "
            f"{status}"
        )

    lines.extend([
        "",
        "## Recommendations",
        "1. Consolidate duplicate rules into rules.json",
        "2. Resolve contradictions by choosing one action",
        "3. Prune stale rules older than 14 days",
        "4. Keep rules under MAX_ACTIVE_RULES limit",
    ])

    return "\n".join(lines)


def main():
    """Run the rule lifecycle audit."""
    print("🔍 Rule Lifecycle Auditor")
    print("=" * 50)

    extractor = RuleExtractor(AGENTS_DIR)
    rules = extractor.get_all_rules()

    analyzer = RuleAnalyzer(rules)
    report = format_report(rules, analyzer)

    print(report)

    # Also save to logs
    log_path = AGENTS_DIR / "main" / "logs" / f"rule-audit-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
    log_path.parent.mkdir(exist_ok=True)
    log_path.write_text(report)
    print(f"\n📝 Report saved to: {log_path}")

    # Exit with non-zero if issues found
    duplicates = len(analyzer.find_duplicates())
    contradictions = len(analyzer.find_contradictions())
    over_limit = sum(1 for s in analyzer.analyze_by_agent().values() if s.get("exceeds_limit"))

    if duplicates + contradictions + over_limit > 0:
        print(f"\n⚠️ Found {duplicates} duplicate groups, {contradictions} contradictions, {over_limit} agents over limit")
        return 1
    return 0


if __name__ == "__main__":
    exit(main())
