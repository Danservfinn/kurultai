#!/usr/bin/env python3
"""
deliverable_send.py — Generalized deliverable dispatcher for agents.

Provides a unified interface for sending task outputs to humans via
multiple channels. Currently supports Signal; email and Slack are
stubbed for future implementation.

This is the HIGH-LEVEL entry point agents should call when they need
to send a deliverable. It handles:
  - Channel routing
  - Formatting the delivery receipt block for the workspace file
  - Logging

Usage:
    python3 deliverable_send.py --channel signal --recipient +19193375833 \
        --content "Your jokes..." --task-id normal-abc123

    # Or via stdin:
    cat jokes.txt | python3 deliverable_send.py --channel signal \
        --recipient +19193375833 --task-id normal-abc123

    # Returns non-zero on failure. Prints a ## Signal Delivery block
    # that the agent should append to its workspace task file.

Exit codes:
    0 — delivered, receipt block printed to stdout
    1 — delivery failed
    2 — channel daemon/service unreachable
    3 — bad arguments
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
SIGNAL_SEND = SCRIPTS_DIR / "signal_send.py"


# ---------------------------------------------------------------------------
# Channel backends
# ---------------------------------------------------------------------------

def _send_signal(recipient: str, content: str) -> tuple[int, str]:
    """Send via Signal HTTP daemon. Returns (exit_code, raw_response_json)."""
    try:
        result = subprocess.run(
            [sys.executable, str(SIGNAL_SEND), recipient, content],
            capture_output=True,
            text=True,
            timeout=30,
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode == 0:
            # Parse timestamp from "SIGNAL_SEND SUCCESS recipient=... ts=..."
            ts = ""
            for part in stdout.split():
                if part.startswith("ts="):
                    ts = part[3:]
            return 0, ts
        else:
            return result.returncode, stderr
    except subprocess.TimeoutExpired:
        return 2, "timeout waiting for signal_send.py"
    except Exception as e:
        return 1, str(e)


def _send_email(recipient: str, content: str) -> tuple[int, str]:
    """Email delivery — not yet implemented."""
    return 1, "email delivery not yet implemented"


def _send_slack(recipient: str, content: str) -> tuple[int, str]:
    """Slack delivery — not yet implemented."""
    return 1, "slack delivery not yet implemented"


_BACKENDS = {
    "signal": _send_signal,
    "email": _send_email,
    "slack": _send_slack,
}


# ---------------------------------------------------------------------------
# Receipt block formatter
# ---------------------------------------------------------------------------

def _get_raw_response(channel: str) -> str:
    """Read the last log entry's raw_result for the receipt block."""
    if channel != "signal":
        return ""
    log_path = Path.home() / ".openclaw" / "logs" / "signal_send.log"
    try:
        lines = log_path.read_text().strip().splitlines()
        if lines:
            entry = json.loads(lines[-1])
            raw = entry.get("raw_result")
            if raw:
                return json.dumps(raw)
    except Exception:
        pass
    return ""


def format_receipt_block(channel: str, recipient: str, exit_code: int, ts: str) -> str:
    """Format the ## Signal Delivery block for the workspace task file."""
    raw = _get_raw_response(channel) if exit_code == 0 else ""
    lines = [
        f"## Signal Delivery",
        f"- recipient: {recipient}",
        f"- exit_code: {exit_code}",
    ]
    if ts:
        lines.append(f"- timestamp: {ts}")
    if raw:
        lines.append(f"- raw_response: {raw}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def send(channel: str, recipient: str, content: str) -> tuple[int, str]:
    """Send content via the specified channel.

    Returns (exit_code, ts_or_error).
    exit_code 0 = success; ts = delivery timestamp string.
    """
    backend = _BACKENDS.get(channel.lower())
    if backend is None:
        return 3, f"unknown channel: {channel}. Supported: {list(_BACKENDS)}"
    return backend(recipient, content)


def main():
    parser = argparse.ArgumentParser(
        description="Send a task deliverable to a human recipient."
    )
    parser.add_argument("--channel", required=True,
                        choices=list(_BACKENDS),
                        help="Delivery channel (signal, email, slack)")
    parser.add_argument("--recipient", required=True,
                        help="Recipient address (phone number, email, etc.)")
    parser.add_argument("--content", default=None,
                        help="Message content (or pipe via stdin)")
    parser.add_argument("--task-id", default="",
                        help="Task ID for logging purposes")
    args = parser.parse_args()

    if args.content:
        content = args.content
    elif not sys.stdin.isatty():
        content = sys.stdin.read().strip()
    else:
        print("Error: provide --content or pipe content via stdin", file=sys.stderr)
        sys.exit(3)

    if not content:
        print("Error: empty content", file=sys.stderr)
        sys.exit(3)

    exit_code, ts_or_error = send(args.channel, args.recipient, content)

    receipt = format_receipt_block(args.channel, args.recipient, exit_code, ts_or_error if exit_code == 0 else "")

    if exit_code == 0:
        print(receipt)
        print(f"\nDELIVERABLE_SEND SUCCESS channel={args.channel} recipient={args.recipient} ts={ts_or_error}")
    else:
        print(receipt, file=sys.stderr)
        print(f"DELIVERABLE_SEND FAILED channel={args.channel} recipient={args.recipient} error={ts_or_error}",
              file=sys.stderr)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
