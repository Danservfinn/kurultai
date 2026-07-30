"""Read-only Hulagu G1 environment doctor.

Task 0 never starts services and never writes to the vault. The atomic-rename
contract is evaluated only from an explicit synthetic fixture at G1.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import plistlib
import stat

# Safe here because diskutil is an absolute fixed executable with fixed argv and no shell.
import subprocess  # nosec B404
from pathlib import Path
from typing import Any

INSTALL_RECORD = Path("/Users/kublai/Library/Application Support/Kurultai/Hulagu/install.json")
DEFAULT_VAULT = Path("/Volumes/KurultaiVault")


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
        enrolled_cli_sha256: str | None = None,
        enrolled_cli_version: str | None = None,
    ) -> None:
        self.vault_path = vault_path
        self.enrolled_volume_uuid = enrolled_volume_uuid
        self.container_cli_path = container_cli_path
        self.container_socket_path = container_socket_path
        self.enrolled_cli_sha256 = enrolled_cli_sha256
        self.enrolled_cli_version = enrolled_cli_version


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
        container_cli_sha256: str | None = None,
        container_cli_version: str | None = None,
        effective_state_inspected: bool = False,
    ) -> None:
        self.vault_present = vault_present
        self.volume_uuid = volume_uuid
        self.volume_encrypted = volume_encrypted
        self.container_cli_present = container_cli_present
        self.container_cli_approved = container_cli_approved
        self.container_socket_present = container_socket_present
        self.container_socket_approved = container_socket_approved
        self.container_cli_sha256 = container_cli_sha256
        self.container_cli_version = container_cli_version
        self.effective_state_inspected = effective_state_inspected


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
    cli_present = cli_absolute and config.container_cli_path.is_file() and not config.container_cli_path.is_symlink()
    socket_present = False
    try:
        socket_present = socket_absolute and stat.S_ISSOCK(config.container_socket_path.lstat().st_mode)
    except OSError:
        pass
    digest: str | None = None
    version: str | None = None
    effective = False
    if cli_present:
        digest = "sha256:" + hashlib.sha256(config.container_cli_path.read_bytes()).hexdigest()
    if cli_present and socket_present:
        try:
            completed = subprocess.run(  # nosec B603
                [
                    str(config.container_cli_path),
                    "-H",
                    f"unix://{config.container_socket_path}",
                    "version",
                    "--format",
                    "{{json .Client}}",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
                env={"PATH": "/usr/bin:/bin"},
            )
            if completed.returncode == 0 and completed.stdout.strip():
                version = completed.stdout.strip()[:500]
                effective = True
        except (OSError, subprocess.SubprocessError):
            pass
    return EnvironmentObservation(
        vault_present=vault_present,
        volume_uuid=volume_uuid,
        volume_encrypted=encrypted,
        container_cli_present=cli_present,
        container_cli_approved=cli_absolute and not config.container_cli_path.is_symlink(),
        container_socket_present=socket_present,
        container_socket_approved=socket_absolute and not config.container_socket_path.is_symlink(),
        container_cli_sha256=digest,
        container_cli_version=version,
        effective_state_inspected=effective,
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
    if config.enrolled_cli_sha256 is None:
        container_reasons.append("container_cli_digest_unenrolled")
    elif observation.container_cli_sha256 != config.enrolled_cli_sha256:
        container_reasons.append("container_cli_digest_drift")
    if config.enrolled_cli_version is None:
        container_reasons.append("container_cli_version_unenrolled")
    elif observation.container_cli_version != config.enrolled_cli_version:
        container_reasons.append("container_cli_version_drift")
    if not observation.effective_state_inspected:
        container_reasons.append("container_effective_state_unavailable")

    return {
        "mode": "read_only",
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


def _config_from_install_record(path: Path) -> DoctorConfig | None:
    if not path.exists():
        return None
    if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        return None
    try:
        value = json.loads(path.read_text())
        if value.get("schema_version") != "HulaguInstall/v1":
            return None
        return DoctorConfig(
            vault_path=Path(value["vault_path"]),
            enrolled_volume_uuid=str(value["vault_uuid"]),
            container_cli_path=Path(value["container_cli"]),
            container_socket_path=Path(value["engine_socket"]),
            enrolled_cli_sha256=str(value["container_cli_sha256"]),
            enrolled_cli_version=str(value["container_cli_version"]),
        )
    except (AttributeError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Hulagu environment doctor")
    parser.add_argument("--vault-path", type=Path)
    parser.add_argument("--enrolled-volume-uuid")
    parser.add_argument("--container-cli", type=Path)
    parser.add_argument("--container-socket", type=Path)
    parser.add_argument("--container-cli-sha256")
    parser.add_argument("--container-cli-version")
    parser.add_argument("--install-record", type=Path, default=INSTALL_RECORD)
    parser.add_argument("--atomic-probe-fixture", type=Path)
    parser.add_argument("--json", action="store_true", help="emit the stable JSON report")
    args = parser.parse_args(argv)
    explicit = (args.vault_path, args.container_cli, args.container_socket)
    if any(item is not None for item in explicit) and not all(item is not None for item in explicit):
        parser.error("explicit doctor mode requires vault, container CLI, and container socket")
    config = (
        DoctorConfig(
            vault_path=args.vault_path,
            enrolled_volume_uuid=args.enrolled_volume_uuid,
            container_cli_path=args.container_cli,
            container_socket_path=args.container_socket,
            enrolled_cli_sha256=args.container_cli_sha256,
            enrolled_cli_version=args.container_cli_version,
        )
        if all(item is not None for item in explicit)
        else _config_from_install_record(args.install_record)
    )
    record_status = "pass" if config is not None else "fail"
    if config is None:
        config = DoctorConfig(
            vault_path=DEFAULT_VAULT,
            enrolled_volume_uuid=None,
            container_cli_path=Path("/nonexistent/hulagu-container-cli"),
            container_socket_path=Path("/nonexistent/hulagu-engine.sock"),
        )
    report = evaluate_environment(config, observe_environment(config))
    report["installation_record"] = {
        "status": record_status,
        "path": str(args.install_record),
        "reason": None if record_status == "pass" else "missing_or_invalid",
    }
    if args.atomic_probe_fixture:
        fixture = json.loads(args.atomic_probe_fixture.read_text())
        report["atomic_rename_fixture"] = evaluate_atomic_rename(AtomicRenameObservation(**fixture))
    print(json.dumps(report, indent=2, sort_keys=True))
    return (
        0
        if record_status == "pass"
        and report["vault"]["status"] == "pass"
        and report["container_install"]["status"] == "pass"
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
