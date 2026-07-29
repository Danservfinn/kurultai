from __future__ import annotations

from typing import Any, cast
from uuid import UUID

import pytest

from hulagu.domain.feedback import (
    DecisionEvidence,
    DecisionRecord,
    FeedbackFlow,
    compile_next_search,
    derive_features,
    pages_for_feedback_republication,
    rank_with_feedback,
)
from hulagu.domain.profile import Profile, ProfileField
from hulagu.persistence.rls import TenantPrincipal
from hulagu.search.planner import compile_search_plan
from hulagu.search.schemas import Candidate
from hulagu.wiki.model import WikiPage

TENANT_A = UUID("81000000-0000-4000-8000-00000000000a")
TENANT_B = UUID("81000000-0000-4000-8000-00000000000b")


def candidate(path: str, *, title: str, company: str, location: str = "Remote") -> Candidate:
    return Candidate(
        canonical_url=f"https://jobs.example.test/{path}",
        title=title,
        company=company,
        location=location,
        remote_signal="remote",
        source_provider="fixture-public-search-adapter",
        retrieved_at="2026-07-29T00:00:00Z",
        snippet=f"Public source evidence for {title} at {company}",
        evidence_grade="source",
    )


def record(
    marker: int,
    tenant: UUID,
    decision: str,
    item: Candidate,
    *,
    reason: str | None = None,
) -> DecisionRecord:
    return DecisionRecord(
        decision_id=UUID(f"82000000-0000-4000-8000-{marker:012d}"),
        tenant_id=tenant,
        candidate_id=UUID(f"83000000-0000-4000-8000-{marker:012d}"),
        decision=decision,
        reason=reason,
        evidence=DecisionEvidence.from_candidate(item),
        applied=True,
    )


def base_plan():
    profile = Profile(
        7,
        (
            ProfileField("target_role", "Engineer", "customer", 1.0),
            ProfileField("location", "New York", "customer", 1.0),
            ProfileField("required_skills", "Python", "customer", 1.0),
            ProfileField("excluded_terms", "Clearance", "customer", 1.0),
            ProfileField("remote_policy", "any", "customer", 1.0),
        ),
        confirmed_version=7,
    )
    return compile_search_plan(profile)


def test_features_are_tenant_local_closed_bounded_and_traceable() -> None:
    saved = candidate("saved", title="Senior Platform Engineer", company="KeepCo")
    rejected = candidate("rejected", title="Sales Engineer", company="RejectCo")
    records = tuple(
        [record(1, TENANT_A, "saved", saved)]
        + [record(index, TENANT_A, "rejected", rejected) for index in range(2, 42)]
        + [record(99, TENANT_B, "rejected", saved)]
    )

    features = derive_features(TENANT_A, records)

    assert set(features.as_dict()) == {
        "preferred_title_tokens",
        "excluded_title_tokens",
        "location_preferences",
        "remote_preferences",
        "company_rejection_counts",
        "role_rejection_counts",
    }
    assert features.preferred_title_tokens[0].source_decision_ids == (records[0].decision_id,)
    assert features.company_rejection_counts[0].value == "rejectco"
    assert features.company_rejection_counts[0].count == 5
    assert len(features.excluded_title_tokens) <= 20
    assert all(item.count <= 5 for values in features.as_dict().values() for item in values)
    assert all(record(99, TENANT_B, "rejected", saved).decision_id not in item.source_decision_ids for values in features.as_dict().values() for item in values)


def test_feedback_changes_next_query_and_rank_with_visible_delta_without_rewriting_hard_constraints() -> None:
    rejected = candidate("old", title="Senior Platform Engineer", company="RejectCo")
    records = (record(1, TENANT_A, "rejected", rejected),)
    original = base_plan()

    next_plan = compile_next_search(original, derive_features(TENANT_A, records))
    ranked = rank_with_feedback(
        (
            candidate("next-reject", title="Senior Platform Engineer", company="RejectCo"),
            candidate("next-other", title="Senior Platform Engineer", company="OtherCo"),
        ),
        next_plan,
    )

    assert next_plan.execution.queries != original.queries
    assert next_plan.execution.role_terms == original.role_terms
    assert next_plan.execution.required_terms == original.required_terms
    assert next_plan.execution.excluded_terms == original.excluded_terms
    assert ranked[0].candidate.company == "OtherCo"
    lowered = next(item for item in ranked if item.candidate.company == "RejectCo")
    assert lowered.components["tenant_feedback_match"] < 0
    assert "rejected company RejectCo" in lowered.explanation
    assert f"{lowered.components['tenant_feedback_match']:g}" in lowered.explanation


def test_explanation_never_changes_public_source_evidence() -> None:
    source = candidate("source", title="Platform Engineer", company="RejectCo")
    before = DecisionEvidence.from_candidate(source)
    next_plan = compile_next_search(base_plan(), derive_features(TENANT_A, (record(1, TENANT_A, "rejected", source),)))

    ranked = rank_with_feedback((source,), next_plan)

    assert ranked[0].candidate is source
    assert DecisionEvidence.from_candidate(ranked[0].candidate) == before
    assert "tenant feedback" in ranked[0].explanation


def test_republication_replaces_only_decisions_and_current_search_pages() -> None:
    item = candidate("visible", title="Platform Engineer", company="RejectCo")
    decision = record(1, TENANT_A, "rejected", item)
    ranked = rank_with_feedback(
        (item,),
        compile_next_search(base_plan(), derive_features(TENANT_A, (decision,))),
    )
    original = (
        WikiPage("index.md", "Index", "[[profile]] [[decisions]] [[searches/run-2]] [[jobs/job-1]]"),
        WikiPage("profile.md", "Profile", "Confirmed customer constraints."),
        WikiPage("decisions.md", "Decisions", "None."),
        WikiPage("searches/run-2.md", "Search", "Old search."),
        WikiPage("jobs/job-1.md", "Job", "Original public source evidence."),
    )

    republished = pages_for_feedback_republication(original, (decision,), ranked, search_path="searches/run-2.md")
    by_path = {page.path: page for page in republished}

    assert "rejected" in by_path["decisions.md"].body
    assert "tenant_feedback_match" in by_path["searches/run-2.md"].body
    assert by_path["jobs/job-1.md"] == original[-1]


def test_republication_renders_hostile_provider_and_customer_fields_as_inert_plain_text() -> None:
    item = candidate(
        "hostile",
        title="Platform Engineer <script>alert(1)</script> [role](https://attacker.test) `code`",
        company="RejectCo <img src=x onerror=alert(1)> ![logo](https://attacker.test/logo) | breakout",
    )
    decision = record(
        1,
        TENANT_A,
        "rejected",
        item,
        reason="Customer says **no** [reason](https://attacker.test/reason)\n| injected | row |\x00",
    )
    ranked = rank_with_feedback(
        (item,),
        compile_next_search(base_plan(), derive_features(TENANT_A, (decision,))),
    )
    original = (
        WikiPage("decisions.md", "Decisions", "None."),
        WikiPage("searches/hostile.md", "Search", "Old search."),
    )

    republished = pages_for_feedback_republication(
        original,
        (decision,),
        ranked,
        search_path="searches/hostile.md",
    )
    by_path = {page.path: page.body for page in republished}
    rendered = "\n".join(by_path.values())

    assert len(by_path["decisions.md"].splitlines()) == 3
    assert len(by_path["searches/hostile.md"].splitlines()) == 3
    assert all(
        fragment not in rendered
        for fragment in ("<script>", "<img", "[role]", "![logo]", "[reason]", "`code`", "| injected |")
    )
    assert "Platform Engineer" in rendered
    assert "RejectCo" in rendered
    assert "Customer says" in rendered
    assert "rejected company RejectCo" in rendered
    assert "&#x3C;script&#x3E;" in rendered
    assert "&#x5B;reason&#x5D;&#x28;https&#x3A;&#x2F;&#x2F;attacker&#x2E;test&#x2F;reason&#x29;" in rendered


def test_feedback_actions_must_have_short_bounded_expiry() -> None:
    flow = FeedbackFlow(
        cast(Any, object()),
        TenantPrincipal.from_identity_resolution(str(TENANT_A), "telegram-customer"),
        signing_key=b"bounded-synthetic-feedback-key-material",
        clock=lambda: 100,
    )

    with pytest.raises(ValueError, match="expiry"):
        flow.issue_action(
            UUID("83000000-0000-4000-8000-000000000001"),
            "saved",
            profile_version=7,
            lifecycle_epoch=3,
            expires_at=1001,
        )
