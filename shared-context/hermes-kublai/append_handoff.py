#!/usr/bin/env python3
"""Append a Hermes/Kublai handoff JSONL entry.

Usage:
  python3 append_handoff.py --from hermes --to kublai --topic protocol --summary "..." --mirror
"""
import argparse
import datetime as dt
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
HANDOFFS = BASE / "handoffs.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(description="Append a Hermes/Kublai handoff")
    parser.add_argument("--from", dest="sender", required=True, choices=["hermes", "kublai", "main", "all"])
    parser.add_argument("--to", dest="recipient", required=True, choices=["hermes", "kublai", "main", "all"])
    parser.add_argument("--topic", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--detail", default="")
    parser.add_argument("--mirror", action="store_true", help="Mirror a concise summary to Telegram")
    parser.add_argument("--status", default="new")
    args = parser.parse_args()

    entry = {
        "ts": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
        "from": args.sender,
        "to": args.recipient,
        "topic": args.topic,
        "summary": args.summary,
        "detail": args.detail,
        "mirror": bool(args.mirror),
        "status": args.status,
    }
    HANDOFFS.parent.mkdir(parents=True, exist_ok=True)
    with HANDOFFS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(json.dumps(entry, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
