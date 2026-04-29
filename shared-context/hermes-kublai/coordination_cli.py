#!/usr/bin/env python3
from __future__ import annotations

"""CLI for the Hermes/Kublai SQLite coordination store."""

import argparse
import json
from pathlib import Path

from coordination_store import CoordinationStore, DEFAULT_DB


def print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hermes/Kublai group-chat coordination store")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite coordination DB path")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Initialize SQLite WAL schema")

    claim = sub.add_parser("claim", help="Claim or inspect a response lock")
    add_scope_args(claim)
    claim.add_argument("--owner", required=True)
    claim.add_argument("--purpose", default="answer")
    claim.add_argument("--tier", default="tier1")
    claim.add_argument("--required-contributor", action="append", default=[])
    claim.add_argument("--ttl-seconds", type=int)

    contribute = sub.add_parser("contribute", aliases=["add-contribution"], help="Add an internal contribution to a lock")
    contribute.add_argument("--lock-id", type=int, required=True)
    contribute.add_argument("--contributor", "--agent", dest="contributor", required=True)
    contribute.add_argument("--summary", "--body", dest="summary", required=True)
    contribute.add_argument("--detail", default="")

    process = sub.add_parser("process", aliases=["process-contribution"], help="Record that the aggregator processed a contribution")
    process.add_argument("--lock-id", type=int, required=True)
    process.add_argument("--contribution-id", type=int, required=True)
    process.add_argument("--actor", required=True)
    process.add_argument("--decision", default="accepted")
    process.add_argument("--note", default="")

    finalize = sub.add_parser("finalize", help="Set lock status/final summary")
    finalize.add_argument("--lock-id", type=int, required=True)
    finalize.add_argument("--status", required=True)
    finalize.add_argument("--summary", default="")
    finalize.add_argument("--actor", default="")

    enqueue = sub.add_parser("enqueue-send", aliases=["enqueue_send"], help="Reserve one public send in the idempotent outbox")
    add_scope_args(enqueue)
    enqueue.add_argument("--owner", required=True)
    enqueue.add_argument("--purpose", default="answer")
    enqueue.add_argument("--text", required=True)
    enqueue.add_argument("--send-key", default="", help="Optional precomputed deterministic send key")

    sent = sub.add_parser("mark-sent", help="Mark an outbox item as sent")
    sent.add_argument("--send-key", required=True)
    sent.add_argument("--provider-message-id", required=True)

    why = sub.add_parser("why", help="Explain lock/contribution/event state for a message")
    add_scope_args(why)
    why.add_argument("--purpose", default="answer")

    return parser


def add_scope_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--channel", required=True)
    parser.add_argument("--chat-id", required=True)
    parser.add_argument("--thread-id", default="")
    parser.add_argument("--root-message-id", required=True)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    store = CoordinationStore(Path(args.db))

    if args.command == "init":
        store.init_schema()
        print_json({"ok": True, "db": str(store.db_path), "journal_mode": store.pragma("journal_mode"), "tables": store.table_names()})
        return 0

    if args.command == "claim":
        result = store.claim_response_lock(
            channel=args.channel,
            chat_id=args.chat_id,
            thread_id=args.thread_id,
            root_message_id=args.root_message_id,
            owner=args.owner,
            purpose=args.purpose,
            tier=args.tier,
            required_contributors=args.required_contributor,
            ttl_seconds=args.ttl_seconds,
        )
        print_json(result)
        return 0

    if args.command in ("contribute", "add-contribution"):
        print_json(store.add_contribution(args.lock_id, args.contributor, args.summary, args.detail))
        return 0

    if args.command in ("process", "process-contribution"):
        print_json(store.process_contribution(args.lock_id, args.contribution_id, args.actor, args.decision, args.note))
        return 0

    if args.command == "finalize":
        print_json(store.finalize_lock(args.lock_id, args.status, args.summary, args.actor))
        return 0

    if args.command in ("enqueue-send", "enqueue_send"):
        send_key = args.send_key or store.make_send_key(args.channel, args.chat_id, args.thread_id, args.root_message_id, args.owner, args.purpose)
        print_json(store.enqueue_send_once(send_key, args.channel, args.chat_id, args.thread_id, args.text))
        return 0

    if args.command == "mark-sent":
        print_json(store.mark_send_sent(args.send_key, args.provider_message_id))
        return 0

    if args.command == "why":
        print_json(store.explain_why(args.channel, args.chat_id, args.root_message_id, args.thread_id, args.purpose))
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
