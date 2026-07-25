"""Pure customer-profile interview and provenance contract for Hulagu."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum


class ProfileFieldSource(StrEnum):
    """The only authorities allowed to supply a confirmed profile field."""

    CV = "cv"
    INTERVIEW = "interview"
    CUSTOMER_EDIT = "customer_edit"


@dataclass(frozen=True, slots=True)
class ProfileField:
    """A profile value plus the provenance required by frozen plan §3.4."""

    value: str
    source: ProfileFieldSource
    confidence: float
    source_span: str | None = None

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise ValueError("profile field value must not be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("profile field confidence must be in the closed interval [0, 1]")


@dataclass(frozen=True, slots=True)
class ProfileQuestion:
    id: str
    prompt: str
    required: bool


REQUIRED_PROFILE_FIELD_IDS: frozenset[str] = frozenset(
    {
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
)
OPTIONAL_PROFILE_FIELD_IDS: frozenset[str] = frozenset(
    {"minimum_compensation", "earliest_start_date"}
)


DEFAULT_PROFILE_QUESTIONS: tuple[ProfileQuestion, ...] = (
    ProfileQuestion("target_roles", "What role families should Hulagu search for?", True),
    ProfileQuestion("seniority", "What seniority levels should Hulagu include or exclude?", True),
    ProfileQuestion("locations", "What locations should Hulagu include or exclude?", True),
    ProfileQuestion(
        "work_mode",
        "What remote, hybrid, or on-site preference should Hulagu use?",
        True,
    ),
    ProfileQuestion(
        "relocation_constraints",
        "What relocation constraints apply? Answer 'none' if there are none.",
        True,
    ),
    ProfileQuestion(
        "work_authorization",
        "What work authorization applies to the target roles?",
        True,
    ),
    ProfileQuestion(
        "sponsorship_requirement",
        "Is employer sponsorship required now or in the future?",
        True,
    ),
    ProfileQuestion("core_skills", "Which core skills should matching roles require?", True),
    ProfileQuestion(
        "skill_exclusions",
        "Which skills or responsibilities should be excluded? Answer 'none' if needed.",
        True,
    ),
    ProfileQuestion("employment_types", "Which employment types should Hulagu include?", True),
    ProfileQuestion(
        "preferred_industries_companies",
        "Which industries or companies should be preferred? Answer 'none' if needed.",
        True,
    ),
    ProfileQuestion(
        "avoided_industries_companies",
        "Which industries or companies should be avoided? Answer 'none' if needed.",
        True,
    ),
    ProfileQuestion(
        "language_constraints",
        "What language constraints apply? Answer 'none' if there are none.",
        True,
    ),
    ProfileQuestion(
        "result_count_preference",
        "How many results should each search run target?",
        True,
    ),
    ProfileQuestion(
        "minimum_compensation",
        "Optional: what minimum compensation should Hulagu use as a filter?",
        False,
    ),
    ProfileQuestion(
        "earliest_start_date",
        "Optional: what is the earliest relevant start date?",
        False,
    ),
)



def first_question(
    questions: Sequence[ProfileQuestion] = DEFAULT_PROFILE_QUESTIONS,
) -> ProfileQuestion | None:
    return questions[0] if questions else None


def next_question_after(
    questions: Sequence[ProfileQuestion],
    question_id: str,
) -> ProfileQuestion | None:
    for index, question in enumerate(questions):
        if question.id == question_id:
            next_index = index + 1
            return questions[next_index] if next_index < len(questions) else None
    raise ValueError(f"unknown profile question: {question_id}")


def question_by_id(
    question_id: str,
    questions: Sequence[ProfileQuestion] = DEFAULT_PROFILE_QUESTIONS,
) -> ProfileQuestion:
    for question in questions:
        if question.id == question_id:
            return question
    raise ValueError(f"unknown profile question: {question_id}")


def required_question_ids(
    questions: Sequence[ProfileQuestion] = DEFAULT_PROFILE_QUESTIONS,
) -> frozenset[str]:
    return frozenset(question.id for question in questions if question.required)
