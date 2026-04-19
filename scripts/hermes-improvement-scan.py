#!/usr/bin/env python3
"""
hermes-improvement-scan.py - Scan for recurring patterns in cascade and action logs.

Groups entries by pattern_type, counts occurrences, and outputs the top
patterns within a configurable time window.

Usage:
    python3 hermes-improvement-scan.py
    python3 hermes-improvement-scan.py --window-hours 4
    python3 hermes-improvement-scan.py --json
"""

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kurultai_logging import setup_logging, get_logger

LOGS_DIR = Path.home() / ".openclaw" / "logs"

logger = get_logger("hermes-improvement-scan", agent="hermes")


def read_jsonl_recent(path: Path, since: datetime) -> list[dict]:
    """Read JSONL lines with a timestamp/ts field newer than since."""
    if not path.exists():
        return []
    entries = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            ts_key = "ts" if "ts" in entry else "timestamp"
            raw = entry.get(ts_key, "")
            if not raw:
                continue
            ts = datetime.fromisoformat(raw)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= since:
                entries.append(entry)
        except (json.JSONDecodeError, ValueError):
            continue
    return entries


def group_patterns(entries: list[dict]) -> dict[str, list[dict]]:
    """Group entries by pattern_type (or type as fallback)."""
    groups: dict[str, list[dict]] = {}
    for entry in entries:
        key = entry.get("pattern_type") or entry.get("type") or "UNKNOWN"
        groups.setdefault(key, []).append(entry)
    return groups


def scan(window_hours: int) -> dict:
    """Run the pattern scan across both log sources."""
    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    cascade_entries = read_jsonl_recent(LOGS_DIR / "cascade-detections.jsonl", since)
    action_entries = read_jsonl_recent(LOGS_DIR / "hermes-actions.jsonl", since)

    cascade_groups = group_patterns(cascade_entries)
    action_groups = group_patterns(action_entries)

    # Build summary with counts
    cascade_summary = {
        name: {"count": len(items), "recent": items[-3:]}
        for name, items in sorted(cascade_groups.items(), key=lambda x: -len(x[1]))
    }
    action_summary = {
        name: {"count": len(items), "recent": items[-3:]}
        for name, items in sorted(action_groups.items(), key=lambda x: -len(x[1]))
    }

    # Top patterns across both sources
    all_types = Counter()
    for e in cascade_entries:
        all_types[e.get("type", "UNKNOWN")] += 1
    for e in action_entries:
        all_types[e.get("pattern_type") or e.get("type") or "UNKNOWN"] += 1

    return {
        "scan_at": datetime.now(timezone.utc).isoformat(),
        "window_hours": window_hours,
        "since": since.isoformat(),
        "total_cascade": len(cascade_entries),
        "total_actions": len(action_entries),
        "top_patterns": dict(all_types.most_common(20)),
        "cascade_patterns": cascade_summary,
        "action_patterns": action_summary,
    }


def main():
    parser = argparse.ArgumentParser(description="Scan for recurring patterns in Hermes logs")
    parser.add_argument("--window-hours", type=int, default=2,
                        help="Lookback window in hours (default: 2)")
    parser.add_argument("--json", action="store_true",
                        help="Output full JSON result")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    setup_logging(level=args.log_level, agent_name="hermes-improvement-scan")

    result = scan(args.window_hours)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        # Human-readable summary
        print(f"Pattern scan — last {args.window_hours}h")
        print(f"  Cascade entries: {result['total_cascade']}")
        print(f"  Action entries:  {result['total_actions']}")
        if result["top_patterns"]:
            print("  Top patterns:")
            for pat, count in result["top_patterns"].items():
                print(f"    {pat}: {count}")
        else:
            print("  No patterns found.")

    logger.info("Scan complete: %d cascade, %d action entries in %dh window",
                result["total_cascade"], result["total_actions"], args.window_hours)
    return 0


if __name__ == "__main__":
    sys.exit(main())
