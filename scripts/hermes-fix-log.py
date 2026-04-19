#!/usr/bin/env python3
"""Hermes fix-log CLI.

Operator-facing audit tool for Hermes commits. Reads HermesCommit and
HermesAction nodes from Neo4j and prints readable summaries.

Usage:
    hermes-fix-log list                     # last 50 Hermes commits
    hermes-fix-log show <sha>               # full commit + status
    hermes-fix-log stats --window 7d        # counts by sweep/outcome
    hermes-fix-log reverted                 # recently-reverted commits
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _driver_session():
    from neo4j_v2_core import TaskStore  # type: ignore
    store = TaskStore()
    return store


def _parse_window(s: str) -> int:
    """Parse '7d' / '24h' / '30m' into hours. Defaults to 24h."""
    if s.endswith("d"):
        return int(s[:-1]) * 24
    if s.endswith("h"):
        return int(s[:-1])
    if s.endswith("m"):
        return max(1, int(s[:-1]) // 60)
    return 24


def cmd_list(limit: int = 50) -> int:
    store = _driver_session()
    try:
        with store.driver.session() as session:
            result = session.run(
                "MATCH (c:HermesCommit) "
                "RETURN c.sha AS sha, c.subject AS subject, "
                "       c.sweep AS sweep, c.autonomy_level AS level, "
                "       c.reverted AS reverted, c.created_at AS created_at "
                "ORDER BY c.created_at DESC LIMIT $n",
                n=limit,
            )
            rows = list(result)
            if not rows:
                print("(no Hermes commits)")
                return 0
            fmt = "{sha:10}  {when:19}  {level:8}  {sweep:16}  {rev}  {subj}"
            print(fmt.format(
                sha="sha", when="created_at", level="level",
                sweep="sweep", rev="rev", subj="subject",
            ))
            print("-" * 100)
            for r in rows:
                created = r["created_at"]
                when = str(created)[:19] if created else "?"
                print(fmt.format(
                    sha=(r["sha"] or "?")[:10],
                    when=when,
                    level=(r["level"] or "?")[:8],
                    sweep=(r["sweep"] or "?")[:16],
                    rev=("R" if r["reverted"] else " "),
                    subj=(r["subject"] or "?")[:60],
                ))
        return 0
    finally:
        store.close()


def cmd_show(sha: str) -> int:
    from hermes_commit import find_commit
    c = find_commit(sha)
    if c is None:
        print(f"No HermesCommit found for {sha!r}")
        return 1
    # Normalize Neo4j DateTime into strings for readability
    out = {}
    for k, v in c.items():
        out[k] = str(v) if not isinstance(v, (str, int, float, bool, list, dict, type(None))) else v
    print(json.dumps(out, indent=2, default=str))
    return 0


def cmd_stats(window: str = "7d") -> int:
    hours = _parse_window(window)
    store = _driver_session()
    try:
        with store.driver.session() as session:
            # Commits grouped by sweep + reverted
            r1 = session.run(
                "MATCH (c:HermesCommit) "
                "WHERE c.created_at > datetime() - duration({hours: $h}) "
                "RETURN c.sweep AS sweep, c.autonomy_level AS level, "
                "       count(c) AS committed, "
                "       sum(CASE WHEN c.reverted THEN 1 ELSE 0 END) AS reverted",
                h=hours,
            )
            print(f"Hermes stats — last {hours}h ({window})")
            print()
            print("Commits by sweep:")
            rows = list(r1)
            if rows:
                fmt = "  {sweep:20}  {level:8}  committed={c:>3}  reverted={r}"
                for rec in rows:
                    print(fmt.format(
                        sweep=rec["sweep"] or "?",
                        level=rec["level"] or "?",
                        c=rec["committed"], r=rec["reverted"],
                    ))
            else:
                print("  (none)")
            print()

            # Action outcomes
            r2 = session.run(
                "MATCH (a:HermesAction) "
                "WHERE a.timestamp > datetime() - duration({hours: $h}) "
                "RETURN a.outcome AS outcome, count(a) AS n "
                "ORDER BY n DESC LIMIT 20",
                h=hours,
            )
            print("Action outcomes:")
            rows2 = list(r2)
            if rows2:
                for rec in rows2:
                    print(f"  {(rec['outcome'] or '?'):30} {rec['n']:>4}")
            else:
                print("  (none)")
        return 0
    finally:
        store.close()


def cmd_reverted(limit: int = 20) -> int:
    store = _driver_session()
    try:
        with store.driver.session() as session:
            result = session.run(
                "MATCH (c:HermesCommit {reverted: true}) "
                "RETURN c.sha AS sha, c.revert_sha AS revert_sha, "
                "       c.subject AS subject, c.reverted_at AS reverted_at "
                "ORDER BY c.reverted_at DESC LIMIT $n",
                n=limit,
            )
            rows = list(result)
            if not rows:
                print("(no reverted Hermes commits)")
                return 0
            for r in rows:
                print(
                    f"{(r['sha'] or '?')[:10]} reverted_by "
                    f"{(r['revert_sha'] or '?')[:10]} at "
                    f"{str(r['reverted_at'] or '')[:19]}  "
                    f"{(r['subject'] or '?')[:60]}"
                )
        return 0
    finally:
        store.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes fix-log CLI")
    sub = parser.add_subparsers(dest="cmd")

    p_list = sub.add_parser("list", help="List recent Hermes commits")
    p_list.add_argument("--limit", type=int, default=50)

    p_show = sub.add_parser("show", help="Show a single Hermes commit")
    p_show.add_argument("sha")

    p_stats = sub.add_parser("stats", help="Aggregate counts")
    p_stats.add_argument("--window", default="7d",
                          help="Window like 24h, 7d, 30m (default: 7d)")

    p_reverted = sub.add_parser("reverted", help="Recently-reverted commits")
    p_reverted.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()

    if args.cmd == "list":
        return cmd_list(args.limit)
    if args.cmd == "show":
        return cmd_show(args.sha)
    if args.cmd == "stats":
        return cmd_stats(args.window)
    if args.cmd == "reverted":
        return cmd_reverted(args.limit)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
