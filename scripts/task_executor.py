"""
task_executor.py — Unified task execution engine for the Openclaw agent fleet.

Replaces:
  - task-watcher.py        (3,724 lines) — session bloat detection, stall detection,
                                           poll/claim/run loop, ledger writes
  - agent-task-handler.py  (4,349 lines) — model drift detection, verify_result gate,
                                           build_agent_env, completion/failure persistence

Architecture (6 components in one file):
  1. Data types     — frozen dataclasses: RunResult, SessionState; module constants
  2. SessionManager — unified session bloat + model drift cleanup in a single pass
  3. TaskRunner     — asyncio subprocess with PID-scoped stall detection
  4. verify_result  — sole completion gate; only path to COMPLETED status
  5. build_agent_env— credential vault loading + environment sanitization
  6. Executor       — asyncio event loop: poll → claim → run → verify → persist

Entry point: `python task_executor.py`
Single-instance enforced via PID-file lock at LOGS_DIR/task-executor.pid.
"""

import asyncio
import json
import logging
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kurultai_paths import (
    AGENTS_DIR,
    DISPATCH_AGENTS,
    CLAUDE_AGENT,
    CLAUDE_TIMEOUT,
    TIMEOUT_BY_PRIORITY,
    SLOW_SKILLS,
    TASK_LEDGER,
    SPAWN_QUEUE,
    LOGS_DIR,
    SCRIPTS_DIR,
    agent_sessions_path,
    VALID_CLAUDE_MODELS,
)
from neo4j_v2_core import TaskStore
from neo4j_v2_wal import WAL
from neo4j_v2_failure import classify_failure
from neo4j_v2_events import emit_event, emit_session_reset
from circuit_breaker import AgentCircuitBreaker
from prompt_sanitizer import PromptSanitizer
from notification_queue import NotificationQueue
from delivery_classifier import classify_delivery_task
from delivery_verifier import verify_delivery
from kurultai_ledger import generate_task_id


# ---------------------------------------------------------------------------
# Component 1: Data Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RunResult:
    """Immutable record of a single agent subprocess execution."""
    success: bool
    content: str
    return_code: int
    duration_s: float
    model: str
    stall_detected: bool


@dataclass(frozen=True)
class SessionState:
    """Immutable record of pre-execution session cleanup outcome."""
    clean: bool           # True if no cleanup was needed
    bloat_reset: bool     # True if sessions.json was reset
    drift_archived: bool  # True if a stale JSONL was archived
    reason: str           # Human-readable: "clean" | "bloat:18432" | "drift:glm-5" | combined


# Pipeline direct-execution pattern: matches "python3 script.py" prompt prefixes
_SCRIPT_RE = re.compile(r'^python3?\s+(\S+\.py)\b')

# Module-level constants
STALL_SILENCE = 900      # seconds of stdout silence before stall check
STALL_MIN_ELAPSED = 900  # only start stall checks after this many seconds
POLL_INTERVAL = 30       # seconds between poll cycles
CONCURRENCY = 1          # concurrent task slots — reduced from 6 to prevent OOM on 16GB machine
CU_LOCK_TIMEOUT = 300    # seconds to wait for Computer Use exclusivity lock

# Stall escalation: after this many stall-detected failures, escalate to STALL_ESCALATED
# instead of re-queuing.  Set via STALL_ESCALATION_THRESHOLD env var for easy tuning.
STALL_ESCALATION_THRESHOLD = int(os.environ.get("STALL_ESCALATION_THRESHOLD", "3"))

# Log file for stall escalations (proposal 3)
STALL_ESCALATION_LOG = Path.home() / ".openclaw" / "logs" / "stall-escalations.jsonl"

# Two-phase prompt generation constants
PROMPT_GEN_TIMEOUT = 120        # Phase 1 timeout (seconds) — uses agent's configured model
PROMPT_START = "<<<OPTIMIZED_PROMPT>>>"
PROMPT_END = "<<<END_OPTIMIZED_PROMPT>>>"
PROMPT_COMPLEXITY_THRESHOLD = 15  # skip Phase 1 for tasks below this complexity


# ---------------------------------------------------------------------------
# Component 2: SessionManager
# ---------------------------------------------------------------------------

class SessionManager:
    """Unified pre-execution session hygiene.

    Replaces both _check_and_reset_bloated_session() (task-watcher.py:1444)
    and _validate_session_model() (agent-task-handler.py:1845) with a single
    atomic pass that handles both bloat AND model drift.
    """

    def __init__(self, bloat_threshold: int = 100_000):  # 100 KB
        self.bloat_threshold = bloat_threshold

    def prepare(self, agent: str) -> SessionState:
        """Single pre-execution cleanup pass. Checks bloat AND drift atomically.

        Args:
            agent: The agent identifier string (e.g. "chagatai", "mongke").

        Returns:
            SessionState describing what was found and cleaned.
        """
        bloat_reset = False
        drift_archived = False
        reasons: list[str] = []

        # Step 1: Check sessions.json for size bloat
        session_path = agent_sessions_path(agent)
        if session_path.exists():
            try:
                size = session_path.stat().st_size
                if size > self.bloat_threshold:
                    backup = session_path.with_suffix(
                        f".bloated.{int(time.time())}.json"
                    )
                    shutil.copy2(session_path, backup)
                    session_path.write_text("{}")
                    bloat_reset = True
                    reasons.append(f"bloat:{size}")
            except OSError:
                pass

        # Step 2: Check latest .jsonl for model drift
        sessions_dir = AGENTS_DIR / agent / "sessions"
        if sessions_dir.exists():
            jsonl_files = sorted(
                [
                    f
                    for f in sessions_dir.glob("*.jsonl")
                    if ".drift-" not in f.name
                ],
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            if jsonl_files:
                latest = jsonl_files[0]
                drift_model = self._detect_drift(latest)
                if drift_model:
                    archive_path = str(latest) + f".drift-{int(time.time())}"
                    try:
                        os.rename(str(latest), archive_path)
                        drift_archived = True
                        reasons.append(f"drift:{drift_model}")
                    except OSError:
                        pass

        return SessionState(
            clean=not (bloat_reset or drift_archived),
            bloat_reset=bloat_reset,
            drift_archived=drift_archived,
            reason=",".join(reasons) if reasons else "clean",
        )

    def _detect_drift(self, session_file: Path) -> Optional[str]:
        """Check if a session file is using a non-Claude model.

        Scans the last 50 lines of the JSONL for known drift provider/model
        strings.

        Returns:
            The offending "provider/model" string, or None if Claude.
        """
        known_drift = [
            "glm-5", "kimi", "qwen", "bailian",
            "dashscope", "minimax", "zai-coding",
        ]
        try:
            with open(session_file) as f:
                lines = f.readlines()[-50:]
            for line in reversed(lines):
                try:
                    entry = json.loads(line)
                    msg = entry.get("message", {})
                    if isinstance(msg, dict):
                        model = msg.get("model", "")
                        provider = msg.get("provider", "")
                        combined = f"{provider}/{model}".lower()
                        if model and any(p in combined for p in known_drift):
                            return f"{provider}/{model}" if provider else model
                except (json.JSONDecodeError, KeyError):
                    continue
        except OSError:
            pass
        return None


# ---------------------------------------------------------------------------
# Component 2b: WorktreeManager
# ---------------------------------------------------------------------------

class WorktreeManager:
    """Git worktree lifecycle for agent-isolated project edits.

    Creates a fresh worktree from main before task execution and
    provides the worktree path for prompt rewriting. Cleanup happens
    post-merge or via scheduled cron.
    """

    def __init__(self):
        from kurultai_paths import PROJECT_REGISTRY, agent_worktree_dir
        self._registry = PROJECT_REGISTRY
        self._agent_worktree_dir = agent_worktree_dir

    def detect_project(self, prompt: str):
        """Scan prompt text for known project root paths.

        Returns the first matching PROJECT_REGISTRY entry with 'root' key,
        or None if no project path is mentioned.
        """
        for root, config in self._registry.items():
            if root in prompt:
                return {**config, "root": root}
        return None

    async def create_worktree(
        self, agent: str, project: dict, task_id: str
    ):
        """Create a git worktree for isolated edits.

        Returns Path to the worktree directory, or None on failure.
        """
        project_root = project["root"]
        branch_name = f"task-{task_id[:12]}"
        worktree_path = self._agent_worktree_dir(agent, project["name"])

        # Ensure parent exists
        worktree_path.parent.mkdir(parents=True, exist_ok=True)

        # Remove stale worktree at same path if exists
        if worktree_path.exists():
            await self._remove_worktree(project_root, worktree_path)

        try:
            # Delete branch if it already exists (from a previous failed run).
            # Must await proc.wait() — fire-and-forget causes a race with worktree add.
            del_proc = await asyncio.create_subprocess_exec(
                "git", "-C", project_root,
                "branch", "-D", branch_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(del_proc.wait(), timeout=10)

            # Create branch from main and worktree
            proc = await asyncio.create_subprocess_exec(
                "git", "-C", project_root,
                "worktree", "add", "-b", branch_name,
                str(worktree_path), project["branch"],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            if proc.returncode != 0:
                logger.warning(
                    f"Worktree creation failed: {stderr.decode()}"
                )
                return None
            return worktree_path
        except Exception as e:
            logger.warning(f"Worktree creation error: {e}")
            return None

    def rewrite_prompt(
        self, prompt: str, project_root: str, worktree_path
    ) -> str:
        """Replace absolute project paths in prompt with worktree paths."""
        return prompt.replace(project_root, str(worktree_path))

    async def _remove_worktree(self, project_root: str, worktree_path):
        """Force-remove a stale worktree."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "-C", project_root,
                "worktree", "remove", str(worktree_path), "--force",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=15)
        except Exception:
            pass

    async def cleanup_worktree(
        self, project_root: str, worktree_path, branch_name: str
    ):
        """Remove the worktree directory and delete its branch.

        Called after task deploy pipeline completes (or fails) to prevent
        stale branch accumulation across tasks.
        """
        await self._remove_worktree(project_root, worktree_path)
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "-C", project_root,
                "branch", "-D", branch_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=10)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Component 3: TaskRunner
# ---------------------------------------------------------------------------

class TaskRunner:
    """asyncio subprocess runner with PID-scoped stall detection.

    Streams stdout line-by-line. After STALL_MIN_ELAPSED seconds, monitors
    for STALL_SILENCE seconds of stdout silence and confirms staleness via
    lsof before terminating.
    """

    def __init__(self, claude_agent: Path = CLAUDE_AGENT):
        self.claude_agent = str(claude_agent)

    async def run(
        self,
        agent: str,
        prompt: str,
        env: dict,
        timeout: int = CLAUDE_TIMEOUT,
        model: Optional[str] = None,
    ) -> RunResult:
        """Execute the claude agent subprocess for a given agent and prompt.

        Args:
            agent:   Agent identifier used to set --workdir.
            prompt:  Full task prompt string passed after --.
            env:     Pre-built environment dict from build_agent_env().
            timeout: Hard wall-clock timeout in seconds.
            model:   Optional model override; omitted if None.

        Returns:
            RunResult with success flag, captured stdout, return code,
            wall-clock duration, model name, and stall_detected flag.
        """
        cmd = [self.claude_agent, "--workdir", str(AGENTS_DIR / agent)]
        if model:
            cmd.extend(["--model", model])
        cmd.extend(["--", prompt])

        start = time.time()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                start_new_session=True,  # Isolate child signals from executor
            )
        except Exception as e:
            return RunResult(
                success=False,
                content=f"Failed to start: {e}",
                return_code=-1,
                duration_s=0.0,
                model=model or "default",
                stall_detected=False,
            )

        content_chunks: list[str] = []
        last_output = time.time()
        stall_detected = False

        try:
            while True:
                try:
                    line = await asyncio.wait_for(proc.stdout.readline(), timeout=1.0)
                    if not line:
                        break  # EOF
                    content_chunks.append(line.decode("utf-8", errors="replace"))
                    last_output = time.time()
                except asyncio.TimeoutError:
                    elapsed = time.time() - start
                    silence = time.time() - last_output

                    # Stall check: only after minimum elapsed time
                    if elapsed > STALL_MIN_ELAPSED and silence > STALL_SILENCE:
                        if not await self._pid_active(proc.pid, agent):
                            stall_detected = True
                            proc.terminate()
                            try:
                                await asyncio.wait_for(proc.wait(), timeout=10)
                            except asyncio.TimeoutError:
                                proc.kill()
                            break

                    # Hard timeout
                    if elapsed > timeout:
                        proc.kill()
                        try:
                            await asyncio.wait_for(proc.wait(), timeout=5)
                        except asyncio.TimeoutError:
                            pass
                        break

            if proc.returncode is None:
                await asyncio.wait_for(proc.wait(), timeout=10)
        except Exception:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass

        content = "".join(content_chunks)
        return RunResult(
            success=proc.returncode == 0 and bool(content.strip()),
            content=content,
            return_code=proc.returncode if proc.returncode is not None else -1,
            duration_s=time.time() - start,
            model=model or "default",
            stall_detected=stall_detected,
        )

    async def _pid_active(self, pid: int, agent: str = "") -> bool:
        """Check if a process group has recently written to any .jsonl file.

        Two-stage check:
        1. lsof -g for currently OPEN .jsonl files (fast, process-group-specific).
        2. Filesystem mtime scan of the agent's claude project directory for
           recently MODIFIED .jsonl files. Handles claude-code's write pattern
           of open → write → close between turns; during long Agent subagent
           dispatches the file is closed but was recently modified.

        Uses lsof -g to check the entire process group (pgid == pid when launched
        with start_new_session=True). This catches activity from child processes
        like the claude binary that is a grandchild of the bash wrapper script.

        Returns:
            True if active, False if stalled (or on any lsof error).
        """
        # Stage 1: lsof check for currently open .jsonl files
        try:
            proc = await asyncio.create_subprocess_exec(
                "lsof", "-g", str(pid), "-F", "n",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            for line in stdout.decode(errors="replace").splitlines():
                if line.startswith("n/") and ".jsonl" in line:
                    path = line[1:]
                    if ".drift-" in path:
                        continue  # Skip already-archived drift files
                    try:
                        if time.time() - os.path.getmtime(path) < 60:
                            return True
                    except OSError:
                        pass
        except Exception:
            pass

        # Stage 2: filesystem mtime scan for agent's claude project directory.
        # claude-code closes its conversation .jsonl between turns, so lsof misses
        # it when the process is idle-waiting for a subagent result. If the file
        # was modified within the STALL_SILENCE window, the process was active
        # recently and should not be killed. (Safe: stall check only fires while
        # proc is still running — EOF would have exited the loop before this point.)
        if agent:
            workdir = str(AGENTS_DIR / agent)
            # Claude Code encodes project paths by replacing ALL non-alphanumeric
            # characters (including '.') with '-'.  A plain replace("/", "-") leaves
            # dots intact, so e.g. "/.openclaw/" encodes to "-.openclaw-" instead of
            # "--openclaw-", causing _pid_active to scan the wrong directory and
            # always return False → every task running >15 min gets false-stall-killed.
            encoded = re.sub(r"[^a-zA-Z0-9]", "-", workdir)
            project_dir = Path.home() / ".claude" / "projects" / encoded
            try:
                for jsonl_path in project_dir.glob("*.jsonl"):
                    try:
                        if time.time() - jsonl_path.stat().st_mtime < STALL_SILENCE:
                            return True
                    except OSError:
                        pass
            except Exception:
                pass

        return False


# ---------------------------------------------------------------------------
# Triage gate helpers (module-level, used by Executor._execute_inner)
# ---------------------------------------------------------------------------

def _find_triage_task_file(agent: str, task_id: str) -> Optional[Path]:
    """Locate the task .md file for a given agent and task_id.

    Tries the executor-standard name ({task_id}.md) first, then falls back
    to scanning dispatch-format files that embed the task_id in their body.
    Returns None if not found.
    """
    tasks_dir = AGENTS_DIR / agent / "tasks"
    if not tasks_dir.exists():
        return None
    # Standard executor naming
    candidate = tasks_dir / f"{task_id}.md"
    if candidate.exists():
        return candidate
    # Fallback: scan dispatch-format files for embedded task_id
    for f in sorted(tasks_dir.glob("*.md")):
        try:
            if task_id in f.read_text(encoding="utf-8", errors="replace"):
                return f
        except OSError:
            pass
    return None


def _is_triage_task(task: dict, task_file: Optional[Path] = None) -> bool:
    """Return True if the task qualifies as a triage task.

    Priority order (first match wins):
    1. Filename contains 'triage'
    2. Prompt body has frontmatter: type: triage | escalation
    3. Title contains 'triage', 'escalation', or 'investigate'
    """
    if task_file and "triage" in task_file.name.lower():
        return True
    prompt = task.get("prompt", task.get("body", ""))
    if re.search(r"^type:\s*(triage|escalation)\s*$", prompt, re.MULTILINE | re.IGNORECASE):
        return True
    title = task.get("title", "").lower()
    if any(kw in title for kw in ("triage", "escalation", "investigate")):
        return True
    return False


def _update_frontmatter_key(file_path: Path, key: str, value: str) -> bool:
    """Insert or overwrite a YAML frontmatter key in a task .md file.

    Returns True on success, False if the file lacks valid frontmatter or
    cannot be written.
    """
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        if not content.startswith("---"):
            return False
        end = content.find("\n---", 3)
        if end == -1:
            return False
        frontmatter = content[3:end]
        rest = content[end + 4:]
        new_line = f"{key}: {value}"
        key_pat = re.compile(rf"^{re.escape(key)}:.*$", re.MULTILINE)
        if key_pat.search(frontmatter):
            frontmatter = key_pat.sub(new_line, frontmatter)
        else:
            frontmatter = frontmatter.rstrip("\n") + f"\n{new_line}"
        file_path.write_text(f"---{frontmatter}\n---{rest}", encoding="utf-8")
        return True
    except OSError:
        return False


def _read_frontmatter_int(file_path: Path, key: str) -> Optional[int]:
    """Read an integer YAML frontmatter field. Returns None if absent or on error."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        m = re.search(rf"^{re.escape(key)}:\s*(\d+)", content, re.MULTILINE)
        return int(m.group(1)) if m else None
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Component 4: verify_result() and build_agent_env()
# ---------------------------------------------------------------------------

def verify_result(
    run_result: RunResult, skip_resolution: bool = False
) -> tuple[bool, str]:
    """THE completion gate. The only path to COMPLETED status.

    Checks, in order:
      1. Process exit code (must be 0)
      2. Non-empty output
      3. No stall flag from TaskRunner
      4. Absence of error patterns masquerading as success (short output only)
      5. Presence of '## Resolution' heading with non-empty body content
         (skipped when skip_resolution=True, e.g. for pipeline/script tasks)

    Args:
        run_result: The RunResult returned by TaskRunner.run().
        skip_resolution: If True, skip the ## Resolution content check.
            Use this for direct pipeline scripts whose stdout is structured
            data rather than a human-readable completion report.

    Returns:
        (passed, reason) — passed=True means safe to mark COMPLETED.
        reason is "verified" on success, or a short error category string
        on failure (e.g. "exit:1", "empty_output", "stall_detected",
        "error_in_output:rate_limited", "missing_resolution").
    """
    if not run_result.success:
        return False, f"exit:{run_result.return_code}"

    content = run_result.content.strip()
    if not content:
        return False, "empty_output"

    if run_result.stall_detected:
        return False, "stall_detected"

    # Error patterns that can appear in short output while exit code is 0
    error_patterns = [
        ("not logged in", "auth_failure"),
        ("please run /login", "auth_failure"),
        ("rate limit", "rate_limited"),
        ("too many requests", "rate_limited"),
        ("429", "rate_limited"),
        ("connection refused", "network_error"),
        ("sigterm", "killed"),
    ]
    content_lower = content.lower()
    if len(content) < 500:
        for pattern, category in error_patterns:
            if pattern in content_lower:
                return False, f"error_in_output:{category}"

    # Resolution content gate — every agent completion must include a
    # '## Resolution' section with at least one non-empty line of content.
    # Pipeline/script tasks are exempt (their stdout is structured data).
    if not skip_resolution:
        resolution_match = re.search(r"^##\s+Resolution\s*$", content, re.MULTILINE | re.IGNORECASE)
        if resolution_match:
            # Verify there is at least one non-empty line after the heading
            after_heading = content[resolution_match.end():].lstrip("\n")
            next_heading = re.search(r"^##\s+", after_heading, re.MULTILINE)
            body = after_heading[: next_heading.start()] if next_heading else after_heading
            if not body.strip():
                return False, "missing_resolution_content"
        else:
            return False, "missing_resolution"

    return True, "verified"


def build_agent_env(agent: str) -> dict:
    """Build a clean subprocess environment for an agent.

    Pipeline:
      1. Copy os.environ
      2. Remove CLAUDECODE (allows nested Claude Code sessions)
      3. Prepend known tool paths to PATH
      4. Strip ALL ANTHROPIC_* vars (prevents key inheritance from parent)
      5. Load vault credentials from ~/.openclaw/credentials/provider.env
      6. Load agent-specific env overrides from .claude/settings.json

    Args:
        agent: Agent identifier string.

    Returns:
        A clean dict suitable for passing as env= to subprocess/asyncio.
    """
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    env["PATH"] = (
        "/Users/kublai/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:"
        + env.get("PATH", "")
    )

    # Strip any inherited ANTHROPIC_* vars to prevent key collision
    for key in [k for k in env if k.startswith("ANTHROPIC_")]:
        del env[key]

    # Load vault credentials
    vault_path = Path.home() / ".openclaw" / "credentials" / "provider.env"
    if vault_path.exists():
        try:
            for line in vault_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip("\"'")
        except OSError:
            pass

    # Load agent-specific env overrides from settings.json
    settings_path = AGENTS_DIR / agent / ".claude" / "settings.json"
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
            for k, v in settings.get("env", {}).items():
                env[k] = str(v)
        except (OSError, json.JSONDecodeError):
            pass

    return env


# ---------------------------------------------------------------------------
# Component 5: Executor
# ---------------------------------------------------------------------------

logger = logging.getLogger("task_executor")


class Executor:
    """asyncio event loop: poll → claim → run → verify → persist.

    Manages CONCURRENCY concurrent tasks across DISPATCH_AGENTS via an
    asyncio.Semaphore. Handles startup orphan recovery, WAL replay, lease
    renewal, spawn-queue processing, and graceful shutdown.
    """

    def __init__(
        self,
        store: TaskStore,
        runner: TaskRunner,
        session_mgr: SessionManager,
        wal: WAL,
        cb: AgentCircuitBreaker,
        sanitizer: PromptSanitizer,
        agents: Optional[list] = None,
        concurrency: int = CONCURRENCY,
    ):
        self._store = store
        self._runner = runner
        self._session_mgr = session_mgr
        self._wal = wal
        self._cb = cb
        self._sanitizer = sanitizer
        self._agents = agents or list(DISPATCH_AGENTS)
        self._semaphore = asyncio.Semaphore(concurrency)
        self._concurrency = concurrency
        self._computer_use_lock = asyncio.Lock()
        self._active_tasks: set[str] = set()
        self._active_task_epochs: dict[str, int] = {}  # task_id → claim_epoch for lease renewal
        self._executor_id = f"exec-{uuid.uuid4().hex[:8]}"
        self._driver = None  # Lazy — resolved via _get_driver()
        self._shutdown = False
        self._worktree_mgr = WorktreeManager()
        self._nqueue = NotificationQueue()

    def _get_driver(self):
        """Lazy driver access — uses TaskStore's property which auto-creates."""
        if self._driver is None:
            self._driver = self._store.driver
        return self._driver

    def _requires_computer_use(self, task: dict) -> bool:
        """Check if task needs exclusive Computer Use access."""
        if task.get("requires_computer_use", False):
            return True
        prompt = (task.get("prompt", "") or "").lower()
        cu_keywords = [
            "screenshot", "click on", "open the app", "computer use",
            "native app", "gui", "interact with the screen",
            "open finder", "open safari", "open terminal",
        ]
        web_keywords = [
            "playwright", "browser_navigate", "headless browser",
            "web page", "browser_snapshot",
        ]
        if any(kw in prompt for kw in web_keywords):
            return False
        return any(kw in prompt for kw in cu_keywords)

    async def run(self):
        """Main loop: startup recovery → WAL replay → poll → dispatch → repeat."""
        # Startup: recover tasks orphaned by a previous crash
        try:
            recovered = self._store.recover_orphans()
            if recovered:
                logger.info(f"Recovered {len(recovered)} orphaned tasks")
                for task in recovered:
                    emit_event(
                        self._get_driver(),
                        "ORPHAN_RECOVERED",
                        task.get("task_id", ""),
                        task.get("assigned_to", ""),
                        executor_id=self._executor_id,
                    )
        except Exception as e:
            logger.warning(f"Orphan recovery failed: {e}")

        # Startup: replay any buffered WAL entries
        try:
            replayed = self._wal.replay(self._get_driver())
            if replayed:
                logger.info(f"Replayed {replayed} WAL entries")
        except Exception as e:
            logger.warning(f"WAL replay failed: {e}")

        emit_event(
            self._get_driver(), "EXECUTOR_STARTED", "", "",
            executor_id=self._executor_id,
        )
        logger.info(
            f"Executor {self._executor_id} started, agents={self._agents}"
        )

        # Background lease renewal
        asyncio.create_task(self._renew_leases())

        # Startup: recover orphans from previous executor crashes
        # Don't wait for lease expiry — check executor_id mismatch
        self._recover_orphaned_working_tasks()

        self._poll_count = 0
        self._last_dispatch_at: Optional[str] = None
        _last_blocked_sweep = 0.0
        _last_fs_sync = 0.0
        BLOCKED_SWEEP_INTERVAL = 120   # seconds — safety net for push-based unblock misses
        FS_SYNC_INTERVAL = 1800        # seconds — reconcile filesystem with Neo4j state
        while not self._shutdown:
            try:
                await self._poll_and_dispatch()
                self._write_heartbeat()
                # Periodically sweep BLOCKED tasks whose all deps are COMPLETED
                now = asyncio.get_running_loop().time()
                if now - _last_blocked_sweep >= BLOCKED_SWEEP_INTERVAL:
                    try:
                        unblocked = self._store.sweep_blocked_tasks()
                        if unblocked:
                            logger.info(f"Blocked sweep recovered {len(unblocked)} stalled tasks: {unblocked}")
                    except Exception as sweep_err:
                        logger.warning(f"Blocked sweep error: {sweep_err}")
                    _last_blocked_sweep = now
                # Periodically sync filesystem state with Neo4j to clear stale .md files
                if now - _last_fs_sync >= FS_SYNC_INTERVAL:
                    try:
                        self._sync_filesystem_state()
                    except Exception as sync_err:
                        logger.warning(f"Filesystem sync error: {sync_err}")
                    _last_fs_sync = now
            except Exception as e:
                logger.error(f"Poll cycle error: {e}")
            await asyncio.sleep(POLL_INTERVAL)

    def _write_heartbeat(self):
        """Write heartbeat file so task-reaper knows we're alive."""
        try:
            hb = {
                "timestamp": datetime.now().isoformat(),
                "pid": os.getpid(),
                "executor_id": self._executor_id,
                "poll_count": self._poll_count,
                "active_tasks": len(self._active_tasks),
                "last_dispatch_at": self._last_dispatch_at,
                "status": "active" if self._active_tasks else "idle",
            }
            self._poll_count += 1
            hb_path = LOGS_DIR / "task-executor-heartbeat.json"
            hb_path.write_text(json.dumps(hb))
        except Exception:
            pass  # Never fail on heartbeat

    def _recover_orphaned_working_tasks(self):
        """Reset WORKING tasks orphaned by previous executor crashes.

        Only resets tasks whose lease has expired — respects the 30-minute
        lease window so in-flight tasks from a recently-crashed executor are
        not re-dispatched while the original subprocess is still running.
        """
        try:
            driver = self._get_driver()
            with driver.session() as session:
                result = session.run("""
                    MATCH (t:Task)
                    WHERE t.status = 'WORKING'
                    AND (t.claimed_by IS NOT NULL)
                    AND (t.lease_expires_at IS NULL OR t.lease_expires_at < datetime())
                    RETURN t.task_id, t.assigned_to, t.claimed_by
                """)
                orphans = []
                for record in result:
                    task_id = record["t.task_id"]
                    orphans.append(task_id)
                    logger.warning(
                        f"ORPHAN_RESET: task {task_id} was WORKING (claimed_by="
                        f"{record['t.claimed_by']}) — resetting to PENDING. "
                        f"If this repeats, executor is crashing during Phase 1."
                    )
                    session.run("""
                        MATCH (t:Task {task_id: $tid, status: 'WORKING'})
                        SET t.status = 'PENDING',
                            t.claimed_by = null,
                            t.retry_count = CASE WHEN t.retry_count IS NOT NULL
                                THEN t.retry_count ELSE 0 END
                    """, tid=task_id)
                if orphans:
                    logger.info(f"Recovered {len(orphans)} orphaned WORKING tasks: {orphans}")
                    for tid in orphans:
                        emit_event(self._get_driver(), "ORPHAN_RECOVERED",
                                   tid, "", executor_id=self._executor_id)
        except Exception as e:
            logger.warning(f"Orphan recovery failed: {e}")

    async def _poll_and_dispatch(self):
        """Single poll cycle: process spawn queue then claim tasks per agent."""
        await self._process_spawn_queue()

        for agent in self._agents:
            # Circuit breaker gate
            cb_status = self._cb.check_agent(agent)
            if not cb_status.get("available", True):
                continue

            # Respect concurrency cap — use active_tasks count, not semaphore
            # (semaphore._value is only updated when the async task actually runs,
            # not when create_task() is called, causing over-claiming in one poll cycle)
            if len(self._active_tasks) >= self._concurrency:
                break

            # Attempt to claim a pending task
            try:
                task = self._store.claim_task(agent)
            except Exception as e:
                logger.warning(f"claim_task failed for {agent}: {e}", exc_info=True)
                continue

            if not task:
                continue

            task_id = task.get("task_id", "")
            if task_id in self._active_tasks:
                continue  # Already running

            self._active_tasks.add(task_id)
            self._active_task_epochs[task_id] = task.get("claim_epoch", 0)
            self._last_dispatch_at = datetime.now().isoformat()
            asyncio.create_task(self._execute_and_cleanup(task))

    async def _execute_and_cleanup(self, task: dict):
        """Semaphore wrapper: acquire → execute → remove from active set."""
        task_id = task.get("task_id", "")
        try:
            async with self._semaphore:
                await self._execute_inner(task)
        except Exception as e:
            logger.error(f"Unhandled error in task {task_id}: {e}")
        finally:
            self._active_tasks.discard(task_id)
            self._active_task_epochs.pop(task_id, None)

    async def _execute_inner(self, task: dict):
        """Full execution pipeline: session → sanitize → run → verify → persist."""
        task_id = task["task_id"]
        agent = task.get("assigned_to", task.get("agent", "unknown"))
        claim_epoch = task.get("claim_epoch", 0)
        priority = task.get("priority", "normal")
        skill_hint = task.get("skill_hint", "")

        # 0. Triage gate — capture baseline byte count at claim time
        triage_file: Optional[Path] = None
        is_triage = False
        triage_baseline: Optional[int] = None
        try:
            triage_file = _find_triage_task_file(agent, task_id)
            is_triage = _is_triage_task(task, triage_file)
            if is_triage and triage_file:
                triage_baseline = os.path.getsize(triage_file)
                if _update_frontmatter_key(
                    triage_file, "triage_baseline_bytes", str(triage_baseline)
                ):
                    logger.info(
                        f"[triage-gate] baseline={triage_baseline}B for {task_id}"
                    )
                else:
                    logger.warning(
                        f"[triage-gate] failed to write baseline for {task_id}"
                    )
        except Exception as _tg_err:
            logger.warning(
                f"[triage-gate] baseline capture error for {task_id}: {_tg_err}"
            )

        emit_event(
            self._get_driver(), "TASK_CLAIMED", task_id, agent,
            executor_id=self._executor_id,
        )
        logger.info(
            f"Executing {task_id} on {agent} (priority={priority})"
        )

        # 1. Session cleanup — single unified pass
        session_state = await asyncio.to_thread(
            self._session_mgr.prepare, agent
        )
        if not session_state.clean:
            emit_session_reset(
                self._get_driver(), task_id, agent,
                executor_id=self._executor_id,
                session_action=session_state.reason,
            )
            logger.info(f"Session reset for {agent}: {session_state.reason}")

        # 1b. Model guard: kimi-k2.5 ignores skill routing directives.
        # If the agent has a skill_hint and session drift was detected to kimi,
        # the session was already archived by prepare(). But also force a reset
        # if the agent's *configured* model is kimi (backup mode).
        if skill_hint and not session_state.clean and "kimi" in session_state.reason.lower():
            logger.warning(
                f"Model guard: {agent} drifted to kimi with skill_hint={skill_hint} "
                f"— session archived, will use primary model"
            )

        # 2. Sanitize task body
        raw_body = task.get("prompt", task.get("body", task.get("title", "")))

        # Inject prior phase context for pipeline tasks that go through Claude
        if task.get("source", "").startswith("pipeline"):
            phase_context = self._resolve_phase_context(task)
            if phase_context:
                raw_body = phase_context + "\n\n---\n\n" + raw_body

        sanitized = self._sanitizer.sanitize(raw_body)
        if not sanitized.safe:
            # HARD REJECT on prompt-injection signals. Escape hatch:
            #   KURULTAI_SANITIZER_BYPASS=1  — operator override (logs loudly).
            # Rationale: warning-only was the pre-existing behaviour, which let
            # injected instructions reach the LLM. False positives are rare
            # because INJECTION_PATTERNS are multi-word phrases.
            threats = sanitized.threats_detected
            bypass = os.environ.get("KURULTAI_SANITIZER_BYPASS") == "1"
            if bypass:
                logger.error(
                    "SANITIZER_BYPASS active for %s — threats=%s",
                    task_id, threats,
                )
                emit_event(
                    self._get_driver(), "PROMPT_INJECTION_BYPASSED", task_id, agent,
                    executor_id=self._executor_id,
                    threats=str(threats)[:500],
                )
            else:
                logger.error(
                    "Hard-reject for %s — injection threats: %s", task_id, threats,
                )
                reject_reason = f"prompt_injection_detected: {threats[:3]}"
                emit_event(
                    self._get_driver(), "PROMPT_INJECTION_BLOCKED", task_id, agent,
                    executor_id=self._executor_id,
                    threats=str(threats)[:500],
                )
                try:
                    self._store.fail_task(
                        task_id, claim_epoch,
                        error_class="prompt_injection",
                        error_msg=reject_reason[:500],
                        is_transient=False,
                        output_snippet="",
                    )
                except Exception as e:
                    logger.warning(
                        "fail_task failed while rejecting %s: %s", task_id, e,
                    )
                    self._wal.buffer(
                        "MATCH (t:Task {task_id: $tid, status: 'WORKING'}) "
                        "SET t.status = 'FAILED', t.updated_at = datetime()",
                        {"tid": task_id},
                    )
                emit_event(
                    self._get_driver(), "TASK_FAILED_PERMANENT", task_id, agent,
                    executor_id=self._executor_id,
                    error_category="prompt_injection",
                    error_msg=reject_reason[:200],
                )
                self._cb.record_result(agent, False, task_id)
                self._rename_task_file(agent, task_id, ".failed.md")
                self._write_ledger(
                    "TASK_FAILED_PERMANENT", task_id, agent,
                    error=reject_reason[:200],
                    error_class="prompt_injection",
                )
                return
        # 2b. Write .executing.md sentinel NOW — before Phase 1 (prompt optimization
        # takes up to 120s). If the executor crashes during Phase 1 the file-based
        # re-dispatch guard sees .executing.md and skips the task, preventing
        # double-execution when the next executor starts and resets Neo4j status.
        # Pipeline tasks skip Phase 1 but still need the sentinel.
        self._rename_task_file(agent, task_id, ".executing.md")

        # 2c. Two-phase prompt: try optimized, fallback to simple
        # Skip optimization for pipeline tasks (deterministic scripts)
        if task.get("source", "").startswith("pipeline"):
            optimized = None
        else:
            optimized = await self._generate_optimized_prompt(
                agent, sanitized.sanitized, task
            )
        if optimized:
            prompt = optimized
            emit_event(
                self._get_driver(), "PROMPT_OPTIMIZED", task_id, agent,
                executor_id=self._executor_id,
                prompt_len=len(optimized),
            )
            # Persist optimized prompt on the Task node for dashboard display
            try:
                with self._get_driver().session() as sess:
                    sess.run(
                        "MATCH (t:Task {task_id: $tid}) "
                        "SET t.optimized_prompt = $prompt",
                        tid=task_id, prompt=optimized[:8000],
                    )
            except Exception as e:
                logger.debug(f"Failed to persist optimized prompt: {e}")
        else:
            prompt = self._build_prompt(agent, sanitized.sanitized, task)
            emit_event(
                self._get_driver(), "PROMPT_FALLBACK", task_id, agent,
                executor_id=self._executor_id,
            )

        # 2c. Worktree isolation — detect project, create worktree, rewrite paths
        worktree_path = None
        project_config = None
        project_config = self._worktree_mgr.detect_project(prompt)
        if project_config:
            worktree_path = await self._worktree_mgr.create_worktree(
                agent, project_config, task_id
            )
            if worktree_path:
                prompt = self._worktree_mgr.rewrite_prompt(
                    prompt, project_config["root"], worktree_path
                )
                emit_event(
                    self._get_driver(), "WORKTREE_CREATED", task_id, agent,
                    executor_id=self._executor_id,
                    project=project_config["name"],
                    worktree_path=str(worktree_path),
                )
                logger.info(f"Worktree for {task_id}: {worktree_path}")
            else:
                logger.warning(
                    f"Worktree creation failed for {task_id}, "
                    f"falling back to in-place editing"
                )

        # 3. Build execution environment and run
        # Detect pipeline tasks before the branch so we can pass skip_resolution below.
        # Use the ORIGINAL task prompt (not worktree-rewritten) for script detection —
        # worktree rewrite changes the path prefix but the python3 command stays the same.
        # Using the rewritten path would still match _SCRIPT_RE but the script won't exist
        # in the worktree (scripts aren't git-tracked), causing exit:127 fallbacks.
        _original_task_body = task.get("prompt", task.get("body", task.get("title", "")))
        is_pipeline = self._is_direct_script(task, _original_task_body)
        if is_pipeline:
            # Direct script execution for pipeline tasks — bypass Claude agent.
            # Use original task body (not worktree-rewritten) so scripts run from their
            # actual location; scripts aren't git-tracked and don't exist in worktrees.
            run_result = await self._execute_direct_script(task, _original_task_body)
            emit_event(
                self._get_driver(), "PIPELINE_SCRIPT_EXECUTED", task_id, agent,
                executor_id=self._executor_id,
                script=_original_task_body.split()[1] if len(_original_task_body.split()) > 1 else "unknown",
                exit_code=run_result.return_code,
                duration_s=run_result.duration_s,
            )
        else:
            env = build_agent_env(agent)

            # 4. Execute — sentinel already written at step 2b above.
            emit_event(
                self._get_driver(), "TASK_EXECUTING", task_id, agent,
                executor_id=self._executor_id,
                model=env.get("ANTHROPIC_MODEL", "default"),
            )

            timeout = self._compute_timeout(priority, skill_hint)

            # Computer Use exclusivity — acquire lock if task needs GUI access
            _needs_cu = self._requires_computer_use(task)
            _cu_acquired = False
            if _needs_cu:
                logger.info("Task requires Computer Use — acquiring exclusive lock (agent=%s)", agent)
                try:
                    await asyncio.wait_for(
                        self._computer_use_lock.acquire(),
                        timeout=CU_LOCK_TIMEOUT,
                    )
                    _cu_acquired = True
                    logger.info("Computer Use lock acquired (agent=%s)", agent)
                except asyncio.TimeoutError:
                    logger.warning(
                        "Computer Use lock timeout after %ds — proceeding anyway (agent=%s)",
                        CU_LOCK_TIMEOUT, agent,
                    )

            try:
                run_result = await self._runner.run(
                    agent, prompt, env,
                    timeout=timeout,
                    model=task.get("model"),
                )
            finally:
                if _cu_acquired:
                    self._computer_use_lock.release()
                    logger.info("Computer Use lock released (agent=%s)", agent)

        # 5. Verify result — THE GATE
        # Direct pipeline scripts AND pipeline LLM tasks (e.g. vote tasks) are both
        # exempt from the ## Resolution requirement: their outputs are structured data
        # consumed by downstream parsers, not human-readable completion reports.
        skip_res = is_pipeline or task.get("source", "").startswith("pipeline")
        passed, reason = verify_result(run_result, skip_resolution=skip_res)

        # 5b. Model fallback on rate-limit or auth failure
        if not passed and reason in (
            "error_in_output:rate_limited",
            "error_in_output:auth_failure",
        ):
            if agent != "tolui":  # tolui uses abliterated model only
                emit_event(
                    self._get_driver(), "MODEL_FALLBACK", task_id, agent,
                    model=run_result.model,
                    fallback_model="claude-sonnet-4-6",
                )
                logger.info(f"Fallback to claude-sonnet-4-6 for {task_id}")
                run_result = await self._runner.run(
                    agent, prompt, env,
                    timeout=timeout,
                    model="claude-sonnet-4-6",
                )
                passed, reason = verify_result(run_result, skip_resolution=skip_res)
                if passed:
                    emit_event(
                        self._get_driver(), "MODEL_FALLBACK_SUCCESS",
                        task_id, agent,
                    )
                else:
                    emit_event(
                        self._get_driver(), "MODEL_FALLBACK_FAILED",
                        task_id, agent,
                        error_msg=reason,
                    )

        # 5c. Delivery gate — for tasks that require external message delivery
        #     Read the agent's workspace task file and verify a delivery receipt.
        #     This runs AFTER verify_result() so a task that fails structurally
        #     won't be double-penalized by delivery failure.
        if passed:
            delivery_spec = classify_delivery_task(task)
            if delivery_spec:
                workspace_dir = AGENTS_DIR / agent / "workspace"
                # Try common naming patterns agents use.
                # IMPORTANT: _post_completion writes to {task_id}.result.md
                # (without "task-" prefix). The legacy candidates below remain
                # for backwards-compat with older gate-passed files.
                candidate_names = [
                    f"{task_id}.result.md",            # primary: written by _post_completion
                    f"task-{task_id}.done.md",         # legacy: old gate-passed format
                    f"task-{task_id}.gate-passed.done.md",
                    f"task-{task_id}.md",
                ]
                workspace_content = ""
                for name in candidate_names:
                    candidate = workspace_dir / name
                    if candidate.exists():
                        try:
                            workspace_content = candidate.read_text(encoding="utf-8", errors="replace")
                        except OSError:
                            pass
                        break

                if workspace_content:
                    delivery_passed, delivery_reason = verify_delivery(
                        workspace_content, delivery_spec.recipient
                    )
                else:
                    delivery_passed = False
                    delivery_reason = f"workspace file not found for task {task_id}"

                if not delivery_passed:
                    passed = False
                    reason = f"delivery_not_verified:{delivery_reason}"
                    emit_event(
                        self._get_driver(), "DELIVERY_UNVERIFIED", task_id, agent,
                        error_msg=delivery_reason,
                        channel=delivery_spec.channel,
                        recipient=delivery_spec.recipient,
                    )
                    logger.warning(
                        f"Delivery gate FAILED for {task_id}: {delivery_reason}"
                    )
                else:
                    emit_event(
                        self._get_driver(), "DELIVERY_VERIFIED", task_id, agent,
                        channel=delivery_spec.channel,
                        recipient=delivery_spec.recipient,
                    )
                    logger.info(
                        f"Delivery gate PASSED for {task_id}: {delivery_reason}"
                    )
                    # Stamp delivery metadata on the Task node itself
                    try:
                        with self._get_driver().session() as _s:
                            _s.run(
                                """
                                MATCH (t:Task {task_id: $id})
                                SET t.delivery_verified = true,
                                    t.delivery_channel = $channel,
                                    t.delivery_recipient = $recipient,
                                    t.delivery_ts = datetime()
                                """,
                                id=task_id,
                                channel=delivery_spec.channel,
                                recipient=delivery_spec.recipient,
                            )
                    except Exception as _e:
                        logger.warning(f"Failed to stamp delivery props on {task_id}: {_e}")

        # 5d. Triage gate — require investigation findings appended to task file.
        # Runs only for triage tasks after the verify_result and delivery gates pass.
        # Gate fails if the task file has not grown since claim time.
        if passed and is_triage:
            # Opt-out: check task dict property or embedded frontmatter in prompt
            optout = str(task.get("completion_gate_optout", "")).lower() in ("true", "1", "yes")
            if not optout:
                optout = bool(re.search(
                    r"^completion_gate_optout:\s*true",
                    task.get("prompt", ""),
                    re.MULTILINE | re.IGNORECASE,
                ))
            if optout:
                logger.info(
                    f"[triage-gate] opt-out — bypassing size check for {task_id}"
                )
            else:
                gate_blocked = True
                if triage_file and triage_file.exists():
                    try:
                        current_size = os.path.getsize(triage_file)
                        baseline = triage_baseline
                        if baseline is None:
                            baseline = _read_frontmatter_int(
                                triage_file, "triage_baseline_bytes"
                            )
                        if baseline is not None and current_size > baseline:
                            gate_blocked = False
                            logger.info(
                                f"[triage-gate] PASSED for {task_id}: "
                                f"{baseline}B → {current_size}B"
                            )
                    except OSError as _sz_err:
                        logger.warning(
                            f"[triage-gate] size check failed for {task_id}: {_sz_err}"
                        )
                if gate_blocked:
                    passed = False
                    reason = "triage_no_findings"
                    logger.warning(
                        f"[triage-gate] BLOCKED {task_id}: "
                        "Triage task requires investigation findings before marking done. "
                        "Append findings to task file first."
                    )
                    emit_event(
                        self._get_driver(), "TRIAGE_GATE_BLOCKED", task_id, agent,
                        executor_id=self._executor_id,
                    )

        # 6. Persist terminal state
        if passed:
            try:
                ok, msg = self._store.complete_task(
                    task_id, claim_epoch,
                    text=run_result.content[:8000],
                    problem=task.get("title", ""),
                    solution=run_result.content[:2000],
                    rationale="",
                    output_lines=run_result.content.count("\n"),
                    duration_s=run_result.duration_s,
                )
            except Exception as e:
                ok, msg = False, str(e)

            if ok:
                emit_event(
                    self._get_driver(), "TASK_COMPLETED", task_id, agent,
                    executor_id=self._executor_id,
                    duration_s=run_result.duration_s,
                    output_lines=run_result.content.count("\n"),
                    model=run_result.model,
                )
                self._cb.record_result(agent, True, task_id)
                self._rename_task_file(agent, task_id, ".done.md")
                await self._post_completion(task, run_result)
                # Deploy pipeline (only if worktree was used)
                if worktree_path and project_config:
                    try:
                        await self._post_deploy(
                            task, run_result, worktree_path, project_config
                        )
                    except Exception as e:
                        logger.warning(
                            f"Post-deploy failed for {task_id}: {e}"
                        )
                        emit_event(
                            self._get_driver(), "DEPLOY_FAILED",
                            task_id, agent,
                            error=str(e)[:200],
                        )
                    finally:
                        # Always remove worktree + branch to prevent accumulation
                        await self._worktree_mgr.cleanup_worktree(
                            project_config["root"],
                            worktree_path,
                            f"task-{task_id[:12]}",
                        )
                self._write_ledger(
                    "TASK_COMPLETED", task_id, agent,
                    duration_s=run_result.duration_s,
                )
                logger.info(
                    f"COMPLETED {task_id} in {run_result.duration_s:.0f}s"
                )
                # Check if implementation was partial despite "success"
                await self._check_continuation(task, run_result, passed=True)
            else:
                # CAS failed or Neo4j unavailable — buffer to WAL
                self._wal.buffer(
                    "MATCH (t:Task {task_id: $tid, status: 'WORKING'}) "
                    "SET t.status = 'COMPLETED', t.completed_at = datetime() "
                    "CREATE (t)-[:HAS_OUTPUT]->(:TaskOutput {text: $text, "
                    "content: $text, output_lines: $lines, duration_s: $dur, "
                    "created_at: datetime()})",
                    {
                        "tid": task_id,
                        "text": run_result.content[:8000],
                        "lines": run_result.content.count("\n"),
                        "dur": run_result.duration_s,
                    },
                )
                # Still rename the filesystem file — WAL will persist Neo4j later
                self._rename_task_file(agent, task_id, ".done.md")
                logger.warning(
                    f"complete_task failed for {task_id}: {msg} — buffered to WAL"
                )
        else:
            # Failed the completion gate
            if "error_in_output" in reason:
                emit_event(
                    self._get_driver(), "FALSE_COMPLETION_BLOCKED", task_id, agent,
                    reason=reason,
                    executor_id=self._executor_id,
                )

            # Classify the failure mode
            error_class, is_transient = classify_failure(
                run_result.return_code,
                stderr="",
                stdout=run_result.content[:1000],
            )

            try:
                ok, new_status = self._store.fail_task(
                    task_id, claim_epoch,
                    error_class=error_class,
                    error_msg=reason[:500],
                    is_transient=is_transient,
                    output_snippet=run_result.content[:500],
                )
            except Exception as e:
                ok = False
                self._wal.buffer(
                    "MATCH (t:Task {task_id: $tid, status: 'WORKING'}) "
                    "SET t.status = 'FAILED', t.updated_at = datetime()",
                    {"tid": task_id},
                )

            event_type = "TASK_FAILED" if is_transient else "TASK_FAILED_PERMANENT"
            emit_event(
                self._get_driver(), event_type, task_id, agent,
                executor_id=self._executor_id,
                error_category=error_class,
                error_msg=reason[:200],
            )
            self._cb.record_result(agent, False, task_id)
            if not is_transient:
                self._rename_task_file(agent, task_id, ".failed.md")
            self._write_ledger(
                event_type, task_id, agent,
                error=reason[:200],
                error_class=error_class,
            )
            logger.info(
                f"FAILED {task_id}: {reason} "
                f"(class={error_class}, transient={is_transient})"
            )

            # Stall escalation gate — if a task has been stall-detected N times,
            # stop re-queuing it and escalate to STALL_ESCALATED for manual review.
            if reason == "stall_detected":
                await self._maybe_escalate_stall(task_id, agent, task)

            # Check if agent created a plan before failing/timing out
            await self._check_continuation(task, run_result, passed=False)

    # -------------------------------------------------------------------
    # Stall Escalation — break infinite stall-triage loops
    # -------------------------------------------------------------------

    async def _maybe_escalate_stall(
        self, task_id: str, agent: str, task: dict
    ):
        """Increment stall_count on the task and escalate if threshold is reached.

        Called only when verify_result() returns reason="stall_detected".

        Flow:
          1. Increment t.stall_count on the Neo4j Task node (atomic)
          2. If stall_count >= STALL_ESCALATION_THRESHOLD:
             a. Set status = 'STALL_ESCALATED' (terminal — won't be re-claimed)
             b. Emit STALL_ESCALATED event node (Neo4j)
             c. Append entry to ~/.openclaw/logs/stall-escalations.jsonl (JSONL ledger)
             d. Send Kublai notification for manual review
        """
        try:
            driver = self._get_driver()
            with driver.session() as session:
                result = session.run(
                    """
                    MATCH (t:Task {task_id: $tid})
                    SET t.stall_count = CASE
                        WHEN t.stall_count IS NULL THEN 1
                        ELSE t.stall_count + 1
                    END
                    RETURN t.stall_count AS stall_count, t.status AS status
                    """,
                    tid=task_id,
                )
                record = result.single()
                if not record:
                    logger.warning(f"stall escalation: task {task_id} not found in Neo4j")
                    return
                stall_count = record["stall_count"]
                current_status = record["status"]
        except Exception as e:
            logger.warning(f"stall escalation: Neo4j increment failed for {task_id}: {e}")
            return

        logger.info(
            f"Stall count for {task_id}: {stall_count}/{STALL_ESCALATION_THRESHOLD}"
        )

        if stall_count < STALL_ESCALATION_THRESHOLD:
            return  # Not yet — let the normal retry / re-queue path handle it

        # Threshold reached — escalate
        logger.warning(
            f"STALL_ESCALATED: {task_id} has stalled {stall_count} times "
            f"(threshold={STALL_ESCALATION_THRESHOLD}), escalating for manual review"
        )

        # 1. Set terminal status in Neo4j
        try:
            driver = self._get_driver()
            with driver.session() as session:
                session.run(
                    """
                    MATCH (t:Task {task_id: $tid})
                    WHERE t.status <> 'STALL_ESCALATED'
                    SET t.status = 'STALL_ESCALATED',
                        t.escalated_at = datetime(),
                        t.stall_count = $stall_count
                    """,
                    tid=task_id,
                    stall_count=stall_count,
                )
        except Exception as e:
            logger.warning(f"stall escalation: status update failed for {task_id}: {e}")
            self._wal.buffer(
                "MATCH (t:Task {task_id: $tid}) "
                "SET t.status = 'STALL_ESCALATED', t.escalated_at = datetime(), "
                "t.stall_count = $stall_count",
                {"tid": task_id, "stall_count": stall_count},
            )

        # 2. Emit Neo4j event node (dual-write observability)
        emit_event(
            self._get_driver(), "STALL_ESCALATED", task_id, agent,
            executor_id=self._executor_id,
            stall_count=stall_count,
            threshold=STALL_ESCALATION_THRESHOLD,
        )

        # 3. Write to JSONL stall-escalation ledger (dual-write observability)
        escalation_entry = {
            "event": "STALL_ESCALATED",
            "ts": datetime.now().isoformat(),
            "task_id": task_id,
            "agent": agent,
            "stall_count": stall_count,
            "threshold": STALL_ESCALATION_THRESHOLD,
            "title": task.get("title", ""),
            "priority": task.get("priority", "unknown"),
        }
        try:
            STALL_ESCALATION_LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(STALL_ESCALATION_LOG, "a") as f:
                f.write(json.dumps(escalation_entry) + "\n")
        except Exception as e:
            logger.warning(f"stall escalation: ledger write failed for {task_id}: {e}")

        # Also write to the main task ledger for unified observability
        self._write_ledger(
            "STALL_ESCALATED", task_id, agent,
            stall_count=stall_count,
            threshold=STALL_ESCALATION_THRESHOLD,
        )

        # 4. Notify Kublai for manual review
        try:
            nqueue = NotificationQueue()
            kublai_number = os.environ.get("KUBLAI_SIGNAL_NUMBER", "+19194133445")
            msg = (
                f"[STALL_ESCALATED] Task {task_id} stalled {stall_count} times\n"
                f"Agent: {agent}\n"
                f"Title: {task.get('title', 'unknown')}\n"
                f"Priority: {task.get('priority', 'unknown')}\n"
                f"Manual review required — task status set to STALL_ESCALATED\n"
                f"https://the.kurult.ai/r/{task_id}"
            )
            nqueue.enqueue(task_id, agent, kublai_number, msg)
            logger.info(f"Kublai notification enqueued for stall escalation: {task_id}")
        except Exception as e:
            logger.warning(f"stall escalation: Kublai notification failed for {task_id}: {e}")

    # -------------------------------------------------------------------
    # Continuation Detection — create follow-up tasks for incomplete work
    # -------------------------------------------------------------------

    async def _check_continuation(
        self, task: dict, run_result: RunResult, passed: bool
    ):
        """Detect incomplete work and create a continuation task.

        Checks for:
        1. Plan file created but implementation not completed (timeout mid-implement)
        2. Output contains "plan saved to" but no completion signal
        3. Task failed/timed out after producing a plan

        Creates a follow-up task assigned to the same agent with
        skill_hint=/horde-implement pointing at the saved plan.
        """
        agent = task.get("assigned_to", task.get("agent", ""))
        task_id = task["task_id"]
        output = run_result.content or ""

        # Look for plan files in the agent's workspace created in the last 30 min
        import glob
        workspace = AGENTS_DIR / agent / "workspace"
        plan_candidates = []

        # Check docs/plans/ in known project directories
        from kurultai_paths import PROJECT_REGISTRY
        for project_root in PROJECT_REGISTRY:
            plans_dir = Path(project_root) / "docs" / "plans"
            if plans_dir.exists():
                for p in plans_dir.glob("*.md"):
                    age = time.time() - p.stat().st_mtime
                    if age < 1800:  # created in last 30 min
                        plan_candidates.append(p)

        # Also check the plan mode plan file directory
        claude_plans = Path.home() / ".claude" / "plans"
        if claude_plans.exists():
            for p in claude_plans.glob("*.md"):
                age = time.time() - p.stat().st_mtime
                if age < 1800:
                    plan_candidates.append(p)

        # Also scan output for explicit "plan saved to" references
        import re
        plan_refs = re.findall(
            r'(?:plan saved|saved plan|plan at|wrote plan)[:\s]+[`"]?([^\s`"]+\.md)',
            output, re.IGNORECASE
        )
        for ref in plan_refs:
            p = Path(ref)
            if p.exists() and p not in plan_candidates:
                plan_candidates.append(p)

        if not plan_candidates:
            return  # No plan found, nothing to continue

        # Pick the most recently modified plan
        plan_file = max(plan_candidates, key=lambda p: p.stat().st_mtime)

        # Check if the task actually completed the implementation
        # Signals that implementation finished:
        completion_signals = [
            "all phases complete",
            "implementation complete",
            "all exit criteria",
            "horde-implement.*complete",
            "## Resolution",
        ]
        impl_done = any(
            re.search(sig, output, re.IGNORECASE)
            for sig in completion_signals
        )

        if impl_done and passed:
            return  # Implementation finished successfully, no continuation needed

        # Create continuation task
        continuation_title = f"Continue: {task.get('title', task_id)[:50]}"
        continuation_body = (
            f"## Continuation Task\n\n"
            f"The previous task `{task_id}` created a plan but did not complete implementation.\n"
            f"{'It timed out or failed.' if not passed else 'It completed planning but implementation is partial.'}\n\n"
            f"**Plan file:** `{plan_file}`\n\n"
            f"## Instructions\n\n"
            f"1. Read the plan at `{plan_file}`\n"
            f"2. Check which phases are already completed (look for existing files/changes)\n"
            f"3. Invoke `/horde-implement` to continue execution from where it left off\n"
        )

        try:
            self._store.create_task(
                task_id=generate_task_id(),
                title=continuation_title,
                prompt=continuation_body,
                assigned_to=agent,
                priority=task.get("priority", "normal"),
                domain="implementation",
                skill_hint="/horde-implement",
                source="continuation",
                parent_id=task_id,
            )
            emit_event(
                self._get_driver(), "TASK_CONTINUATION", task_id, agent,
                plan_file=str(plan_file),
                continuation_reason="timeout" if not passed else "partial_implementation",
            )
            self._write_ledger(
                "TASK_CONTINUATION", task_id, agent,
                plan_file=str(plan_file),
            )
            logger.info(
                f"Continuation task created for {task_id} → plan: {plan_file}"
            )
        except Exception as e:
            logger.warning(f"Failed to create continuation task: {e}")

    def _resolve_phase_context(self, task: dict) -> str:
        """Fetch outputs from all dependency tasks for context injection."""
        task_id = task.get("task_id", "")
        if not task_id:
            return ""
        try:
            with self._get_driver().session() as sess:
                result = sess.run("""
                    MATCH (t:Task {task_id: $tid})-[:DEPENDS_ON]->(dep:Task)
                    OPTIONAL MATCH (dep)-[:HAS_OUTPUT]->(o:TaskOutput)
                    RETURN dep.task_id AS dep_id, dep.title AS title,
                           dep.assigned_to AS agent, dep.phase AS phase,
                           o.text AS text, o.solution AS solution
                    ORDER BY dep.phase, dep.assigned_to
                """, tid=task_id)

                sections = []
                total_len = 0
                MAX_CONTEXT = 8000

                for rec in result:
                    content = rec["text"] or rec["solution"] or ""
                    if not content:
                        continue
                    section = f"## {rec['title']} ({rec['agent']})\n{content}\n"
                    if total_len + len(section) > MAX_CONTEXT:
                        break
                    sections.append(section)
                    total_len += len(section)

                if sections:
                    return "# Prior Phase Outputs\n\n" + "\n".join(sections)
        except Exception as e:
            logger.debug(f"_resolve_phase_context failed for {task_id}: {e}")
        return ""

    def _is_direct_script(self, task: dict, prompt: str) -> bool:
        """Return True if this pipeline task should run as a direct subprocess."""
        return (task.get("source", "").startswith("pipeline")
                and bool(_SCRIPT_RE.match(prompt.strip())))

    async def _execute_direct_script(self, task: dict, prompt: str) -> RunResult:
        """Run a python3 pipeline script directly instead of via Claude agent."""
        parts = shlex.split(prompt.strip())
        script_name = parts[1] if len(parts) > 1 else ""
        script_path = SCRIPTS_DIR / script_name
        if not script_path.exists():
            return RunResult(False, f"Script not found: {script_path}", 127, 0.0, "direct", False)

        timeout = task.get("timeout_s", 300)
        phase_context = self._resolve_phase_context(task)
        env = {**os.environ,
               "PIPELINE_ID": task.get("pipeline_id", ""),
               "PIPELINE_CONTEXT": phase_context[:16000] if phase_context else ""}
        start = time.time()

        proc = await asyncio.create_subprocess_exec(
            *parts, cwd=str(SCRIPTS_DIR),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return RunResult(False, "Script timeout", -1, time.time() - start, "direct", True)

        content = stdout.decode("utf-8", errors="replace")
        if stderr:
            content += "\n--- STDERR ---\n" + stderr.decode("utf-8", errors="replace")
        return RunResult(proc.returncode == 0, content, proc.returncode,
                         time.time() - start, "direct", False)

    def _build_prompt(self, agent: str, task_body: str, task: dict) -> str:
        """Build execution prompt with optional skill preamble and agent memory.

        Args:
            agent:     Agent identifier for memory lookup.
            task_body: Sanitized task body text.
            task:      Full task dict (may contain skill_hint).

        Returns:
            Assembled prompt string ready to pass to the claude agent.
        """
        # Pipeline tasks get raw prompt — no horde-plan/implement wrapper
        if task.get("source", "").startswith("pipeline"):
            return task_body

        skill_hint = task.get("skill_hint", "")
        sections: list[str] = []

        if skill_hint:
            skill_name = skill_hint.lstrip("/")
            sections.append(
                f"## MANDATORY: Invoke Skill '{skill_name}' Before Any Work\n"
                f"You MUST call: Skill: {skill_hint}\n"
                f"Complete all skill phases before marking this task done.\n---\n"
            )

        sections.append(task_body)

        memory = self._load_agent_memory(agent)
        if memory:
            sections.append(f"\n## Recent Context\n{memory}")

        sections.append(
            "\n## Execution Protocol (mandatory)\n"
            "**Step 1 — Plan (MUST run in plan mode):**\n"
            "1. Call `EnterPlanMode` FIRST — you must be in plan mode before planning\n"
            "2. Then invoke `Skill(\"/horde-plan\")` to create a structured execution plan\n"
            "3. Read relevant files, understand the scope, produce a phased plan with exit criteria\n"
            "4. The /horde-plan skill will call `ExitPlanMode` when the plan is complete\n"
            "5. The plan will be saved to disk automatically\n\n"
            "**Step 2 — Implement:**\n"
            "Invoke `Skill(\"/horde-implement\")` to execute the saved plan. "
            "Work through each phase, verify exit criteria, and confirm completion.\n\n"
            "**CRITICAL:** Do NOT skip Step 1. Do NOT start coding before the plan is complete. "
            "Do NOT call EnterPlanMode and ExitPlanMode without invoking /horde-plan in between."
        )
        return "\n".join(sections)

    def _load_agent_memory(self, agent: str) -> str:
        """Load the most recently modified memory file for an agent.

        Returns:
            Up to 2000 characters of the latest memory file, or "" if none.
        """
        memory_dir = AGENTS_DIR / agent / "memory"
        if not memory_dir.exists():
            return ""
        try:
            files = sorted(
                memory_dir.glob("*.md"),
                key=os.path.getmtime,
                reverse=True,
            )
            if files:
                return files[0].read_text()[:2000]
        except OSError:
            pass
        return ""

    # ------------------------------------------------------------------
    # Two-phase prompt generation (Phase 1: optimize, Phase 2: execute)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_optimized_prompt(raw_output: str) -> Optional[str]:
        """Extract optimized prompt from Phase 1 output using delimiters."""
        start = raw_output.find(PROMPT_START)
        end = raw_output.find(PROMPT_END)
        if start == -1 or end == -1 or end <= start:
            return None
        return raw_output[start + len(PROMPT_START):end].strip()

    def _should_optimize(self, task_body: str, priority: str) -> bool:
        """Decide whether to run Phase 1 prompt optimization.

        Skip for critical-priority tasks (need to start NOW) and trivial tasks
        where the overhead of a prompt generation session isn't worth it.
        """
        if priority == "critical":
            return False
        try:
            sys.path.insert(0, os.path.expanduser("~/.claude/skills/horde-prompt"))
            from prompts import score_task_complexity
            return score_task_complexity(task_body) >= PROMPT_COMPLEXITY_THRESHOLD
        except (ImportError, Exception):
            return True  # default to optimizing if we can't score

    def _build_meta_prompt(
        self, agent: str, task_body: str, task: dict, kb_content: str
    ) -> str:
        """Build the meta-prompt for Phase 1 (prompt generation).

        Instructs Claude Code to invoke /horde-prompt and output the
        optimized execution prompt between delimiters.
        """
        skill_hint = task.get("skill_hint", "")
        priority = task.get("priority", "normal")
        memory = self._load_agent_memory(agent)

        # Resolve the horde-prompt agent type
        try:
            sys.path.insert(0, os.path.expanduser("~/.claude/skills/horde-prompt"))
            from prompts import resolve_agent_type
            resolved_type = resolve_agent_type(agent, task_body)
        except (ImportError, Exception):
            resolved_type = "general-purpose"

        # Determine token budget
        budget = "standard"
        if priority == "critical":
            budget = "minimal"

        # Skill-specific optimizer directives
        skill_directives = ""
        if skill_hint in ("/suno-clone", "suno-clone"):
            skill_directives = """
## SKILL-SPECIFIC DIRECTIVE: suno-clone
The /suno-clone skill is SELF-CONTAINED. It runs a 5-stage pipeline
(download -> identify -> analyze -> separate -> generate) and produces its own output files.

CRITICAL for the optimized prompt:
1. Do NOT generate a custom "Output Format" section - the skill defines its own
2. Include this step: "After pipeline completes, read claude-translation-prompt.md and use it to refine the draft Suno prompt"
3. The skill outputs Title + Style + Structural Meta Tags - NOT a flat Genre/Mood/BPM list
4. Keep the skill invocation instruction compact (one line, not a full page)
"""

        # Include prior failure context for continuation tasks
        failure_context = ""
        parent_id = task.get("parent_id")
        if parent_id:
            try:
                fail_reason = self._get_fail_reason(parent_id)
                if fail_reason:
                    failure_context = (
                        f"\n## Prior Failure Context\n"
                        f"Previous run ({parent_id}) failed: {fail_reason}\n"
                        f"Avoid repeating this failure mode.\n"
                    )
            except Exception:
                pass

        return f"""You are a prompt optimizer for the Kurultai task execution system.
Generate an optimized execution prompt using the /horde-prompt skill.

## TASK TO OPTIMIZE FOR
---
{task_body}
---

## AGENT: {agent} (horde-prompt type: {resolved_type})
## SKILL HINT: {skill_hint or "none"}
## PRIORITY: {priority}
{skill_directives}
## KNOWLEDGE BASE CONTEXT
The following documentation is from the Kurultai knowledge base.
Use ONLY the facts that are relevant to the TASK above.
Do NOT include irrelevant KB sections in the final prompt.

{kb_content if kb_content else "(no KB docs selected for this task)"}

## AGENT MEMORY (recent context for this agent)
{memory if memory else "(no recent memory)"}
{failure_context}
## INSTRUCTIONS
1. Invoke /horde-prompt with:
   - task: the TASK text above
   - agent_type: {resolved_type}
   - token_budget: {budget}
2. Take the generated prompt and ENHANCE it:
   a. Extract RELEVANT facts from KNOWLEDGE BASE CONTEXT and add them
      as a "## System Knowledge" section. Include specific details
      (schema fields, endpoint paths, config values) the agent will need.
   b. If SKILL HINT is present, prepend a compact skill invocation instruction.
   c. Append AGENT MEMORY as "## Recent Context".
   d. Add the agent-specific execution instruction footer.
3. Output the COMPLETE final prompt between these EXACT delimiters:

{PROMPT_START}
[complete execution prompt here]
{PROMPT_END}

Output NOTHING after the end delimiter."""

    async def _generate_optimized_prompt(
        self, agent: str, task_body: str, task: dict
    ) -> Optional[str]:
        """Phase 1: Spawn claude-agent to generate an optimized prompt.

        Returns the optimized prompt string, or None on failure (triggers
        fallback to the simple _build_prompt path).
        """
        task_id = task.get("task_id", "unknown")

        if not self._should_optimize(task_body, task.get("priority", "normal")):
            logger.info(f"Skipping prompt optimization for {task_id[:8]} (below threshold or critical)")
            return None

        # Select relevant KB docs
        try:
            from kb_selector import select_kb_docs
            kb_hint = task.get("kb_hint")
            kb_content = select_kb_docs(task_body, kb_hint=kb_hint)
        except (ImportError, Exception) as e:
            logger.warning(f"KB selector failed: {e}")
            kb_content = ""

        # Build the meta-prompt
        meta_prompt = self._build_meta_prompt(agent, task_body, task, kb_content)

        # Build environment using the agent's configured model/provider
        # (same as dashboard at the.kurult.ai/sessions — no model override)
        env = build_agent_env(agent)

        # Spawn Phase 1 claude-agent session
        try:
            run_result = await self._runner.run(
                agent, meta_prompt, env,
                timeout=PROMPT_GEN_TIMEOUT,
            )
        except Exception as e:
            logger.warning(f"Phase 1 prompt generation failed for {task_id[:8]}: {e}")
            return None

        if not run_result.success or not run_result.content:
            logger.warning(
                f"Phase 1 returned no content for {task_id[:8]} "
                f"(rc={run_result.return_code}, stall={run_result.stall_detected})"
            )
            return None

        # Extract the optimized prompt from delimiters
        optimized = self._extract_optimized_prompt(run_result.content)
        if not optimized:
            logger.warning(
                f"Phase 1 delimiter extraction failed for {task_id[:8]} "
                f"(output={len(run_result.content)} chars)"
            )
            return None

        logger.info(
            f"Phase 1 prompt generated for {task_id[:8]}: "
            f"{len(optimized)} chars in {run_result.duration_s:.1f}s"
        )
        return optimized

    def _compute_timeout(self, priority: str, skill_hint: str) -> int:
        """Compute effective timeout from priority tier and skill hint.

        Takes the maximum of the priority-based timeout and any skill-specific
        extended timeout defined in SLOW_SKILLS.

        Returns:
            Timeout in seconds.
        """
        priority_timeout = TIMEOUT_BY_PRIORITY.get(priority, CLAUDE_TIMEOUT)
        skill_timeout = SLOW_SKILLS.get(skill_hint, 0) if skill_hint else 0
        return max(priority_timeout, skill_timeout)

    async def _renew_leases(self):
        """Background coroutine: extend Neo4j lease and emit events every 10 minutes."""
        while not self._shutdown:
            await asyncio.sleep(600)
            for task_id, epoch in list(self._active_task_epochs.items()):
                try:
                    self._store.renew_lease(task_id, epoch)
                    emit_event(
                        self._get_driver(), "LEASE_RENEWED", task_id, "",
                        executor_id=self._executor_id,
                    )
                except Exception:
                    pass

    def _rename_task_file(self, agent: str, task_id: str, suffix: str) -> None:
        """Rename a task's .md file to {name}{suffix} to reflect terminal state.

        Keeps filesystem in sync with Neo4j state so queue-depth monitors
        don't count completed/failed tasks as pending.

        Handles two filename conventions:
          - Standard:  {task_id}.md  (UUID-format task_id matches filename)
          - Dispatch:  {priority}-{ts}-{short_id}.md  (task_id is in frontmatter,
                       differs from filename)

        For dispatch-format files, scans the tasks directory for a file whose
        frontmatter contains `task_id: {task_id}`.
        """
        tasks_dir = AGENTS_DIR / agent / "tasks"
        # Fast path: standard naming convention — check both .md and .executing.md sources
        for src_suffix in (".md", ".executing.md"):
            src = tasks_dir / f"{task_id}{src_suffix}"
            if src.exists():
                dst = tasks_dir / f"{task_id}{suffix}"
                if not dst.exists():
                    try:
                        src.rename(dst)
                    except OSError as e:
                        logger.warning(f"Failed to rename task file {src.name} -> {dst.name}: {e}")
                return

        # Slow path: dispatch-format files where task_id is embedded in frontmatter
        if not tasks_dir.exists():
            return
        try:
            needle = f"\ntask_id: {task_id}"
            for f in tasks_dir.iterdir():
                fname = f.name
                if not fname.endswith(".md"):
                    continue
                if any(s in fname for s in (".done.", ".cancelled.", ".failed.", ".pending-gate.")):
                    continue
                try:
                    if needle in f.read_text(encoding="utf-8", errors="replace"):
                        # Use base name only (strip all intermediate suffixes) so
                        # e.g. normal-123.pending-gate.executing.md → normal-123.done.md
                        base = fname.split(".")[0]
                        new_name = base + suffix  # e.g. high-123-abc.done.md
                        dst = tasks_dir / new_name
                        if not dst.exists():
                            f.rename(dst)
                            logger.info(
                                f"Renamed dispatch-format task file {fname} -> {new_name}"
                            )
                        return
                except OSError:
                    continue
        except OSError as e:
            logger.warning(f"Failed to scan tasks dir for {task_id}: {e}")

    def _sync_filesystem_state(self) -> None:
        """Reconcile filesystem task files with Neo4j terminal states.

        Finds .md files that are still named as pending but whose Neo4j status
        is COMPLETED, FAILED, CANCELLED, or STALL_ESCALATED, then renames them
        to the correct terminal suffix (.done.md or .failed.md).

        Runs every FS_SYNC_INTERVAL seconds as a background maintenance pass.
        Prevents phantom queue-depth inflation in routing_audit and other monitors
        that read the filesystem.
        """
        TERMINAL_DONE = frozenset({"COMPLETED", "STALL_ESCALATED"})
        TERMINAL_FAILED = frozenset({"FAILED", "CANCELLED"})
        SKIP_SUFFIXES = (".done.", ".cancelled.", ".failed.", ".executing.", ".pending-gate.")

        driver = self._get_driver()
        if driver is None:
            return

        renamed = 0
        try:
            with driver.session() as sess:
                for agent in self._agents:
                    tasks_dir = AGENTS_DIR / agent / "tasks"
                    if not tasks_dir.exists():
                        continue
                    for f in tasks_dir.iterdir():
                        fname = f.name
                        if not fname.endswith(".md"):
                            continue
                        if any(s in fname for s in SKIP_SUFFIXES):
                            continue
                        # Extract task_id: try frontmatter first, then filename stem
                        content = None
                        tid = None
                        try:
                            content = f.read_text(encoding="utf-8", errors="replace")
                            m = re.search(r"^task_id:\s*(\S+)", content, re.MULTILINE)
                            if m:
                                tid = m.group(1)
                        except OSError:
                            continue
                        if not tid:
                            tid = fname[:-3]  # strip .md

                        rec = sess.run(
                            "MATCH (t:Task {task_id: $tid}) RETURN t.status",
                            tid=tid,
                        ).single()
                        if not rec:
                            continue
                        status = rec[0]
                        if status in TERMINAL_DONE:
                            new_name = fname[:-3] + ".done.md"
                        elif status in TERMINAL_FAILED:
                            new_name = fname[:-3] + ".failed.md"
                        else:
                            continue
                        dst = tasks_dir / new_name
                        if not dst.exists():
                            try:
                                f.rename(dst)
                                renamed += 1
                            except OSError as e:
                                logger.warning(f"fs-sync rename {fname}: {e}")
        except Exception as e:
            logger.warning(f"Filesystem sync pass error: {e}")

        if renamed:
            logger.info(f"Filesystem sync: renamed {renamed} stale task files")

    async def _post_completion(self, task: dict, run_result: RunResult):
        """Write result file after a task completes, then send notification.

        Persists .result.md in the agent's workspace and sends a Signal
        notification directly via signal_send (no subprocess).
        """
        agent = task.get("assigned_to", task.get("agent", ""))
        try:
            # Persist output to workspace
            result_dir = AGENTS_DIR / agent / "workspace"
            result_dir.mkdir(parents=True, exist_ok=True)
            result_file = result_dir / f"{task['task_id']}.result.md"
            header = (
                f"# Task Result: {task.get('title', task['task_id'])}\n\n"
                f"**Task ID:** {task['task_id']}\n"
                f"**Agent:** {agent}\n"
                f"**Duration:** {run_result.duration_s:.0f}s\n\n---\n\n"
            )
            result_file.write_text(header + run_result.content)

            # Send notification directly
            asyncio.create_task(
                self._send_notification(agent, task, run_result.content)
            )
        except Exception as e:
            logger.warning(
                f"Post-completion failed for {task['task_id']}: {e}"
            )

    async def _send_notification(self, agent: str, task: dict,
                                 result_content: str):
        """Send Signal notification directly via signal_send (no subprocess)."""
        import signal_send

        origin_type = task.get('origin_type')
        if origin_type is not None and origin_type != 'human':
            return  # Skip system/cron/agent tasks
        if origin_type is None:
            logger.warning(
                f"origin_type not hydrated for task {task.get('task_id')}, "
                "sending notification anyway"
            )

        notify_target = task.get(
            'notify_target', task.get('origin_initiator', '')
        )
        if not notify_target or not notify_target.startswith('+'):
            return

        title = task.get('title', 'Task')
        body = (result_content or '').strip()
        task_id = task.get('task_id', '')
        message = (
            f"[DONE] {agent}: {title}\n\n"
            f"{body}\n\n"
            f"https://the.kurult.ai/r/{task_id}"
        )

        quote_ts = task.get('origin_message_id')
        quote_author = task.get('origin_initiator') if quote_ts else None

        loop = asyncio.get_running_loop()
        try:
            rc, _ = await loop.run_in_executor(
                None, signal_send.send, notify_target, message,
                quote_ts, quote_author,
            )
            if rc != 0:
                logger.warning(
                    f"Direct send failed for {task_id}, enqueueing fallback"
                )
                self._nqueue.enqueue(task_id, agent, notify_target, message)
        except Exception as e:
            logger.warning(f"Notification error for {task_id}: {e}, enqueueing")
            self._nqueue.enqueue(task_id, agent, notify_target, message)

    # -------------------------------------------------------------------
    # Deploy Pipeline — PR creation from worktree after task completion
    # -------------------------------------------------------------------

    async def _post_deploy(
        self, task: dict, run_result: RunResult,
        worktree_path, project_config: dict,
    ):
        """Create a PR from the worktree branch after successful task completion.

        Pipeline: privilege check → detect changes → diff guard → stage/commit
        → push → PR creation → optional auto-merge.
        """
        agent = task.get("assigned_to", task.get("agent", ""))
        task_id = task["task_id"]
        project_name = project_config["name"]

        # 1. Privilege check
        is_docs = self._is_docs_only_change(worktree_path)
        allowed = project_config.get("allowed_agents", [])
        docs_allowed = project_config.get("docs_agents", [])

        if agent not in allowed and not (is_docs and agent in docs_allowed):
            emit_event(
                self._get_driver(), "DEPLOY_BLOCKED", task_id, agent,
                project=project_name,
                reason=f"agent {agent} not in allowed_agents",
            )
            self._write_ledger("DEPLOY_BLOCKED", task_id, agent,
                               project=project_name)
            logger.info(f"Deploy blocked: {agent} not allowed for {project_name}")
            return

        # 2. Check for actual changes
        diff_stat = await self._git_cmd(worktree_path, "diff", "--stat", "HEAD")
        if not diff_stat.strip():
            logger.info(f"No changes in worktree for {task_id}, skipping PR")
            return

        # 3. Diff size guard
        numstat = await self._git_cmd(
            worktree_path, "diff", "--numstat", "HEAD"
        )
        total_changed = 0
        for line in numstat.strip().splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                total_changed += int(parts[0]) + int(parts[1])

        MAX_DIFF_LINES = 2000
        if total_changed > MAX_DIFF_LINES:
            emit_event(
                self._get_driver(), "DEPLOY_BLOCKED", task_id, agent,
                project=project_name,
                reason=f"diff too large: {total_changed} lines",
            )
            logger.warning(f"Diff too large ({total_changed} lines), blocking PR")
            return

        # 4. Protected file check — disable auto-merge if infra files changed
        changed_files = await self._git_cmd(
            worktree_path, "diff", "--name-only", "HEAD"
        )
        protected = {"Dockerfile", "docker-compose.yml", "railway.toml",
                      "package.json", ".github/workflows/ci.yml",
                      ".github/workflows/deploy.yml"}
        has_protected = any(
            f.strip() in protected for f in changed_files.splitlines()
        )
        auto_merge = project_config.get("auto_merge", False) and not has_protected

        # 5. Stage + commit
        branch_name = f"task-{task_id[:12]}"
        await self._git_cmd(worktree_path, "add", "-A")

        commit_msg = (
            f"feat({project_name}): {task.get('title', task_id)[:60]}\n\n"
            f"Task: {task_id}\n"
            f"Agent: {agent}\n"
            f"Duration: {run_result.duration_s:.0f}s"
        )
        commit_result = await self._git_cmd(
            worktree_path, "commit", "-m", commit_msg
        )
        if "nothing to commit" in commit_result.lower():
            logger.info(f"Nothing to commit for {task_id}")
            return

        # 6. Push branch
        push_result = await self._git_cmd(
            worktree_path, "push", "-u", "origin", branch_name
        )

        # 7. Create PR via gh
        pr_title = f"[{agent}] {task.get('title', task_id)[:60]}"
        pr_body = (
            f"## Task\n"
            f"- **ID:** `{task_id}`\n"
            f"- **Agent:** {agent}\n"
            f"- **Priority:** {task.get('priority', 'normal')}\n\n"
            f"## Changes\n```\n{diff_stat[:500]}\n```\n\n"
            f"---\nAutomated PR by Kurultai task executor."
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                "gh", "pr", "create",
                "--repo", project_config["repo"],
                "--head", branch_name,
                "--base", project_config["branch"],
                "--title", pr_title,
                "--body", pr_body,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(worktree_path),
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=30
            )
            pr_url = stdout.decode().strip()

            if proc.returncode == 0 and pr_url:
                emit_event(
                    self._get_driver(), "PR_CREATED", task_id, agent,
                    project=project_name, pr_url=pr_url,
                )
                self._write_ledger("PR_CREATED", task_id, agent,
                                   project=project_name, pr_url=pr_url)
                logger.info(f"PR created: {pr_url}")

                # 8. Enable auto-merge if configured
                if auto_merge:
                    await self._enable_auto_merge(pr_url)
                    if project_config.get("health_url"):
                        asyncio.create_task(
                            self._post_merge_health_check(
                                project_config, task_id, agent
                            )
                        )
            else:
                err_msg = stderr.decode()[:200]
                emit_event(
                    self._get_driver(), "PR_FAILED", task_id, agent,
                    project=project_name, reason=err_msg,
                )
                self._write_ledger("PR_FAILED", task_id, agent,
                                   project=project_name, reason=err_msg)
                logger.warning(f"PR creation failed: {err_msg}")
        except Exception as e:
            emit_event(
                self._get_driver(), "PR_FAILED", task_id, agent,
                project=project_name, reason=str(e)[:200],
            )
            logger.warning(f"PR creation error: {e}")

    async def _enable_auto_merge(self, pr_url: str):
        """Enable GitHub auto-merge on a PR (merges when CI passes)."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "gh", "pr", "merge", pr_url, "--auto", "--squash",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=15)
            if proc.returncode == 0:
                logger.info(f"Auto-merge enabled for {pr_url}")
        except Exception as e:
            logger.warning(f"Auto-merge enable failed: {e}")

    async def _post_merge_health_check(
        self, project_config: dict, task_id: str, agent: str
    ):
        """Curl the project health_url after auto-merge with 5 retries, 15s apart.

        Emits HEALTH_CHECK_PASSED or HEALTH_CHECK_FAILED. On failure, creates
        a CRITICAL investigation task for ogedei.
        """
        health_url = project_config.get("health_url")
        project_name = project_config["name"]
        if not health_url:
            return

        # Wait for Railway to start deploying (initial grace period)
        await asyncio.sleep(30)

        for attempt in range(1, 6):
            try:
                proc = await asyncio.create_subprocess_exec(
                    "curl", "-sf", "--max-time", "10", health_url,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
                if proc.returncode == 0:
                    emit_event(
                        self._get_driver(), "HEALTH_CHECK_PASSED", task_id, agent,
                        project=project_name, attempt=attempt,
                    )
                    self._write_ledger("HEALTH_CHECK_PASSED", task_id, agent,
                                       project=project_name, attempt=attempt)
                    logger.info(f"Health check passed for {project_name} (attempt {attempt})")
                    return
            except Exception as e:
                logger.warning(f"Health check attempt {attempt} error: {e}")

            if attempt < 5:
                await asyncio.sleep(15)

        # All 5 attempts failed — emit failure and escalate to ogedei
        emit_event(
            self._get_driver(), "HEALTH_CHECK_FAILED", task_id, agent,
            project=project_name, health_url=health_url,
        )
        self._write_ledger("HEALTH_CHECK_FAILED", task_id, agent,
                           project=project_name, health_url=health_url)
        logger.error(f"Health check failed for {project_name} after 5 attempts")

        # Create investigation task for ogedei
        try:
            self._store.create_task({
                "title": f"[HEALTH FAIL] {project_name} health check failed post-deploy",
                "body": (
                    f"Health check failed after auto-merge.\n\n"
                    f"Project: {project_name}\n"
                    f"Health URL: {health_url}\n"
                    f"Triggered by task: {task_id}\n"
                    f"Agent: {agent}\n\n"
                    f"Investigate: check Railway logs and recent deployment."
                ),
                "assigned_to": "ogedei",
                "priority": "critical",
                "parent_task_id": task_id,
            })
            logger.info(f"Created investigation task for ogedei re: {project_name} health failure")
        except Exception as e:
            logger.warning(f"Failed to create escalation task: {e}")

    def _is_docs_only_change(self, worktree_path) -> bool:
        """Check if all changed files are documentation."""
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=str(worktree_path),
                capture_output=True, text=True, timeout=10,
            )
            if not result.stdout.strip():
                return True
            doc_exts = {".md", ".txt", ".rst", ".mdx"}
            return all(
                Path(f.strip()).suffix.lower() in doc_exts
                for f in result.stdout.strip().splitlines()
                if f.strip()
            )
        except Exception:
            return False

    async def _git_cmd(self, cwd, *args: str) -> str:
        """Run a git command in a directory and return stdout."""
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        return stdout.decode(errors="replace")

    async def _process_spawn_queue(self):
        """Drain spawn-pending.json and create tasks in Neo4j.

        Reads the spawn queue file, creates each task via TaskStore, then
        clears the queue. Errors on individual entries are logged and skipped.
        """
        spawn_path = Path(str(SPAWN_QUEUE))
        if not spawn_path.exists():
            return
        try:
            data = json.loads(spawn_path.read_text())
            if not data:
                return
            for entry in data:
                try:
                    self._store.create_task(
                        task_id=entry.get(
                            "task_id", f"spawn-{uuid.uuid4().hex[:8]}"
                        ),
                        title=entry.get("title", "Spawned task"),
                        prompt=entry.get("body", entry.get("prompt", "")),
                        assigned_to=entry.get("agent", "temujin"),
                        priority=entry.get("priority", "normal"),
                        source="spawn-queue",
                        skill_hint=entry.get("skill_hint", ""),
                    )
                except Exception as e:
                    logger.warning(f"Spawn queue entry failed: {e}")
            spawn_path.write_text("[]")
        except (json.JSONDecodeError, OSError):
            pass

    def _write_ledger(
        self, event_type: str, task_id: str, agent: str, **kwargs
    ):
        """Append an event record to task-ledger.jsonl for backward compatibility."""
        entry = {
            "event": event_type,
            "ts": datetime.now().isoformat(),
            "task_id": task_id,
            "agent": agent,
            **kwargs,
        }
        try:
            ledger_path = Path(str(TASK_LEDGER))
            ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with open(ledger_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.warning(f"Ledger write failed: {e}")

    def shutdown(self):
        """Signal graceful shutdown — stops the main poll loop after the current cycle."""
        self._shutdown = True
        emit_event(
            self._get_driver(), "EXECUTOR_STOPPED", "", "",
            executor_id=self._executor_id,
        )


# ---------------------------------------------------------------------------
# Component 6: Entry Point
# ---------------------------------------------------------------------------

def acquire_lock() -> bool:
    """Acquire a PID-file lock to prevent dual executor instances.

    Returns:
        True if the lock was acquired, False if another live instance exists.
    """
    pid_file = LOGS_DIR / "task-executor.pid"
    if pid_file.exists():
        try:
            old_pid = int(pid_file.read_text().strip())
            os.kill(old_pid, 0)  # Signal 0: check existence without killing
            return False          # Another live instance owns the lock
        except (OSError, ValueError):
            pass  # Stale PID file — safe to overwrite
    pid_file.write_text(str(os.getpid()))
    return True


def release_lock():
    """Remove the PID file if it belongs to this process."""
    pid_file = LOGS_DIR / "task-executor.pid"
    try:
        if pid_file.exists() and pid_file.read_text().strip() == str(os.getpid()):
            pid_file.unlink()
    except OSError:
        pass


def build_executor() -> Executor:
    """Factory function: wire all components into a ready-to-run Executor."""
    store = TaskStore()
    return Executor(
        store=store,
        runner=TaskRunner(),
        session_mgr=SessionManager(),
        wal=WAL(),
        cb=AgentCircuitBreaker(),
        sanitizer=PromptSanitizer(),
    )


async def main():
    """Async entry point: build executor, register signal handlers, run."""
    executor = build_executor()

    loop = asyncio.get_running_loop()
    _signal_received: list[signal.Signals] = []

    def _shutdown_handler(sig: signal.Signals = signal.SIGTERM):
        _signal_received.append(sig)
        executor.shutdown()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _shutdown_handler, sig)

    try:
        await executor.run()
    finally:
        release_lock()
        # Exit with code 1 if shutdown was triggered by a signal, so that
        # launchd (KeepAlive.Crashed=true) treats it as a crash and restarts
        # the executor automatically.  Without this, SIGTERM → clean exit
        # (code 0) → KeepAlive.SuccessfulExit=false → launchd does NOT restart
        # → executor stays dead until manually kicked.
        if _signal_received:
            logger.info(
                f"Exiting with code 1 after signal {_signal_received[0].name} "
                "so launchd restarts the executor."
            )
            sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    if not acquire_lock():
        print(
            "Another task_executor instance is already running. Exiting.",
            file=sys.stderr,
        )
        sys.exit(0)  # Exit 0 so launchd doesn't treat as crash and restart

    logger.info("Starting unified task executor...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted. Shutting down.")
    finally:
        release_lock()
