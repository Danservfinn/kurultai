"""Durable PostgreSQL authority adapter for bounded Telegram outbox delivery."""

from __future__ import annotations

import json
import secrets
from typing import cast

from ..telegram.commands import SealedRoute
from ..telegram.sender import DeliveryState, OutboxClaim, OutboxMessage
from .db import ConnectionProtocol, tenant_transaction
from .rls import TenantPrincipal


class PostgresOutboxStore:
    def __init__(self, connection: ConnectionProtocol, principal: TenantPrincipal) -> None:
        self._connection = connection
        self._principal = principal

    def claim(self, *, batch: int, lease_seconds: int) -> list[OutboxClaim]:
        lease_token_hash = secrets.token_hex(32)
        with tenant_transaction(
            self._connection,
            self._principal,
            correlation_id=f"telegram-outbox-claim:{lease_token_hash[:24]}",
        ), self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT outbox_id,delivery_key,kind,payload,attempt,lifecycle_epoch,work_epoch "
                "FROM hulagu_api.claim_outbox_delivery(%s,%s,%s)",
                (lease_token_hash, batch, lease_seconds),
            )
            rows = cursor.fetchall()
        claims: list[OutboxClaim] = []
        for row in rows:
            payload_value = row[3]
            payload = json.loads(payload_value) if isinstance(payload_value, str) else payload_value
            if not isinstance(payload, dict):
                raise TypeError("outbox payload is not an object")
            event_id = payload.get("event_id")
            text = payload.get("text")
            if (
                "chat_id" in payload
                or not isinstance(event_id, str)
                or not event_id
                or not isinstance(text, str)
                or not text
            ):
                raise RuntimeError("outbox payload is not sendable")
            try:
                sealed_route = SealedRoute.from_dict(payload.get("sealed_route"))
            except (TypeError, ValueError) as exc:
                raise RuntimeError("outbox payload has no valid encrypted route") from exc
            delivery_key = str(row[1])
            claims.append(
                OutboxClaim(
                    message=OutboxMessage(
                        delivery_id=str(row[0]),
                        chat_id=None,
                        event_id=event_id,
                        text=text,
                        sealed_route=sealed_route,
                        transport_key=delivery_key,
                    ),
                    delivery_key=delivery_key,
                    attempt=int(row[4]),
                    lifecycle_epoch=int(row[5]),
                    work_epoch=int(row[6]),
                    lease_token_hash=lease_token_hash,
                )
            )
        return claims

    def record(self, claim: OutboxClaim, state: DeliveryState, error_class: str | None) -> str:
        with tenant_transaction(
            self._connection,
            self._principal,
            correlation_id=f"telegram-outbox-record:{claim.lease_token_hash[:24]}",
        ), self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT hulagu_api.record_outbox_delivery(%s,%s,%s,%s,%s,%s,%s)",
                (
                    claim.message.delivery_id,
                    claim.attempt,
                    claim.lease_token_hash,
                    claim.lifecycle_epoch,
                    claim.work_epoch,
                    state.value,
                    error_class,
                ),
            )
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("outbox record authority returned no outcome")
        return cast(str, row[0])
