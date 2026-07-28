from __future__ import annotations

import pytest

from hulagu.telegram.adapter import TelegramPrincipalError, normalize_update


def raw(*, chat_type: str = "private", actor: int | None = 42, chat: int = 42, callback: bool = False, forwarded: bool = False) -> dict[str, object]:
    envelope: dict[str, object] = {"message_id": 1, "chat": {"id": chat, "type": chat_type}}
    if actor is not None:
        envelope["from"] = {"id": actor}
    if forwarded:
        envelope["forward_origin"] = {"type": "user"}
    if callback:
        return {"update_id": 1, "callback_query": {"id": "cb-1", "from": {"id": actor} if actor is not None else {}, "data": "opaque", "message": envelope}}
    return {"update_id": 1, "message": envelope}


@pytest.mark.parametrize("payload", [raw(chat_type="group"), raw(actor=43), raw(actor=None), raw(forwarded=True), raw(callback=True, actor=43)])
def test_rejects_non_authoritative_telegram_principals(payload: dict[str, object]) -> None:
    with pytest.raises(TelegramPrincipalError):
        normalize_update(payload, pinned_bot_id=7)


def test_callback_actor_not_payload_supplies_principal() -> None:
    update = normalize_update(raw(callback=True), pinned_bot_id=7)
    assert update.principal == (7, 42)
    assert update.callback_data == "opaque"
