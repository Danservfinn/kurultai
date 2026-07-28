"""Typed configuration entrypoints for the source-only Task 0 tools.

This module deliberately does not inspect arbitrary environment variables or search
PATH. Installation values must be passed explicitly by an approved caller.
"""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import NamedTuple


class VaultConfig(NamedTuple):
    path: Path
    enrolled_volume_uuid: str | None


class ContainerInstallConfig(NamedTuple):
    cli_path: Path
    socket_path: Path


class HulaguConfig(NamedTuple):
    vault: VaultConfig
    container: ContainerInstallConfig


def doctor_main() -> None:
    script = Path(__file__).parents[2] / "deploy" / "scripts" / "doctor.py"
    runpy.run_path(str(script), run_name="__main__")


def verify_plan_gate_main() -> None:
    script = Path(__file__).parents[2] / "deploy" / "scripts" / "verify_plan_gate.py"
    runpy.run_path(str(script), run_name="__main__")
