from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).parents[2] / "deploy" / "scripts" / "doctor.py"


def load_doctor() -> ModuleType:
    spec = importlib.util.spec_from_file_location("hulagu_doctor_atomic", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "changes",
    [
        {"source_device": 10, "destination_device": 11},
        {"replace_succeeded": False},
        {"file_fsynced": False},
        {"parent_fsynced": False},
    ],
)
def test_same_volume_atomic_rename_probe_fails_closed(changes: dict[str, object]) -> None:
    module = load_doctor()
    probe = module.AtomicRenameObservation(
        source_device=10,
        destination_device=10,
        replace_succeeded=True,
        file_fsynced=True,
        parent_fsynced=True,
    )
    for field, value in changes.items():
        setattr(probe, field, value)
    assert module.evaluate_atomic_rename(probe)["status"] == "fail"


def test_complete_same_volume_atomic_rename_probe_passes() -> None:
    module = load_doctor()
    probe = module.AtomicRenameObservation(
        source_device=10,
        destination_device=10,
        replace_succeeded=True,
        file_fsynced=True,
        parent_fsynced=True,
    )
    assert module.evaluate_atomic_rename(probe) == {"status": "pass", "reasons": []}
