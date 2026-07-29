"""Separate runner composition root with lease-fenced parser jobs."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess  # nosec B404
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from .domain.profile import Profile
from .ingest.quarantine import (
    QuarantineAuthority,
    capture_quarantine_authority,
    open_authorized_document,
)
from .runtime.policy import ContextAuditSink


class RunnerCrash(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ParserJob:
    job_id: str
    tenant_id: str
    document_digest: str
    input_path: Path
    immutable_input_digest: str
    input_authority: QuarantineAuthority
    state: str = "queued"
    attempt: int = 0
    lease_token_hash: str | None = None
    lease_expires_at: int | None = None
    result_digest: str | None = None
    profile: Profile | None = None


@dataclass(frozen=True, slots=True)
class ParserLease:
    job_id: str
    attempt: int
    token: str
    immutable_input_digest: str
    tenant_id: str
    document_digest: str
    input_path: Path
    input_authority: QuarantineAuthority
    lifecycle_epoch: int = 0
    work_epoch: int = 0


class ParserExecutor(Protocol):
    def execute(self, input_payload: bytes, *, expected_digest: str) -> bytes: ...


class ParserJobQueue(Protocol):
    def enqueue(
        self,
        *,
        tenant_id: str,
        document_digest: str,
        input_path: Path,
        input_authority: QuarantineAuthority | None = None,
    ) -> tuple[ParserJob, bool]: ...
    def claim(self, *, lease_seconds: int = 60, now: int | None = None) -> ParserLease | None: ...
    def complete(self, lease: ParserLease, *, result_digest: str, profile: Profile, now: int | None = None) -> bool: ...
    def fail(self, lease: ParserLease, *, now: int | None = None) -> bool: ...


class MemoryParserJobQueue:
    """Deterministic durable-authority fake used to exercise the real runner entrypoint."""

    def __init__(self, *, clock: Callable[[], int]) -> None:
        self._clock = clock
        self._jobs: dict[str, ParserJob] = {}
        self._digest_index: dict[tuple[str, str], str] = {}
        self.control_events: list[str] = []

    @property
    def queued_count(self) -> int:
        return sum(job.state == "queued" for job in self._jobs.values())

    def enqueue(
        self,
        *,
        tenant_id: str,
        document_digest: str,
        input_path: Path,
        input_authority: QuarantineAuthority | None = None,
    ) -> tuple[ParserJob, bool]:
        authority = input_authority or capture_quarantine_authority(input_path, tenant_id=tenant_id)
        descriptor = open_authorized_document(input_path, tenant_id=tenant_id, authority=authority)
        os.close(descriptor)
        key = (tenant_id, document_digest)
        existing_id = self._digest_index.get(key)
        if existing_id is not None:
            return self._jobs[existing_id], False
        immutable = hashlib.sha256(
            f"parser/v2\0{tenant_id}\0{document_digest}\0{authority.serialize()}".encode()
        ).hexdigest()
        job = ParserJob(str(uuid4()), tenant_id, document_digest, input_path, immutable, authority)
        self._jobs[job.job_id] = job
        self._digest_index[key] = job.job_id
        return job, True

    def claim(self, *, lease_seconds: int = 60, now: int | None = None) -> ParserLease | None:
        now = self._clock() if now is None else now
        candidates = sorted(self._jobs.values(), key=lambda job: job.job_id)
        for job in candidates:
            if job.state == "claimed" and job.lease_expires_at is not None and job.lease_expires_at <= now:
                job = replace(job, state="queued", lease_token_hash=None, lease_expires_at=None)
                self._jobs[job.job_id] = job
            if job.state != "queued":
                continue
            token = secrets.token_hex(32)
            claimed = replace(
                job,
                state="claimed",
                attempt=job.attempt + 1,
                lease_token_hash=hashlib.sha256(token.encode()).hexdigest(),
                lease_expires_at=now + lease_seconds,
            )
            self._jobs[job.job_id] = claimed
            return ParserLease(
                claimed.job_id,
                claimed.attempt,
                token,
                claimed.immutable_input_digest,
                claimed.tenant_id,
                claimed.document_digest,
                claimed.input_path,
                claimed.input_authority,
            )
        return None

    def complete(self, lease: ParserLease, *, result_digest: str, profile: Profile, now: int | None = None) -> bool:
        job = self._jobs[lease.job_id]
        if not self._matches(job, lease, now=now):
            return False
        self._jobs[job.job_id] = replace(
            job,
            state="succeeded",
            lease_token_hash=None,
            lease_expires_at=None,
            result_digest=result_digest,
            profile=profile,
        )
        return True

    def fail(self, lease: ParserLease, *, now: int | None = None) -> bool:
        job = self._jobs[lease.job_id]
        if not self._matches(job, lease, now=now):
            return False
        self._jobs[job.job_id] = replace(job, state="failed", lease_token_hash=None, lease_expires_at=None)
        return True

    def _matches(self, job: ParserJob, lease: ParserLease, *, now: int | None = None) -> bool:
        observed_now = self._clock() if now is None else now
        return (
            job.state == "claimed"
            and job.attempt == lease.attempt
            and job.immutable_input_digest == lease.immutable_input_digest
            and job.lease_token_hash == hashlib.sha256(lease.token.encode()).hexdigest()
            and job.lease_expires_at is not None
            and job.lease_expires_at > observed_now
        )

    def state(self, job_id: str) -> str:
        return self._jobs[job_id].state

    def profile_for(self, job_id: str) -> Profile | None:
        return self._jobs[job_id].profile


class PostgresParserJobQueue:
    """Production queue adapter whose every operation uses a fresh PostgreSQL session."""

    def __init__(self, dsn: str, *, tenant_root: Path) -> None:
        if not tenant_root.is_absolute():
            raise ValueError("tenant root must be absolute")
        self._dsn = dsn
        self._tenant_root = tenant_root.absolute()

    def _query(self, sql: str, *, role: str, variables: dict[str, str]) -> list[list[str]]:
        target = f"{self._dsn}&user={role}"
        command = ["/opt/homebrew/bin/psql", "-X", "-q", "-A", "-t", "-F", "\t", "-v", "ON_ERROR_STOP=1"]
        for name, value in variables.items():
            if "\n" in value or "\r" in value:
                raise ValueError("invalid PostgreSQL queue value")
            command.extend(("-v", f"{name}={value}"))
        command.append(target)
        try:
            result = subprocess.run(  # nosec B603
                command,
                check=True,
                capture_output=True,
                input=sql,
                text=True,
                timeout=30,
                env={"PATH": "/usr/bin:/bin"},
            )
        except (subprocess.SubprocessError, OSError):
            raise RuntimeError("parser queue database operation failed") from None
        return [line.split("\t") for line in result.stdout.splitlines() if line]

    def enqueue(
        self,
        *,
        tenant_id: str,
        document_digest: str,
        input_path: Path,
        input_authority: QuarantineAuthority | None = None,
    ) -> tuple[ParserJob, bool]:
        tenant = str(UUID(tenant_id))
        expected_root = self._tenant_root / tenant
        if not input_path.is_absolute() or not input_path.is_relative_to(expected_root):
            raise ValueError("parser input is outside typed tenant root")
        authority = input_authority or capture_quarantine_authority(input_path, tenant_id=tenant)
        descriptor = open_authorized_document(input_path, tenant_id=tenant, authority=authority)
        os.close(descriptor)
        storage_ref = "/tenants/" + input_path.relative_to(self._tenant_root).as_posix()
        rows = self._query(
            "SELECT job_id,tenant_id,document_digest,immutable_input_digest,lifecycle_epoch,"
            "work_epoch,state,attempt,created FROM hulagu_api.enqueue_parser_job("
            ":'tenant'::uuid,:'digest',:'storage_ref',:'input_authority')",
            role="hulagu_app",
            variables={
                "tenant": tenant,
                "digest": document_digest,
                "storage_ref": storage_ref,
                "input_authority": authority.serialize(),
            },
        )
        if len(rows) != 1 or len(rows[0]) != 9:
            raise RuntimeError("invalid parser enqueue result")
        row = rows[0]
        return (
            ParserJob(
                job_id=row[0],
                tenant_id=row[1],
                document_digest=row[2],
                input_path=input_path,
                immutable_input_digest=row[3],
                input_authority=authority,
                state=row[6],
                attempt=int(row[7]),
            ),
            row[8] == "t",
        )

    def claim(self, *, lease_seconds: int = 60, now: int | None = None) -> ParserLease | None:
        del now
        token = secrets.token_hex(32)
        rows = self._query(
            "SELECT job_id,tenant_id,document_digest,storage_ref,attempt,immutable_input_digest,"
            "lifecycle_epoch,work_epoch,input_authority FROM hulagu_api.claim_parser_job("
            ":'token_hash',:'lease_seconds'::integer)",
            role="hulagu_runner",
            variables={
                "token_hash": hashlib.sha256(token.encode()).hexdigest(),
                "lease_seconds": str(lease_seconds),
            },
        )
        if not rows:
            return None
        if len(rows) != 1 or len(rows[0]) != 9:
            raise RuntimeError("invalid parser claim result")
        row = rows[0]
        prefix = f"/tenants/{row[1]}/"
        if not row[3].startswith(prefix):
            raise RuntimeError("invalid parser storage authority")
        input_path = self._tenant_root / row[3].removeprefix("/tenants/")
        expected_root = self._tenant_root / row[1]
        if not input_path.is_relative_to(expected_root):
            raise RuntimeError("parser storage escaped tenant root")
        return ParserLease(
            job_id=row[0],
            attempt=int(row[4]),
            token=token,
            immutable_input_digest=row[5],
            tenant_id=row[1],
            document_digest=row[2],
            input_path=input_path,
            input_authority=QuarantineAuthority.parse(row[8]),
            lifecycle_epoch=int(row[6]),
            work_epoch=int(row[7]),
        )

    def complete(self, lease: ParserLease, *, result_digest: str, profile: Profile, now: int | None = None) -> bool:
        del now
        profile_json = json.dumps(
            {
                "version": profile.version,
                "fields": [asdict(field) for field in profile.fields],
                "intentionally_omitted": list(profile.intentionally_omitted),
                "confirmed_version": profile.confirmed_version,
            },
            allow_nan=False,
            separators=(",", ":"),
        )
        rows = self._query(
            "SELECT hulagu_api.complete_parser_job(:'job_id'::uuid,:'attempt'::integer,"
            ":'token_hash',:'input_digest',:'lifecycle_epoch'::bigint,:'work_epoch'::bigint,"
            ":'result_digest',:'profile'::jsonb)",
            role="hulagu_runner",
            variables=self._lease_variables(lease)
            | {"result_digest": result_digest, "profile": profile_json},
        )
        return rows == [["t"]]

    def fail(self, lease: ParserLease, *, now: int | None = None) -> bool:
        del now
        rows = self._query(
            "SELECT hulagu_api.fail_parser_job(:'job_id'::uuid,:'attempt'::integer,"
            ":'token_hash',:'input_digest',:'lifecycle_epoch'::bigint,:'work_epoch'::bigint)",
            role="hulagu_runner",
            variables=self._lease_variables(lease),
        )
        return rows == [["t"]]

    @staticmethod
    def _lease_variables(lease: ParserLease) -> dict[str, str]:
        return {
            "job_id": lease.job_id,
            "attempt": str(lease.attempt),
            "token_hash": hashlib.sha256(lease.token.encode()).hexdigest(),
            "input_digest": lease.immutable_input_digest,
            "lifecycle_epoch": str(lease.lifecycle_epoch),
            "work_epoch": str(lease.work_epoch),
        }


class RunnerApp:
    def __init__(
        self,
        queue: ParserJobQueue,
        executor: ParserExecutor,
        *,
        work_root: Path,
        clock: Callable[[], int],
        context_audit: ContextAuditSink | None = None,
        lease_seconds: int = 60,
        crash_after_claim: bool = False,
    ) -> None:
        del work_root
        self._queue = queue
        self._executor = executor
        self._clock = clock
        self._context_audit = context_audit
        self._lease_seconds = lease_seconds
        self._crash_after_claim = crash_after_claim

    def run_once(self) -> str:
        lease = self._queue.claim(lease_seconds=self._lease_seconds, now=self._clock())
        if lease is None:
            return "idle"
        if self._crash_after_claim:
            raise RunnerCrash("injected crash after claim")
        try:
            from .ingest.parser import parse_result
            from .ingest.sanitize import draft_profile

            input_payload = _read_verified_document(
                lease.input_path,
                tenant_id=lease.tenant_id,
                authority=lease.input_authority,
                expected_digest=lease.document_digest,
            )
            payload = self._executor.execute(
                input_payload,
                expected_digest=lease.document_digest,
            )
            parsed = parse_result(payload, expected_digest=lease.document_digest)
            profile = draft_profile(parsed)
            result_digest = hashlib.sha256(payload).hexdigest()
            if not self._queue.complete(lease, result_digest=result_digest, profile=profile, now=self._clock()):
                return "stale"
            return "succeeded"
        except (RuntimeError, ValueError, OSError):
            self._queue.fail(lease, now=self._clock())
            return "failed"


def _read_verified_document(
    path: Path,
    *,
    tenant_id: str,
    authority: QuarantineAuthority,
    expected_digest: str,
) -> bytes:
    descriptor = open_authorized_document(path, tenant_id=tenant_id, authority=authority)
    digest = hashlib.sha256()
    payload = bytearray()
    try:
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            if len(payload) + len(chunk) > 10 * 1024 * 1024:
                raise ValueError("parser input limit")
            payload.extend(chunk)
            digest.update(chunk)
    finally:
        os.close(descriptor)
    if digest.hexdigest() != expected_digest:
        raise ValueError("parser input digest drift")
    return bytes(payload)
