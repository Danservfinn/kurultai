from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

PRODUCT_ROOT = Path(__file__).parents[2]
SCRIPT = PRODUCT_ROOT / "deploy/scripts/doctor.py"


def load_doctor():
    spec = importlib.util.spec_from_file_location("doctor", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Observer:
    def __init__(self, *, exists=True, uuid="ENROLLED", encrypted=True, cli=True, socket=True):
        self.exists = exists
        self.uuid = uuid
        self.encrypted = encrypted
        self.cli = cli
        self.socket = socket

    def volume_info(self, path: Path) -> dict:
        return {"exists": self.exists, "uuid": self.uuid, "encrypted": self.encrypted}

    def executable_ok(self, path: Path) -> bool:
        return self.cli

    def executable_sha256(self, path: Path) -> str | None:
        return "a" * 64

    def unix_socket_ok(self, path: Path) -> bool:
        return self.socket


def config(expected_uuid="ENROLLED"):
    from hulagu.config import ContainerEnrollment, HulaguConfig, VaultEnrollment

    return HulaguConfig(
        vault=VaultEnrollment(Path("/Volumes/KurultaiVault"), expected_uuid),
        container=ContainerEnrollment(
            Path("/approved/container-cli"), Path("/approved/engine.sock"), "a" * 64
        ),
    )


@pytest.mark.parametrize(
    ("observer", "expected_uuid", "reason"),
    [
        (Observer(exists=False), "ENROLLED", "absent"),
        (Observer(uuid="OTHER"), "ENROLLED", "wrong_uuid"),
        (Observer(), None, "unenrolled_uuid"),
        (Observer(encrypted=False), "ENROLLED", "unencrypted"),
    ],
)
def test_vault_preflight_fails_closed(
    observer: Observer, expected_uuid: str | None, reason: str
) -> None:
    report = load_doctor().run_doctor(config(expected_uuid), observer)
    assert report["checks"]["vault"]["status"] == "fail"
    assert reason in report["checks"]["vault"]["reasons"]
    assert report["runtime"]["postgresql"] == "not_evaluated"
    assert report["runtime"]["container"] == "not_evaluated"


def test_vault_preflight_accepts_exact_encrypted_enrollment() -> None:
    report = load_doctor().run_doctor(config(), Observer())
    assert report["checks"]["vault"] == {"status": "pass", "reasons": []}


def test_actual_doctor_report_validates_against_health_report_contract() -> None:
    from hulagu import schema_validator

    report = load_doctor().run_doctor(config(), Observer())

    schema_validator("health-report-v1").validate(report)


@pytest.mark.parametrize(
    ("mount_path", "reason"),
    [
        (Path("relative-vault"), "vault_path_not_absolute"),
        (Path("/Volumes/OtherVault"), "vault_path_not_enrolled_home"),
    ],
)
def test_vault_preflight_rejects_unapproved_home(mount_path: Path, reason: str) -> None:
    candidate = config()
    from hulagu.config import HulaguConfig, VaultEnrollment

    candidate = HulaguConfig(
        vault=VaultEnrollment(mount_path, candidate.vault.expected_volume_uuid),
        container=candidate.container,
    )
    report = load_doctor().run_doctor(candidate, Observer())
    assert reason in report["checks"]["vault"]["reasons"]


@pytest.mark.parametrize("value", [False, "No", "false", "unencrypted", None])
def test_plist_encryption_parser_fails_closed(value) -> None:
    assert load_doctor()._plist_encrypted({"FileVault": value}) is False


def test_atomic_rename_probe_fails_closed_across_volumes(tmp_path: Path) -> None:
    doctor = load_doctor()

    class Stat:
        def __init__(self, dev: int):
            self.st_dev = dev

    devices = {tmp_path / "source": 1, tmp_path / "destination": 2}
    for path in devices:
        path.mkdir()
    result = doctor.probe_atomic_rename_fixture(
        tmp_path / "source",
        tmp_path / "destination",
        stat_fn=lambda path: Stat(devices[Path(path)]),
    )
    assert result["status"] == "fail"
    assert "different_volume" in result["reasons"]


def test_atomic_rename_probe_fails_closed_when_replace_fails(tmp_path: Path) -> None:
    doctor = load_doctor()
    directory = tmp_path / "same-volume"
    directory.mkdir()

    def fail_replace(source, destination):
        raise OSError("synthetic replace failure")

    result = doctor.probe_atomic_rename_fixture(directory, directory, replace_fn=fail_replace)
    assert result["status"] == "fail"
    assert "atomic_rename_failed" in result["reasons"]


def test_doctor_cli_has_no_apply_mode() -> None:
    doctor = load_doctor()
    with pytest.raises(SystemExit):
        doctor.parse_args(["--apply"])


def test_frozen_doctor_json_command_emits_schema_valid_fail_closed_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from hulagu import schema_validator

    doctor = load_doctor()
    monkeypatch.setattr(doctor, "DEFAULT_CONFIG_PATH", tmp_path / "missing-install.json")

    exit_code = doctor.main(["--json"])
    report = __import__("json").loads(capsys.readouterr().out)

    assert exit_code == 1
    assert report["checks"]["configuration"]["status"] == "fail"
    assert report["mutation_performed"] is False
    schema_validator("health-report-v1").validate(report)
