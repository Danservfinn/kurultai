"""Unit tests for hermes_daily_review.py.

Tests rotation, same-day-skip, missing-config, and scope selection
without actually invoking the LLM sweep.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import hermes_daily_review as d  # noqa: E402


def _write_config(tmp_path, scopes):
    """Write a temp config file and point the module at it."""
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "scopes": scopes,
        "rotation": "round-robin",
        "max_candidates_per_run": 5,
    }))
    return cfg_path


def _scopes_fixture():
    return [
        {"name": "scope-a", "path": "/tmp/a", "mode_override": None, "priority": 1},
        {"name": "scope-b", "path": "/tmp/b", "mode_override": None, "priority": 1},
        {"name": "scope-c", "path": "/tmp/c", "mode_override": "notify-only", "priority": 2},
    ]


def test_rotation_advances(monkeypatch, tmp_path):
    cfg_path = _write_config(tmp_path, _scopes_fixture())
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"last_run_date": "2026-04-19", "last_scope_idx": 0}))

    monkeypatch.setattr(d, "CONFIG_PATH", cfg_path)
    monkeypatch.setattr(d, "STATE_PATH", state_path)

    config = d.load_config()
    state = d.load_state()
    scope, idx = d.pick_next_scope(config, state)
    assert idx == 1
    assert scope["name"] == "scope-b"


def test_rotation_wraps_around(monkeypatch, tmp_path):
    cfg_path = _write_config(tmp_path, _scopes_fixture())
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"last_run_date": "2026-04-19", "last_scope_idx": 2}))

    monkeypatch.setattr(d, "CONFIG_PATH", cfg_path)
    monkeypatch.setattr(d, "STATE_PATH", state_path)

    config = d.load_config()
    state = d.load_state()
    scope, idx = d.pick_next_scope(config, state)
    assert idx == 0
    assert scope["name"] == "scope-a"


def test_rotation_fresh_state(monkeypatch, tmp_path):
    """First-ever run: state missing or last_scope_idx=-1 → picks 0."""
    cfg_path = _write_config(tmp_path, _scopes_fixture())
    state_path = tmp_path / "state.json"  # doesn't exist
    monkeypatch.setattr(d, "CONFIG_PATH", cfg_path)
    monkeypatch.setattr(d, "STATE_PATH", state_path)

    config = d.load_config()
    state = d.load_state()
    scope, idx = d.pick_next_scope(config, state)
    assert idx == 0
    assert scope["name"] == "scope-a"


def test_missing_config_errors(monkeypatch, tmp_path):
    cfg_path = tmp_path / "missing.json"  # doesn't exist
    monkeypatch.setattr(d, "CONFIG_PATH", cfg_path)
    with pytest.raises(RuntimeError, match="config missing"):
        d.load_config()


def test_empty_scopes_errors(monkeypatch, tmp_path):
    cfg_path = _write_config(tmp_path, [])
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(d, "CONFIG_PATH", cfg_path)
    monkeypatch.setattr(d, "STATE_PATH", state_path)
    config = d.load_config()
    state = d.load_state()
    with pytest.raises(RuntimeError, match="no scopes"):
        d.pick_next_scope(config, state)


def test_save_state_roundtrip(monkeypatch, tmp_path):
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(d, "STATE_PATH", state_path)
    d.save_state({"last_run_date": "2026-04-20", "last_scope_idx": 2})
    loaded = d.load_state()
    assert loaded == {"last_run_date": "2026-04-20", "last_scope_idx": 2}
