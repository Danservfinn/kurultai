from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, cast

from hulagu.app import HulaguApp, PostgresStore
from hulagu.persistence.outbox import PostgresOutboxStore
from hulagu.persistence.rls import TenantPrincipal
from hulagu.telegram.adapter import FakeTelegramAdapter
from hulagu.telegram.commands import CallbackCodec, IdentityDigestKeys, RouteKeys
from hulagu.telegram.sender import DeliveryState, TelegramOutboxRuntime, TelegramSender

ROOT = Path(__file__).parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "hulagu_task3_outbox_pg_helpers",
    ROOT / "tests" / "e2e" / "test_start_and_resume.py",
)
assert _SPEC is not None and _SPEC.loader is not None
_HELPERS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HELPERS)
PsqlConnection = _HELPERS.PsqlConnection
postgres_cluster = _HELPERS.postgres_cluster
psql = _HELPERS.psql


def _route_keys() -> RouteKeys:
    return RouteKeys(
        {1: b"active-route-key-one-material", 2: b"active-route-key-two-material"},
        active_version=1,
        binding_key=b"distinct-route-binding-key-material",
    )


def _route_payload(routes: RouteKeys, *, event_id: str, text: str) -> str:
    return json.dumps(
        {
            "event_id": event_id,
            "text": text,
            "sealed_route": routes.seal(7, 42, generation=1).as_dict(),
        },
        separators=(",", ":"),
    )


def _message(update_id: int, actor_id: int, text: str = "/start") -> dict[str, object]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "from": {"id": actor_id},
            "chat": {"id": actor_id, "type": "private"},
            "text": text,
        },
    }


def _enroll_and_promote(
    dsn: str,
    connection: Any,
    routes: RouteKeys,
    *,
    actor_id: int,
    update_id: int,
) -> str:
    identity_keys = IdentityDigestKeys({1: b"identity-key"}, 1)
    service = HulaguApp(
        FakeTelegramAdapter(bot_id=7),
        PostgresStore(connection, bot_id=7),
        pinned_bot_id=7,
        identity_keys=identity_keys,
        callback_codec=CallbackCodec(b"callback-key"),
        route_keys=routes,
        clock=lambda: 100,
    )
    enrollment = service.handle_update(_message(update_id, actor_id))
    assert enrollment.reply is not None and enrollment.reply.callback_data is not None
    callback = {
        "update_id": update_id + 1,
        "callback_query": {
            "id": f"consent-{actor_id}",
            "from": {"id": actor_id},
            "data": enrollment.reply.callback_data,
            "message": {
                "message_id": update_id + 1,
                "chat": {"id": actor_id, "type": "private"},
            },
        },
    }
    assert service.handle_update(callback).outcome == "consent_promoted"
    return cast(
        str,
        psql(
            dsn,
            "SELECT tenant_id FROM hulagu.identity_bindings "
            f"WHERE subject_digest='{identity_keys.digest(7, actor_id).value}'",
        ).stdout.strip(),
    )


class OutcomeAdapter(FakeTelegramAdapter):
    def __init__(self) -> None:
        super().__init__(bot_id=7, ambiguous_delivery_keys={"stable:unknown"})

    def send_message(self, chat_id: int, text: str, delivery_key: str) -> None:
        if delivery_key == "stable:failed":
            raise RuntimeError("synthetic transport failure")
        super().send_message(chat_id, text, delivery_key)


def test_runtime_durably_records_outcomes_retries_and_stable_keys_across_restart() -> None:
    tenant_id = "71000000-0000-4000-8000-000000000021"
    routes = _route_keys()
    delivered_payload = _route_payload(routes, event_id="event-delivered", text="Ready")
    failed_payload = _route_payload(routes, event_id="event-failed", text="Retry")
    unknown_payload = _route_payload(routes, event_id="event-unknown", text="Maybe")
    with postgres_cluster() as dsn:
        psql(
            dsn,
            f"INSERT INTO hulagu.tenants(id,state,lifecycle_epoch) VALUES('{tenant_id}','READY',4);"
            "INSERT INTO hulagu.outbox_messages("
            "tenant_id,kind,payload,lifecycle_epoch,work_epoch,state,delivery_key,max_attempts"
            ") VALUES "
            f"('{tenant_id}','ordinary','{delivered_payload}',4,0,'pending','stable:delivered',2),"
            f"('{tenant_id}','ordinary','{failed_payload}',4,0,'pending','stable:failed',2),"
            f"('{tenant_id}','ordinary','{unknown_payload}',4,0,'pending','stable:unknown',2);",
        )
        principal = TenantPrincipal.from_identity_resolution(tenant_id, "telegram-customer")
        adapter = OutcomeAdapter()

        first_connection = PsqlConnection(dsn)
        try:
            first = TelegramOutboxRuntime(
                TelegramSender(adapter, route_keys=routes, bot_id=7),
                PostgresOutboxStore(first_connection, principal),
            )
            first_results = first.deliver_once(batch=10)
        finally:
            first_connection.close()
        assert sorted(
            (item.delivery_key, item.delivery.state, item.record_outcome) for item in first_results
        ) == [
            ("stable:delivered", DeliveryState.DELIVERED, "delivered"),
            ("stable:failed", DeliveryState.FAILED, "failed"),
            ("stable:unknown", DeliveryState.DELIVERY_UNKNOWN, "delivery_unknown"),
        ]

        restarted_connection = PsqlConnection(dsn)
        try:
            restarted = TelegramOutboxRuntime(
                TelegramSender(adapter, route_keys=routes, bot_id=7),
                PostgresOutboxStore(restarted_connection, principal),
            )
            retry_results = restarted.deliver_once(batch=10)
            assert [(item.delivery.state, item.delivery.attempts, item.record_outcome) for item in retry_results] == [
                (DeliveryState.FAILED, 2, "failed"),
            ]
            assert restarted.deliver_once(batch=10) == []
        finally:
            restarted_connection.close()

        assert sorted(sent.delivery_key for sent in adapter.sent_messages) == ["stable:delivered", "stable:unknown"]
        assert psql(
            dsn,
            "SELECT delivery_key || ':' || state || ':' || attempt_count "
            "FROM hulagu.outbox_messages ORDER BY delivery_key",
        ).stdout.splitlines() == [
            "stable:delivered:delivered:1",
            "stable:failed:failed:2",
            "stable:unknown:delivery_unknown:1",
        ]


def test_runtime_recording_obeys_lifecycle_work_and_lease_fences() -> None:
    cases = [
        ("31", "UPDATE hulagu.tenants SET lifecycle_epoch=5 WHERE id='{tenant}'", "cancelled", "cancelled"),
        ("32", "UPDATE hulagu.outbox_messages SET work_epoch=1 WHERE tenant_id='{tenant}'", "rejected", "claimed"),
        (
            "33",
            "UPDATE hulagu.outbox_messages SET lease_expires_at=now()-interval '1 second' WHERE tenant_id='{tenant}'",
            "rejected",
            "claimed",
        ),
    ]
    with postgres_cluster() as dsn:
        for suffix, mutation_template, expected_record, expected_state in cases:
            tenant_id = f"71000000-0000-4000-8000-0000000000{suffix}"
            delivery_key = f"stable:fence:{suffix}"
            routes = _route_keys()
            payload = _route_payload(routes, event_id="fence", text="Fence")
            psql(
                dsn,
                f"INSERT INTO hulagu.tenants(id,state,lifecycle_epoch) VALUES('{tenant_id}','READY',4);"
                "INSERT INTO hulagu.outbox_messages("
                "tenant_id,kind,payload,lifecycle_epoch,work_epoch,state,delivery_key,max_attempts"
                ") VALUES "
                f"('{tenant_id}','ordinary','{payload}',"
                f"4,0,'pending','{delivery_key}',2);",
            )

            class FencingAdapter(FakeTelegramAdapter):
                def __init__(self, mutation: str, tenant: str) -> None:
                    super().__init__(bot_id=7)
                    self._mutation = mutation
                    self._tenant = tenant

                def send_message(self, chat_id: int, text: str, delivery_key: str) -> None:
                    psql(dsn, self._mutation.format(tenant=self._tenant))
                    super().send_message(chat_id, text, delivery_key)

            connection = PsqlConnection(dsn)
            try:
                principal = TenantPrincipal.from_identity_resolution(tenant_id, "telegram-customer")
                runtime = TelegramOutboxRuntime(
                    TelegramSender(
                        FencingAdapter(mutation_template, tenant_id),
                        route_keys=routes,
                        bot_id=7,
                    ),
                    PostgresOutboxStore(connection, principal),
                )
                result = runtime.deliver_once(batch=1)
            finally:
                connection.close()
            assert len(result) == 1
            assert result[0].record_outcome == expected_record
            assert psql(
                dsn,
                f"SELECT state FROM hulagu.outbox_messages WHERE tenant_id='{tenant_id}'",
            ).stdout.strip() == expected_state


def test_real_postgres_route_is_encrypted_supports_overlap_and_fails_after_revocation_or_deletion() -> None:
    routes = _route_keys()
    adapter = FakeTelegramAdapter(bot_id=7)
    with postgres_cluster() as dsn:
        connection = PsqlConnection(dsn)
        try:
            overlap_tenant = _enroll_and_promote(dsn, connection, routes, actor_id=42, update_id=1)
            stored_payload = psql(
                dsn,
                f"SELECT payload::text FROM hulagu.outbox_messages WHERE tenant_id='{overlap_tenant}'",
            ).stdout.strip()
            assert '"chat_id"' not in stored_payload
            assert '"sealed_route"' in stored_payload
            assert '"active_key_version": 1' in stored_payload

            routes.activate(2)
            overlap_runtime = TelegramOutboxRuntime(
                TelegramSender(adapter, route_keys=routes, bot_id=7),
                PostgresOutboxStore(
                    connection,
                    TenantPrincipal.from_identity_resolution(overlap_tenant, "telegram-customer"),
                ),
            )
            overlap_result = overlap_runtime.deliver_once(batch=1)
            assert len(overlap_result) == 1
            assert overlap_result[0].delivery.state is DeliveryState.DELIVERED
            assert adapter.sent_messages[-1].chat_id == 42

            revoked_tenant = _enroll_and_promote(dsn, connection, routes, actor_id=43, update_id=10)
            routes.revoke(2)
            revoked_runtime = TelegramOutboxRuntime(
                TelegramSender(adapter, route_keys=routes, bot_id=7),
                PostgresOutboxStore(
                    connection,
                    TenantPrincipal.from_identity_resolution(revoked_tenant, "telegram-customer"),
                ),
            )
            revoked_result = revoked_runtime.deliver_once(batch=1)
            assert len(revoked_result) == 1
            assert revoked_result[0].delivery.state is DeliveryState.FAILED
            assert [sent.chat_id for sent in adapter.sent_messages] == [42]

            routes.activate(1)
            deleted_tenant = _enroll_and_promote(dsn, connection, routes, actor_id=44, update_id=20)
            psql(dsn, f"UPDATE hulagu.tenants SET state='DELETING', lifecycle_epoch=lifecycle_epoch+1 WHERE id='{deleted_tenant}'")
            deleted_runtime = TelegramOutboxRuntime(
                TelegramSender(adapter, route_keys=routes, bot_id=7),
                PostgresOutboxStore(
                    connection,
                    TenantPrincipal.from_identity_resolution(deleted_tenant, "telegram-customer"),
                ),
            )
            assert deleted_runtime.deliver_once(batch=1) == []
            assert [sent.chat_id for sent in adapter.sent_messages] == [42]
            psql(
                dsn,
                f"DELETE FROM hulagu.inbound_updates WHERE tenant_id='{deleted_tenant}';"
                f"DELETE FROM hulagu.tenants WHERE id='{deleted_tenant}'",
            )
            assert psql(
                dsn,
                f"SELECT count(*) FROM hulagu.outbox_messages WHERE tenant_id='{deleted_tenant}'",
            ).stdout.strip() == "0"
        finally:
            connection.close()
