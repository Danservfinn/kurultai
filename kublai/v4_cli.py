"""Command-line facade for Kublai brain v4 workflows."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .brain_service import BrainService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kublai-v4")
    parser.add_argument("--wiki-root", default=os.getenv("BRAIN_WIKI_ROOT", str(Path.home() / "brain")))
    parser.add_argument("--telemetry-db", default=os.getenv("KUBLAI_TELEMETRY_DB", str(Path.home() / ".kublai/telemetry.db")))
    parser.add_argument("--index-db", default=os.getenv("BRAIN_INDEX_DB", str(Path.home() / ".brain-index/brain.db")))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--request-id")
    sub = parser.add_subparsers(dest="command", required=True)

    ask = sub.add_parser("ask")
    ask.add_argument("query")
    ask.add_argument("--privacy-scope", default="public", choices=["public", "private", "hard-private"])

    for name in ("capture", "ingest", "save"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--content", required=True)
        cmd.add_argument("--title")
        cmd.add_argument("--source")
        cmd.add_argument("--publish", action="store_true")
        cmd.add_argument("--public-stub", action="store_true")
        cmd.add_argument("--privacy-scope", default=None, choices=["public", "private", "hard-private"])
        cmd.add_argument("--apply", action="store_true")
        cmd.add_argument("--dry-run", action="store_true")

    publish = sub.add_parser("publish")
    publish.add_argument("--output-root")
    publish.add_argument("--apply", action="store_true")
    publish.add_argument("--dry-run", action="store_true")
    publish.add_argument("--privacy-scope", default="public", choices=["public", "private", "hard-private"])

    research = sub.add_parser("research")
    research.add_argument("query")
    research.add_argument("--privacy-scope", default="public", choices=["public", "private", "hard-private"])

    write = sub.add_parser("write")
    write.add_argument("topic")
    write.add_argument("--privacy-scope", default="public", choices=["public", "private", "hard-private"])

    wiki = sub.add_parser("wiki")
    wiki.add_argument("--query", default="")
    wiki.add_argument("--rel-path")
    wiki.add_argument("--privacy-scope", default="public", choices=["public", "private", "hard-private"])

    sub.add_parser("process-inbox")
    sub.add_parser("connect")
    sub.add_parser("brief")
    sub.add_parser("lint")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    service = BrainService(args.wiki_root, args.telemetry_db, args.index_db)
    try:
        result = dispatch(service, args)
        if args.json:
            print(json.dumps(result, sort_keys=True))
        else:
            print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        payload = {"ok": False, "error": type(exc).__name__, "message": str(exc)}
        print(json.dumps(payload, sort_keys=True), file=sys.stderr)
        return 1


def dispatch(service: BrainService, args: argparse.Namespace) -> dict[str, Any]:
    request_id = args.request_id
    if args.command == "ask":
        return {"ok": True, "result": service.v4.ask(query=args.query, privacy_scope=args.privacy_scope, request_id=request_id)}
    if args.command in {"capture", "ingest", "save"}:
        method = "capture" if args.command == "save" else args.command
        frontmatter: dict[str, Any] = {}
        if args.publish:
            frontmatter["publish"] = True
        if args.public_stub:
            frontmatter["public_stub"] = True
        params = {
            "content": args.content,
            "title": args.title,
            "source": args.source,
            "frontmatter": frontmatter or None,
            "privacy_scope": args.privacy_scope,
            "request_id": request_id,
        }
        if args.apply:
            return {"ok": True, "result": getattr(service.v4, f"{method}_apply")(**params)}
        return {"ok": True, "result": getattr(service.v4, f"{method}_dry_run")(**params)}
    if args.command == "publish":
        if args.privacy_scope != "public":
            raise ValueError("publish is public-only")
        params = {"output_root": args.output_root, "request_id": request_id}
        return {"ok": True, "result": service.v4.publish_apply(**params) if args.apply else service.v4.publish_dry_run(**params)}
    if args.command == "research":
        if args.privacy_scope != "public":
            raise ValueError("research external/RSG surface is public-only")
        return {"ok": True, "result": service.v4.research_public_dossier(query=args.query, request_id=request_id)}
    if args.command == "write":
        if args.privacy_scope != "public":
            raise ValueError("write uses public exemplars and public context only")
        return {"ok": True, "result": service.v4.write_dry_run(topic=args.topic, request_id=request_id)}
    if args.command == "wiki":
        if args.privacy_scope != "public":
            raise ValueError("wiki CLI defaults to public-safe retrieval")
        if args.rel_path:
            return {"ok": True, "result": service.v4.public_get(rel_path=args.rel_path)}
        return {"ok": True, "result": service.v4.public_search(query=args.query, limit=10) if args.query else service.v4.public_pages()}
    if args.command in {"process-inbox", "connect", "brief"}:
        return {"ok": True, "result": {"dry_run": True, "command": args.command, "proposal_required": True, "message": "Workflow registered; mutating actions require explicit --apply through capture/ingest/write/publish surfaces."}}
    if args.command == "lint":
        return {"ok": True, "result": service.v4.lint()}
    raise ValueError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
