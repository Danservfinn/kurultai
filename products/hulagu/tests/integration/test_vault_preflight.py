from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).parents[2] / "deploy" / "scripts" / "doctor.py"
EXPECTED_UUID = "OWNER-ENROLLED-UUID"


def load_doctor() -> ModuleType:
    spec = importlib.util.spec_from_file_location("hulagu_doctor", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def valid_config(module: ModuleType):
    return module.DoctorConfig(
        vault_path=Path("/Volumes/ApprovedVault"),
        enrolled_volume_uuid=EXPECTED_UUID,
        container_cli_path=Path("/opt/approved/bin/docker"),
        container_socket_path=Path("/Users/operator/.approved/docker.sock"),
    )


def valid_observation(module: ModuleType):
    return module.EnvironmentObservation(
        vault_present=True,
        volume_uuid=EXPECTED_UUID,
        volume_encrypted=True,
        container_cli_present=True,
        container_cli_approved=True,
        container_socket_present=True,
        container_socket_approved=True,
    )


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"vault_present": False}, "vault_absent"),
        ({"volume_uuid": "WRONG-UUID"}, "vault_uuid_mismatch"),
        ({"volume_uuid": None}, "vault_uuid_absent"),
        ({"volume_encrypted": False}, "vault_unencrypted"),
    ],
)
def test_vault_identity_and_encryption_fail_closed(changes: dict[str, object], code: str) -> None:
    module = load_doctor()
    observation = valid_observation(module)
    for field, value in changes.items():
        setattr(observation, field, value)
    report = module.evaluate_environment(valid_config(module), observation)
    assert report["vault"]["status"] == "fail"
    assert code in report["vault"]["reasons"]


def test_unenrolled_vault_uuid_fails_closed() -> None:
    module = load_doctor()
    config = valid_config(module)
    config.enrolled_volume_uuid = None
    report = module.evaluate_environment(config, valid_observation(module))
    assert "vault_uuid_unenrolled" in report["vault"]["reasons"]


def test_g1_reports_runtime_services_not_evaluated() -> None:
    module = load_doctor()
    report = module.evaluate_environment(valid_config(module), valid_observation(module))
    assert report["postgresql"]["status"] == "not_evaluated"
    assert report["container_runtime"]["status"] == "not_evaluated"


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"container_cli_present": False}, "container_cli_absent"),
        ({"container_cli_approved": False}, "container_cli_unapproved"),
        ({"container_socket_present": False}, "container_socket_absent"),
        ({"container_socket_approved": False}, "container_socket_unapproved"),
    ],
)
def test_absolute_container_install_state_is_reported(changes: dict[str, object], code: str) -> None:
    module = load_doctor()
    observation = valid_observation(module)
    for field, value in changes.items():
        setattr(observation, field, value)
    report = module.evaluate_environment(valid_config(module), observation)
    assert code in report["container_install"]["reasons"]


def test_observer_does_not_search_path(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_doctor()
    monkeypatch.setenv("PATH", "/tmp/attacker-controlled")
    monkeypatch.setattr(shutil, "which", lambda *_: (_ for _ in ()).throw(AssertionError("PATH searched")))
    observation = module.observe_environment(valid_config(module))
    assert observation.container_cli_present is False
