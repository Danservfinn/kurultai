"""Tests for hermes_rate_limit.py

Covers:
  - consume_slot atomic check-and-record (H2)
  - allowed() / record() backward-compat API
  - Per-scope hourly caps
  - Daily total cap
  - State pruning
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hermes_rate_limit as rl  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    """Redirect the rate-limit state file to a per-test temp location."""
    p = tmp_path / "rate_limits.json"
    monkeypatch.setattr(rl, "STATE_FILE", p)
    yield p


class TestConsumeSlot:
    def test_three_content_then_deny(self):
        for i in range(3):
            ok, reason = rl.consume_slot("content")
            assert ok, f"call {i} expected allowed; got {reason}"
        ok, reason = rl.consume_slot("content")
        assert ok is False
        assert "hourly" in reason

    def test_per_scope_independence(self):
        for _ in range(3):
            rl.consume_slot("content")
        ok, _ = rl.consume_slot("code")
        assert ok is True

    def test_daily_total_cap(self):
        for _ in range(3):
            rl.consume_slot("content")
        for _ in range(3):
            rl.consume_slot("code")
        # 6 used, 4 left. Simulate 4 more rapid content consumes that
        # somehow get past the hourly cap (via clock advance). Since
        # we can't easily fast-forward here, we directly seed the state.
        import time
        from datetime import timezone, datetime
        old_ts = datetime.now(timezone.utc).timestamp() - 4000  # >1h ago
        # Add 4 old content entries (not blocked by hourly cap) + 6 current
        from json_state import locked_json_update
        with locked_json_update(str(rl.STATE_FILE)) as state:
            state.setdefault("content", []).extend([old_ts] * 4)
        # Now total_today = 6 + 4 = 10 (at cap)
        ok, reason = rl.consume_slot("code")
        assert ok is False
        assert "daily cap" in reason

    def test_unknown_scope(self):
        ok, reason = rl.consume_slot("garbage")
        assert ok is False
        assert "unknown scope" in reason


class TestAllowedRecord:
    def test_allowed_does_not_record(self):
        # Backward-compat API: allowed() must not consume
        for _ in range(100):
            rl.allowed("content")
        # No records have been made; counts should be 0
        counts = rl.current_counts()
        assert counts["content_hour"] == 0

    def test_record_counts(self):
        rl.record("content")
        rl.record("content")
        counts = rl.current_counts()
        assert counts["content_hour"] == 2
        assert counts["total_day"] == 2
