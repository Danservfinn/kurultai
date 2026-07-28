from __future__ import annotations

import importlib.util
from collections.abc import Callable
from pathlib import Path

from hulagu.domain.profile import Profile, ProfileField
from hulagu.persistence.rls import TenantPrincipal
from hulagu.telegram.profile_flow import ProfileFlow

ROOT = Path(__file__).parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "hulagu_task5_pg_helpers_restart",
    ROOT / "tests" / "e2e" / "test_start_and_resume.py",
)
assert _SPEC is not None and _SPEC.loader is not None
_HELPERS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HELPERS)
PsqlConnection = _HELPERS.PsqlConnection
postgres_cluster = _HELPERS.postgres_cluster
psql = _HELPERS.psql

TENANT = "75000000-0000-4000-8000-000000000001"


def profile_fields(*, omit: frozenset[str] = frozenset(), compensation_confidence: float | None = None) -> tuple[ProfileField, ...]:
    values = {
        "target_role": "Synthetic Engineer",
        "seniority": "staff",
        "location": "New York",
        "work_arrangement": "hybrid",
        "relocation_constraints": "none",
        "work_authorization": "authorized",
        "sponsorship_required": "no",
        "core_skills": "Python",
        "exclusions": "none",
        "employment_types": "full-time",
        "preferred_industries": "software",
        "avoided_companies": "none",
        "language_constraints": "English",
        "result_count": "10",
    }
    fields = [ProfileField(key, value, "cv", 1.0) for key, value in values.items() if key not in omit]
    if compensation_confidence is not None:
        fields.append(ProfileField("minimum_compensation", "$synthetic", "cv", compensation_confidence))
    return tuple(fields)


def principal() -> TenantPrincipal:
    return TenantPrincipal.from_identity_resolution(TENANT, "telegram-customer")


def seed_tenant(dsn: str) -> None:
    psql(dsn, f"INSERT INTO hulagu.tenants(id,state) VALUES('{TENANT}','READY')")


def nonce_factory() -> Callable[[], str]:
    counter = 0

    def issue() -> str:
        nonlocal counter
        counter += 1
        return f"task5-nonce-{counter}"

    return issue


def test_answer_survives_real_process_boundary_and_only_one_question_is_active() -> None:
    with postgres_cluster() as dsn:
        seed_tenant(dsn)
        issue = nonce_factory()
        first_connection = PsqlConnection(dsn)
        try:
            first = ProfileFlow(first_connection, principal(), clock=lambda: 100, nonce_factory=issue)
            opened = first.start(
                Profile(version=1, fields=profile_fields(omit=frozenset({"location", "employment_types"}))),
                correlation_id="task5-start",
            )
            assert opened.active_question is not None and opened.active_question.field_id == "location"
            assert len(opened.active_question_ids) == 1
            answer_nonce = opened.answer_nonce
            assert answer_nonce is not None
        finally:
            first_connection.close()

        restarted_connection = PsqlConnection(dsn)
        try:
            restarted = ProfileFlow(restarted_connection, principal(), clock=lambda: 100, nonce_factory=issue)
            resumed = restarted.current(correlation_id="task5-resume")
            assert resumed.active_question is not None and resumed.active_question.field_id == "location"
            answered = restarted.answer(
                resumed.active_question.question_id,
                "Boston",
                answer_nonce,
                correlation_id="task5-answer",
            )
            assert answered.active_question is not None
            assert answered.active_question.field_id == "employment_types"
            assert answered.profile.field("location") is not None
            replayed = restarted.answer(
                resumed.active_question.question_id,
                "mutated",
                answer_nonce,
                correlation_id="task5-replay",
            )
            assert replayed == answered
        finally:
            restarted_connection.close()

        third_connection = PsqlConnection(dsn)
        try:
            after_second_restart = ProfileFlow(third_connection, principal(), clock=lambda: 100, nonce_factory=issue).current(
                correlation_id="task5-second-resume"
            )
            location = after_second_restart.profile.field("location")
            assert location is not None and location.value == "Boston"
            assert after_second_restart.active_question is not None
            assert after_second_restart.active_question.field_id == "employment_types"
        finally:
            third_connection.close()

        assert psql(dsn, f"SELECT count(*) FROM hulagu.profile_answers WHERE tenant_id='{TENANT}'").stdout.strip() == "1"


def test_optional_skip_is_accepted_but_required_skip_is_rejected_without_mutation() -> None:
    with postgres_cluster() as dsn:
        seed_tenant(dsn)
        issue = nonce_factory()
        connection = PsqlConnection(dsn)
        try:
            flow = ProfileFlow(connection, principal(), clock=lambda: 100, nonce_factory=issue)
            required = flow.start(
                Profile(version=1, fields=profile_fields(omit=frozenset({"location"}))),
                correlation_id="task5-required",
            )
            assert required.active_question is not None and required.skip_nonce is not None
            assert required.edit_nonce("target_role") is None
            rejected = flow.skip(
                required.active_question.question_id,
                required.skip_nonce,
                correlation_id="task5-required-skip",
            )
            assert rejected == required
            assert rejected.active_question == required.active_question
        finally:
            connection.close()

    with postgres_cluster() as dsn:
        seed_tenant(dsn)
        issue = nonce_factory()
        connection = PsqlConnection(dsn)
        try:
            flow = ProfileFlow(connection, principal(), clock=lambda: 100, nonce_factory=issue)
            optional = flow.start(
                Profile(version=1, fields=profile_fields(compensation_confidence=0.2)),
                correlation_id="task5-optional",
            )
            assert optional.active_question is not None
            assert optional.active_question.field_id == "minimum_compensation"
            assert optional.skip_nonce is not None
            skipped = flow.skip(
                optional.active_question.question_id,
                optional.skip_nonce,
                correlation_id="task5-optional-skip",
            )
            assert skipped.active_question is None
            assert "minimum_compensation" in skipped.profile.intentionally_omitted
            duplicate = flow.skip(
                optional.active_question.question_id,
                optional.skip_nonce,
                correlation_id="task5-optional-replay",
            )
            assert duplicate == skipped
        finally:
            connection.close()

        assert psql(dsn, f"SELECT count(*) FROM hulagu.profile_answers WHERE tenant_id='{TENANT}'").stdout.strip() == "1"
