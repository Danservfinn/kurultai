from __future__ import annotations

import ast
import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from hulagu.runtime.container import ContainerExecutionError, ParserContainerExecutor
from hulagu.runtime.policy import ContainerEffectiveState, EngineEnrollment, ParserInvocation


class FakeBackend:
    def __init__(self, effective: ContainerEffectiveState) -> None:
        self.effective = effective
        self.invocations: list[ParserInvocation] = []
        self.removed: list[str] = []
        self.starts: list[str] = []

    def create_parser(self, invocation: ParserInvocation) -> str:
        self.invocations.append(invocation)
        return "container-1"

    def inspect(self, container_id: str) -> ContainerEffectiveState:
        assert container_id == "container-1"
        return self.effective

    def start(self, container_id: str, timeout_seconds: int, input_payload: bytes) -> bytes:
        assert container_id == "container-1" and timeout_seconds == 30
        assert input_payload == b"synthetic"
        self.starts.append(container_id)
        digest = hashlib.sha256(input_payload).hexdigest().encode()
        return b'{"schema_version":"ParsedCv/v1","document_sha256":"' + digest + b'","fields":[]}'

    def remove(self, container_id: str) -> None:
        self.removed.append(container_id)


def secure_state() -> ContainerEffectiveState:
    return ContainerEffectiveState(
        network_mode="none",
        environment_keys=(),
        mounts=(),
        user="65532:65532",
        cap_drop=("ALL",),
        no_new_privileges=True,
        read_only=True,
        pids_limit=64,
        memory_bytes=268_435_456,
        cpu_count=1.0,
        tmpfs_bytes=67_108_864,
        open_files=128,
        supplementary_groups=(),
    )


def enrollment(tmp_path: Path) -> EngineEnrollment:
    cli = tmp_path / "docker"
    cli.write_bytes(b"synthetic enrolled executable")
    cli.chmod(0o700)
    socket = tmp_path / "docker.sock"
    socket.touch()
    return EngineEnrollment(
        cli_path=cli,
        cli_sha256=hashlib.sha256(cli.read_bytes()).hexdigest(),
        socket_path=socket,
        image="hulagu-parser@sha256:" + "b" * 64,
    )


def execute_synthetic(executor: ParserContainerExecutor) -> bytes:
    return executor.execute(
        b"synthetic",
        expected_digest=hashlib.sha256(b"synthetic").hexdigest(),
    )


def test_app_boundary_has_no_container_engine_or_parser_imports() -> None:
    root = Path(__file__).parents[2] / "src" / "hulagu"
    forbidden_imports = {"subprocess", "docker", "pypdf", "PyPDF2", "fitz", "docx"}
    for relative in ("app.py", "telegram/documents.py"):
        tree = ast.parse((root / relative).read_text())
        imported = {
            node.names[0].name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom)) and node.names
        }
        assert imported.isdisjoint(forbidden_imports)
    assert "runtime.container" not in (root / "app.py").read_text()
    assert "runtime.container" not in (root / "telegram" / "documents.py").read_text()


def test_engine_is_never_discovered_through_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("shutil.which", lambda *_: (_ for _ in ()).throw(AssertionError("PATH searched")))
    config = enrollment(tmp_path)
    assert config.validate().cli_path == config.cli_path


def test_unapproved_executable_and_socket_drift_fail_closed(tmp_path: Path) -> None:
    config = enrollment(tmp_path)
    config.cli_path.write_bytes(b"drift")
    with pytest.raises(ValueError, match="executable digest"):
        config.validate()
    other = tmp_path / "other.sock"
    other.touch()
    with pytest.raises(ValueError, match="socket"):
        EngineEnrollment(config.cli_path, hashlib.sha256(b"drift").hexdigest(), other, config.image, approved_socket_path=config.socket_path).validate()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda state: replace(state, network_mode="bridge"),
        lambda state: replace(state, environment_keys=("OPENAI_API_KEY",)),
        lambda state: replace(state, mounts=state.mounts + ((Path("/Users"), "/host", True),)),
        lambda state: replace(state, supplementary_groups=(20,)),
        lambda state: replace(state, no_new_privileges=False),
    ],
)
def test_effective_container_network_secret_mount_and_privilege_drift_is_rejected(tmp_path: Path, mutate: object) -> None:
    input_path = tmp_path / "input.pdf"
    input_path.write_bytes(b"synthetic")
    output_path = tmp_path / "output"
    output_path.mkdir()
    initial = secure_state()
    backend = FakeBackend(mutate(initial))  # type: ignore[operator]
    executor = ParserContainerExecutor(enrollment(tmp_path), backend=backend)
    with pytest.raises(ContainerExecutionError):
        execute_synthetic(executor)
    assert backend.starts == [] and backend.removed == ["container-1"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda state: replace(state, pids_limit=0),
        lambda state: replace(state, pids_limit=-1),
        lambda state: replace(state, memory_bytes=0),
        lambda state: replace(state, cpu_count=0),
        lambda state: replace(state, cpu_count=float("inf")),
        lambda state: replace(state, tmpfs_bytes=0),
        lambda state: replace(state, open_files=0),
        lambda state: replace(state, open_files=-1),
        lambda state: replace(state, pids_limit=65),
        lambda state: replace(state, memory_bytes=268_435_457),
        lambda state: replace(state, cpu_count=1.01),
        lambda state: replace(state, tmpfs_bytes=67_108_865),
        lambda state: replace(state, open_files=129),
    ],
)
def test_absent_unlimited_nonpositive_and_excessive_effective_limits_never_start(
    tmp_path: Path,
    mutate: object,
) -> None:
    input_path = tmp_path / "input.pdf"
    input_path.write_bytes(b"synthetic")
    output_path = tmp_path / "output"
    output_path.mkdir()
    backend = FakeBackend(mutate(secure_state()))  # type: ignore[operator]
    executor = ParserContainerExecutor(enrollment(tmp_path), backend=backend)
    with pytest.raises(ContainerExecutionError, match="resource policy drift"):
        execute_synthetic(executor)
    assert backend.starts == []
    assert backend.removed == ["container-1"]


def test_executor_exposes_only_typed_fixed_parser_invocation(tmp_path: Path) -> None:
    input_path = tmp_path / "input.pdf"
    input_path.write_bytes(b"synthetic")
    output_path = tmp_path / "output"
    output_path.mkdir()
    backend = FakeBackend(secure_state())
    executor = ParserContainerExecutor(enrollment(tmp_path), backend=backend)
    execute_synthetic(executor)
    invocation = backend.invocations[0]
    assert not hasattr(invocation, "input_path") and not hasattr(invocation, "output_path")
    assert backend.effective.mounts == ()
    assert not hasattr(executor, "run") and not hasattr(executor, "execute_argv")
    assert backend.removed == ["container-1"]

def test_executor_accepts_verified_bytes_without_host_input_or_output_paths(tmp_path: Path) -> None:
    backend = FakeBackend(secure_state())
    executor = ParserContainerExecutor(enrollment(tmp_path), backend=backend)

    payload = executor.execute(
        b"synthetic",
        expected_digest=hashlib.sha256(b"synthetic").hexdigest(),
    )

    assert b'"schema_version":"ParsedCv/v1"' in payload
    invocation = backend.invocations[0]
    assert not hasattr(invocation, "input_path")
    assert not hasattr(invocation, "output_path")
    assert backend.effective.mounts == ()
    assert backend.starts == ["container-1"]

def test_executor_rejects_unverified_bytes_before_container_creation(tmp_path: Path) -> None:
    backend = FakeBackend(secure_state())
    executor = ParserContainerExecutor(enrollment(tmp_path), backend=backend)

    with pytest.raises(ContainerExecutionError, match="verified parser input"):
        executor.execute(b"synthetic", expected_digest="0" * 64)

    assert backend.invocations == []
    assert backend.starts == []
