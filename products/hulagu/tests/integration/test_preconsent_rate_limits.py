from __future__ import annotations

import importlib.util
from pathlib import Path

from hulagu.app import HulaguApp, MemoryStore, PostgresStore, RateLimits
from hulagu.telegram.adapter import FakeTelegramAdapter
from hulagu.telegram.commands import CallbackCodec, IdentityDigestKeys

ROOT = Path(__file__).parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "hulagu_task3_rate_limit_pg_helpers",
    ROOT / "tests" / "e2e" / "test_start_and_resume.py",
)
assert _SPEC is not None and _SPEC.loader is not None
_HELPERS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HELPERS)
PsqlConnection = _HELPERS.PsqlConnection
postgres_cluster = _HELPERS.postgres_cluster
psql = _HELPERS.psql


def update(update_id: int, actor: int = 42) -> dict[str, object]:
    return {"update_id": update_id, "message": {"message_id": update_id, "from": {"id": actor}, "chat": {"id": actor, "type": "private"}, "text": "/start"}}


def test_unconsented_flood_is_bounded_without_tenant_jobs_or_outbox() -> None:
    store = MemoryStore()
    service = HulaguApp(FakeTelegramAdapter(bot_id=7), store, pinned_bot_id=7, identity_keys=IdentityDigestKeys({1: b"identity-key"}, 1), callback_codec=CallbackCodec(b"callback-key"), rate_limits=RateLimits(per_subject=2, global_updates=3, window_seconds=60), clock=lambda: 100)
    outcomes = [service.handle_update(update(i)).outcome for i in range(1, 6)]
    assert outcomes == ["enrollment_started", "enrollment_resumed", "rate_limited", "rate_limited", "rate_limited"]
    assert len(store.enrollments) == 1
    assert store.tenants == {} and store.bindings == {} and store.jobs == [] and store.outbox == {}
    assert store.command_work_count == 2


def test_existing_tenant_lookup_never_implicitly_creates_tenant() -> None:
    store = MemoryStore()
    service = HulaguApp(FakeTelegramAdapter(bot_id=7), store, pinned_bot_id=7, identity_keys=IdentityDigestKeys({1: b"identity-key"}, 1), callback_codec=CallbackCodec(b"callback-key"), clock=lambda: 100)
    result = service.handle_update({"update_id": 1, "message": {"message_id": 1, "from": {"id": 42}, "chat": {"id": 42, "type": "private"}, "text": "/status"}})
    assert result.outcome == "preconsent_command_rejected"
    assert store.tenants == {} and store.bindings == {}


def test_postgres_unconsented_flood_is_durably_bounded_without_tenant_or_outbox() -> None:
    with postgres_cluster() as dsn:
        connection = PsqlConnection(dsn)
        try:
            service = HulaguApp(
                FakeTelegramAdapter(bot_id=7),
                PostgresStore(connection, bot_id=7),
                pinned_bot_id=7,
                identity_keys=IdentityDigestKeys({1: b"identity-key"}, 1),
                callback_codec=CallbackCodec(b"callback-key"),
                rate_limits=RateLimits(per_subject=2, global_updates=3, window_seconds=60),
                clock=lambda: 100,
            )

            outcomes = [service.handle_update(update(index)).outcome for index in range(1, 6)]
        finally:
            connection.close()

        assert outcomes == [
            "enrollment_started",
            "enrollment_resumed",
            "rate_limited",
            "rate_limited",
            "rate_limited",
        ]
        assert psql(dsn, "SELECT count(*) FROM hulagu.enrollments").stdout.strip() == "1"
        assert psql(dsn, "SELECT count(*) FROM hulagu.tenants").stdout.strip() == "0"
        assert psql(dsn, "SELECT count(*) FROM hulagu.outbox_messages").stdout.strip() == "0"
