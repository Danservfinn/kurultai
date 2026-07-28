"""Deterministic, model-free planning for the customer profile interview."""

from __future__ import annotations

from dataclasses import dataclass

from .profile import Profile, ProfileQuestion

MIN_CONFIDENCE = 0.8


@dataclass(frozen=True, slots=True)
class FieldSpec:
    field_id: str
    label: str
    required: bool = True


FIELD_SPECS = (
    FieldSpec("target_role", "Target role"),
    FieldSpec("seniority", "Seniority"),
    FieldSpec("location", "Location"),
    FieldSpec("work_arrangement", "Work arrangement"),
    FieldSpec("relocation_constraints", "Relocation constraints"),
    FieldSpec("work_authorization", "Work authorization"),
    FieldSpec("sponsorship_required", "Sponsorship required"),
    FieldSpec("core_skills", "Core skills"),
    FieldSpec("exclusions", "Exclusions"),
    FieldSpec("employment_types", "Employment types"),
    FieldSpec("preferred_industries", "Preferred industries"),
    FieldSpec("avoided_companies", "Companies to avoid"),
    FieldSpec("language_constraints", "Language constraints"),
    FieldSpec("result_count", "Result count"),
    FieldSpec("minimum_compensation", "Minimum compensation", required=False),
)
FIELD_SPEC_BY_ID = {item.field_id: item for item in FIELD_SPECS}


@dataclass(frozen=True, slots=True)
class InterviewPlan:
    questions: tuple[ProfileQuestion, ...]
    active_question: ProfileQuestion | None
    confirmed_field_ids: frozenset[str]


def plan_interview(profile: Profile) -> InterviewPlan:
    """Return stable required gaps and uncertain supplied values in policy order."""

    questions: list[ProfileQuestion] = []
    confirmed: set[str] = set()
    omitted = frozenset(profile.intentionally_omitted)
    for spec in FIELD_SPECS:
        existing = profile.field(spec.field_id)
        if existing is not None and existing.confidence >= MIN_CONFIDENCE:
            confirmed.add(spec.field_id)
            continue
        if spec.required or (existing is not None and spec.field_id not in omitted):
            questions.append(
                ProfileQuestion(
                    question_id=f"profile:{spec.field_id}",
                    field_id=spec.field_id,
                    required=spec.required,
                )
            )
    planned = tuple(questions)
    return InterviewPlan(
        questions=planned,
        active_question=planned[0] if planned else None,
        confirmed_field_ids=frozenset(confirmed),
    )
