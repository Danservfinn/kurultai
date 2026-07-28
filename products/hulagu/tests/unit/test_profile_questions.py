from __future__ import annotations

from dataclasses import replace

from hulagu.domain.events import AnswerSubmitted, OptionalFieldSkipped, ProfileConfirmed
from hulagu.domain.profile import Profile, ProfileField, ProfileQuestion
from hulagu.domain.state_machine import (
    NonceAction,
    NonceFact,
    TenantState,
    TenantStatus,
    TransitionCode,
    transition_tenant,
)

NOW = 100
EXPIRY = 200
TENANT = "tenant-1"


def authority(nonce: str, action: NonceAction, object_id: str, version: int) -> NonceFact:
    return NonceFact(
        nonce=nonce,
        tenant_id=TENANT,
        action=action,
        object_id=object_id,
        version=version,
        lifecycle_epoch=0,
        expires_at=EXPIRY,
    )


def interview_state(*questions: ProfileQuestion) -> TenantState:
    active_question = questions[0] if questions else None
    facts = {
        authority("confirm-1", NonceAction.CONFIRM_PROFILE, "profile", 1),
    }
    if active_question is not None:
        facts.update(
            {
                authority(
                    "answer-1",
                    NonceAction.ANSWER_QUESTION,
                    active_question.question_id,
                    1,
                ),
                authority(
                    "skip-1",
                    NonceAction.SKIP_OPTIONAL_FIELD,
                    active_question.question_id,
                    1,
                ),
            }
        )
    return TenantState(
        status=TenantStatus.INTERVIEWING,
        tenant_id=TENANT,
        profile=Profile(
            version=1,
            fields=(ProfileField("role", "engineer", "cv", 0.6),),
        ),
        questions=questions,
        active_question=active_question,
        nonce_facts=frozenset(facts),
    )


def test_answer_without_active_question_is_rejected() -> None:
    tenant = replace(
        interview_state(),
        nonce_facts=frozenset(
            {authority("answer-1", NonceAction.ANSWER_QUESTION, "q-role", 1)}
        ),
    )

    result = transition_tenant(
        tenant,
        AnswerSubmitted("q-role", "staff engineer", "answer-1", NOW, EXPIRY),
    )

    assert result.code is TransitionCode.REJECTED
    assert result.reason == "no_active_question"
    assert result.state == tenant


def test_optional_field_can_be_skipped_and_advances_to_confirmation() -> None:
    question = ProfileQuestion("q-comp", "minimum_compensation", False)
    tenant = interview_state(question)

    result = transition_tenant(
        tenant,
        OptionalFieldSkipped("q-comp", "skip-1", NOW, EXPIRY),
    )

    assert result.code is TransitionCode.APPLIED
    assert result.state.status is TenantStatus.AWAITING_PROFILE_CONFIRMATION
    assert result.state.active_question is None
    assert result.state.profile is not None
    assert result.state.profile.intentionally_omitted == ("minimum_compensation",)


def test_required_field_skip_is_rejected_without_mutation() -> None:
    question = ProfileQuestion("q-role", "role", True)
    tenant = interview_state(question)

    result = transition_tenant(
        tenant,
        OptionalFieldSkipped("q-role", "skip-1", NOW, EXPIRY),
    )

    assert result.code is TransitionCode.REJECTED
    assert result.reason == "required_field"
    assert result.state == tenant


def test_answer_updates_exactly_the_active_question_and_advances_once() -> None:
    first = ProfileQuestion("q-location", "location", True)
    second = ProfileQuestion("q-comp", "minimum_compensation", False)
    tenant = interview_state(first, second)

    result = transition_tenant(
        tenant,
        AnswerSubmitted("q-location", "New York", "answer-1", NOW, EXPIRY),
    )

    assert result.code is TransitionCode.APPLIED
    assert result.state.active_question == second
    assert result.state.profile is not None
    assert result.state.profile.field("location") == ProfileField(
        "location", "New York", "interview", 1.0
    )


def test_wrong_question_or_stale_duplicate_nonce_cannot_mutate_profile() -> None:
    question = ProfileQuestion("q-location", "location", True)
    tenant = interview_state(question)

    wrong = transition_tenant(
        tenant,
        AnswerSubmitted("q-other", "New York", "answer-1", NOW, EXPIRY),
    )
    expired = transition_tenant(
        tenant,
        AnswerSubmitted("q-location", "New York", "answer-1", EXPIRY + 1, EXPIRY),
    )
    applied = transition_tenant(
        tenant,
        AnswerSubmitted("q-location", "New York", "answer-1", NOW, EXPIRY),
    )
    duplicate = transition_tenant(
        replace(applied.state, active_question=question, questions=(question,)),
        AnswerSubmitted("q-location", "Boston", "answer-1", NOW, EXPIRY),
    )

    assert wrong.state == tenant
    assert expired.code is TransitionCode.INVALID_CALLBACK
    assert expired.state == tenant
    assert duplicate.code is TransitionCode.NOOP
    assert duplicate.state.profile == applied.state.profile


def test_unissued_action_nonce_is_rejected_even_when_unexpired() -> None:
    question = ProfileQuestion("q-location", "location", True)
    tenant = replace(
        interview_state(question),
        nonce_facts=frozenset(
            {authority("issued-answer", NonceAction.ANSWER_QUESTION, "q-location", 1)}
        ),
    )

    result = transition_tenant(
        tenant,
        AnswerSubmitted("q-location", "New York", "forged-answer", NOW, EXPIRY),
    )

    assert result.code is TransitionCode.INVALID_CALLBACK
    assert result.reason == "stale_action_nonce"
    assert result.state == tenant


def test_profile_confirmation_requires_exact_version_and_valid_nonce() -> None:
    tenant = replace(interview_state(), status=TenantStatus.AWAITING_PROFILE_CONFIRMATION)

    stale = transition_tenant(
        tenant,
        ProfileConfirmed(0, "confirm-1", NOW, EXPIRY),
    )
    expired = transition_tenant(
        tenant,
        ProfileConfirmed(1, "confirm-1", EXPIRY + 1, EXPIRY),
    )
    confirmed = transition_tenant(
        tenant,
        ProfileConfirmed(1, "confirm-1", NOW, EXPIRY),
    )

    assert stale.code is TransitionCode.INVALID_CALLBACK
    assert stale.reason == "stale_action_authority"
    assert stale.state == tenant
    assert expired.code is TransitionCode.INVALID_CALLBACK
    assert expired.state == tenant
    assert confirmed.state.status is TenantStatus.READY
    assert confirmed.state.profile is not None
    assert confirmed.state.profile.confirmed_version == 1
