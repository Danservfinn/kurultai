"""Credential-free Task 3 composition root for durable Telegram ingress."""

from __future__ import annotations

import copy
import hashlib
import secrets
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from .persistence.db import ConnectionProtocol
from .persistence.identity import promote_consented_enrollment, resolve_existing_tenant
from .telegram.adapter import TelegramAdapter, TelegramContractError, TelegramUpdate, normalize_update
from .telegram.commands import CallbackAction, CallbackCodec, IdentityDigest, IdentityDigestKeys, RouteKeys
from .telegram.sender import OutboxMessage


@dataclass(frozen=True, slots=True)
class Reply:
    text: str
    callback_data: str | None = None


@dataclass(frozen=True, slots=True)
class ProcessResult:
    outcome: str
    reply: Reply | None = None


@dataclass(frozen=True, slots=True)
class RateLimits:
    per_subject: int = 30
    global_updates: int = 300
    window_seconds: int = 60


@dataclass(frozen=True, slots=True)
class Enrollment:
    enrollment_id: str
    subject: IdentityDigest
    nonce: str
    expires_at: int


@dataclass(frozen=True, slots=True)
class TenantRecord:
    tenant_id: str
    state: str


class SingletonLock(Protocol):
    def acquire(self, bot_id: int) -> bool: ...
    def assert_alive(self) -> None: ...
    def release(self) -> None: ...


class _LocalLock:
    def acquire(self, bot_id: int) -> bool:
        return True
    def assert_alive(self) -> None:
        return None
    def release(self) -> None:
        return None


class PostgresAdvisoryLock:
    """Bot-bound singleton held and monitored on one dedicated DB session."""

    def __init__(self, connection: ConnectionProtocol) -> None:
        self._connection = connection
        self._bot_id: int | None = None

    def acquire(self, bot_id: int) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", (bot_id,))
            row = cursor.fetchone()
        acquired = bool(row and row[0] is True)
        self._bot_id = bot_id if acquired else None
        return acquired

    def assert_alive(self) -> None:
        if self._bot_id is None:
            raise RuntimeError("singleton lock not held")
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            row = cursor.fetchone()
        if row != (1,):
            raise RuntimeError("advisory lock session lost")

    def release(self) -> None:
        if self._bot_id is None:
            return
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", (self._bot_id,))
        self._bot_id = None


class MemoryStore:
    """Transactional fake persistence used only by fake-server verification."""

    def __init__(self, *, offset: int = 0) -> None:
        self.offset = offset
        self.enrollments: dict[str, Enrollment] = {}
        self.tenants: dict[str, TenantRecord] = {}
        self.bindings: dict[str, str] = {}
        self.outbox: dict[str, OutboxMessage] = {}
        self.jobs: list[object] = []
        self.processed_updates: set[tuple[int, int]] = set()
        self.processed_callbacks: set[tuple[int, str]] = set()
        self.subject_rate: dict[str, list[int]] = {}
        self.global_rate: list[int] = []
        self.command_work_count = 0
        self.fail_next_commit = False

    @contextmanager
    def transaction(self) -> Iterator[MemoryStore]:
        fail_commit = self.fail_next_commit
        self.fail_next_commit = False
        snapshot = copy.deepcopy(self.__dict__)
        try:
            yield self
            if fail_commit:
                raise RuntimeError("injected commit failure")
        except BaseException:
            self.__dict__.clear()
            self.__dict__.update(snapshot)
            raise

    def resolve_existing_tenant(self, subject_digest: str) -> TenantRecord | None:
        tenant_id = self.bindings.get(subject_digest)
        return None if tenant_id is None else self.tenants.get(tenant_id)


class PostgresStore:
    """Runtime authority backed only by audited hulagu_app SECURITY DEFINER APIs."""

    def __init__(self, connection: ConnectionProtocol, *, bot_id: int) -> None:
        self.connection = connection
        self.bot_id = bot_id

    @contextmanager
    def transaction(self) -> Iterator[PostgresStore]:
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("BEGIN")
            yield self
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise

    @property
    def offset(self) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT hulagu_api.telegram_polling_offset(%s)", (self.bot_id,))
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("polling offset authority returned no value")
        return int(row[0])

    def resolve_existing_tenant(self, subject_digest: str) -> TenantRecord | None:
        principal = resolve_existing_tenant(self.connection, subject_digest=subject_digest)
        if principal is None:
            return None
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT state FROM hulagu.tenants WHERE id=%s", (str(principal.tenant_id),))
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("resolved tenant state is unavailable")
        return TenantRecord(str(principal.tenant_id), str(row[0]))

    def admit_enrollment(
        self,
        update: TelegramUpdate,
        subject: IdentityDigest,
        *,
        nonce: str,
        rate_limits: RateLimits,
    ) -> tuple[str, str | None]:
        nonce_hash = hashlib.sha256(nonce.encode()).hexdigest()
        fence = hashlib.sha256(f"hulagu.subject-fence.v1\0{subject.value}".encode()).hexdigest()
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT outcome, enrollment_id FROM hulagu_api.admit_telegram_enrollment_ingress("
                "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    self.bot_id,
                    update.update_id,
                    update.callback_query_id,
                    update.update_id + 1,
                    subject.value,
                    fence,
                    "telegram-consent-v1",
                    nonce_hash,
                    datetime.now(UTC) + timedelta(minutes=15),
                    datetime.now(UTC) + timedelta(days=1),
                    rate_limits.per_subject,
                    rate_limits.global_updates,
                    rate_limits.window_seconds,
                ),
            )
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("enrollment ingress authority returned no outcome")
        return str(row[0]), None if row[1] is None else str(row[1])

    def promote(self, enrollment_id: str, *, nonce: str) -> str:
        principal = promote_consented_enrollment(
            self.connection,
            enrollment_id=UUID(enrollment_id),
            notice_version="telegram-consent-v1",
            consent_nonce_hash=hashlib.sha256(nonce.encode()).hexdigest(),
        )
        return str(principal.tenant_id)

    def persist(
        self,
        update: TelegramUpdate,
        *,
        subject_digest: str | None,
        outcome: str,
        delivery_key: str | None = None,
        outbox_payload: dict[str, object] | None = None,
    ) -> str:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT hulagu_api.persist_telegram_ingress(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    self.bot_id,
                    update.update_id,
                    update.callback_query_id,
                    update.update_id + 1,
                    subject_digest,
                    outcome,
                    datetime.now(UTC) + timedelta(days=1),
                    delivery_key,
                    "ordinary" if delivery_key is not None else None,
                    outbox_payload,
                ),
            )
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("ingress authority returned no outcome")
        return str(row[0])

    def persist_terminal(self, *, update_id: int, callback_query_id: str | None) -> str:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT hulagu_api.persist_telegram_ingress(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    self.bot_id,
                    update_id,
                    callback_query_id,
                    update_id + 1,
                    None,
                    "terminal_dedupe",
                    datetime.now(UTC) + timedelta(days=1),
                    None,
                    None,
                    None,
                ),
            )
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("terminal ingress authority returned no outcome")
        return str(row[0])


class HulaguApp:
    def __init__(self, adapter: TelegramAdapter, store: MemoryStore | PostgresStore, *, pinned_bot_id: int, identity_keys: IdentityDigestKeys, callback_codec: CallbackCodec, route_keys: RouteKeys | None = None, singleton_lock: SingletonLock | None = None, rate_limits: RateLimits | None = None, clock: Callable[[], int]) -> None:
        self._adapter = adapter
        self._store = store
        self._pinned_bot_id = pinned_bot_id
        self._identity_keys = identity_keys
        self._callback_codec = callback_codec
        self._route_keys = route_keys
        self._lock = singleton_lock or _LocalLock()
        self._rates = rate_limits or RateLimits()
        self._clock = clock
        self._started = False

    def start(self) -> None:
        if self._adapter.get_me() != self._pinned_bot_id:
            raise RuntimeError("Telegram bot identity mismatch")
        if self._adapter.get_webhook_info():
            raise RuntimeError("configured webhook forbids long polling")
        if not self._lock.acquire(self._pinned_bot_id):
            raise RuntimeError("poller singleton lock unavailable")
        self._started = True

    def stop(self) -> None:
        self._lock.release()
        self._started = False

    def poll_once(self) -> int:
        if not self._started:
            raise RuntimeError("poller not started")
        self._lock.assert_alive()
        raw_updates = self._adapter.get_updates(self._store.offset)
        processed = 0
        for raw in raw_updates:
            try:
                update = normalize_update(raw, pinned_bot_id=self._pinned_bot_id)
            except TelegramContractError:
                if not isinstance(self._store, PostgresStore):
                    raise
                update_id, callback_query_id = self._terminal_envelope(raw)
                with self._store.transaction():
                    self._store.persist_terminal(
                        update_id=update_id,
                        callback_query_id=callback_query_id,
                    )
                processed += 1
                continue
            with self._store.transaction():
                if isinstance(self._store, PostgresStore):
                    self._process_postgres(update)
                else:
                    self._process(update)
                    self._store.offset = max(self._store.offset, update.update_id + 1)
            processed += 1
        return processed

    @staticmethod
    def _terminal_envelope(raw: dict[str, object]) -> tuple[int, str | None]:
        update_id = raw.get("update_id")
        if (
            not isinstance(update_id, int)
            or isinstance(update_id, bool)
            or update_id < 0
            or update_id >= 9223372036854775807
        ):
            raise TelegramContractError("invalid update_id")
        callback_query_id: str | None = None
        callback = raw.get("callback_query")
        if isinstance(callback, dict):
            candidate = callback.get("id")
            if isinstance(candidate, str) and 1 <= len(candidate.encode("utf-8")) <= 256:
                callback_query_id = candidate
        return update_id, callback_query_id

    def handle_update(self, raw: dict[str, object]) -> ProcessResult:
        update = normalize_update(raw, pinned_bot_id=self._pinned_bot_id)
        with self._store.transaction():
            if isinstance(self._store, PostgresStore):
                return self._process_postgres(update)
            return self._process(update)

    def _process_postgres(self, update: TelegramUpdate) -> ProcessResult:
        if not isinstance(self._store, PostgresStore):
            raise TypeError("PostgreSQL processing requires PostgresStore")
        action: CallbackAction | None = None
        if update.callback_query_id is not None:
            if update.callback_data is None:
                outcome = self._store.persist_terminal(
                    update_id=update.update_id,
                    callback_query_id=update.callback_query_id,
                )
                return ProcessResult(outcome if outcome.startswith("duplicate_") else "invalid_callback")
            try:
                action = self._callback_codec.verify(update.callback_data, actor_id=update.actor_id, now=self._clock())
            except ValueError:
                outcome = self._store.persist_terminal(
                    update_id=update.update_id,
                    callback_query_id=update.callback_query_id,
                )
                return ProcessResult(outcome if outcome.startswith("duplicate_") else "invalid_callback")
            if action.action != "consent":
                outcome = self._store.persist_terminal(
                    update_id=update.update_id,
                    callback_query_id=update.callback_query_id,
                )
                return ProcessResult(outcome if outcome.startswith("duplicate_") else "invalid_callback")
        subjects = self._subjects(update)
        existing: TenantRecord | None = None
        matched_subject = subjects[0]
        for candidate in subjects:
            existing = self._store.resolve_existing_tenant(candidate.value)
            if existing is not None:
                matched_subject = candidate
                break
        if update.callback_query_id is not None:
            if action is None:
                raise RuntimeError("validated callback has no action")
            if existing is not None:
                outcome = self._store.persist(update, subject_digest=matched_subject.value, outcome="invalid_callback")
                return ProcessResult(outcome if outcome.startswith("duplicate_") else "invalid_callback")
            tenant_id = self._store.promote(action.enrollment_id, nonce=action.nonce)
            if self._route_keys is None:
                raise RuntimeError("active return-route keys are required")
            sealed_route = self._route_keys.seal(
                self._pinned_bot_id,
                update.chat_id,
                generation=1,
            )
            delivery_key = hashlib.sha256(f"consent-promoted\0{tenant_id}".encode()).hexdigest()
            outcome = self._store.persist(
                update,
                subject_digest=subjects[0].value,
                outcome="consent_promoted",
                delivery_key=delivery_key,
                outbox_payload={
                    "event_id": f"consent:{action.enrollment_id}",
                    "text": "Consent recorded. Send your CV.",
                    "sealed_route": sealed_route.as_dict(),
                },
            )
            return ProcessResult(
                outcome if outcome.startswith("duplicate_") else "consent_promoted",
                Reply("Consent recorded."),
            )
        if existing is not None:
            outcome = self._store.persist(update, subject_digest=matched_subject.value, outcome="status")
            if outcome.startswith("duplicate_"):
                return ProcessResult(outcome)
            if update.text in {"/start", "/status"}:
                return ProcessResult("status", Reply(f"Status: {existing.state}"))
            return ProcessResult("unsupported_command", Reply("Use /status."))
        if update.text != "/start":
            outcome = self._store.persist(update, subject_digest=None, outcome="terminal_dedupe")
            return ProcessResult(outcome if outcome.startswith("duplicate_") else "preconsent_command_rejected", Reply("Use /start to review consent."))
        nonce = hashlib.sha256(
            f"hulagu.consent-nonce.v1\0{update.bot_id}\0{update.actor_id}\0{subjects[0].value}".encode()
        ).hexdigest()
        outcome, enrollment_id = self._store.admit_enrollment(
            update,
            subjects[0],
            nonce=nonce,
            rate_limits=self._rates,
        )
        if outcome.startswith("duplicate_") or outcome == "rate_limited":
            return ProcessResult(outcome)
        if enrollment_id is None:
            raise RuntimeError("admitted enrollment has no authority")
        token = self._callback_codec.issue(CallbackAction("consent", enrollment_id, nonce, update.actor_id, self._clock() + 900))
        return ProcessResult(outcome, Reply("Review consent.", token))

    def _process(self, update: TelegramUpdate) -> ProcessResult:
        store = self._memory_store()
        update_key = (update.bot_id, update.update_id)
        if update_key in store.processed_updates:
            return ProcessResult("duplicate_update")
        store.processed_updates.add(update_key)
        if update.callback_query_id is not None:
            callback_key = (update.bot_id, update.callback_query_id)
            if callback_key in store.processed_callbacks:
                return ProcessResult("duplicate_callback")
            store.processed_callbacks.add(callback_key)
            return self._handle_callback(update)
        return self._handle_command(update)

    def _memory_store(self) -> MemoryStore:
        if not isinstance(self._store, MemoryStore):
            raise TypeError("memory processing requires MemoryStore")
        return self._store

    def _subjects(self, update: TelegramUpdate) -> tuple[IdentityDigest, ...]:
        return self._identity_keys.candidates(update.bot_id, update.actor_id)

    def _subject(self, update: TelegramUpdate) -> IdentityDigest:
        return self._subjects(update)[0]

    def _existing_tenant(self, update: TelegramUpdate) -> TenantRecord | None:
        store = self._memory_store()
        for subject in self._subjects(update):
            existing = store.resolve_existing_tenant(subject.value)
            if existing is not None:
                return existing
        return None

    def _admit_preconsent(self, subject: str, now: int) -> bool:
        store = self._memory_store()
        floor = now - self._rates.window_seconds
        store.global_rate = [seen for seen in store.global_rate if seen > floor]
        subject_events = [seen for seen in store.subject_rate.get(subject, []) if seen > floor]
        if len(subject_events) >= self._rates.per_subject or len(store.global_rate) >= self._rates.global_updates:
            return False
        subject_events.append(now)
        store.subject_rate[subject] = subject_events
        store.global_rate.append(now)
        return True

    def _handle_command(self, update: TelegramUpdate) -> ProcessResult:
        store = self._memory_store()
        subject = self._subject(update)
        existing = self._existing_tenant(update)
        if existing is not None:
            if update.text in {"/start", "/status"}:
                return ProcessResult("status", Reply(f"Status: {existing.state}"))
            return ProcessResult("unsupported_command", Reply("Use /status."))
        now = self._clock()
        if not self._admit_preconsent(subject.value, now):
            return ProcessResult("rate_limited", Reply("Too many updates; try again later."))
        store.command_work_count += 1
        if update.text != "/start":
            return ProcessResult("preconsent_command_rejected", Reply("Use /start to review consent."))
        current = store.enrollments.get(subject.value)
        if current is not None:
            token = self._callback_codec.issue(CallbackAction("consent", current.enrollment_id, current.nonce, update.actor_id, current.expires_at))
            return ProcessResult("enrollment_resumed", Reply("Review consent.", token))
        enrollment = Enrollment(secrets.token_hex(16), subject, secrets.token_urlsafe(18), now + 900)
        store.enrollments[subject.value] = enrollment
        token = self._callback_codec.issue(CallbackAction("consent", enrollment.enrollment_id, enrollment.nonce, update.actor_id, enrollment.expires_at))
        return ProcessResult("enrollment_started", Reply("Review consent.", token))

    def _handle_callback(self, update: TelegramUpdate) -> ProcessResult:
        store = self._memory_store()
        if update.callback_data is None:
            return ProcessResult("invalid_callback")
        try:
            action = self._callback_codec.verify(update.callback_data, actor_id=update.actor_id, now=self._clock())
        except ValueError:
            return ProcessResult("invalid_callback")
        if action.action != "consent":
            return ProcessResult("invalid_callback")
        subject = self._subject(update)
        enrollment = store.enrollments.get(subject.value)
        if enrollment is None or enrollment.enrollment_id != action.enrollment_id or enrollment.nonce != action.nonce:
            return ProcessResult("invalid_callback")
        tenant_id = secrets.token_hex(16)
        store.tenants[tenant_id] = TenantRecord(tenant_id, "awaiting_cv")
        store.bindings[subject.value] = tenant_id
        del store.enrollments[subject.value]
        delivery_key = hashlib.sha256(f"consent-promoted\0{tenant_id}".encode()).hexdigest()
        store.outbox[delivery_key] = OutboxMessage(
            delivery_key,
            update.chat_id,
            f"tenant-start:{tenant_id}",
            "Consent recorded. Send your CV.",
        )
        return ProcessResult("consent_promoted", Reply("Consent recorded."))
