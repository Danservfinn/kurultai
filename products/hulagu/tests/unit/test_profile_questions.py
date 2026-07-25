from __future__ import annotations

import pytest

from hulagu.domain.profile import (
    DEFAULT_PROFILE_QUESTIONS,
    OPTIONAL_PROFILE_FIELD_IDS,
    REQUIRED_PROFILE_FIELD_IDS,
    ProfileField,
    ProfileFieldSource,
    ProfileQuestion,
    first_question,
    next_question_after,
    required_question_ids,
)


def test_profile_questions_are_deterministic_and_unique() -> None:
    ids = [question.id for question in DEFAULT_PROFILE_QUESTIONS]

    assert ids == sorted(ids, key=ids.index)
    assert len(ids) == len(set(ids))
    assert first_question(DEFAULT_PROFILE_QUESTIONS) == DEFAULT_PROFILE_QUESTIONS[0]


def test_profile_questions_separate_required_and_optional_fields() -> None:
    required = required_question_ids(DEFAULT_PROFILE_QUESTIONS)
    optional = {question.id for question in DEFAULT_PROFILE_QUESTIONS if not question.required}

    assert required == REQUIRED_PROFILE_FIELD_IDS
    assert optional == OPTIONAL_PROFILE_FIELD_IDS
    assert required == {
        "target_roles",
        "seniority",
        "locations",
        "work_mode",
        "relocation_constraints",
        "work_authorization",
        "sponsorship_requirement",
        "core_skills",
        "skill_exclusions",
        "employment_types",
        "preferred_industries_companies",
        "avoided_industries_companies",
        "language_constraints",
        "result_count_preference",
    }
    assert optional == {"minimum_compensation", "earliest_start_date"}
    assert required.isdisjoint(optional)


def test_profile_field_carries_required_provenance_and_confidence() -> None:
    field = ProfileField(
        value="Staff ML Engineer",
        source=ProfileFieldSource.INTERVIEW,
        confidence=1.0,
        source_span="answer:target_roles",
    )

    assert field.value == "Staff ML Engineer"
    assert field.source is ProfileFieldSource.INTERVIEW
    assert field.confidence == 1.0
    assert field.source_span == "answer:target_roles"


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_profile_field_rejects_confidence_outside_closed_unit_interval(confidence: float) -> None:
    with pytest.raises(ValueError, match="confidence"):
        ProfileField(
            value="x",
            source=ProfileFieldSource.CV,
            confidence=confidence,
        )


def test_next_question_after_advances_in_order_and_returns_none_at_end() -> None:
    questions = (
        ProfileQuestion(id="a", prompt="A?", required=True),
        ProfileQuestion(id="b", prompt="B?", required=False),
    )

    assert next_question_after(questions, "a") == questions[1]
    assert next_question_after(questions, "b") is None


def test_next_question_after_rejects_unknown_question_id() -> None:
    with pytest.raises(ValueError, match="unknown profile question"):
        next_question_after(DEFAULT_PROFILE_QUESTIONS, "unknown")
