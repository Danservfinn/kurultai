"""
test_hermes_auto_fix.py -- Unit tests for hermes_auto_fix.py

Covers kill-switch gating, dry-run semantics, live operations (mocked),
error handling, and the CLI entry point for all public T0 auto-fix functions.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import the module under test.  hermes_auto_fix appends its own directory
# to sys.path, so we import normally.
# ---------------------------------------------------------------------------
import hermes_auto_fix as haf


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture(autouse=True)
def _isolate_logs(tmp_path, monkeypatch):
    """Redirect LOGS_DIR to a temp directory so no real logs are written."""
    monkeypatch.setattr(haf, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(haf, "HERMES_ACTIONS_LOG", tmp_path / "hermes-actions.jsonl")


@pytest.fixture(autouse=True)
def _isolate_neo4j(monkeypatch):
    """Stub neo4j_v2_core so tests never write HermesAction nodes to prod Neo4j."""
    mock_module = MagicMock()
    monkeypatch.setitem(sys.modules, "neo4j_v2_core", mock_module)


@pytest.fixture(autouse=True)
def _isolate_flag_paths(tmp_path, monkeypatch):
    """Redirect kill-switch flag paths to per-test tmp dirs so tests are
    hermetic regardless of production flag state. Tests that want either
    flag ON must explicitly request kill_switch_on / risky_flag_on."""
    flag_dir = tmp_path / "_auto_flags"
    flag_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(haf, "KILL_SWITCH_PATH", flag_dir / "hermes-disabled.flag")
    monkeypatch.setattr(haf, "RISKY_KILL_SWITCH_PATH", flag_dir / "hermes-risky-disabled.flag")


@pytest.fixture
def kill_switch_off(tmp_path, monkeypatch):
    """Ensure the kill-switch flag file does NOT exist."""
    flag_dir = tmp_path / "flags"
    flag_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(haf, "KILL_SWITCH_PATH", flag_dir / "hermes-disabled.flag")
    return flag_dir


@pytest.fixture
def kill_switch_on(kill_switch_off):
    """Create the kill-switch flag so all actions are disabled."""
    haf.KILL_SWITCH_PATH.touch()
    return haf.KILL_SWITCH_PATH


@pytest.fixture
def risky_flag_off(tmp_path, monkeypatch):
    """Ensure the risky-action flag file does NOT exist."""
    flag_dir = tmp_path / "flags"
    flag_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(haf, "RISKY_KILL_SWITCH_PATH", flag_dir / "hermes-risky-disabled.flag")
    return flag_dir


@pytest.fixture
def risky_flag_on(risky_flag_off):
    """Create the risky-action flag so risky T0s are disabled."""
    haf.RISKY_KILL_SWITCH_PATH.touch()
    return haf.RISKY_KILL_SWITCH_PATH


@pytest.fixture
def fake_agents_dir(tmp_path):
    """Provide a temporary AGENTS_DIR with a minimal agent layout."""
    agents = tmp_path / "agents"
    agents.mkdir()
    return agents


@pytest.fixture
def fake_scripts_dir(tmp_path):
    """Provide a temporary SCRIPTS_DIR."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    return scripts


# ===================================================================
# 1. Kill switch
# ===================================================================

class TestCheckKillSwitch:
    """Tests for _check_kill_switch()."""

    def test_returns_false_when_flag_absent(self, kill_switch_off):
        assert haf._check_kill_switch() is False

    def test_returns_true_when_flag_present(self, kill_switch_on):
        assert haf._check_kill_switch() is True

    def test_fail_closed_on_oserror(self, kill_switch_off, monkeypatch):
        """Transient FS errors (e.g., EACCES) are treated as 'flag present'
        so T0s stay disabled rather than firing under ambiguous state."""
        def raise_oserror(self_path):
            raise OSError("EACCES")
        monkeypatch.setattr(Path, "exists", raise_oserror)
        assert haf._check_kill_switch() is True


class TestCheckRiskyKillSwitch:
    """Tests for _check_risky_kill_switch() — second-layer gate for
    credential-affecting T0s (rotate_failing_provider,
    force_refresh_reflection_bridge)."""

    def test_returns_false_when_flag_absent(self, risky_flag_off):
        assert haf._check_risky_kill_switch() is False

    def test_returns_true_when_flag_present(self, risky_flag_on):
        assert haf._check_risky_kill_switch() is True

    def test_fail_closed_on_oserror(self, risky_flag_off, monkeypatch):
        def raise_oserror(self_path):
            raise OSError("EACCES")
        monkeypatch.setattr(Path, "exists", raise_oserror)
        assert haf._check_risky_kill_switch() is True


class TestRiskyGateEnforcement:
    """The risky gate must block credential-affecting T0s while allowing
    safe T0s, even when the global kill-switch is off."""

    def test_rotate_failing_provider_blocked_when_risky_flag_set(
        self, kill_switch_off, risky_flag_on
    ):
        result = haf.rotate_failing_provider("jochi", dry_run=True)
        assert result["outcome"] == "DISABLED_BY_RISKY_FLAG"

    def test_force_refresh_reflection_bridge_blocked_when_risky_flag_set(
        self, kill_switch_off, risky_flag_on
    ):
        result = haf.force_refresh_reflection_bridge(dry_run=True)
        assert result["outcome"] == "DISABLED_BY_RISKY_FLAG"

    def test_global_flag_takes_precedence_over_risky_flag(
        self, kill_switch_on, risky_flag_on
    ):
        """When both flags are set, the global DISABLED_BY_FLAG wins
        (global check runs first)."""
        result = haf.rotate_failing_provider("jochi", dry_run=True)
        assert result["outcome"] == "DISABLED_BY_FLAG"

    def test_safe_t0_not_blocked_by_risky_flag(
        self, kill_switch_off, risky_flag_on, tmp_path
    ):
        """clear_bloated_session is a safe T0 — risky flag must not block it."""
        # Point AGENTS_DIR at a fake layout so the function runs to completion
        agent_dir = tmp_path / "agents" / "jochi"
        agent_dir.mkdir(parents=True)
        (agent_dir / "sessions.json").write_text("{}")
        (agent_dir / "tasks").mkdir()
        monkeypatch_ok = getattr(
            pytest, "MonkeyPatch", None
        )  # py>=6 has this
        if monkeypatch_ok:
            mp = monkeypatch_ok()
            mp.setattr(haf, "AGENTS_DIR", tmp_path / "agents")
            try:
                result = haf.clear_bloated_session("jochi", dry_run=True)
            finally:
                mp.undo()
        else:
            result = haf.clear_bloated_session("jochi", dry_run=True)
        # Not risky-flag-blocked; outcome is either skipped (no bloat)
        # or would_archive — but NEVER DISABLED_BY_RISKY_FLAG
        assert result["outcome"] != "DISABLED_BY_RISKY_FLAG"


# ===================================================================
# 2. Kill-switch gating across all public T0 functions
# ===================================================================

class TestKillSwitchGating:
    """When the global kill switch is active, every T0 action returns
    outcome='DISABLED_BY_FLAG'."""

    def test_requeue_stuck_task_disabled(self, kill_switch_on):
        result = haf.requeue_stuck_task("/tmp/x.executing.md")
        assert result["outcome"] == "DISABLED_BY_FLAG"
        assert result["dry_run"] is False

    def test_rotate_failing_provider_disabled(self, kill_switch_on):
        result = haf.rotate_failing_provider("temujin")
        assert result["outcome"] == "DISABLED_BY_FLAG"

    def test_clear_bloated_session_disabled(self, kill_switch_on):
        result = haf.clear_bloated_session("temujin")
        assert result["outcome"] == "DISABLED_BY_FLAG"

    def test_force_refresh_reflection_bridge_disabled(self, kill_switch_on):
        result = haf.force_refresh_reflection_bridge()
        assert result["outcome"] == "DISABLED_BY_FLAG"

    def test_reconcile_orphan_tasks_disabled(self, kill_switch_on):
        result = haf.reconcile_orphan_tasks()
        assert result["outcome"] == "DISABLED_BY_FLAG"


# ===================================================================
# 3. requeue_stuck_task
# ===================================================================

class TestRequeueStuckTask:

    def test_skips_non_executing_extension(self, kill_switch_off):
        result = haf.requeue_stuck_task("/tmp/some-task.md")
        assert result["outcome"] == "skipped"
        assert "does not end in .executing.md" in result["evidence"]["reason"]

    def test_file_not_found(self, kill_switch_off):
        result = haf.requeue_stuck_task("/nonexistent/xyz.executing.md")
        assert result["outcome"] == "error"
        assert result["evidence"]["reason"] == "file not found"

    def test_dry_run_returns_would_requeue_when_pid_dead(
        self, kill_switch_off, tmp_path, monkeypatch
    ):
        task_file = tmp_path / "T001.executing.md"
        task_file.write_text("---\ntask_id: T001\npid: 99999\n---\nbody")

        # Make lsof return empty (pid dead) by mocking subprocess.run
        mock_proc = MagicMock()
        mock_proc.stdout = ""
        mock_proc.stderr = ""
        monkeypatch.setattr(
            "hermes_auto_fix.subprocess.run", lambda *a, **kw: mock_proc
        )

        result = haf.requeue_stuck_task(str(task_file), dry_run=True)
        assert result["outcome"] == "would_emit_reap"
        assert result["dry_run"] is True
        assert result["evidence"]["pid"] == 99999
        assert result["evidence"]["pid_alive"] is False

    def test_skips_when_pid_alive(self, kill_switch_off, tmp_path, monkeypatch):
        task_file = tmp_path / "T002.executing.md"
        task_file.write_text("---\ntask_id: T002\npid: 1234\n---\nbody")

        # lsof returns output -> PID alive
        mock_proc = MagicMock()
        mock_proc.stdout = "COMMAND PID\nprocess 1234\n"
        mock_proc.stderr = ""
        monkeypatch.setattr(
            "hermes_auto_fix.subprocess.run", lambda *a, **kw: mock_proc
        )

        result = haf.requeue_stuck_task(str(task_file))
        assert result["outcome"] == "skipped"
        assert "PID still alive" in result["evidence"]["reason"]

    def test_live_emits_reap_event_without_touching_file(
        self, kill_switch_off, tmp_path, monkeypatch
    ):
        """Post single-writer refactor: hermes emits HERMES_REQUEST_REAP
        for task-reaper to consume; it does NOT move the file itself."""
        task_file = tmp_path / "T003.executing.md"
        task_file.write_text("---\ntask_id: T003\n---\nbody")

        # No PID in frontmatter -> pid_alive = False
        mock_proc = MagicMock()
        mock_proc.stdout = ""
        mock_proc.stderr = ""
        monkeypatch.setattr(
            "hermes_auto_fix.subprocess.run", lambda *a, **kw: mock_proc
        )

        result = haf.requeue_stuck_task(str(task_file), dry_run=False)
        assert result["outcome"] == "event_emitted"
        # Original file is NOT moved — task-reaper is the sole writer
        assert task_file.exists()

    def test_no_pid_assumes_stuck(self, kill_switch_off, tmp_path):
        """When no PID is in frontmatter, the task is assumed stuck
        (no running process to conflict)."""
        task_file = tmp_path / "T004.executing.md"
        task_file.write_text("---\ntask_id: T004\n---\nbody")

        result = haf.requeue_stuck_task(str(task_file), dry_run=True)
        assert result["outcome"] == "would_emit_reap"
        assert result["evidence"]["pid"] is None
        assert result["evidence"]["pid_alive"] is False

    def test_lsof_timeout_treats_pid_as_alive(
        self, kill_switch_off, tmp_path, monkeypatch
    ):
        import subprocess
        task_file = tmp_path / "T005.executing.md"
        task_file.write_text("---\ntask_id: T005\npid: 1111\n---\nbody")

        monkeypatch.setattr(
            "hermes_auto_fix.subprocess.run",
            MagicMock(side_effect=subprocess.TimeoutExpired(cmd="lsof", timeout=5)),
        )

        result = haf.requeue_stuck_task(str(task_file))
        assert result["outcome"] == "skipped"
        assert result["evidence"]["pid_alive"] is True


# ===================================================================
# 4. rotate_failing_provider
# ===================================================================

class TestRotateFailingProvider:

    def test_mode_json_not_found(self, kill_switch_off, fake_agents_dir, monkeypatch):
        monkeypatch.setattr(haf, "AGENTS_DIR", fake_agents_dir)
        result = haf.rotate_failing_provider("nonexistent_agent")
        assert result["outcome"] == "error"
        assert "mode.json not found" in result["evidence"]["reason"]

    def test_no_providers_configured(
        self, kill_switch_off, fake_agents_dir, monkeypatch
    ):
        monkeypatch.setattr(haf, "AGENTS_DIR", fake_agents_dir)
        agent_dir = fake_agents_dir / "temujin"
        agent_dir.mkdir()
        mode_file = agent_dir / "mode.json"
        mode_file.write_text(json.dumps({"providers": []}))

        result = haf.rotate_failing_provider("temujin")
        assert result["outcome"] == "skipped"
        assert "no providers configured" in result["evidence"]["reason"]

    def test_all_providers_already_failed(
        self, kill_switch_off, fake_agents_dir, monkeypatch
    ):
        monkeypatch.setattr(haf, "AGENTS_DIR", fake_agents_dir)
        agent_dir = fake_agents_dir / "jochi"
        agent_dir.mkdir()
        mode_file = agent_dir / "mode.json"
        mode_file.write_text(json.dumps({
            "providers": [
                {"name": "openai", "failed": True},
                {"name": "anthropic", "failed": True},
            ]
        }))

        result = haf.rotate_failing_provider("jochi")
        assert result["outcome"] == "skipped"
        assert "all providers already marked failed" in result["evidence"]["reason"]

    def test_no_backup_provider(
        self, kill_switch_off, fake_agents_dir, monkeypatch
    ):
        monkeypatch.setattr(haf, "AGENTS_DIR", fake_agents_dir)
        agent_dir = fake_agents_dir / "kublai"
        agent_dir.mkdir()
        mode_file = agent_dir / "mode.json"
        mode_file.write_text(json.dumps({
            "providers": [{"name": "openai"}]
        }))

        result = haf.rotate_failing_provider("kublai")
        assert result["outcome"] == "skipped"
        assert "no backup provider available" in result["evidence"]["reason"]

    def test_dry_run_returns_would_rotate(
        self, kill_switch_off, fake_agents_dir, monkeypatch
    ):
        monkeypatch.setattr(haf, "AGENTS_DIR", fake_agents_dir)
        agent_dir = fake_agents_dir / "ogedei"
        agent_dir.mkdir()
        mode_file = agent_dir / "mode.json"
        mode_file.write_text(json.dumps({
            "providers": [
                {"name": "openai"},
                {"name": "anthropic"},
            ]
        }))

        result = haf.rotate_failing_provider("ogedei", dry_run=True)
        assert result["outcome"] == "would_rotate"
        assert result["evidence"]["primary"] == "openai"
        assert result["evidence"]["backup"] == "anthropic"
        assert result["evidence"]["new_primary"] == "anthropic"
        # mode.json should NOT have changed
        data = json.loads(mode_file.read_text())
        assert data["providers"][0]["name"] == "openai"

    def test_live_rotation_reorders_providers(
        self, kill_switch_off, fake_agents_dir, monkeypatch
    ):
        monkeypatch.setattr(haf, "AGENTS_DIR", fake_agents_dir)
        agent_dir = fake_agents_dir / "tolui"
        agent_dir.mkdir()
        mode_file = agent_dir / "mode.json"
        mode_file.write_text(json.dumps({
            "providers": [
                {"name": "openai"},
                {"name": "anthropic"},
            ]
        }))

        result = haf.rotate_failing_provider("tolui", dry_run=False)
        assert result["outcome"] == "rotated"
        assert result["evidence"]["new_primary"] == "anthropic"

        # Verify file was updated
        data = json.loads(mode_file.read_text())
        assert data["providers"][0]["name"] == "anthropic"
        assert data["providers"][1]["name"] == "openai"
        assert data["providers"][1]["failed"] is True
        assert "failed_at" in data["providers"][1]


# ===================================================================
# 5. clear_bloated_session
# ===================================================================

class TestClearBloatedSession:

    def test_sessions_file_not_found(
        self, kill_switch_off, fake_agents_dir, monkeypatch
    ):
        monkeypatch.setattr(haf, "AGENTS_DIR", fake_agents_dir)
        result = haf.clear_bloated_session("mongke")
        assert result["outcome"] == "skipped"
        assert "sessions.json not found" in result["evidence"]["reason"]

    def test_below_bloat_threshold(
        self, kill_switch_off, fake_agents_dir, monkeypatch
    ):
        monkeypatch.setattr(haf, "AGENTS_DIR", fake_agents_dir)
        sessions_dir = fake_agents_dir / "mongke" / "sessions"
        sessions_dir.mkdir(parents=True)
        sessions_file = sessions_dir / "sessions.json"
        sessions_file.write_text("{}")  # well below 100KB

        result = haf.clear_bloated_session("mongke")
        assert result["outcome"] == "skipped"
        assert "below bloat threshold" in result["evidence"]["reason"]

    def test_dry_run_with_bloated_session(
        self, kill_switch_off, fake_agents_dir, monkeypatch
    ):
        monkeypatch.setattr(haf, "AGENTS_DIR", fake_agents_dir)
        sessions_dir = fake_agents_dir / "mongke" / "sessions"
        sessions_dir.mkdir(parents=True)
        sessions_file = sessions_dir / "sessions.json"
        # Write >100KB
        sessions_file.write_text("x" * (haf.SESSION_BLOAT_THRESHOLD + 1))

        result = haf.clear_bloated_session("mongke", dry_run=True)
        assert result["outcome"] == "would_archive"
        assert sessions_file.exists()  # file should still exist in dry-run

    def test_skips_when_active_executing_tasks(
        self, kill_switch_off, fake_agents_dir, monkeypatch
    ):
        monkeypatch.setattr(haf, "AGENTS_DIR", fake_agents_dir)
        sessions_dir = fake_agents_dir / "mongke" / "sessions"
        sessions_dir.mkdir(parents=True)
        sessions_file = sessions_dir / "sessions.json"
        sessions_file.write_text("x" * (haf.SESSION_BLOAT_THRESHOLD + 1))

        # Create an active executing task
        tasks_dir = fake_agents_dir / "mongke" / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "T100.executing.md").write_text("---\n---\nbody")

        result = haf.clear_bloated_session("mongke")
        assert result["outcome"] == "skipped"
        assert "active executing tasks" in result["evidence"]["reason"]

    def test_live_archive_moves_and_replaces(
        self, kill_switch_off, fake_agents_dir, monkeypatch
    ):
        monkeypatch.setattr(haf, "AGENTS_DIR", fake_agents_dir)
        sessions_dir = fake_agents_dir / "mongke" / "sessions"
        sessions_dir.mkdir(parents=True)
        sessions_file = sessions_dir / "sessions.json"
        original_content = "x" * (haf.SESSION_BLOAT_THRESHOLD + 1)
        sessions_file.write_text(original_content)

        result = haf.clear_bloated_session("mongke", dry_run=False)
        assert result["outcome"] == "archived"
        assert "archive_path" in result["evidence"]

        # Original sessions.json should now be a fresh empty object
        assert sessions_file.read_text() == "{}\n"

        # Archive should exist and contain original data
        archive_dir = sessions_dir / ".archive-backup"
        assert archive_dir.is_dir()
        archived_files = list(archive_dir.glob("sessions-*.json"))
        assert len(archived_files) == 1
        assert archived_files[0].read_text() == original_content


# ===================================================================
# 6. force_refresh_reflection_bridge
# ===================================================================

class TestForceRefreshReflectionBridge:

    def test_bridge_script_not_found(
        self, kill_switch_off, fake_scripts_dir, monkeypatch
    ):
        monkeypatch.setattr(haf, "SCRIPTS_DIR", fake_scripts_dir)
        result = haf.force_refresh_reflection_bridge()
        assert result["outcome"] == "error"
        assert "bridge script not found" in result["evidence"]["reason"]

    def test_dry_run_returns_would_run(
        self, kill_switch_off, fake_scripts_dir, monkeypatch
    ):
        monkeypatch.setattr(haf, "SCRIPTS_DIR", fake_scripts_dir)
        bridge = fake_scripts_dir / "reflection_pipeline_bridge.py"
        bridge.write_text("#!/usr/bin/env python3\nprint('ok')\n")

        result = haf.force_refresh_reflection_bridge(dry_run=True)
        assert result["outcome"] == "would_run"
        assert result["dry_run"] is True

    def test_live_run_success(self, kill_switch_off, fake_scripts_dir, monkeypatch):
        monkeypatch.setattr(haf, "SCRIPTS_DIR", fake_scripts_dir)
        bridge = fake_scripts_dir / "reflection_pipeline_bridge.py"
        bridge.write_text("#!/usr/bin/env python3\nprint('ok')\n")

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "reflection complete"
        mock_proc.stderr = ""
        monkeypatch.setattr(
            "hermes_auto_fix.subprocess.run", lambda *a, **kw: mock_proc
        )

        result = haf.force_refresh_reflection_bridge(dry_run=False)
        assert result["outcome"] == "success"
        assert "reflection complete" in result["evidence"]["stdout_tail"]

    def test_live_run_script_error(
        self, kill_switch_off, fake_scripts_dir, monkeypatch
    ):
        monkeypatch.setattr(haf, "SCRIPTS_DIR", fake_scripts_dir)
        bridge = fake_scripts_dir / "reflection_pipeline_bridge.py"
        bridge.write_text("#!/usr/bin/env python3\nprint('ok')\n")

        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = ""
        mock_proc.stderr = "something went wrong"
        monkeypatch.setattr(
            "hermes_auto_fix.subprocess.run", lambda *a, **kw: mock_proc
        )

        result = haf.force_refresh_reflection_bridge(dry_run=False)
        assert result["outcome"] == "script_error"

    def test_live_run_timeout(self, kill_switch_off, fake_scripts_dir, monkeypatch):
        import subprocess
        monkeypatch.setattr(haf, "SCRIPTS_DIR", fake_scripts_dir)
        bridge = fake_scripts_dir / "reflection_pipeline_bridge.py"
        bridge.write_text("#!/usr/bin/env python3\nprint('ok')\n")

        monkeypatch.setattr(
            "hermes_auto_fix.subprocess.run",
            MagicMock(side_effect=subprocess.TimeoutExpired(cmd="bridge", timeout=120)),
        )

        result = haf.force_refresh_reflection_bridge(dry_run=False)
        assert result["outcome"] == "timeout"
        assert "timed out" in result["evidence"]["reason"]


# ===================================================================
# 7. reconcile_orphan_tasks
# ===================================================================

class TestReconcileOrphanTasks:

    def test_reconciler_script_not_found(
        self, kill_switch_off, fake_scripts_dir, monkeypatch
    ):
        monkeypatch.setattr(haf, "SCRIPTS_DIR", fake_scripts_dir)
        result = haf.reconcile_orphan_tasks()
        assert result["outcome"] == "error"
        assert "reconciler script not found" in result["evidence"]["reason"]

    def test_dry_run_does_not_pass_fix_flag(
        self, kill_switch_off, fake_scripts_dir, monkeypatch
    ):
        monkeypatch.setattr(haf, "SCRIPTS_DIR", fake_scripts_dir)
        reconciler = fake_scripts_dir / "task-consistency-reconciler.py"
        reconciler.write_text("#!/usr/bin/env python3\nprint('ok')\n")

        # Capture the actual command passed to subprocess.run
        captured_cmd = {}
        def fake_run(cmd, **kwargs):
            captured_cmd["cmd"] = cmd
            mock = MagicMock()
            mock.returncode = 0
            mock.stdout = "ok"
            mock.stderr = ""
            return mock
        monkeypatch.setattr("hermes_auto_fix.subprocess.run", fake_run)

        result = haf.reconcile_orphan_tasks(dry_run=True)
        assert result["outcome"] == "success"
        assert "--fix" not in captured_cmd["cmd"]

    def test_live_run_passes_fix_flag(
        self, kill_switch_off, fake_scripts_dir, monkeypatch
    ):
        monkeypatch.setattr(haf, "SCRIPTS_DIR", fake_scripts_dir)
        reconciler = fake_scripts_dir / "task-consistency-reconciler.py"
        reconciler.write_text("#!/usr/bin/env python3\nprint('ok')\n")

        captured_cmd = {}
        def fake_run(cmd, **kwargs):
            captured_cmd["cmd"] = cmd
            mock = MagicMock()
            mock.returncode = 0
            mock.stdout = "ok"
            mock.stderr = ""
            return mock
        monkeypatch.setattr("hermes_auto_fix.subprocess.run", fake_run)

        result = haf.reconcile_orphan_tasks(dry_run=False)
        assert result["outcome"] == "success"
        assert "--fix" in captured_cmd["cmd"]

    def test_timeout_handling(self, kill_switch_off, fake_scripts_dir, monkeypatch):
        import subprocess
        monkeypatch.setattr(haf, "SCRIPTS_DIR", fake_scripts_dir)
        reconciler = fake_scripts_dir / "task-consistency-reconciler.py"
        reconciler.write_text("#!/usr/bin/env python3\nprint('ok')\n")

        monkeypatch.setattr(
            "hermes_auto_fix.subprocess.run",
            MagicMock(side_effect=subprocess.TimeoutExpired(cmd="reconciler", timeout=120)),
        )

        result = haf.reconcile_orphan_tasks()
        assert result["outcome"] == "timeout"


# ===================================================================
# 8. emit_hermes_heartbeat
# ===================================================================

class TestEmitHermesHeartbeat:

    def test_calls_write_heartbeat(self, monkeypatch):
        mock_write = MagicMock()
        monkeypatch.setattr(haf, "write_heartbeat", mock_write)
        haf.emit_hermes_heartbeat()
        mock_write.assert_called_once_with(daemon_name="hermes-watchdog")


# ===================================================================
# 9. _emit_hermes_action (internal helper)
# ===================================================================

class TestEmitHermesAction:

    def test_writes_jsonl_entry(self, kill_switch_off):
        haf._emit_hermes_action(
            "test_action", "test_target", "test_outcome",
            dry_run=True, evidence={"key": "value"},
        )
        log = haf.HERMES_ACTIONS_LOG
        assert log.exists()
        lines = log.read_text().strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["action_type"] == "test_action"
        assert entry["target"] == "test_target"
        assert entry["outcome"] == "test_outcome"
        assert entry["dry_run"] is True
        assert entry["evidence"]["key"] == "value"

    def test_neo4j_failure_does_not_raise(self, kill_switch_off, monkeypatch):
        """If Neo4j import fails, the function should log a warning but not raise."""
        # Make LOGS_DIR writable (already set by autouse fixture)
        # The Neo4j import inside _emit_hermes_action will fail because the
        # module is not available in the test environment.
        # This should not raise an exception.
        haf._emit_hermes_action("test", "t", "ok")

    def test_jsonl_write_failure_does_not_raise(self, tmp_path, monkeypatch):
        """If the JSONL file cannot be written, the function should not raise."""
        # Point LOGS_DIR to a read-only path
        readonly = tmp_path / "readonly"
        readonly.mkdir()
        monkeypatch.setattr(haf, "LOGS_DIR", readonly)
        monkeypatch.setattr(haf, "HERMES_ACTIONS_LOG", readonly / "nope.jsonl")
        monkeypatch.setattr(Path, "mkdir", MagicMock(side_effect=OSError("read-only")))
        # Should not raise
        haf._emit_hermes_action("test", "t", "ok")


# ===================================================================
# 10. CLI parser and main()
# ===================================================================

class TestCLI:

    def test_build_cli_parser_returns_parser(self):
        parser = haf._build_cli_parser()
        assert isinstance(parser, argparse.ArgumentParser)

    def test_parser_requires_action(self):
        parser = haf._build_cli_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_parser_valid_actions(self):
        parser = haf._build_cli_parser()
        expected_actions = [
            "requeue_stuck_task",
            "rotate_failing_provider",
            "clear_bloated_session",
            "force_refresh_reflection_bridge",
            "reconcile_orphan_tasks",
            "emit_heartbeat",
        ]
        for action in expected_actions:
            args = parser.parse_args(["--action", action])
            assert args.action == action

    def test_parser_dry_run_flag(self):
        parser = haf._build_cli_parser()
        args = parser.parse_args(["--action", "emit_heartbeat", "--dry-run"])
        assert args.dry_run is True

    def test_parser_target_option(self):
        parser = haf._build_cli_parser()
        args = parser.parse_args(["--action", "requeue_stuck_task", "--target", "/tmp/x"])
        assert args.target == "/tmp/x"

    def test_main_emits_heartbeat(self, kill_switch_on, monkeypatch, capsys):
        """Integration-ish test: main() with --action emit_heartbeat produces output."""
        monkeypatch.setattr(sys, "argv", ["hermes_auto_fix.py", "--action", "emit_heartbeat"])
        mock_write = MagicMock()
        monkeypatch.setattr(haf, "write_heartbeat", mock_write)
        haf.main()
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["action"] == "emit_heartbeat"
        assert output["outcome"] == "written"


# ===================================================================
# 11. Result structure consistency
# ===================================================================

class TestResultStructure:
    """All T0 functions should return dicts with the same canonical keys."""

    @pytest.fixture
    def setup_env(self, kill_switch_on):
        """Kill switch on is the simplest way to get a result from each function."""
        return

    @pytest.mark.parametrize("func,args", [
        (haf.requeue_stuck_task, ("/tmp/x.executing.md",)),
        (haf.rotate_failing_provider, ("temujin",)),
        (haf.clear_bloated_session, ("temujin",)),
        (haf.force_refresh_reflection_bridge, ()),
        (haf.reconcile_orphan_tasks, ()),
    ])
    def test_result_has_canonical_keys(self, setup_env, func, args):
        result = func(*args)
        for key in ("action", "target", "dry_run", "outcome", "evidence"):
            assert key in result, f"Missing key '{key}' in result from {func.__name__}"

    @pytest.mark.parametrize("func,args", [
        (haf.requeue_stuck_task, ("/tmp/x.executing.md", True)),
        (haf.rotate_failing_provider, ("temujin", True)),
        (haf.clear_bloated_session, ("temujin", True)),
        (haf.force_refresh_reflection_bridge, (True,)),
        (haf.reconcile_orphan_tasks, (True,)),
    ])
    def test_dry_run_reflected_in_result(self, setup_env, func, args):
        result = func(*args)
        assert result["dry_run"] is True
