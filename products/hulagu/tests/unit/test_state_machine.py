from __future__ import annotations

from dataclasses import replace
from itertools import product

from hulagu.domain.events import (
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
    ProfileConfirmed,
    RunCancelled,
    RunPaused,
    RunResumed,
    SearchRequested,
    WorkerRetry,
)
from hulagu.domain.profile import Profile, ProfileField, ProfileQuestion
from hulagu.domain.state_machine import (
    EnrollmentStatus,
    NonceAction,
    NonceFact,
    RunState,
    RunStatus,
    SearchState,
    TenantState,
    TenantStatus,
    TransitionCode,
    start_enrollment,
    transition_enrollment,
    transition_search,
    transition_tenant,
)

NOW = 100
EXPIRY = 200
NOTICE = "privacy-v1"
TENANT = "tenant-1"


def authority(
    nonce: str,
    action: NonceAction,
    object_id: str,
    version: int,
    *,
    expires_at: int = EXPIRY,
    lifecycle_epoch: int = 0,
    tenant_id: str = TENANT,
) -> NonceFact:
    return NonceFact(
        nonce=nonce,
        tenant_id=tenant_id,
        action=action,
        object_id=object_id,
        version=version,
        lifecycle_epoch=lifecycle_epoch,
        expires_at=expires_at,
    )


def parsed_profile() -> Profile:
    return Profile(
        version=1,
        fields=(ProfileField("role", "engineer", "cv", 0.99),),
    )


def ready_tenant() -> TenantState:
    profile = replace(parsed_profile(), confirmed_version=1)
    return TenantState(
        status=TenantStatus.READY,
        tenant_id=TENANT,
        profile=profile,
        nonce_facts=frozenset(
            {
                authority("delete-request", NonceAction.REQUEST_DELETE, TENANT, 0),
                authority("edit-1", NonceAction.EDIT_FIELD, "role", 1),
            }
        ),
    )


def test_duplicate_start_resumes_same_enrollment() -> None:
    first = start_enrollment(NOTICE, "consent-1", EXPIRY)
    second = start_enrollment(NOTICE, "consent-2", EXPIRY, current=first.state)

    assert second.code is TransitionCode.NOOP
    assert second.state == first.state


def test_consent_decline_erases_provisional_state_without_tenant() -> None:
    enrollment = start_enrollment(NOTICE, "consent-1", EXPIRY).state

    result = transition_enrollment(enrollment, ConsentDeclined(NOTICE, "consent-1", NOW))

    assert result.code is TransitionCode.APPLIED
    assert result.state.status is EnrollmentStatus.DECLINED
    assert result.state.tenant_created is False
    assert result.state.subject_digest is None


def test_stale_notice_version_cannot_create_tenant() -> None:
    enrollment = start_enrollment(NOTICE, "consent-1", EXPIRY).state

    result = transition_enrollment(enrollment, ConsentAccepted("privacy-v0", "consent-1", NOW))

    assert result.code is TransitionCode.INVALID_CALLBACK
    assert result.reason == "stale_notice_version"
    assert result.state == enrollment
    assert result.state.tenant_created is False


def test_tenant_is_created_only_by_valid_consent() -> None:
    enrollment = start_enrollment(NOTICE, "consent-1", EXPIRY).state
    assert enrollment.tenant_created is False

    result = transition_enrollment(enrollment, ConsentAccepted(NOTICE, "consent-1", NOW))

    assert result.state.status is EnrollmentStatus.PROMOTED
    assert result.state.tenant_created is True


def test_stale_duplicate_and_expired_consent_actions_do_not_mutate() -> None:
    enrollment = start_enrollment(NOTICE, "consent-1", EXPIRY).state
    invalid_events = (
        ConsentAccepted(NOTICE, "wrong", NOW),
        ConsentAccepted(NOTICE, "consent-1", EXPIRY + 1),
    )
    for event in invalid_events:
        result = transition_enrollment(enrollment, event)
        assert result.code is TransitionCode.INVALID_CALLBACK
        assert result.state == enrollment

    accepted = transition_enrollment(enrollment, ConsentAccepted(NOTICE, "consent-1", NOW)).state
    duplicate = transition_enrollment(accepted, ConsentAccepted(NOTICE, "consent-1", NOW))
    assert duplicate.code is TransitionCode.NOOP
    assert duplicate.state == accepted


def test_cv_is_rejected_outside_awaiting_cv() -> None:
    tenant = TenantState(status=TenantStatus.INTERVIEWING, profile=parsed_profile())

    result = transition_tenant(tenant, CvReceived("doc-1"))

    assert result.code is TransitionCode.REJECTED
    assert result.reason == "cv_wrong_state"
    assert result.state == tenant


def test_restart_during_interview_preserves_active_question_and_duplicate_answer_is_noop() -> None:
    questions = (
        ProfileQuestion("q-role", "role", True),
        ProfileQuestion("q-comp", "minimum_compensation", False),
    )
    tenant = transition_tenant(
        TenantState(
            status=TenantStatus.PARSING_CV,
            nonce_facts=frozenset(
                {authority("answer-1", NonceAction.ANSWER_QUESTION, "q-role", 1)}
            ),
        ),
        CvParsed(parsed_profile(), questions),
    ).state
    event = AnswerSubmitted("q-role", "staff engineer", "answer-1", NOW, EXPIRY)

    after_answer = transition_tenant(tenant, event).state
    restarted = replace(after_answer)
    duplicate = transition_tenant(restarted, event)

    assert restarted.active_question == questions[1]
    assert duplicate.code is TransitionCode.NOOP
    assert duplicate.state == restarted


def test_search_before_profile_confirmation_is_rejected() -> None:
    tenant = TenantState(
        status=TenantStatus.AWAITING_PROFILE_CONFIRMATION,
        profile=parsed_profile(),
    )
    search = SearchState(
        nonce_facts=frozenset(
            {authority("search-1", NonceAction.REQUEST_SEARCH, "run-1", 1)}
        )
    )

    result = transition_search(
        search, tenant, SearchRequested("run-1", 1, "search-1", NOW, EXPIRY)
    )

    assert result.code is TransitionCode.REJECTED
    assert result.reason == "profile_not_confirmed"
    assert result.state == search


def test_pause_and_resume_before_any_run_return_no_active_run() -> None:
    tenant = ready_tenant()
    search = SearchState()

    for event in (
        RunPaused("run-1", "pause-1", NOW, EXPIRY),
        RunResumed("run-1", "resume-1", NOW, EXPIRY),
    ):
        result = transition_search(search, tenant, event)
        assert result.code is TransitionCode.NO_ACTIVE_RUN
        assert result.reason == "no_active_run"
        assert result.state == search


def test_pause_resume_and_cancel_increment_only_named_run_work_epoch() -> None:
    tenant = ready_tenant()
    search = SearchState(
        runs=(
            RunState("old-run", RunStatus.RESULTS_READY, 7),
            RunState("run-1", RunStatus.SEARCHING, 1),
        ),
        nonce_facts=frozenset(
            {
                authority("pause-1", NonceAction.PAUSE_RUN, "run-1", 1),
                authority("resume-1", NonceAction.RESUME_RUN, "run-1", 2),
                authority("cancel-1", NonceAction.CANCEL_RUN, "run-1", 3),
            }
        ),
    )

    paused = transition_search(search, tenant, RunPaused("run-1", "pause-1", NOW, EXPIRY)).state
    assert paused.run("run-1") == RunState("run-1", RunStatus.PAUSED, 2)
    assert paused.run("old-run") == search.run("old-run")

    resumed = transition_search(paused, tenant, RunResumed("run-1", "resume-1", NOW, EXPIRY)).state
    assert resumed.run("run-1") == RunState("run-1", RunStatus.QUEUED, 3)

    cancelled = transition_search(
        resumed, tenant, RunCancelled("run-1", "cancel-1", NOW, EXPIRY)
    ).state
    assert cancelled.run("run-1") == RunState("run-1", RunStatus.CANCELLED, 4)
    assert cancelled.run("old-run") == search.run("old-run")


def test_second_nonterminal_run_is_rejected() -> None:
    tenant = ready_tenant()
    search = SearchState(
        runs=(RunState("run-1", RunStatus.SEARCHING, 1),),
        nonce_facts=frozenset(
            {authority("search-2", NonceAction.REQUEST_SEARCH, "run-2", 1)}
        ),
    )

    result = transition_search(
        search, tenant, SearchRequested("run-2", 1, "search-2", NOW, EXPIRY)
    )

    assert result.code is TransitionCode.REJECTED
    assert result.reason == "active_run_exists"
    assert result.state == search


def test_delete_requires_two_steps_and_double_confirmation_is_noop() -> None:
    tenant = ready_tenant()
    pending = transition_tenant(
        tenant,
        DeleteRequested("delete-request", NOW, EXPIRY, "delete-decision", EXPIRY),
    ).state

    assert pending.status is TenantStatus.DELETE_PENDING
    request_replay = transition_tenant(pending, DeleteConfirmed("delete-request", NOW))
    first = transition_tenant(pending, DeleteConfirmed("delete-decision", NOW)).state
    second = transition_tenant(first, DeleteConfirmed("delete-decision", NOW))

    assert request_replay.code is TransitionCode.NOOP
    assert request_replay.state == pending
    assert first.status is TenantStatus.DELETING
    assert first.lifecycle_epoch == tenant.lifecycle_epoch + 1
    assert first.profile == tenant.profile
    assert not first.nonce_facts
    assert second.code is TransitionCode.NOOP
    assert second.state == first

    completed = transition_tenant(first, DeletionCompleted(first.lifecycle_epoch))
    stale_completion = transition_tenant(first, DeletionCompleted(tenant.lifecycle_epoch))

    assert completed.code is TransitionCode.APPLIED
    assert completed.state.status is TenantStatus.DELETED
    assert completed.state.profile is None
    assert stale_completion.code is TransitionCode.REJECTED
    assert stale_completion.state == first


def test_delete_cancellation_restores_prior_state() -> None:
    tenant = ready_tenant()
    pending = transition_tenant(
        tenant,
        DeleteRequested("delete-request", NOW, EXPIRY, "delete-decision", EXPIRY),
    ).state

    result = transition_tenant(pending, DeleteCancelled("delete-decision", NOW))

    assert result.code is TransitionCode.APPLIED
    assert result.state.status is TenantStatus.READY
    assert result.state.delete_nonce is None


def test_worker_retry_is_deterministic_or_terminal() -> None:
    tenant_retry = TenantState(
        status=TenantStatus.RETRY_WAIT,
        retry_target=TenantStatus.PARSING_CV,
        retry_count=0,
        max_retries=1,
    )
    retried = transition_tenant(tenant_retry, WorkerRetry()).state
    exhausted = transition_tenant(replace(tenant_retry, retry_count=1), WorkerRetry()).state

    assert retried.status is TenantStatus.PARSING_CV
    assert retried.retry_count == 1
    assert exhausted.status is TenantStatus.NEEDS_OPERATOR

    for worker_state in (RunStatus.SEARCHING, RunStatus.PUBLISHING):
        search = SearchState(
            runs=(RunState("run-1", RunStatus.RETRY_WAIT, 1, retry_target=worker_state),)
        )
        result = transition_search(search, ready_tenant(), WorkerRetry(run_id="run-1"))
        assert result.state.run("run-1").status is worker_state


def test_profile_edit_invalidates_confirmation_and_increments_version() -> None:
    tenant = ready_tenant()

    result = transition_tenant(
        tenant,
        FieldEdited("role", "principal engineer", 1, "edit-1", NOW, EXPIRY),
    )

    assert result.code is TransitionCode.APPLIED
    assert result.state.status is TenantStatus.AWAITING_PROFILE_CONFIRMATION
    assert result.state.profile is not None
    assert result.state.profile.version == 2
    assert result.state.profile.confirmed_version is None


def test_event_supplied_expiry_cannot_extend_persisted_authority() -> None:
    tenant = ready_tenant()

    result = transition_tenant(
        tenant,
        FieldEdited("role", "principal engineer", 1, "edit-1", 1_000, 2_000),
    )

    assert result.code is TransitionCode.INVALID_CALLBACK
    assert result.reason == "expired_callback"
    assert result.state == tenant


def test_edit_nonce_cannot_request_deletion() -> None:
    tenant = ready_tenant()

    result = transition_tenant(
        tenant,
        DeleteRequested("edit-1", NOW, EXPIRY, "delete-decision", EXPIRY),
    )

    assert result.code is TransitionCode.INVALID_CALLBACK
    assert result.state == tenant


def test_pause_nonce_cannot_cancel_run() -> None:
    tenant = ready_tenant()
    search = SearchState(
        runs=(RunState("run-1", RunStatus.SEARCHING, 1),),
        nonce_facts=frozenset(
            {authority("pause-1", NonceAction.PAUSE_RUN, "run-1", 1)}
        ),
    )

    result = transition_search(
        search,
        tenant,
        RunCancelled("run-1", "pause-1", NOW, EXPIRY),
    )

    assert result.code is TransitionCode.INVALID_CALLBACK
    assert result.state == search


def test_generated_tenant_profile_sequences_cannot_bypass_confirmation_or_authority() -> None:
    baseline = TenantState(
        status=TenantStatus.AWAITING_PROFILE_CONFIRMATION,
        tenant_id=TENANT,
        profile=parsed_profile(),
        nonce_facts=frozenset(
            {
                authority("confirm-good", NonceAction.CONFIRM_PROFILE, "profile", 1),
                authority("edit-good", NonceAction.EDIT_FIELD, "role", 1),
                authority("edit-action", NonceAction.EDIT_FIELD, "profile", 1),
                authority("wrong-version", NonceAction.CONFIRM_PROFILE, "profile", 1),
                authority("wrong-object", NonceAction.EDIT_FIELD, "location", 1),
                authority("expired", NonceAction.EDIT_FIELD, "role", 1, expires_at=NOW - 1),
                authority(
                    "wrong-tenant",
                    NonceAction.EDIT_FIELD,
                    "role",
                    1,
                    tenant_id="tenant-2",
                ),
                authority(
                    "wrong-epoch",
                    NonceAction.EDIT_FIELD,
                    "role",
                    1,
                    lifecycle_epoch=1,
                ),
            }
        ),
    )
    invalid_events = (
        ProfileConfirmed(1, "edit-action", NOW, EXPIRY),
        ProfileConfirmed(2, "wrong-version", NOW, EXPIRY),
        FieldEdited("role", "principal", 1, "wrong-object", NOW, EXPIRY),
        FieldEdited("role", "principal", 1, "expired", NOW, 10_000),
        FieldEdited("role", "principal", 1, "wrong-tenant", NOW, EXPIRY),
        FieldEdited("role", "principal", 1, "wrong-epoch", NOW, EXPIRY),
        DeleteRequested("edit-good", NOW, EXPIRY, "decision", EXPIRY),
    )
    for sequence in product(invalid_events, repeat=2):
        state = baseline
        for event in sequence:
            state = transition_tenant(state, event).state
        assert state == baseline

    valid_events = (
        ProfileConfirmed(1, "confirm-good", NOW, EXPIRY),
        FieldEdited("role", "principal", 1, "edit-good", NOW, EXPIRY),
    )
    for sequence in product(valid_events, repeat=2):
        state = baseline
        for event in sequence:
            state = transition_tenant(state, event).state
        assert state.profile is not None
        if state.status is TenantStatus.READY:
            assert state.profile.confirmed_version == state.profile.version
        if state.profile.version > 1:
            assert state.status is TenantStatus.AWAITING_PROFILE_CONFIRMATION
            assert state.profile.confirmed_version is None


def test_enrollment_event_sequences_never_bypass_versioned_consent() -> None:
    events = (
        ConsentAccepted(NOTICE, "consent-1", NOW),
        ConsentAccepted("stale", "consent-1", NOW),
        ConsentDeclined(NOTICE, "consent-1", NOW),
    )
    for sequence in product(events, repeat=3):
        state = start_enrollment(NOTICE, "consent-1", EXPIRY).state
        for event in sequence:
            state = transition_enrollment(state, event).state
        assert state.tenant_created is (state.status is EnrollmentStatus.PROMOTED)
        if state.tenant_created:
            first_current_notice_event = next(
                event for event in sequence if event.notice_version == NOTICE
            )
            assert first_current_notice_event == ConsentAccepted(NOTICE, "consent-1", NOW)


def test_deleted_tenant_never_reactivates_for_generated_event_sequences() -> None:
    deleted = TenantState(status=TenantStatus.DELETED, lifecycle_epoch=3)
    events = (
        CvReceived("doc-1"),
        CvParseFailed(),
        DeleteRequested("delete-2", NOW, EXPIRY, "delete-decision-2", EXPIRY),
        WorkerRetry(),
    )
    for sequence in product(events, repeat=3):
        state = deleted
        for event in sequence:
            state = transition_tenant(state, event).state
        assert state == deleted


def test_generated_search_actions_cannot_mutate_absent_or_different_run() -> None:
    tenant = ready_tenant()
    baseline = SearchState(
        runs=(RunState("run-1", RunStatus.SEARCHING, 4),),
        nonce_facts=frozenset(
            {
                authority("pause-action", NonceAction.PAUSE_RUN, "run-1", 4),
                authority("wrong-object", NonceAction.CANCEL_RUN, "other-run", 4),
                authority("wrong-version", NonceAction.CANCEL_RUN, "run-1", 3),
                authority(
                    "expired-cancel",
                    NonceAction.CANCEL_RUN,
                    "run-1",
                    4,
                    expires_at=NOW - 1,
                ),
                authority(
                    "wrong-tenant",
                    NonceAction.CANCEL_RUN,
                    "run-1",
                    4,
                    tenant_id="tenant-2",
                ),
                authority(
                    "wrong-epoch",
                    NonceAction.CANCEL_RUN,
                    "run-1",
                    4,
                    lifecycle_epoch=1,
                ),
            }
        ),
    )
    events = (
        RunPaused("missing", "p-1", NOW, EXPIRY),
        RunCancelled("missing", "c-1", NOW, EXPIRY),
        RunCancelled("run-1", "pause-action", NOW, EXPIRY),
        RunCancelled("run-1", "wrong-object", NOW, EXPIRY),
        RunCancelled("run-1", "wrong-version", NOW, EXPIRY),
        RunCancelled("run-1", "expired-cancel", NOW, 10_000),
        RunCancelled("run-1", "wrong-tenant", NOW, EXPIRY),
        RunCancelled("run-1", "wrong-epoch", NOW, EXPIRY),
    )
    for sequence in product(events, repeat=2):
        state = baseline
        for event in sequence:
            state = transition_search(state, tenant, event).state
        assert state == baseline


def test_all_declared_worker_retry_states_have_a_deterministic_route() -> None:
    terminal = {RunStatus.PARTIAL, RunStatus.FAILED, RunStatus.NEEDS_OPERATOR}
    for target in (RunStatus.SEARCHING, RunStatus.PUBLISHING):
        for retry_count in range(3):
            state = SearchState(
                runs=(
                    RunState(
                        "run-1",
                        RunStatus.RETRY_WAIT,
                        1,
                        retry_target=target,
                        retry_count=retry_count,
                        max_retries=2,
                    ),
                )
            )
            result = transition_search(state, ready_tenant(), WorkerRetry(run_id="run-1"))
            next_status = result.state.run("run-1").status
            assert next_status is target or next_status in terminal
