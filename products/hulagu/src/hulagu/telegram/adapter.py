"""Strict Telegram Bot API contract boundary used by the standalone Hulagu poller."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class TelegramContractError(ValueError):
    pass


class TelegramPrincipalError(TelegramContractError):
    pass


class AmbiguousDeliveryError(RuntimeError):
    """The remote may have accepted a send whose response was not observed."""


@dataclass(frozen=True, slots=True)
class TelegramUpdate:
    bot_id: int
    update_id: int
    chat_id: int
    actor_id: int
    message_id: int | None
    callback_query_id: str | None
    text: str | None = None
    callback_data: str | None = None

    @property
    def principal(self) -> tuple[int, int]:
        return (self.bot_id, self.actor_id)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "TelegramUpdate/v1",
            "bot_id": self.bot_id,
            "update_id": self.update_id,
            "chat_id": self.chat_id,
            "chat_type": "private",
            "actor_id": self.actor_id,
            "message_id": self.message_id,
            "callback_query_id": self.callback_query_id,
        }


@dataclass(frozen=True, slots=True)
class SentMessage:
    chat_id: int
    text: str
    delivery_key: str


class TelegramAdapter(Protocol):
    def get_me(self) -> int: ...
    def get_webhook_info(self) -> str: ...
    def get_updates(self, offset: int) -> list[dict[str, object]]: ...
    def send_message(self, chat_id: int, text: str, delivery_key: str) -> None: ...


def _mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TelegramContractError(f"missing {field}")
    return value


def _positive_int(value: object, field: str, *, allow_zero: bool = False) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < (0 if allow_zero else 1):
        raise TelegramContractError(f"invalid {field}")
    return value


def normalize_update(raw: dict[str, object], *, pinned_bot_id: int, max_text_bytes: int = 4096) -> TelegramUpdate:
    update_id = _positive_int(raw.get("update_id"), "update_id", allow_zero=True)
    callback = raw.get("callback_query")
    callback_id: str | None = None
    callback_data: str | None = None
    if callback is not None:
        callback_map = _mapping(callback, "callback_query")
        callback_id_value = callback_map.get("id")
        callback_data_value = callback_map.get("data")
        if not isinstance(callback_id_value, str) or not callback_id_value:
            raise TelegramContractError("invalid callback query id")
        if not isinstance(callback_data_value, str) or not callback_data_value:
            raise TelegramContractError("invalid callback data")
        callback_id = callback_id_value
        callback_data = callback_data_value
        envelope = _mapping(callback_map.get("message"), "callback message")
        actor = _mapping(callback_map.get("from"), "callback actor")
    else:
        envelope = _mapping(raw.get("message"), "message")
        actor_value = envelope.get("from")
        if not isinstance(actor_value, dict):
            raise TelegramPrincipalError("missing actor is not authoritative")
        actor = actor_value
    chat = _mapping(envelope.get("chat"), "chat")
    actor_id = _positive_int(actor.get("id"), "actor id")
    chat_id = _positive_int(chat.get("id"), "chat id")
    if chat.get("type") != "private" or chat_id != actor_id:
        raise TelegramPrincipalError("update is not an authoritative private-DM principal")
    if "forward_origin" in envelope or "forward_from" in envelope or "sender_chat" in envelope:
        raise TelegramPrincipalError("forwarded or anonymous principals are not authoritative")
    message_id_value = envelope.get("message_id")
    message_id = None if message_id_value is None else _positive_int(message_id_value, "message id")
    text_value = envelope.get("text")
    text = text_value if isinstance(text_value, str) else None
    if text is not None and len(text.encode("utf-8")) > max_text_bytes:
        raise TelegramContractError("oversized text")
    return TelegramUpdate(pinned_bot_id, update_id, chat_id, actor_id, message_id, callback_id, text, callback_data)


class FakeTelegramAdapter:
    """Credential-free deterministic fake; it performs no network I/O."""

    def __init__(self, *, bot_id: int, webhook_url: str = "", updates: list[dict[str, object]] | None = None, ambiguous_delivery_keys: set[str] | None = None) -> None:
        self.bot_id = bot_id
        self.webhook_url = webhook_url
        self.updates = list(updates or [])
        self.ambiguous_delivery_keys = set(ambiguous_delivery_keys or set())
        self.requested_offsets: list[int] = []
        self.sent_messages: list[SentMessage] = []

    def get_me(self) -> int:
        return self.bot_id

    def get_webhook_info(self) -> str:
        return self.webhook_url

    def get_updates(self, offset: int) -> list[dict[str, object]]:
        self.requested_offsets.append(offset)
        selected: list[dict[str, object]] = []
        for item in self.updates:
            update_id = item.get("update_id")
            if isinstance(update_id, int) and not isinstance(update_id, bool) and update_id >= offset:
                selected.append(item)
        return selected

    def send_message(self, chat_id: int, text: str, delivery_key: str) -> None:
        self.sent_messages.append(SentMessage(chat_id, text, delivery_key))
        if delivery_key in self.ambiguous_delivery_keys:
            raise AmbiguousDeliveryError("remote acceptance is unknown")
