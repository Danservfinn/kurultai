"""Unit tests for hermes_sweep_horde_review plugin.

Mocks the LLM invocation (so tests don't actually spawn claude or
spend tokens) and verifies the filtering/cap behaviour around denylist
and severity.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import hermes_sweep_horde_review as plugin  # noqa: E402


def _mock_run_review(findings):
    """Return a callable that replaces _run_review with a canned list."""
    def fn(scope):
        return findings
    return fn


def test_audit_requires_scope(monkeypatch):
    monkeypatch.delenv("HERMES_SWEEP_SCOPE", raising=False)
    with pytest.raises(RuntimeError, match="SCOPE"):
        plugin.audit()


def test_audit_returns_empty_on_no_findings(monkeypatch):
    monkeypatch.setenv("HERMES_SWEEP_SCOPE", "/tmp/dummy")
    monkeypatch.setattr(plugin, "_run_review", _mock_run_review([]))
    assert plugin.audit() == []


def test_audit_drops_low_severity(monkeypatch):
    monkeypatch.setenv("HERMES_SWEEP_SCOPE", "/tmp/dummy")
    findings = [
        {
            "severity": "critical",
            "title": "crit issue",
            "target": "/Users/kublai/brain/raw/file1.md",
            "autonomy_level": "content",
            "fix_description": "fix it",
        },
        {
            "severity": "high",
            "title": "high issue",
            "target": "/Users/kublai/brain/raw/file2.md",
            "autonomy_level": "content",
            "fix_description": "fix it",
        },
        {
            "severity": "low",  # should be dropped
            "title": "low issue",
            "target": "/Users/kublai/brain/raw/file3.md",
            "autonomy_level": "content",
            "fix_description": "ignore",
        },
    ]
    monkeypatch.setattr(plugin, "_run_review", _mock_run_review(findings))
    # Monkeypatch is_denied to always allow (avoid hitting the real denylist)
    import hermes_denylist
    monkeypatch.setattr(hermes_denylist, "is_denied", lambda p: (False, ""))
    cands = plugin.audit()
    assert len(cands) == 2
    assert all("low" not in c["reason"] for c in cands)


def test_audit_drops_denylisted(monkeypatch):
    monkeypatch.setenv("HERMES_SWEEP_SCOPE", "/tmp/dummy")
    findings = [
        {
            "severity": "high",
            "title": "denylisted target",
            "target": "/Users/kublai/.openclaw/agents/main/scripts/hermes_chat.py",
            "autonomy_level": "code",
            "fix_description": "would be rejected at apply anyway",
        },
        {
            "severity": "high",
            "title": "allowed target",
            "target": "/Users/kublai/brain/raw/ok.md",
            "autonomy_level": "content",
            "fix_description": "fine to fix",
        },
    ]
    monkeypatch.setattr(plugin, "_run_review", _mock_run_review(findings))
    # Mock is_denied to reject anything under agents/main/scripts/hermes_*
    import hermes_denylist
    def fake_deny(p):
        if "hermes_chat.py" in p or "/agents/main/scripts/hermes" in p:
            return (True, "protected")
        return (False, "")
    monkeypatch.setattr(hermes_denylist, "is_denied", fake_deny)
    cands = plugin.audit()
    assert len(cands) == 1
    assert cands[0]["target"] == "/Users/kublai/brain/raw/ok.md"


def test_audit_caps_at_max(monkeypatch):
    monkeypatch.setenv("HERMES_SWEEP_SCOPE", "/tmp/dummy")
    # 10 high-severity findings; should cap at MAX_CANDIDATES=5
    findings = [
        {
            "severity": "high",
            "title": f"issue {i}",
            "target": f"/Users/kublai/brain/raw/file{i}.md",
            "autonomy_level": "content",
            "fix_description": "fix",
        }
        for i in range(10)
    ]
    monkeypatch.setattr(plugin, "_run_review", _mock_run_review(findings))
    import hermes_denylist
    monkeypatch.setattr(hermes_denylist, "is_denied", lambda p: (False, ""))
    cands = plugin.audit()
    assert len(cands) == plugin.MAX_CANDIDATES
    assert plugin.MAX_CANDIDATES == 5


def test_audit_rejects_relative_target(monkeypatch):
    monkeypatch.setenv("HERMES_SWEEP_SCOPE", "/tmp/dummy")
    findings = [
        {
            "severity": "high",
            "title": "relative path",
            "target": "relative/path.md",  # not absolute — should drop
            "autonomy_level": "content",
            "fix_description": "ignore",
        },
        {
            "severity": "high",
            "title": "absolute ok",
            "target": "/Users/kublai/brain/raw/x.md",
            "autonomy_level": "content",
            "fix_description": "keep",
        },
    ]
    monkeypatch.setattr(plugin, "_run_review", _mock_run_review(findings))
    import hermes_denylist
    monkeypatch.setattr(hermes_denylist, "is_denied", lambda p: (False, ""))
    cands = plugin.audit()
    assert len(cands) == 1
    assert cands[0]["target"] == "/Users/kublai/brain/raw/x.md"


def test_extract_findings_parses_correctly():
    stream = (
        "some prose here\n"
        "more prose\n"
        'HERMES_FINDINGS=[{"severity":"high","title":"t","target":"/x","autonomy_level":"content","fix_description":"d"}]\n'
        "trailing text\n"
    )
    out = plugin._extract_findings(stream)
    assert len(out) == 1
    assert out[0]["severity"] == "high"


def test_extract_findings_returns_empty_on_missing_marker():
    assert plugin._extract_findings("no marker here at all") == []


def test_extract_findings_handles_malformed_json():
    stream = "HERMES_FINDINGS=not valid json{"
    assert plugin._extract_findings(stream) == []


def test_extract_findings_picks_last_line():
    # If the agent emits multiple marker lines, last wins
    stream = (
        'HERMES_FINDINGS=[{"severity":"low","title":"first","target":"/x","autonomy_level":"content","fix_description":"d"}]\n'
        "reasoning...\n"
        'HERMES_FINDINGS=[{"severity":"high","title":"second","target":"/y","autonomy_level":"content","fix_description":"d"}]\n'
    )
    out = plugin._extract_findings(stream)
    assert len(out) == 1
    assert out[0]["title"] == "second"
