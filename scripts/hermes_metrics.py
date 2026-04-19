#!/usr/bin/env python3
"""Hermes metrics module.

Cypher-backed summary queries for dashboards, daily digest, and CLI
invocations. Returns plain dicts — consumers format as they see fit.

Usage:
    hermes_metrics.py --summary
    hermes_metrics.py --summary --window 24h
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _session():
    from neo4j_v2_core import TaskStore  # type: ignore
    return TaskStore()


def _parse_window(s: str) -> int:
    """Parse '24h' / '7d' / '30m' → hours."""
    if s.endswith("d"):
        return int(s[:-1]) * 24
    if s.endswith("h"):
        return int(s[:-1])
    if s.endswith("m"):
        return max(1, int(s[:-1]) // 60)
    return 24


def commits_by_sweep(hours: int) -> list[dict]:
    store = _session()
    try:
        with store.driver.session() as s:
            r = s.run(
                "MATCH (c:HermesCommit) "
                "WHERE c.created_at > datetime() - duration({hours: $h}) "
                "RETURN c.sweep AS sweep, c.autonomy_level AS level, "
                "       count(c) AS committed, "
                "       sum(CASE WHEN c.reverted THEN 1 ELSE 0 END) AS reverted",
                h=hours,
            )
            return [dict(rec) for rec in r]
    finally:
        store.close()


def action_outcomes(hours: int) -> dict:
    store = _session()
    try:
        with store.driver.session() as s:
            r = s.run(
                "MATCH (a:HermesAction) "
                "WHERE a.timestamp > datetime() - duration({hours: $h}) "
                "RETURN a.outcome AS outcome, count(a) AS n",
                h=hours,
            )
            return {rec["outcome"] or "unknown": rec["n"] for rec in r}
    finally:
        store.close()


def revert_rate(hours: int) -> dict:
    """Return {committed, reverted, revert_rate} for the window."""
    store = _session()
    try:
        with store.driver.session() as s:
            r = s.run(
                "MATCH (c:HermesCommit) "
                "WHERE c.created_at > datetime() - duration({hours: $h}) "
                "RETURN count(c) AS committed, "
                "       sum(CASE WHEN c.reverted THEN 1 ELSE 0 END) AS reverted",
                h=hours,
            )
            rec = next(iter(r), None)
            if rec is None:
                return {"committed": 0, "reverted": 0, "rate": 0.0}
            c, v = rec["committed"] or 0, rec["reverted"] or 0
            rate = (v / c) if c else 0.0
            return {"committed": c, "reverted": v, "rate": round(rate, 3)}
    finally:
        store.close()


def most_active_targets(hours: int, limit: int = 10) -> list[dict]:
    """Targets most frequently committed against in the window."""
    store = _session()
    try:
        with store.driver.session() as s:
            r = s.run(
                "MATCH (c:HermesCommit) "
                "WHERE c.created_at > datetime() - duration({hours: $h}) "
                "UNWIND c.target_paths AS target "
                "RETURN target, count(c) AS n "
                "ORDER BY n DESC LIMIT $limit",
                h=hours, limit=limit,
            )
            return [dict(rec) for rec in r]
    finally:
        store.close()


def time_to_revert_stats(hours: int = 168) -> dict:
    """For commits that were reverted in the window, how fast was the revert?"""
    store = _session()
    try:
        with store.driver.session() as s:
            r = s.run(
                "MATCH (c:HermesCommit {reverted: true}) "
                "WHERE c.reverted_at > datetime() - duration({hours: $h}) "
                "WITH duration.between(c.created_at, c.reverted_at).seconds AS ttr "
                "RETURN count(*) AS reverted, "
                "       avg(ttr) AS avg_seconds, "
                "       min(ttr) AS min_seconds, "
                "       max(ttr) AS max_seconds",
                h=hours,
            )
            rec = next(iter(r), None)
            if rec is None or rec["reverted"] == 0:
                return {"reverted": 0}
            return {
                "reverted": rec["reverted"],
                "avg_seconds": rec["avg_seconds"],
                "min_seconds": rec["min_seconds"],
                "max_seconds": rec["max_seconds"],
            }
    finally:
        store.close()


def summary(window: str = "7d") -> dict:
    """Aggregate snapshot used by the digest and CLI."""
    hours = _parse_window(window)
    return {
        "window": window,
        "hours": hours,
        "commits_by_sweep": commits_by_sweep(hours),
        "action_outcomes": action_outcomes(hours),
        "revert_rate": revert_rate(hours),
        "most_active_targets": most_active_targets(hours),
        "time_to_revert": time_to_revert_stats(hours),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes metrics")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--window", default="7d")
    args = parser.parse_args()

    if args.summary:
        print(json.dumps(summary(args.window), indent=2, default=str))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
