from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Self
from uuid import uuid4

import pytest

from hulagu.deletion_app import (
    DeletionDispatcher,
    FixedCompletionRequest,
    MemoryDeletionDeliveryStore,
    PostgresDeletionDeliveryStore,
    RouteBindingRecord,
    RouteBindingValidator,
    RouteEnvelopeKeys,
    UnixDeletionCompletionClient,
    UnixDeletionCompletionServer,
    route_binding_digest,
)

ROOT = Path(__file__).parents[2]
_SPEC = importlib.util.spec_from_file_location("hulagu_deletion_pg_helpers", ROOT / "tests" / "integration" / "test_migrations.py")
assert _SPEC is not None and _SPEC.loader is not None
_HELPERS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HELPERS)
postgres_cluster = _HELPERS.postgres_cluster
psql = _HELPERS.psql
seed_deletion_tenant = _HELPERS._seed_single_use_deletion_tenant


def test_deletion_dispatcher_module_has_executable_main_entrypoint() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "hulagu.deletion_app", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0
    assert "hulagu-deletion-dispatcher" in completed.stdout
    assert "--postgres-dsn-file" in completed.stdout
    assert "--deletion-key-file" in completed.stdout
    assert "--app-socket" in completed.stdout


class FakeCursor:
    def __init__(self, executed: list[tuple[str, tuple[object, ...]]], projection: str, role: str) -> None:
        self._executed = executed
        self._projection = projection
        self._role = role
        self._last_sql = ""

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_error: object) -> None:
        return None

    def execute(self, sql: str, parameters: tuple[object, ...] = ()) -> None:
        self._last_sql = sql
        self._executed.append((sql, parameters))

    def fetchone(self) -> tuple[object, ...]:
        if self._last_sql == "SELECT current_user":
            return (self._role,)
        if "deletion_delivery_outcome" in self._last_sql:
            return (None,)
        if "claim_deletion_delivery" in self._last_sql:
            return (json.dumps({"status": "claimed", "encrypted_route": self._projection}),)
        if "complete_deletion_delivery" in self._last_sql:
            return ("delivered",)
        raise AssertionError(f"unexpected SQL: {self._last_sql}")


class FakeConnection:
    def __init__(self, executed: list[tuple[str, tuple[object, ...]]], projection: str, role: str) -> None:
        self._executed = executed
        self._projection = projection
        self._role = role

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_error: object) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return FakeCursor(self._executed, self._projection, self._role)


def test_postgres_delivery_adapter_uses_only_narrow_role_functions_and_deletion_projection() -> None:
    deletion_id = "92000000-0000-4000-8000-000000000002"
    issuer = RouteEnvelopeKeys.for_issuer(active_keys={1: b"a" * 32}, deletion_keys={2: b"d" * 32})
    projection = issuer.seal(
        12345,
        generation=4,
        bot_id=777,
        active_key_version=1,
        deletion_key_version=2,
    ).deletion_projection()
    executed: list[tuple[str, tuple[object, ...]]] = []
    store = PostgresDeletionDeliveryStore(
        "host=/synthetic/postgres user=hulagu_deletion dbname=hulagu",
        connect=lambda _dsn: FakeConnection(executed, projection, "hulagu_deletion"),
        token_source=lambda _deletion_id: b"t" * 32,
    )

    assert store.claim(deletion_id, now=0) == projection
    assert store.finalize(deletion_id, "delivered") == "delivered"
    sql = [statement for statement, _parameters in executed]
    assert sql == [
        "SELECT current_user",
        "SELECT hulagu_api.claim_deletion_delivery(%s::uuid,%s)",
        "SELECT current_user",
        "SELECT hulagu_api.deletion_delivery_outcome(%s::uuid)",
        "SELECT current_user",
        "SELECT hulagu_api.complete_deletion_delivery(%s::uuid,%s,%s)",
    ]
    assert all("tenants" not in statement and "active_route" not in statement for statement in sql)


def test_actual_unix_socket_authenticates_peer_and_app_validates_binding_hmac(tmp_path: Path) -> None:
    deletion_id = "92000000-0000-4000-8000-000000000001"
    binding_key = b"app-side-binding-key-material"
    binding = RouteBindingRecord(
        bot_id=777,
        route_generation=4,
        key_version=2,
        binding_digest=route_binding_digest(binding_key, bot_id=777, route=12345, generation=4),
    )
    validator = RouteBindingValidator({2: binding_key}, lookup=lambda candidate: binding if candidate == deletion_id else None)
    sent: list[FixedCompletionRequest] = []
    socket_path = Path("/tmp") / f"hulagu-deletion-{uuid4().hex}.sock"
    server = UnixDeletionCompletionServer(
        socket_path,
        allowed_peer_uids={os.getuid()},
        validator=validator,
        send_fixed=sent.append,
    )
    server.bind()
    worker = threading.Thread(target=server.serve_once)
    worker.start()
    client = UnixDeletionCompletionClient(socket_path)
    valid = FixedCompletionRequest(deletion_id, 12345, 4, "deletion-complete-v1")
    assert client.send_deletion_completion(valid) == "sent"
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert sent == [valid]

    server.bind()
    worker = threading.Thread(target=server.serve_once)
    worker.start()
    substituted = FixedCompletionRequest(deletion_id, 99999, 4, "deletion-complete-v1")
    with pytest.raises(PermissionError, match="binding"):
        client.send_deletion_completion(substituted)
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert sent == [valid]
    server.close()


def test_dispatch_restart_reclaims_only_same_job_and_terminalizes_exactly_once() -> None:
    store = MemoryDeletionDeliveryStore()
    issuer = RouteEnvelopeKeys.for_issuer(active_keys={1: b"a" * 32}, deletion_keys={2: b"z" * 32})
    keys = RouteEnvelopeKeys.for_deletion({2: b"z" * 32})
    projection = issuer.seal(
        777,
        generation=2,
        bot_id=999,
        active_key_version=1,
        deletion_key_version=2,
    ).deletion_projection()
    store.enqueue("deletion-7", projection, expires_at=500)
    calls: list[str] = []

    def ambiguous(request: object) -> None:
        calls.append("sent")
        raise TimeoutError("synthetic ambiguous delivery")

    first = DeletionDispatcher(store, keys, ambiguous, clock=lambda: 100)
    assert first.dispatch("deletion-7") == "delivery_unknown"
    restarted = DeletionDispatcher(store, keys, ambiguous, clock=lambda: 101)
    assert restarted.dispatch("deletion-7") == "delivery_unknown"
    assert calls == ["sent"]
    assert store.outcome("deletion-7") == "delivery_unknown"


def test_expired_delivery_authority_has_no_send_effect() -> None:
    store = MemoryDeletionDeliveryStore()
    issuer = RouteEnvelopeKeys.for_issuer(active_keys={1: b"a" * 32}, deletion_keys={2: b"z" * 32})
    keys = RouteEnvelopeKeys.for_deletion({2: b"z" * 32})
    projection = issuer.seal(
        888,
        generation=2,
        bot_id=999,
        active_key_version=1,
        deletion_key_version=2,
    ).deletion_projection()
    store.enqueue("deletion-8", projection, expires_at=100)
    sent: list[object] = []
    assert DeletionDispatcher(store, keys, sent.append, clock=lambda: 101).dispatch("deletion-8") == "expired"
    assert sent == []


def test_postgres_restart_after_committed_claim_terminalizes_unknown_without_duplicate_send(tmp_path: Path) -> None:
    tenant_id = "92000000-0000-4000-8000-000000000003"
    nonce_hash = hashlib.sha256(b"adapter-restart-nonce").hexdigest()
    issuer = RouteEnvelopeKeys.for_issuer(active_keys={1: b"a" * 32}, deletion_keys={2: b"d" * 32})
    deletion_keys = RouteEnvelopeKeys.for_deletion({2: b"d" * 32})
    projection = issuer.seal(
        12345,
        generation=4,
        bot_id=777,
        active_key_version=1,
        deletion_key_version=2,
    ).deletion_projection()
    tenants_root = tmp_path / "tenants"
    tenant_root = tenants_root / tenant_id
    tenant_root.mkdir(parents=True)
    (tenant_root / "private.txt").write_text("synthetic private bytes")

    def deterministic_token(_deletion_id: str) -> bytes:
        return b"restart-safe-token-material"

    def connect_deletion(dsn: str) -> object:
        psycopg = importlib.import_module("psycopg")
        connection = psycopg.connect(dsn, autocommit=True)
        connection.execute("SET ROLE hulagu_deletion")
        return connection

    with postgres_cluster() as dsn:
        seed_deletion_tenant(dsn, tenant_id, epoch=3, nonce_hash=nonce_hash)
        deletion_id = psql(
            dsn,
            "BEGIN;"
            f"SET LOCAL app.tenant_id='{tenant_id}';"
            f"SELECT hulagu_api.request_deletion('{nonce_hash}','{projection}',repeat('c',64));"
            "COMMIT;",
            user="hulagu_app",
        ).stdout.strip()
        first_process = PostgresDeletionDeliveryStore(
            "host=/synthetic/postgres user=hulagu_deletion dbname=hulagu",
            connect=lambda _dsn: connect_deletion(dsn),
            tenants_root=tenants_root,
            token_source=deterministic_token,
        )
        assert first_process.claim(deletion_id, now=100) == projection
        assert not tenant_root.exists()

        sent: list[FixedCompletionRequest] = []
        restarted = PostgresDeletionDeliveryStore(
            "host=/synthetic/postgres user=hulagu_deletion dbname=hulagu",
            connect=lambda _dsn: connect_deletion(dsn),
            tenants_root=tenants_root,
            token_source=deterministic_token,
        )
        assert DeletionDispatcher(restarted, deletion_keys, sent.append, clock=lambda: 101).dispatch(deletion_id) == (
            "delivery_unknown"
        )
        assert sent == []
        assert restarted.outcome(deletion_id) == "delivery_unknown"
        assert psql(
            dsn,
            f"SELECT outcome FROM hulagu.deletion_receipts WHERE deletion_id='{deletion_id}'",
        ).stdout.strip() == "delivery_unknown"
