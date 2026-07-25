"""Observation-only, fail-closed G1 preflight probes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import stat
import subprocess  # nosec B404 -- only fixed /usr/sbin/diskutil, never PATH/shell
import tempfile
from pathlib import Path
from typing import Protocol

from hulagu.config import ContainerEnrollment, HulaguConfig, VaultEnrollment

DISKUTIL = Path("/usr/sbin/diskutil")
ENROLLED_VAULT_HOME = Path("/Volumes/KurultaiVault")
DEFAULT_CONFIG_PATH = Path(
    "/Users/kublai/Library/Application Support/Kurultai/Hulagu/install.json"
)
HEALTH_REPORT_SCHEMA_VERSION = "health-report/v1"
_SHA256_HEX = frozenset("0123456789abcdef")


class Observer(Protocol):
    def volume_info(self, path: Path) -> dict: ...
    def executable_ok(self, path: Path) -> bool: ...
    def executable_sha256(self, path: Path) -> str | None: ...
    def unix_socket_ok(self, path: Path) -> bool: ...


def _plist_encrypted(info: dict) -> bool:
    """Interpret only explicit affirmative plist values; unknown text fails closed."""
    for key in ("Encrypted", "APFSEncrypted", "FileVault"):
        value = info.get(key)
        if value is True:
            return True
        if isinstance(value, str) and value.strip().casefold() in {
            "yes",
            "true",
            "encrypted",
            "on",
        }:
            return True
    return False


class SystemObserver:
    """Read-only local observations. It never discovers executables through PATH."""

    def volume_info(self, path: Path) -> dict:
        if not path.exists() or not DISKUTIL.is_file():
            return {"exists": path.exists(), "uuid": None, "encrypted": False}
        try:
            result = subprocess.run(  # noqa: S603  # nosec B603 -- fixed binary
                [str(DISKUTIL), "info", "-plist", str(path)],
                check=True,
                capture_output=True,
                timeout=10,
            )
            info = plistlib.loads(result.stdout)
        except (OSError, subprocess.SubprocessError, plistlib.InvalidFileException):
            return {"exists": True, "uuid": None, "encrypted": False}
        return {
            "exists": True,
            "uuid": info.get("VolumeUUID") or info.get("APFSVolumeUUID"),
            "encrypted": _plist_encrypted(info),
        }

    def executable_ok(self, path: Path) -> bool:
        return path.is_file() and os.access(path, os.X_OK)

    def executable_sha256(self, path: Path) -> str | None:
        try:
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest()
        except OSError:
            return None

    def unix_socket_ok(self, path: Path) -> bool:
        try:
            return stat.S_ISSOCK(path.stat().st_mode)
        except OSError:
            return False


def _valid_sha256(value: str | None) -> bool:
    return bool(value and len(value) == 64 and set(value) <= _SHA256_HEX)


def _vault_check(enrollment: VaultEnrollment, observer: Observer) -> dict:
    reasons: list[str] = []
    if not enrollment.mount_path.is_absolute():
        reasons.append("vault_path_not_absolute")
    if enrollment.mount_path != ENROLLED_VAULT_HOME:
        reasons.append("vault_path_not_enrolled_home")
    info = observer.volume_info(enrollment.mount_path)
    if not info.get("exists"):
        reasons.append("absent")
    if not enrollment.expected_volume_uuid:
        reasons.append("unenrolled_uuid")
    elif info.get("uuid") != enrollment.expected_volume_uuid:
        reasons.append("wrong_uuid")
    if not info.get("encrypted"):
        reasons.append("unencrypted")
    return {"status": "fail" if reasons else "pass", "reasons": reasons}


def _container_check(enrollment: ContainerEnrollment, observer: Observer) -> dict:
    reasons: list[str] = []
    cli = enrollment.cli_path
    socket = enrollment.socket_path
    approved_sha = enrollment.approved_cli_sha256
    if cli is None:
        reasons.append("unenrolled_cli")
    elif not cli.is_absolute():
        reasons.append("cli_not_absolute")
    elif not observer.executable_ok(cli):
        reasons.append("cli_absent_or_not_executable")
    if not approved_sha:
        reasons.append("unenrolled_cli_sha256")
    elif not _valid_sha256(approved_sha):
        reasons.append("invalid_cli_sha256")
    elif cli is not None and cli.is_absolute() and observer.executable_ok(cli):
        observed_sha = observer.executable_sha256(cli)
        if observed_sha != approved_sha:
            reasons.append("cli_sha256_mismatch")
    if socket is None:
        reasons.append("unenrolled_socket")
    elif not socket.is_absolute():
        reasons.append("socket_not_absolute")
    elif not observer.unix_socket_ok(socket):
        reasons.append("socket_absent_or_not_unix")
    return {"status": "fail" if reasons else "pass", "reasons": reasons}


def run_doctor(config: HulaguConfig, observer: Observer | None = None) -> dict:
    observer = observer or SystemObserver()
    return {
        "schema_version": HEALTH_REPORT_SCHEMA_VERSION,
        "mode": "observation_only",
        "checks": {
            "vault": _vault_check(config.vault, observer),
            "container_enrollment": _container_check(config.container, observer),
        },
        "runtime": {"postgresql": "not_evaluated", "container": "not_evaluated"},
        "mutation_performed": False,
    }


def probe_atomic_rename_fixture(
    source_dir: Path,
    destination_dir: Path,
    *,
    stat_fn=os.stat,
    replace_fn=os.replace,
) -> dict:
    """Exercise rename only on a synthetic fixture after proving same-volume identity."""
    reasons: list[str] = []
    if stat_fn(source_dir).st_dev != stat_fn(destination_dir).st_dev:
        return {"status": "fail", "reasons": ["different_volume"]}
    source: Path | None = None
    destination: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=source_dir, prefix=".hulagu-probe-", delete=False
        ) as handle:
            handle.write(b"synthetic-hulagu-probe")
            handle.flush()
            os.fsync(handle.fileno())
            source = Path(handle.name)
        destination = destination_dir / f"{source.name}.renamed"
        replace_fn(source, destination)
        if not destination.exists():
            reasons.append("destination_missing")
    except OSError:
        reasons.append("atomic_rename_failed")
    finally:
        for candidate in (source, destination):
            if candidate is not None:
                try:
                    candidate.unlink(missing_ok=True)
                except OSError:
                    reasons.append("fixture_cleanup_failed")
    return {"status": "fail" if reasons else "pass", "reasons": reasons}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Observation-only Hulagu G1 doctor")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="authorized JSON install record",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the machine-readable health-report/v1 document (the default output)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        raw = json.loads(args.config.read_text(encoding="utf-8"))
        config = HulaguConfig.from_mapping(raw)
        report = run_doctor(config)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report = {
            "schema_version": HEALTH_REPORT_SCHEMA_VERSION,
            "mode": "observation_only",
            "checks": {"configuration": {"status": "fail", "reasons": [type(exc).__name__]}},
            "runtime": {"postgresql": "not_evaluated", "container": "not_evaluated"},
            "mutation_performed": False,
        }
    print(json.dumps(report, sort_keys=True))
    return 0 if all(check["status"] == "pass" for check in report["checks"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
