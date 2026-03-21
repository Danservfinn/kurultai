#!/usr/bin/env python3
"""
ogedei_dispatch.py — Persistent asyncio dispatcher for agent-owned task execution.

Architecture (Option B):
    - Agents own planning, execution, and subagent dispatch
    - Ogedei dispatches, monitors PID liveness, verifies output, sends notifications
    - Uses dispatch_phase sub-status (not new Neo4j statuses) for rollback safety

Loops:
    1. Dispatch loop (15s) — claim PENDING, launch agent subprocess
    2. Verification loop (15s) — validate pending_verification outputs
    3. Notification loop (15s) — process persistent SQLite notification queue
    4. Health loop (30s) — credential checks, queue balance, circuit breakers
    5. Orphan loop (150s) — recover expired leases, promote orphans

Usage:
    python3 ogedei_dispatch.py                # Run dispatcher
    python3 ogedei_dispatch.py --shadow       # Shadow mode (read-only, log only)
    python3 ogedei_dispatch.py --dry-run      # Show claimable tasks
    python3 ogedei_dispatch.py --once         # Single dispatch cycle
"""

import asyncio
import json
import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
import queue as _queue
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_v2_core import TaskStore
from neo4j_v2_failure import classify_failure, classify_validation_failure
from neo4j_v2_validator import validate_completion
from neo4j_v2_scorer import score_completed_task, score_failed_task
from neo4j_v2_wal import WAL
from notification_queue import NotificationQueue
from agents_config import AGENTS
from kurultai_paths import (
    CLAUDE_AGENT, AGENTS_DIR, DISPATCH_AGENTS,
    STALE_EXECUTING_SECS, CLAUDE_TIMEOUT,
    SLOW_SKILLS, LOGS_DIR, TASK_LEDGER,
    VALID_AGENTS, agent_workspace_dir,
)
from kurultai_ledger import append_ledger

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

POLL_INTERVAL = 15  # seconds between dispatch cycles
LEASE_MINUTES = 45
LEASE_RENEW_INTERVAL = 600  # renew every 10 minutes
ORPHAN_GRACE_MINUTES = 5
VERIFY_INTERVAL = 15
NOTIFY_INTERVAL = 15
HEALTH_INTERVAL = 30
ORPHAN_INTERVAL = 150

# Stall detection (ported from v2-executor)
STALL_SILENCE_THRESHOLD = 900
STALL_MIN_ELAPSED = 900
SLOW_SKILL_STALL_SILENCE = 1200
SLOW_SKILL_STALL_ELAPSED = 1200
PROXY_STALL_SILENCE = 2400
PROXY_STALL_ELAPSED = 1800
PROXY_ENDPOINTS = ['dashscope.aliyuncs.com', 'openrouter.ai', 'api.z.ai']

HEARTBEAT_FILE = LOGS_DIR / "ogedei-dispatcher-heartbeat.json"
HAIKU_TIMEOUT = 120

# Prompt injection patterns (ported from agent-task-handler.py)
INJECTION_PATTERNS = [
    (r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|rules?|directives?)", "[FILTERED]"),
    (r"disregard\s+(all\s+)?(previous|above|prior)", "[FILTERED]"),
    (r"forget\s+(all\s+)?(previous|above|your\s+instructions?)", "[FILTERED]"),
    (r"you\s+are\s+now\s+", "[FILTERED]"),
    (r"new\s+instructions?:", "[FILTERED]"),
    (r"<\|.*?\|>", "[FILTERED]"),
    (r"\[SYSTEM\]", "[FILTERED]"),
    (r"\[/SYSTEM\]", "[FILTERED]"),
    (r"<<.*?>>", "[FILTERED]"),
    (r"developer\s+mode", "[FILTERED]"),
    (r"override\s+safety", "[FILTERED]"),
]


def sanitize_task_content(content: str) -> str:
    """Port of agent-task-handler.py sanitize_task_content."""
    if not content:
        return content
    sanitized = content
    for pattern, replacement in INJECTION_PATTERNS:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
    return sanitized


def validate_result_path(agent_name: str, result_file: str) -> bool:
    """Defense in depth: also validated at write time in task_state.py."""
    if not agent_name or agent_name not in VALID_AGENTS:
        return False
    allowed = os.path.realpath(str(AGENTS_DIR / agent_name / "workspace"))
    canonical = os.path.realpath(result_file)
    return canonical.startswith(allowed + os.sep) or canonical == allowed


# ---------------------------------------------------------------------------
# Agent Tracker
# ---------------------------------------------------------------------------

class AgentTracker:
    """Track which agents are busy and with what task."""

    def __init__(self, store: TaskStore):
        self._busy: dict[str, dict] = {}  # agent -> {task_id, pid, start_time}
        self._rebuild_from_neo4j(store)

    def _rebuild_from_neo4j(self, store: TaskStore):
        """On startup, infer busy agents from Neo4j state."""
        try:
            with store.driver.session() as session:
                result = session.run("""
                    MATCH (t:Task {status: 'WORKING'})
                    WHERE t.dispatch_phase IS NOT NULL
                    RETURN t.assigned_to AS agent, t.task_id AS task_id
                """)
                for record in result:
                    agent = record['agent']
                    if agent:
                        self._busy[agent] = {
                            'task_id': record['task_id'],
                            'pid': None,
                            'start_time': time.time(),
                        }
            if self._busy:
                logger.info(f"AgentTracker rebuilt: {list(self._busy.keys())} busy")
        except Exception as e:
            logger.warning(f"AgentTracker rebuild failed: {e}")

    def mark_busy(self, agent: str, task_id: str, pid: int):
        self._busy[agent] = {
            'task_id': task_id,
            'pid': pid,
            'start_time': time.time(),
        }

    def mark_idle(self, agent: str):
        self._busy.pop(agent, None)

    def is_busy(self, agent: str) -> bool:
        return agent in self._busy

    def get_busy_info(self, agent: str) -> Optional[dict]:
        return self._busy.get(agent)

    def get_all_busy(self) -> dict:
        return dict(self._busy)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

class OgedeiDispatcher:
    """Main dispatcher with isolated async loops."""

    def __init__(self, shadow: bool = False, agents: list[str] = None):
        self.shadow = shadow
        self.store = TaskStore()
        self.wal = WAL()
        self.nqueue = NotificationQueue()
        self.agents = agents or DISPATCH_AGENTS
        self.tracker = AgentTracker(self.store)
        self.shutdown = asyncio.Event()
        self._poll_count = 0
        self._dispatch_count = 0

    # ------------------------------------------------------------------
    # Environment + Prompt (ported from v2-executor)
    # ------------------------------------------------------------------

    def _build_env(self, agent_name: str) -> dict:
        """Build clean execution environment for claude-agent."""
        env = os.environ.copy()
        env.pop('CLAUDECODE', None)
        env['PATH'] = (
            "/Users/kublai/.local/bin:/opt/homebrew/bin:"
            "/usr/local/bin:/usr/bin:/bin:" + env.get('PATH', '')
        )

        for key in [k for k in env if k.startswith('ANTHROPIC_')]:
            del env[key]

        # Load vault credentials
        vault_path = Path.home() / '.openclaw' / 'credentials' / 'provider.env'
        if vault_path.exists():
            try:
                with open(vault_path) as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        if '=' in line:
                            key, value = line.split('=', 1)
                            env[key.strip()] = value.strip().strip('"\'')
            except Exception as e:
                logger.warning(f"Vault load failed: {e}")

        # Load agent-specific settings
        agent_root = str(AGENTS_DIR / agent_name)
        try:
            with open(f"{agent_root}/.claude/settings.json") as f:
                settings = json.load(f)
            for key, value in settings.get('env', {}).items():
                env[key] = value
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        # NOTE: Do NOT override ANTHROPIC_MODEL here. The claude-agent wrapper
        # reads per-agent config from settings.json (written by dashboard UI)
        # and handles model resolution + fallback chain internally.
        # The dispatcher's _build_env only provides vault credentials and PATH.

        return env

    def _build_envelope(self, task: dict) -> dict:
        """Build JSON dispatch envelope (AD5)."""
        return {
            "task_id": task['task_id'],
            "title": task.get('title', ''),
            "body": sanitize_task_content(
                task.get('body', task.get('prompt', ''))
            ),
            "priority": task.get('priority', 'normal'),
            "skill_hint": task.get('skill_hint', ''),
            "notify_target": task.get(
                'notify_target',
                task.get('origin_initiator', '+19194133445'),
            ),
            "timeout_seconds": task.get('timeout_s', CLAUDE_TIMEOUT),
            "requester_id": task.get('requester_id', 'operator'),
            "claim_epoch": task['claim_epoch'],
            "created_at": task.get('created_at', ''),
            "domain": task.get('domain', ''),
            "depth": task.get('depth', 0),
            "max_retries": task.get('max_retries', 3),
        }

    def _build_dispatch_prompt(self, task: dict, envelope: dict) -> str:
        """Build dispatch prompt with TASK_DISPATCH prefix."""
        parts = []

        # Prior failure context
        failures = task.get('failure_reports', [])
        if failures:
            parts.append("## Prior Attempts (failed)\n")
            for f in failures:
                parts.append(
                    f"- Attempt {f.get('attempt', '?')}: "
                    f"{f.get('error_class', 'unknown')} — "
                    f"{f.get('error_msg', 'no details')}\n"
                )
            parts.append("\nUse this context to avoid repeating the same failure.\n\n")

        parts.append(f"TASK_DISPATCH:{json.dumps(envelope)}")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Auth preflight (ported from agent-task-handler.py)
    # ------------------------------------------------------------------

    async def _auth_preflight(self, agent_name: str) -> bool:
        """Quick auth check before dispatching."""
        env = self._build_env(agent_name)
        base_url = env.get('ANTHROPIC_BASE_URL', '')
        is_proxy = any(ep in base_url for ep in PROXY_ENDPOINTS)

        # OAuth agents don't need key check
        if not is_proxy and not env.get('ANTHROPIC_API_KEY'):
            # OAuth — assumed good
            return True

        if is_proxy and not env.get('ANTHROPIC_API_KEY'):
            logger.warning(f"Auth preflight: {agent_name} proxy has no API key")
            return False

        return True

    # ------------------------------------------------------------------
    # Dispatch loop
    # ------------------------------------------------------------------

    async def _dispatch_loop(self):
        """Poll Neo4j, claim tasks, launch agents."""
        while not self.shutdown.is_set():
            try:
                await self._dispatch_cycle()
            except Exception as e:
                logger.exception(f"Dispatch cycle error: {e}")
            await self._sleep(POLL_INTERVAL)

    async def _dispatch_cycle(self):
        """Single dispatch cycle across all agents."""
        self._poll_count += 1

        for agent in self.agents:
            if self.shutdown.is_set():
                break
            if self.tracker.is_busy(agent):
                continue

            try:
                if self.shadow:
                    # Shadow mode: read-only, log what would happen
                    depths = self.store.get_queue_depth(agent)
                    if depths.get('PENDING', 0) > 0:
                        logger.info(f"[SHADOW] Would claim task for {agent} "
                                    f"(PENDING={depths['PENDING']})")
                    continue

                task = self.store.claim_task(agent, LEASE_MINUTES)
            except Exception as e:
                logger.error(f"Claim failed for {agent}: {e}")
                continue

            if task is None:
                continue

            # Auth preflight
            if not await self._auth_preflight(agent):
                self.store.fail_task(
                    task['task_id'], task['claim_epoch'],
                    'AUTH_FAILURE', 'Auth preflight failed', True,
                )
                _emit_event("AUTH_PREFLIGHT_FAIL", task['task_id'], agent)
                continue

            # Set dispatch_phase
            self._set_dispatch_phase(
                task['task_id'], task['claim_epoch'], 'dispatched',
            )
            _emit_event("PHASE_DISPATCHED", task['task_id'], agent)

            # Build envelope and prompt
            envelope = self._build_envelope(task)
            prompt = self._build_dispatch_prompt(task, envelope)

            # Launch agent
            asyncio.create_task(
                self._launch_and_monitor(agent, task, prompt)
            )

            self._dispatch_count += 1
            logger.info(f"Dispatched {task['task_id']} to {agent}")

    async def _launch_and_monitor(self, agent: str, task: dict, prompt: str):
        """Launch agent subprocess and monitor until completion."""
        task_id = task['task_id']
        claim_epoch = task['claim_epoch']
        agent_root = str(AGENTS_DIR / agent)
        env = self._build_env(agent)
        timeout_s = task.get('timeout_s', CLAUDE_TIMEOUT)
        skill_hint = task.get('skill_hint', '')
        priority = task.get('priority', 'normal')

        # Determine stall thresholds
        base_url = env.get('ANTHROPIC_BASE_URL', '')
        is_proxy = any(ep in base_url for ep in PROXY_ENDPOINTS)
        is_slow = (skill_hint in SLOW_SKILLS) or priority == 'high'

        if is_proxy:
            stall_elapsed, stall_silence = PROXY_STALL_ELAPSED, PROXY_STALL_SILENCE
        elif is_slow:
            stall_elapsed = SLOW_SKILL_STALL_ELAPSED
            stall_silence = SLOW_SKILL_STALL_SILENCE
        else:
            stall_elapsed, stall_silence = STALL_MIN_ELAPSED, STALL_SILENCE_THRESHOLD

        # Pre-dispatch orphan cleanup
        _cleanup_script = Path(__file__).parent / "cleanup-orphan-claude.sh"
        if _cleanup_script.exists():
            try:
                subprocess.run(
                    ["bash", str(_cleanup_script), "--run", "--older-minutes=45"],
                    capture_output=True, text=True, timeout=15,
                )
            except Exception:
                pass

        # Build command
        cmd = [
            str(CLAUDE_AGENT), "--workdir", agent_root,
            "--effort", "high", "--", prompt,
        ]

        start = time.time()
        loop = asyncio.get_event_loop()

        # Lease renewal task
        lease_task = asyncio.create_task(
            self._renew_lease_loop(task_id, claim_epoch)
        )

        try:
            # Run in executor thread (subprocess blocks)
            result = await loop.run_in_executor(
                None, self._run_subprocess, cmd, env, timeout_s,
                stall_elapsed, stall_silence, agent, start,
            )

            duration_s = result.get('duration_s', time.time() - start)

            # Check dispatch_phase — if agent marked pending_verification, skip
            current_task = self.store.get_task(task_id)
            current_phase = current_task.get('dispatch_phase') if current_task else None

            if current_phase == 'pending_verification':
                # Agent self-completed the protocol — verification loop handles it
                logger.info(f"Agent {agent} self-marked {task_id} as pending_verification")
            elif result['success']:
                # Agent completed but didn't use dispatch protocol — handle directly
                await self._handle_direct_completion(
                    task, result, claim_epoch, agent, duration_s
                )
            else:
                # Process failure
                await self._handle_failure(
                    task, result, claim_epoch, agent, duration_s
                )

        except Exception as e:
            logger.exception(f"Error monitoring {task_id}")
            try:
                self.store.fail_task(
                    task_id, claim_epoch, "DISPATCHER_ERROR",
                    str(e), is_transient=True,
                )
            except Exception:
                pass
        finally:
            lease_task.cancel()
            self.tracker.mark_idle(agent)

    def _run_subprocess(self, cmd, env, timeout_s, stall_elapsed,
                        stall_silence, agent, start) -> dict:
        """Run claude-agent subprocess with stall detection (blocking)."""
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=env,
        )

        self.tracker.mark_busy(agent, "running", proc.pid)

        stdout_chunks = []
        last_output_time = time.time()
        stdout_q = _queue.Queue()

        def _reader(pipe, q):
            for line in pipe:
                q.put(line)
            q.put(None)

        reader_thread = threading.Thread(
            target=_reader, args=(proc.stdout, stdout_q), daemon=True
        )
        reader_thread.start()

        while True:
            elapsed = time.time() - start

            # Hard timeout
            if elapsed >= timeout_s:
                proc.kill()
                proc.wait()
                return {
                    "success": False,
                    "content": "".join(stdout_chunks),
                    "error": f"Timed out after {timeout_s}s",
                    "return_code": -1,
                    "duration_s": elapsed,
                }

            # Drain stdout
            got_output = False
            while True:
                try:
                    line = stdout_q.get_nowait()
                except _queue.Empty:
                    break
                if line is None:
                    got_output = True
                    break
                stdout_chunks.append(line)
                got_output = True

            if got_output:
                last_output_time = time.time()

            # Check if process exited
            if proc.poll() is not None:
                remaining_stderr = proc.stderr.read() if proc.stderr else ""
                return {
                    "success": proc.returncode == 0,
                    "content": "".join(stdout_chunks),
                    "error": remaining_stderr if proc.returncode != 0 else "",
                    "return_code": proc.returncode,
                    "duration_s": time.time() - start,
                }

            # Stall detection (ported from v2-executor lines 410-449)
            silence = time.time() - last_output_time
            if elapsed >= stall_elapsed and silence >= stall_silence:
                # Check session JSONL mtime before killing
                session_active = False
                try:
                    agent_root = str(AGENTS_DIR / agent)
                    project_slug = agent_root.replace('/', '-')
                    project_dir = os.path.expanduser(
                        f"~/.claude/projects/{project_slug}"
                    )
                    if os.path.isdir(project_dir):
                        now = time.time()
                        for fname in os.listdir(project_dir):
                            if fname.endswith('.jsonl'):
                                fpath = os.path.join(project_dir, fname)
                                if now - os.path.getmtime(fpath) < 60:
                                    session_active = True
                                    break
                except Exception:
                    pass

                if session_active:
                    last_output_time = time.time() - (stall_silence - 60)
                    time.sleep(0.5)
                    continue

                logger.warning(
                    f"Stall: {agent} silent {silence:.0f}s after {elapsed:.0f}s"
                )
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                return {
                    "success": False,
                    "content": "".join(stdout_chunks),
                    "error": f"STALL: no output for {silence:.0f}s",
                    "return_code": proc.returncode or -1,
                    "duration_s": time.time() - start,
                }

            time.sleep(0.5)

    async def _handle_direct_completion(self, task, result, claim_epoch,
                                         agent, duration_s):
        """Handle completion when agent didn't use dispatch protocol."""
        task_id = task['task_id']
        valid, parsed = validate_completion(result['content'])

        if valid:
            ok, reason = self.store.complete_task(
                task_id, claim_epoch,
                text=result['content'],
                problem=parsed['problem'],
                solution=parsed['solution'],
                rationale=parsed['rationale'],
                output_lines=result['content'].count('\n'),
                duration_s=duration_s,
            )
            if ok:
                self.store.record_execution(task_id, agent, 'completed', duration_s)
                score_completed_task(
                    self.store, task_id, agent, task.get('skill_hint', '')
                )
                _emit_event("COMPLETED", task_id, agent, duration_s=duration_s)
                logger.info(f"Task {task_id} completed in {duration_s:.0f}s")

                # Persist result and queue notification
                result_file = self._persist_result(
                    agent, task_id, result['content'], task, duration_s
                )
                self._queue_notification(task, agent, duration_s, result_file)
            else:
                logger.error(f"Complete CAS failed for {task_id}: {reason}")
        else:
            reason = parsed.get('reason', 'validation_failed')
            error_class, transient = classify_validation_failure(reason)
            self.store.fail_task(
                task_id, claim_epoch, error_class,
                f"Output validation: {reason}", transient,
                output_snippet=result['content'][:2000],
            )
            self.store.record_execution(
                task_id, agent, 'validation_failed', duration_s
            )
            _emit_event("VERIFICATION_FAILED", task_id, agent, reason=reason)

    async def _handle_failure(self, task, result, claim_epoch, agent, duration_s):
        """Handle process failure."""
        task_id = task['task_id']
        error_class, transient = classify_failure(
            result.get('return_code', 1),
            result.get('error', ''),
            result.get('content', ''),
        )
        ok, new_status = self.store.fail_task(
            task_id, claim_epoch, error_class,
            result.get('error', 'Unknown error'),
            transient, output_snippet=result.get('content', '')[:2000],
        )
        self.store.record_execution(
            task_id, agent, f'failed:{error_class}', duration_s
        )
        if new_status == 'FAILED':
            score_failed_task(
                self.store, task_id, agent, task.get('skill_hint', '')
            )
        _emit_event(
            "FAILED", task_id, agent,
            error_class=error_class, error=result.get('error', '')[:500],
        )

    # ------------------------------------------------------------------
    # Verification loop
    # ------------------------------------------------------------------

    async def _verification_loop(self):
        """Validate outputs from tasks in pending_verification phase."""
        while not self.shutdown.is_set():
            try:
                await self._verify_cycle()
            except Exception as e:
                logger.exception(f"Verification cycle error: {e}")
            await self._sleep(VERIFY_INTERVAL)

    async def _verify_cycle(self):
        """Process tasks with dispatch_phase='pending_verification'."""
        with self.store.driver.session() as session:
            result = session.run("""
                MATCH (t:Task {status: 'WORKING'})
                WHERE t.dispatch_phase = 'pending_verification'
                RETURN t {.*} AS task
                LIMIT 10
            """)
            tasks = [dict(r['task']) for r in result]

        for task in tasks:
            task_id = task['task_id']
            claim_epoch = task.get('claim_epoch', 0)
            agent = task.get('assigned_to', '')
            result_file = task.get('result_file')

            # Validate path
            if not result_file or not validate_result_path(agent, result_file):
                self.store.fail_task(
                    task_id, claim_epoch, 'VALIDATION',
                    'Invalid or missing result_file path', False,
                )
                _emit_event("VERIFICATION_FAILED", task_id, agent,
                            reason="invalid_result_path")
                continue

            if not os.path.exists(result_file):
                self.store.fail_task(
                    task_id, claim_epoch, 'VALIDATION',
                    'Result file missing', True,
                )
                _emit_event("VERIFICATION_FAILED", task_id, agent,
                            reason="result_file_missing")
                continue

            # Read and validate output
            try:
                output = Path(result_file).read_text()
            except Exception as e:
                self.store.fail_task(
                    task_id, claim_epoch, 'VALIDATION',
                    f'Cannot read result file: {e}', True,
                )
                continue

            valid, parsed = validate_completion(output)

            if valid:
                ok, reason = self.store.complete_task(
                    task_id, claim_epoch,
                    text=output,
                    problem=parsed['problem'],
                    solution=parsed['solution'],
                    rationale=parsed['rationale'],
                    output_lines=output.count('\n'),
                )
                if ok:
                    self.store.record_execution(
                        task_id, agent, 'completed', 0
                    )
                    score_completed_task(
                        self.store, task_id, agent,
                        task.get('skill_hint', ''),
                    )
                    _emit_event("VERIFICATION_PASSED", task_id, agent)
                    logger.info(f"Verified + completed {task_id}")

                    # Queue notification
                    self._queue_notification(task, agent, 0, result_file)
                else:
                    logger.warning(f"Verify complete CAS failed: {reason}")
            else:
                reason = parsed.get('reason', 'validation_failed')
                error_class, transient = classify_validation_failure(reason)
                self.store.fail_task(
                    task_id, claim_epoch, error_class,
                    f"Verification: {reason}", transient,
                    output_snippet=output[:2000],
                )
                _emit_event("VERIFICATION_FAILED", task_id, agent, reason=reason)

    # ------------------------------------------------------------------
    # Notification loop
    # ------------------------------------------------------------------

    async def _notification_loop(self):
        """Process notification queue (non-blocking)."""
        while not self.shutdown.is_set():
            try:
                item = self.nqueue.peek()
                if item:
                    loop = asyncio.get_event_loop()
                    try:
                        await loop.run_in_executor(
                            None, self._send_notification_sync, item
                        )
                        self.nqueue.mark_sent(item['id'])
                        _emit_event(
                            "NOTIFICATION_SENT", item['task_id'],
                            item['agent'],
                        )
                    except Exception as e:
                        self.nqueue.increment_attempts(
                            item['id'], str(e)[:500]
                        )
                        _emit_event(
                            "NOTIFICATION_FAILED", item['task_id'],
                            item['agent'], error=str(e)[:200],
                        )
            except Exception as e:
                logger.exception(f"Notification loop error: {e}")
            await self._sleep(NOTIFY_INTERVAL)

    def _send_notification_sync(self, item: dict):
        """Send Signal notification via /task-complete skill (blocking)."""
        agent_name = item['agent']
        task_id = item['task_id']

        # Write breadcrumb for /task-complete
        bc_path = AGENTS_DIR / agent_name / "last-completed-task.json"
        bc_data = {
            "task_id": task_id,
            "agent": agent_name,
            "notify_target": item.get('notify_target', '+19194133445'),
            "ts": datetime.now().isoformat(),
            "model": "claude-sonnet-4-6",
        }
        bc_path.write_text(json.dumps(bc_data))

        env_notify = os.environ.copy()
        env_notify.pop('CLAUDECODE', None)
        env_notify['TASK_COMPLETE_AGENT'] = agent_name

        log_file = LOGS_DIR / "task-complete-debug.log"
        with open(log_file, 'a') as log_f:
            log_f.write(
                f"[{datetime.now().isoformat()}] dispatcher: "
                f"/task-complete for {agent_name} task={task_id}\n"
            )
            proc = subprocess.Popen(
                [str(CLAUDE_AGENT), "--model", "claude-sonnet-4-6",
                 "/task-complete"],
                stdout=log_f, stderr=log_f,
                close_fds=True, env=env_notify,
            )
            try:
                proc.wait(timeout=HAIKU_TIMEOUT)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                raise TimeoutError(f"/task-complete timed out ({HAIKU_TIMEOUT}s)")

    def _queue_notification(self, task: dict, agent: str, duration_s: float,
                            result_file: str = None):
        """Queue a notification for delivery."""
        task_id = task['task_id']
        notify_target = task.get(
            'notify_target',
            task.get('origin_initiator', '+19194133445'),
        )
        title = task.get('title', task_id)
        message = f"Task completed: {title} ({duration_s:.0f}s)"

        self.nqueue.enqueue(task_id, agent, notify_target, message)
        _emit_event("NOTIFICATION_QUEUED", task_id, agent)

    # ------------------------------------------------------------------
    # Health loop (ported from ogedei-watchdog.py)
    # ------------------------------------------------------------------

    async def _health_loop(self):
        """Periodic health checks."""
        while not self.shutdown.is_set():
            try:
                await self._health_cycle()
            except Exception as e:
                logger.exception(f"Health cycle error: {e}")
            await self._sleep(HEALTH_INTERVAL)

    async def _health_cycle(self):
        """Run ported watchdog checks."""
        # Check 8: model drift (O001)
        self._check_model_drift()

        # Check 10: agent failure rates
        self._check_agent_failure_rates()

        # Check 11: credential failures
        self._check_credential_failures()

        # Check 12: queue balance
        self._check_queue_balance()

        # Check 13: cascade risk
        self._check_cascade_risk()

        # Check 17: circuit breaker health
        self._check_circuit_breaker()

    def _check_model_drift(self):
        """Port of watchdog check_model_drift (O001)."""
        try:
            config_path = Path.home() / '.openclaw' / 'kurultai.json'
            if not config_path.exists():
                return
            config = json.loads(config_path.read_text())
            for agent_name, cfg in config.get('agents', {}).items():
                expected = cfg.get('model', 'claude-opus-4-6')
                settings_path = AGENTS_DIR / agent_name / '.claude' / 'settings.json'
                if not settings_path.exists():
                    continue
                settings = json.loads(settings_path.read_text())
                actual = settings.get('env', {}).get('ANTHROPIC_MODEL', expected)
                if actual != expected:
                    logger.warning(
                        f"Model drift: {agent_name} config={expected} "
                        f"settings={actual}"
                    )
        except Exception as e:
            logger.debug(f"Model drift check error: {e}")

    def _check_agent_failure_rates(self):
        """Port of watchdog check_agent_failure_rates."""
        try:
            events = _read_ledger_safe(hours=1)
            if not events:
                return

            agent_completed = {}
            agent_failed = {}
            for ev in events:
                agent = ev.get("agent")
                if not agent:
                    continue
                evt = ev.get("event", "")
                if evt == "COMPLETED":
                    agent_completed[agent] = agent_completed.get(agent, 0) + 1
                elif evt == "FAILED":
                    agent_failed[agent] = agent_failed.get(agent, 0) + 1

            flags = {}
            for agent in set(list(agent_completed) + list(agent_failed)):
                c = agent_completed.get(agent, 0)
                f = agent_failed.get(agent, 0)
                total = c + f
                if total == 0:
                    continue
                rate = f / total
                flags[agent] = {
                    "completed": c, "failed": f,
                    "failure_rate": round(rate, 2),
                    "healthy": rate < 0.5,
                }

            if flags:
                health_path = LOGS_DIR / "agent-health-flags.json"
                health_path.write_text(json.dumps({
                    "timestamp": time.time(), "agents": flags,
                }))
        except Exception as e:
            logger.debug(f"Failure rate check error: {e}")

    def _check_credential_failures(self):
        """Port of watchdog check_credential_failures."""
        try:
            events = _read_ledger_safe(hours=0.5)
            if not events:
                return

            cred_keywords = [
                "unauthorized", "authentication", "invalid token",
                "401", "403", "auth failed",
            ]
            agent_cred = {}
            for ev in events:
                agent = ev.get("agent")
                if not agent:
                    continue
                err_type = ev.get("error_type", "")
                err_msg = (ev.get("error") or ev.get("error_msg") or "").lower()
                if err_type in ("AUTH", "PROXY_AUTH") or any(
                    kw in err_msg for kw in cred_keywords
                ):
                    agent_cred[agent] = agent_cred.get(agent, 0) + 1

            for agent, count in agent_cred.items():
                if count >= 2:
                    logger.warning(
                        f"Credential alert: {agent} has {count} auth failures"
                    )
                    _emit_event(
                        "CREDENTIAL_REDISPATCH", "system", agent,
                        failure_count=count,
                    )
        except Exception as e:
            logger.debug(f"Credential check error: {e}")

    def _check_queue_balance(self):
        """Check for unbalanced queues across agents."""
        try:
            depths = {}
            for agent in self.agents:
                d = self.store.get_queue_depth(agent)
                depths[agent] = d.get('PENDING', 0)

            if not depths:
                return

            max_depth = max(depths.values())
            min_depth = min(depths.values())
            if max_depth > 5 and min_depth == 0:
                logger.info(
                    f"Queue imbalance: max={max_depth} min={min_depth} "
                    f"depths={depths}"
                )
        except Exception as e:
            logger.debug(f"Queue balance check error: {e}")

    def _check_cascade_risk(self):
        """Detect cascade failure patterns."""
        try:
            events = _read_ledger_safe(hours=0.17)  # ~10 min
            if not events:
                return
            fail_count = sum(1 for e in events if e.get('event') == 'FAILED')
            if fail_count >= 5:
                logger.warning(
                    f"Cascade risk: {fail_count} failures in 10 minutes"
                )
        except Exception:
            pass

    def _check_circuit_breaker(self):
        """Check circuit breaker state files."""
        try:
            cb_path = LOGS_DIR / "circuit-breaker-state.json"
            if not cb_path.exists():
                return
            state = json.loads(cb_path.read_text())
            for name, cb in state.items():
                if cb.get('state') == 'open':
                    logger.warning(f"Circuit breaker OPEN: {name}")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Orphan loop
    # ------------------------------------------------------------------

    async def _orphan_loop(self):
        """Recover orphaned tasks periodically."""
        while not self.shutdown.is_set():
            try:
                promoted = self.store.promote_orphans(hold_minutes=5)
                if promoted:
                    logger.info(f"Promoted {len(promoted)} orphans to PENDING")
                recovered = self.store.recover_orphans(ORPHAN_GRACE_MINUTES)
                if recovered:
                    logger.info(f"Recovered {len(recovered)} orphans")
            except Exception as e:
                logger.exception(f"Orphan loop error: {e}")
            await self._sleep(ORPHAN_INTERVAL)

    # ------------------------------------------------------------------
    # Heartbeat writer
    # ------------------------------------------------------------------

    async def _heartbeat_writer(self):
        """Write dispatcher heartbeat file for dead-man's switch."""
        while not self.shutdown.is_set():
            try:
                heartbeat = {
                    "timestamp": time.time(),
                    "pid": os.getpid(),
                    "poll_count": self._poll_count,
                    "dispatch_count": self._dispatch_count,
                    "active_agents": list(self.tracker.get_all_busy().keys()),
                    "notification_pending": self.nqueue.pending_count(),
                    "status": "running",
                }
                HEARTBEAT_FILE.write_text(json.dumps(heartbeat))
            except Exception:
                pass
            await self._sleep(15)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_dispatch_phase(self, task_id: str, claim_epoch: int,
                             phase: str):
        """Set dispatch_phase on a WORKING task."""
        try:
            with self.store.driver.session() as session:
                session.run("""
                    MATCH (t:Task {task_id: $id, status: 'WORKING',
                                   claim_epoch: $epoch})
                    SET t.dispatch_phase = $phase,
                        t.phase_updated_at = datetime()
                """, id=task_id, epoch=claim_epoch, phase=phase)
        except Exception as e:
            logger.warning(f"Failed to set dispatch_phase: {e}")

    def _persist_result(self, agent, task_id, content, task, duration_s):
        """Write task result to agent's workspace."""
        try:
            result_dir = AGENTS_DIR / agent / "workspace"
            result_dir.mkdir(parents=True, exist_ok=True)
            result_file = result_dir / f"{task_id}.result.md"
            title = task.get('title', task_id)
            body = task.get('body', '')[:300]
            header = (
                f"# Task Result: {title}\n\n"
                f"**Task ID:** {task_id}\n"
                f"**Agent:** {agent}\n"
                f"**Duration:** {duration_s:.0f}s\n"
                f"**Task:** {body}\n\n---\n\n"
            )
            result_file.write_text(header + content)
            result_file.chmod(0o600)
            return str(result_file)
        except Exception as e:
            logger.warning(f"Failed to persist result for {task_id}: {e}")
            return None

    async def _renew_lease_loop(self, task_id: str, claim_epoch: int):
        """Periodically renew lease while task executes."""
        try:
            while True:
                await asyncio.sleep(LEASE_RENEW_INTERVAL)
                ok = self.store.renew_lease(task_id, claim_epoch, LEASE_MINUTES)
                if not ok:
                    logger.warning(f"Lease renewal failed for {task_id}")
                    break
        except asyncio.CancelledError:
            pass

    async def _sleep(self, seconds: float):
        """Interruptible sleep."""
        try:
            await asyncio.wait_for(self.shutdown.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------

    async def run(self):
        """Start all loops."""
        logger.info(
            f"Starting Ogedei Dispatcher: agents={self.agents}, "
            f"shadow={self.shadow}"
        )

        # Startup recovery
        recovered = self.store.recover_orphans(ORPHAN_GRACE_MINUTES)
        if recovered:
            logger.info(f"Startup: recovered {len(recovered)} orphans")

        pending = self.wal.pending_count()
        if pending > 0:
            try:
                replayed = self.wal.replay(self.store.driver)
                logger.info(f"WAL replayed {replayed} entries")
            except Exception as e:
                logger.error(f"WAL replay failed: {e}")

        # Launch all loops as independent tasks
        tasks = [
            asyncio.create_task(self._dispatch_loop()),
            asyncio.create_task(self._verification_loop()),
            asyncio.create_task(self._notification_loop()),
            asyncio.create_task(self._health_loop()),
            asyncio.create_task(self._orphan_loop()),
            asyncio.create_task(self._heartbeat_writer()),
        ]

        # Block until shutdown
        await self.shutdown.wait()
        logger.info("Shutdown requested, waiting for loops...")

        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        self.store.close()
        logger.info("Dispatcher shut down")

    def request_shutdown(self):
        self.shutdown.set()


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _emit_event(event: str, task_id: str, agent: str, **extra):
    """Emit ledger event."""
    entry = {
        "event": event,
        "task_id": task_id,
        "agent": agent,
        "ts": datetime.now(timezone.utc).isoformat(),
        "executor": "ogedei-dispatcher",
    }
    entry.update(extra)
    try:
        append_ledger(entry)
    except Exception:
        pass


def _read_ledger_safe(hours: float = 1) -> list:
    """Read ledger events safely."""
    try:
        from kurultai_ledger import read_ledger
        return read_ledger(hours=hours, valid_only=True)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Ogedei persistent dispatcher")
    parser.add_argument("--shadow", action="store_true",
                        help="Shadow mode: read-only, log dispatch decisions")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show claimable tasks without dispatching")
    parser.add_argument("--once", action="store_true",
                        help="Single dispatch cycle then exit")
    parser.add_argument("--agents", nargs="+", default=DISPATCH_AGENTS)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.dry_run:
        store = TaskStore()
        for agent in args.agents:
            depths = store.get_queue_depth(agent)
            tasks = store.get_agent_tasks(agent, status="PENDING", limit=5)
            print(f"{agent}: PENDING={depths['PENDING']} WORKING={depths['WORKING']}")
            for t in tasks:
                print(f"  {t['task_id']} [{t.get('priority','?')}] "
                      f"{t.get('title','')[:60]}")
        store.close()
        return

    dispatcher = OgedeiDispatcher(shadow=args.shadow, agents=args.agents)

    loop = asyncio.new_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, dispatcher.request_shutdown)

    if args.once:
        async def _once():
            await dispatcher._dispatch_cycle()
            dispatcher.store.close()
        loop.run_until_complete(_once())
    else:
        loop.run_until_complete(dispatcher.run())

    loop.close()


if __name__ == "__main__":
    main()
