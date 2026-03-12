#!/usr/bin/env python3
"""
Documentation Gap Scanner for Chagatai (C002: Documentation Self-Tasking)

Scans docs/ directory for:
1. Stale documentation (>7 days since last update)
2. Missing expected documentation files
3. Orphaned or incomplete docs

Outputs prioritized gap list for task creation.
"""

import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict

# Configuration
DOCS_DIR = Path("/Users/kublai/.openclaw/agents/main/docs")
STALE_DAYS = 7
MIN_CHARS = 300  # Minimum chars for a "complete" doc

# Expected documentation (files that should exist)
EXPECTED_DOCS = [
    "architecture.md",
    "state-management-reference.md",
    "reflection-rules-quickref.md",
    "auth-health-preflight.md",
    "ops-behavioral-rules.md",
    "completion-gate.md",
]

def get_file_age_days(filepath: Path) -> int:
    """Return days since file was last modified."""
    if not filepath.exists():
        return 999
    mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
    age = (datetime.now() - mtime).days
    return age

def is_orphaned(filepath: Path) -> bool:
    """Check if file exists but is too short to be useful."""
    if not filepath.exists():
        return False
    return filepath.stat().st_size < MIN_CHARS

def scan_stale_docs() -> List[Dict]:
    """Find docs not updated in STALE_DAYS."""
    gaps = []
    for md_file in DOCS_DIR.glob("*.md"):
        age = get_file_age_days(md_file)
        if age >= STALE_DAYS:
            gaps.append({
                "type": "stale",
                "path": str(md_file.relative_to(DOCS_DIR)),
                "age_days": age,
                "priority": "HIGH" if age > 30 else "MEDIUM",
                "reason": f"Not updated in {age} days"
            })
    return sorted(gaps, key=lambda x: x["age_days"], reverse=True)

def scan_missing_docs() -> List[Dict]:
    """Find expected docs that don't exist."""
    gaps = []
    for expected in EXPECTED_DOCS:
        filepath = DOCS_DIR / expected
        if not filepath.exists():
            gaps.append({
                "type": "missing",
                "path": expected,
                "age_days": 999,
                "priority": "HIGH",
                "reason": "Expected documentation file missing"
            })
    return gaps

def scan_incomplete_docs() -> List[Dict]:
    """Find docs that are too short to be useful."""
    gaps = []
    for md_file in DOCS_DIR.glob("*.md"):
        if is_orphaned(md_file):
            gaps.append({
                "type": "incomplete",
                "path": str(md_file.relative_to(DOCS_DIR)),
                "age_days": get_file_age_days(md_file),
                "priority": "MEDIUM",
                "reason": f"Too short ({md_file.stat().st_size} chars < {MIN_CHARS} minimum)"
            })
    return gaps

def main():
    all_gaps = []
    all_gaps.extend(scan_stale_docs())
    all_gaps.extend(scan_missing_docs())
    all_gaps.extend(scan_incomplete_docs())

    # Sort by priority: HIGH first, then by age
    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    all_gaps.sort(key=lambda x: (priority_order.get(x["priority"], 3), -x["age_days"]))

    # Output JSON for programmatic use
    result = {
        "scan_time": datetime.now().isoformat(),
        "total_gaps": len(all_gaps),
        "gaps_by_type": {
            "stale": len([g for g in all_gaps if g["type"] == "stale"]),
            "missing": len([g for g in all_gaps if g["type"] == "missing"]),
            "incomplete": len([g for g in all_gaps if g["type"] == "incomplete"]),
        },
        "gaps": all_gaps[:10]  # Top 10 for actionable list
    }

    print(json.dumps(result, indent=2))

    # Also output human-readable summary
    if all_gaps:
        print("\n=== TOP PRIORITY GAPS ===", file=__import__('sys').stderr)
        for gap in all_gaps[:5]:
            print(f"  [{gap['priority']}] {gap['path']} - {gap['reason']}", file=__import__('sys').stderr)
    else:
        print("\n=== NO GAPS FOUND ===", file=__import__('sys').stderr)

if __name__ == "__main__":
    main()
