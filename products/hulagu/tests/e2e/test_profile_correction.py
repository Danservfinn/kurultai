from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from hulagu.domain.profile import Profile, ProfileField
from hulagu.persistence.rls import TenantPrincipal
from hulagu.telegram.profile_flow import ProfileFlow

ROOT = Path(__file__).parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "hulagu_task5_pg_helpers_correction",
    ROOT / "tests" / "e2e" / "test_start_and_resume.py",
)
assert _SPEC is not None and _SPEC.loader is not None
_HELPERS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HELPERS)
PsqlConnection = _HELPERS.PsqlConnection
postgres_cluster = _HELPERS.postgres_cluster
psql = _HELPERS.psql

TENANT = "76000000-0000-4000-8000-000000000001"
REQUIRED = {
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


def complete_profile() -> Profile:
    return Profile(
        version=1,
        fields=tuple(ProfileField(key, value, "cv", 1.0) for key, value in REQUIRED.items()),
    )


def principal() -> TenantPrincipal:
    return TenantPrincipal.from_identity_resolution(TENANT, "telegram-customer")


def test_readable_summary_requires_explicit_confirmation_and_edit_invalidates_it() -> None:
    with postgres_cluster() as dsn:
        psql(dsn, f"INSERT INTO hulagu.tenants(id,state) VALUES('{TENANT}','READY')")
        counter = 0

        def issue() -> str:
            nonlocal counter
            counter += 1
            return f"task5-correction-{counter}"

        connection = PsqlConnection(dsn)
        try:
            flow = ProfileFlow(connection, principal(), clock=lambda: 100, nonce_factory=issue)
            awaiting = flow.start(complete_profile(), correlation_id="task5-correction-start")
            assert awaiting.is_search_confirmed is False
            assert awaiting.confirmation_nonce is not None
            assert "Profile version 1" in awaiting.summary
            assert "Target role: Synthetic Engineer" in awaiting.summary

            confirmed = flow.confirm(awaiting.confirmation_nonce, correlation_id="task5-confirm-v1")
            assert confirmed.is_search_confirmed is True
            assert confirmed.profile.confirmed_version == 1
            edit_nonce = confirmed.edit_nonce("target_role")
            assert edit_nonce is not None

            edited = flow.edit(
                "target_role",
                "Synthetic Principal Engineer",
                edit_nonce,
                correlation_id="task5-edit",
            )
            assert edited.profile.version == 2
            assert edited.profile.confirmed_version is None
            assert edited.is_search_confirmed is False
            assert edited.confirmation_nonce is not None
            assert "Profile version 2" in edited.summary
            assert "Target role: Synthetic Principal Engineer" in edited.summary

            replayed = flow.edit(
                "target_role",
                "must-not-apply",
                edit_nonce,
                correlation_id="task5-edit-replay",
            )
            assert replayed == edited

            reconfirmed = flow.confirm(edited.confirmation_nonce, correlation_id="task5-confirm-v2")
            assert reconfirmed.is_search_confirmed is True
            assert reconfirmed.profile.confirmed_version == 2
        finally:
            connection.close()

        rows = psql(
            dsn,
            f"SELECT profile_version || ':' || state FROM hulagu.customer_profiles WHERE tenant_id='{TENANT}' ORDER BY profile_version",
        ).stdout.splitlines()
        assert rows == ["1:confirmed", "2:confirmed"]
        old_value = psql(
            dsn,
            f"SELECT profile_json->'profile'->'fields'->0->>'value' FROM hulagu.customer_profiles WHERE tenant_id='{TENANT}' AND profile_version=1",
        ).stdout.strip()
        assert old_value == "Synthetic Engineer"


def test_lifecycle_epoch_change_rejects_stale_confirmation_without_mutation() -> None:
    with postgres_cluster() as dsn:
        psql(
            dsn,
            f"INSERT INTO hulagu.tenants(id,state,lifecycle_epoch) VALUES('{TENANT}','READY',7)",
        )
        counter = 0

        def issue() -> str:
            nonlocal counter
            counter += 1
            return f"task5-epoch-{counter}"

        connection = PsqlConnection(dsn)
        try:
            flow = ProfileFlow(connection, principal(), clock=lambda: 100, nonce_factory=issue)
            awaiting = flow.start(complete_profile(), correlation_id="task5-epoch-start")
            assert awaiting.confirmation_nonce is not None
            before_raw = psql(
                dsn,
                f"SELECT profile_json::text FROM hulagu.customer_profiles WHERE tenant_id='{TENANT}'",
            ).stdout.strip()

            psql(dsn, f"UPDATE hulagu.tenants SET lifecycle_epoch=8 WHERE id='{TENANT}'")
            rejected = flow.confirm(
                awaiting.confirmation_nonce,
                correlation_id="task5-stale-epoch-confirm",
            )
        finally:
            connection.close()

        after_raw = psql(
            dsn,
            f"SELECT profile_json::text FROM hulagu.customer_profiles WHERE tenant_id='{TENANT}'",
        ).stdout.strip()
        before = json.loads(before_raw)
        assert before["lifecycle_epoch"] == 7
        assert {fact["lifecycle_epoch"] for fact in before["nonce_facts"]} == {7}
        assert rejected.is_search_confirmed is False
        assert rejected.profile.confirmed_version is None
        assert after_raw == before_raw
