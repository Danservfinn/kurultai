"""Tests for hermes_revert_handler.py (Phase 7).

Covers:
  - Non-existent SHA -> NOT_FOUND
  - Non-Hermes commit -> NOT_HERMES_COMMIT (defense in depth)
  - Empty 24h window -> outcome='empty'
  - Revert-all-today stops on first conflict
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

import hermes_revert_handler as rh  # noqa: E402


@pytest.fixture(autouse=True)
def _stub_notify(monkeypatch):
    """Prevent any real DMs."""
    fake = MagicMock()
    fake.notify_revert_confirmed = lambda *a, **kw: None
    fake._enqueue = lambda *a, **kw: None
    monkeypatch.setitem(sys.modules, "hermes_notify", fake)


class TestHandleRevert:
    def test_bogus_sha(self, monkeypatch):
        fake = MagicMock()
        fake.find_commit = lambda sha: None
        fake.recent_commits = lambda n=1: []
        fake.mark_reverted = lambda *a, **kw: True
        monkeypatch.setitem(sys.modules, "hermes_commit", fake)
        result = rh.handle_revert("abc1234")
        assert result["outcome"] == "NOT_FOUND"

    def test_empty_recent_when_no_arg(self, monkeypatch):
        fake = MagicMock()
        fake.recent_commits = lambda n=1: []
        fake.find_commit = lambda sha: None
        fake.mark_reverted = lambda *a, **kw: True
        monkeypatch.setitem(sys.modules, "hermes_commit", fake)
        result = rh.handle_revert(None)
        assert result["outcome"] == "NO_RECENT_HERMES_COMMIT"

    def test_not_hermes_commit_rejected(self, monkeypatch):
        # find_commit returns a match but git log says the author isn't Hermes
        fake = MagicMock()
        fake.find_commit = lambda sha: {
            "sha": "cafef00d" * 5, "subject": "evil",
            "repo": "openclaw-scripts", "target_paths": [],
        }
        fake.mark_reverted = lambda *a, **kw: True
        monkeypatch.setitem(sys.modules, "hermes_commit", fake)
        # Stub the git-log check to return a human author
        monkeypatch.setattr(
            rh, "_git_show_author_email",
            lambda repo, sha: "attacker@example.com",
        )
        result = rh.handle_revert("cafef00d")
        assert result["outcome"] == "NOT_HERMES_COMMIT"
        assert result["actual_author"] == "attacker@example.com"

    def test_revert_failure_captured(self, monkeypatch):
        fake = MagicMock()
        fake.find_commit = lambda sha: {
            "sha": "feedface" * 5, "subject": "x",
            "repo": "brain", "target_paths": [],
        }
        fake.mark_reverted = lambda *a, **kw: True
        monkeypatch.setitem(sys.modules, "hermes_commit", fake)
        monkeypatch.setattr(
            rh, "_git_show_author_email",
            lambda repo, sha: rh.HERMES_EMAIL,
        )
        monkeypatch.setattr(
            rh, "_git_revert",
            lambda repo, sha: (False, "", "merge conflict"),
        )
        result = rh.handle_revert("feedface")
        assert result["outcome"] == "REVERT_FAILED"
        assert "conflict" in result["reason"]


class TestRevertAllToday:
    def test_empty_window(self, monkeypatch):
        fake = MagicMock()
        fake.commits_in_last_hours = lambda h: []
        monkeypatch.setitem(sys.modules, "hermes_commit", fake)
        result = rh.handle_revert_all_today()
        assert result["outcome"] == "empty"
        assert result["found"] == 0

    def test_stops_on_first_conflict(self, monkeypatch):
        commits = [
            {"sha": "a" * 40, "subject": "A", "repo": "brain", "target_paths": []},
            {"sha": "b" * 40, "subject": "B", "repo": "brain", "target_paths": []},
            {"sha": "c" * 40, "subject": "C", "repo": "brain", "target_paths": []},
        ]
        fake = MagicMock()
        fake.commits_in_last_hours = lambda h: commits
        fake.find_commit = lambda sha: next(
            (c for c in commits if c["sha"].startswith(sha[:8])), None)
        fake.mark_reverted = lambda *a, **kw: True
        monkeypatch.setitem(sys.modules, "hermes_commit", fake)
        monkeypatch.setattr(
            rh, "_git_show_author_email",
            lambda repo, sha: rh.HERMES_EMAIL,
        )
        # First revert succeeds, second fails (conflict), third never attempted
        calls = []
        def fake_revert(repo, sha):
            calls.append(sha)
            if sha.startswith("a"):
                return True, "revert-of-a", "ok"
            return False, "", "merge conflict"
        monkeypatch.setattr(rh, "_git_revert", fake_revert)
        monkeypatch.setattr(rh, "_git_push", lambda r: (True, ""))

        result = rh.handle_revert_all_today()
        assert result["outcome"] == "partial_conflict"
        assert len(result["reverted"]) == 1
        assert result["conflict"]["sha"].startswith("b")
        # Third commit was never attempted (loop stopped)
        assert len(calls) == 2
