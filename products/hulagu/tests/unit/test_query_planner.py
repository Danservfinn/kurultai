from __future__ import annotations

import pytest

from hulagu.domain.profile import Profile, ProfileField
from hulagu.search.planner import compile_search_plan
from hulagu.search.schemas import BudgetLimits


def confirmed_profile() -> Profile:
    return Profile(
        version=3,
        confirmed_version=3,
        fields=(
            ProfileField("target_role", "Software Engineer", "customer", 1.0),
            ProfileField("location", "New York", "customer", 1.0),
            ProfileField("remote_policy", "hybrid", "customer", 1.0),
            ProfileField("required_skills", "Python, PostgreSQL", "customer", 1.0),
            ProfileField("excluded_terms", "clearance, unpaid", "customer", 1.0),
        ),
    )


def test_search_requires_current_profile_confirmation() -> None:
    with pytest.raises(ValueError, match="confirmed profile"):
        compile_search_plan(Profile(version=3, confirmed_version=2))


def test_query_plan_is_deterministic_and_bounded() -> None:
    first = compile_search_plan(confirmed_profile())
    second = compile_search_plan(confirmed_profile())
    assert first == second
    assert first.schema_version == "SearchPlan/v1"
    assert first.profile_version == 3
    assert first.role_terms == ("software engineer",)
    assert first.location_terms == ("new york",)
    assert first.required_terms == ("python", "postgresql")
    assert first.excluded_terms == ("clearance", "unpaid")
    assert first.remote_policy == "hybrid"
    assert first.provider == "fixture-public-search-adapter"
    assert first.budgets == BudgetLimits()
    assert len(first.queries) <= first.budgets.max_queries


@pytest.mark.parametrize("field_id", ["target_role", "location", "required_skills"])
def test_private_contact_data_never_enters_queries(field_id: str) -> None:
    profile = confirmed_profile().set_field(ProfileField(field_id, "person@example.com", "customer", 1.0))
    profile = Profile(profile.version, profile.fields, profile.intentionally_omitted, profile.version)
    with pytest.raises(ValueError, match="private contact"):
        compile_search_plan(profile)
