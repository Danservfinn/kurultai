#!/usr/bin/env python3
"""calendar_cli.py — CLI entry point for calendar commands.

Called by OpenClaw agent when calendar-intent messages are detected.

Usage:
    python3 calendar_cli.py --sender "+1234567890" --sender-name "Danny" --message "Dinner Friday 7pm"

Returns:
    JSON response on stdout: {"response": "...", "success": true}
"""
import sys
import os
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load Neo4j credentials
NEO4J_ENV = os.path.expanduser("~/.openclaw/credentials/neo4j.env")
if os.path.exists(NEO4J_ENV):
    with open(NEO4J_ENV) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, _, v = line.partition('=')
                os.environ.setdefault(k.strip(), v.strip())

from calendar_handler import handle_message


def main():
    parser = argparse.ArgumentParser(description="Calendar CLI for OpenClaw")
    parser.add_argument("--sender", required=True, help="Sender phone number")
    parser.add_argument("--sender-name", required=True, help="Sender display name")
    parser.add_argument("--message", required=True, help="Calendar command text")
    parser.add_argument("--group-id", default=os.getenv("SIGNAL_GROUP_ID", ""))
    args = parser.parse_args()

    msg = {
        "message": args.message,
        "sender": args.sender,
        "sender_name": args.sender_name,
        "group_id": args.group_id,
    }

    try:
        response = handle_message(msg)
        print(json.dumps({"response": response or "", "success": True}))
    except Exception as e:
        print(json.dumps({"response": str(e), "success": False}))
        sys.exit(1)


if __name__ == "__main__":
    main()
