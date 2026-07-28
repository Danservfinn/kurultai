from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from hulagu.app import HulaguApp, MemoryStore, PostgresStore
from hulagu.telegram.adapter import FakeTelegramAdapter
from hulagu.telegram.commands import CallbackAction, CallbackCodec, IdentityDigestKeys

ROOT = Path(__file__).parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "hulagu_task3_e2e_helpers",
    ROOT / "tests" / "e2e" / "test_start_and_resume.py",
)
assert _SPEC is not None and _SPEC.loader is not None
_HELPERS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HELPERS)
PsqlConnection = _HELPERS.PsqlConnection
postgres_cluster = _HELPERS.postgres_cluster
psql = _HELPERS.psql
pg_app = _HELPERS.pg_app


def start(update_id: int = 1) -> dict[str, object]:
    return {"update_id": update_id, "message": {"message_id": 1, "from": {"id": 42}, "chat": {"id": 42, "type": "private"}, "text": "/start"}}


def make_app(adapter: FakeTelegramAdapter, store: MemoryStore) -> HulaguApp:
    return HulaguApp(adapter, store, pinned_bot_id=7, identity_keys=IdentityDigestKeys({1: b"identity-key"}, 1), callback_codec=CallbackCodec(b"callback-key"), clock=lambda: 100)


def test_update_and_callback_replays_have_no_duplicate_effects() -> None:
    store = MemoryStore()
    service = make_app(FakeTelegramAdapter(bot_id=7), store)
    first = service.handle_update(start())
    replay = service.handle_update(start())
    assert first.outcome == "enrollment_started"
    assert replay.outcome == "duplicate_update"
    assert len(store.enrollments) == 1
    token = first.reply
    assert token is not None and token.callback_data is not None
    callback = {"update_id": 2, "callback_query": {"id": "cb-1", "from": {"id": 42}, "data": token.callback_data, "message": {"message_id": 1, "chat": {"id": 42, "type": "private"}}}}
    service.handle_update(callback)
    callback["update_id"] = 3
    assert service.handle_update(callback).outcome == "duplicate_callback"
    assert len(store.tenants) == 1 and len(store.outbox) == 1


def test_commit_failure_keeps_prior_offset_and_replay_is_harmless() -> None:
    adapter = FakeTelegramAdapter(bot_id=7, updates=[start(5)])
    store = MemoryStore(offset=5)
    service = make_app(adapter, store)
    service.start()
    store.fail_next_commit = True
    with pytest.raises(RuntimeError, match="commit"):
        service.poll_once()
    assert store.offset == 5 and store.enrollments == {}
    assert service.poll_once() == 1
    assert store.offset == 6 and len(store.enrollments) == 1
    assert adapter.requested_offsets == [5, 5]


def test_postgres_duplicate_update_does_not_mutate_enrollment_rate_state() -> None:
    with postgres_cluster() as dsn:
        connection = PsqlConnection(dsn)
        try:
            service = pg_app(connection)
            assert service.handle_update(start(20)).outcome == "enrollment_started"
            initial_rate_count = psql(dsn, "SELECT rate_count FROM hulagu.enrollments").stdout.strip()
            assert service.handle_update(start(20)).outcome == "duplicate_update"
        finally:
            connection.close()

        assert psql(dsn, "SELECT rate_count FROM hulagu.enrollments").stdout.strip() == initial_rate_count
        assert psql(dsn, "SELECT count(*) FROM hulagu.inbound_updates").stdout.strip() == "1"
        assert psql(dsn, "SELECT hulagu_api.telegram_polling_offset(7)", user="hulagu_app").stdout.strip() == "21"


def test_postgres_commit_failure_keeps_offset_and_state_for_replay() -> None:
    with postgres_cluster() as dsn:
        connection = PsqlConnection(dsn)
        original_commit = connection.commit

        def fail_commit() -> None:
            connection.rollback()
            raise RuntimeError("injected commit failure")

        try:
            connection.commit = fail_commit
            service = HulaguApp(
                FakeTelegramAdapter(bot_id=7),
                PostgresStore(connection, bot_id=7),
                pinned_bot_id=7,
                identity_keys=IdentityDigestKeys({1: b"identity-key"}, 1),
                callback_codec=CallbackCodec(b"callback-key"),
                clock=lambda: 100,
            )
            with pytest.raises(RuntimeError, match="commit"):
                service.handle_update(start(30))
            assert psql(dsn, "SELECT hulagu_api.telegram_polling_offset(7)", user="hulagu_app").stdout.strip() == "0"
            assert psql(dsn, "SELECT count(*) FROM hulagu.enrollments").stdout.strip() == "0"

            connection.commit = original_commit
            assert service.handle_update(start(30)).outcome == "enrollment_started"
        finally:
            connection.close()

        assert psql(dsn, "SELECT hulagu_api.telegram_polling_offset(7)", user="hulagu_app").stdout.strip() == "31"
        assert psql(dsn, "SELECT count(*) FROM hulagu.enrollments").stdout.strip() == "1"


def test_postgres_poller_terminally_dedupes_rejected_principals_and_invalid_callbacks() -> None:
    rejected_updates: list[dict[str, object]] = [
        {
            "update_id": 2,
            "callback_query": {
                "id": "tampered-callback",
                "from": {"id": 42},
                "data": "v1.tampered.signature",
                "message": {"message_id": 2, "chat": {"id": 42, "type": "private"}},
            },
        },
        {
            "update_id": 3,
            "message": {
                "message_id": 3,
                "from": {"id": 42},
                "chat": {"id": -100, "type": "group"},
                "text": "/start",
            },
        },
        {
            "update_id": 4,
            "message": {
                "message_id": 4,
                "from": {"id": 42},
                "chat": {"id": 43, "type": "private"},
                "text": "/start",
            },
        },
        {
            "update_id": 5,
            "message": {"message_id": 5, "chat": {"id": 42, "type": "private"}, "text": "/start"},
        },
        {
            "update_id": 6,
            "message": {
                "message_id": 6,
                "from": {"id": 42},
                "chat": {"id": 42, "type": "private"},
                "forward_origin": {"type": "user"},
                "text": "/start",
            },
        },
    ]
    with postgres_cluster() as dsn:
        connection = PsqlConnection(dsn)
        try:
            assert pg_app(connection).handle_update(start(1)).outcome == "enrollment_started"
            adapter = FakeTelegramAdapter(bot_id=7, updates=rejected_updates)
            service = HulaguApp(
                adapter,
                PostgresStore(connection, bot_id=7),
                pinned_bot_id=7,
                identity_keys=IdentityDigestKeys({1: b"identity-key"}, 1),
                callback_codec=CallbackCodec(b"callback-key"),
                clock=lambda: 100,
            )
            service.start()
            assert service.poll_once() == len(rejected_updates)
            assert service.poll_once() == 0
        finally:
            connection.close()

        assert psql(dsn, "SELECT count(*) FROM hulagu.inbound_updates").stdout.strip() == "6"
        assert psql(
            dsn,
            "SELECT string_agg(update_id::text || ':' || outcome_class, ',' ORDER BY update_id) "
            "FROM hulagu.inbound_updates WHERE update_id >= 2",
        ).stdout.strip() == "2:terminal_dedupe,3:terminal_dedupe,4:terminal_dedupe,5:terminal_dedupe,6:terminal_dedupe"
        assert psql(dsn, "SELECT hulagu_api.telegram_polling_offset(7)", user="hulagu_app").stdout.strip() == "7"


def test_invalid_callback_classes_never_reach_tenant_resolution_and_replay_durably() -> None:
    codec = CallbackCodec(b"callback-key")
    consent = CallbackAction("consent", "00000000-0000-4000-8000-000000000001", "nonce", 42, 200)
    valid_token = codec.issue(consent)
    invalid_callbacks: list[tuple[str, str | None]] = [
        ("missing", None),
        ("invalid", "not-a-callback"),
        ("tampered", valid_token[:-1] + ("A" if valid_token[-1] != "A" else "B")),
        ("expired", codec.issue(CallbackAction("consent", consent.enrollment_id, "nonce", 42, 99))),
        ("wrong-actor", codec.issue(CallbackAction("consent", consent.enrollment_id, "nonce", 99, 200))),
        ("wrong-action", codec.issue(CallbackAction("decline", consent.enrollment_id, "nonce", 42, 200))),
    ]
    updates: list[dict[str, object]] = []
    for update_id, (callback_id, callback_data) in enumerate(invalid_callbacks, start=40):
        callback: dict[str, object] = {
            "id": callback_id,
            "from": {"id": 42},
            "message": {"message_id": update_id, "chat": {"id": 42, "type": "private"}},
        }
        if callback_data is not None:
            callback["data"] = callback_data
        updates.append({"update_id": update_id, "callback_query": callback})

    with postgres_cluster() as dsn:
        def poll_with_denied_resolution() -> tuple[int, list[int]]:
            connection = PsqlConnection(dsn)
            adapter = FakeTelegramAdapter(bot_id=7, updates=updates)
            store = PostgresStore(connection, bot_id=7)

            def deny_resolution(subject_digest: str) -> None:
                raise AssertionError(f"tenant resolution reached for invalid callback: {subject_digest}")

            store.resolve_existing_tenant = deny_resolution  # type: ignore[method-assign]
            try:
                service = HulaguApp(
                    adapter,
                    store,
                    pinned_bot_id=7,
                    identity_keys=IdentityDigestKeys({1: b"identity-key"}, 1),
                    callback_codec=codec,
                    clock=lambda: 100,
                )
                service.start()
                return service.poll_once(), adapter.requested_offsets
            finally:
                connection.close()

        assert poll_with_denied_resolution() == (6, [0])
        assert psql(
            dsn,
            "SELECT string_agg(update_id::text || ':' || outcome_class, ',' ORDER BY update_id) "
            "FROM hulagu.inbound_updates",
        ).stdout.strip() == ",".join(f"{update_id}:terminal_dedupe" for update_id in range(40, 46))
        assert psql(dsn, "SELECT hulagu_api.telegram_polling_offset(7)", user="hulagu_app").stdout.strip() == "46"

        assert poll_with_denied_resolution() == (0, [46])

        psql(dsn, "UPDATE hulagu.telegram_polling_offsets SET next_update_id=40 WHERE bot_id=7")
        assert poll_with_denied_resolution() == (6, [40])
        assert psql(dsn, "SELECT count(*) FROM hulagu.inbound_updates").stdout.strip() == "6"
        assert psql(dsn, "SELECT hulagu_api.telegram_polling_offset(7)", user="hulagu_app").stdout.strip() == "46"
