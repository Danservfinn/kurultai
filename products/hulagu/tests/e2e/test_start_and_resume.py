from __future__ import annotations

import importlib.util
import json
import subprocess
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Self

from hulagu.app import HulaguApp, MemoryStore, PostgresStore
from hulagu.telegram.adapter import FakeTelegramAdapter
from hulagu.telegram.commands import CallbackCodec, IdentityDigestKeys, RouteKeys


def raw(update_id: int, text: str) -> dict[str, object]:
    return {"update_id": update_id, "message": {"message_id": update_id, "from": {"id": 42}, "chat": {"id": 42, "type": "private"}, "text": text}}


def build(store: MemoryStore) -> HulaguApp:
    return HulaguApp(FakeTelegramAdapter(bot_id=7), store, pinned_bot_id=7, identity_keys=IdentityDigestKeys({1: b"identity-key"}, 1), callback_codec=CallbackCodec(b"callback-key"), clock=lambda: 100)


def test_forced_restart_status_resumes_from_durable_state() -> None:
    store = MemoryStore()
    first = build(store)
    enrollment = first.handle_update(raw(1, "/start"))
    assert enrollment.reply is not None and enrollment.reply.callback_data is not None
    callback = {"update_id": 2, "callback_query": {"id": "consent-1", "from": {"id": 42}, "data": enrollment.reply.callback_data, "message": {"message_id": 2, "chat": {"id": 42, "type": "private"}}}}
    first.handle_update(callback)
    restarted = build(store)
    status = restarted.handle_update(raw(3, "/status"))
    assert status.reply is not None
    assert status.reply.text == "Status: awaiting_cv"
    assert len(store.tenants) == 1


ROOT = Path(__file__).parents[2]
_SPEC = importlib.util.spec_from_file_location("hulagu_task3_pg_helpers", ROOT / "tests" / "integration" / "test_migrations.py")
assert _SPEC is not None and _SPEC.loader is not None
_HELPERS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HELPERS)
postgres_cluster = _HELPERS.postgres_cluster
psql = _HELPERS.psql


def _literal(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, datetime):
        value = value.isoformat()
    if isinstance(value, dict):
        return "'" + json.dumps(value, separators=(",", ":")).replace("'", "''") + "'::jsonb"
    return "'" + str(value).replace("'", "''") + "'"


class PsqlConnection:
    """Small DB-API-shaped test connection over one persistent local psql session."""

    def __init__(self, dsn: str) -> None:
        self._process = subprocess.Popen(
            ["/opt/homebrew/bin/psql", "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", f"{dsn}&user=hulagu_app"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert self._process.stdin is not None and self._process.stdout is not None and self._process.stderr is not None
        self._stdin = self._process.stdin
        self._stdout = self._process.stdout
        self._stderr = self._process.stderr
        self._row: tuple[object, ...] | None = None
        self._rows: list[tuple[object, ...]] = []

    def cursor(self) -> Self:
        return self

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def execute(self, statement: str, params: tuple[object, ...] | None = None) -> None:
        rendered = statement
        for value in params or ():
            rendered = rendered.replace("%s", _literal(value), 1)
        marker = "__hulagu_task3_done__"
        self._stdin.write(f"{rendered.rstrip(';')};\n\\echo {marker}\n")
        self._stdin.flush()
        rows: list[str] = []
        while True:
            raw_line = self._stdout.readline()
            if raw_line == "":
                raise RuntimeError(f"psql session ended: {self._stderr.read().strip()}")
            line = raw_line.rstrip("\n")
            if line == marker:
                break
            if line:
                rows.append(line)
        self._rows = [tuple(row.split("|")) for row in rows]
        self._row = None if not self._rows else self._rows[-1]

    def fetchone(self) -> tuple[object, ...] | None:
        return self._row

    def fetchall(self) -> list[tuple[object, ...]]:
        return list(self._rows)

    def commit(self) -> None:
        self.execute("COMMIT")

    def rollback(self) -> None:
        self.execute("ROLLBACK")

    def close(self) -> None:
        if self._process.poll() is None:
            self._stdin.write("\\q\n")
            self._stdin.flush()
        self._process.communicate(timeout=5)


def pg_app(connection: PsqlConnection) -> HulaguApp:
    return HulaguApp(
        FakeTelegramAdapter(bot_id=7),
        PostgresStore(connection, bot_id=7),
        pinned_bot_id=7,
        identity_keys=IdentityDigestKeys({1: b"identity-key"}, 1),
        callback_codec=CallbackCodec(b"callback-key"),
        route_keys=RouteKeys(
            {1: b"active-route-key-material"},
            1,
            binding_key=b"distinct-route-binding-key-material",
        ),
        clock=lambda: 100,
    )


def test_postgres_restart_drives_real_app_entrypoints_and_preserves_offset_state_and_outbox() -> None:
    with postgres_cluster() as dsn:
        first_connection = PsqlConnection(dsn)
        try:
            first = pg_app(first_connection)
            enrollment = first.handle_update(raw(1, "/start"))
            assert enrollment.reply is not None and enrollment.reply.callback_data is not None
            callback = {"update_id": 2, "callback_query": {"id": "consent-pg", "from": {"id": 42}, "data": enrollment.reply.callback_data, "message": {"message_id": 2, "chat": {"id": 42, "type": "private"}}}}
            assert first.handle_update(callback).outcome == "consent_promoted"
        finally:
            first_connection.close()

        restarted_connection = PsqlConnection(dsn)
        try:
            status = pg_app(restarted_connection).handle_update(raw(3, "/status"))
            assert status.reply is not None and status.reply.text == "Status: READY"
        finally:
            restarted_connection.close()

        assert psql(dsn, "SELECT count(*) FROM hulagu.tenants").stdout.strip() == "1"
        assert psql(dsn, "SELECT count(*) FROM hulagu.inbound_updates").stdout.strip() == "3"
        assert psql(dsn, "SELECT count(*) FROM hulagu.outbox_messages").stdout.strip() == "1"
        assert psql(dsn, "SELECT hulagu_api.telegram_polling_offset(7)", user="hulagu_app").stdout.strip() == "4"


def test_postgres_rejects_consumed_consent_token_presented_as_a_new_callback() -> None:
    with postgres_cluster() as dsn:
        connection = PsqlConnection(dsn)
        try:
            service = pg_app(connection)
            enrollment = service.handle_update(raw(10, "/start"))
            assert enrollment.reply is not None and enrollment.reply.callback_data is not None
            callback = {
                "update_id": 11,
                "callback_query": {
                    "id": "consent-original",
                    "from": {"id": 42},
                    "data": enrollment.reply.callback_data,
                    "message": {"message_id": 11, "chat": {"id": 42, "type": "private"}},
                },
            }
            service.handle_update(callback)
            callback["update_id"] = 12
            callback_query = callback["callback_query"]
            assert isinstance(callback_query, dict)
            callback_query["id"] = "consent-stale-new-id"

            assert service.handle_update(callback).outcome == "invalid_callback"
        finally:
            connection.close()

        assert psql(dsn, "SELECT count(*) FROM hulagu.tenants").stdout.strip() == "1"
        assert psql(dsn, "SELECT count(*) FROM hulagu.outbox_messages").stdout.strip() == "1"
