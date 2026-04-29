#!/usr/bin/env python3
from __future__ import annotations

"""Thread and root message ID resolution for Telegram messages.

Determines the root_message_id and thread_id used for lock keying,
so follow-ups in the same thread all map to the same lock scope.
"""

from typing import Any


def resolve_thread_root(message_data: dict[str, Any]) -> tuple[str, str]:
    """Resolve (root_message_id, thread_id) from a Telegram message dict.

    Rules (in priority order):
      1. If this message is a reply, root = the replied-to message_id.
         Walk the chain one level only (we don't have full chain available).
      2. If message_thread_id is set (forum/topic group), root = thread_id start.
         thread_id = message_thread_id.
      3. Otherwise root = this message_id, thread_id = "".

    Returns:
      (root_message_id, thread_id) — both as strings.
    """
    msg_id = str(message_data.get("message_id", ""))
    thread_id = str(message_data.get("message_thread_id", "") or "")

    reply_to = message_data.get("reply_to_message")
    if reply_to:
        root = str(reply_to.get("message_id", msg_id))
        return root, thread_id

    if thread_id:
        return thread_id, thread_id

    return msg_id, ""


def make_canonical_lock_id(channel: str, chat_id: str, root_message_id: str) -> str:
    """Format: channel:chat_id:root_message_id — used as the canonical lock_id string."""
    return f"{channel}:{chat_id}:{root_message_id}"


def normalize_chat_id(raw_chat_id: Any) -> str:
    """Ensure chat_id is a string (Telegram IDs may be ints in some SDKs)."""
    return str(raw_chat_id)


def extract_message_metadata(update: dict[str, Any]) -> dict[str, Any]:
    """Pull normalized metadata from a raw Telegram update dict.

    Returns:
      chat_id, message_id, root_message_id, thread_id,
      sender_id, text, is_bot, date, channel.
    """
    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat", {})
    sender = message.get("from", {})

    chat_id = normalize_chat_id(chat.get("id", ""))
    message_id = str(message.get("message_id", ""))
    root_message_id, thread_id = resolve_thread_root(message)

    return {
        "channel": "telegram",
        "chat_id": chat_id,
        "message_id": message_id,
        "root_message_id": root_message_id,
        "thread_id": thread_id,
        "sender_id": str(sender.get("id", "")),
        "sender_username": sender.get("username", ""),
        "is_bot": bool(sender.get("is_bot", False)),
        "text": message.get("text", ""),
        "date": message.get("date", 0),
        "canonical_lock_id": make_canonical_lock_id("telegram", chat_id, root_message_id),
    }
