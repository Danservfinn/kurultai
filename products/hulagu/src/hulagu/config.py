"""Frozen typed installation configuration; no ambient environment authority."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class VaultEnrollment:
    mount_path: Path
    expected_volume_uuid: str | None


@dataclass(frozen=True, slots=True)
class ContainerEnrollment:
    cli_path: Path | None
    socket_path: Path | None
    approved_cli_sha256: str | None


@dataclass(frozen=True, slots=True)
class HulaguConfig:
    vault: VaultEnrollment
    container: ContainerEnrollment

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> HulaguConfig:
        """Build config from an already-authorized mapping and reject unknown keys."""
        allowed = {"vault", "container"}
        unknown = set(raw) - allowed
        if unknown:
            raise ValueError(f"unknown configuration keys: {sorted(unknown)}")
        vault = _mapping(raw.get("vault"), "vault")
        container = _mapping(raw.get("container"), "container")
        _reject_unknown(vault, {"mount_path", "expected_volume_uuid"}, "vault")
        _reject_unknown(
            container,
            {"cli_path", "socket_path", "approved_cli_sha256"},
            "container",
        )
        return cls(
            vault=VaultEnrollment(
                mount_path=Path(_required_string(vault, "mount_path")),
                expected_volume_uuid=_optional_string(vault, "expected_volume_uuid"),
            ),
            container=ContainerEnrollment(
                cli_path=_optional_path(container, "cli_path"),
                socket_path=_optional_path(container, "socket_path"),
                approved_cli_sha256=_optional_string(container, "approved_cli_sha256"),
            ),
        )


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return value


def _reject_unknown(raw: Mapping[str, Any], allowed: set[str], name: str) -> None:
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError(f"unknown {name} keys: {sorted(unknown)}")


def _required_string(raw: Mapping[str, Any], name: str) -> str:
    value = raw.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _optional_string(raw: Mapping[str, Any], name: str) -> str | None:
    value = raw.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be null or a non-empty string")
    return value


def _optional_path(raw: Mapping[str, Any], name: str) -> Path | None:
    value = _optional_string(raw, name)
    return Path(value) if value is not None else None
