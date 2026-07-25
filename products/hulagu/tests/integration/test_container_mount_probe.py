from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

PRODUCT_ROOT = Path(__file__).parents[2]
SCRIPT = PRODUCT_ROOT / "deploy/scripts/doctor.py"


def load_doctor():
    spec = importlib.util.spec_from_file_location("doctor_container", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Observer:
    def __init__(self, *, cli=True, socket=True, cli_sha="a" * 64):
        self.cli = cli
        self.socket = socket
        self.cli_sha = cli_sha

    def volume_info(self, path: Path) -> dict:
        return {"exists": True, "uuid": "ENROLLED", "encrypted": True}

    def executable_ok(self, path: Path) -> bool:
        return self.cli

    def executable_sha256(self, path: Path) -> str | None:
        return self.cli_sha

    def unix_socket_ok(self, path: Path) -> bool:
        return self.socket


def config(cli, socket, approved_sha="a" * 64):
    from hulagu.config import ContainerEnrollment, HulaguConfig, VaultEnrollment

    return HulaguConfig(
        vault=VaultEnrollment(Path("/Volumes/KurultaiVault"), "ENROLLED"),
        container=ContainerEnrollment(
            Path(cli) if cli else None,
            Path(socket) if socket else None,
            approved_sha,
        ),
    )


@pytest.mark.parametrize(
    ("cli", "socket", "observer", "reason"),
    [
        (None, None, Observer(), "unenrolled_cli"),
        ("container-cli", "/approved/engine.sock", Observer(), "cli_not_absolute"),
        ("/approved/container-cli", "engine.sock", Observer(), "socket_not_absolute"),
        (
            "/approved/container-cli",
            "/approved/engine.sock",
            Observer(cli=False),
            "cli_absent_or_not_executable",
        ),
        (
            "/approved/container-cli",
            "/approved/engine.sock",
            Observer(socket=False),
            "socket_absent_or_not_unix",
        ),
    ],
)
def test_container_enrollment_fails_closed(cli, socket, observer: Observer, reason: str) -> None:
    report = load_doctor().run_doctor(config(cli, socket), observer)
    assert report["checks"]["container_enrollment"]["status"] == "fail"
    assert reason in report["checks"]["container_enrollment"]["reasons"]
    assert report["runtime"]["container"] == "not_evaluated"


def test_container_probe_never_searches_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        shutil,
        "which",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("PATH searched")),
    )
    report = load_doctor().run_doctor(config(None, None), Observer())
    assert report["checks"]["container_enrollment"]["status"] == "fail"


def test_approved_absolute_cli_and_socket_pass_source_contract() -> None:
    report = load_doctor().run_doctor(
        config("/approved/container-cli", "/approved/engine.sock"), Observer()
    )
    assert report["checks"]["container_enrollment"] == {"status": "pass", "reasons": []}
    assert report["runtime"]["container"] == "not_evaluated"


@pytest.mark.parametrize(
    ("approved_sha", "observer", "reason"),
    [
        (None, Observer(), "unenrolled_cli_sha256"),
        ("not-a-digest", Observer(), "invalid_cli_sha256"),
        ("a" * 64, Observer(cli_sha="b" * 64), "cli_sha256_mismatch"),
    ],
)
def test_container_enrollment_binds_approved_executable_digest(
    approved_sha, observer, reason
) -> None:
    report = load_doctor().run_doctor(
        config("/approved/container-cli", "/approved/engine.sock", approved_sha), observer
    )
    assert reason in report["checks"]["container_enrollment"]["reasons"]
