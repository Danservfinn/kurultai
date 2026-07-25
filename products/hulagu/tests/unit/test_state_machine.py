from __future__ import annotations

from dataclasses import replace

from hypothesis import given, settings
from hypothesis import strategies as st

from hulagu.domain.profile import DEFAULT_PROFILE_QUESTIONS, REQUIRED_PROFILE_FIELD_IDS
from hulagu.domain.state_machine import (
    CustomerState,
    ProfileStatus,
    SearchRunStatus,
    WorkerState,
    answer_question,
    cancel_delete,
    cancel_run,
    confirm_delete,
    confirm_profile,
    consent,
    decline_consent,
    edit_profile,
    record_cv,
    request_search,
    resume_interview,
    resume_run,
    retry_worker,
    skip_question,
    start,
    start_interview,
    start_run,
    worker_failed,
    worker_succeeded,
)


def test_duplicate_start_is_idempotent_and_does_not_create_tenant() -> None:
    state = CustomerState.initial()
    started, first = start(state, notice_version="2026-07-25", action_nonce="n1")
    repeated, second = start(started, notice_version="2026-07-25", action_nonce="n1")

    assert first.code == "notice_sent"
    assert second.code == "duplicate_start"
    assert repeated == started
    assert not repeated.tenant_created


def test_consent_decline_and_stale_notice_do_not_create_tenant() -> None:
    state, _ = start(CustomerState.initial(), notice_version="v2", action_nonce="n1")

    declined, declined_result = decline_consent(state, notice_version="v2", action_nonce="n1")
    stale, stale_result = consent(state, notice_version="v1", action_nonce="n1")

    assert declined_result.code == "consent_declined"
    assert declined.consent_declined
    assert not declined.tenant_created
    assert stale_result.code == "stale_notice_version"
    assert stale == state


def test_tenant_cannot_be_created_before_versioned_consent() -> None:
    state = CustomerState.initial()

    unchanged, result = consent(state, notice_version="v1", action_nonce="n1")

    assert result.code == "notice_required"
    assert unchanged == state
    assert not unchanged.tenant_created


def test_stale_or_duplicate_action_nonce_cannot_mutate_state() -> None:
    state, _ = start(CustomerState.initial(), notice_version="v1", action_nonce="n1")
    consented, first = consent(state, notice_version="v1", action_nonce="n1")
    replayed, replay = consent(consented, notice_version="v1", action_nonce="n1")
    wrong_nonce, wrong = consent(state, notice_version="v1", action_nonce="other")

    assert first.code == "tenant_created"
    assert replay.code == "stale_or_duplicate_action_nonce"
    assert replayed == consented
    assert wrong.code == "invalid_action_nonce"
    assert wrong_nonce == state


def test_cv_only_records_after_consent_before_or_during_interview() -> None:
    fresh = CustomerState.initial()
    blocked, blocked_result = record_cv(fresh, document_id="doc-1")
    consented = _consented_state()
    with_cv, ok = record_cv(consented, document_id="doc-1")
    confirmed, _ = confirm_profile(_answered_required(with_cv))
    after_confirm, after_confirm_result = record_cv(confirmed, document_id="doc-2")

    assert blocked_result.code == "cv_wrong_state"
    assert blocked == fresh
    assert ok.code == "cv_recorded"
    assert with_cv.cv_document_id == "doc-1"
    assert after_confirm_result.code == "cv_wrong_state"
    assert after_confirm == confirmed


def test_answer_requires_active_question_and_restart_preserves_interview_progress() -> None:
    consented = _consented_state()
    unchanged, no_question = answer_question(consented, "target_roles", "ML Engineer")
    interviewing, _ = start_interview(consented)
    answered, answered_result = answer_question(interviewing, "target_roles", "ML Engineer")
    restarted, restarted_result = resume_interview(answered)

    assert no_question.code == "no_active_question"
    assert unchanged == consented
    assert answered_result.code == "answer_recorded"
    assert answered.profile_answers["target_roles"].value == "ML Engineer"
    assert answered.profile_answers["target_roles"].source.value == "interview"
    assert answered.profile_answers["target_roles"].confidence == 1.0
    assert restarted_result.code == "interview_resumed"
    assert restarted == answered


def test_optional_skip_advances_and_required_skip_is_rejected() -> None:
    interviewing, _ = start_interview(_consented_state())
    required_skip, required_result = skip_question(interviewing, "target_roles")
    with_required, _ = answer_question(interviewing, "target_roles", "ML Engineer")
    optional_question = _advance_until_active_question(with_required, "minimum_compensation")
    optional_skip, optional_result = skip_question(optional_question, "minimum_compensation")

    assert required_result.code == "required_field_skip_rejected"
    assert required_skip == interviewing
    assert optional_result.code == "optional_field_skipped"
    assert "minimum_compensation" in optional_skip.skipped_optional_fields


def test_search_requires_profile_confirmation_and_rejects_second_nonterminal_run() -> None:
    consented = _consented_state()
    blocked, blocked_result = request_search(consented)
    confirmed, _ = confirm_profile(_answered_required(consented))
    requested, request_result = request_search(confirmed)
    duplicate, duplicate_result = request_search(requested)

    assert blocked_result.code == "profile_confirmation_required"
    assert blocked == consented
    assert request_result.code == "search_requested"
    assert requested.active_run is not None
    assert duplicate_result.code == "nonterminal_run_exists"
    assert duplicate == requested


def test_profile_confirmation_rejects_legacy_three_field_subset() -> None:
    state = _consented_state()
    state, _ = record_cv(state, document_id="doc-1")
    state, _ = start_interview(state)
    legacy_fields = {"target_roles", "locations", "work_mode"}
    for question in DEFAULT_PROFILE_QUESTIONS:
        if question.id in legacy_fields:
            state = replace(state, active_question_id=question.id)
            state, _ = answer_question(state, question.id, f"answer-{question.id}")

    unchanged, result = confirm_profile(state)

    assert result.code == "profile_incomplete"
    assert unchanged.profile_status is ProfileStatus.INTERVIEWING
    assert set(unchanged.profile_answers) == legacy_fields
    assert REQUIRED_PROFILE_FIELD_IDS - set(unchanged.profile_answers)


def test_repeated_profile_after_confirmation_is_idempotent() -> None:
    state = CustomerState.initial()
    for event in ["start", "consent", "profile", "profile"]:
        state = _apply_symbolic_event(state, event)

    repeated, result = confirm_profile(state)

    assert result.code == "profile_already_confirmed"
    assert repeated == state
    assert state.profile_status is ProfileStatus.CONFIRMED


def test_pause_resume_before_any_run_returns_no_active_run() -> None:
    confirmed, _ = confirm_profile(_answered_required(_consented_state()))

    paused, pause_result = start_run(confirmed, run_id="missing")
    resumed, resume_result = resume_run(confirmed, run_id="missing")

    assert pause_result.code == "no_active_run"
    assert resume_result.code == "no_active_run"
    assert paused == confirmed
    assert resumed == confirmed


def test_pause_resume_one_active_run_changes_work_epoch_only_for_that_run() -> None:
    running = _running_state(run_id="run-1")

    paused, pause_result = start_run(running, run_id="run-1")
    resumed, resume_result = resume_run(paused, run_id="run-1")
    wrong, wrong_result = resume_run(paused, run_id="run-2")

    assert pause_result.code == "run_paused"
    assert paused.active_run is not None
    assert paused.active_run.status is SearchRunStatus.PAUSED
    assert paused.work_epoch == running.work_epoch + 1
    assert resume_result.code == "run_resumed"
    assert resumed.active_run is not None
    assert resumed.active_run.status is SearchRunStatus.RUNNING
    assert resumed.work_epoch == paused.work_epoch + 1
    assert wrong_result.code == "no_active_run"
    assert wrong == paused


def test_cancel_run_moves_active_run_to_terminal_history() -> None:
    running = _running_state(run_id="run-1")

    cancelled, result = cancel_run(running, run_id="run-1")

    assert result.code == "run_cancelled"
    assert cancelled.active_run is None
    assert cancelled.completed_runs[-1].status is SearchRunStatus.CANCELLED


def test_double_delete_confirmation_and_delete_cancellation() -> None:
    confirmed, _ = confirm_profile(_answered_required(_consented_state()))
    asked, ask_result = confirm_delete(confirmed, action_nonce="del-1", confirmed=False)
    cancelled, cancel_result = cancel_delete(asked)
    deleted, delete_result = confirm_delete(asked, action_nonce="del-1", confirmed=True)
    repeated, repeated_result = confirm_delete(deleted, action_nonce="del-2", confirmed=True)

    assert ask_result.code == "delete_confirmation_required"
    assert cancel_result.code == "delete_cancelled"
    assert cancelled.delete_pending is False
    assert delete_result.code == "tenant_deleted"
    assert deleted.deleted
    assert deleted.tenant_lifecycle_epoch == confirmed.tenant_lifecycle_epoch + 1
    assert repeated_result.code == "already_deleted"
    assert repeated == deleted


def test_worker_retry_success_and_terminal_routes_are_deterministic() -> None:
    running = _running_state(run_id="run-1")
    failed, fail_result = worker_failed(running, error_code="timeout")
    retrying, retry_result = retry_worker(failed)
    succeeded, success_result = worker_succeeded(retrying)
    retry_after_terminal, terminal_retry = retry_worker(succeeded)

    assert fail_result.code == "worker_retry_scheduled"
    assert failed.worker_state is WorkerState.RETRY_WAIT
    assert retry_result.code == "worker_retry_started"
    assert retrying.worker_state is WorkerState.RUNNING
    assert success_result.code == "worker_succeeded"
    assert succeeded.active_run is None
    assert succeeded.completed_runs[-1].status is SearchRunStatus.SUCCEEDED
    assert terminal_retry.code == "worker_not_retryable"
    assert retry_after_terminal == succeeded


def test_invalid_or_expired_callback_cannot_mutate_state() -> None:
    state, _ = start(CustomerState.initial(), notice_version="v1", action_nonce="n1")

    invalid, invalid_result = consent(state, notice_version="v1", action_nonce="bad")
    expired, expired_result = confirm_delete(state, action_nonce="expired", confirmed=True, expired=True)

    assert invalid_result.code == "invalid_action_nonce"
    assert invalid == state
    assert expired_result.code == "invalid_or_expired_callback"
    assert expired == state


def test_profile_edit_invalidates_confirmation() -> None:
    confirmed, _ = confirm_profile(_answered_required(_consented_state()))

    edited, result = edit_profile(confirmed, field_id="target_roles", value="Staff ML Engineer")

    assert result.code == "profile_edited_confirmation_invalidated"
    assert edited.profile_status is ProfileStatus.INTERVIEWING
    assert edited.profile_answers["target_roles"].value == "Staff ML Engineer"
    assert edited.profile_answers["target_roles"].source.value == "customer_edit"
    assert edited.profile_confirmation_epoch == confirmed.profile_confirmation_epoch + 1


_SYMBOLIC_EVENTS = (
    "start",
    "decline",
    "consent",
    "profile",
    "search",
    "pause",
    "resume",
    "cancel",
    "fail",
    "retry",
    "success",
    "delete",
)


@given(st.lists(st.sampled_from(_SYMBOLIC_EVENTS), min_size=0, max_size=40))
@settings(max_examples=150, deadline=None)
def test_core_invariants_hold_for_generated_event_sequences(sequence: list[str]) -> None:
    state = CustomerState.initial()
    for event in sequence:
        state = _apply_symbolic_event(state, event)
        _assert_core_invariants(state)


def _consented_state() -> CustomerState:
    state, _ = start(CustomerState.initial(), notice_version="v1", action_nonce="n1")
    state, result = consent(state, notice_version="v1", action_nonce="n1")
    assert result.code == "tenant_created"
    return state


def _answered_required(state: CustomerState) -> CustomerState:
    state, _ = record_cv(state, document_id="doc-1")
    state, _ = start_interview(state)
    for question in DEFAULT_PROFILE_QUESTIONS:
        if question.required:
            state = replace(state, active_question_id=question.id)
            state, result = answer_question(state, question.id, f"answer-{question.id}")
            assert result.mutated
    return state


def _advance_until_active_question(state: CustomerState, question_id: str) -> CustomerState:
    return replace(state, active_question_id=question_id, profile_status=ProfileStatus.INTERVIEWING)


def _running_state(run_id: str) -> CustomerState:
    confirmed, _ = confirm_profile(_answered_required(_consented_state()))
    requested, _ = request_search(confirmed, run_id=run_id)
    running, result = start_run(requested, run_id=run_id)
    assert result.code == "run_started"
    return running


def _apply_symbolic_event(state: CustomerState, event: str) -> CustomerState:
    if event == "start":
        return start(state, notice_version="v1", action_nonce="n1")[0]
    if event == "decline":
        return decline_consent(state, notice_version="v1", action_nonce="n1")[0]
    if event == "consent":
        return consent(state, notice_version="v1", action_nonce="n1")[0]
    if event == "profile" and state.tenant_created and not state.deleted:
        if state.profile_status is ProfileStatus.CONFIRMED:
            return confirm_profile(state)[0]
        return confirm_profile(_answered_required(state))[0]
    if event == "search":
        return request_search(state, run_id="run-1")[0]
    if event == "pause":
        run_id = state.active_run.run_id if state.active_run else "run-1"
        return start_run(state, run_id=run_id)[0]
    if event == "resume":
        run_id = state.active_run.run_id if state.active_run else "run-1"
        return resume_run(state, run_id=run_id)[0]
    if event == "cancel":
        run_id = state.active_run.run_id if state.active_run else "run-1"
        return cancel_run(state, run_id=run_id)[0]
    if event == "fail":
        return worker_failed(state, error_code="timeout")[0]
    if event == "retry":
        return retry_worker(state)[0]
    if event == "success":
        return worker_succeeded(state)[0]
    if event == "delete":
        pending, _ = confirm_delete(state, action_nonce="del", confirmed=False)
        return confirm_delete(pending, action_nonce="del", confirmed=True)[0]
    return state


def _assert_core_invariants(state: CustomerState) -> None:
    if state.tenant_created:
        assert state.consented_notice_version is not None
    if state.active_run is not None:
        assert state.profile_status is ProfileStatus.CONFIRMED
        assert state.active_run.status in SearchRunStatus.nonterminal()
    if state.deleted:
        assert state.active_run is None
        mutated, _ = consent(state, notice_version="v1", action_nonce="n2")
        assert mutated == state
    if state.worker_state is WorkerState.RETRY_WAIT:
        retried, result = retry_worker(state)
        assert result.code == "worker_retry_started"
        assert retried.worker_state is WorkerState.RUNNING
