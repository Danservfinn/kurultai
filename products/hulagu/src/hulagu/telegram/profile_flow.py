"""Durable Telegram profile-interview entrypoints over the pure state machine."""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID, uuid4

from ..domain.events import AnswerSubmitted, CvParsed, FieldEdited, OptionalFieldSkipped, ProfileConfirmed
from ..domain.interview import FIELD_SPEC_BY_ID, plan_interview
from ..domain.profile import Profile, ProfileField, ProfileQuestion
from ..domain.state_machine import (
    NonceAction,
    NonceFact,
    TenantState,
    TenantStatus,
    TransitionCode,
    transition_tenant,
)
from ..persistence.db import ConnectionProtocol, CursorProtocol, tenant_transaction
from ..persistence.rls import TenantPrincipal

ACTION_TTL_SECONDS = 15 * 60


@dataclass(frozen=True, slots=True)
class EditAction:
    field_id: str
    nonce: str


@dataclass(frozen=True, slots=True)
class ProfileView:
    profile_id: UUID
    profile: Profile
    status: TenantStatus
    active_question: ProfileQuestion | None
    answer_nonce: str | None
    skip_nonce: str | None
    confirmation_nonce: str | None
    edit_actions: tuple[EditAction, ...]
    summary: str

    @property
    def active_question_ids(self) -> tuple[str, ...]:
        return () if self.active_question is None else (self.active_question.question_id,)

    @property
    def is_search_confirmed(self) -> bool:
        return self.status is TenantStatus.READY and self.profile.confirmed_version == self.profile.version

    def edit_nonce(self, field_id: str) -> str | None:
        action = next((item for item in self.edit_actions if item.field_id == field_id), None)
        return None if action is None else action.nonce


@dataclass(frozen=True, slots=True)
class _StoredProfile:
    profile_id: UUID
    state: TenantState


class ProfileFlow:
    """Persist one tenant's current MAX(profile_version) interview aggregate."""

    def __init__(
        self,
        connection: ConnectionProtocol,
        principal: TenantPrincipal,
        *,
        clock: Callable[[], int],
        nonce_factory: Callable[[], str] = lambda: secrets.token_urlsafe(24),
    ) -> None:
        self._connection = connection
        self._principal = principal
        self._clock = clock
        self._nonce_factory = nonce_factory

    def start(self, profile: Profile, *, correlation_id: str) -> ProfileView:
        with (
            tenant_transaction(self._connection, self._principal, correlation_id=correlation_id),
            self._connection.cursor() as cursor,
        ):
                lifecycle_epoch = self._lock_tenant(cursor)
                existing = self._load_current(cursor)
                if existing is not None:
                    return self._view(existing)
                cursor.execute(
                    "SELECT COALESCE(MAX(profile_version),0) FROM hulagu.customer_profiles"
                )
                row = cursor.fetchone()
                version = 1 if row is None else int(row[0]) + 1
                draft = replace(profile, version=version, confirmed_version=None)
                plan = plan_interview(draft)
                parsed = transition_tenant(
                    TenantState(
                        status=TenantStatus.PARSING_CV,
                        tenant_id=str(self._principal.tenant_id),
                        lifecycle_epoch=lifecycle_epoch,
                    ),
                    CvParsed(draft, plan.questions),
                )
                if parsed.code is not TransitionCode.APPLIED:
                    raise RuntimeError("profile interview could not start")
                state = self._with_fresh_actions(parsed.state)
                stored = _StoredProfile(uuid4(), state)
                cursor.execute(
                    "INSERT INTO hulagu.customer_profiles(tenant_id,id,profile_version,profile_json,state) "
                    "VALUES(current_setting('app.tenant_id')::uuid,%s,%s,%s::jsonb,%s)",
                    (
                        stored.profile_id,
                        version,
                        self._serialize_state(state),
                        self._database_state(state.status),
                    ),
                )
                return self._view(stored)

    def current(self, *, correlation_id: str) -> ProfileView:
        with (
            tenant_transaction(self._connection, self._principal, correlation_id=correlation_id),
            self._connection.cursor() as cursor,
        ):
                stored = self._load_current(cursor)
                if stored is None:
                    raise LookupError("profile not found")
                return self._view(stored)

    def answer(
        self,
        question_id: str,
        value: str,
        nonce: str,
        *,
        correlation_id: str,
    ) -> ProfileView:
        event = AnswerSubmitted(question_id, value, nonce, self._clock(), self._clock())
        return self._mutate(
            event,
            correlation_id=correlation_id,
            answer={"value": value},
            provenance={"source": "interview", "action": "answer"},
        )

    def skip(self, question_id: str, nonce: str, *, correlation_id: str) -> ProfileView:
        event = OptionalFieldSkipped(question_id, nonce, self._clock(), self._clock())
        return self._mutate(
            event,
            correlation_id=correlation_id,
            answer={"skipped": True},
            provenance={"source": "interview", "action": "skip"},
        )

    def edit(
        self,
        field_id: str,
        value: str,
        nonce: str,
        *,
        correlation_id: str,
    ) -> ProfileView:
        stored = self._read_for_event(correlation_id=f"{correlation_id}:version")
        event = FieldEdited(
            field_id,
            value,
            stored.state.profile.version if stored.state.profile is not None else -1,
            nonce,
            self._clock(),
            self._clock(),
        )
        return self._mutate(event, correlation_id=correlation_id, insert_new_version=True)

    def confirm(self, nonce: str, *, correlation_id: str) -> ProfileView:
        stored = self._read_for_event(correlation_id=f"{correlation_id}:version")
        event = ProfileConfirmed(
            stored.state.profile.version if stored.state.profile is not None else -1,
            nonce,
            self._clock(),
            self._clock(),
        )
        return self._mutate(event, correlation_id=correlation_id)

    def _read_for_event(self, *, correlation_id: str) -> _StoredProfile:
        with (
            tenant_transaction(self._connection, self._principal, correlation_id=correlation_id),
            self._connection.cursor() as cursor,
        ):
                stored = self._load_current(cursor)
                if stored is None:
                    raise LookupError("profile not found")
                return stored

    def _mutate(
        self,
        event: AnswerSubmitted | OptionalFieldSkipped | FieldEdited | ProfileConfirmed,
        *,
        correlation_id: str,
        answer: dict[str, object] | None = None,
        provenance: dict[str, object] | None = None,
        insert_new_version: bool = False,
    ) -> ProfileView:
        with (
            tenant_transaction(self._connection, self._principal, correlation_id=correlation_id),
            self._connection.cursor() as cursor,
        ):
                lifecycle_epoch = self._lock_tenant(cursor)
                stored = self._load_current(cursor)
                if stored is None:
                    raise LookupError("profile not found")
                stored = replace(
                    stored,
                    state=replace(stored.state, lifecycle_epoch=lifecycle_epoch),
                )
                result = transition_tenant(stored.state, event)
                if result.code is not TransitionCode.APPLIED:
                    return self._view(stored)
                state = self._with_fresh_actions(result.state)
                if answer is not None and provenance is not None:
                    if not isinstance(event, (AnswerSubmitted, OptionalFieldSkipped)):
                        raise RuntimeError("answer persistence requires a question event")
                    cursor.execute(
                        "INSERT INTO hulagu.profile_answers(tenant_id,profile_id,question_id,answer,provenance) "
                        "VALUES(current_setting('app.tenant_id')::uuid,%s,%s,%s::jsonb,%s::jsonb)",
                        (
                            stored.profile_id,
                            event.question_id,
                            json.dumps(answer, separators=(",", ":"), sort_keys=True),
                            json.dumps(provenance, separators=(",", ":"), sort_keys=True),
                        ),
                    )
                changed = _StoredProfile(stored.profile_id, state)
                if insert_new_version:
                    if state.profile is None:
                        raise RuntimeError("edited profile missing")
                    changed = _StoredProfile(uuid4(), state)
                    cursor.execute(
                        "INSERT INTO hulagu.customer_profiles(tenant_id,id,profile_version,profile_json,state) "
                        "VALUES(current_setting('app.tenant_id')::uuid,%s,%s,%s::jsonb,%s)",
                        (
                            changed.profile_id,
                            state.profile.version,
                            self._serialize_state(state),
                            self._database_state(state.status),
                        ),
                    )
                else:
                    cursor.execute(
                        "UPDATE hulagu.customer_profiles SET profile_json=%s::jsonb,state=%s "
                        "WHERE id=%s AND profile_version=%s",
                        (
                            self._serialize_state(state),
                            self._database_state(state.status),
                            stored.profile_id,
                            stored.state.profile.version if stored.state.profile is not None else -1,
                        ),
                    )
                return self._view(changed)

    def _lock_tenant(self, cursor: CursorProtocol) -> int:
        cursor.execute("SELECT lifecycle_epoch FROM hulagu.tenants WHERE id=current_setting('app.tenant_id')::uuid FOR UPDATE")
        row = cursor.fetchone()
        if row is None:
            raise LookupError("tenant not found")
        return int(row[0])

    def _load_current(self, cursor: CursorProtocol) -> _StoredProfile | None:
        cursor.execute(
            "SELECT id,profile_json FROM hulagu.customer_profiles "
            "ORDER BY profile_version DESC LIMIT 1"
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return _StoredProfile(UUID(str(row[0])), self._deserialize_state(str(row[1])))

    def _with_fresh_actions(self, state: TenantState) -> TenantState:
        if state.profile is None:
            return state
        expires_at = self._clock() + ACTION_TTL_SECONDS
        facts: set[NonceFact] = set()
        active = state.active_question
        if active is not None:
            facts.add(self._fact(NonceAction.ANSWER_QUESTION, active.question_id, state, expires_at))
            facts.add(self._fact(NonceAction.SKIP_OPTIONAL_FIELD, active.question_id, state, expires_at))
        if state.status is TenantStatus.AWAITING_PROFILE_CONFIRMATION:
            facts.add(self._fact(NonceAction.CONFIRM_PROFILE, "profile", state, expires_at))
        if state.status in {TenantStatus.AWAITING_PROFILE_CONFIRMATION, TenantStatus.READY}:
            for field in state.profile.fields:
                if field.field_id in FIELD_SPEC_BY_ID:
                    facts.add(self._fact(NonceAction.EDIT_FIELD, field.field_id, state, expires_at))
        return replace(state, nonce_facts=frozenset(facts))

    def _fact(
        self,
        action: NonceAction,
        object_id: str,
        state: TenantState,
        expires_at: int,
    ) -> NonceFact:
        if state.profile is None:
            raise RuntimeError("profile action missing profile")
        return NonceFact(
            nonce=self._nonce_factory(),
            tenant_id=state.tenant_id,
            action=action,
            object_id=object_id,
            version=state.profile.version,
            lifecycle_epoch=state.lifecycle_epoch,
            expires_at=expires_at,
        )

    def _view(self, stored: _StoredProfile) -> ProfileView:
        state = stored.state
        if state.profile is None:
            raise RuntimeError("stored profile missing")

        def nonce(action: NonceAction, object_id: str) -> str | None:
            fact = next(
                (
                    item
                    for item in state.nonce_facts
                    if item.action is action and item.object_id == object_id
                ),
                None,
            )
            return None if fact is None else fact.nonce

        active = state.active_question
        edits = tuple(
            EditAction(field.field_id, action_nonce)
            for field in state.profile.fields
            if (action_nonce := nonce(NonceAction.EDIT_FIELD, field.field_id)) is not None
        )
        return ProfileView(
            profile_id=stored.profile_id,
            profile=state.profile,
            status=state.status,
            active_question=active,
            answer_nonce=None if active is None else nonce(NonceAction.ANSWER_QUESTION, active.question_id),
            skip_nonce=None if active is None else nonce(NonceAction.SKIP_OPTIONAL_FIELD, active.question_id),
            confirmation_nonce=nonce(NonceAction.CONFIRM_PROFILE, "profile"),
            edit_actions=edits,
            summary=self._summary(state.profile),
        )

    @staticmethod
    def _summary(profile: Profile) -> str:
        lines = [f"Profile version {profile.version}"]
        for field in profile.fields:
            spec = FIELD_SPEC_BY_ID.get(field.field_id)
            label = field.field_id.replace("_", " ").title() if spec is None else spec.label
            lines.append(f"{label}: {field.value}")
        for field_id in profile.intentionally_omitted:
            spec = FIELD_SPEC_BY_ID.get(field_id)
            label = field_id.replace("_", " ").title() if spec is None else spec.label
            lines.append(f"{label}: Not provided (optional)")
        return "\n".join(lines)

    @staticmethod
    def _database_state(status: TenantStatus) -> str:
        return {
            TenantStatus.INTERVIEWING: "interviewing",
            TenantStatus.AWAITING_PROFILE_CONFIRMATION: "awaiting_confirmation",
            TenantStatus.READY: "confirmed",
        }[status]

    @staticmethod
    def _serialize_state(state: TenantState) -> str:
        if state.profile is None:
            raise RuntimeError("cannot serialize missing profile")
        payload = {
            "status": state.status.value,
            "tenant_id": state.tenant_id,
            "lifecycle_epoch": state.lifecycle_epoch,
            "profile": {
                "version": state.profile.version,
                "fields": [
                    {
                        "field_id": field.field_id,
                        "value": field.value,
                        "source": field.source,
                        "confidence": field.confidence,
                        "source_span": field.source_span,
                    }
                    for field in state.profile.fields
                ],
                "intentionally_omitted": list(state.profile.intentionally_omitted),
                "confirmed_version": state.profile.confirmed_version,
            },
            "questions": [
                {
                    "question_id": item.question_id,
                    "field_id": item.field_id,
                    "required": item.required,
                }
                for item in state.questions
            ],
            "active_question_id": None if state.active_question is None else state.active_question.question_id,
            "nonce_facts": [
                {
                    "nonce": fact.nonce,
                    "tenant_id": fact.tenant_id,
                    "action": fact.action.value,
                    "object_id": fact.object_id,
                    "version": fact.version,
                    "lifecycle_epoch": fact.lifecycle_epoch,
                    "expires_at": fact.expires_at,
                }
                for fact in sorted(state.nonce_facts, key=lambda item: item.nonce)
            ],
            "used_nonces": sorted(state.used_nonces),
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    @staticmethod
    def _deserialize_state(raw: str) -> TenantState:
        payload: dict[str, Any] = json.loads(raw)
        profile_payload = payload["profile"]
        profile = Profile(
            version=int(profile_payload["version"]),
            fields=tuple(
                ProfileField(
                    field_id=str(item["field_id"]),
                    value=str(item["value"]),
                    source=str(item["source"]),
                    confidence=float(item["confidence"]),
                    source_span=None if item["source_span"] is None else str(item["source_span"]),
                )
                for item in profile_payload["fields"]
            ),
            intentionally_omitted=tuple(str(item) for item in profile_payload["intentionally_omitted"]),
            confirmed_version=(
                None
                if profile_payload["confirmed_version"] is None
                else int(profile_payload["confirmed_version"])
            ),
        )
        questions = tuple(
            ProfileQuestion(
                question_id=str(item["question_id"]),
                field_id=str(item["field_id"]),
                required=bool(item["required"]),
            )
            for item in payload["questions"]
        )
        active_id = payload["active_question_id"]
        return TenantState(
            status=TenantStatus(str(payload["status"])),
            tenant_id=str(payload["tenant_id"]),
            lifecycle_epoch=int(payload["lifecycle_epoch"]),
            profile=profile,
            questions=questions,
            active_question=next((item for item in questions if item.question_id == active_id), None),
            nonce_facts=frozenset(
                NonceFact(
                    nonce=str(item["nonce"]),
                    tenant_id=str(item["tenant_id"]),
                    action=NonceAction(str(item["action"])),
                    object_id=str(item["object_id"]),
                    version=int(item["version"]),
                    lifecycle_epoch=int(item["lifecycle_epoch"]),
                    expires_at=int(item["expires_at"]),
                )
                for item in payload["nonce_facts"]
            ),
            used_nonces=frozenset(str(item) for item in payload["used_nonces"]),
        )
