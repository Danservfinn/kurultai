"""Fixed parser-container executor bound to an enrolled local engine."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess  # nosec B404
import threading
from pathlib import Path
from typing import IO, Protocol

from .policy import ContainerEffectiveState, EngineEnrollment, ParserInvocation, safe_container_name

_ALLOWED_ENVIRONMENT_KEYS = {
    "LANG",
    "PATH",
    "PYTHON_PIP_VERSION",
    "PYTHON_SHA256",
    "PYTHON_VERSION",
}
_CONTAINER_TMP = "/" + "tmp"
_CONTAINER_TMPFS = _CONTAINER_TMP + ":rw,noexec,nosuid,nodev,size=67108864"
_STREAM_LIMIT_BYTES = 1_048_576


class ContainerExecutionError(RuntimeError):
    pass


class ContainerBackend(Protocol):
    def create_parser(self, invocation: ParserInvocation) -> str: ...
    def inspect(self, container_id: str) -> ContainerEffectiveState: ...
    def start(self, container_id: str, timeout_seconds: int, input_payload: bytes) -> bytes: ...
    def remove(self, container_id: str) -> None: ...


class DockerCliBackend:
    """Docker CLI adapter that never searches PATH and has no generic public command method."""

    def __init__(self, enrollment: EngineEnrollment) -> None:
        self._enrollment = enrollment.validate()

    def _invoke(
        self,
        arguments: tuple[str, ...],
        *,
        timeout: int = 15,
        input_payload: bytes | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        command = (str(self._enrollment.cli_path), "-H", self._enrollment.endpoint, *arguments)
        try:
            process = subprocess.Popen(  # nosec B603
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={"PATH": "/usr/bin:/bin"},
                start_new_session=True,
            )
            if process.stdin is None or process.stdout is None or process.stderr is None:
                raise ContainerExecutionError("missing process stream")
            stdin = process.stdin
            stdout = process.stdout
            stderr = process.stderr
            buffers = {"stdout": bytearray(), "stderr": bytearray()}
            violation: list[str] = []
            lock = threading.Lock()

            def terminate() -> None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except OSError:
                    process.kill()

            def drain(stream: IO[bytes], name: str) -> None:
                while True:
                    chunk = stream.read(65_536)
                    if not chunk:
                        return
                    with lock:
                        remaining = _STREAM_LIMIT_BYTES - len(buffers[name])
                        buffers[name].extend(chunk[:remaining])
                        if len(chunk) > remaining and not violation:
                            violation.append(name)
                            terminate()
                            return

            def write_input() -> None:
                try:
                    stdin.write(input_payload or b"")
                    stdin.flush()
                except BrokenPipeError:
                    pass
                finally:
                    stdin.close()

            threads = [
                threading.Thread(target=drain, args=(stdout, "stdout"), daemon=True),
                threading.Thread(target=drain, args=(stderr, "stderr"), daemon=True),
                threading.Thread(target=write_input, daemon=True),
            ]
            for thread in threads:
                thread.start()
            try:
                return_code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                terminate()
                process.wait()
                raise
            finally:
                for thread in threads:
                    thread.join(timeout=1)
            if violation:
                raise ContainerExecutionError(f"{violation[0]} output limit")
            if return_code != 0:
                raise subprocess.CalledProcessError(return_code, command)
            return subprocess.CompletedProcess(command, return_code, bytes(buffers["stdout"]), bytes(buffers["stderr"]))
        except ContainerExecutionError:
            raise
        except (subprocess.SubprocessError, OSError) as error:
            raise ContainerExecutionError(type(error).__name__) from None

    def create_parser(self, invocation: ParserInvocation) -> str:
        script = "/sandbox/parse_cv.py" if invocation.job_kind == "parser" else "/sandbox/rank_candidates.py"
        result = self._invoke(
            (
                "create",
                "--interactive",
                "--name",
                invocation.name,
                "--network",
                "none",
                "--user",
                "65532:65532",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--read-only",
                "--pids-limit",
                "64",
                "--memory",
                "256m",
                "--cpus",
                "1",
                "--ulimit",
                "nofile=128:128",
                "--tmpfs",
                _CONTAINER_TMPFS,
                "--entrypoint",
                "/usr/local/bin/python",
                invocation.image,
                script,
                *(("-", f"{_CONTAINER_TMP}/result.json") if invocation.job_kind == "parser" else ()),
            )
        )
        container_id = result.stdout.decode("ascii", "strict").strip()
        if not container_id:
            raise ContainerExecutionError("engine returned no container id")
        return container_id

    def inspect(self, container_id: str) -> ContainerEffectiveState:
        result = self._invoke(("inspect", container_id))
        try:
            record = json.loads(result.stdout)[0]
            host = record["HostConfig"]
            config = record["Config"]
            mounts = tuple(
                (Path(item["Source"]), str(item["Destination"]), not bool(item.get("RW", False)))
                for item in record.get("Mounts", [])
            )
            tmpfs = host.get("Tmpfs", {}).get(_CONTAINER_TMP, "")
            tmpfs_bytes = int(next(part.split("=", 1)[1] for part in tmpfs.split(",") if part.startswith("size=")))
            ulimits = {item["Name"]: int(item["Hard"]) for item in host.get("Ulimits") or []}
            environment = tuple(sorted(item.split("=", 1)[0] for item in config.get("Env") or []))
            security = host.get("SecurityOpt") or []
            nano_cpus = int(host.get("NanoCpus") or 0)
            return ContainerEffectiveState(
                network_mode=str(host["NetworkMode"]),
                environment_keys=environment,
                mounts=mounts,
                user=str(config["User"]),
                cap_drop=tuple(host.get("CapDrop") or ()),
                no_new_privileges="no-new-privileges" in security,
                read_only=bool(host["ReadonlyRootfs"]),
                pids_limit=int(host["PidsLimit"]),
                memory_bytes=int(host["Memory"]),
                cpu_count=nano_cpus / 1_000_000_000,
                tmpfs_bytes=tmpfs_bytes,
                open_files=ulimits.get("nofile", 0),
                supplementary_groups=tuple(int(group) for group in host.get("GroupAdd") or ()),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, StopIteration):
            raise ContainerExecutionError("invalid engine inspection") from None

    def start(self, container_id: str, timeout_seconds: int, input_payload: bytes) -> bytes:
        return self._invoke(
            ("start", "--attach", "--interactive", container_id),
            timeout=timeout_seconds,
            input_payload=input_payload,
        ).stdout

    def remove(self, container_id: str) -> None:
        try:
            self._invoke(("rm", "--force", container_id))
        except ContainerExecutionError:
            return


class ParserContainerExecutor:
    def __init__(self, enrollment: EngineEnrollment, *, backend: ContainerBackend | None = None) -> None:
        self._enrollment = enrollment.validate()
        self._backend = backend or DockerCliBackend(self._enrollment)

    def execute(self, input_payload: bytes, *, expected_digest: str, job_kind: str = "parser") -> bytes:
        if hashlib.sha256(input_payload).hexdigest() != expected_digest:
            raise ContainerExecutionError("invalid verified parser input")
        if job_kind not in {"parser", "ranker"}:
            raise ContainerExecutionError("unsupported sandbox job kind")
        invocation = ParserInvocation(
            self._enrollment.image,
            safe_container_name(expected_digest, job_kind),
            job_kind,
        )
        container_id = self._backend.create_parser(invocation)
        try:
            effective = self._backend.inspect(container_id)
            self._validate_effective(effective, invocation)
            payload = self._backend.start(container_id, 30, input_payload)
            if len(payload) > _STREAM_LIMIT_BYTES:
                raise ContainerExecutionError(f"{job_kind} output limit")
            return payload
        finally:
            self._backend.remove(container_id)

    @staticmethod
    def _validate_effective(effective: ContainerEffectiveState, invocation: ParserInvocation) -> None:
        expected_mounts: set[tuple[Path, str, bool]] = set()
        if effective.network_mode != "none" or not set(effective.environment_keys) <= _ALLOWED_ENVIRONMENT_KEYS:
            raise ContainerExecutionError("network or environment policy drift")
        if set(effective.mounts) != expected_mounts:
            raise ContainerExecutionError("mount policy drift")
        if effective.user != "65532:65532" or effective.supplementary_groups:
            raise ContainerExecutionError("identity policy drift")
        if set(effective.cap_drop) != {"ALL"} or not effective.no_new_privileges or not effective.read_only:
            raise ContainerExecutionError("privilege policy drift")
        if (
            not 0 < effective.pids_limit <= 64
            or not 0 < effective.memory_bytes <= 268_435_456
            or not 0 < effective.cpu_count <= 1.0
            or not 0 < effective.tmpfs_bytes <= 67_108_864
            or not 0 < effective.open_files <= 128
        ):
            raise ContainerExecutionError("resource policy drift")


