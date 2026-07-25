"""Pure restartable customer state machine for Hulagu.

This module intentionally contains only dataclasses, enums, and transition
functions. It does not import Telegram, storage, runtime, provider, model, or
filesystem authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum

from hulagu.domain.profile import (
    DEFAULT_PROFILE_QUESTIONS,
    ProfileField,
    ProfileFieldSource,
    next_question_after,
    question_by_id,
    required_question_ids,
)


class ProfileStatus(StrEnum):
    NOT_STARTED = "not_started"
    INTERVIEWING = "interviewing"
    CONFIRMED = "confirmed"


class SearchRunStatus(StrEnum):
    REQUESTED = "requested"
    RUNNING = "running"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

    @classmethod
    def nonterminal(cls) -> frozenset[SearchRunStatus]:
        return frozenset({cls.REQUESTED, cls.RUNNING, cls.PAUSED})

    @classmethod
    def terminal(cls) -> frozenset[SearchRunStatus]:
        return frozenset({cls.CANCELLED, cls.SUCCEEDED, cls.FAILED})


class WorkerState(StrEnum):
    IDLE = "idle"
    QUEUED = "queued"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class TransitionResult:
    code: str
    mutated: bool
    message: str = ""


@dataclass(frozen=True, slots=True)
class SearchRun:
    run_id: str
    status: SearchRunStatus
    work_epoch: int
    retry_count: int = 0
    last_error_code: str | None = None


@dataclass(frozen=True, slots=True)
class CustomerState:
    notice_version: str | None = None
    consented_notice_version: str | None = None
    consent_declined: bool = False
    tenant_created: bool = False
    tenant_lifecycle_epoch: int = 0
    deleted: bool = False
    delete_pending: bool = False
    cv_document_id: str | None = None
    profile_status: ProfileStatus = ProfileStatus.NOT_STARTED
    active_question_id: str | None = None
    profile_answers: dict[str, ProfileField] = field(default_factory=dict)
    skipped_optional_fields: frozenset[str] = frozenset()
    profile_revision: int = 0
    profile_confirmation_epoch: int = 0
    expected_action_nonce: str | None = None
    consumed_action_nonces: frozenset[str] = frozenset()
    delete_action_nonce: str | None = None
    active_run: SearchRun | None = None
    completed_runs: tuple[SearchRun, ...] = ()
    work_epoch: int = 0
    worker_state: WorkerState = WorkerState.IDLE

    @classmethod
    def initial(cls) -> CustomerState:
        return cls()


def start(
    state: CustomerState,
    *,
    notice_version: str,
    action_nonce: str,
) -> tuple[CustomerState, TransitionResult]:
    if state.deleted:
        return _unchanged(state, "already_deleted")
    if state.notice_version == notice_version and state.expected_action_nonce == action_nonce:
        return _unchanged(state, "duplicate_start")
    if state.tenant_created:
        return _unchanged(state, "tenant_already_created")
    return (
        replace(
            state,
            notice_version=notice_version,
            consent_declined=False,
            expected_action_nonce=action_nonce,
        ),
        TransitionResult("notice_sent", True),
    )


def consent(
    state: CustomerState,
    *,
    notice_version: str,
    action_nonce: str,
) -> tuple[CustomerState, TransitionResult]:
    if state.deleted:
        return _unchanged(state, "already_deleted")
    if action_nonce in state.consumed_action_nonces:
        return _unchanged(state, "stale_or_duplicate_action_nonce")
    nonce_error = _validate_expected_nonce(state, action_nonce)
    if nonce_error is not None:
        return _unchanged(state, nonce_error)
    if state.notice_version is None:
        return _unchanged(state, "notice_required")
    if notice_version != state.notice_version:
        return _unchanged(state, "stale_notice_version")
    if state.consent_declined:
        return _unchanged(state, "consent_declined")
    if state.tenant_created:
        return _unchanged(state, "tenant_already_created")
    return (
        replace(
            state,
            consented_notice_version=notice_version,
            tenant_created=True,
            tenant_lifecycle_epoch=state.tenant_lifecycle_epoch + 1,
            consumed_action_nonces=state.consumed_action_nonces | frozenset({action_nonce}),
            expected_action_nonce=None,
        ),
        TransitionResult("tenant_created", True),
    )


def decline_consent(
    state: CustomerState,
    *,
    notice_version: str,
    action_nonce: str,
) -> tuple[CustomerState, TransitionResult]:
    if state.deleted:
        return _unchanged(state, "already_deleted")
    if action_nonce in state.consumed_action_nonces:
        return _unchanged(state, "stale_or_duplicate_action_nonce")
    nonce_error = _validate_expected_nonce(state, action_nonce)
    if nonce_error is not None:
        return _unchanged(state, nonce_error)
    if state.notice_version != notice_version:
        return _unchanged(state, "stale_notice_version")
    return (
        replace(
            state,
            consent_declined=True,
            consumed_action_nonces=state.consumed_action_nonces | frozenset({action_nonce}),
            expected_action_nonce=None,
        ),
        TransitionResult("consent_declined", True),
    )


def record_cv(
    state: CustomerState,
    *,
    document_id: str,
) -> tuple[CustomerState, TransitionResult]:
    if not state.tenant_created or state.deleted:
        return _unchanged(state, "cv_wrong_state")
    if state.profile_status is ProfileStatus.CONFIRMED:
        return _unchanged(state, "cv_wrong_state")
    return replace(state, cv_document_id=document_id), TransitionResult("cv_recorded", True)


def start_interview(state: CustomerState) -> tuple[CustomerState, TransitionResult]:
    if not state.tenant_created or state.deleted:
        return _unchanged(state, "tenant_required")
    if state.profile_status is ProfileStatus.CONFIRMED:
        return _unchanged(state, "profile_already_confirmed")
    active_question = state.active_question_id or DEFAULT_PROFILE_QUESTIONS[0].id
    return (
        replace(
            state,
            profile_status=ProfileStatus.INTERVIEWING,
            active_question_id=active_question,
        ),
        TransitionResult("interview_started", True),
    )


def resume_interview(state: CustomerState) -> tuple[CustomerState, TransitionResult]:
    if state.profile_status is not ProfileStatus.INTERVIEWING or state.active_question_id is None:
        return _unchanged(state, "no_active_question")
    return state, TransitionResult("interview_resumed", False)


def answer_question(
    state: CustomerState,
    question_id: str,
    answer: str,
) -> tuple[CustomerState, TransitionResult]:
    if state.deleted or state.profile_status is not ProfileStatus.INTERVIEWING:
        return _unchanged(state, "no_active_question")
    if state.active_question_id != question_id:
        return _unchanged(state, "no_active_question")
    if not answer:
        return _unchanged(state, "empty_answer_rejected")
    next_question = next_question_after(DEFAULT_PROFILE_QUESTIONS, question_id)
    answers = dict(state.profile_answers)
    answers[question_id] = ProfileField(
        value=answer,
        source=ProfileFieldSource.INTERVIEW,
        confidence=1.0,
        source_span=f"answer:{question_id}",
    )
    return (
        replace(
            state,
            profile_answers=answers,
            active_question_id=next_question.id if next_question else None,
            profile_revision=state.profile_revision + 1,
        ),
        TransitionResult("answer_recorded", True),
    )


def skip_question(state: CustomerState, question_id: str) -> tuple[CustomerState, TransitionResult]:
    if state.deleted or state.profile_status is not ProfileStatus.INTERVIEWING:
        return _unchanged(state, "no_active_question")
    if state.active_question_id != question_id:
        return _unchanged(state, "no_active_question")
    question = question_by_id(question_id)
    if question.required:
        return _unchanged(state, "required_field_skip_rejected")
    next_question = next_question_after(DEFAULT_PROFILE_QUESTIONS, question_id)
    return (
        replace(
            state,
            skipped_optional_fields=state.skipped_optional_fields | frozenset({question_id}),
            active_question_id=next_question.id if next_question else None,
            profile_revision=state.profile_revision + 1,
        ),
        TransitionResult("optional_field_skipped", True),
    )


def confirm_profile(state: CustomerState) -> tuple[CustomerState, TransitionResult]:
    if state.deleted or not state.tenant_created:
        return _unchanged(state, "tenant_required")
    if state.profile_status is ProfileStatus.CONFIRMED:
        return _unchanged(state, "profile_already_confirmed")
    missing = required_question_ids() - set(state.profile_answers)
    if state.cv_document_id is None:
        missing = missing | frozenset({"cv_document"})
    if missing:
        return _unchanged(state, "profile_incomplete")
    return (
        replace(
            state,
            profile_status=ProfileStatus.CONFIRMED,
            active_question_id=None,
            profile_confirmation_epoch=state.profile_confirmation_epoch + 1,
        ),
        TransitionResult("profile_confirmed", True),
    )


def edit_profile(
    state: CustomerState,
    *,
    field_id: str,
    value: str,
) -> tuple[CustomerState, TransitionResult]:
    if state.deleted or not state.tenant_created:
        return _unchanged(state, "tenant_required")
    if not value:
        return _unchanged(state, "empty_answer_rejected")
    question_by_id(field_id)
    answers = dict(state.profile_answers)
    answers[field_id] = ProfileField(
        value=value,
        source=ProfileFieldSource.CUSTOMER_EDIT,
        confidence=1.0,
        source_span=f"edit:{field_id}",
    )
    return (
        replace(
            state,
            profile_answers=answers,
            profile_status=ProfileStatus.INTERVIEWING,
            active_question_id=None,
            profile_revision=state.profile_revision + 1,
            profile_confirmation_epoch=state.profile_confirmation_epoch + 1,
        ),
        TransitionResult("profile_edited_confirmation_invalidated", True),
    )


def request_search(
    state: CustomerState,
    *,
    run_id: str = "run-1",
) -> tuple[CustomerState, TransitionResult]:
    if state.deleted:
        return _unchanged(state, "already_deleted")
    if state.profile_status is not ProfileStatus.CONFIRMED:
        return _unchanged(state, "profile_confirmation_required")
    if state.active_run is not None and state.active_run.status in SearchRunStatus.nonterminal():
        return _unchanged(state, "nonterminal_run_exists")
    run = SearchRun(run_id=run_id, status=SearchRunStatus.REQUESTED, work_epoch=state.work_epoch)
    return (
        replace(state, active_run=run, worker_state=WorkerState.QUEUED),
        TransitionResult("search_requested", True),
    )


def start_run(state: CustomerState, *, run_id: str) -> tuple[CustomerState, TransitionResult]:
    active_run = state.active_run
    if active_run is None or active_run.run_id != run_id or state.deleted:
        return _unchanged(state, "no_active_run")
    if active_run.status is SearchRunStatus.REQUESTED:
        return (
            replace(
                state,
                active_run=replace(active_run, status=SearchRunStatus.RUNNING),
                worker_state=WorkerState.RUNNING,
            ),
            TransitionResult("run_started", True),
        )
    if active_run.status is SearchRunStatus.RUNNING:
        next_epoch = state.work_epoch + 1
        return (
            replace(
                state,
                active_run=replace(
                    active_run,
                    status=SearchRunStatus.PAUSED,
                    work_epoch=next_epoch,
                ),
                work_epoch=next_epoch,
            ),
            TransitionResult("run_paused", True),
        )
    return _unchanged(state, "run_not_pausable")


def resume_run(state: CustomerState, *, run_id: str) -> tuple[CustomerState, TransitionResult]:
    active_run = state.active_run
    if active_run is None or active_run.run_id != run_id or state.deleted:
        return _unchanged(state, "no_active_run")
    if active_run.status is not SearchRunStatus.PAUSED:
        return _unchanged(state, "run_not_resumable")
    next_epoch = state.work_epoch + 1
    return (
        replace(
            state,
            active_run=replace(active_run, status=SearchRunStatus.RUNNING, work_epoch=next_epoch),
            work_epoch=next_epoch,
            worker_state=WorkerState.RUNNING,
        ),
        TransitionResult("run_resumed", True),
    )


def cancel_run(state: CustomerState, *, run_id: str) -> tuple[CustomerState, TransitionResult]:
    active_run = state.active_run
    if active_run is None or active_run.run_id != run_id or state.deleted:
        return _unchanged(state, "no_active_run")
    cancelled = replace(active_run, status=SearchRunStatus.CANCELLED)
    return (
        replace(
            state,
            active_run=None,
            completed_runs=state.completed_runs + (cancelled,),
            worker_state=WorkerState.CANCELLED,
        ),
        TransitionResult("run_cancelled", True),
    )


def worker_failed(
    state: CustomerState,
    *,
    error_code: str,
) -> tuple[CustomerState, TransitionResult]:
    active_run = state.active_run
    if active_run is None or active_run.status not in {
        SearchRunStatus.REQUESTED,
        SearchRunStatus.RUNNING,
    }:
        return _unchanged(state, "no_active_run")
    return (
        replace(
            state,
            active_run=replace(
                active_run,
                status=SearchRunStatus.RUNNING,
                retry_count=active_run.retry_count + 1,
                last_error_code=error_code,
            ),
            worker_state=WorkerState.RETRY_WAIT,
        ),
        TransitionResult("worker_retry_scheduled", True),
    )


def retry_worker(state: CustomerState) -> tuple[CustomerState, TransitionResult]:
    active_run = state.active_run
    if active_run is None or state.worker_state is not WorkerState.RETRY_WAIT:
        return _unchanged(state, "worker_not_retryable")
    return (
        replace(
            state,
            active_run=replace(active_run, status=SearchRunStatus.RUNNING),
            worker_state=WorkerState.RUNNING,
        ),
        TransitionResult("worker_retry_started", True),
    )


def worker_succeeded(state: CustomerState) -> tuple[CustomerState, TransitionResult]:
    active_run = state.active_run
    if active_run is None or active_run.status not in {
        SearchRunStatus.REQUESTED,
        SearchRunStatus.RUNNING,
    }:
        return _unchanged(state, "no_active_run")
    succeeded = replace(active_run, status=SearchRunStatus.SUCCEEDED)
    return (
        replace(
            state,
            active_run=None,
            completed_runs=state.completed_runs + (succeeded,),
            worker_state=WorkerState.SUCCEEDED,
        ),
        TransitionResult("worker_succeeded", True),
    )


def confirm_delete(
    state: CustomerState,
    *,
    action_nonce: str,
    confirmed: bool,
    expired: bool = False,
) -> tuple[CustomerState, TransitionResult]:
    if state.deleted:
        return _unchanged(state, "already_deleted")
    if expired or action_nonce in state.consumed_action_nonces:
        return _unchanged(state, "invalid_or_expired_callback")
    if not confirmed:
        return (
            replace(state, delete_pending=True, delete_action_nonce=action_nonce),
            TransitionResult("delete_confirmation_required", True),
        )
    if not state.delete_pending or state.delete_action_nonce != action_nonce:
        return _unchanged(state, "invalid_or_expired_callback")
    return (
        replace(
            state,
            deleted=True,
            delete_pending=False,
            delete_action_nonce=None,
            tenant_created=False,
            active_run=None,
            worker_state=WorkerState.CANCELLED,
            tenant_lifecycle_epoch=state.tenant_lifecycle_epoch + 1,
            consumed_action_nonces=state.consumed_action_nonces | frozenset({action_nonce}),
        ),
        TransitionResult("tenant_deleted", True),
    )


def cancel_delete(state: CustomerState) -> tuple[CustomerState, TransitionResult]:
    if not state.delete_pending:
        return _unchanged(state, "no_delete_pending")
    return (
        replace(state, delete_pending=False, delete_action_nonce=None),
        TransitionResult("delete_cancelled", True),
    )


def _validate_expected_nonce(state: CustomerState, action_nonce: str) -> str | None:
    if state.expected_action_nonce is None:
        return "notice_required"
    if state.expected_action_nonce != action_nonce:
        return "invalid_action_nonce"
    return None


def _unchanged(state: CustomerState, code: str) -> tuple[CustomerState, TransitionResult]:
    return state, TransitionResult(code, False)
