#!/usr/bin/env python3
"""
hermes-reflection.py - Prepare daily reflection context pack for Hermes.

Gathers events from the last 24 hours: Neo4j task completions/failures,
cascade detections, and agent health flags. Outputs a JSON context pack.

Usage:
    python3 hermes-reflection.py
    python3 hermes-reflection.py --output-dir /tmp/reflections/
    python3 hermes-reflection.py --hours 12
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
DEFAULT_OUTPUT_DIR = Path.home() / ".openclaw" / "agents" / "hermes" / "workspace" / "reflections"

logger = get_logger("hermes-reflection", agent="hermes")


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


def query_task_counts(since: datetime) -> dict[str, dict[str, int]]:
    """Query Neo4j for completed/failed task counts per agent."""
    try:
        from neo4j_v2_core import TaskStore
        store = TaskStore()
        counts: dict[str, dict[str, int]] = {}
        with store.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.updated_at >= datetime($since)
                  AND t.status IN ['COMPLETED', 'FAILED']
                RETURN t.assigned_to AS agent, t.status AS status, count(*) AS cnt
            """, since=since.isoformat())
            for record in result:
                agent = record["agent"] or "unassigned"
                status = record["status"]
                cnt = record["cnt"]
                counts.setdefault(agent, {"COMPLETED": 0, "FAILED": 0})
                counts[agent][status] = cnt
        store.close()
        return counts
    except Exception as exc:
        logger.warning("Neo4j query failed: %s", exc)
        return {}


def read_health_flags() -> dict:
    """Read agent-health-flags.json."""
    path = LOGS_DIR / "agent-health-flags.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read health flags: %s", exc)
        return {}


def build_context_pack(hours: int) -> dict:
    """Assemble the full reflection context pack."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    cascade_entries = read_jsonl_recent(LOGS_DIR / "cascade-detections.jsonl", since)
    task_counts = query_task_counts(since)
    health_flags = read_health_flags()

    cascade_types = Counter(e.get("type", "UNKNOWN") for e in cascade_entries)
    cascade_severities = Counter(e.get("severity", "UNKNOWN") for e in cascade_entries)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_hours": hours,
        "since": since.isoformat(),
        "task_counts": task_counts,
        "cascade_detections": {
            "total": len(cascade_entries),
            "by_type": dict(cascade_types),
            "by_severity": dict(cascade_severities),
            "entries": cascade_entries[-20:],  # last 20 for context
        },
        "agent_health_flags": health_flags,
    }


def main():
    parser = argparse.ArgumentParser(description="Prepare Hermes daily reflection context pack")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                        help="Directory to write context pack (default: hermes workspace)")
    parser.add_argument("--hours", type=int, default=24,
                        help="Lookback window in hours (default: 24)")
    parser.add_argument("--stdout", action="store_true",
                        help="Write JSON to stdout instead of file")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    setup_logging(level=args.log_level, agent_name="hermes-reflection")

    pack = build_context_pack(args.hours)
    output_json = json.dumps(pack, indent=2, default=str)

    if args.stdout:
        print(output_json)
    else:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"reflection-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        out_path = args.output_dir / filename
        out_path.write_text(output_json + "\n")
        logger.info("Wrote context pack to %s", out_path)
        print(json.dumps({"status": "ok", "path": str(out_path), "entries": pack["cascade_detections"]["total"]}))

    return 0


if __name__ == "__main__":
    sys.exit(main())
