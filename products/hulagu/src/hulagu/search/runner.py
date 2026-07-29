"""Lease-fenced in-memory ranker queue and bytes-only runner entrypoint."""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Protocol
from uuid import uuid4

from hulagu.domain.ranking import rank_job_input

from .schemas import RankingJobInput, validate_ranker_output


class RunnerCrash(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RankingJob:
    job_id: str
    bundle: RankingJobInput
    input_digest: str
    lifecycle_epoch: int
    work_epoch: int
    state: str = "queued"
    attempt: int = 0
    token_hash: str | None = None
    lease_expires_at: int | None = None
    result: bytes | None = None


@dataclass(frozen=True, slots=True)
class RankingLease:
    job_id: str
    attempt: int
    token: str
    input_digest: str
    lifecycle_epoch: int
    work_epoch: int
    input_payload: bytes


class RankerExecutor(Protocol):
    def execute(self, input_payload: bytes, *, expected_digest: str, job_kind: str = "parser") -> bytes: ...


class MemoryRankingJobQueue:
    def __init__(
        self,
        *,
        clock: Callable[[], int],
        max_attempts_per_job: int = 3,
        max_container_attempts_total: int = 12,
    ) -> None:
        self._clock = clock
        self._jobs: dict[str, RankingJob] = {}
        self._digest_index: dict[tuple[int, int, str], str] = {}
        self._lifecycle_epoch = 0
        self._work_epoch = 0
        self._authority_state = "READY"
        self._container_attempts = 0
        self._max_attempts = max_attempts_per_job
        self._max_total = max_container_attempts_total
        self._clock_override: int | None = None
        self.terminal_reason: str | None = None

    def enqueue(self, bundle: RankingJobInput, *, lifecycle_epoch: int, work_epoch: int) -> tuple[RankingJob, bool]:
        if lifecycle_epoch != self._lifecycle_epoch or work_epoch != self._work_epoch:
            raise ValueError("enqueue authority does not match stored epoch")
        digest = bundle.digest
        dedup_key = (lifecycle_epoch, work_epoch, digest)
        existing = self._digest_index.get(dedup_key)
        if existing is not None:
            return self._jobs[existing], False
        job = RankingJob(str(uuid4()), bundle, digest, self._lifecycle_epoch, self._work_epoch)
        self._jobs[job.job_id] = job
        self._digest_index[dedup_key] = job.job_id
        return job, True

    def advance_clock(self, now: int) -> None:
        self._clock_override = now

    def set_authority(self, *, lifecycle_epoch: int, work_epoch: int, state: str) -> None:
        if lifecycle_epoch < self._lifecycle_epoch or work_epoch < self._work_epoch:
            raise ValueError("authority epoch rewind")
        self._lifecycle_epoch = lifecycle_epoch
        self._work_epoch = work_epoch
        self._authority_state = state

    def claim(self, *, lease_seconds: int = 60, now: int | None = None) -> RankingLease | None:
        observed = self._now(now)
        if self._authority_state in {"PAUSED", "CANCELLED", "DELETING", "DELETED"}:
            return None
        for current in sorted(self._jobs.values(), key=lambda item: item.job_id):
            job = current
            if job.lifecycle_epoch != self._lifecycle_epoch or job.work_epoch != self._work_epoch:
                continue
            if job.state == "claimed" and job.lease_expires_at is not None and job.lease_expires_at <= observed:
                job = replace(job, state="queued", token_hash=None, lease_expires_at=None)
                self._jobs[job.job_id] = job
            if job.state != "queued":
                continue
            if job.attempt >= self._max_attempts or self._container_attempts >= self._max_total:
                self.terminal_reason = "FAILED_BUDGET"
                self._jobs[job.job_id] = replace(job, state="failed")
                continue
            token = secrets.token_hex(32)
            claimed = replace(
                job,
                state="claimed",
                attempt=job.attempt + 1,
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                lease_expires_at=observed + lease_seconds,
            )
            self._jobs[job.job_id] = claimed
            self._container_attempts += 1
            return RankingLease(
                claimed.job_id,
                claimed.attempt,
                token,
                claimed.input_digest,
                claimed.lifecycle_epoch,
                claimed.work_epoch,
                claimed.bundle.to_bytes(),
            )
        return None

    def complete(self, lease: RankingLease, payload: bytes, *, now: int | None = None) -> bool:
        if not self._matches(lease, now=now):
            return False
        job = self._jobs[lease.job_id]
        decoded = validate_ranker_output(
            payload,
            allowed_urls={candidate.canonical_url for candidate in job.bundle.candidates},
            max_ranked=job.bundle.max_ranked,
        )
        if decoded != rank_job_input(job.bundle):
            raise ValueError("ranker output does not match immutable input")
        self._jobs[job.job_id] = replace(job, state="succeeded", token_hash=None, lease_expires_at=None, result=payload)
        return True

    def fail(self, lease: RankingLease, *, now: int | None = None) -> bool:
        if not self._matches(lease, now=now):
            return False
        job = self._jobs[lease.job_id]
        self._jobs[job.job_id] = replace(job, state="failed", token_hash=None, lease_expires_at=None)
        return True

    def _matches(self, lease: RankingLease, *, now: int | None) -> bool:
        observed = self._now(now)
        job = self._jobs.get(lease.job_id)
        return bool(
            job is not None
            and job.state == "claimed"
            and job.attempt == lease.attempt
            and job.token_hash == hashlib.sha256(lease.token.encode()).hexdigest()
            and job.input_digest == lease.input_digest
            and hashlib.sha256(lease.input_payload).hexdigest() == lease.input_digest
            and job.lifecycle_epoch == lease.lifecycle_epoch == self._lifecycle_epoch
            and job.work_epoch == lease.work_epoch == self._work_epoch
            and self._authority_state not in {"PAUSED", "CANCELLED", "DELETING", "DELETED"}
            and job.lease_expires_at is not None
            and job.lease_expires_at > observed
        )

    def _now(self, provided: int | None) -> int:
        if provided is not None:
            return provided
        if self._clock_override is not None:
            return self._clock_override
        return self._clock()

    def state(self, job_id: str) -> str:
        return self._jobs[job_id].state

    def attempts(self, job_id: str) -> int:
        return self._jobs[job_id].attempt

    def input_digest(self, job_id: str) -> str:
        return self._jobs[job_id].input_digest

    @property
    def candidate_count(self) -> int:
        total = 0
        for job in self._jobs.values():
            if job.result is not None:
                total += len(validate_ranker_output(job.result)["ranked"])  # type: ignore[arg-type]
        return total


class SearchRunner:
    def __init__(self, queue: MemoryRankingJobQueue, executor: RankerExecutor, *, clock: Callable[[], int], crash_after_claim: bool = False) -> None:
        self._queue = queue
        self._executor = executor
        self._clock = clock
        self._crash_after_claim = crash_after_claim

    def run_once(self) -> str:
        lease = self._queue.claim(now=self._clock())
        if lease is None:
            return "idle"
        if self._crash_after_claim:
            raise RunnerCrash("injected crash after claim")
        try:
            output = self._executor.execute(lease.input_payload, expected_digest=lease.input_digest, job_kind="ranker")
            if not self._queue.complete(lease, output, now=self._clock()):
                return "stale"
            return "succeeded"
        except (RuntimeError, TypeError, ValueError):
            self._queue.fail(lease, now=self._clock())
            return "failed"
