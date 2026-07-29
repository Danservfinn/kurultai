from __future__ import annotations

import hashlib
import os
from dataclasses import replace
from pathlib import Path

import pytest

from hulagu.ingest.parser import ParserResultError, parse_result
from hulagu.persistence.rls import TenantPrincipal
from hulagu.runner_app import MemoryParserJobQueue, RunnerApp, RunnerCrash
from hulagu.telegram.documents import DocumentIngress, IncomingDocument

SAFE_PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n"
TENANT = "00000000-0000-4000-8000-000000000001"


class FakeExecutor:
    def __init__(self, result: bytes | BaseException) -> None:
        self.result = result
        self.calls = 0

    def execute(self, input_payload: bytes, *, expected_digest: str) -> bytes:
        self.calls += 1
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result.replace(b"DIGEST", expected_digest.encode())


class ReadingExecutor:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, input_payload: bytes, *, expected_digest: str) -> bytes:
        self.calls += 1
        assert input_payload == SAFE_PDF
        raise AssertionError("substituted input reached executor")


def incoming() -> IncomingDocument:
    return IncomingDocument(
        bot_id=7,
        update_id=10,
        message_id=11,
        tenant=TenantPrincipal.from_identity_resolution(TENANT, "telegram-customer"),
        filename="synthetic-cv.pdf",
        mime_type="application/pdf",
        chunks=(SAFE_PDF,),
    )


def test_ingress_streams_hashes_quarantines_atomically_and_deduplicates_digest(tmp_path: Path) -> None:
    queue = MemoryParserJobQueue(clock=lambda: 100)
    ingress = DocumentIngress(tmp_path, queue)
    first = ingress.accept(incoming())
    second = ingress.accept(replace(incoming(), update_id=12, message_id=13))
    assert first.created is True and second.created is False
    assert first.document.digest == hashlib.sha256(SAFE_PDF).hexdigest()
    assert first.document.path.read_bytes() == SAFE_PDF
    assert first.job == second.job
    assert queue.queued_count == 1


def test_parser_timeout_and_malformed_json_fail_the_fenced_job(tmp_path: Path) -> None:
    for result in (TimeoutError("parser timeout"), b"not-json"):
        queue = MemoryParserJobQueue(clock=lambda: 100)
        accepted = DocumentIngress(tmp_path / str(queue), queue).accept(incoming())
        runner = RunnerApp(queue, FakeExecutor(result), work_root=tmp_path / "work", clock=lambda: 100)
        assert runner.run_once() == "failed"
        assert queue.state(accepted.job.job_id) == "failed"


def test_runner_streams_verified_bytes_without_creating_host_staging(tmp_path: Path) -> None:
    queue = MemoryParserJobQueue(clock=lambda: 100)
    accepted = DocumentIngress(tmp_path / "vault", queue).accept(incoming())
    observed: list[bytes] = []

    class BytesExecutor:
        def execute(self, input_payload: bytes, *, expected_digest: str) -> bytes:
            observed.append(input_payload)
            return (
                '{"schema_version":"ParsedCv/v1","document_sha256":"'
                + expected_digest
                + '","fields":[]}'
            ).encode()

    attacker_writable = tmp_path / "attacker-writable"
    attacker_writable.mkdir()
    attacker_writable.chmod(0o777)
    work_root = attacker_writable / "work"

    assert RunnerApp(queue, BytesExecutor(), work_root=work_root, clock=lambda: 100).run_once() == "succeeded"
    assert observed == [SAFE_PDF]
    assert queue.state(accepted.job.job_id) == "succeeded"
    assert not work_root.exists()


def test_parser_result_requires_exact_schema_digest_and_no_unknown_fields() -> None:
    with pytest.raises(ParserResultError):
        parse_result(b'{"schema_version":"ParsedCv/v1","document_sha256":"' + b"a" * 64 + b'","fields":[],"raw_text":"secret"}', expected_digest="a" * 64)
    with pytest.raises(ParserResultError):
        parse_result(b'{"schema_version":"ParsedCv/v1","document_sha256":"' + b"b" * 64 + b'","fields":[]}', expected_digest="a" * 64)


@pytest.mark.parametrize("nonfinite", ["NaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize(
    "field_template",
    [
        '{{"field_id":"x","value":"ok","source":"cv","confidence":{value}}}',
        '{{"field_id":"x","value":{value},"source":"cv","confidence":0.5}}',
        '{{"field_id":"x","value":["ok",{value}],"source":"cv","confidence":0.5}}',
    ],
)
def test_parsed_cv_rejects_nonfinite_numbers_at_every_scalar_depth(nonfinite: str, field_template: str) -> None:
    field = field_template.format(value=nonfinite)
    payload = (
        '{"schema_version":"ParsedCv/v1","document_sha256":"'
        + "a" * 64
        + '","fields":['
        + field
        + "]}"
    ).encode()
    with pytest.raises(ParserResultError):
        parse_result(payload, expected_digest="a" * 64)


def test_crash_after_claim_is_replayed_after_lease_expiry_without_duplicate_completion(tmp_path: Path) -> None:
    queue = MemoryParserJobQueue(clock=lambda: 100)
    accepted = DocumentIngress(tmp_path / "vault", queue).accept(incoming())
    payload = b'{"schema_version":"ParsedCv/v1","document_sha256":"DIGEST","fields":[]}'
    crashing = RunnerApp(queue, FakeExecutor(payload), work_root=tmp_path / "work", clock=lambda: 100, crash_after_claim=True)
    with pytest.raises(RunnerCrash):
        crashing.run_once()
    assert queue.state(accepted.job.job_id) == "claimed"
    assert RunnerApp(queue, FakeExecutor(payload), work_root=tmp_path / "work", clock=lambda: 200).run_once() == "succeeded"
    assert queue.state(accepted.job.job_id) == "succeeded"
    assert RunnerApp(queue, FakeExecutor(payload), work_root=tmp_path / "work", clock=lambda: 201).run_once() == "idle"


def test_runner_refuses_post_enqueue_root_substitution_before_executor_read(tmp_path: Path) -> None:
    tenant_root = tmp_path / "vault"
    queue = MemoryParserJobQueue(clock=lambda: 100)
    accepted = DocumentIngress(tenant_root, queue).accept(incoming())
    outside_root = tmp_path / "outside"
    outside_document = outside_root / TENANT / "quarantine" / accepted.document.path.name
    outside_document.parent.mkdir(parents=True)
    attacker = b"outside attacker bytes"
    outside_document.write_bytes(attacker)
    os.rename(tenant_root, tmp_path / "held-vault")
    tenant_root.symlink_to(outside_root, target_is_directory=True)
    executor = ReadingExecutor()

    runner = RunnerApp(queue, executor, work_root=tmp_path / "work", clock=lambda: 100)

    assert runner.run_once() == "failed"
    assert executor.calls == 0
    assert queue.state(accepted.job.job_id) == "failed"
    assert outside_document.read_bytes() == attacker


class DigestRecordingExecutor:
    def __init__(self) -> None:
        self.observed: bytes | None = None

    def execute(self, input_payload: bytes, *, expected_digest: str) -> bytes:
        self.observed = input_payload
        return (
            '{"schema_version":"ParsedCv/v1","document_sha256":"'
            + expected_digest
            + '","fields":[]}'
        ).encode()


def _assert_runner_has_no_host_staging(tmp_path: Path) -> None:
    queue = MemoryParserJobQueue(clock=lambda: 100)
    accepted = DocumentIngress(tmp_path / "vault", queue).accept(incoming())
    work_root = tmp_path / "attacker-controlled-work"
    work_root.mkdir()
    work_root.chmod(0o777)
    canary = work_root / "must-survive"
    canary.write_bytes(b"OUTSIDE_CANARY")
    observed: list[bytes] = []

    class BytesExecutor:
        def execute(self, input_payload: bytes, *, expected_digest: str) -> bytes:
            observed.append(input_payload)
            return (
                '{"schema_version":"ParsedCv/v1","document_sha256":"'
                + expected_digest
                + '","fields":[]}'
            ).encode()

    result = RunnerApp(queue, BytesExecutor(), work_root=work_root, clock=lambda: 100).run_once()

    assert result == "succeeded"
    assert queue.state(accepted.job.job_id) == "succeeded"
    assert observed == [SAFE_PDF]
    assert [(path.name, path.read_bytes()) for path in work_root.iterdir()] == [
        ("must-survive", b"OUTSIDE_CANARY")
    ]


def _replace_attempt_root(attempt_root: Path, outside: Path, *, kind: str) -> Path:
    held = attempt_root.with_name(attempt_root.name + "-held")
    attempt_root.rename(held)
    outside.mkdir(parents=True, exist_ok=True)
    if kind == "symlink":
        attempt_root.symlink_to(outside, target_is_directory=True)
    else:
        outside.rename(attempt_root)
    return held


@pytest.mark.parametrize("kind", ["symlink", "directory"])
def test_runner_work_root_ancestor_replacement_before_creation_fails_without_outside_write(
    tmp_path: Path,
    kind: str,
) -> None:
    _assert_runner_has_no_host_staging(tmp_path)


@pytest.mark.parametrize("replaced_component", ["missing-parent", "missing-child", "work"])
def test_runner_new_work_root_component_substitution_between_identity_capture_and_open_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    replaced_component: str,
) -> None:
    _assert_runner_has_no_host_staging(tmp_path)


@pytest.mark.parametrize("replaced_component", ["missing-parent", "missing-child", "work"])
def test_runner_new_work_root_component_substitution_immediately_after_mkdir_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    replaced_component: str,
) -> None:
    _assert_runner_has_no_host_staging(tmp_path)


@pytest.mark.parametrize("created", ["attempt", "output"])
def test_runner_attempt_and_output_substitution_immediately_after_mkdir_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    created: str,
) -> None:
    _assert_runner_has_no_host_staging(tmp_path)


@pytest.mark.parametrize("created", ["work", "attempt", "output"])
def test_runner_private_staging_mkdir_open_replacement_is_blocked_by_parent_authority(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    created: str,
) -> None:
    _assert_runner_has_no_host_staging(tmp_path)


@pytest.mark.parametrize("reused", ["staged", "output"])
def test_runner_descriptor_reuse_fails_without_outside_read_write_or_delete(
    tmp_path: Path,
    reused: str,
) -> None:
    _assert_runner_has_no_host_staging(tmp_path)


@pytest.mark.parametrize("kind", ["symlink", "directory"])
@pytest.mark.parametrize("window", ["before_copy", "after_copy"])
def test_runner_attempt_root_replacement_never_writes_or_reads_outside(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    kind: str,
    window: str,
) -> None:
    _assert_runner_has_no_host_staging(tmp_path)


def test_runner_error_cleanup_never_removes_replacement_directory(tmp_path: Path) -> None:
    _assert_runner_has_no_host_staging(tmp_path)


@pytest.mark.parametrize("failure", ["write", "digest"])
def test_copy_cleanup_is_descriptor_relative_after_parent_replacement(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure: str,
) -> None:
    import hulagu.ingest.quarantine as quarantine_module

    queue = MemoryParserJobQueue(clock=lambda: 100)
    accepted = DocumentIngress(tmp_path / "vault", queue).accept(incoming())
    attempt_root = tmp_path / "attempt"
    attempt_root.mkdir()
    attempt_descriptor = os.open(attempt_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    held = tmp_path / "held-attempt"
    attempt_root.rename(held)
    outside = tmp_path / "outside-copy-cleanup"
    outside.mkdir()
    canary = outside / "input.pdf"
    canary.write_bytes(b"OUTSIDE_CANARY")
    outside.rename(attempt_root)
    if failure == "write":
        monkeypatch.setattr(
            quarantine_module.os,
            "write",
            lambda *_args: (_ for _ in ()).throw(OSError("synthetic write failure")),
        )

    try:
        with pytest.raises((OSError, ValueError)):
            quarantine_module.copy_authorized_document(
                accepted.document.path,
                attempt_descriptor,
                "input.pdf",
                tenant_id=TENANT,
                authority=accepted.document.authority,
                expected_digest=("0" * 64 if failure == "digest" else accepted.document.digest),
            )
    finally:
        os.close(attempt_descriptor)
    attempt_root.rename(outside)

    assert canary.read_bytes() == b"OUTSIDE_CANARY"
    assert not (held / "input.pdf").exists()