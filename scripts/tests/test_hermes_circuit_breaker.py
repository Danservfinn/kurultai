"""Tests for hermes_circuit_breaker.py

Covers:
  - Trip at 2 apply_failed in 30m
  - Trip at 3 rollbacks in 60m
  - Trip at 1 denylist_violation
  - Reset clears flag and state
  - Status reporting
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hermes_circuit_breaker as cb  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    """Redirect the breaker's state file + flag to per-test temp paths.

    Also stub notify_circuit_breaker_tripped so no real Signal queue
    enqueue happens during tests.
    """
    state = tmp_path / "cb_state.json"
    flag = tmp_path / "flags" / "hermes-autonomous-disabled.flag"
    monkeypatch.setattr(cb, "STATE_FILE", state)
    monkeypatch.setattr(cb, "DISABLE_FLAG", flag)

    # Stub out the notify import so no DM fires
    import sys as _sys
    from unittest.mock import MagicMock
    mock_notify = MagicMock()
    _sys.modules["hermes_notify"] = mock_notify
    yield state, flag
    del _sys.modules["hermes_notify"]


class TestTripThresholds:
    def test_single_apply_failed_does_not_trip(self, _isolate_state):
        _, flag = _isolate_state
        cb.record_event("apply_failed", "test")
        assert cb.is_tripped() is False
        assert not flag.exists()

    def test_two_apply_failed_trips(self, _isolate_state):
        _, flag = _isolate_state
        cb.record_event("apply_failed", "first")
        cb.record_event("apply_failed", "second")
        assert cb.is_tripped() is True
        assert flag.exists()

    def test_two_rollbacks_does_not_trip(self, _isolate_state):
        # Rollback threshold is 3, not 2
        cb.record_event("rollback", "r1")
        cb.record_event("rollback", "r2")
        assert cb.is_tripped() is False

    def test_three_rollbacks_trips(self, _isolate_state):
        _, flag = _isolate_state
        for i in range(3):
            cb.record_event("rollback", f"r{i}")
        assert cb.is_tripped() is True

    def test_denylist_violation_trips_immediately(self, _isolate_state):
        _, flag = _isolate_state
        cb.record_event("denylist_violation", "test")
        assert cb.is_tripped() is True
        assert flag.exists()


class TestReset:
    def test_reset_clears_flag(self, _isolate_state):
        _, flag = _isolate_state
        cb.record_event("denylist_violation", "to-be-reset")
        assert flag.exists()
        cb.reset("manual test")
        assert not flag.exists()

    def test_reset_clears_events(self, _isolate_state):
        cb.record_event("apply_failed", "e1")
        cb.reset("manual test")
        st = cb.status()
        assert st["event_count"] == 0


class TestStatus:
    def test_status_reflects_trip(self, _isolate_state):
        cb.record_event("denylist_violation", "test")
        st = cb.status()
        assert st["tripped"] is True
        assert st["tripped_at"] is not None
        assert "denylist" in st["trip_reason"]
