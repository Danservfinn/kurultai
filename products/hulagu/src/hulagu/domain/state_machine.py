"""Pure transition functions for Hulagu's three customer aggregates."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Generic, TypeVar

from .events import (
    AnswerSubmitted,
    ConsentAccepted,
    ConsentDeclined,
    CvParsed,
    CvParseFailed,
    CvReceived,
    DeleteCancelled,
    DeleteConfirmed,
    DeleteRequested,
    DeletionCompleted,
    FieldEdited,
    OptionalFieldSkipped,
    ProfileConfirmed,
    RunCancelled,
    RunPaused,
    RunResumed,
    SearchRequested,
    WorkerRetry,
)
from .profile import Profile, ProfileField, ProfileQuestion


class TransitionCode(str, Enum):
    APPLIED = "applied"
    NOOP = "noop"
    REJECTED = "rejected"
    INVALID_CALLBACK = "invalid_callback"
    NO_ACTIVE_RUN = "no_active_run"


StateT = TypeVar("StateT")


@dataclass(frozen=True, slots=True)
class TransitionResult(Generic[StateT]):
    state: StateT
    code: TransitionCode
    reason: str


class EnrollmentStatus(str, Enum):
    AWAITING_CONSENT = "awaiting_consent"
    PROMOTED = "promoted"
    DECLINED = "declined"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class EnrollmentState:
    status: EnrollmentStatus
    notice_version: str
    action_nonce: str
    nonce_expires_at: int
    subject_digest: str | None = "provisional"
    tenant_created: bool = False


class TenantStatus(str, Enum):
    AWAITING_CV = "awaiting_cv"
    PARSING_CV = "parsing_cv"
    INTERVIEWING = "interviewing"
    AWAITING_PROFILE_CONFIRMATION = "awaiting_profile_confirmation"
    READY = "ready"
    RETRY_WAIT = "retry_wait"
    NEEDS_OPERATOR = "needs_operator"
    DELETE_PENDING = "delete_pending"
    DELETING = "deleting"
    DELETED = "deleted"


class NonceAction(str, Enum):
    ANSWER_QUESTION = "answer_question"
    SKIP_OPTIONAL_FIELD = "skip_optional_field"
    EDIT_FIELD = "edit_field"
    CONFIRM_PROFILE = "confirm_profile"
    REQUEST_SEARCH = "request_search"
    PAUSE_RUN = "pause_run"
    RESUME_RUN = "resume_run"
    CANCEL_RUN = "cancel_run"
    REQUEST_DELETE = "request_delete"
    DECIDE_DELETE = "decide_delete"


@dataclass(frozen=True, slots=True)
class NonceFact:
    nonce: str
    tenant_id: str
    action: NonceAction
    object_id: str
    version: int
    lifecycle_epoch: int
    expires_at: int


@dataclass(frozen=True, slots=True)
class TenantState:
    status: TenantStatus
    tenant_id: str = "tenant-1"
    lifecycle_epoch: int = 0
    profile: Profile | None = None
    questions: tuple[ProfileQuestion, ...] = ()
    active_question: ProfileQuestion | None = None
    nonce_facts: frozenset[NonceFact] = frozenset()
    used_nonces: frozenset[str] = frozenset()
    delete_nonce: str | None = None
    delete_prior_status: TenantStatus | None = None
    retry_target: TenantStatus | None = None
    retry_count: int = 0
    max_retries: int = 2


class RunStatus(str, Enum):
    QUEUED = "queued"
    SEARCHING = "searching"
    PUBLISHING = "publishing"
    RESULTS_READY = "results_ready"
    RETRY_WAIT = "retry_wait"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    PARTIAL = "partial"
    FAILED = "failed"
    NEEDS_OPERATOR = "needs_operator"


@dataclass(frozen=True, slots=True)
class RunState:
    run_id: str
    status: RunStatus
    work_epoch: int
    retry_target: RunStatus | None = None
    retry_count: int = 0
    max_retries: int = 2


@dataclass(frozen=True, slots=True)
class SearchState:
    tenant_id: str = "tenant-1"
    runs: tuple[RunState, ...] = ()
    nonce_facts: frozenset[NonceFact] = frozenset()
    used_nonces: frozenset[str] = frozenset()

    def run(self, run_id: str) -> RunState | None:
        return next((run for run in self.runs if run.run_id == run_id), None)


EnrollmentEvent = ConsentAccepted | ConsentDeclined
TenantEvent = (
    CvReceived
    | CvParsed
    | CvParseFailed
    | AnswerSubmitted
    | OptionalFieldSkipped
    | FieldEdited
    | ProfileConfirmed
    | DeleteRequested
    | DeleteConfirmed
    | DeleteCancelled
    | DeletionCompleted
    | WorkerRetry
)
SearchEvent = SearchRequested | RunPaused | RunResumed | RunCancelled | WorkerRetry


def _result(state: StateT, code: TransitionCode, reason: str) -> TransitionResult[StateT]:
    return TransitionResult(state=state, code=code, reason=reason)


def start_enrollment(
    notice_version: str,
    action_nonce: str,
    nonce_expires_at: int,
    *,
    current: EnrollmentState | None = None,
) -> TransitionResult[EnrollmentState]:
    if current is not None:
        return _result(current, TransitionCode.NOOP, "enrollment_resumed")
    state = EnrollmentState(
        status=EnrollmentStatus.AWAITING_CONSENT,
        notice_version=notice_version,
        action_nonce=action_nonce,
        nonce_expires_at=nonce_expires_at,
    )
    return _result(state, TransitionCode.APPLIED, "enrollment_started")


def transition_enrollment(
    state: EnrollmentState, event: EnrollmentEvent
) -> TransitionResult[EnrollmentState]:
    if state.status is not EnrollmentStatus.AWAITING_CONSENT:
        return _result(state, TransitionCode.NOOP, "enrollment_terminal")
    if event.notice_version != state.notice_version:
        return _result(state, TransitionCode.INVALID_CALLBACK, "stale_notice_version")
    if event.nonce != state.action_nonce:
        return _result(state, TransitionCode.INVALID_CALLBACK, "stale_action_nonce")
    if event.now > state.nonce_expires_at:
        return _result(state, TransitionCode.INVALID_CALLBACK, "expired_callback")
    if isinstance(event, ConsentDeclined):
        declined = replace(
            state,
            status=EnrollmentStatus.DECLINED,
            subject_digest=None,
            action_nonce="",
        )
        return _result(declined, TransitionCode.APPLIED, "consent_declined")
    promoted = replace(
        state,
        status=EnrollmentStatus.PROMOTED,
        tenant_created=True,
        subject_digest=None,
        action_nonce="",
    )
    return _result(promoted, TransitionCode.APPLIED, "consent_accepted")


CallbackStateT = TypeVar("CallbackStateT", TenantState, SearchState)


def _callback_error(
    state: CallbackStateT,
    nonce: str,
    now: int,
    action: NonceAction,
    object_id: str,
    version: int,
    lifecycle_epoch: int,
) -> TransitionResult[CallbackStateT] | None:
    if nonce in state.used_nonces:
        return _result(state, TransitionCode.NOOP, "action_nonce_consumed")
    matches = tuple(item for item in state.nonce_facts if item.nonce == nonce)
    if not nonce or len(matches) != 1:
        return _result(state, TransitionCode.INVALID_CALLBACK, "stale_action_nonce")
    fact = matches[0]
    if now > fact.expires_at:
        return _result(state, TransitionCode.INVALID_CALLBACK, "expired_callback")
    if (
        fact.tenant_id != state.tenant_id
        or fact.action is not action
        or fact.object_id != object_id
        or fact.version != version
        or fact.lifecycle_epoch != lifecycle_epoch
    ):
        return _result(state, TransitionCode.INVALID_CALLBACK, "stale_action_authority")
    return None


def _consume_tenant_nonce(state: TenantState, nonce: str) -> TenantState:
    return replace(
        state,
        nonce_facts=frozenset(fact for fact in state.nonce_facts if fact.nonce != nonce),
        used_nonces=state.used_nonces | {nonce},
    )


def _advance_question(state: TenantState) -> TenantState:
    remaining = state.questions[1:] if state.questions else ()
    return replace(
        state,
        questions=remaining,
        active_question=remaining[0] if remaining else None,
        status=(TenantStatus.INTERVIEWING if remaining else TenantStatus.AWAITING_PROFILE_CONFIRMATION),
    )


def transition_tenant(state: TenantState, event: TenantEvent) -> TransitionResult[TenantState]:
    if state.status is TenantStatus.DELETED:
        return _result(state, TransitionCode.NOOP, "tenant_deleted")

    if isinstance(event, DeletionCompleted):
        if state.status is not TenantStatus.DELETING:
            return _result(state, TransitionCode.NOOP, "deletion_not_running")
        if event.expected_lifecycle_epoch != state.lifecycle_epoch:
            return _result(state, TransitionCode.REJECTED, "stale_lifecycle_epoch")
        deleted = replace(
            state,
            status=TenantStatus.DELETED,
            profile=None,
            questions=(),
            active_question=None,
            nonce_facts=frozenset(),
        )
        return _result(deleted, TransitionCode.APPLIED, "tenant_deleted")

    if state.status is TenantStatus.DELETING and isinstance(event, DeleteConfirmed):
        return _result(state, TransitionCode.NOOP, "deletion_in_progress")

    if state.status is TenantStatus.DELETING:
        return _result(state, TransitionCode.REJECTED, "tenant_deleting")

    if isinstance(event, DeleteConfirmed):
        if state.status is not TenantStatus.DELETE_PENDING:
            return _result(state, TransitionCode.NOOP, "delete_not_pending")
        error = _callback_error(
            state,
            event.nonce,
            event.now,
            NonceAction.DECIDE_DELETE,
            state.tenant_id,
            state.lifecycle_epoch,
            state.lifecycle_epoch,
        )
        if error is not None or event.nonce != state.delete_nonce:
            return _result(
                state,
                error.code if error is not None else TransitionCode.INVALID_CALLBACK,
                error.reason if error is not None else "stale_action_nonce",
            )
        deleting = replace(
            state,
            status=TenantStatus.DELETING,
            lifecycle_epoch=state.lifecycle_epoch + 1,
            nonce_facts=frozenset(),
            used_nonces=state.used_nonces | {event.nonce},
            delete_nonce=None,
            delete_prior_status=None,
        )
        return _result(deleting, TransitionCode.APPLIED, "tenant_deleting")

    if isinstance(event, DeleteCancelled):
        if state.status is not TenantStatus.DELETE_PENDING:
            return _result(state, TransitionCode.NOOP, "delete_not_pending")
        error = _callback_error(
            state,
            event.nonce,
            event.now,
            NonceAction.DECIDE_DELETE,
            state.tenant_id,
            state.lifecycle_epoch,
            state.lifecycle_epoch,
        )
        if error is not None or event.nonce != state.delete_nonce:
            return _result(
                state,
                error.code if error is not None else TransitionCode.INVALID_CALLBACK,
                error.reason if error is not None else "stale_action_nonce",
            )
        restored = replace(
            _consume_tenant_nonce(state, event.nonce),
            status=state.delete_prior_status or TenantStatus.AWAITING_CV,
            delete_nonce=None,
            delete_prior_status=None,
        )
        return _result(restored, TransitionCode.APPLIED, "delete_cancelled")

    if isinstance(event, DeleteRequested):
        error = _callback_error(
            state,
            event.nonce,
            event.now,
            NonceAction.REQUEST_DELETE,
            state.tenant_id,
            state.lifecycle_epoch,
            state.lifecycle_epoch,
        )
        if error is not None:
            return _result(error.state, error.code, error.reason)
        if state.status is TenantStatus.DELETE_PENDING:
            return _result(state, TransitionCode.NOOP, "delete_already_pending")
        if (
            not event.decision_nonce
            or event.decision_nonce == event.nonce
            or event.decision_nonce in state.used_nonces
            or any(fact.nonce == event.decision_nonce for fact in state.nonce_facts)
        ):
            return _result(state, TransitionCode.REJECTED, "invalid_delete_decision_nonce")
        decision_fact = NonceFact(
            nonce=event.decision_nonce,
            tenant_id=state.tenant_id,
            action=NonceAction.DECIDE_DELETE,
            object_id=state.tenant_id,
            version=state.lifecycle_epoch,
            lifecycle_epoch=state.lifecycle_epoch,
            expires_at=event.decision_expires_at,
        )
        consumed = _consume_tenant_nonce(state, event.nonce)
        pending = replace(
            consumed,
            status=TenantStatus.DELETE_PENDING,
            nonce_facts=consumed.nonce_facts | {decision_fact},
            delete_nonce=event.decision_nonce,
            delete_prior_status=state.status,
        )
        return _result(pending, TransitionCode.APPLIED, "delete_pending")

    if state.status is TenantStatus.DELETE_PENDING:
        return _result(state, TransitionCode.REJECTED, "delete_pending")

    if isinstance(event, CvReceived):
        if state.status is not TenantStatus.AWAITING_CV:
            return _result(state, TransitionCode.REJECTED, "cv_wrong_state")
        return _result(replace(state, status=TenantStatus.PARSING_CV), TransitionCode.APPLIED, "cv_received")

    if isinstance(event, CvParsed):
        if state.status is not TenantStatus.PARSING_CV:
            return _result(state, TransitionCode.REJECTED, "parse_wrong_state")
        parsed = replace(
            state,
            status=(TenantStatus.INTERVIEWING if event.questions else TenantStatus.AWAITING_PROFILE_CONFIRMATION),
            profile=event.profile,
            questions=event.questions,
            active_question=event.questions[0] if event.questions else None,
            retry_target=None,
        )
        return _result(parsed, TransitionCode.APPLIED, "cv_parsed")

    if isinstance(event, CvParseFailed):
        if state.status is not TenantStatus.PARSING_CV:
            return _result(state, TransitionCode.REJECTED, "parse_wrong_state")
        waiting = replace(state, status=TenantStatus.RETRY_WAIT, retry_target=TenantStatus.PARSING_CV)
        return _result(waiting, TransitionCode.APPLIED, "parser_retry_wait")

    if isinstance(event, WorkerRetry):
        if event.run_id is not None or state.status is not TenantStatus.RETRY_WAIT:
            return _result(state, TransitionCode.REJECTED, "worker_not_retryable")
        next_count = state.retry_count + 1
        if next_count > state.max_retries or state.retry_target is None:
            terminal = replace(state, status=TenantStatus.NEEDS_OPERATOR, retry_count=next_count)
            return _result(terminal, TransitionCode.APPLIED, "retry_exhausted")
        retried = replace(state, status=state.retry_target, retry_count=next_count, retry_target=None)
        return _result(retried, TransitionCode.APPLIED, "worker_retried")

    if isinstance(event, AnswerSubmitted):
        error = _callback_error(
            state,
            event.nonce,
            event.now,
            NonceAction.ANSWER_QUESTION,
            event.question_id,
            state.profile.version if state.profile is not None else -1,
            state.lifecycle_epoch,
        )
        if error is not None:
            return _result(error.state, error.code, error.reason)
        if state.active_question is None:
            return _result(state, TransitionCode.REJECTED, "no_active_question")
        if event.question_id != state.active_question.question_id:
            return _result(state, TransitionCode.REJECTED, "stale_question")
        if state.profile is None:
            return _result(state, TransitionCode.REJECTED, "profile_missing")
        profile = state.profile.set_field(
            ProfileField(state.active_question.field_id, event.value, "interview", 1.0)
        )
        advanced = _advance_question(replace(_consume_tenant_nonce(state, event.nonce), profile=profile))
        return _result(advanced, TransitionCode.APPLIED, "answer_recorded")

    if isinstance(event, OptionalFieldSkipped):
        error = _callback_error(
            state,
            event.nonce,
            event.now,
            NonceAction.SKIP_OPTIONAL_FIELD,
            event.question_id,
            state.profile.version if state.profile is not None else -1,
            state.lifecycle_epoch,
        )
        if error is not None:
            return _result(error.state, error.code, error.reason)
        if state.active_question is None:
            return _result(state, TransitionCode.REJECTED, "no_active_question")
        if event.question_id != state.active_question.question_id:
            return _result(state, TransitionCode.REJECTED, "stale_question")
        if state.active_question.required:
            return _result(state, TransitionCode.REJECTED, "required_field")
        if state.profile is None:
            return _result(state, TransitionCode.REJECTED, "profile_missing")
        profile = state.profile.omit(state.active_question.field_id)
        advanced = _advance_question(replace(_consume_tenant_nonce(state, event.nonce), profile=profile))
        return _result(advanced, TransitionCode.APPLIED, "optional_field_skipped")

    if isinstance(event, ProfileConfirmed):
        error = _callback_error(
            state,
            event.nonce,
            event.now,
            NonceAction.CONFIRM_PROFILE,
            "profile",
            event.expected_profile_version,
            state.lifecycle_epoch,
        )
        if error is not None:
            return _result(error.state, error.code, error.reason)
        if state.status is not TenantStatus.AWAITING_PROFILE_CONFIRMATION or state.profile is None:
            return _result(state, TransitionCode.REJECTED, "profile_not_confirmable")
        if event.expected_profile_version != state.profile.version:
            return _result(state, TransitionCode.INVALID_CALLBACK, "stale_profile_version")
        confirmed = replace(
            _consume_tenant_nonce(state, event.nonce),
            status=TenantStatus.READY,
            profile=state.profile.confirm(),
        )
        return _result(confirmed, TransitionCode.APPLIED, "profile_confirmed")

    if isinstance(event, FieldEdited):
        error = _callback_error(
            state,
            event.nonce,
            event.now,
            NonceAction.EDIT_FIELD,
            event.field_id,
            event.expected_profile_version,
            state.lifecycle_epoch,
        )
        if error is not None:
            return _result(error.state, error.code, error.reason)
        if state.profile is None:
            return _result(state, TransitionCode.REJECTED, "profile_missing")
        if event.expected_profile_version != state.profile.version:
            return _result(state, TransitionCode.INVALID_CALLBACK, "stale_profile_version")
        edited_profile = state.profile.set_field(
            ProfileField(event.field_id, event.value, "customer_edit", 1.0),
            increment_version=True,
        )
        edited = replace(
            _consume_tenant_nonce(state, event.nonce),
            status=TenantStatus.AWAITING_PROFILE_CONFIRMATION,
            profile=edited_profile,
        )
        return _result(edited, TransitionCode.APPLIED, "profile_edited")

    return _result(state, TransitionCode.REJECTED, "unsupported_event")


def _replace_run(state: SearchState, changed: RunState, nonce: str | None = None) -> SearchState:
    runs = tuple(changed if run.run_id == changed.run_id else run for run in state.runs)
    used = state.used_nonces if nonce is None else state.used_nonces | {nonce}
    facts = (
        state.nonce_facts
        if nonce is None
        else frozenset(fact for fact in state.nonce_facts if fact.nonce != nonce)
    )
    return replace(state, runs=runs, nonce_facts=facts, used_nonces=used)


def _run_is_nonterminal(status: RunStatus) -> bool:
    return status not in {
        RunStatus.RESULTS_READY,
        RunStatus.CANCELLED,
        RunStatus.PARTIAL,
        RunStatus.FAILED,
        RunStatus.NEEDS_OPERATOR,
    }


def transition_search(
    state: SearchState,
    tenant: TenantState,
    event: SearchEvent,
) -> TransitionResult[SearchState]:
    if state.tenant_id != tenant.tenant_id:
        return _result(state, TransitionCode.INVALID_CALLBACK, "tenant_mismatch")

    if isinstance(event, SearchRequested):
        error = _callback_error(
            state,
            event.nonce,
            event.now,
            NonceAction.REQUEST_SEARCH,
            event.run_id,
            event.expected_profile_version,
            tenant.lifecycle_epoch,
        )
        if error is not None:
            return _result(error.state, error.code, error.reason)
        if (
            tenant.status is not TenantStatus.READY
            or tenant.profile is None
            or tenant.profile.confirmed_version != tenant.profile.version
        ):
            return _result(state, TransitionCode.REJECTED, "profile_not_confirmed")
        if event.expected_profile_version != tenant.profile.version:
            return _result(state, TransitionCode.INVALID_CALLBACK, "stale_profile_version")
        if any(_run_is_nonterminal(run.status) for run in state.runs):
            return _result(state, TransitionCode.REJECTED, "active_run_exists")
        if state.run(event.run_id) is not None:
            return _result(state, TransitionCode.REJECTED, "run_id_exists")
        started = replace(
            state,
            runs=state.runs + (RunState(event.run_id, RunStatus.QUEUED, 1),),
            nonce_facts=frozenset(
                fact for fact in state.nonce_facts if fact.nonce != event.nonce
            ),
            used_nonces=state.used_nonces | {event.nonce},
        )
        return _result(started, TransitionCode.APPLIED, "search_started")

    if isinstance(event, WorkerRetry):
        if event.run_id is None:
            return _result(state, TransitionCode.NO_ACTIVE_RUN, "no_active_run")
        run = state.run(event.run_id)
        if run is None or not _run_is_nonterminal(run.status):
            return _result(state, TransitionCode.NO_ACTIVE_RUN, "no_active_run")
        if run.status is not RunStatus.RETRY_WAIT:
            return _result(state, TransitionCode.REJECTED, "worker_not_retryable")
        next_count = run.retry_count + 1
        if next_count > run.max_retries or run.retry_target not in {RunStatus.SEARCHING, RunStatus.PUBLISHING}:
            changed = replace(run, status=RunStatus.NEEDS_OPERATOR, retry_count=next_count)
            return _result(_replace_run(state, changed), TransitionCode.APPLIED, "retry_exhausted")
        changed = replace(run, status=run.retry_target, retry_count=next_count, retry_target=None)
        return _result(_replace_run(state, changed), TransitionCode.APPLIED, "worker_retried")

    run = state.run(event.run_id)
    if run is None or not _run_is_nonterminal(run.status):
        return _result(state, TransitionCode.NO_ACTIVE_RUN, "no_active_run")
    if tenant.status is not TenantStatus.READY:
        return _result(state, TransitionCode.REJECTED, "tenant_not_ready")
    action = (
        NonceAction.PAUSE_RUN
        if isinstance(event, RunPaused)
        else NonceAction.RESUME_RUN
        if isinstance(event, RunResumed)
        else NonceAction.CANCEL_RUN
    )
    error = _callback_error(
        state,
        event.nonce,
        event.now,
        action,
        event.run_id,
        run.work_epoch,
        tenant.lifecycle_epoch,
    )
    if error is not None:
        return _result(error.state, error.code, error.reason)

    if isinstance(event, RunPaused):
        if run.status is RunStatus.PAUSED:
            return _result(state, TransitionCode.NOOP, "run_already_paused")
        changed = replace(run, status=RunStatus.PAUSED, work_epoch=run.work_epoch + 1)
        return _result(_replace_run(state, changed, event.nonce), TransitionCode.APPLIED, "run_paused")

    if isinstance(event, RunResumed):
        if run.status is not RunStatus.PAUSED:
            return _result(state, TransitionCode.REJECTED, "run_not_paused")
        changed = replace(run, status=RunStatus.QUEUED, work_epoch=run.work_epoch + 1)
        return _result(_replace_run(state, changed, event.nonce), TransitionCode.APPLIED, "run_resumed")

    changed = replace(run, status=RunStatus.CANCELLED, work_epoch=run.work_epoch + 1)
    return _result(_replace_run(state, changed, event.nonce), TransitionCode.APPLIED, "run_cancelled")
