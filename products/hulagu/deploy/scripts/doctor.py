"""Read-only Hulagu G1 environment doctor.

Task 0 never starts services and never writes to the vault. The atomic-rename
contract is evaluated only from an explicit synthetic fixture at G1.
"""

from __future__ import annotations

import argparse
import json
import plistlib

# Safe here because diskutil is an absolute fixed executable with fixed argv and no shell.
import subprocess  # nosec B404
from pathlib import Path
from typing import Any


class DoctorConfig:
    vault_path: Path
    enrolled_volume_uuid: str | None
    container_cli_path: Path
    container_socket_path: Path

    def __init__(
        self,
        *,
        vault_path: Path,
        enrolled_volume_uuid: str | None,
        container_cli_path: Path,
        container_socket_path: Path,
    ) -> None:
        self.vault_path = vault_path
        self.enrolled_volume_uuid = enrolled_volume_uuid
        self.container_cli_path = container_cli_path
        self.container_socket_path = container_socket_path


class EnvironmentObservation:
    vault_present: bool
    volume_uuid: str | None
    volume_encrypted: bool
    container_cli_present: bool
    container_cli_approved: bool
    container_socket_present: bool
    container_socket_approved: bool

    def __init__(
        self,
        *,
        vault_present: bool,
        volume_uuid: str | None,
        volume_encrypted: bool,
        container_cli_present: bool,
        container_cli_approved: bool,
        container_socket_present: bool,
        container_socket_approved: bool,
    ) -> None:
        self.vault_present = vault_present
        self.volume_uuid = volume_uuid
        self.volume_encrypted = volume_encrypted
        self.container_cli_present = container_cli_present
        self.container_cli_approved = container_cli_approved
        self.container_socket_present = container_socket_present
        self.container_socket_approved = container_socket_approved


class AtomicRenameObservation:
    source_device: int
    destination_device: int
    replace_succeeded: bool
    file_fsynced: bool
    parent_fsynced: bool

    def __init__(
        self,
        *,
        source_device: int,
        destination_device: int,
        replace_succeeded: bool,
        file_fsynced: bool,
        parent_fsynced: bool,
    ) -> None:
        self.source_device = source_device
        self.destination_device = destination_device
        self.replace_succeeded = replace_succeeded
        self.file_fsynced = file_fsynced
        self.parent_fsynced = parent_fsynced


def _disk_observation(path: Path) -> tuple[str | None, bool]:
    diskutil = Path("/usr/sbin/diskutil")
    if not diskutil.is_file():
        return None, False
    # The executable and operation are fixed; the enrolled path is passed only as a data argument.
    completed = subprocess.run(  # nosec B603
        [str(diskutil), "info", "-plist", str(path)],
        check=False,
        capture_output=True,
        timeout=10,
    )
    if completed.returncode != 0:
        return None, False
    try:
        info = plistlib.loads(completed.stdout)
    except (plistlib.InvalidFileException, ValueError):
        return None, False
    uuid = info.get("VolumeUUID")
    encrypted = bool(info.get("Encrypted") or info.get("FileVault"))
    return (str(uuid) if uuid else None), encrypted


def observe_environment(config: DoctorConfig) -> EnvironmentObservation:
    """Observe only enrolled absolute paths; never search PATH or Docker contexts."""
    vault_present = config.vault_path.is_dir()
    volume_uuid, encrypted = _disk_observation(config.vault_path) if vault_present else (None, False)
    cli_absolute = config.container_cli_path.is_absolute()
    socket_absolute = config.container_socket_path.is_absolute()
    return EnvironmentObservation(
        vault_present=vault_present,
        volume_uuid=volume_uuid,
        volume_encrypted=encrypted,
        container_cli_present=cli_absolute and config.container_cli_path.is_file(),
        container_cli_approved=cli_absolute,
        container_socket_present=socket_absolute and config.container_socket_path.exists(),
        container_socket_approved=socket_absolute,
    )


def evaluate_environment(config: DoctorConfig, observation: EnvironmentObservation) -> dict[str, Any]:
    vault_reasons: list[str] = []
    if not observation.vault_present:
        vault_reasons.append("vault_absent")
    if config.enrolled_volume_uuid is None:
        vault_reasons.append("vault_uuid_unenrolled")
    if observation.volume_uuid is None:
        vault_reasons.append("vault_uuid_absent")
    elif config.enrolled_volume_uuid is not None and observation.volume_uuid != config.enrolled_volume_uuid:
        vault_reasons.append("vault_uuid_mismatch")
    if not observation.volume_encrypted:
        vault_reasons.append("vault_unencrypted")

    container_reasons: list[str] = []
    if not observation.container_cli_present:
        container_reasons.append("container_cli_absent")
    if not observation.container_cli_approved:
        container_reasons.append("container_cli_unapproved")
    if not observation.container_socket_present:
        container_reasons.append("container_socket_absent")
    if not observation.container_socket_approved:
        container_reasons.append("container_socket_unapproved")

    return {
        "mode": "G1_read_only",
        "mutation_performed": False,
        "vault": {"status": "fail" if vault_reasons else "pass", "reasons": vault_reasons},
        "container_install": {"status": "fail" if container_reasons else "pass", "reasons": container_reasons},
        "postgresql": {"status": "not_evaluated", "reasons": []},
        "container_runtime": {"status": "not_evaluated", "reasons": []},
    }


def evaluate_atomic_rename(observation: AtomicRenameObservation) -> dict[str, Any]:
    reasons: list[str] = []
    if observation.source_device != observation.destination_device:
        reasons.append("cross_volume")
    if not observation.replace_succeeded:
        reasons.append("replace_failed")
    if not observation.file_fsynced:
        reasons.append("file_fsync_missing")
    if not observation.parent_fsynced:
        reasons.append("parent_fsync_missing")
    return {"status": "fail" if reasons else "pass", "reasons": reasons}


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Hulagu G1 environment doctor")
    parser.add_argument("--vault-path", type=Path, required=True)
    parser.add_argument("--enrolled-volume-uuid")
    parser.add_argument("--container-cli", type=Path, required=True)
    parser.add_argument("--container-socket", type=Path, required=True)
    parser.add_argument("--atomic-probe-fixture", type=Path)
    args = parser.parse_args()
    config = DoctorConfig(
        vault_path=args.vault_path,
        enrolled_volume_uuid=args.enrolled_volume_uuid,
        container_cli_path=args.container_cli,
        container_socket_path=args.container_socket,
    )
    report = evaluate_environment(config, observe_environment(config))
    if args.atomic_probe_fixture:
        fixture = json.loads(args.atomic_probe_fixture.read_text())
        report["atomic_rename_fixture"] = evaluate_atomic_rename(AtomicRenameObservation(**fixture))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["vault"]["status"] == "pass" and report["container_install"]["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
