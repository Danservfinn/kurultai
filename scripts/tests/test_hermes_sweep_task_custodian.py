"""Unit tests for hermes_sweep_task_custodian.

Uses a mocked Neo4j session + driver so the tests can run without a
live Neo4j. The plugin's audit() dispatches into three helpers in
hermes_task_queries — we monkeypatch those directly to return fixtures.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import hermes_sweep_task_custodian as plugin  # noqa: E402
from hermes_sweep_task_custodian import _classify_failure  # noqa: E402


@pytest.fixture
def mock_task_store(monkeypatch):
    """Replace TaskStore with a mock that yields a mock session."""
    session_cm = MagicMock()
    session_cm.__enter__ = MagicMock(return_value=MagicMock())
    session_cm.__exit__ = MagicMock(return_value=None)

    driver = MagicMock()
    driver.session = MagicMock(return_value=session_cm)

    store = MagicMock()
    store.driver = driver
    store.close = MagicMock()

    class _FakeTaskStore:
        def __init__(self, *a, **kw):
            self.driver = driver
        def close(self):
            store.close()

    import neo4j_v2_core
    monkeypatch.setattr(neo4j_v2_core, "TaskStore", _FakeTaskStore)
    return store


def _patch_queries(monkeypatch, *, repeat_failures=None, duplicates=None,
                   chronic_orphans=None):
    """Monkey-patch the three query helpers to return fixtures."""
    import hermes_task_queries as q

    def _rf(session, threshold=3, window_hours=24):
        return repeat_failures or []

    def _dp(session, prompt_prefix_chars=200, max_groups=20):
        return duplicates or []

    def _co(session, min_bounces=2, window_days=7):
        return chronic_orphans or []

    monkeypatch.setattr(q, "find_repeat_failures", _rf)
    monkeypatch.setattr(q, "find_duplicate_pending", _dp)
    monkeypatch.setattr(q, "find_chronic_orphans", _co)


def test_classify_transient_failure_to_retry():
    rec = {"last_error_category": "timeout"}
    assert _classify_failure(rec) == "retry"


def test_classify_prompt_error_to_rewrite():
    rec = {"last_error_category": "prompt_error"}
    assert _classify_failure(rec) == "rewrite_prompt"


def test_classify_unknown_failure_falls_back_to_reassign():
    rec = {"last_error_category": "mystery_glitch"}
    assert _classify_failure(rec) == "reassign"


def test_audit_caps_at_max_candidates(mock_task_store, monkeypatch):
    # Produce 12 repeat failures — audit should cap at 5
    many = [
        {"task_id": f"t-{i}", "agent": "kublai", "source": "kanban-ui",
         "status": "FAILED", "fail_count": 5, "last_error_category": "timeout",
         "last_error_msg": "x"}
        for i in range(12)
    ]
    _patch_queries(monkeypatch, repeat_failures=many)
    candidates = plugin.audit()
    assert len(candidates) == plugin.MAX_CANDIDATES


def test_audit_filters_denylisted_sources(mock_task_store, monkeypatch):
    fails = [
        {"task_id": "t-hermes", "agent": "hermes", "source": "hermes_sweep",
         "status": "FAILED", "fail_count": 3, "last_error_category": "timeout",
         "last_error_msg": "self-targeting"},
        {"task_id": "t-user", "agent": "kublai", "source": "kanban-ui",
         "status": "FAILED", "fail_count": 3, "last_error_category": "timeout",
         "last_error_msg": "ok to act"},
    ]
    _patch_queries(monkeypatch, repeat_failures=fails)
    candidates = plugin.audit()
    assert len(candidates) == 1
    assert candidates[0]["evidence"]["task_id"] == "t-user"


def test_audit_filters_hermes_assigned_tasks(mock_task_store, monkeypatch):
    # Even if the source isn't denylisted, assigned_to=hermes blocks it
    fails = [
        {"task_id": "t-1", "agent": "hermes", "source": "pipeline",
         "status": "FAILED", "fail_count": 3, "last_error_category": "timeout",
         "last_error_msg": "x"},
        {"task_id": "t-2", "agent": "kublai", "source": "pipeline",
         "status": "FAILED", "fail_count": 3, "last_error_category": "timeout",
         "last_error_msg": "x"},
    ]
    _patch_queries(monkeypatch, repeat_failures=fails)
    candidates = plugin.audit()
    assert len(candidates) == 1
    assert candidates[0]["evidence"]["agent"] == "kublai"


def test_audit_emits_task_action_autonomy_and_action_kind(
    mock_task_store, monkeypatch
):
    _patch_queries(monkeypatch, repeat_failures=[{
        "task_id": "t-1", "agent": "kublai", "source": "kanban-ui",
        "status": "FAILED", "fail_count": 4,
        "last_error_category": "rate_limit",
        "last_error_msg": "too many requests",
    }])
    candidates = plugin.audit()
    assert len(candidates) == 1
    c = candidates[0]
    assert c["autonomy_level"] == "task_action"
    assert c["evidence"]["action_kind"] == "retry"
    assert c["target"] == "task:t-1"
    assert "failed 4x/24h" in c["reason"]


def test_audit_duplicates_produce_delete_per_extra(
    mock_task_store, monkeypatch
):
    keeper = {"task_id": "keep-1", "agent": "kublai", "source": "kanban-ui",
              "status": "PENDING"}
    dup_a = {"task_id": "dup-a", "agent": "kublai", "source": "kanban-ui",
             "status": "PENDING"}
    dup_b = {"task_id": "dup-b", "agent": "kublai", "source": "kanban-ui",
             "status": "PENDING"}
    _patch_queries(monkeypatch, duplicates=[[keeper, dup_a, dup_b]])
    candidates = plugin.audit()
    assert len(candidates) == 2
    assert all(c["evidence"]["action_kind"] == "delete" for c in candidates)
    ids = {c["evidence"]["task_id"] for c in candidates}
    assert ids == {"dup-a", "dup-b"}
    assert "keep-1" not in ids
