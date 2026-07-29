"""Deterministic confirmed-profile query planning."""

from __future__ import annotations

import re

from hulagu.domain.profile import Profile

from .schemas import BudgetLimits, SearchPlan

_PRIVATE_CONTACT = re.compile(r"(?:[\w.+-]+@[\w.-]+|\+?\d[\d ()-]{7,}\d)")


def _terms(profile: Profile, field_id: str) -> tuple[str, ...]:
    field = profile.field(field_id)
    if field is None or not field.value.strip():
        return ()
    values = tuple(dict.fromkeys(part.strip().lower() for part in field.value.split(",") if part.strip()))
    if any(_PRIVATE_CONTACT.search(value) for value in values):
        raise ValueError("private contact data is forbidden in search terms")
    return values


def compile_search_plan(profile: Profile) -> SearchPlan:
    if profile.confirmed_version != profile.version:
        raise ValueError("current confirmed profile required")
    role_terms = _terms(profile, "target_role")
    if not role_terms:
        raise ValueError("confirmed profile requires target role")
    location_terms = _terms(profile, "location")
    required_terms = _terms(profile, "required_skills")
    excluded_terms = _terms(profile, "excluded_terms")
    remote = _terms(profile, "remote_policy")
    remote_policy = remote[0] if remote else "any"
    if remote_policy not in {"remote", "hybrid", "onsite", "any"}:
        raise ValueError("invalid remote policy")
    budgets = BudgetLimits()
    query_parts = (role_terms[0], *(location_terms[:1]), *(required_terms[:2]))
    queries = (" ".join(query_parts),)
    return SearchPlan(
        "SearchPlan/v1",
        profile.version,
        role_terms,
        location_terms,
        remote_policy,
        required_terms,
        excluded_terms,
        "fixture-public-search-adapter",
        budgets,
        queries[: budgets.max_queries],
    )
