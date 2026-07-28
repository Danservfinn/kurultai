from __future__ import annotations

from hulagu.app import HulaguApp, MemoryStore
from hulagu.telegram.adapter import FakeTelegramAdapter
from hulagu.telegram.commands import CallbackCodec, IdentityDigestKeys


def update(update_id: int, text: str = "/start", *, callback_id: str | None = None) -> dict[str, object]:
    if callback_id is not None:
        return {"update_id": update_id, "callback_query": {"id": callback_id, "from": {"id": 42}, "data": text, "message": {"message_id": 2, "chat": {"id": 42, "type": "private"}}}}
    return {"update_id": update_id, "message": {"message_id": 1, "from": {"id": 42}, "chat": {"id": 42, "type": "private"}, "text": text}}


def app(store: MemoryStore) -> HulaguApp:
    return HulaguApp(FakeTelegramAdapter(bot_id=7), store, pinned_bot_id=7, identity_keys=IdentityDigestKeys({1: b"identity-key"}, 1), callback_codec=CallbackCodec(b"callback-key"), clock=lambda: 100)


def test_start_creates_only_enrollment_then_consent_atomically_promotes_once() -> None:
    store = MemoryStore()
    started = app(store).handle_update(update(1))
    assert len(store.enrollments) == 1
    assert store.tenants == {} and store.outbox == {} and store.jobs == []
    assert started.reply is not None and started.reply.callback_data is not None
    accepted = app(store).handle_update(update(2, started.reply.callback_data, callback_id="cb-1"))
    assert accepted.outcome == "consent_promoted"
    assert len(store.tenants) == 1 and len(store.bindings) == 1 and store.enrollments == {}
    assert len(store.outbox) == 1
    replay = app(store).handle_update(update(3, started.reply.callback_data, callback_id="cb-2"))
    assert replay.outcome == "invalid_callback"
    assert len(store.tenants) == 1 and len(store.outbox) == 1


def test_tenant_a_actor_cannot_present_tenant_b_bound_callback() -> None:
    store = MemoryStore()
    other = {"update_id": 1, "message": {"message_id": 1, "from": {"id": 99}, "chat": {"id": 99, "type": "private"}, "text": "/start"}}
    token = app(store).handle_update(other).reply
    assert token is not None and token.callback_data is not None
    result = app(store).handle_update(update(2, token.callback_data, callback_id="cross-actor"))
    assert result.outcome == "invalid_callback"
    assert store.tenants == {}
    assert "tenant" not in token.callback_data.lower()
