from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Self

import pytest

from hulagu.persistence.db import RuntimeRole, runtime_dsn, tenant_transaction
from hulagu.persistence.rls import TenantPrincipal


class FakeCursor(AbstractContextManager["FakeCursor"]):
    def __init__(self, events: list[tuple[str, tuple[Any, ...] | None]]) -> None:
        self.events = events

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, statement: str, params: tuple[Any, ...] | None = None) -> None:
        self.events.append((statement, params))


class FakeConnection:
    def __init__(self) -> None:
        self.events: list[tuple[str, tuple[Any, ...] | None]] = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.events)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def principal(value: str = "00000000-0000-4000-8000-000000000001") -> TenantPrincipal:
    return TenantPrincipal.from_identity_resolution(value, "telegram-customer")


def test_context_is_transaction_local_parameterized_and_committed() -> None:
    connection = FakeConnection()
    with tenant_transaction(connection, principal(), correlation_id="corr-1"):
        pass
    statements = [event[0] for event in connection.events]
    assert statements == [
        "BEGIN",
        "SET LOCAL app.tenant_id = %s",
        "SET LOCAL app.actor = %s",
        "SET LOCAL app.correlation_id = %s",
    ]
    assert connection.commits == 1
    assert connection.rollbacks == 0


def test_failed_transaction_rolls_back_so_pool_context_cannot_leak() -> None:
    connection = FakeConnection()
    with pytest.raises(RuntimeError, match="boom"), tenant_transaction(
        connection, principal(), correlation_id="corr-2"
    ):
        raise RuntimeError("boom")
    assert connection.commits == 0
    assert connection.rollbacks == 1


@pytest.mark.parametrize(
    ("role", "expected_user"),
    [
        (RuntimeRole.APP, "hulagu_app"),
        (RuntimeRole.RUNNER, "hulagu_runner"),
        (RuntimeRole.DELETION, "hulagu_deletion"),
    ],
)
def test_runtime_dsn_requires_its_separated_role(role: RuntimeRole, expected_user: str) -> None:
    dsn = f"postgresql://{expected_user}@localhost/hulagu"
    assert runtime_dsn(dsn, role) == dsn
    with pytest.raises(ValueError, match="runtime DSN role mismatch"):
        runtime_dsn("postgresql://hulagu_migrator@localhost/hulagu", role)
