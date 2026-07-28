from __future__ import annotations

import pytest

from hulagu.app import HulaguApp, MemoryStore
from hulagu.telegram.adapter import FakeTelegramAdapter
from hulagu.telegram.commands import CallbackCodec, IdentityDigestKeys, RouteKeys
from hulagu.telegram.sender import DeliveryState, OutboxMessage, TelegramSender


def test_digest_rotation_resolves_overlap_and_new_writes_use_active_version() -> None:
    keys = IdentityDigestKeys({1: b"old-key-material", 2: b"new-key-material"}, active_version=1)
    old = keys.digest(7, 42)
    keys.activate(2)
    new = keys.digest(7, 42)
    assert old.version == 1 and new.version == 2
    assert keys.matches(old, 7, 42)
    keys.revoke(1)
    assert not keys.matches(old, 7, 42)
    assert keys.matches(new, 7, 42)


def test_active_route_rotation_preserves_overlap_but_revocation_stops_old_route() -> None:
    routes = RouteKeys(
        {1: b"route-key-one-32-bytes-material", 2: b"route-key-two-32-bytes-material"},
        active_version=1,
        binding_key=b"distinct-route-binding-key-material",
    )
    old = routes.seal(7, 42, generation=3)
    routes.activate(2)
    assert routes.open(old, expected_bot_id=7) == (42, 3)
    routes.revoke(1)
    with pytest.raises(ValueError, match="revoked"):
        routes.open(old, expected_bot_id=7)
    current = routes.seal(7, 42, generation=4)
    assert routes.open(current, expected_bot_id=7) == (42, 4)


def test_app_resolves_existing_binding_during_identity_digest_key_overlap() -> None:
    store = MemoryStore()
    keys = IdentityDigestKeys({1: b"old-key-material", 2: b"new-key-material"}, active_version=1)
    service = HulaguApp(
        FakeTelegramAdapter(bot_id=7),
        store,
        pinned_bot_id=7,
        identity_keys=keys,
        callback_codec=CallbackCodec(b"callback-key"),
        clock=lambda: 100,
    )
    started = service.handle_update(
        {"update_id": 1, "message": {"message_id": 1, "from": {"id": 42}, "chat": {"id": 42, "type": "private"}, "text": "/start"}}
    )
    assert started.reply is not None and started.reply.callback_data is not None
    service.handle_update(
        {"update_id": 2, "callback_query": {"id": "consent", "from": {"id": 42}, "data": started.reply.callback_data, "message": {"message_id": 2, "chat": {"id": 42, "type": "private"}}}}
    )

    keys.activate(2)
    status = service.handle_update(
        {"update_id": 3, "message": {"message_id": 3, "from": {"id": 42}, "chat": {"id": 42, "type": "private"}, "text": "/status"}}
    )

    assert status.outcome == "status"
    assert len(store.tenants) == 1


def test_sender_refuses_a_revoked_encrypted_return_route_before_send() -> None:
    adapter = FakeTelegramAdapter(bot_id=7)
    routes = RouteKeys(
        {1: b"route-key-one-32-bytes-material", 2: b"route-key-two-32-bytes-material"},
        1,
        binding_key=b"distinct-route-binding-key-material",
    )
    old_route = routes.seal(7, 42, generation=3)
    routes.activate(2)
    routes.revoke(1)
    sender = TelegramSender(adapter, route_keys=routes, bot_id=7)

    result = sender.deliver(OutboxMessage("delivery-1", None, "run-1:event-1", "Ready", old_route))

    assert result.state is DeliveryState.FAILED
    assert adapter.sent_messages == []
