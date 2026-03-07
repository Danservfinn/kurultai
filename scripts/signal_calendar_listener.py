#!/usr/bin/env python3
"""
Signal Calendar Listener - Receives Signal messages and routes to calendar handler

Uses signal-cli daemon HTTP API to receive messages.

Usage:
    python3 signal_calendar_listener.py
    (Runs in daemon mode, polls every 10 seconds)

Or with --once flag for single poll:
    python3 signal_calendar_listener.py --once
"""

import os
import sys
import json
import time
import signal
import requests
from datetime import datetime
from pathlib import Path

# Setup path
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from calendar_handler import handle_message

# Configuration
SIGNAL_ACCOUNT = os.getenv("SIGNAL_ACCOUNT", "+15165643945")
SIGNAL_API_URL = os.getenv("SIGNAL_API_URL", "http://127.0.0.1:8080")
GROUP_ID = os.getenv("SIGNAL_GROUP_ID", "BROemHVncLgSz8tReUKBz6V3BeDhDB0EXaJd+sRp6oA=")
POLL_INTERVAL = int(os.getenv("CALENDAR_POLL_INTERVAL", "10"))
LOG_FILE = os.path.expanduser("~/.openclaw/logs/signal_calendar_listener.log")

# Known group members (for name resolution)
GROUP_MEMBERS = {
    "+19194133445": "Danny",
    "+16624580725": "Liz",
}


def log(message: str, level: str = "INFO"):
    """Log to file and stdout."""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    timestamp = datetime.now().isoformat()
    log_line = f"[{timestamp}] [{level}] {message}\n"
    with open(LOG_FILE, "a") as f:
        f.write(log_line)
    print(log_line.strip())


def get_messages() -> list:
    """Poll signal-cli HTTP API for new messages."""
    try:
        # Get messages from the daemon
        response = requests.get(f"{SIGNAL_API_URL}/v1/receive/{SIGNAL_ACCOUNT}", timeout=30)

        if response.status_code != 200:
            log(f"API error: {response.status_code} - {response.text[:100]}", "WARNING")
            return []

        messages = response.json()
        return messages if isinstance(messages, list) else []

    except requests.exceptions.ConnectionError:
        # Daemon not running or not reachable
        return []
    except Exception as e:
        log(f"Error getting messages: {e}", "ERROR")
        return []


def extract_group_messages(raw_messages: list) -> list:
    """Filter for group messages and format for calendar handler."""
    group_messages = []

    for msg in raw_messages:
        # Check for envelope format
        envelope = msg.get("envelope", {})

        # Get sender info
        sender = envelope.get("sender", {})
        sender_number = sender.get("number", "")
        sender_name = sender.get("name") or GROUP_MEMBERS.get(sender_number) or sender_number

        # Get message data
        data_message = envelope.get("dataMessage", {})
        if not data_message:
            continue

        message_text = data_message.get("message", "")

        # Check if it's from our target group
        group_info = data_message.get("groupInfo", {})
        group_id = group_info.get("groupId", "")

        if group_id and group_id != GROUP_ID:
            continue

        if not message_text:
            continue

        group_messages.append({
            "message": message_text,
            "sender": sender_number,
            "sender_name": sender_name,
            "group_id": GROUP_ID,
            "timestamp": datetime.now(),
            "message_id": envelope.get("timestamp")
        })

    return group_messages


def process_calendar_message(raw_msg: dict) -> bool:
    """Process a single message through calendar handler."""
    try:
        response = handle_message(raw_msg)

        if response:
            # Send response back to group
            send_response(response, raw_msg.get("group_id", GROUP_ID))
            return True

        return False

    except Exception as e:
        log(f"Error processing message: {e}", "ERROR")
        return False


def send_response(text: str, group_id: str):
    """Send a response message to the group via API."""
    try:
        payload = {
            "message": text,
            "groupId": group_id
        }
        response = requests.post(
            f"{SIGNAL_API_URL}/v1/send/{SIGNAL_ACCOUNT}",
            json=payload,
            timeout=10
        )

        if response.status_code == 200:
            log(f"Sent response to group")
        else:
            log(f"Failed to send response: {response.status_code} - {response.text[:100]}", "WARNING")

    except Exception as e:
        log(f"Error sending response: {e}", "ERROR")


def run_once():
    """Run a single poll cycle."""
    log("Running single poll cycle")
    raw_messages = get_messages()
    group_messages = extract_group_messages(raw_messages)

    if group_messages:
        log(f"Found {len(group_messages)} group message(s)")
        for msg in group_messages:
            log(f"Processing: [{msg['sender_name']}] {msg['message'][:50]}...")
            process_calendar_message(msg)
    else:
        log("No new messages")

    return len(group_messages)


def run_daemon():
    """Run as daemon, polling for messages."""
    log(f"Starting Signal calendar listener (poll every {POLL_INTERVAL}s)")

    # Setup signal handlers for graceful shutdown
    def handle_signal(signum, frame):
        log("Shutting down listener")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    while True:
        try:
            run_once()
        except Exception as e:
            log(f"Error in daemon loop: {e}", "ERROR")

        time.sleep(POLL_INTERVAL)


def main():
    """Main entry point."""
    if "--once" in sys.argv:
        run_once()
    else:
        run_daemon()


if __name__ == "__main__":
    main()