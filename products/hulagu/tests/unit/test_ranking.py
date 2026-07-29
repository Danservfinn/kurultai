from __future__ import annotations

import pytest

from hulagu.domain.ranking import rank_candidates
from hulagu.search.schemas import Candidate


def candidate(url: str, *, title: str = "Senior Python Engineer", required: tuple[str, ...] = ("python",)) -> Candidate:
    return Candidate(
        canonical_url=url,
        title=title,
        company="Synthetic Co",
        location="New York",
        remote_signal="hybrid",
        source_provider="fixture-public-search-adapter",
        retrieved_at="2026-07-29T00:00:00Z",
        snippet="Python PostgreSQL role",
        evidence_grade="provider_returned",
        required_terms=required,
    )


def test_ranking_is_deterministic_visible_and_capped() -> None:
    ranked = rank_candidates(
        (candidate("https://jobs.example.test/1"), candidate("https://jobs.example.test/2", title="Designer")),
        role_terms=("engineer",),
        location_terms=("new york",),
        required_terms=("python",),
        excluded_terms=("unpaid",),
        max_ranked=1,
    )
    assert len(ranked) == 1
    assert ranked[0].candidate.canonical_url.endswith("/1")
    assert set(ranked[0].components) == {
        "role_match", "required_skill_match", "location_match", "seniority_match", "freshness_signal", "tenant_feedback_match", "hard_exclusion_penalties"
    }
    assert ranked[0].explanation.startswith("Deterministic score")
    assert ranked[0].total_score == sum(ranked[0].components.values())


def test_duplicate_canonical_url_is_rejected() -> None:
    duplicate = candidate("https://jobs.example.test/1?utm_source=x")
    with pytest.raises(ValueError, match="duplicate URL"):
        rank_candidates(
            (candidate("https://jobs.example.test/1"), duplicate),
            role_terms=("engineer",), location_terms=(), required_terms=(), excluded_terms=(), max_ranked=20,
        )


def test_hard_exclusion_is_recorded_as_a_penalty() -> None:
    ranked = rank_candidates(
        (candidate("https://jobs.example.test/1", title="Unpaid Engineer"),),
        role_terms=("engineer",), location_terms=(), required_terms=(), excluded_terms=("unpaid",), max_ranked=20,
    )
    assert ranked[0].components["hard_exclusion_penalties"] < 0
    assert "unpaid" in ranked[0].matched_constraints
