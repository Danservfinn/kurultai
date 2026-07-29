from __future__ import annotations

import hashlib
import json

import pytest

from hulagu.domain.profile import Profile, ProfileField
from hulagu.domain.ranking import rank_input_payload
from hulagu.search.planner import compile_search_plan
from hulagu.search.provider import (
    BudgetExceeded,
    FixtureSearchProvider,
    ProviderAttempt,
    ProviderOutcome,
    SearchCoordinator,
)
from hulagu.search.runner import MemoryRankingJobQueue, SearchRunner
from hulagu.search.schemas import BudgetLimits, SearchPlan


def profile() -> Profile:
    return Profile(1, (ProfileField("target_role", "Engineer", "customer", 1.0),), confirmed_version=1)


class RankerExecutor:
    def execute(self, input_payload: bytes, *, expected_digest: str, job_kind: str = "parser") -> bytes:
        assert job_kind == "ranker" and hashlib.sha256(input_payload).hexdigest() == expected_digest
        return json.dumps(rank_input_payload(json.loads(input_payload)), separators=(",", ":"), sort_keys=True).encode()


class ForgedRankerExecutor:
    def execute(self, input_payload: bytes, *, expected_digest: str, job_kind: str = "parser") -> bytes:
        assert job_kind == "ranker" and hashlib.sha256(input_payload).hexdigest() == expected_digest
        return json.dumps(
            {
                "schema_version": "RankedCandidates/v1",
                "ranked": [
                    {
                        "canonical_url": "https://forged.example.test/not-in-input",
                        "total_score": 100.0,
                    }
                ],
            },
            separators=(",", ":"),
        ).encode()


def test_fixture_search_run_reserves_before_every_attempt_charges_ambiguous_and_deduplicates() -> None:
    plan = compile_search_plan(profile())
    provider = FixtureSearchProvider([
        ProviderAttempt(ProviderOutcome.AMBIGUOUS),
        ProviderAttempt.success([
            {"url": "https://jobs.example.test/1?utm_source=x", "title": "Engineer", "company": "Synthetic", "location": "Remote", "remote_signal": "remote", "snippet": "Engineer role"},
            {"url": "https://jobs.example.test/1", "title": "Engineer", "company": "Synthetic", "location": "Remote", "remote_signal": "remote", "snippet": "duplicate"},
        ]),
    ])
    coordinator = SearchCoordinator(provider, clock=lambda: 10)
    result = coordinator.run(plan)
    assert len(result.candidates) == 1
    assert result.budget.provider_requests_used == 2
    assert result.budget.provider_cost_units_used == 20
    assert [receipt.outcome for receipt in result.receipts] == ["delivery_unknown", "succeeded"]
    assert provider.observed_reservations == [(1, 10), (2, 20)]


def test_provider_timeout_redirect_private_oversized_and_schema_invalid_fail_closed() -> None:
    plan = compile_search_plan(profile())
    invalid_attempts = [
        ProviderAttempt(ProviderOutcome.TIMEOUT),
        ProviderAttempt.success([{"url": "http://jobs.example.test/1"}]),
        ProviderAttempt.success([{"url": "https://127.0.0.1/job"}]),
        ProviderAttempt.raw(b"x" * 1_048_577),
        ProviderAttempt.raw(b'{"schema_version":"wrong"}'),
    ]
    for attempt in invalid_attempts:
        result = SearchCoordinator(FixtureSearchProvider([attempt]), clock=lambda: 10).run(plan)
        assert result.candidates == ()
        assert result.receipts[0].outcome in {"failed", "delivery_unknown"}


def test_provider_request_cost_and_wall_clock_budgets_are_retry_inclusive() -> None:
    base = compile_search_plan(profile())
    plan = SearchPlan.with_budgets(base, BudgetLimits(max_provider_requests_total=1, max_provider_cost_units=10, wall_seconds=1))
    provider = FixtureSearchProvider([ProviderAttempt(ProviderOutcome.AMBIGUOUS), ProviderAttempt.success([])])
    with pytest.raises(BudgetExceeded) as raised:
        SearchCoordinator(provider, clock=iter((0, 0, 2)).__next__).run(plan)
    assert provider.calls == 1
    assert raised.value.receipts[0].outcome == "delivery_unknown"
    assert raised.value.usage is not None
    assert raised.value.usage.provider_requests_used == 1
    assert raised.value.usage.provider_cost_units_used == 10


def test_publication_budget_is_independent_and_capped() -> None:
    budget = BudgetLimits(max_publication_attempts=1)
    usage = budget.new_usage()
    usage.reserve_publication()
    with pytest.raises(BudgetExceeded):
        usage.reserve_publication()


def test_end_to_end_fixture_provider_to_immutable_bundle_to_ranker() -> None:
    plan = compile_search_plan(profile())
    provider = FixtureSearchProvider([ProviderAttempt.success([
        {"url": "https://jobs.example.test/1", "title": "Engineer", "company": "Synthetic", "location": "Remote", "remote_signal": "remote", "snippet": "Engineer"}
    ])])
    search = SearchCoordinator(provider, clock=lambda: 10).run(plan)
    queue = MemoryRankingJobQueue(clock=lambda: 10)
    queue.set_authority(lifecycle_epoch=2, work_epoch=3, state="READY")
    job, created = queue.enqueue(search.to_ranking_input("run-1"), lifecycle_epoch=2, work_epoch=3)
    assert created is True
    immutable_before = job.input_digest
    assert SearchRunner(queue, RankerExecutor(), clock=lambda: 10).run_once() == "succeeded"
    assert queue.input_digest(job.job_id) == immutable_before
    assert queue.state(job.job_id) == "succeeded"


def test_end_to_end_rejects_forged_ranker_candidate_outside_immutable_bundle() -> None:
    plan = compile_search_plan(profile())
    provider = FixtureSearchProvider([ProviderAttempt.success([
        {"url": "https://jobs.example.test/real", "title": "Engineer", "company": "Synthetic", "location": "Remote", "remote_signal": "remote", "snippet": "Engineer"}
    ])])
    search = SearchCoordinator(provider, clock=lambda: 10).run(plan)
    queue = MemoryRankingJobQueue(clock=lambda: 10)
    queue.set_authority(lifecycle_epoch=2, work_epoch=3, state="READY")
    job, _ = queue.enqueue(search.to_ranking_input("run-forged"), lifecycle_epoch=2, work_epoch=3)

    assert SearchRunner(queue, ForgedRankerExecutor(), clock=lambda: 10).run_once() == "failed"
    assert queue.state(job.job_id) == "failed"
    assert queue.candidate_count == 0
