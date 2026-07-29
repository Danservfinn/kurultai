from __future__ import annotations

import ast
import hashlib
import json
import os
import socket
import stat
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from hulagu.runtime.container import ContainerExecutionError, DockerCliBackend, ParserContainerExecutor
from hulagu.runtime.policy import ContainerEffectiveState, EngineEnrollment, ParserInvocation
from hulagu.search.schemas import validate_ranker_output


class RankerBackend:
    def __init__(self, state: ContainerEffectiveState, output: bytes) -> None:
        self.state = state
        self.output = output
        self.invocations: list[ParserInvocation] = []
        self.starts = 0

    def create_parser(self, invocation: ParserInvocation) -> str:
        self.invocations.append(invocation)
        return "ranker-1"

    def inspect(self, container_id: str) -> ContainerEffectiveState:
        assert container_id == "ranker-1"
        return self.state

    def start(self, container_id: str, timeout_seconds: int, input_payload: bytes) -> bytes:
        self.starts += 1
        return self.output

    def remove(self, container_id: str) -> None:
        assert container_id == "ranker-1"


def secure_state() -> ContainerEffectiveState:
    return ContainerEffectiveState("none", (), (), "65532:65532", ("ALL",), True, True, 64, 268_435_456, 1.0, 67_108_864, 128, ())


def enrollment(tmp_path: Path) -> EngineEnrollment:
    cli = tmp_path / "docker"
    cli.write_bytes(b"fixture")
    cli.chmod(0o700)
    sock = tmp_path / "docker.sock"
    sock.touch()
    return EngineEnrollment(cli, hashlib.sha256(b"fixture").hexdigest(), sock, "hulagu-parser@sha256:" + "a" * 64)


def valid_output() -> bytes:
    return json.dumps({"schema_version": "RankedCandidates/v1", "ranked": []}, separators=(",", ":")).encode()


@pytest.mark.parametrize(
    "state",
    [
        replace(secure_state(), network_mode="bridge"),
        replace(secure_state(), environment_keys=("SEARCH_API_KEY",)),
        replace(secure_state(), supplementary_groups=(20,)),
        replace(secure_state(), mounts=((Path("/host"), "/input", True),)),
        replace(secure_state(), tmpfs_bytes=0),
        replace(secure_state(), open_files=0),
    ],
)
def test_ranker_never_starts_with_network_secret_group_mount_or_unbounded_resource(tmp_path: Path, state: ContainerEffectiveState) -> None:
    backend = RankerBackend(state, valid_output())
    executor = ParserContainerExecutor(enrollment(tmp_path), backend=backend)
    payload = b'{"schema_version":"RankerInput/v1"}'
    with pytest.raises(ContainerExecutionError):
        executor.execute(payload, expected_digest=hashlib.sha256(payload).hexdigest(), job_kind="ranker")
    assert backend.starts == 0


def test_ranker_uses_fixed_bytes_only_invocation_and_bounds_stdout(tmp_path: Path) -> None:
    backend = RankerBackend(secure_state(), b"x" * 1_048_577)
    executor = ParserContainerExecutor(enrollment(tmp_path), backend=backend)
    payload = b'{"schema_version":"RankerInput/v1"}'
    with pytest.raises(ContainerExecutionError, match="output limit"):
        executor.execute(payload, expected_digest=hashlib.sha256(payload).hexdigest(), job_kind="ranker")
    invocation = backend.invocations[0]
    assert invocation.job_kind == "ranker"
    assert not hasattr(invocation, "input_path") and not hasattr(invocation, "output_path")


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo", "device", "socket"])
def test_filesystem_nodes_are_not_accepted_as_ranker_output(tmp_path: Path, kind: str) -> None:
    node = tmp_path / kind
    target = tmp_path / "target"
    target.write_bytes(valid_output())
    if kind == "symlink":
        node.symlink_to(target)
    elif kind == "hardlink":
        os.link(target, node)
    elif kind == "fifo":
        os.mkfifo(node)
    elif kind == "socket":
        node = Path("/tmp") / f"hulagu-ranker-{os.getpid()}.sock"
        node.unlink(missing_ok=True)
        sock = socket.socket(socket.AF_UNIX)
        sock.bind(str(node))
        sock.close()
    else:
        node.write_bytes(b"not-a-device")
        os.chmod(node, stat.S_IFCHR | 0o600)
    with pytest.raises((TypeError, ValueError), match="regular stdout bytes"):
        validate_ranker_output(node)
    if kind == "socket":
        node.unlink(missing_ok=True)


def test_schema_invalid_ranker_output_is_rejected() -> None:
    with pytest.raises(ValueError, match="RankedCandidates/v1"):
        validate_ranker_output(b'{"schema_version":"wrong","ranked":[]}')


@pytest.mark.parametrize(
    "payload",
    [
        b'{"schema_version":"RankedCandidates/v1","ranked":[{}]}',
        b'{"schema_version":"RankedCandidates/v1","ranked":[{"canonical_url":"https://jobs.example.test/1","total_score":"100"}]}',
        b'{"schema_version":"RankedCandidates/v1","ranked":[{"canonical_url":"https://127.0.0.1/1","total_score":10}]}',
        b'{"schema_version":"RankedCandidates/v1","ranked":[{"canonical_url":"https://jobs.example.test/1","total_score":NaN}]}',
    ],
)
def test_ranker_output_rejects_invalid_item_schema_private_urls_and_nonfinite_scores(payload: bytes) -> None:
    with pytest.raises(ValueError, match="RankedCandidates/v1"):
        validate_ranker_output(payload)


def test_enrolled_ranker_executes_domain_ranking_and_emits_full_evidence() -> None:
    script = Path(__file__).parents[2] / "sandbox" / "rank_candidates.py"
    tree = ast.parse(script.read_text())
    imported_modules = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert "hulagu.domain.ranking" in imported_modules

    payload = {
        "schema_version": "RankerInput/v1",
        "run_id": "run-1",
        "profile_version": 1,
        "candidates": [
            {
                "canonical_url": "https://jobs.example.test/1",
                "title": "Senior Python Engineer",
                "company": "Synthetic Co",
                "location": "New York",
                "remote_signal": "hybrid",
                "source_provider": "fixture-public-search-adapter",
                "retrieved_at": "2026-07-29T00:00:00Z",
                "snippet": "Python PostgreSQL role",
                "evidence_grade": "provider_returned",
                "required_terms": ["python"],
                "normalized_url_hash": hashlib.sha256(b"https://jobs.example.test/1").hexdigest(),
            }
        ],
        "intent": {
            "role_terms": ["engineer"],
            "location_terms": ["new york"],
            "required_terms": ["python", "rust"],
            "excluded_terms": ["unpaid"],
        },
        "max_ranked": 1,
    }
    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(Path(__file__).parents[2] / "src")}
    result = subprocess.run([sys.executable, str(script)], input=json.dumps(payload), text=True, capture_output=True, env=env, check=True)
    item = json.loads(result.stdout)["ranked"][0]
    assert set(item) == {
        "canonical_url", "components", "total_score", "matched_constraints", "missing_constraints", "explanation"
    }
    assert set(item["components"]) == {
        "role_match", "required_skill_match", "location_match", "seniority_match", "freshness_signal",
        "tenant_feedback_match", "hard_exclusion_penalties",
    }
    assert item["matched_constraints"] == ["python"]
    assert item["missing_constraints"] == ["rust"]
    assert item["explanation"].startswith("Deterministic score:")


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_docker_cli_terminates_before_oversized_stream_is_fully_buffered(tmp_path: Path, stream: str) -> None:
    marker = tmp_path / "completed"
    cli = tmp_path / "docker"
    redirect = "1>&2" if stream == "stderr" else ""
    cli.write_text(
        "#!/bin/sh\n"
        f"dd if=/dev/zero bs=65536 count=32 {redirect} 2>/dev/null\n"
        f"printf completed > {marker}\n"
    )
    cli.chmod(0o700)
    sock = tmp_path / "docker.sock"
    sock.touch()
    enrolled = EngineEnrollment(cli, hashlib.sha256(cli.read_bytes()).hexdigest(), sock, "hulagu-parser@sha256:" + "a" * 64)
    backend = DockerCliBackend(enrolled)

    with pytest.raises(ContainerExecutionError, match=f"{stream} output limit"):
        backend._invoke(("version",), timeout=5)
    assert not marker.exists()


def test_ranker_script_has_no_secret_or_network_capability_and_runs_on_stdin() -> None:
    script = Path(__file__).parents[2] / "sandbox" / "rank_candidates.py"
    dockerfile = script.parent / "Dockerfile"
    dockerfile_text = dockerfile.read_text()
    assert "COPY --chown=65532:65532 --chmod=0555 sandbox/rank_candidates.py /sandbox/rank_candidates.py" in dockerfile_text
    assert "COPY --chown=65532:65532 --chmod=0555 src/hulagu/domain/ranking.py /sandbox/hulagu/domain/ranking.py" in dockerfile_text
    assert "COPY --chown=65532:65532 --chmod=0555 src/hulagu/search/schemas.py /sandbox/hulagu/search/schemas.py" in dockerfile_text
    tree = ast.parse(script.read_text())
    imports = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert imports.isdisjoint({"socket", "urllib", "http", "requests", "subprocess"})
    env = {
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(Path(__file__).parents[2] / "src"),
        "TELEGRAM_BOT_TOKEN": "SECRET_CANARY",
        "SEARCH_API_KEY": "SECRET_CANARY",
    }
    payload = {
        "schema_version": "RankerInput/v1",
        "run_id": "run-empty",
        "profile_version": 1,
        "candidates": [],
        "intent": {"role_terms": [], "location_terms": [], "required_terms": [], "excluded_terms": []},
        "max_ranked": 20,
    }
    result = subprocess.run([sys.executable, str(script)], input=json.dumps(payload), text=True, capture_output=True, env=env, check=True)
    assert "SECRET_CANARY" not in result.stdout + result.stderr
    assert json.loads(result.stdout) == {"schema_version": "RankedCandidates/v1", "ranked": []}
