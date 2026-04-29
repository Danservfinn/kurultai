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
    why.add_argument("--format", choices=["json", "telegram"], default="json",
                     help="Output format: raw json or human-readable Telegram text")

    req_contrib = sub.add_parser("request-contribution", help="Emit a contribution.requested event")
    req_contrib.add_argument("--lock-id", type=int, required=True)
    req_contrib.add_argument("--from-agent", required=True)
    req_contrib.add_argument("--to-agent", required=True)
    req_contrib.add_argument("--question", required=True)
    req_contrib.add_argument("--deadline-at", default=None)

    final_ready = sub.add_parser("final-answer-ready", help="Transition lock to ready_to_answer")
    final_ready.add_argument("--lock-id", type=int, required=True)
    final_ready.add_argument("--actor", required=True)
    final_ready.add_argument("--contributors", nargs="*", default=[])
    final_ready.add_argument("--send-key", required=True)
    final_ready.add_argument("--timeout-disclosed", action="store_true", default=False)

    req_review = sub.add_parser("request-review", help="Transition lock to reviewing status")
    req_review.add_argument("--lock-id", type=int, required=True)
    req_review.add_argument("--from-agent", required=True)
    req_review.add_argument("--to-agent", required=True)
    req_review.add_argument("--draft-id", required=True)
    req_review.add_argument("--draft-hash", default="")
    req_review.add_argument("--deadline-at", default=None)

    submit_review = sub.add_parser("submit-review", help="Submit a draft review result")
    submit_review.add_argument("--lock-id", type=int, required=True)
    submit_review.add_argument("--from-agent", required=True)
    submit_review.add_argument("--verdict", required=True,
                               choices=["approve", "approve_with_edits", "reject", "conditional", "abstain"])
    submit_review.add_argument("--blocking", action="store_true", default=False)
    submit_review.add_argument("--safe-public-attribution", default="")

    cancel = sub.add_parser("cancel", help="Cancel an active lock")
    cancel.add_argument("--lock-id", type=int, required=True)
    cancel.add_argument("--actor", required=True)
    cancel.add_argument("--cancel-message-id", default=None)
    cancel.add_argument("--reason", default="human_cancel")

    scope = sub.add_parser("increment-scope", help="Increment scope_version on a lock")
    scope.add_argument("--lock-id", type=int, required=True)
    scope.add_argument("--reason", default="scope_change")
    scope.add_argument("--actor", default="")

    req_approval = sub.add_parser("require-approval", help="Mark lock as requiring human approval")
    req_approval.add_argument("--lock-id", type=int, required=True)
    req_approval.add_argument("--reason", required=True)
    req_approval.add_argument("--actor", default="")

    grant_approval = sub.add_parser("grant-approval", help="Record human approval on a lock")
    grant_approval.add_argument("--lock-id", type=int, required=True)
    grant_approval.add_argument("--by-message-id", required=True)
    grant_approval.add_argument("--actor", default="human")

    disclose_timeout = sub.add_parser("disclose-timeout", help="Record contribution timeout disclosure")
    disclose_timeout.add_argument("--lock-id", type=int, required=True)
    disclose_timeout.add_argument("--missing-contributor", action="append", default=[])
    disclose_timeout.add_argument("--actor", default="")

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
        data = store.explain_why(args.channel, args.chat_id, args.root_message_id, args.thread_id, args.purpose)
        if getattr(args, "format", "json") == "telegram":
            print(store.format_why_for_telegram(data))
        else:
            print_json(data)
        return 0

    if args.command == "request-contribution":
        print_json(store.request_contribution_event(
            args.lock_id, args.from_agent, args.to_agent, args.question,
            getattr(args, "deadline_at", None),
        ))
        return 0

    if args.command == "final-answer-ready":
        print_json(store.record_final_answer_ready(
            args.lock_id, args.actor, args.contributors, args.send_key,
            timeout_disclosed=args.timeout_disclosed,
        ))
        return 0

    if args.command == "request-review":
        print_json(store.request_draft_review(
            args.lock_id, args.from_agent, args.to_agent,
            args.draft_id, getattr(args, "draft_hash", ""),
            deadline_at=getattr(args, "deadline_at", None),
        ))
        return 0

    if args.command == "submit-review":
        print_json(store.submit_draft_review(
            args.lock_id, args.from_agent, args.verdict,
            blocking=args.blocking,
            safe_public_attribution=getattr(args, "safe_public_attribution", ""),
        ))
        return 0

    if args.command == "cancel":
        print_json(store.cancel_lock(
            args.lock_id, args.actor,
            cancel_message_id=getattr(args, "cancel_message_id", None),
            reason=args.reason,
        ))
        return 0

    if args.command == "increment-scope":
        print_json(store.increment_scope_version(args.lock_id, reason=args.reason, actor=args.actor))
        return 0

    if args.command == "require-approval":
        print_json(store.mark_human_approval_required(args.lock_id, args.reason, actor=args.actor))
        return 0

    if args.command == "grant-approval":
        print_json(store.set_human_approved(args.lock_id, args.by_message_id, actor=args.actor))
        return 0

    if args.command == "disclose-timeout":
        print_json(store.disclose_timeout(
            args.lock_id,
            missing_contributors=args.missing_contributor,
            actor=args.actor,
        ))
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
