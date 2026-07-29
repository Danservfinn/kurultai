from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from hulagu.search.runner import MemoryRankingJobQueue, RankingLease, RunnerCrash, SearchRunner
from hulagu.search.schemas import RankingJobInput


def bundle() -> RankingJobInput:
    return RankingJobInput.synthetic(run_id="run-1", profile_version=1)


class FixtureExecutor:
    def execute(self, input_payload: bytes, *, expected_digest: str, job_kind: str = "parser") -> bytes:
        assert job_kind == "ranker"
        assert hashlib.sha256(input_payload).hexdigest() == expected_digest
        return b'{"schema_version":"RankedCandidates/v1","ranked":[]}'


def test_expired_replayed_changed_digest_and_stale_epochs_cannot_complete() -> None:
    queue = MemoryRankingJobQueue(clock=lambda: 100)
    queue.set_authority(lifecycle_epoch=4, work_epoch=7, state="READY")
    job, created = queue.enqueue(bundle(), lifecycle_epoch=4, work_epoch=7)
    assert created is True
    lease = queue.claim(lease_seconds=10)
    assert lease is not None
    stale: tuple[RankingLease, ...] = (
        replace(lease, token="wrong"),
        replace(lease, attempt=lease.attempt + 1),
        replace(lease, input_digest="f" * 64),
        replace(lease, lifecycle_epoch=5),
        replace(lease, work_epoch=8),
    )
    for candidate in stale:
        assert queue.complete(candidate, b'{"schema_version":"RankedCandidates/v1","ranked":[]}', now=100) is False
    assert queue.complete(lease, b'{"schema_version":"RankedCandidates/v1","ranked":[]}', now=111) is False
    assert queue.complete(lease, b'{"schema_version":"RankedCandidates/v1","ranked":[]}', now=100) is True
    assert queue.complete(lease, b'{"schema_version":"RankedCandidates/v1","ranked":[]}', now=100) is False
    assert queue.state(job.job_id) == "succeeded"


def test_pause_cancel_and_delete_revoke_claim_and_completion_authority() -> None:
    queue = MemoryRankingJobQueue(clock=lambda: 100)
    queue.set_authority(lifecycle_epoch=4, work_epoch=7, state="READY")
    queue.enqueue(bundle(), lifecycle_epoch=4, work_epoch=7)
    lease = queue.claim()
    assert lease is not None
    queue.set_authority(lifecycle_epoch=4, work_epoch=8, state="PAUSED")
    assert queue.complete(lease, b'{"schema_version":"RankedCandidates/v1","ranked":[]}', now=100) is False
    assert queue.claim() is None
    queue.set_authority(lifecycle_epoch=5, work_epoch=9, state="DELETING")
    assert queue.fail(lease, now=100) is False
    assert queue.candidate_count == 0


def test_stale_enqueue_cannot_rewind_authority_even_on_duplicate_fast_path() -> None:
    queue = MemoryRankingJobQueue(clock=lambda: 100)
    queue.set_authority(lifecycle_epoch=4, work_epoch=8, state="READY")
    queued, created = queue.enqueue(bundle(), lifecycle_epoch=4, work_epoch=8)
    assert created is True

    queue.set_authority(lifecycle_epoch=4, work_epoch=9, state="READY")
    with pytest.raises(ValueError, match="enqueue authority"):
        queue.enqueue(bundle(), lifecycle_epoch=4, work_epoch=8)
    with pytest.raises(ValueError, match="authority epoch rewind"):
        queue.set_authority(lifecycle_epoch=4, work_epoch=7, state="READY")

    assert queue.claim() is None
    assert queue.state(queued.job_id) == "queued"


def test_current_epoch_enqueue_replaces_revoked_duplicate_and_still_deduplicates_current_job() -> None:
    queue = MemoryRankingJobQueue(clock=lambda: 100)
    queue.set_authority(lifecycle_epoch=4, work_epoch=7, state="READY")
    revoked, created = queue.enqueue(bundle(), lifecycle_epoch=4, work_epoch=7)
    assert created is True

    queue.set_authority(lifecycle_epoch=4, work_epoch=8, state="READY")
    current, created = queue.enqueue(bundle(), lifecycle_epoch=4, work_epoch=8)
    assert created is True
    assert current.job_id != revoked.job_id
    assert (current.lifecycle_epoch, current.work_epoch) == (4, 8)

    duplicate, created = queue.enqueue(bundle(), lifecycle_epoch=4, work_epoch=8)
    assert created is False
    assert duplicate == current

    lease = queue.claim()
    assert lease is not None
    assert lease.job_id == current.job_id
    assert (lease.lifecycle_epoch, lease.work_epoch) == (4, 8)


def test_claim_does_not_mutate_expired_work_after_epoch_revocation() -> None:
    queue = MemoryRankingJobQueue(clock=lambda: 100)
    queue.set_authority(lifecycle_epoch=4, work_epoch=7, state="READY")
    job, _ = queue.enqueue(bundle(), lifecycle_epoch=4, work_epoch=7)
    assert queue.claim(lease_seconds=1) is not None

    queue.set_authority(lifecycle_epoch=4, work_epoch=8, state="READY")
    queue.advance_clock(102)

    assert queue.claim() is None
    assert queue.state(job.job_id) == "claimed"


def test_crash_after_claim_retries_once_without_duplicate_candidates() -> None:
    queue = MemoryRankingJobQueue(clock=lambda: 100, max_attempts_per_job=3, max_container_attempts_total=3)
    job, _ = queue.enqueue(bundle(), lifecycle_epoch=0, work_epoch=0)
    crashing = SearchRunner(queue, FixtureExecutor(), clock=lambda: 100, crash_after_claim=True)
    with pytest.raises(RunnerCrash):
        crashing.run_once()
    queue.advance_clock(161)
    assert SearchRunner(queue, FixtureExecutor(), clock=lambda: 161).run_once() == "succeeded"
    assert queue.attempts(job.job_id) == 2
    assert queue.candidate_count == 0


def test_per_job_and_total_container_attempt_budgets_include_expired_leases() -> None:
    queue = MemoryRankingJobQueue(clock=lambda: 0, max_attempts_per_job=1, max_container_attempts_total=1)
    queue.enqueue(bundle(), lifecycle_epoch=0, work_epoch=0)
    assert queue.claim(lease_seconds=1) is not None
    queue.advance_clock(2)
    assert queue.claim(lease_seconds=1) is None
    assert queue.terminal_reason == "FAILED_BUDGET"
