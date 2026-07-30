"""Dry-run-first Hulagu uninstall that preserves customer data by default."""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import shutil  # noqa: F401 -- regression probes ensure path-named rmtree is not reintroduced
import stat
import subprocess  # nosec B404
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

DEFAULT_DATA_ROOT = Path("/Volumes/KurultaiVault/hulagu")
_CONFIRMATION = "DELETE-HULAGU-CUSTOMER-DATA"
_SERVICE_LABELS = (
    "com.kurultai.hulagu-deletion",
    "com.kurultai.hulagu-runner",
    "com.kurultai.hulagu-app",
    "com.kurultai.hulagu-postgres",
)
DEFAULT_CODE_CONFIG_PATHS = (
    Path("/Users/kublai/Library/Application Support/Kurultai/Hulagu/install.json"),
    *(Path("/Users/kublai/Library/LaunchAgents") / f"{label}.plist" for label in _SERVICE_LABELS),
)


class VaultInspector(Protocol):
    def inspect_vault(self, path: Path) -> tuple[str, bool, int, int]: ...


class NativeVaultInspector:
    def inspect_vault(self, path: Path) -> tuple[str, bool, int, int]:
        completed = subprocess.run(  # nosec B603
            ["/usr/sbin/diskutil", "info", "-plist", str(path)],
            check=True,
            capture_output=True,
            timeout=10,
            env={"PATH": "/usr/bin:/bin"},
        )
        payload = plistlib.loads(completed.stdout)
        usage = os.statvfs(path)
        return (
            str(payload.get("VolumeUUID") or ""),
            bool(payload.get("Encrypted") or payload.get("FileVault")),
            usage.f_blocks * usage.f_frsize,
            usage.f_bavail * usage.f_frsize,
        )


def _stop_service(label: str) -> bool:
    completed = subprocess.run(  # nosec B603
        ["/bin/launchctl", "bootout", f"gui/{os.getuid()}/{label}"],
        check=False,
        capture_output=True,
        timeout=15,
        env={"PATH": "/usr/bin:/bin"},
    )
    stderr = completed.stderr.decode(errors="replace") if isinstance(completed.stderr, bytes) else completed.stderr
    if completed.returncode == 0:
        return True
    if "Could not find specified service" in stderr or "No such process" in stderr:
        return False
    raise RuntimeError("launchctl service stop failed")


def _load_install_record(path: Path) -> dict[str, object]:
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise PermissionError("unsafe enrolled install record")
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or value.get("schema_version") != "HulaguInstall/v1":
        raise ValueError("invalid enrolled install record")
    return value


def _confined_identity(path: Path) -> tuple[int, int]:
    if not path.is_absolute() or path == Path("/"):
        raise ValueError("unsafe customer data root")
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        metadata = current.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError("unsafe customer data root symlink")
    metadata = path.lstat()
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError("unsafe customer data root")
    return metadata.st_dev, metadata.st_ino


def _clear_directory(descriptor: int, *, flags: int, nofollow: int) -> None:
    """Erase descendants through held directory identities, never a reopened root path."""

    for name in os.listdir(descriptor):
        metadata = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        if stat.S_ISDIR(metadata.st_mode):
            child = os.open(name, flags | nofollow, dir_fd=descriptor)
            try:
                opened = os.fstat(child)
                if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
                    raise PermissionError("customer data descendant identity drifted at deletion effect")
                _clear_directory(child, flags=flags, nofollow=nofollow)
            finally:
                os.close(child)
            current = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino):
                raise PermissionError("customer data descendant identity drifted at deletion effect")
            os.rmdir(name, dir_fd=descriptor)
        else:
            os.unlink(name, dir_fd=descriptor)


def _confined_rmtree(path: Path, expected_identity: tuple[int, int]) -> None:
    """Remove only the enrolled directory opened through no-follow descriptors."""

    if not path.is_absolute() or path == Path("/") or not path.name:
        raise ValueError("unsafe customer data root")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path.anchor, flags | nofollow)
    try:
        for component in path.parent.parts[1:]:
            next_descriptor = os.open(component, flags | nofollow, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        target_descriptor = os.open(path.name, flags | nofollow, dir_fd=descriptor)
        try:
            metadata = os.fstat(target_descriptor)
            if not stat.S_ISDIR(metadata.st_mode):
                raise ValueError("unsafe customer data root")
            if (metadata.st_dev, metadata.st_ino) != expected_identity:
                raise PermissionError("customer data root identity drifted at deletion effect")
            _clear_directory(target_descriptor, flags=flags, nofollow=nofollow)
        finally:
            os.close(target_descriptor)
        current = os.stat(path.name, dir_fd=descriptor, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != expected_identity:
            raise PermissionError("customer data root identity drifted at deletion effect")
        if not stat.S_ISDIR(current.st_mode):
            raise ValueError("unsafe customer data root")
        os.rmdir(path.name, dir_fd=descriptor)
    finally:
        os.close(descriptor)


def _remove_code_config(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        metadata = path.lstat()
        _confined_rmtree(path, (metadata.st_dev, metadata.st_ino))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hulagu-uninstall")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--delete-customer-data", action="store_true")
    parser.add_argument("--confirm")
    return parser


def run(
    argv: list[str] | None = None,
    *,
    data_root: Path = DEFAULT_DATA_ROOT,
    remove_path: Callable[[Path, tuple[int, int]], None] = _confined_rmtree,
    stop_service: Callable[[str], bool] = _stop_service,
    code_config_paths: tuple[Path, ...] = DEFAULT_CODE_CONFIG_PATHS,
    remove_code_config: Callable[[Path], None] = _remove_code_config,
    record_path: Path = DEFAULT_CODE_CONFIG_PATHS[0],
    inspector: VaultInspector | None = None,
) -> dict[str, object]:
    args = _parser().parse_args(argv)
    if args.delete_customer_data and args.confirm != _CONFIRMATION:
        raise PermissionError("destructive customer-data confirmation is required")
    if args.confirm is not None and not args.delete_customer_data:
        raise ValueError("destructive confirmation requires --delete-customer-data")
    if args.delete_customer_data and (
        not data_root.is_absolute() or data_root == Path("/") or data_root.is_symlink()
    ):
        raise ValueError("unsafe customer data root")
    record: dict[str, object] | None = None
    identity: tuple[int, int] | None = None
    if args.delete_customer_data and args.apply:
        record = _load_install_record(record_path)
        vault_path = Path(str(record.get("vault_path", "")))
        expected_root = vault_path / "hulagu"
        if data_root != expected_root:
            raise PermissionError("customer data root does not match enrollment")
        identity = _confined_identity(data_root)

    report: dict[str, object] = {
        "schema_version": "HulaguUninstallPlan/v1",
        "mutation_performed": False,
        "service_stop_order": list(_SERVICE_LABELS),
        "remove_code_and_config": True,
        "customer_data_path": str(data_root),
        "customer_data_deleted": False,
    }
    if not args.apply:
        return report
    for label in _SERVICE_LABELS:
        outcome = stop_service(label)
        if not isinstance(outcome, bool):
            raise TypeError("invalid service stop outcome")
    if args.delete_customer_data:
        if record is None or identity is None:
            raise RuntimeError("destructive uninstall authority was not established")
        inspector = inspector or NativeVaultInspector()
        observed_uuid, encrypted, _capacity, _free = inspector.inspect_vault(Path(str(record["vault_path"])))
        if not encrypted or observed_uuid != record.get("vault_uuid"):
            raise PermissionError("mounted encrypted vault identity drifted")
        if _confined_identity(data_root) != identity:
            raise PermissionError("customer data root identity drifted")
    if args.delete_customer_data:
        if identity is None:
            raise RuntimeError("destructive uninstall authority was not established")
        try:
            remove_path(data_root, identity)
        except FileNotFoundError:
            pass
        report["customer_data_deleted"] = True
    for path in code_config_paths:
        remove_code_config(path)
    report["mutation_performed"] = True
    return report


def main(argv: list[str] | None = None) -> int:
    report = run(argv)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
