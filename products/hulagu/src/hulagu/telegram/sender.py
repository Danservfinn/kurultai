"""At-least-once Telegram outbox delivery semantics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from .adapter import AmbiguousDeliveryError, TelegramAdapter
from .commands import RouteKeys, SealedRoute


class DeliveryState(str, Enum):
    DELIVERED = "delivered"
    FAILED = "failed"
    DELIVERY_UNKNOWN = "delivery_unknown"


@dataclass(frozen=True, slots=True)
class OutboxMessage:
    delivery_id: str
    chat_id: int | None
    event_id: str
    text: str
    sealed_route: SealedRoute | None = None
    transport_key: str | None = None


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    state: DeliveryState
    attempts: int


class DeliveryRecorder(Protocol):
    def record_delivery(self, delivery_id: str, state: DeliveryState, attempts: int) -> None: ...


@dataclass(frozen=True, slots=True)
class OutboxClaim:
    message: OutboxMessage
    delivery_key: str
    attempt: int
    lifecycle_epoch: int
    work_epoch: int
    lease_token_hash: str


class DurableOutboxStore(Protocol):
    def claim(self, *, batch: int, lease_seconds: int) -> list[OutboxClaim]: ...

    def record(self, claim: OutboxClaim, state: DeliveryState, error_class: str | None) -> str: ...


@dataclass(frozen=True, slots=True)
class RuntimeDelivery:
    delivery_key: str
    delivery: DeliveryResult
    record_outcome: str


class TelegramSender:
    def __init__(
        self,
        adapter: TelegramAdapter,
        *,
        max_attempts: int = 3,
        route_keys: RouteKeys | None = None,
        bot_id: int | None = None,
        recorder: DeliveryRecorder | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max attempts must be positive")
        if (route_keys is None) != (bot_id is None):
            raise ValueError("route keys and bot identity must be configured together")
        self._adapter = adapter
        self._max_attempts = max_attempts
        self._route_keys = route_keys
        self._bot_id = bot_id
        self._recorder = recorder
        self._attempts: dict[str, int] = {}
        self.duplicate_risk_count = 0

    def _result(self, delivery_id: str, state: DeliveryState, attempts: int) -> DeliveryResult:
        if self._recorder is not None:
            self._recorder.record_delivery(delivery_id, state, attempts)
        return DeliveryResult(state, attempts)

    def deliver(self, message: OutboxMessage) -> DeliveryResult:
        attempts = self._attempts.get(message.delivery_id, 0)
        if attempts >= self._max_attempts:
            return self._result(message.delivery_id, DeliveryState.FAILED, attempts)
        attempts += 1
        self._attempts[message.delivery_id] = attempts
        return self._deliver_attempt(message, attempts)

    def deliver_claimed(self, message: OutboxMessage, *, attempt: int) -> DeliveryResult:
        if attempt < 1:
            raise ValueError("claimed attempt must be positive")
        return self._deliver_attempt(message, attempt)

    def _deliver_attempt(self, message: OutboxMessage, attempts: int) -> DeliveryResult:
        chat_id = message.chat_id
        if message.sealed_route is not None:
            if self._route_keys is None or self._bot_id is None:
                return self._result(message.delivery_id, DeliveryState.FAILED, attempts)
            try:
                chat_id, _generation = self._route_keys.open(message.sealed_route, expected_bot_id=self._bot_id)
            except ValueError:
                return self._result(message.delivery_id, DeliveryState.FAILED, attempts)
        if chat_id is None:
            return self._result(message.delivery_id, DeliveryState.FAILED, attempts)
        rendered = f"[{message.event_id}] {message.text}"
        transport_key = message.transport_key or message.event_id
        try:
            self._adapter.send_message(chat_id, rendered, transport_key)
        except AmbiguousDeliveryError:
            self.duplicate_risk_count += 1
            return self._result(message.delivery_id, DeliveryState.DELIVERY_UNKNOWN, attempts)
        except RuntimeError:
            return self._result(message.delivery_id, DeliveryState.FAILED, attempts)
        return self._result(message.delivery_id, DeliveryState.DELIVERED, attempts)


class TelegramOutboxRuntime:
    """Claim, send, and durably record one bounded batch without claiming network exactly-once."""

    def __init__(self, sender: TelegramSender, store: DurableOutboxStore) -> None:
        self._sender = sender
        self._store = store

    def deliver_once(self, *, batch: int = 10, lease_seconds: int = 60) -> list[RuntimeDelivery]:
        completed: list[RuntimeDelivery] = []
        for claim in self._store.claim(batch=batch, lease_seconds=lease_seconds):
            delivery = self._sender.deliver_claimed(claim.message, attempt=claim.attempt)
            error_class = {
                DeliveryState.DELIVERED: None,
                DeliveryState.FAILED: "telegram_transport_failure",
                DeliveryState.DELIVERY_UNKNOWN: "telegram_delivery_unknown",
            }[delivery.state]
            recorded = self._store.record(claim, delivery.state, error_class)
            completed.append(RuntimeDelivery(claim.delivery_key, delivery, recorded))
        return completed
