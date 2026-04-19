"""Tests for hermes_denylist.py

Covers:
  - Case-insensitivity bypass fix (C1)
  - Variant-filename matching (M2)
  - Override flag semantics
  - Symlink canonicalization
  - Unresolvable-path fail-closed
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hermes_denylist as dl  # noqa: E402


class TestIsDenied:
    def test_hermes_watchdog_denied_exact(self):
        d, r = dl.is_denied(
            "~/.openclaw/agents/main/scripts/hermes-watchdog.py"
        )
        assert d is True
        assert "self-denylisted" in r

    @pytest.mark.skipif(
        not dl._CASE_INSENSITIVE_FS,
        reason="case-insensitive FS required for this bypass",
    )
    def test_hermes_watchdog_denied_uppercase(self):
        # C1 regression: on macOS APFS (default), the bypass must NOT work
        d, r = dl.is_denied(
            "~/.openclaw/agents/main/scripts/HERMES-WATCHDOG.py"
        )
        assert d is True, f"case-insensitive FS must deny case variant; got {d, r}"

    @pytest.mark.skipif(
        not dl._CASE_INSENSITIVE_FS,
        reason="case-insensitive FS required for this bypass",
    )
    def test_hermes_auto_fix_denied_mixed_case(self):
        d, r = dl.is_denied(
            "~/.openclaw/agents/main/scripts/Hermes_Auto_Fix.py"
        )
        assert d is True

    def test_variant_denied(self):
        # M2 regression: sibling variants of denylisted files
        d, r = dl.is_denied(
            "~/.openclaw/agents/main/scripts/hermes-watchdog.py.new"
        )
        assert d is True
        assert "variant" in r

    def test_variant_of_auto_fix_denied(self):
        d, r = dl.is_denied(
            "~/.openclaw/agents/main/scripts/hermes_auto_fix.py.bak"
        )
        assert d is True

    def test_knowledge_doc_allowed(self):
        d, r = dl.is_denied(
            "~/.openclaw/agents/main/knowledge/agent-roster.md"
        )
        assert d is False
        assert r == ""

    def test_flags_dir_all_denied(self):
        for name in ["hermes-disabled.flag", "something-else.flag", ""]:
            d, _ = dl.is_denied(f"~/.openclaw/flags/{name}")
            # Empty filename resolves to flags dir itself, still denied
            assert d is True

    def test_credentials_denied(self):
        assert dl.is_denied("~/.claude/credentials.json")[0] is True

    def test_scratch_allowed(self):
        assert dl.is_denied("/tmp/hermes-scratch.md") == (False, "")

    def test_symlink_canonicalized(self, tmp_path):
        # A symlink pointing at a denylisted target must be denied even
        # when addressed by the link name.
        real_target = tmp_path / "real.md"
        real_target.write_text("target")
        denylisted = Path.home() / ".openclaw" / "flags" / "hermes-disabled.flag"
        link = tmp_path / "innocent-looking.md"
        try:
            link.symlink_to(denylisted)
        except OSError:
            pytest.skip("cannot create symlink in this environment")
        d, r = dl.is_denied(str(link))
        assert d is True
        assert "prefix" in r

    def test_unresolvable_path_denied(self):
        # Path with null byte is unresolvable on POSIX
        d, r = dl.is_denied("/tmp/\x00bad")
        assert d is True
        assert "unresolvable" in r

    def test_override_allows_hermes_watchdog(self, monkeypatch):
        monkeypatch.setattr(dl, "_override_active", lambda: True)
        d, r = dl.is_denied(
            "~/.openclaw/agents/main/scripts/hermes-watchdog.py"
        )
        assert d is False
        assert "override active" in r

    def test_override_inactive_fallback(self, monkeypatch):
        # When override flag is absent, denylist stands
        monkeypatch.setattr(dl, "_override_active", lambda: False)
        d, _ = dl.is_denied(
            "~/.openclaw/agents/main/scripts/hermes-watchdog.py"
        )
        assert d is True


class TestNormalize:
    def test_norm_lowercases_on_case_insensitive_fs(self):
        if dl._CASE_INSENSITIVE_FS:
            assert dl._norm("/Foo/BAR.PY") == "/foo/bar.py"
        else:
            assert dl._norm("/Foo/BAR.PY") == "/Foo/BAR.PY"
