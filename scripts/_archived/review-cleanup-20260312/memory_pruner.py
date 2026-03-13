#!/usr/bin/env python3
"""Memory Pruner — Consolidates old daily memory files into weekly summaries.

Prevents unbounded growth of agent memory directories by:
1. Keeping recent daily files (last 3 days) intact
2. Consolidating older daily files into weekly summary files
3. Preserving key learnings while removing raw telemetry

Run: python3 memory_pruner.py [--dry-run] [--keep-days N]
"""

import os
import re
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

AGENTS_DIR = Path(os.environ.get("AGENTS_DIR", os.path.expanduser("~/.openclaw/agents")))
KEEP_DAYS = 3  # Keep daily files for last N days
DAILY_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")

# Sections to extract as key learnings (case-insensitive partial match)
KEY_SECTIONS = [
    "key learning", "improvement", "proposal", "decision",
    "rule", "fix", "bug", "insight", "pattern",
    "strength", "weakness", "priority"
]

# Sections to discard (raw telemetry, metrics snapshots)
SKIP_SECTIONS = [
    "system metrics", "pipeline health", "task assignment",
    "capability scores", "performance metrics", "chat history",
    "system logs", "system health"
]


def find_daily_files(memory_dir: Path) -> dict:
    """Find all daily memory files grouped by date."""
    files = {}
    for f in memory_dir.iterdir():
        if f.is_file():
            m = DAILY_PATTERN.match(f.name)
            if m:
                try:
                    date = datetime.strptime(m.group(1), "%Y-%m-%d").date()
                    files[date] = f
                except ValueError:
                    continue
    return files


def extract_key_sections(content: str) -> list:
    """Extract key learning sections from a daily file, skip telemetry."""
    sections = []
    current_section = None
    current_lines = []
    is_key = False
    is_skip = False

    for line in content.split("\n"):
        # Detect section headers (## or ###)
        if line.startswith("## ") or line.startswith("### "):
            # Save previous section if it was key
            if current_section and is_key and not is_skip:
                text = "\n".join(current_lines).strip()
                if len(text) > 20:  # Skip near-empty sections
                    sections.append(f"### {current_section}\n{text}")

            current_section = line.lstrip("#").strip()
            current_lines = []
            lower = current_section.lower()
            is_key = any(k in lower for k in KEY_SECTIONS)
            is_skip = any(k in lower for k in SKIP_SECTIONS)
        elif current_section:
            current_lines.append(line)

    # Final section
    if current_section and is_key and not is_skip:
        text = "\n".join(current_lines).strip()
        if len(text) > 20:
            sections.append(f"### {current_section}\n{text}")

    return sections


def get_week_key(date) -> str:
    """Get ISO week key for grouping (e.g., '2026-W10')."""
    iso = date.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def consolidate_week(agent: str, week_key: str, daily_files: dict, dry_run: bool) -> dict:
    """Consolidate a week's daily files into a weekly summary."""
    dates = sorted(daily_files.keys())
    total_lines = 0
    all_sections = []

    for date in dates:
        filepath = daily_files[date]
        content = filepath.read_text(encoding="utf-8", errors="replace")
        total_lines += content.count("\n")
        sections = extract_key_sections(content)
        if sections:
            all_sections.append(f"## {date}\n\n" + "\n\n".join(sections))

    if not all_sections:
        # Even if no key sections, create a minimal summary
        all_sections.append(f"No key learnings extracted from {len(dates)} daily files.")

    summary = f"""# Weekly Memory Summary — {agent} — {week_key}
# Consolidated from {len(dates)} daily files ({dates[0]} to {dates[-1]})
# Original: {total_lines} lines → {sum(len(s.split(chr(10))) for s in all_sections)} lines

{"".join(chr(10) + chr(10) + s for s in all_sections)}
"""

    result = {
        "agent": agent,
        "week": week_key,
        "dates": [str(d) for d in dates],
        "original_lines": total_lines,
        "summary_lines": summary.count("\n"),
        "compression": round(1 - summary.count("\n") / max(total_lines, 1), 2),
    }

    if not dry_run:
        # Determine output directory
        memory_dir = daily_files[dates[0]].parent
        summary_path = memory_dir / f"weekly-{week_key}.md"
        summary_path.write_text(summary, encoding="utf-8")
        result["summary_path"] = str(summary_path)

        # Remove original daily files
        for date in dates:
            daily_files[date].unlink()
            result.setdefault("removed", []).append(str(daily_files[date]))

    return result


def prune_agent(agent_name: str, memory_dir: Path, keep_days: int, dry_run: bool) -> list:
    """Prune one agent's memory directory."""
    if not memory_dir.is_dir():
        return []

    daily_files = find_daily_files(memory_dir)
    if not daily_files:
        return []

    cutoff = datetime.now().date() - timedelta(days=keep_days)
    old_files = {d: f for d, f in daily_files.items() if d < cutoff}

    if not old_files:
        return []

    # Group by ISO week
    weeks = defaultdict(dict)
    for date, filepath in old_files.items():
        week_key = get_week_key(date)
        weeks[week_key][date] = filepath

    results = []
    for week_key, week_files in sorted(weeks.items()):
        result = consolidate_week(agent_name, week_key, week_files, dry_run)
        results.append(result)

    return results


def main():
    dry_run = "--dry-run" in sys.argv
    keep_days = KEEP_DAYS

    # Parse --keep-days N
    for i, arg in enumerate(sys.argv):
        if arg == "--keep-days" and i + 1 < len(sys.argv):
            keep_days = int(sys.argv[i + 1])

    if dry_run:
        print("=== DRY RUN — no files will be modified ===\n")

    all_results = []

    # Process each agent's memory directory
    for agent_dir in sorted(AGENTS_DIR.iterdir()):
        if not agent_dir.is_dir():
            continue
        agent_name = agent_dir.name
        memory_dir = agent_dir / "memory"

        results = prune_agent(agent_name, memory_dir, keep_days, dry_run)
        if results:
            all_results.extend(results)

    # Summary
    if all_results:
        total_original = sum(r["original_lines"] for r in all_results)
        total_summary = sum(r["summary_lines"] for r in all_results)
        total_files = sum(len(r["dates"]) for r in all_results)
        print(f"Pruned {total_files} daily files across {len(all_results)} weeks")
        print(f"Compression: {total_original} → {total_summary} lines ({round(100 * (1 - total_summary / max(total_original, 1)))}% reduction)")
        for r in all_results:
            action = "would consolidate" if dry_run else "consolidated"
            print(f"  {r['agent']}/{r['week']}: {len(r['dates'])} files, {r['original_lines']}→{r['summary_lines']} lines")
    else:
        print(f"No daily files older than {keep_days} days found. Nothing to prune.")

    # Output JSON for automation
    if "--json" in sys.argv:
        print(json.dumps(all_results, indent=2))

    return 0 if all_results or dry_run else 0


if __name__ == "__main__":
    sys.exit(main())
