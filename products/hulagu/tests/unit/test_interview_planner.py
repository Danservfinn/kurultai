from __future__ import annotations

from hulagu.domain.interview import plan_interview
from hulagu.domain.profile import Profile, ProfileField


def field(field_id: str, value: str = "synthetic", confidence: float = 1.0) -> ProfileField:
    return ProfileField(field_id, value, "cv", confidence)


def test_low_confidence_cv_field_is_a_question_not_a_confirmed_fact() -> None:
    plan = plan_interview(Profile(version=1, fields=(field("target_role", confidence=0.49),)))

    question = next(item for item in plan.questions if item.field_id == "target_role")
    assert question.required is True
    assert "target_role" not in plan.confirmed_field_ids


def test_planner_orders_questions_deterministically_and_activates_exactly_one() -> None:
    profile = Profile(version=1, fields=(field("core_skills"),))

    first = plan_interview(profile)
    second = plan_interview(profile)

    assert first.questions == second.questions
    assert len(first.questions) >= 2
    assert first.active_question == first.questions[0]
    assert sum(item is first.active_question for item in first.questions) == 1


def test_absent_sensitive_optional_compensation_is_not_demanded() -> None:
    plan = plan_interview(Profile(version=1))

    assert all(item.field_id != "minimum_compensation" for item in plan.questions)


def test_present_low_confidence_compensation_is_optional_and_skippable() -> None:
    profile = Profile(
        version=1,
        fields=(field("minimum_compensation", "$synthetic", confidence=0.2),),
    )

    question = next(item for item in plan_interview(profile).questions if item.field_id == "minimum_compensation")
    assert question.required is False
