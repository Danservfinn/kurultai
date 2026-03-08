#!/usr/bin/env python3
"""
Calendar Reminder Worker - Background job for sending event reminders

Runs every minute via launchd/cron, checks Neo4j for due reminders,
and sends them via signal-cli.

NOISE REDUCTION PRINCIPLES:
1. Only log when actionable work is performed
2. Suppress all "system check" / "heartbeat" style messages
3. Send digest only once per day (track state)
4. Never retry failed sends within the same window (prevents spam)
"""

import os
import sys
import subprocess
import json
from datetime import datetime, date
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_calendar import (
    get_due_reminders,
    mark_reminder_sent,
    get_daily_digest,
    get_due_notifications,
    mark_notification_sent,
)

# Signal configuration
SIGNAL_ACCOUNT = os.getenv("SIGNAL_ACCOUNT", "+15165643945")
GROUP_ID = os.getenv("SIGNAL_GROUP_ID", "BROemHVncLgSz8tReUKBz6V3BeDhDB0EXaJd+sRp6oA=")

# Do-not-remind list — these numbers will never receive calendar reminders
DO_NOT_REMIND_LIST = [
    "+16624580725",  # Liz — opted out
]

# Logging - only for actionable events
LOG_FILE = os.path.expanduser("~/.openclaw/logs/calendar_reminders.log")
STATE_FILE = os.path.expanduser("~/.openclaw/state/calendar_reminders.json")

# Quiet hours for digest (don't spam if system was down)
DIGEST_HOUR = 8
DIGEST_WINDOW_MINUTES = 5  # Only attempt digest within 5 min window


def _load_state() -> dict:
    """Load persistent state tracking what we've already done."""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {
        "last_digest_date": None,
        "failed_reminders": [],  # Track failures to avoid retry spam
        "digest_attempts_today": 0
    }


def _save_state(state: dict):
    """Save persistent state."""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def log(message: str):
    """Log a message with timestamp - ONLY for actionable events."""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    timestamp = datetime.now().isoformat()
    log_line = f"[{timestamp}] {message}\n"
    with open(LOG_FILE, "a") as f:
        f.write(log_line)
    print(log_line.strip())


def send_signal_dm(phone: str, message: str) -> bool:
    """Send a direct message via signal-cli."""
    cmd = [
        "signal-cli",
        "-a", SIGNAL_ACCOUNT,
        "send",
        "-m", message,
        phone
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )
        # Don't log errors here - let caller decide what to log
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        # Silently fail - we don't want noise about signal-cli not being installed
        return False


def send_group_message(message: str) -> bool:
    """Send a message to the group via signal-cli."""
    cmd = [
        "signal-cli",
        "-a", SIGNAL_ACCOUNT,
        "send",
        "-m", message,
        "-g", GROUP_ID
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return False


def process_due_reminders(state: dict) -> int:
    """
    Process all due reminders. Returns count of reminders sent.
    Skips reminders that recently failed (prevents spam on transient errors).
    """
    reminders = get_due_reminders()

    if not reminders:
        return 0

    # Clear old failures (older than 1 hour) to allow retry
    now = datetime.now()
    state["failed_reminders"] = [
        r for r in state["failed_reminders"]
        if (now - datetime.fromisoformat(r["time"])).total_seconds() < 3600
    ]
    failed_ids = {r["id"] for r in state["failed_reminders"]}

    sent_count = 0
    for reminder in reminders:
        reminder_id = reminder["reminder_id"]

        # Skip if we already tried and failed recently (prevents spam)
        if reminder_id in failed_ids:
            continue

        event_name = reminder["event_name"]
        event_start = reminder["event_start"]
        person_name = reminder["person_name"]
        phone = reminder["phone"]
        offset = reminder.get("offset", "custom")

        # Skip if this person opted out of reminders
        if phone in DO_NOT_REMIND_LIST:
            mark_reminder_sent(reminder_id)  # Mark as handled so we don't keep checking
            continue

        # Format message
        if event_start:
            start_str = event_start.strftime("%I:%M %p")
        else:
            start_str = "soon"

        message = f"Reminder: {event_name} at {start_str}"
        if offset:
            message += f" ({offset})"

        # Send DM
        success = send_signal_dm(phone, message)

        if success:
            mark_reminder_sent(reminder_id)
            sent_count += 1
            log(f"Sent reminder to {person_name}: {event_name}")
        else:
            # Track failure to prevent immediate retry
            state["failed_reminders"].append({
                "id": reminder_id,
                "time": now.isoformat()
            })
            # Only log first failure, not retries
            if reminder_id not in failed_ids:
                log(f"Failed to send reminder to {person_name}: {event_name} (will retry later)")

    return sent_count


def process_due_notifications(state: dict) -> int:
    """
    Process all due notification instances from advanced notification rules.
    Supports templates, escalating reminders, and multiple channels.
    Returns count of notifications sent.
    """
    notifications = get_due_notifications()

    if not notifications:
        return 0

    # Clear old failures (older than 1 hour)
    now = datetime.now()
    state["failed_notifications"] = [
        n for n in state.get("failed_notifications", [])
        if (now - datetime.fromisoformat(n["time"])).total_seconds() < 3600
    ]
    failed_ids = {n["id"] for n in state["failed_notifications"]}

    sent_count = 0
    for notif in notifications:
        notification_id = notif["notification_id"]

        # Skip if we already tried and failed recently
        if notification_id in failed_ids:
            continue

        event_name = notif["event_name"]
        event_start = notif["event_start"]
        person_name = notif["person_name"]
        phone = notif["person_phone"]
        template = notif.get("template", "meeting")
        channel = notif.get("channel", "signal")
        message_template = notif.get("message_template")

        # Skip if this person opted out
        if phone in DO_NOT_REMIND_LIST:
            mark_notification_sent(notification_id)
            continue

        # Format message based on template
        if event_start:
            start_str = event_start.strftime("%I:%M %p")
            day_str = event_start.strftime("%a %B %d")
        else:
            start_str = "soon"
            day_str = "TBD"

        # Template-based messages
        if message_template:
            message = message_template.format(
                event_name=event_name,
                start_time=start_str,
                start_date=day_str
            )
        elif template == "deadline":
            message = f"Deadline Alert: {event_name} at {start_str} ({day_str})"
        elif template == "travel":
            message = f"Travel Reminder: {event_name} departs {start_str} ({day_str})"
        else:
            # Default meeting template
            message = f"Reminder: {event_name} at {start_str}"

        # Send via appropriate channel (currently only Signal supported)
        if channel == "signal":
            success = send_signal_dm(phone, message)
        else:
            # For unsupported channels, mark as sent with a note
            success = True
            log(f"Notification {notification_id} uses unsupported channel: {channel}")

        if success:
            mark_notification_sent(notification_id)
            sent_count += 1
            log(f"Sent {template} notification to {person_name}: {event_name}")
        else:
            # Track failure
            if "failed_notifications" not in state:
                state["failed_notifications"] = []
            state["failed_notifications"].append({
                "id": notification_id,
                "time": now.isoformat()
            })
            if notification_id not in failed_ids:
                log(f"Failed to send notification to {person_name}: {event_name} (will retry)")

    return sent_count


def should_send_digest(state: dict) -> bool:
    """
    Determine if we should attempt to send the daily digest.
    Returns True only if:
    1. We're in the digest time window (8:00-8:05 AM)
    2. We haven't already sent a digest today
    3. We haven't already tried too many times (prevents spam if signal-cli fails)
    """
    now = datetime.now()

    # Check time window
    if now.hour != DIGEST_HOUR or now.minute > DIGEST_WINDOW_MINUTES:
        return False

    today_str = now.date().isoformat()

    # Reset daily counters if it's a new day
    if state["last_digest_date"] != today_str:
        state["digest_attempts_today"] = 0

    # Already sent today?
    if state["last_digest_date"] == today_str:
        return False

    # Too many attempts today? (prevents spam if signal-cli is down)
    if state["digest_attempts_today"] >= 2:
        return False

    return True


def send_morning_digest(state: dict) -> bool:
    """
    Send daily digest to the group.
    Updates state to track that digest was attempted/sent.
    """
    today_str = date.today().isoformat()
    state["digest_attempts_today"] = state.get("digest_attempts_today", 0) + 1

    events = get_daily_digest(days=3)

    if not events:
        # No events today - mark as "sent" (nothing to report)
        state["last_digest_date"] = today_str
        return True

    lines = ["[Calendar] Morning! Here's what's coming up:"]
    for e in events:
        dt = e.get("start_datetime")
        if dt:
            date_str = dt.strftime("%a %B %d at %I:%M %p")
        else:
            date_str = "TBD"

        name = e.get("name", "Unnamed")
        location = e.get("location", {})
        loc_name = location.get("name") if location else None
        attendees = e.get("attendees", [])

        line = f"  {date_str} - {name}"
        if loc_name:
            line += f" at {loc_name}"
        if attendees:
            line += f" ({len(attendees)} going)"
        lines.append(line)

    message = "\n".join(lines)
    success = send_group_message(message)

    if success:
        state["last_digest_date"] = today_str
        return True
    else:
        # Don't log failure - we'll try again tomorrow or until attempts exhausted
        return False


def main():
    """
    Main entry point.

    NOISE REDUCTION: This function produces NO OUTPUT unless:
    1. A reminder is successfully sent
    2. A reminder fails (first failure only, not retries)
    3. The daily digest is successfully sent

    This ensures the logs only contain actionable information, not
    "system is running" noise every minute.
    """
    state = _load_state()
    work_done = []

    # Process due reminders (legacy single reminders)
    sent = process_due_reminders(state)
    if sent > 0:
        work_done.append(f"Sent {sent} reminder(s)")

    # Process due notifications (advanced notification rules)
    notif_sent = process_due_notifications(state)
    if notif_sent > 0:
        work_done.append(f"Sent {notif_sent} notification(s)")

    # Check if we should send daily digest
    if should_send_digest(state):
        try:
            digest_sent = send_morning_digest(state)
            if digest_sent:
                work_done.append("Sent morning digest")
        except Exception:
            # Silently ignore digest errors - we'll try again tomorrow
            pass

    # Save state (digest tracking, failure tracking)
    _save_state(state)

    # Only log if we did something actionable
    if work_done:
        log(f"Reminder worker: {', '.join(work_done)}")

    # Exit silently if no work (no logs = no noise)


if __name__ == "__main__":
    main()
