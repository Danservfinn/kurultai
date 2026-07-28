"""Typed transaction boundary for transaction-local PostgreSQL tenant context."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from enum import Enum
from types import TracebackType
from typing import Any, Protocol, Self
from urllib.parse import parse_qs, urlsplit

from .rls import TenantPrincipal


class CursorProtocol(Protocol):
    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def execute(self, statement: str, params: tuple[Any, ...] | None = None) -> None: ...

    def fetchone(self) -> tuple[Any, ...] | None: ...

    def fetchall(self) -> list[tuple[Any, ...]]: ...


class ConnectionProtocol(Protocol):
    def cursor(self) -> CursorProtocol: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class RuntimeRole(Enum):
    APP = "hulagu_app"
    RUNNER = "hulagu_runner"
    DELETION = "hulagu_deletion"


def runtime_dsn(dsn: str, role: RuntimeRole) -> str:
    """Reject owner/migrator credentials at every runtime composition boundary."""

    parsed = urlsplit(dsn)
    query_user = parse_qs(parsed.query).get("user", [None])[0]
    actual_user = parsed.username or query_user
    if actual_user != role.value:
        raise ValueError("runtime DSN role mismatch")
    return dsn


@contextmanager
def tenant_transaction(
    connection: ConnectionProtocol,
    principal: TenantPrincipal,
    *,
    correlation_id: str,
) -> Iterator[ConnectionProtocol]:
    """Install context with SET LOCAL and guarantee commit-or-rollback cleanup."""

    if not correlation_id or len(correlation_id) > 128:
        raise ValueError("invalid correlation id")
    try:
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
            cursor.execute("SET LOCAL app.tenant_id = %s", (str(principal.tenant_id),))
            cursor.execute("SET LOCAL app.actor = %s", (principal.actor,))
            cursor.execute("SET LOCAL app.correlation_id = %s", (correlation_id,))
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
