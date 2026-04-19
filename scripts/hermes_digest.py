#!/usr/bin/env python3
"""Hermes daily digest.

Addresses review finding H4 — silent failures.

Runs once per day (cron) and enqueues a Signal DM summarizing the last
24 h of Hermes activity: fixes applied, rolled back, rate-limited,
denied at authoring, aborted at baseline, plus circuit-breaker state
and queue depths. Fires even if activity was zero, so the operator
always sees recent status and detects silent stalls.

If SignalHealthFlag is degraded, writes a hermes task instead of
enqueueing a DM — the task surfaces on next daemon cycle and is
visible via the dashboard / on-box inspection.

Usage:
    python3 hermes_digest.py               # send digest for last 24h
    python3 hermes_digest.py --dry-run     # print digest text, do not enqueue
    python3 hermes_digest.py --hours 12    # custom window
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

QUEUE_DIR = Path.home() / ".openclaw" / "queues" / "hermes-fix-jobs"
CIRCUIT_STATE = Path.home() / ".openclaw" / "state" / "hermes_circuit_breaker.json"
RATE_STATE = Path.home() / ".openclaw" / "state" / "hermes_rate_limits.json"
FLAGS_DIR = Path.home() / ".openclaw" / "flags"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _count_files(p: Path) -> int:
    try:
        return sum(1 for _ in p.glob("*.json"))
    except OSError:
        return 0


def _queue_depths() -> dict:
    return {
        "pending": _count_files(QUEUE_DIR / "pending"),
        "in_progress": _count_files(QUEUE_DIR / "in-progress"),
        "done": _count_files(QUEUE_DIR / "done"),
        "failed": _count_files(QUEUE_DIR / "failed"),
        "rate_limited": _count_files(QUEUE_DIR / "rate-limited"),
    }


def _active_flags() -> list[str]:
    try:
        return sorted(p.name for p in FLAGS_DIR.glob("hermes-*.flag"))
    except OSError:
        return []


def _circuit_state() -> dict:
    if not CIRCUIT_STATE.exists():
        return {"tripped": False, "event_count": 0}
    try:
        state = json.loads(CIRCUIT_STATE.read_text())
        return {
            "tripped": state.get("tripped_at") is not None,
            "trip_reason": state.get("trip_reason"),
            "tripped_at": state.get("tripped_at"),
            "event_count": len(state.get("events", [])),
        }
    except Exception:
        return {"tripped": False, "event_count": 0, "parse_error": True}


def _rate_state() -> dict:
    if not RATE_STATE.exists():
        return {"content_24h": 0, "code_24h": 0}
    try:
        state = json.loads(RATE_STATE.read_text())
        now = _now().timestamp()
        content_24h = sum(1 for t in state.get("content", []) if now - t < 86400)
        code_24h = sum(1 for t in state.get("code", []) if now - t < 86400)
        return {"content_24h": content_24h, "code_24h": code_24h}
    except Exception:
        return {"content_24h": 0, "code_24h": 0, "parse_error": True}


def _action_counts(hours: int) -> dict:
    """Count HermesAction outcomes in the last N hours via Neo4j."""
    try:
        from neo4j_v2_core import TaskStore  # type: ignore
        store = TaskStore()
        try:
            with store.driver.session() as session:
                result = session.run(
                    """
                    MATCH (a:HermesAction)
                    WHERE a.timestamp > datetime() - duration({hours: $h})
                    RETURN a.outcome AS outcome, count(a) AS n
                    ORDER BY n DESC
                    """,
                    h=hours,
                )
                return {r["outcome"] or "unknown": r["n"] for r in result}
        finally:
            store.close()
    except Exception as e:
        return {"__neo4j_error__": str(e)[:120]}


def _commit_counts(hours: int) -> dict:
    """Count HermesCommit nodes in the last N hours, grouped by sweep."""
    try:
        from neo4j_v2_core import TaskStore  # type: ignore
        store = TaskStore()
        try:
            with store.driver.session() as session:
                result = session.run(
                    """
                    MATCH (c:HermesCommit)
                    WHERE c.created_at > datetime() - duration({hours: $h})
                    RETURN c.sweep AS sweep,
                           c.autonomy_level AS level,
                           count(c) AS n,
                           sum(CASE WHEN c.reverted THEN 1 ELSE 0 END) AS reverted
                    """,
                    h=hours,
                )
                return [
                    {
                        "sweep": r["sweep"],
                        "level": r["level"],
                        "committed": r["n"],
                        "reverted": r["reverted"],
                    }
                    for r in result
                ]
        finally:
            store.close()
    except Exception as e:
        return [{"__neo4j_error__": str(e)[:120]}]


def build_digest(hours: int = 24) -> str:
    """Assemble the digest text."""
    actions = _action_counts(hours)
    commits = _commit_counts(hours)
    queues = _queue_depths()
    circuit = _circuit_state()
    rates = _rate_state()
    flags = _active_flags()

    window_end = _now()
    window_start = window_end - timedelta(hours=hours)

    lines = [
        "Hermes daily digest",
        f"Window: {window_start.isoformat(timespec='minutes')} UTC "
        f"-> {window_end.isoformat(timespec='minutes')} UTC ({hours}h)",
        "",
        "Fix activity:",
    ]
    if commits:
        for c in commits:
            if "__neo4j_error__" in c:
                lines.append(f"  (Neo4j error: {c['__neo4j_error__']})")
            else:
                lines.append(
                    f"  sweep={c['sweep']:<20} level={c['level']:<8} "
                    f"committed={c['committed']:>3}  reverted={c['reverted']}"
                )
    else:
        lines.append("  (no commits in window)")

    lines += [
        "",
        "Action outcomes:",
    ]
    if actions and "__neo4j_error__" not in actions:
        for outcome, n in sorted(actions.items(), key=lambda kv: -kv[1])[:10]:
            lines.append(f"  {outcome:<30} {n:>4}")
    else:
        msg = actions.get("__neo4j_error__", "no actions in window")
        lines.append(f"  ({msg})")

    lines += [
        "",
        f"Rate-limit consumption 24h: content={rates.get('content_24h')} "
        f"code={rates.get('code_24h')}  (caps: 3/hr per scope, 10/day total)",
        "",
        "Queue depths:",
        f"  pending={queues['pending']}  "
        f"in-progress={queues['in_progress']}  "
        f"done={queues['done']}  "
        f"failed={queues['failed']}  "
        f"rate-limited={queues['rate_limited']}",
        "",
    ]

    if circuit.get("tripped"):
        lines.append(
            f"CIRCUIT BREAKER TRIPPED at {circuit.get('tripped_at')}: "
            f"{circuit.get('trip_reason')}"
        )
    else:
        lines.append("Circuit breaker: OK")

    if flags:
        lines.append(f"Active flags ({len(flags)}):")
        for flag in flags:
            lines.append(f"  {flag}")
    else:
        lines.append("No Hermes flags active (fully enabled).")

    return "\n".join(lines)


def _signal_degraded() -> bool:
    try:
        from signal_health_flag import SignalHealthFlag  # type: ignore
        return SignalHealthFlag().is_degraded()
    except Exception:
        return False


def _write_hermes_task(title: str, body: str) -> bool:
    """Fallback path when Signal is degraded — write a task for the daemon
    to surface."""
    try:
        from hermes_watchdog_task_bridge import write_hermes_task  # type: ignore
        write_hermes_task(title, body, priority="high")
        return True
    except ImportError:
        # Fallback: write directly to ~/.openclaw/agents/hermes/tasks/
        try:
            tasks_dir = Path.home() / ".openclaw" / "agents" / "hermes" / "tasks"
            tasks_dir.mkdir(parents=True, exist_ok=True)
            ts = _now().strftime("%Y%m%d-%H%M%S")
            slug = "hermes-digest-signal-degraded"
            path = tasks_dir / f"high-{ts}-{slug}.md"
            path.write_text(
                f"---\n"
                f"agent: hermes\n"
                f"priority: high\n"
                f"created: {_now().isoformat()}\n"
                f"task_type: digest_escalation\n"
                f"source: hermes-digest\n"
                f"---\n\n"
                f"# {title}\n\n{body}\n"
            )
            return True
        except Exception:
            return False
    except Exception:
        return False


def send_digest(hours: int = 24, dry_run: bool = False) -> dict:
    body = build_digest(hours)

    if dry_run:
        print(body)
        return {"status": "dry_run", "bytes": len(body)}

    if _signal_degraded():
        ok = _write_hermes_task("Hermes digest (Signal degraded)", body)
        return {"status": "task_file" if ok else "failed", "reason": "signal_degraded"}

    try:
        from notification_queue import NotificationQueue  # type: ignore
        from hermes_notify import _operator_phone  # type: ignore
        q = NotificationQueue()
        task_id = f"digest-{_now().strftime('%Y%m%d')}"
        qid = q.enqueue(
            task_id=task_id,
            agent="hermes",
            notify_target=_operator_phone(),
            message=body,
        )
        return {"status": "queued", "queue_id": qid}
    except Exception as e:
        # Last-ditch: try to get the digest into a task file
        ok = _write_hermes_task("Hermes digest (queue unreachable)", body)
        return {
            "status": "task_file" if ok else "failed",
            "reason": f"queue_error: {e}",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes daily digest")
    parser.add_argument("--hours", type=int, default=24,
                        help="Lookback window in hours (default: 24)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print digest text to stdout, do not enqueue")
    args = parser.parse_args()

    result = send_digest(hours=args.hours, dry_run=args.dry_run)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] in ("queued", "task_file", "dry_run") else 1


if __name__ == "__main__":
    sys.exit(main())
