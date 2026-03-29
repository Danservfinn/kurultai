#!/usr/bin/env python3
"""
signal_send.py — Send a Signal message via the HTTP JSON-RPC daemon.

NEVER use signal-cli CLI directly when the daemon is running — file lock conflict.

Usage:
    python3 signal_send.py "+19193375833" "Hello, world"
    echo "Hello" | python3 signal_send.py "+19193375833"

Exit codes:
    0 — SUCCESS: daemon confirmed delivery
    1 — DELIVERY_FAILURE: daemon returned non-SUCCESS result
    2 — DAEMON_UNREACHABLE: cannot connect to 127.0.0.1:8080
    3 — BAD_ARGS: missing recipient or message

Logs every send attempt to ~/.openclaw/logs/signal_send.log (JSON lines).
Prints one-line summary to stdout for agent capture:
    SIGNAL_SEND SUCCESS recipient=+19193375833 ts=1742700000000
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

SIGNAL_ACCOUNT = os.getenv("SIGNAL_ACCOUNT", "+15165643945")
DAEMON_URL = os.getenv("SIGNAL_DAEMON_URL", "http://127.0.0.1:8080/api/v1/rpc")
LOG_FILE = os.path.expanduser("~/.openclaw/logs/signal_send.log")
TIMEOUT_SECS = 15


def _log(entry: dict):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


CHUNK_LIMIT = 3800  # Signal practical limit with safety margin


def send(recipient: str, message: str,
         quote_timestamp: int = None,
         quote_author: str = None) -> tuple[int, dict]:
    """
    Send a Signal message via the HTTP daemon.
    Returns (exit_code, log_entry).
    exit_code: 0=success, 1=delivery_failure, 2=daemon_unreachable

    Long messages are automatically chunked into multiple sends.
    The first chunk gets the reply-threading quote; subsequent chunks
    are plain follow-up messages.

    Optional: quote_timestamp + quote_author create a threaded reply
    to the original message (Signal's quoteTimestamp feature).
    """
    if len(message) <= CHUNK_LIMIT:
        return _send_single(recipient, message, quote_timestamp, quote_author)

    # Chunk long messages at paragraph boundaries
    chunks = _chunk_message(message, CHUNK_LIMIT)
    last_rc, last_entry = 0, {}
    for i, chunk in enumerate(chunks):
        # Only first chunk gets the reply-thread quote
        qt = quote_timestamp if i == 0 else None
        qa = quote_author if i == 0 else None
        rc, entry = _send_single(recipient, chunk, qt, qa)
        last_rc, last_entry = rc, entry
        if rc != 0:
            return rc, entry  # Stop on first failure
    return last_rc, last_entry


def _chunk_message(text: str, limit: int) -> list[str]:
    """Split text into chunks at paragraph boundaries."""
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        # Try to break at a double-newline (paragraph)
        cut = text.rfind('\n\n', 0, limit)
        if cut < limit // 3:
            # No good paragraph break — try single newline
            cut = text.rfind('\n', 0, limit)
        if cut < limit // 3:
            # No good line break — hard cut at limit
            cut = limit
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip('\n')
    return chunks


def _send_single(recipient: str, message: str,
                 quote_timestamp: int = None,
                 quote_author: str = None) -> tuple[int, dict]:
    """Send a single Signal message (no chunking)."""
    params = {
        "account": SIGNAL_ACCOUNT,
        "recipient": [recipient],
        "message": message,
    }
    if quote_timestamp and quote_author:
        params["quoteTimestamp"] = quote_timestamp
        params["quoteAuthor"] = quote_author

    payload = {
        "jsonrpc": "2.0",
        "method": "send",
        "params": params,
        "id": 1,
    }

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        DAEMON_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    ts = datetime.now(timezone.utc).isoformat()

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECS) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.URLError as e:
        entry = {"ts": ts, "recipient": recipient, "status": "DAEMON_UNREACHABLE", "error": str(e)}
        _log(entry)
        print(f"SIGNAL_SEND DAEMON_UNREACHABLE: {e}", file=sys.stderr)
        return 2, entry
    except Exception as e:
        entry = {"ts": ts, "recipient": recipient, "status": "SEND_ERROR", "error": str(e)}
        _log(entry)
        print(f"SIGNAL_SEND ERROR: {e}", file=sys.stderr)
        return 1, entry

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        entry = {"ts": ts, "recipient": recipient, "status": "BAD_RESPONSE", "raw": raw[:500], "error": str(e)}
        _log(entry)
        print(f"SIGNAL_SEND BAD_RESPONSE: {e}", file=sys.stderr)
        return 1, entry

    result = data.get("result", {})
    results_list = result.get("results", []) if isinstance(result, dict) else []
    delivery_type = results_list[0].get("type", "UNKNOWN") if results_list else None
    receipt_ts = result.get("timestamp") if isinstance(result, dict) else None

    entry = {
        "ts": ts,
        "recipient": recipient,
        "message_preview": message[:80],
        "status": delivery_type or "NO_RESULT",
        "timestamp": receipt_ts,
        "raw_result": data,
    }
    _log(entry)

    if delivery_type == "SUCCESS":
        print(f"SIGNAL_SEND SUCCESS recipient={recipient} ts={receipt_ts}")
        return 0, entry
    else:
        print(f"SIGNAL_SEND FAILED type={delivery_type} recipient={recipient}", file=sys.stderr)
        return 1, entry


def main():
    if len(sys.argv) < 2:
        print("Usage: signal_send.py RECIPIENT [MESSAGE]", file=sys.stderr)
        print("       echo MESSAGE | signal_send.py RECIPIENT", file=sys.stderr)
        sys.exit(3)

    recipient = sys.argv[1]

    if len(sys.argv) >= 3:
        message = " ".join(sys.argv[2:])
    elif not sys.stdin.isatty():
        message = sys.stdin.read().strip()
    else:
        print("Error: no message provided (pass as arg or pipe via stdin)", file=sys.stderr)
        sys.exit(3)

    if not message:
        print("Error: empty message", file=sys.stderr)
        sys.exit(3)

    exit_code, _ = send(recipient, message)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
