#!/usr/bin/env python3
"""
neo4j_v2_ledger_compat.py — Drop-in read_ledger() replacement using Neo4j.

Provides the same interface as kurultai_ledger.read_ledger() but reads from
Neo4j Task/FailureReport nodes instead of the JSONL file.

This allows ~30 scripts that `from kurultai_ledger import read_ledger` to be
migrated incrementally by changing their import to:
    from neo4j_v2_ledger_compat import read_ledger

The return format matches the JSONL schema:
    [{"event": "COMPLETED", "ts": "...", "task_id": "...", "agent": "...", ...}, ...]

Usage:
    from neo4j_v2_ledger_compat import read_ledger
    entries = read_ledger(hours=24)
"""

import os
import sys
import logging
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_v2_core import TaskStore

logger = logging.getLogger(__name__)

# Map Neo4j task statuses to ledger event types
_STATUS_TO_EVENT = {
    "PENDING": "QUEUED",
    "WORKING": "EXECUTING",
    "COMPLETED": "COMPLETED",
    "FAILED": "FAILED",
}


def read_ledger(hours: int = None, valid_only: bool = False,
                store: TaskStore = None) -> list[dict]:
    """Read task events from Neo4j in JSONL-compatible format.

    Args:
        hours: Limit to events within the last N hours (None = all)
        valid_only: If True, only return core lifecycle events

    Returns:
        List of dicts matching the JSONL ledger schema.
    """
    _store = store or TaskStore()
    try:
        entries = []
        with _store.driver.session() as session:
            # Build time filter
            time_filter = ""
            params = {}
            if hours:
                time_filter = "WHERE t.created_at > datetime() - duration({hours: $hours})"
                params["hours"] = hours

            # Get all tasks with their events
            result = session.run(f"""
                MATCH (t:Task)
                {time_filter}
                OPTIONAL MATCH (t)-[:HAS_OUTPUT]->(o:TaskOutput)
                OPTIONAL MATCH (t)-[:HAS_FAILURE]->(f:FailureReport)
                WITH t, o, collect(f {{.*}}) AS failures
                RETURN t {{.*,
                    output: o {{.*}},
                    failures: failures
                }} AS task
                ORDER BY t.created_at DESC
            """, **params)

            for record in result:
                task = dict(record["task"])
                task_id = task.get("task_id", "unknown")
                agent = task.get("assigned_to", task.get("agent", "unknown"))

                # Generate QUEUED event from creation
                created_at = task.get("created_at")
                if created_at:
                    try:
                        ts = created_at.iso_format() if hasattr(created_at, 'iso_format') else str(created_at)
                    except Exception:
                        ts = str(created_at)
                    entries.append({
                        "event": "QUEUED",
                        "ts": ts,
                        "task_id": task_id,
                        "agent": agent,
                        "priority": task.get("priority", "normal"),
                        "domain": task.get("domain", ""),
                        "source": task.get("source", ""),
                        "title": task.get("title", ""),
                        "skill_hint": task.get("skill_hint", ""),
                    })

                # Generate EXECUTING event if task was started
                started_at = task.get("started_at")
                if started_at:
                    try:
                        ts = started_at.iso_format() if hasattr(started_at, 'iso_format') else str(started_at)
                    except Exception:
                        ts = str(started_at)
                    entries.append({
                        "event": "EXECUTING",
                        "ts": ts,
                        "task_id": task_id,
                        "agent": agent,
                        "executor": "claude-code",
                    })

                # Generate failure events
                for f in task.get("failures", []):
                    f_created = f.get("created_at")
                    try:
                        ts = f_created.iso_format() if hasattr(f_created, 'iso_format') else str(f_created)
                    except Exception:
                        ts = str(f_created) if f_created else ""
                    entries.append({
                        "event": "FAILED",
                        "ts": ts,
                        "task_id": task_id,
                        "agent": agent,
                        "error_class": f.get("error_class", ""),
                        "error_msg": f.get("error_msg", ""),
                        "is_transient": f.get("is_transient", False),
                        "attempt": f.get("attempt", 0),
                    })

                # Generate COMPLETED event if task completed
                status = task.get("status", "")
                completed_at = task.get("completed_at")
                output = task.get("output")
                if status == "COMPLETED" and completed_at:
                    try:
                        ts = completed_at.iso_format() if hasattr(completed_at, 'iso_format') else str(completed_at)
                    except Exception:
                        ts = str(completed_at)
                    entry = {
                        "event": "COMPLETED",
                        "ts": ts,
                        "task_id": task_id,
                        "agent": agent,
                        "executor": "claude-code",
                        "score": task.get("score"),
                    }
                    if output:
                        entry["output_lines"] = output.get("output_lines", 0)
                        entry["duration_s"] = output.get("duration_s", 0)
                    entries.append(entry)

        # Also read telemetry events from PipelineEvent nodes
        # These include SKILL_INVOCATION, SKILL_OUTCOME, EXECUTION_DETAIL,
        # EXECUTION_TRACE, etc. written by _append_ledger_direct
        if not valid_only:
            try:
                with _store.driver.session() as pe_session:
                    pe_params = {}
                    time_clause = ""
                    if hours:
                        time_clause = "AND e.created > datetime() - duration({hours: $hours})"
                        pe_params["hours"] = hours

                    pe_result = pe_session.run(f"""
                        MATCH (e:PipelineEvent)
                        WHERE e.payload IS NOT NULL
                        {time_clause}
                        RETURN e.event_type AS event_type, e.payload AS payload,
                               e.agent AS agent, e.created AS created
                        ORDER BY e.created DESC
                        LIMIT 500
                    """, **pe_params)

                    import json as _json
                    for record in pe_result:
                        payload_str = record.get("payload")
                        if not payload_str:
                            continue
                        try:
                            payload = _json.loads(payload_str)
                            # Only include telemetry events not already covered by Task nodes
                            if payload.get("event") in (
                                "SKILL_INVOCATION", "SKILL_OUTCOME", "SKILL_AGGREGATE",
                                "EXECUTION_DETAIL", "EXECUTION_TRACE",
                                "R008_SKILL_NOT_INVOKED",
                                "REFLECT_SUMMARY", "ARCH_UPDATE_CHECK",
                                "TASK_REPORT_GENERATED", "MODEL_USED",
                                "SESSION_AUTO_CLEANUP",
                            ):
                                entries.append(payload)
                        except Exception:
                            continue
            except Exception as pe_err:
                logger.debug(f"PipelineEvent read failed (non-fatal): {pe_err}")

        # Sort by timestamp
        entries.sort(key=lambda e: e.get("ts", ""))

        if valid_only:
            valid_events = {"QUEUED", "EXECUTING", "COMPLETED", "FAILED"}
            entries = [e for e in entries if e.get("event") in valid_events]

        return entries

    finally:
        if store is None:
            _store.close()


def read_ledger_for_agent(agent: str, hours: int = 24,
                           store: TaskStore = None) -> list[dict]:
    """Read events for a specific agent."""
    entries = read_ledger(hours=hours, store=store)
    return [e for e in entries if e.get("agent") == agent]


def count_events(hours: int = 24, store: TaskStore = None) -> dict:
    """Count events by type in the last N hours."""
    entries = read_ledger(hours=hours, store=store)
    counts = {}
    for e in entries:
        event = e.get("event", "UNKNOWN")
        counts[event] = counts.get(event, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Neo4j-backed ledger reader")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--agent", default=None)
    parser.add_argument("--counts", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    import json

    if args.counts:
        counts = count_events(args.hours)
        for event, count in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"  {event}: {count}")
    elif args.agent:
        entries = read_ledger_for_agent(args.agent, args.hours)
        if args.json:
            print(json.dumps(entries, indent=2, default=str))
        else:
            for e in entries[-20:]:
                print(f"  [{e['event']}] {e['ts'][:19]} {e.get('title', '')[:50]}")
    else:
        entries = read_ledger(hours=args.hours)
        if args.json:
            print(json.dumps(entries, indent=2, default=str))
        else:
            print(f"Total events in last {args.hours}h: {len(entries)}")
            counts = {}
            for e in entries:
                counts[e["event"]] = counts.get(e["event"], 0) + 1
            for event, count in sorted(counts.items(), key=lambda x: -x[1]):
                print(f"  {event}: {count}")


if __name__ == "__main__":
    main()
