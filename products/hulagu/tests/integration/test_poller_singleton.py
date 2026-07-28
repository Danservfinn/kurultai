from __future__ import annotations

from types import TracebackType
from typing import Self

import pytest

from hulagu.app import HulaguApp, MemoryStore, PostgresAdvisoryLock
from hulagu.telegram.adapter import FakeTelegramAdapter
from hulagu.telegram.commands import CallbackCodec, IdentityDigestKeys


class LockConnection:
    def __init__(self, acquired: bool = True) -> None:
        self.acquired = acquired
        self.alive = True
        self.sql: list[tuple[str, tuple[object, ...] | None]] = []
        self._row: tuple[object, ...] | None = None
    def cursor(self) -> Self: return self
    def __enter__(self) -> Self: return self
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None
    def execute(self, sql: str, params: tuple[object, ...] | None = None) -> None:
        self.sql.append((sql, params))
        if "pg_try_advisory_lock" in sql: self._row = (self.acquired,)
        elif "SELECT 1" in sql:
            if not self.alive: raise RuntimeError("session lost")
            self._row = (1,)
    def fetchone(self) -> tuple[object, ...] | None: return self._row
    def fetchall(self) -> list[tuple[object, ...]]: return []
    def commit(self) -> None: pass
    def rollback(self) -> None: pass


def service(adapter: FakeTelegramAdapter, store: MemoryStore, lock: PostgresAdvisoryLock) -> HulaguApp:
    return HulaguApp(adapter, store, pinned_bot_id=7, identity_keys=IdentityDigestKeys({1: b"identity-key"}, 1), callback_codec=CallbackCodec(b"callback-key"), singleton_lock=lock, clock=lambda: 100)


def test_wrong_bot_and_configured_webhook_fail_closed_before_polling() -> None:
    with pytest.raises(RuntimeError, match="identity"):
        service(FakeTelegramAdapter(bot_id=8), MemoryStore(), PostgresAdvisoryLock(LockConnection())).start()
    with pytest.raises(RuntimeError, match="webhook"):
        service(FakeTelegramAdapter(bot_id=7, webhook_url="https://configured.invalid/hook"), MemoryStore(), PostgresAdvisoryLock(LockConnection())).start()


def test_second_poller_refuses_same_bot_advisory_lock() -> None:
    first = LockConnection(acquired=True)
    second = LockConnection(acquired=False)
    service(FakeTelegramAdapter(bot_id=7), MemoryStore(), PostgresAdvisoryLock(first)).start()
    with pytest.raises(RuntimeError, match="singleton"):
        service(FakeTelegramAdapter(bot_id=7), MemoryStore(), PostgresAdvisoryLock(second)).start()
    assert first.sql[0][1] == second.sql[0][1] == (7,)


def test_lock_session_loss_stops_before_another_fetch() -> None:
    connection = LockConnection()
    adapter = FakeTelegramAdapter(bot_id=7)
    poller = service(adapter, MemoryStore(), PostgresAdvisoryLock(connection))
    poller.start()
    connection.alive = False
    with pytest.raises(RuntimeError, match="session lost"):
        poller.poll_once()
    assert adapter.requested_offsets == []
