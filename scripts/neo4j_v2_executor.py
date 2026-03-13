#!/usr/bin/env python3
"""
neo4j_v2_executor.py — Asyncio task executor for Neo4j-first task system.

Polls Neo4j for PENDING tasks, claims with fencing tokens, spawns claude-agent,
monitors for stalls/timeouts, and handles completion/failure with structured output.

Architecture:
    - asyncio event loop with Semaphore-based concurrency
    - One extra semaphore slot reserved for child tasks (prevents delegation deadlock)
    - Stall detection: no stdout for threshold period -> SIGTERM -> SIGKILL
    - Lease renewal in background while task executes
    - Orphan recovery on startup

Usage:
    python3 neo4j_v2_executor.py                    # Run executor
    python3 neo4j_v2_executor.py --once             # Single poll cycle
    python3 neo4j_v2_executor.py --dry-run          # Show what would be claimed
    python3 neo4j_v2_executor.py --concurrency 4    # Override concurrency
"""

import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
import queue as _queue
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_v2_core import TaskStore
from neo4j_v2_failure import classify_failure, classify_validation_failure
from neo4j_v2_validator import validate_completion
from neo4j_v2_scorer import score_completed_task, score_failed_task
from neo4j_v2_wal import WAL
from agents_config import AGENTS
from kurultai_paths import (
    CLAUDE_AGENT, AGENTS_DIR, DISPATCH_AGENTS,
    STALE_EXECUTING_SECS, CLAUDE_TIMEOUT,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

POLL_INTERVAL = 30  # seconds between poll cycles
LEASE_MINUTES = 45  # lease duration for claimed tasks
LEASE_RENEW_INTERVAL = 600  # renew lease every 10 minutes
DEFAULT_CONCURRENCY = len(DISPATCH_AGENTS) + 1  # +1 for child tasks
ORPHAN_GRACE_MINUTES = 5  # grace period before recovering orphans

# Stall detection thresholds (from agent-task-handler.py)
STALL_SILENCE_THRESHOLD = 900  # 15 min silence
STALL_MIN_ELAPSED = 900  # check after 15 min
SLOW_SKILL_STALL_SILENCE = 1200  # 20 min for horde skills
SLOW_SKILL_STALL_ELAPSED = 1200
HIGH_PRIORITY_STALL_SILENCE = 1200
HIGH_PRIORITY_STALL_ELAPSED = 1200
PROXY_STALL_SILENCE = 2400  # 40 min for proxy
PROXY_STALL_ELAPSED = 1800

SLOW_SKILLS = {
    '/horde-brainstorming', '/golden-horde', '/horde-implement',
    '/horde-review', '/horde-debug', '/horde-learn', '/horde-swarm',
    '/horde-test', '/systematic-debugging', '/kurultai-health',
    '/code-reviewer',
}

PROXY_ENDPOINTS = ['dashscope.aliyuncs.com', 'openrouter.ai', 'api.z.ai']

# Prompt template additions for delegation
DELEGATION_PROMPT = """
## Delegation

If this task requires specialized work from another agent, you can delegate:

  kurultai-delegate --parent-id {task_id} --title "Subtask title" --prompt "Description..."

Available agents: temujin (implementation), mongke (research), chagatai (docs),
                  jochi (security/review), ogedei (ops)

Check child status: kurultai-task-status <child_task_id>
Read child output:  kurultai-task-output <child_task_id>

Do NOT delegate if you can do the work yourself. Delegation adds latency.
Max depth: {max_depth} (you {can_delegate_msg}).
"""

# ---------------------------------------------------------------------------
# Environment setup (mirrors agent-task-handler.py)
# ---------------------------------------------------------------------------

def _build_env(agent_name: str) -> dict:
    """Build clean execution environment for claude-agent."""
    env = os.environ.copy()
    env.pop('CLAUDECODE', None)
    env['PATH'] = (
        "/Users/kublai/.local/bin:/opt/homebrew/bin:"
        "/usr/local/bin:/usr/bin:/bin:" + env.get('PATH', '')
    )

    # Strip inherited ANTHROPIC_* vars
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
    settings_path = f"{agent_root}/.claude/settings.json"
    try:
        with open(settings_path) as f:
            settings = json.load(f)
        for key, value in settings.get('env', {}).items():
            env[key] = value
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # Validate model
    valid_models = {'claude-opus-4-6', 'claude-sonnet-4-6', 'claude-haiku-4-5'}
    env_model = env.get('ANTHROPIC_MODEL')
    base_url = env.get('ANTHROPIC_BASE_URL', '')
    is_proxy = any(ep in base_url for ep in PROXY_ENDPOINTS)
    if env_model and env_model not in valid_models and not is_proxy:
        env['ANTHROPIC_MODEL'] = 'claude-opus-4-6'

    return env


def _build_prompt(task: dict) -> str:
    """Build the full prompt for claude-agent, including delegation instructions."""
    prompt_parts = []

    # Prior failure context
    failures = task.get('failure_reports', [])
    if failures:
        prompt_parts.append("## Prior Attempts (failed)\n")
        for f in failures:
            prompt_parts.append(
                f"- Attempt {f.get('attempt', '?')}: {f.get('error_class', 'unknown')} — "
                f"{f.get('error_msg', 'no details')}\n"
            )
        prompt_parts.append(
            "\nUse this context to avoid repeating the same failure.\n\n"
        )

    # Skill hint instruction
    skill_hint = task.get('skill_hint', '')
    if skill_hint:
        prompt_parts.append(
            f"**IMPORTANT:** This task has a skill hint. You MUST invoke the Skill tool "
            f"with `{skill_hint}` before starting work.\n\n"
        )

    # Main task content
    prompt_parts.append(f"# Task: {task.get('title', 'Untitled')}\n\n")
    prompt_parts.append(task.get('prompt', task.get('body', '')))

    # Delegation instructions (if depth allows)
    depth = task.get('depth', 0)
    max_depth = 2
    if depth < max_depth:
        remaining = max_depth - depth
        can_msg = f"can delegate (depth {depth}/{max_depth})"
        prompt_parts.append(
            DELEGATION_PROMPT.format(
                task_id=task['task_id'],
                max_depth=max_depth,
                can_delegate_msg=can_msg,
            )
        )

    # Completion requirements
    prompt_parts.append("""
## Completion Requirements

Your output MUST include these three sections:
1. **Problem**: What was the core problem or task?
2. **Solution**: What did you do to solve it?
3. **Rationale**: Why did you choose this approach?

Without these sections, the task will be marked as failed and retried.
""")

    return "\n".join(prompt_parts)


# ---------------------------------------------------------------------------
# Task execution
# ---------------------------------------------------------------------------

async def run_claude_agent(task: dict) -> dict:
    """Spawn claude-agent and monitor for stalls/timeouts.

    Returns dict with keys: success, content, error, return_code, duration_s
    """
    agent_name = task.get('assigned_to', task.get('agent', 'temujin'))
    agent_root = str(AGENTS_DIR / agent_name)
    env = _build_env(agent_name)
    prompt = _build_prompt(task)
    timeout_s = task.get('timeout_s', CLAUDE_TIMEOUT)
    skill_hint = task.get('skill_hint', '')
    priority = task.get('priority', 'normal')

    # Determine stall thresholds
    base_url = env.get('ANTHROPIC_BASE_URL', '')
    is_proxy = any(ep in base_url for ep in PROXY_ENDPOINTS)
    is_slow = (skill_hint in SLOW_SKILLS) or priority == 'high'

    if is_proxy:
        stall_elapsed = PROXY_STALL_ELAPSED
        stall_silence = PROXY_STALL_SILENCE
    elif is_slow:
        stall_elapsed = SLOW_SKILL_STALL_ELAPSED
        stall_silence = SLOW_SKILL_STALL_SILENCE
    else:
        stall_elapsed = STALL_MIN_ELAPSED
        stall_silence = STALL_SILENCE_THRESHOLD

    # Pre-dispatch orphan cleanup: kill stale Claude processes before spawning a new one.
    # Applies to all agents to prevent OOM (temujin historically most affected).
    # Uses --older-minutes=45 to catch processes that launched but haven't been active,
    # without touching processes that are legitimately mid-task (active < 45 min).
    _cleanup_script = Path(__file__).parent / "cleanup-orphan-claude.sh"
    if _cleanup_script.exists():
        try:
            result = subprocess.run(
                ["bash", str(_cleanup_script), "--run", "--older-minutes=45"],
                capture_output=True, text=True, timeout=15,
            )
            if result.stdout.strip():
                logger.info(f"pre-dispatch cleanup ({agent_name}): {result.stdout.strip()[-200:]}")
        except Exception as _e:
            logger.debug(f"pre-dispatch cleanup skipped: {_e}")

    # Build command
    cmd = [str(CLAUDE_AGENT), "--workdir", agent_root, "--effort", "medium", "--", prompt]

    loop = asyncio.get_event_loop()
    start = time.time()

    # Run subprocess in thread to avoid blocking event loop
    def _run():
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=env,
        )

        stdout_chunks = []
        last_output_time = time.time()
        stdout_q = _queue.Queue()

        def _reader(pipe, q):
            for line in pipe:
                q.put(line)
            q.put(None)

        reader_thread = threading.Thread(target=_reader, args=(proc.stdout, stdout_q), daemon=True)
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
                # Drain remaining
                remaining_stderr = proc.stderr.read() if proc.stderr else ""
                return {
                    "success": proc.returncode == 0,
                    "content": "".join(stdout_chunks),
                    "error": remaining_stderr if proc.returncode != 0 else "",
                    "return_code": proc.returncode,
                    "duration_s": time.time() - start,
                }

            # Stall detection
            silence = time.time() - last_output_time
            if elapsed >= stall_elapsed and silence >= stall_silence:
                # Check if session JSONL is still active
                session_active = False
                try:
                    project_slug = agent_root.replace('/', '-').lstrip('-')
                    project_dir = os.path.expanduser(f"~/.claude/projects/{project_slug}")
                    if os.path.isdir(project_dir):
                        now = time.time()
                        for fname in os.listdir(project_dir):
                            if fname.endswith('.jsonl') and now - os.path.getmtime(
                                os.path.join(project_dir, fname)) < 60:
                                session_active = True
                                break
                except Exception:
                    pass

                if session_active:
                    last_output_time = time.time() - (stall_silence - 60)
                    time.sleep(0.5)
                    continue

                logger.warning(
                    f"Stall detected: {agent_name} silent {silence:.0f}s "
                    f"after {elapsed:.0f}s"
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
                    "error": f"STALL: no output for {silence:.0f}s after {elapsed:.0f}s",
                    "return_code": proc.returncode or -1,
                    "duration_s": time.time() - start,
                }

            time.sleep(0.5)

    return await loop.run_in_executor(None, _run)


# ---------------------------------------------------------------------------
# Main executor loop
# ---------------------------------------------------------------------------

class Executor:
    """Asyncio-based task executor."""

    def __init__(self, concurrency: int = DEFAULT_CONCURRENCY,
                 agents: list[str] = None, v2_only: bool = True):
        self.store = TaskStore()
        self.wal = WAL()
        self.concurrency = concurrency
        self.semaphore = asyncio.Semaphore(concurrency)
        self.agents = agents or DISPATCH_AGENTS
        self.v2_only = v2_only
        self.shutdown = asyncio.Event()
        self._active_tasks: dict[str, asyncio.Task] = {}

    async def startup_recovery(self):
        """Recover orphaned tasks on startup."""
        logger.info("Running startup orphan recovery...")
        recovered = self.store.recover_orphans(ORPHAN_GRACE_MINUTES)
        if recovered:
            logger.info(f"Recovered {len(recovered)} orphans: "
                        f"{[t['task_id'] for t in recovered]}")

        # Replay WAL if any buffered operations
        pending = self.wal.pending_count()
        if pending > 0:
            logger.info(f"Replaying {pending} WAL entries...")
            try:
                replayed = self.wal.replay(self.store.driver)
                logger.info(f"Replayed {replayed} WAL entries")
            except Exception as e:
                logger.error(f"WAL replay failed: {e}")

    async def execute_task(self, task: dict):
        """Execute a single task: run claude-agent, validate, complete/fail."""
        task_id = task['task_id']
        claim_epoch = task['claim_epoch']
        agent = task.get('assigned_to', task.get('agent', 'unknown'))

        logger.info(f"Executing {task_id} for {agent} (epoch={claim_epoch})")

        # Start lease renewal background task
        lease_task = asyncio.create_task(
            self._renew_lease_loop(task_id, claim_epoch)
        )

        try:
            result = await run_claude_agent(task)
            duration_s = result.get('duration_s', 0)

            if result['success']:
                # Validate output
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
                        score_completed_task(self.store, task_id, agent, task.get('skill_hint', ''))
                        logger.info(f"Task {task_id} completed in {duration_s:.0f}s")
                    else:
                        logger.error(f"Task {task_id} complete CAS failed: {reason}")
                        error_class, transient = classify_validation_failure(reason)
                        self.store.fail_task(
                            task_id, claim_epoch, error_class, reason, transient
                        )
                else:
                    # Output failed validation
                    reason = parsed.get('reason', 'validation_failed')
                    error_class, transient = classify_validation_failure(reason)
                    self.store.fail_task(
                        task_id, claim_epoch, error_class,
                        f"Output validation failed: {reason}",
                        transient, output_snippet=result['content'][:2000],
                    )
                    self.store.record_execution(task_id, agent, 'validation_failed', duration_s)
                    logger.warning(f"Task {task_id} failed validation: {reason}")
            else:
                # Process failure
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
                self.store.record_execution(task_id, agent, f'failed:{error_class}', duration_s)
                if new_status == 'FAILED':
                    score_failed_task(self.store, task_id, agent, task.get('skill_hint', ''))
                logger.warning(
                    f"Task {task_id} failed: {error_class} -> {new_status} "
                    f"(transient={transient})"
                )

        except Exception as e:
            logger.exception(f"Unexpected error executing {task_id}")
            try:
                self.store.fail_task(
                    task_id, claim_epoch, "EXECUTOR_ERROR",
                    str(e), is_transient=True,
                )
            except Exception:
                logger.exception(f"Failed to record failure for {task_id}")
        finally:
            lease_task.cancel()
            self._active_tasks.pop(task_id, None)

    async def _renew_lease_loop(self, task_id: str, claim_epoch: int):
        """Periodically renew lease while task is executing."""
        try:
            while True:
                await asyncio.sleep(LEASE_RENEW_INTERVAL)
                ok = self.store.renew_lease(task_id, claim_epoch, LEASE_MINUTES)
                if ok:
                    logger.debug(f"Lease renewed for {task_id}")
                else:
                    logger.warning(f"Lease renewal failed for {task_id} — may have been recovered")
                    break
        except asyncio.CancelledError:
            pass

    async def run_with_semaphore(self, task: dict):
        """Execute task with semaphore-limited concurrency."""
        async with self.semaphore:
            await self.execute_task(task)

    async def poll_cycle(self):
        """Single poll cycle: try to claim tasks for each agent."""
        for agent in self.agents:
            if self.shutdown.is_set():
                break
            # Check if we have concurrency available
            if self.semaphore._value <= 0:
                break

            try:
                task = self.store.claim_task(agent, LEASE_MINUTES)
            except Exception as e:
                logger.error(f"Claim failed for {agent}: {e}")
                continue

            if task is None:
                continue

            task_id = task['task_id']
            if task_id in self._active_tasks:
                logger.warning(f"Task {task_id} already active, skipping")
                continue

            logger.info(f"Claimed {task_id} for {agent}")
            t = asyncio.create_task(self.run_with_semaphore(task))
            self._active_tasks[task_id] = t

    async def main_loop(self):
        """Main executor loop."""
        logger.info(
            f"Starting v2 executor: agents={self.agents}, "
            f"concurrency={self.concurrency}, poll={POLL_INTERVAL}s"
        )

        await self.startup_recovery()

        while not self.shutdown.is_set():
            try:
                await self.poll_cycle()
            except Exception as e:
                logger.exception(f"Poll cycle error: {e}")

            try:
                await asyncio.wait_for(
                    self.shutdown.wait(), timeout=POLL_INTERVAL
                )
                break  # Shutdown requested
            except asyncio.TimeoutError:
                pass  # Normal: poll interval elapsed

        # Wait for active tasks to finish
        if self._active_tasks:
            logger.info(f"Waiting for {len(self._active_tasks)} active tasks...")
            await asyncio.gather(*self._active_tasks.values(), return_exceptions=True)

        self.store.close()
        logger.info("Executor shut down")

    def request_shutdown(self):
        """Request graceful shutdown."""
        self.shutdown.set()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Neo4j v2 task executor")
    parser.add_argument("--once", action="store_true", help="Single poll cycle then exit")
    parser.add_argument("--dry-run", action="store_true", help="Show claimable tasks without claiming")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
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
                print(f"  {t['task_id']} [{t.get('priority','?')}] {t.get('title','')[:60]}")
        store.close()
        return

    executor = Executor(concurrency=args.concurrency, agents=args.agents)

    # Handle signals for graceful shutdown
    loop = asyncio.new_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, executor.request_shutdown)

    if args.once:
        async def _once():
            await executor.startup_recovery()
            await executor.poll_cycle()
            # Wait briefly for any started tasks
            if executor._active_tasks:
                await asyncio.gather(*executor._active_tasks.values(), return_exceptions=True)
            executor.store.close()
        loop.run_until_complete(_once())
    else:
        loop.run_until_complete(executor.main_loop())

    loop.close()


if __name__ == "__main__":
    main()
