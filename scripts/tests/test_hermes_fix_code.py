"""Tests for hermes-fix-code.py (Phase 4).

Covers gates unique to code fixing:
  - Denylist + flags (shared with content)
  - Diff-size cap -> DIFF_TOO_BIG + notify (no commit)
  - AST syntax check -> VALIDATION_FAILED
  - Baseline test must pass first -> BASELINE_BROKEN
  - Dry-run produces validated diff without committing
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hfcode = _load_module("hermes_fix_code", SCRIPTS_DIR / "hermes-fix-code.py")


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.setitem(sys.modules, "neo4j_v2_core", MagicMock())
    monkeypatch.setitem(sys.modules, "notification_queue", MagicMock())


@pytest.fixture
def flags_off(monkeypatch):
    import hermes_auto_fix as haf
    monkeypatch.setattr(haf, "_check_kill_switch", lambda: False)
    monkeypatch.setattr(haf, "_check_autonomous_disabled", lambda: False)
    monkeypatch.setattr(haf, "_check_autonomous_fix_code_disabled", lambda: False)


@pytest.fixture
def scratch_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)
    target = repo / "mod.py"
    target.write_text("def add(a, b):\n    return a + b\n")
    subprocess.run(["git", "add", "mod.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=repo, check=True)
    return repo, target


class TestGates:
    def test_denylist_reject(self, monkeypatch, flags_off):
        monkeypatch.setattr(hfcode._hfc, "_invoke_llm",
                            lambda p: (0, "should not be called", ""))
        result = hfcode.author_code_fix(
            "~/.openclaw/agents/main/scripts/hermes-watchdog.py",
            "try to fix",
        )
        assert result["outcome"] == "DENYLIST_VIOLATION"

    def test_code_flag_blocks(self, monkeypatch):
        import hermes_auto_fix as haf
        monkeypatch.setattr(haf, "_check_kill_switch", lambda: False)
        monkeypatch.setattr(haf, "_check_autonomous_disabled", lambda: False)
        monkeypatch.setattr(haf, "_check_autonomous_fix_code_disabled", lambda: True)
        result = hfcode.author_code_fix("/tmp/ok.py", "test")
        assert result["outcome"] == "DISABLED_BY_CODE_FLAG"


def _make_git_diff(repo: Path, relpath: str, new_content: str) -> str:
    """Generate a canonical git-diff by temporarily writing new_content
    and running `git diff`. Restores the original after."""
    target = repo / relpath
    original = target.read_text(encoding="utf-8")
    try:
        target.write_text(new_content)
        result = subprocess.run(
            ["git", "diff", "--", relpath],
            cwd=repo, capture_output=True, text=True, check=True,
        )
        return result.stdout
    finally:
        target.write_text(original)


class TestDiffGates:
    def test_dry_run_valid_diff(self, monkeypatch, flags_off, scratch_repo):
        repo, target = scratch_repo
        diff = _make_git_diff(
            repo, "mod.py",
            "def add(a, b):\n    return a + b\n# added comment\n",
        )
        monkeypatch.setattr(hfcode._hfc, "_invoke_llm", lambda p: (0, diff, ""))
        result = hfcode.author_code_fix(str(target), "add comment", dry_run=True)
        assert result["outcome"] == "dry_run_ok", result
        assert result["validation"] == "ast ok"

    def test_diff_too_big_skipped(self, monkeypatch, flags_off, scratch_repo):
        repo, target = scratch_repo
        # Add 10 lines — well over the 3-line cap for this test
        added = "\n".join(f"# line{i}" for i in range(10))
        new = f"def add(a, b):\n    return a + b\n{added}\n"
        diff = _make_git_diff(repo, "mod.py", new)
        monkeypatch.setattr(hfcode._hfc, "_invoke_llm", lambda p: (0, diff, ""))
        # Stub the notification so no DM queued
        fake_notify = MagicMock()
        fake_notify.notify_fix_skipped_too_big = lambda **kw: None
        monkeypatch.setitem(sys.modules, "hermes_notify", fake_notify)
        result = hfcode.author_code_fix(
            str(target), "add lots", dry_run=True, max_diff_lines=3,
        )
        assert result["outcome"] == "DIFF_TOO_BIG"
        assert result["diff_lines"] > 3

    def test_syntax_error_rejected(self, monkeypatch, flags_off, scratch_repo):
        repo, target = scratch_repo
        # Add a syntactically-broken line
        broken = "def add(a, b):\n    return a + b\ndef broken(  # unclosed\n"
        diff = _make_git_diff(repo, "mod.py", broken)
        monkeypatch.setattr(hfcode._hfc, "_invoke_llm", lambda p: (0, diff, ""))
        result = hfcode.author_code_fix(str(target), "break it", dry_run=True)
        assert result["outcome"] == "VALIDATION_FAILED"
        assert "SyntaxError" in result["reason"]


class TestBaselineGate:
    def test_baseline_broken_aborts(self, monkeypatch, flags_off, scratch_repo):
        repo, target = scratch_repo
        # Create a failing test for this module
        tests_dir = repo / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_mod.py").write_text(
            "def test_broken():\n    assert False\n"
        )
        # LLM should never be called
        llm_called = []
        monkeypatch.setattr(
            hfcode._hfc, "_invoke_llm",
            lambda p: llm_called.append(1) or (0, "", ""),
        )
        result = hfcode.author_code_fix(str(target), "anything")
        assert result["outcome"] == "BASELINE_BROKEN"
        assert not llm_called, "LLM must not be called when baseline is broken"
