#!/usr/bin/env python3
"""
telegram_send.py — Send a Telegram message via Bot API.

Mirrors signal_send.py interface for drop-in routing.

Exit codes:
    0 — SUCCESS
    1 — DELIVERY_FAILURE: API returned non-ok
    2 — DAEMON_UNREACHABLE: network error / bot token invalid
    3 — BAD_ARGS: missing chat_id or message

Logs every attempt to ~/.openclaw/logs/telegram_send.log (JSON lines).
"""
from __future__ import annotations
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

COORDINATION_DIR = Path(__file__).resolve().parents[1] / "shared-context" / "hermes-kublai"
if str(COORDINATION_DIR) not in sys.path:
    sys.path.insert(0, str(COORDINATION_DIR))

try:
    from coordination_store import CoordinationStore, DEFAULT_DB
except Exception:  # pragma: no cover - keep legacy raw send usable if coordination import breaks
    CoordinationStore = None
    DEFAULT_DB = COORDINATION_DIR / "coordination.db"

TOKEN_FILE = os.path.expanduser(
    "~/.openclaw/secrets/telegram_kublai_bot_token"
)
LOG_FILE = os.path.expanduser("~/.openclaw/logs/telegram_send.log")
CHUNK_LIMIT = 4000  # Telegram max is 4096; leave headroom


def _load_token() -> str:
    with open(TOKEN_FILE) as f:
        return f.read().strip()


def _log(entry: dict):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


def send(chat_id: str, message: str,
         reply_to_message_id: int = None,
         bypass_reason: str = None) -> tuple[int, dict]:
    """
    Send a Telegram message via Bot API.
    Returns (exit_code, log_entry).
    exit_code: 0=success, 1=delivery_failure/denied, 2=unreachable, 3=bad_args

    bypass_reason is required. Without it, the send is denied to enforce the
    coordination send gate. Use send_once() for public same-group answers.
    Pass bypass_reason="operator-notification" (or similar) only for
    cross-chat/legacy notification paths that are exempt from group locking.

    Long messages are chunked at CHUNK_LIMIT characters.
    The first chunk uses reply_to_message_id (threading); rest are plain.
    """
    if not bypass_reason:
        entry = {"ts": datetime.now(timezone.utc).isoformat(),
                 "chat_id": chat_id, "status": "RAW_SEND_DENIED",
                 "reason": "missing_bypass_reason"}
        _log(entry)
        return 1, entry

    if not message or not message.strip():
        entry = {"ts": datetime.now(timezone.utc).isoformat(),
                 "chat_id": chat_id, "status": "BAD_ARGS",
                 "error": "empty message"}
        _log(entry)
        return 3, entry

    bypass_entry = {"ts": datetime.now(timezone.utc).isoformat(),
                    "chat_id": chat_id, "status": "RAW_SEND_BYPASS",
                    "bypass_reason": bypass_reason}
    _log(bypass_entry)

    try:
        token = _load_token()
    except Exception as e:
        entry = {"ts": datetime.now(timezone.utc).isoformat(),
                 "chat_id": chat_id, "status": "DAEMON_UNREACHABLE",
                 "error": f"Token read error: {e}"}
        _log(entry)
        return 2, entry

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    chunks = [message[i:i + CHUNK_LIMIT]
              for i in range(0, max(len(message), 1), CHUNK_LIMIT)]

    for idx, chunk in enumerate(chunks):
        payload = {
            "chat_id": chat_id,
            "text": chunk,
        }
        if idx == 0 and reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id

        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        ts = datetime.now(timezone.utc).isoformat()
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = json.loads(resp.read())
                if not body.get("ok"):
                    entry = {"ts": ts, "chat_id": chat_id,
                             "status": "DELIVERY_FAILURE",
                             "error": body.get("description", "api error"),
                             "chunk": idx}
                    _log(entry)
                    return 1, entry
        except urllib.error.URLError as e:
            entry = {"ts": ts, "chat_id": chat_id,
                     "status": "DAEMON_UNREACHABLE",
                     "error": str(e), "chunk": idx}
            _log(entry)
            return 2, entry

    entry = {"ts": datetime.now(timezone.utc).isoformat(),
             "chat_id": chat_id, "status": "SUCCESS",
             "message_preview": message[:80],
             "bypass_reason": bypass_reason}
    _log(entry)
    return 0, entry


def send_once(
    chat_id: str,
    message: str,
    root_message_id: str,
    owner: str,
    channel: str = "telegram",
    thread_id: str = "",
    purpose: str = "answer",
    reply_to_message_id: int = None,
    db_path: str | os.PathLike = None,
) -> tuple[int, dict]:
    """Reserve a deterministic outbox key, then send at most once.

    This is the Phase 1 same-group send gate. Callers that have already
    claimed/aggregated a response should use this instead of raw send().
    Raw send() is preserved for cross-chat/legacy notification paths.
    """
    if CoordinationStore is None:
        entry = {"ts": datetime.now(timezone.utc).isoformat(),
                 "chat_id": chat_id, "status": "COORDINATION_UNAVAILABLE",
                 "error": "coordination_store import failed"}
        _log(entry)
        return 2, entry

    store = CoordinationStore(db_path or DEFAULT_DB)
    why = store.explain_why(channel, chat_id, str(root_message_id), thread_id, purpose)
    lock = why.get("lock")
    if not lock:
        entry = {"ts": datetime.now(timezone.utc).isoformat(),
                 "chat_id": chat_id, "status": "SEND_DENIED",
                 "reason": "missing_active_lock",
                 "root_message_id": str(root_message_id)}
        _log(entry)
        return 1, entry

    reservation = store.reserve_public_answer_send(
        lock_id=int(lock["lock_id"]),
        actor=owner,
        text=message,
        purpose=purpose,
    )
    if not reservation.get("allowed"):
        reason = reservation.get("reason")
        if reason in {"duplicate_send_reserved", "terminal_lock"}:
            send_purpose = f"{purpose}:v{lock.get('scope_version', 1)}"
            send_key = store.make_send_key(channel, chat_id, thread_id, str(root_message_id), owner, send_purpose)
            existing = store.get_outbox_item(send_key)
            if existing:
                entry = {"ts": datetime.now(timezone.utc).isoformat(),
                         "chat_id": chat_id, "status": "DEDUPED",
                         "send_key": send_key,
                         "existing_status": existing.get("status")}
                _log(entry)
                return 0, entry
        entry = {"ts": datetime.now(timezone.utc).isoformat(),
                 "chat_id": chat_id, "status": "SEND_DENIED",
                 "reason": reason,
                 "owner": reservation.get("owner") or (reservation.get("lock") or {}).get("owner")}
        _log(entry)
        return 1, entry

    send_key = reservation["send_key"]
    rc, result = send(chat_id, message, reply_to_message_id=reply_to_message_id,
                      bypass_reason=f"coordination_send_gate_reserved:{send_key}")
    if rc == 0:
        provider_message_id = str(result.get("provider_message_id") or result.get("message_id") or "sent")
        store.mark_public_answer_sent(int(lock["lock_id"]), send_key, provider_message_id, owner, final_summary=message[:240])
        result = dict(result)
        result["send_key"] = send_key
    return rc, result


class SameChatMessageToolDenied(Exception):
    """Raised when the message tool is used to send to the same chat it was invoked from.

    The canonical protocol forbids using the message tool for same-group replies.
    Use the normal in-session assistant reply path instead.
    """


def message_tool_guard(
    target_chat_id: str,
    current_chat_id: str,
    purpose: str = "normal",
) -> None:
    """Raise SameChatMessageToolDenied if target == current group and purpose is not explicitly approved.

    Call this before using the Telegram message tool to send a reply.
    For same-group replies, use the normal in-session reply path instead.

    Args:
        target_chat_id: The chat the message would be sent to.
        current_chat_id: The chat the agent is currently active in.
        purpose: Use 'approved_exception' to bypass (cross-chat DMs, channel posts, etc.).
    """
    if str(target_chat_id) == str(current_chat_id) and purpose != "approved_exception":
        raise SameChatMessageToolDenied(
            f"Use normal in-session reply path for same Telegram group {target_chat_id}. "
            "The message tool must not be used to post a second copy into the same group."
        )


if __name__ == "__main__":
    import argparse as _ap
    _parser = _ap.ArgumentParser()
    _parser.add_argument("chat_id")
    _parser.add_argument("message")
    _parser.add_argument("--bypass-reason", default=None)
    _args = _parser.parse_args()
    rc, result = send(_args.chat_id, _args.message, bypass_reason=_args.bypass_reason)
    print(json.dumps(result))
    sys.exit(rc)
