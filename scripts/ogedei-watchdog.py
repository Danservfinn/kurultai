#!/usr/bin/env python3
"""
Ogedei Watchdog — Persistent quality-assurance daemon for the Kurultai.

Runs every 30 seconds between tock cycles. Seventeen checks per cycle:
  1. check_watcher_alive()         — pgrep neo4j_v2_executor + log mtime
  2. check_stalled_tasks()         — .executing.md files > 15 min old
  3. verify_recent_completions()   — new .done.md → check for real Claude Code execution + quality gate
  4. periodic_queue_audit()        — full queue_audit.audit() every 30 min
  5. cleanup_malformed()           — remove .executing.completed.done artifacts > 24h
  6. check_reflection_pipeline()   — reflection-status.json age + step timing
  7. check_memory_health()         — memory_audit.py every 30 min (contamination, bloat, rules)
  8. check_routing_drift()         — keyword vs actual routing drift every 30 min
  9. check_agent_failure_rates()   — 1h failure rate per agent, writes health flags every 5 min
  9b. check_credential_failures()  — AUTH/PROXY_AUTH detection, O006 auth_health_preflight.py trigger
 10. check_queue_balance()         — auto-redistribute tasks from overloaded to underloaded agents
 11. check_cascade_risk()          — detect cascade failure patterns every 10 min
 12. check_quality_gate()          — verify completion quality on recent .done.md files
 13. update_self_healing_score()   — track and report self-healing metrics every hour
 14. check_watchdog_health()       — internal watchdog health check
 15. check_circuit_breaker_health() — proactive circuit breaker state transitions
 16. check_git_operations()        — autonomous git activity monitoring
 17. check_proactive_health_patrol() — O003/O006 activation: fleet health patrol when idle
 18. check_model_drift()             — O001 detection: session model vs config model mismatch

False Positive Prevention:
  The escalation system skips tasks with terminal state patterns in their filenames:
  - .gate-passed.      — Gate audit passed, task is done
  - .resolved.         — Task was resolved
  - .false-positive    — Previously marked as false positive
  - .completed.done.md — Fully completed
  - .verified.done.md  — Verified completion
  - .bypass.done.md    — Bypassed gate

Usage:
    python3 ogedei-watchdog.py --once    # single cycle
    python3 ogedei-watchdog.py --daemon  # persistent mode (30s poll)
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event

sys.path.insert(0, str(Path(__file__).parent))
from json_state import locked_json_read, locked_json_update
from kurultai_paths import AGENTS_DIR, LOGS_DIR


def check_agent_credentials(agent: str) -> tuple[bool, str | None]:
    """Check if agent has valid API credentials.

    Returns (is_valid, error_message) tuple:
    - is_valid: True if credentials are valid
    - error_message: Description of issue if invalid, None if valid

    Credential model (2026-03-09):
    1. OAuth for Anthropic (no stored token) — check credentials.json
    2. Centralized vault (provider.env) for fallbacks
    3. Per-agent tokens in settings.json (legacy, being phased out)

    Prevents escalation to agents with invalid credentials (credential crisis guard).
    """
    try:
        # 1. Check OAuth status (primary auth method for Anthropic)
        _claude_creds_path = Path.home() / ".claude" / "credentials.json"
        if _claude_creds_path.exists():
            try:
                with open(_claude_creds_path, 'r') as f:
                    _creds = json.load(f)
                if _creds.get('loggedIn') and _creds.get('authMethod') == 'oauth_token':
                    # OAuth is active — credentials are valid
                    return True, None
            except (json.JSONDecodeError, IOError):
                pass  # Fall through to vault check

        # 2. Check centralized vault for fallback credentials
        _vault_path = Path.home() / ".openclaw" / "credentials" / "provider.env"
        if _vault_path.exists():
            try:
                with open(_vault_path, 'r') as f:
                    _vault_content = f.read()
                # Check for Z.AI or Alibaba fallback tokens
                _has_zai = 'ZAI_AUTH_TOKEN=' in _vault_content and 'b5b1f953' in _vault_content
                _has_alibaba = 'ALIBABA_AUTH_TOKEN=' in _vault_content and 'sk-sp-' in _vault_content
                if _has_zai or _has_alibaba:
                    return True, None  # Vault has valid fallback credentials
            except IOError:
                pass  # Fall through to legacy check

        # 3. Legacy: Check for per-agent token in settings.json
        agent_root = AGENTS_DIR / agent
        settings_path = agent_root / ".claude" / "settings.json"

        if not settings_path.exists():
            return False, f"No settings.json found for {agent}"

        with open(settings_path, 'r') as f:
            settings = json.load(f)

        # Check for ANTHROPIC_AUTH_TOKEN in env (Claude Code format)
        auth_token = None
        if 'env' in settings:
            auth_token = settings['env'].get('ANTHROPIC_AUTH_TOKEN')

        # Also check direct apiKey field
        if not auth_token:
            auth_token = settings.get('apiKey')

        if not auth_token:
            return False, f"No ANTHROPIC_AUTH_TOKEN found"

        # Validate token format - accept Anthropic, Z.AI, or Alibaba tokens
        _is_anthropic = auth_token.startswith('sk-ant-')
        _is_zai = len(auth_token.split('.')) == 2 and len(auth_token.split('.')[0]) == 32
        _is_alibaba = auth_token.startswith('sk-sp-') or auth_token.startswith('sk-')

        if not (_is_anthropic or _is_zai or _is_alibaba):
            return False, f"Invalid token: {auth_token[:10]}... (expected sk-ant-*, Z.AI, or Alibaba)"

        return True, None

    except Exception as e:
        return False, f"Credential check error: {e}"

# Force unbuffered output for launchd
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Configuration
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Configuration
SCRIPTS_DIR = Path(__file__).parent
STATE_FILE = LOGS_DIR / "ogedei-watchdog-state.json"
LOG_FILE = LOGS_DIR / "ogedei-watchdog.log"
WATCHER_PLIST = "com.kurultai.v2-executor"
WATCHER_LOG = LOGS_DIR / "neo4j-v2-executor.log"

POLL_INTERVAL = 30        # seconds
STALE_EXECUTING_SECS = 900  # 15 minutes
WATCHER_LOG_MAX_AGE = 300   # 5 minutes
MALFORMED_MAX_AGE = 86400   # 24 hours
QUEUE_AUDIT_INTERVAL = 1800 # 30 minutes
MEMORY_AUDIT_INTERVAL = 1800 # 30 minutes
STALL_WARN_COOLDOWN = 600   # 10 minutes between repeated warnings for same file
REFLECTION_MAX_AGE = 4500   # 75 minutes — cron runs at :02, allow buffer
REFLECTION_STATUS = LOGS_DIR / "reflection-status.json"
REFLECTION_STEP_TIMING = LOGS_DIR / "reflection-step-timing.json"

# ============================================================
# P0 Self-Healing: Tiered Stale Task Recovery
# ============================================================
# Tier 1 (900s):  Log warning, check process liveness
# Tier 2 (1800s): Verify PID dead → clear lock → requeue
# Tier 3 (3600s): Verify PID dead + check completion → escalate if truly stuck
TIER_WARN_S = 900          # 15 minutes - warn only
TIER_RECOVER_S = 1800      # 30 minutes - auto-recover if PID dead
TIER_ESCALATE_S = 3600     # 60 minutes - escalate only if PID dead

# Recovery tracking to prevent thrashing
_recovery_cooldowns: dict[str, float] = {}  # task_path -> last recovery time
REFLECTION_STATUS = LOGS_DIR / "reflection-status.json"
REFLECTION_STEP_TIMING = LOGS_DIR / "reflection-step-timing.json"

# ============================================================
# False Positive Prevention: Skip patterns for escalation
# ============================================================
# Tasks matching these patterns are already resolved and should NOT be escalated.
# This prevents circular escalation chains where completed tasks get flagged as stale.
SKIP_PATTERNS = [
    '.gate-passed.',      # Gate audit passed, task is done
    '.resolved.',         # Task was resolved
    '.false-positive',    # Previously marked as false positive
    '.completed.done.md', # Fully completed
    '.verified.done.md',  # Verified completion
    '.bypass.done.md',    # Bypassed gate
]

AGENTS = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei", "tolui"]

stop_event = Event()
# Track last warning time per stalled file to avoid spamming
_stall_warned_at: dict[str, float] = {}


def log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {level}: {msg}"
    # stdout is captured by launchd → LOG_FILE already; no direct write needed
    print(line)


def load_state():
    return locked_json_read(str(STATE_FILE), default={
        "last_audit": 0,
        "cycles": 0,
        "last_cycle": None,
        "watcher_restarts": 0,
        "stalled_warnings": 0,
        "fakes_detected": 0,
        "malformed_cleaned": 0,
        "audit_result": {},
        "stall_escalations": {},  # Persist escalation timestamps to prevent re-escalation after watchdog restart
    })


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with locked_json_update(str(STATE_FILE)) as data:
        data.clear()
        data.update(state)


# ============================================================
# Circuit breaker for agent health (loaded after log is available)
# ============================================================
try:
    from circuit_breaker import AgentCircuitBreaker
    _circuit_breaker = AgentCircuitBreaker()
except Exception as e:
    log(f"Circuit breaker init failed (non-fatal): {e}", "WARN")
    _circuit_breaker = None


# ============================================================
# Check 1: Is task-watcher alive?
# ============================================================
def check_watcher_alive(state):
    """Verify neo4j_v2_executor is running and its log is fresh."""
    issues = []

    # Check process
    try:
        result = subprocess.run(
            ["pgrep", "-f", "neo4j_v2_executor"],
            capture_output=True, text=True, timeout=5
        )
        alive = result.returncode == 0
    except Exception:
        alive = False

    if not alive:
        log("WATCHER DOWN — attempting restart via launchctl", "WARN")
        issues.append("neo4j_v2_executor not running")
        try:
            result = subprocess.run(
                ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{WATCHER_PLIST}"],
                capture_output=True, text=True, timeout=15
            )
            success = result.returncode == 0
            state["watcher_restarts"] = state.get("watcher_restarts", 0) + 1
            log("Restart issued via launchctl kickstart")
            record_gateway_restart(success)
        except Exception as e:
            log(f"Failed to restart watcher: {e}", "ERROR")
            record_gateway_restart(False)
        return issues

    # Check log freshness
    if WATCHER_LOG.exists():
        age = time.time() - WATCHER_LOG.stat().st_mtime
        if age > WATCHER_LOG_MAX_AGE:
            log(f"WATCHER LOG STALE — {age:.0f}s old (threshold: {WATCHER_LOG_MAX_AGE}s)", "WARN")
            issues.append(f"neo4j_v2_executor log stale ({age:.0f}s)")

    return issues


# ============================================================
# Check 2: Stalled .executing tasks with Tiered Recovery (P0 Self-Healing)
# ============================================================

def verify_process_dead(task_path: Path) -> bool:
    """Verify the PID is actually dead before clearing lock."""
    pid_file = task_path.with_suffix(".pid")
    if not pid_file.exists():
        return True
    try:
        pid_str = pid_file.read_text().strip()
        pid = int(pid_str)
    except (ValueError, OSError):
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            if "claude-agent" in result.stdout or "claude" in result.stdout.lower():
                return False
            log(f"Orphaned PID {pid} for {task_path.name}")
            return True
    except Exception:
        pass
    return False


def recover_task(task_path: Path, agent: str, age_s: int, state: dict) -> bool:
    """Clear locks and requeue the task."""
    try:
        task_name = task_path.name
        base_name = task_name.replace(".executing.md", ".md")
        task_path.rename(task_path.parent / base_name)
        pid_file = task_path.with_suffix(".pid")
        if pid_file.exists():
            pid_file.unlink()
        state["tasks_recovered"] = state.get("tasks_recovered", 0) + 1
        _recovery_cooldowns[str(task_path)] = time.time()
        log(f"RECOVERED: {agent}/{base_name} (was {age_s:.0f}s old)")
        return True
    except Exception as e:
        log(f"RECOVERY FAILED for {agent}/{task_path.name}: {e}", "ERROR")
        return False


def escalate_to_kublai(task_path: Path, agent: str, age_s: int) -> bool:
    """Create high-priority task for Kublai investigation.

    SAFETY CHECKS (prevents escalation loops):
    - Skip tasks with terminal state patterns (.gate-passed., .resolved., .false-positive, etc.)
    - Skip .resolved tasks (already resolved)
    - Skip escalation tasks (ESCALATE-*, quality-escalate-*)
    - Check escalation depth (max 2 levels)
    - Skip recently modified files (< 5 min old)
    - Check if task already has a verified completion
    - Credential crisis guard (check kublai can execute)
    """
    try:
        workspace = Path("/Users/kublai/.openclaw/agents/kublai/tasks")
        workspace.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        task_name = task_path.name.replace(".executing.md", "")

        # SAFETY CHECK 0: Skip tasks with terminal state patterns
        # This prevents false positive escalations of already-completed tasks
        # where the completion state is embedded in the filename itself
        for pattern in SKIP_PATTERNS:
            if pattern in task_name:
                log(f"SKIP: {agent}/{task_name} - matches pattern '{pattern}' (not escalating)", "INFO")
                # Clean up stale .executing.md artifact
                try:
                    task_path.unlink()
                    pid_file = task_path.with_suffix(".pid")
                    if pid_file.exists():
                        pid_file.unlink()
                    log(f"CLEANED: stale artifact {agent}/{task_path.name}")
                except Exception as e:
                    log(f"Cleanup failed for {agent}/{task_path.name}: {e}", "ERROR")
                return False

        # SAFETY CHECK 1: Skip .resolved tasks (already resolved)
        if ".resolved." in task_name or task_name.endswith(".resolved"):
            log(f"SKIP: {agent}/{task_name} - contains .resolved (not escalating)", "INFO")
            return False

        # SAFETY CHECK 2: Skip escalation tasks (prevent meta-escalations)
        # This includes both stale-task escalations and quality gate escalations
        if task_name.startswith("ESCALATE-stale-task-") or task_name.startswith("quality-escalate-"):
            log(f"SKIP: {agent}/{task_name} - is an escalation task (not escalating)", "INFO")
            return False

        # SAFETY CHECK 3: Escalation depth limit (max 2 levels)
        # Count how many times "escalate" appears in the task name (case-insensitive)
        escalation_count = task_name.lower().count("escalate")
        if escalation_count >= 2:
            log(f"SKIP: {agent}/{task_name} - escalation depth {escalation_count} >= 2 (not escalating)", "INFO")
            return False

        # SAFETY CHECK 4: Skip recently modified files (< 5 min = 300 seconds)
        # The age_s parameter is how long the task has been "stale", not file mtime
        # Check the actual file modification time
        file_age = time.time() - task_path.stat().st_mtime
        if file_age < 300:
            log(f"SKIP: {agent}/{task_name} - modified {file_age:.0f}s ago < 300s threshold (not escalating)", "INFO")
            return False

        # SAFETY CHECK 5: Skip administrative fix-up tasks
        # Tasks like "critical-fix-resolution-*" are one-time cleanup operations
        # that should never be escalated, as they create false-positive cascades
        if task_name.startswith("critical-fix-resolution-") or task_name.startswith("fix-resolution-"):
            log(f"SKIP: {agent}/{task_name} - is an administrative fix-up task (not escalating)", "INFO")
            return False

        # SAFETY CHECK 6: Check if task already has a verified completion
        # This prevents false positive escalations of completed tasks
        completion_check = is_task_already_completed(task_path, agent)
        if completion_check:
            log(f"SKIP: {agent}/{task_name} - already completed (not escalating)", "INFO")
            # Clean up stale .executing.md artifact
            try:
                task_path.unlink()
                pid_file = task_path.with_suffix(".pid")
                if pid_file.exists():
                    pid_file.unlink()
                log(f"CLEANED: stale artifact {agent}/{task_path.name}")
            except Exception as e:
                log(f"Cleanup failed for {agent}/{task_path.name}: {e}", "ERROR")
            return False

        # SAFETY CHECK 6: Credential crisis guard — check if escalation target (kublai) has valid credentials
        # Prevents piling up escalation tasks when kublai cannot execute them
        kublai_creds_valid, creds_error = check_agent_credentials("kublai")
        if not kublai_creds_valid:
            log(f"SKIP_ESCALATION: kublai has invalid credentials ({creds_error}) — NOT escalating {agent}/{task_name}", "WARN")
            log(f"  Reason: Escalation would create a task kublai cannot execute (credential crisis guard)", "INFO")
            return False

        escalation_file = workspace / f"ESCALATE-stale-task-{agent}-{task_name}-{timestamp}.md"
        task_content = task_path.read_text()[:500] if task_path.exists() else "(file not found)"
        escalation_content = f"""---
agent: kublai
priority: critical
created: {datetime.now().isoformat()}
task_type: escalation
source: ogedei-watchdog
original_task: {agent}/{task_name}
stalled_age_seconds: {age_s}
---

# Escalation: Stale Task Recovery

**Original Task:** {agent}/{task_name}
**Stalled For:** {age_s:.0f}s ({age_s // 60} min)

Investigate why this task is stuck and re-queue or cancel as appropriate.
Threshold: {TIER_ESCALATE_S}s
"""
        escalation_file.write_text(escalation_content)
        log(f"ESCALATED to Kublai: {escalation_file.name}")
        return True
    except Exception as e:
        log(f"ESCALATION FAILED: {e}", "ERROR")
        return False


def _check_task_frontmatter_for_completion(task_file: Path) -> bool:
    """Check task file frontmatter for completion indicators.

    Prevents false-positive escalations by checking if a task is already
    verified, graded, or resolved based on frontmatter content.

    Args:
        task_file: Path to the task file (.executing.md or base task)

    Returns:
        True if task has completion markers (grade A-F or resolved: true)
    """
    try:
        content = task_file.read_text()
    except (OSError, UnicodeDecodeError):
        return False

    # Extract frontmatter (between --- markers)
    frontmatter_match = content.split('---', 2)
    if len(frontmatter_match) < 3:
        return False

    frontmatter = frontmatter_match[1].lower()

    # Check for grade: A-F (indicates verified completion)
    # Pattern: "grade: a" through "grade: f" (case-insensitive)
    import re
    if re.search(r'^grade:\s*[a-f]', frontmatter, re.MULTILINE):
        return True

    # Check for resolved: true
    if re.search(r'^resolved:\s*true', frontmatter, re.MULTILINE):
        return True

    return False


def _extract_task_timeout(task_file: Path) -> int:
    """Extract the timeout value from a task file's frontmatter.

    Args:
        task_file: Path to the task file (.executing.md or base task)

    Returns:
        Timeout value in seconds. Defaults to 7200s (2 hours) if not specified.
    """
    try:
        content = task_file.read_text()
    except (OSError, UnicodeDecodeError):
        return 7200  # Default timeout

    # Extract frontmatter (between --- markers)
    frontmatter_match = content.split('---', 2)
    if len(frontmatter_match) < 3:
        return 7200  # Default timeout

    frontmatter = frontmatter_match[1]

    # Check for timeout: value (case-insensitive)
    import re
    timeout_match = re.search(r'^timeout:\s*(\d+)', frontmatter, re.MULTILINE | re.IGNORECASE)
    if timeout_match:
        try:
            return int(timeout_match.group(1))
        except ValueError:
            return 7200  # Default timeout on parse error

    return 7200  # Default timeout


def is_task_already_completed(executing_file: Path, agent: str) -> bool:
    """Check if a task has a corresponding .done.md completion marker.

    For a file like 'task-name.executing.md', checks if any variant
    ending with '.done.md' exists in the same directory.

    This prevents false positive escalations when .executing.md files
    are left as stale artifacts after task completion.

    IMPORTANT: Handles nested escalation filenames by stripping all
    ESCALATE-stale-task-{agent}- prefixes before checking for completions.
    This prevents false positives when escalation tasks themselves go stale.

    Args:
        executing_file: Path to the .executing.md file
        agent: Agent name (e.g., 'mongke', 'temujin')

    Returns:
        True if a corresponding .done.md file exists, False otherwise
    """
    if not executing_file.name.endswith(".executing.md"):
        return False

    # Get the base task name without .executing.md
    # e.g., 'tock-qmd-merge-123.verified' from 'tock-qmd-merge-123.verified.executing.md'
    base_name = executing_file.name[:-len(".executing.md")]

    # Strip all nested escalation prefixes to get the actual task ID
    # Example: "ESCALATE-stale-task-mongke-ESCALATE-stale-task-kublai-task-123"
    # becomes "task-123" after stripping all ESCALATE-stale-task-{agent}- prefixes
    # Also strip timestamps added by escalation: "-20260308-175342"
    import re
    original_base = base_name
    while True:
        new_base = re.sub(r'^ESCALATE-stale-task-[a-z]+-', '', base_name, flags=re.IGNORECASE)
        if new_base == base_name:  # No more prefixes to strip
            break
        base_name = new_base

    # Strip timestamp suffix added by escalation (format: -YYYYMMDD-HHMMSS)
    # Example: "task-123.verified-20260308-175342" -> "task-123.verified"
    base_name = re.sub(r'-\d{8}-\d{6}$', '', base_name)

    # EARLY RETURN: If base_name already ends with a completion marker, task is done
    # This handles cases like "task.completed.done.md.executing.md" where stripping
    # .executing.md leaves "task.completed.done.md" - already a completed state
    COMPLETION_SUFFIXES = (
        '.done.md',
        '.completed.done.md',
        '.verified.done.md',
        '.failed.done.md',
        '.no_output.done.md',
        '.gate-passed.done.md',
        '.bypass.done.md',
        '.resolved.done.md',
        '.resolved.md',
        '.false-positive.resolved.md',
        '.false-positive.done.md',
        '.unverified.done.md',
        '.cancelled.md',
        '.obsolete.md',
    )
    if base_name.endswith(COMPLETION_SUFFIXES):
        log(f"SKIP: {executing_file.name} already has completion suffix '{base_name}' (not escalating)", "DEBUG")
        return True

    tasks_dir = executing_file.parent

    # CONTENT-BASED PRE-FILTER: Check frontmatter of executing file itself
    # This prevents false-positive escalations when tasks have completion markers
    # in their frontmatter (grade: A-F, resolved: true) even if a .done.md file
    # hasn't been created yet. See: mongke/workspace/stale-task-escalation-cost-analysis-2026-03-09.md
    if _check_task_frontmatter_for_completion(executing_file):
        log(f"SKIP: {executing_file.name} has completion markers in frontmatter (grade/resolved)", "DEBUG")
        return True

    # Check for any .done.md variant of this task
    # Patterns to check:
    # - base_name.done.md
    # - base_name.verified.done.md
    # - base_name.verified.verified.done.md
    # - base_name.completed.done.md
    # - base_name.no_output.done.md
    # - base_name.failed.done.md
    # - base_name.gate-passed.done.md
    # - base_name.bypass.done.md
    # - base_name.resolved.done.md
    # - base_name.unverified.done.md (chagatai pattern)
    # - base_name.unverified.unverified.done.md (double-unverified)
    completion_patterns = [
        f"{base_name}.done.md",
        f"{base_name}.verified.done.md",
        f"{base_name}.verified.verified.done.md",
        f"{base_name}.completed.done.md",
        f"{base_name}.no_output.done.md",
        f"{base_name}.failed.done.md",
        # Gate completion states
        f"{base_name}.gate-passed.done.md",
        f"{base_name}.bypass.done.md",
        f"{base_name}.resolved.done.md",
        # Terminal states for resolved escalation tasks (k010)
        f"{base_name}.resolved.md",
        f"{base_name}.resolved.executing.md",
        f"{base_name}.false-positive.resolved.md",
        f"{base_name}.false-positive.done.md",  # Fix: false-positive escalations marked as .done.md not .resolved.md
        # Chagatai unverified patterns (fix for mongke cost-analysis-2026-03-09)
        f"{base_name}.unverified.done.md",
        f"{base_name}.unverified.unverified.done.md",
    ]

    for pattern in completion_patterns:
        candidate = tasks_dir / pattern
        if candidate.exists() and candidate.is_file():
            return True

    return False


# ============================================================
# Original check_stalled_tasks below (updated with tiered recovery)
# ============================================================
def check_stalled_tasks(state):
    """Find and recover .executing.md files based on tiered policy.

    FAST-TRACK (60s+): 0 bytes + dead PID -> immediate recovery (no wait)
    Tier 1 (900s):  Log warning with cooldown
    Tier 2 (1800s to escalate_threshold): Verify PID dead -> clear lock -> requeue
    Tier 3 (escalate_threshold+): Verify PID dead + check completion -> escalate

    IMPORTANT: Escalation threshold is TIMEOUT-AWARE:
    - Extracts task timeout from frontmatter (defaults to 7200s)
    - Escalate threshold = task_timeout * 1.5 (150% of configured timeout)
    - Example: task with timeout=7200s escalates at 10800s (3 hours)

    Before escalating (Tier 3):
    1. Checks if PID is still alive - skips escalation if active (prevents false positives)
    2. Checks if a corresponding .done.md file exists - cleans up stale artifact if present
    Only escalates if PID is dead AND no completion marker exists.
    """
    issues = []
    now = time.time()

    # Load persisted escalation timestamps to prevent re-escalation after watchdog restart
    persisted_escalations = state.get("stall_escalations", {})
    if persisted_escalations:
        log(f"Loaded {len(persisted_escalations)} persisted escalation cooldown(s)", "INFO")
    # Prune old entries (>24h) and merge into in-memory cooldowns
    pruned = 0
    for key, ts in list(persisted_escalations.items()):
        if now - ts > 86400:  # Remove entries older than 24 hours
            del persisted_escalations[key]
            pruned += 1
        else:
            _recovery_cooldowns[key] = ts
    if pruned:
        log(f"Pruned {pruned} stale escalation cooldown(s) (>24h)", "INFO")

    for agent in AGENTS:
        tasks_dir = AGENTS_DIR / agent / "tasks"
        if not tasks_dir.exists():
            continue
        for f in tasks_dir.iterdir():
            name = f.name
            if not name.endswith(".executing.md"):
                continue
            # Skip files with completion status markers - these are not actually stalled
            # Patterns: .verified.done.md.executing.md, .completed.done.md.executing.md,
            #           .no_output.done.md.executing.md, .failed.done.md.executing.md,
            #           .done.md.executing.md, .failed.md.executing.md, .completed.md.executing.md,
            #           .resolved.md.executing.md (resolved escalation tasks)
            #           .gate-passed.done.md.executing.md, .bypass.done.md.executing.md
            # IMPORTANT: Never escalate escalation tasks - prevents infinite loops
            # This includes both stale-task escalations (ESCALATE-stale-task-*) and quality escalations (quality-escalate-*)
            if name.startswith("ESCALATE-") or name.startswith("quality-escalate-"):
                continue
            # IMPORTANT: Never escalate administrative fix-up tasks - prevents false-positive cascades
            # These are one-time cleanup operations (critical-fix-resolution-*, fix-resolution-*)
            if name.startswith("critical-fix-resolution-") or name.startswith("fix-resolution-"):
                continue
            # EARLY SKIP: Check for terminal state patterns anywhere in filename (not just suffix)
            # This catches tasks like "task.gate-passed.done.md.executing.md" where the pattern
            # is embedded in the middle of the filename
            if any(pattern in name for pattern in SKIP_PATTERNS):
                continue
            if any(name.endswith(pattern) for pattern in [
                ".verified.done.md.executing.md",
                ".completed.done.md.executing.md",
                ".no_output.done.md.executing.md",
                ".failed.done.md.executing.md",
                ".done.md.executing.md",
                ".failed.md.executing.md",
                ".completed.md.executing.md",
                ".resolved.md.executing.md",  # Prevent false positive escalations on resolved tasks
                ".gate-passed.done.md.executing.md",  # Gate passed tasks
                ".bypass.done.md.executing.md",  # Bypassed tasks
                ".unverified.done.md.executing.md",  # Chagatai unverified tasks (fix mongke-2026-03-09)
                ".unverified.unverified.done.md.executing.md",  # Double-unverified
            ]):
                continue
            if not f.is_file():
                continue
            try:
                age = now - f.stat().st_mtime
            except OSError:
                continue

            if age < TIER_WARN_S:
                continue

            key = f"{agent}/{name}"
            task_path = f

            # FAST-TRACK: Empty output with dead PID = immediate recovery
            # Tasks that produce 0 bytes with a dead process are clear failures
            # Don't wait for age thresholds - recover immediately to reduce queue blockage
            try:
                file_size = f.stat().st_size
                if file_size == 0 and age >= 60:  # At least 1 min old + 0 bytes = dead
                    if verify_process_dead(task_path):
                        log(f"FAST-TRACK RECOVER: {key} - 0 bytes, PID dead, age={age:.0f}s", "WARN")
                        if recover_task(task_path, agent, age, state):
                            issues.append(f"{key} fast-track recovered (0 bytes)")
                            state["fast_track_recovered"] = state.get("fast_track_recovered", 0) + 1
                            continue  # Skip normal tier processing
                        else:
                            issues.append(f"{key} fast-track recovery failed")
            except OSError:
                pass

            # Extract task timeout for timeout-aware escalation
            # Default to 7200s (2 hours) if not specified in frontmatter
            task_timeout = _extract_task_timeout(task_path)
            escalate_threshold = int(task_timeout * 1.5)  # 150% of configured timeout

            # Tier 1 (900-1800s): Warning only
            if age < TIER_RECOVER_S:
                last_warned = _stall_warned_at.get(key, 0)
                if (now - last_warned) >= STALL_WARN_COOLDOWN:
                    log(f"STALLED: {key} - {age:.0f}s old (Tier 1, timeout={task_timeout}s)", "WARN")
                    _stall_warned_at[key] = now
                    state["stalled_warnings"] = state.get("stalled_warnings", 0) + 1
                issues.append(f"{key} stalled {age:.0f}s")

            # Tier 2 (1800s to escalate_threshold): Attempt recovery if PID dead
            elif age < escalate_threshold:
                last_recovery = _recovery_cooldowns.get(key, 0)
                if (now - last_recovery) < STALL_WARN_COOLDOWN:
                    issues.append(f"{key} stalled {age:.0f}s (cooldown)")
                    continue

                if verify_process_dead(task_path):
                    log(f"RECOVERING: {key} - {age:.0f}s old (Tier 2, timeout={task_timeout}s)", "WARN")
                    if recover_task(task_path, agent, age, state):
                        issues.append(f"{key} recovered after {age:.0f}s")
                        _stall_warned_at.pop(key, None)
                    else:
                        issues.append(f"{key} recovery failed")
                else:
                    log(f"STALLED: {key} - {age:.0f}s old (Tier 2: PID alive, timeout={task_timeout}s)", "WARN")
                    issues.append(f"{key} stalled {age:.0f}s (alive)")

            # Tier 3 (escalate_threshold+): Escalate to Kublai
            # Only triggers after 150% of task's configured timeout
            else:
                last_esc = _recovery_cooldowns.get(f"{key}_escalation", 0)
                if (now - last_esc) < 3600:
                    issues.append(f"{key} stalled {age:.0f}s (escalated)")
                    continue

                # PID ALIVENESS CHECK: Skip escalation if process is still running
                # This prevents false positive escalations for actively executing tasks
                if not verify_process_dead(task_path):
                    log(f"SKIP: {key} - {age:.0f}s old (Tier 3: PID alive, not escalating)", "INFO")
                    state["stall_skips_alive"] = state.get("stall_skips_alive", 0) + 1
                    issues.append(f"{key} stalled {age:.0f}s (alive)")
                    continue

                # Check if task is already completed before escalating
                # This prevents false positive escalations for tasks with .done.md markers
                if is_task_already_completed(task_path, agent):
                    log(f"SKIP: {key} - already has .done.md marker (not escalating)", "INFO")
                    state["stall_skips_completed"] = state.get("stall_skips_completed", 0) + 1
                    # Optionally clean up the stale .executing.md file
                    try:
                        task_path.unlink()
                        log(f"CLEANED: stale .executing.md for completed task: {key}", "INFO")
                        state["stall_cleaned_artifacts"] = state.get("stall_cleaned_artifacts", 0) + 1
                    except OSError:
                        pass
                    continue

                log(f"ESCALATING: {key} - {age:.0f}s old (Tier 3, timeout={task_timeout}s, threshold={escalate_threshold}s)", "ERROR")
                if escalate_to_kublai(task_path, agent, age):
                    escalation_key = f"{key}_escalation"
                    _recovery_cooldowns[escalation_key] = now
                    # Persist to state to survive watchdog restarts
                    state.setdefault("stall_escalations", {})[escalation_key] = now
                    state["stall_escalated"] = state.get("stall_escalated", 0) + 1
                    issues.append(f"{key} escalated")
                else:
                    issues.append(f"{key} escalation failed")

    # Prune cooldown entries
    for key in list(_stall_warned_at):
        parts = key.split("/", 1)
        if len(parts) == 2:
            agent_part, fname = parts
            if not (AGENTS_DIR / agent_part / "tasks" / fname).exists():
                del _stall_warned_at[key]

    return issues


# ============================================================
# Check 3: Verify recent completions are real
# ============================================================
def verify_recent_completions(state):
    """Check new .done.md files for real Claude Code execution markers."""
    issues = []
    now = time.time()
    last_cycle = state.get("last_cycle_epoch", 0)

    # Import queue_audit functions
    try:
        sys.path.insert(0, str(SCRIPTS_DIR))
        from importlib import import_module
        # queue-audit.py has a hyphen, need importlib
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "queue_audit", str(SCRIPTS_DIR / "queue-audit.py")
        )
        qa = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(qa)
    except Exception as e:
        log(f"Cannot import queue-audit: {e}", "ERROR")
        return issues

    for agent in AGENTS:
        tasks_dir = AGENTS_DIR / agent / "tasks"
        if not tasks_dir.exists():
            continue
        for f in tasks_dir.iterdir():
            if ".done.md" not in f.name or not f.is_file():
                continue
            try:
                mtime = f.stat().st_mtime
            except OSError:
                continue
            # Only check files completed since last cycle
            if mtime <= last_cycle:
                continue
            # Skip test tasks
            try:
                content = f.read_text()
            except OSError:
                continue
            if qa.is_test_task(content):
                continue
            # Check result file
            result_path = qa.find_result_file(agent, mtime)
            if qa.is_fake(result_path, done_path=str(f)):
                log(f"FAKE completion: {agent}/{f.name}", "WARN")
                issues.append(f"{agent}/{f.name} fake completion")
                state["fakes_detected"] = state.get("fakes_detected", 0) + 1
                # Re-queue
                if qa.requeue(agent, str(f)):
                    log(f"  Re-queued: {agent}/{f.name}")
                    record_fake_completion_requeued(agent, f.name)

    return issues


# ============================================================
# Check 4: Periodic full queue audit (every 30 min)
# ============================================================
def periodic_queue_audit(state):
    """Run full queue audit every QUEUE_AUDIT_INTERVAL seconds."""
    issues = []
    now = time.time()
    last_audit = state.get("last_audit", 0)

    if (now - last_audit) < QUEUE_AUDIT_INTERVAL:
        return issues

    log("Running periodic queue audit")

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "queue_audit", str(SCRIPTS_DIR / "queue-audit.py")
        )
        qa = importlib.util.module_from_spec(spec)
        # Temporarily set sys.argv for audit() which checks --dry-run
        old_argv = sys.argv
        sys.argv = ["queue-audit.py"]
        spec.loader.exec_module(qa)
        totals, details = qa.audit()
        sys.argv = old_argv

        state["last_audit"] = now
        state["audit_result"] = totals

        if totals.get("fake_found", 0) > 0:
            log(f"AUDIT: {totals['fake_found']} fakes, {totals['requeued']} requeued")
            issues.append(f"audit found {totals['fake_found']} fakes")

    except Exception as e:
        log(f"Queue audit failed: {e}", "ERROR")
        issues.append(f"audit error: {e}")

    return issues


# ============================================================
# Check 5: Clean up malformed file artifacts
# ============================================================
def cleanup_malformed(state):
    """Remove .executing.completed.done and similar malformed artifacts older than 24h."""
    issues = []
    now = time.time()
    cleaned = 0

    for agent in AGENTS:
        tasks_dir = AGENTS_DIR / agent / "tasks"
        if not tasks_dir.exists():
            continue
        for check_dir in [tasks_dir]:
            if not check_dir.exists():
                continue
            for f in check_dir.iterdir():
                if not f.is_file():
                    continue
                name = f.name
                # Detect malformed patterns
                is_malformed = (
                    ".executing.completed.done" in name or
                    ".executing.failed.done" in name or
                    ".executing.executing" in name
                )
                if not is_malformed:
                    continue
                try:
                    age = now - f.stat().st_mtime
                except OSError:
                    continue
                if age > MALFORMED_MAX_AGE:
                    try:
                        f.unlink()
                        cleaned += 1
                    except OSError:
                        pass

    if cleaned > 0:
        log(f"Cleaned {cleaned} malformed artifact(s)")
        state["malformed_cleaned"] = state.get("malformed_cleaned", 0) + cleaned
        issues.append(f"cleaned {cleaned} malformed files")

    return issues


# ============================================================
# Check 6: Reflection pipeline freshness
# ============================================================
def check_reflection_pipeline(state):
    """Verify the hourly reflection pipeline is running on schedule.

    Checks reflection-status.json age (should be < 75 min if cron is healthy).
    Also reads step timing data if available to flag slow steps.
    """
    issues = []
    now = time.time()

    if not REFLECTION_STATUS.exists():
        log("REFLECTION STATUS MISSING — hourly_reflection.sh may never have run", "WARN")
        issues.append("reflection-status.json missing")
        return issues

    try:
        age = now - REFLECTION_STATUS.stat().st_mtime
    except OSError:
        return issues

    if age > REFLECTION_MAX_AGE:
        age_min = int(age / 60)
        consecutive = state.get("reflection_misses", 0) + 1
        state["reflection_misses"] = consecutive
        log(f"REFLECTION STALE — {age_min}m old (threshold: {REFLECTION_MAX_AGE // 60}m, "
            f"consecutive misses: {consecutive})", "WARN")
        issues.append(f"reflection stale {age_min}m (miss #{consecutive})")
    else:
        state["reflection_misses"] = 0

    # Check step timing for slow steps (written by hourly_reflection.sh)
    if REFLECTION_STEP_TIMING.exists():
        try:
            with open(REFLECTION_STEP_TIMING) as f:
                timing = json.load(f)
            for step in timing.get("steps", []):
                duration = step.get("duration_s", 0)
                name = step.get("name", "?")
                if duration > 60:
                    log(f"REFLECTION SLOW STEP: {name} took {duration:.0f}s", "WARN")
                    issues.append(f"slow reflection step: {name} ({duration:.0f}s)")
        except Exception:
            pass

    return issues


# ============================================================
# Check 7: Memory health audit (contamination, bloat, rules)
# ============================================================
def check_memory_health(state):
    """Run memory_audit.py periodically to detect contamination, bloat, and rule excess."""
    issues = []
    now = time.time()
    last_mem_audit = state.get("last_memory_audit", 0)

    if (now - last_mem_audit) < MEMORY_AUDIT_INTERVAL:
        return issues

    log("Running periodic memory health audit")

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "memory_audit", str(SCRIPTS_DIR / "memory_audit.py")
        )
        ma = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ma)
        results = ma.run_audit()

        state["last_memory_audit"] = now

        criticals = [r for r in results if r["severity"] == "critical"]
        warnings = [r for r in results if r["severity"] == "warning"]

        state["memory_audit_result"] = {
            "total": len(results),
            "critical": len(criticals),
            "warning": len(warnings),
            "ts": datetime.now().isoformat(),
        }

        if criticals:
            for r in criticals:
                log(f"MEMORY CRITICAL: {r['message']}", "WARN")
                issues.append(f"memory: {r['message']}")
            # Auto-fix contamination (highest severity, most damaging)
            contamination = [r for r in criticals if r["type"] == "contamination"]
            if contamination:
                fixed = ma.fix_contamination(contamination)
                if fixed:
                    log(f"AUTO-FIX: Cleared {fixed} contaminated memory file(s)")
                    state["memory_fixes"] = state.get("memory_fixes", 0) + fixed
                    record_memory_fix("contamination", fixed)

        if warnings:
            for r in warnings:
                log(f"MEMORY WARNING: {r['message']}", "WARN")
                issues.append(f"memory: {r['message']}")

            # Auto-fix bloat issues (context_bloat, intraday_bloat, stale_entries)
            # These are safe, reversible fixes that reduce token waste in task execution
            total_bloat_fixed = 0
            context_bloat = [r for r in warnings if r["type"] == "context_bloat"]
            if context_bloat:
                fixed = ma.fix_context_bloat(context_bloat)
                total_bloat_fixed += fixed
            intraday_bloat = [r for r in warnings if r["type"] == "intraday_bloat"]
            if intraday_bloat:
                fixed = ma.fix_intraday_bloat(intraday_bloat)
                total_bloat_fixed += fixed
            stale = [r for r in results if r["type"] == "stale_entries"]
            if stale:
                fixed = ma.fix_stale_entries(stale)
                total_bloat_fixed += fixed
            # Auto-fix dead rules (active but never evaluated past threshold)
            dead_rules = [r for r in results if r["type"] == "dead_rule"]
            if dead_rules:
                fixed = ma.fix_dead_rules(dead_rules)
                total_bloat_fixed += fixed

            if total_bloat_fixed:
                log(f"AUTO-FIX: Resolved {total_bloat_fixed} memory bloat/rule issue(s)")
                state["memory_fixes"] = state.get("memory_fixes", 0) + total_bloat_fixed
                record_memory_fix("bloat", total_bloat_fixed)

        # Prune deprecated rules (safe at any severity level, runs on "info" results)
        pruneable = [r for r in results if r["type"] == "pruneable_deprecated"]
        if pruneable:
            fixed = ma.fix_pruneable_deprecated(pruneable)
            if fixed:
                log(f"AUTO-FIX: Pruned {fixed} deprecated rule(s) from rules.json")
                state["memory_fixes"] = state.get("memory_fixes", 0) + fixed
                record_memory_fix("deprecated_rules", fixed)

        if not results:
            log("Memory audit: ALL CLEAR")

    except Exception as e:
        log(f"Memory audit failed: {e}", "ERROR")
        issues.append(f"memory audit error: {e}")

    return issues


# ============================================================
# Check 8: Routing keyword drift detection
# ============================================================
ROUTING_DRIFT_INTERVAL = 1800  # 30 minutes
ROUTING_DRIFT_LOG = LOGS_DIR / "routing-decisions.jsonl"
ROUTING_DRIFT_WARN_PCT = 30    # warn if >30% keyword mismatches

# Check 9: Agent failure rate monitoring
FAILURE_RATE_INTERVAL = 300    # 5 minutes
FAILURE_RATE_LOOKBACK_H = 1    # 1-hour window for short-term failure rate
FAILURE_RATE_THRESHOLD = 0.5   # warn if >50% failure rate
FAILURE_RATE_MIN_TASKS = 3     # minimum tasks before flagging
AGENT_HEALTH_FLAGS_FILE = LOGS_DIR / "agent-health-flags.json"

# Check 9b: Credential failure monitoring (CRITICAL for DashScope incidents)
CRED_FAILURE_INTERVAL = 180    # 3 minutes between credential checks
CRED_FAILURE_LOOKBACK_M = 30   # 30-minute lookback for credential failures
CRED_FAILURE_THRESHOLD = 2     # Alert after 2+ credential failures in lookback
CRED_ALERT_FILE = LOGS_DIR / "credential-alerts.json"

# Check 13: Auto queue balancing
QUEUE_BALANCE_INTERVAL = 300   # 5 minutes between balance checks
QUEUE_MAX_DEPTH = 8            # Trigger if agent has >8 tasks
QUEUE_MIN_DEPTH = 2            # Don't redistribute to agents with <2 tasks
QUEUE_IMBALANCE_THRESHOLD = 5  # Trigger if max-min difference > 5
QUEUE_MAX_MOVE_PER_CYCLE = 10  # Limit tasks moved per cycle

# Check 11: Cascade failure detection
CASCADE_CHECK_INTERVAL = 600   # 10 minutes between cascade risk checks
CASCADE_LOOKBACK_MINUTES = 30  # Lookback period for cascade detection

# Check 12: Quality gate
QUALITY_GATE_INTERVAL = 180    # 3 minutes between quality gate checks
QUALITY_LOOKBACK_MINUTES = 15  # Check completions from last 15 minutes

# Check 13: Self-healing score
SELF_HEALING_SCORE_INTERVAL = 3600  # 1 hour between score updates
SELF_HEALING_SCORE_HOURS = 24       # Calculate score over 24h window

# Check 16: Git operation monitoring
GIT_OPERATION_INTERVAL = 300        # 5 minutes between git operation checks
GIT_SPIKE_THRESHOLD = 5             # commits per hour to trigger alert
GIT_STALE_BRANCH_DAYS = 7           # days before branch is considered stale
GIT_LARGE_DELETION_THRESHOLD = 100  # files deleted in single commit to alert

# Check 17: Proactive health patrol (O003/O006 activation)
PROACTIVE_PATROL_INTERVAL = 1800    # 30 minutes between proactive patrol checks
PROACTIVE_PATROL_COOLDOWN = LOGS_DIR / "ogedei-proactive-patrol-cooldown.json"
PROACTIVE_PATROL_IDLE_MINUTES = 30  # Only patrol if no cascade activity for 30 min

# Check 18: Session model drift detection (O001)
MODEL_DRIFT_INTERVAL = 1800         # 30 minutes between model drift checks
TOCK_LATEST_FILE = LOGS_DIR / "tock" / "latest.json"
MODEL_DRIFT_FLEET_THRESHOLD = 3     # Escalate if >= 3 agents have model drift


def check_model_drift(state):
    """Detect session model vs config model mismatch fleet-wide (O001 anomaly).

    Reads the latest tock snapshot and checks each agent's session.model against
    config_model.resolved. A mismatch means the agent is running under a different
    model than configured (e.g., glm-5 instead of claude-opus-4-6), which silently
    degrades task quality.

    Fleet-wide drift (>= MODEL_DRIFT_FLEET_THRESHOLD agents mismatched) triggers
    an O001 escalation task routed to kublai for credential/config investigation.
    """
    issues = []
    now = time.time()
    last_check = state.get("last_model_drift_check", 0)

    if (now - last_check) < MODEL_DRIFT_INTERVAL:
        return issues

    state["last_model_drift_check"] = now

    if not TOCK_LATEST_FILE.exists():
        return issues

    try:
        with open(str(TOCK_LATEST_FILE), "r") as f:
            tock = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        log(f"MODEL_DRIFT: Cannot read tock snapshot: {e}", "WARN")
        return issues

    tock_age_s = now - TOCK_LATEST_FILE.stat().st_mtime
    if tock_age_s > 3600:
        log(f"MODEL_DRIFT: Tock snapshot is {tock_age_s/60:.0f}m old, skipping drift check", "WARN")
        return issues

    agents_data = tock.get("agents", {})
    drifted = []
    checked = 0

    for agent, data in agents_data.items():
        session = data.get("session", {})
        config_model = data.get("config_model", {})

        session_model = session.get("model", "none")
        resolved_model = config_model.get("resolved", "unknown")
        session_match = config_model.get("session_match", True)

        # Only flag agents that have an active session (model != "none")
        if session_model == "none":
            continue

        checked += 1
        if not session_match:
            drifted.append({
                "agent": agent,
                "session_model": session_model,
                "config_model": resolved_model,
            })
            log(f"O001 MODEL_DRIFT: {agent} running {session_model!r} "
                f"(configured: {resolved_model!r})", "WARN")
            issues.append(f"O001 model drift: {agent} session={session_model} config={resolved_model}")

    if not drifted:
        if checked > 0:
            log(f"MODEL_DRIFT: {checked} active agents — all session models match config", "INFO")
        state["model_drift_last_clean"] = datetime.now().isoformat()
        state["model_drift_drifted"] = []
        return issues

    # Persist drift summary to state for tock/dashboard consumption
    state["model_drift_drifted"] = drifted
    state["model_drift_checked"] = checked
    state["model_drift_ts"] = datetime.now().isoformat()

    drift_pct = len(drifted) / checked * 100 if checked else 0
    log(f"O001 MODEL_DRIFT SUMMARY: {len(drifted)}/{checked} agents mismatched "
        f"({drift_pct:.0f}%) — session model != configured model", "WARN")

    # Fleet-wide drift escalation
    if len(drifted) >= MODEL_DRIFT_FLEET_THRESHOLD:
        drift_last_escalate = state.get("model_drift_last_escalate", 0)
        if (now - drift_last_escalate) > 7200:  # 2-hour cooldown on escalation
            _escalate_model_drift(drifted, state)
            state["model_drift_last_escalate"] = now

    return issues


def _escalate_model_drift(drifted: list, state: dict):
    """Create a kublai task to investigate fleet-wide model drift."""
    try:
        kublai_tasks_dir = AGENTS_DIR / "kublai" / "tasks"
        kublai_tasks_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        task_path = kublai_tasks_dir / f"ogedei-model-drift-alert-{ts}.md"

        drift_lines = "\n".join(
            f"  - {d['agent']}: session={d['session_model']!r} config={d['config_model']!r}"
            for d in drifted
        )
        content = f"""# Task: Investigate Fleet-Wide Model Drift (O001)

**Priority:** HIGH
**Source:** ogedei-watchdog check_model_drift()
**Detected:** {datetime.now().isoformat()}

## Problem

{len(drifted)} agents are running under a different model than their configured model.
This silently degrades task quality (e.g., glm-5 producing lower quality output than claude-opus-4-6).

## Drifted Agents

{drift_lines}

## Investigation Steps

1. Check `~/.openclaw/agents/{{agent}}/config.json` vs active session model in tock snapshot
2. Verify credential provider resolves to correct model (Z.AI/DashScope maps differently)
3. Check `~/.openclaw/kurultai.json` primary/fallback model config
4. If Z.AI fallback is active, confirm model mapping in provider config

## Success Criteria

- All active agents' session models match their configured models
- Tock snapshot shows session_match=true for all agents with active sessions
"""
        with open(str(task_path), "w") as f:
            f.write(content)
        log(f"MODEL_DRIFT: Escalation task created → {task_path.name}", "WARN")
    except Exception as e:
        log(f"MODEL_DRIFT: Failed to create escalation task: {e}", "ERROR")


def check_routing_drift(state):
    """Detect keyword routing vs actual routing disagreement.

    Reads recent routing decisions, re-runs route_by_text() on each,
    compares with actual destination. High drift means the keyword table
    is out of sync with LLM routing and needs updating.
    """
    issues = []
    now = time.time()
    last_check = state.get("last_routing_drift_check", 0)

    if (now - last_check) < ROUTING_DRIFT_INTERVAL:
        return issues

    try:
        from task_intake import route_by_text
    except Exception as e:
        log(f"Cannot import route_by_text for drift check: {e}", "ERROR")
        state["last_routing_drift_check"] = now
        return issues

    if not ROUTING_DRIFT_LOG.exists():
        state["last_routing_drift_check"] = now
        return issues

    # Read last 2 hours of routing decisions
    from datetime import timedelta
    cutoff = datetime.now() - timedelta(hours=2)
    decisions = []
    try:
        with open(ROUTING_DRIFT_LOG) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    ts = datetime.fromisoformat(entry["ts"])
                    if ts >= cutoff:
                        decisions.append(entry)
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
    except Exception:
        state["last_routing_drift_check"] = now
        return issues

    # Only compare actual routings (skip explicit, mention, and diagnostic entries)
    _SKIP_METHODS = {"explicit", "mention", "explicit_misroute", "skill_reroute"}
    comparable = [d for d in decisions if d.get("method") not in _SKIP_METHODS]
    if not comparable:
        state["last_routing_drift_check"] = now
        state["routing_drift"] = {"total": 0, "mismatches": 0, "drift_pct": 0.0,
                                  "ts": datetime.now().isoformat()}
        return issues

    mismatches = []
    for d in comparable:
        task = d.get("task", "")
        actual = d.get("dest", "")
        keyword_result = route_by_text(task)
        if keyword_result != actual:
            mismatches.append({
                "task": task[:80],
                "actual": actual,
                "keyword_would": keyword_result,
            })

    total = len(comparable)
    drift_pct = (len(mismatches) / total * 100) if total > 0 else 0.0

    state["routing_drift"] = {
        "total": total,
        "mismatches": len(mismatches),
        "drift_pct": round(drift_pct, 1),
        "top_examples": mismatches[:5],
        "ts": datetime.now().isoformat(),
    }
    state["last_routing_drift_check"] = now

    if drift_pct > ROUTING_DRIFT_WARN_PCT and len(mismatches) >= 2:
        log(f"ROUTING DRIFT: {len(mismatches)}/{total} ({drift_pct:.0f}%) keyword mismatches", "WARN")
        for m in mismatches[:3]:
            log(f"  DRIFT: '{m['task'][:60]}' keyword={m['keyword_would']} actual={m['actual']}", "WARN")
        issues.append(f"routing drift {drift_pct:.0f}% ({len(mismatches)}/{total} mismatches)")
    elif mismatches:
        log(f"Routing drift: {len(mismatches)}/{total} ({drift_pct:.0f}%) — within tolerance")

    return issues


# ============================================================
# Check 9: Short-term agent failure rate monitoring
# ============================================================
def check_agent_failure_rates(state):
    """Compute 1-hour failure rates per agent and write health flags.

    Reads COMPLETED and FAILED events from the task ledger for the last hour.
    Writes agent-health-flags.json with per-agent failure status so that
    route_quality_tracker.should_divert() can use real-time data instead of
    relying solely on 7-day rolling averages.
    """
    issues = []
    now = time.time()
    last_check = state.get("last_failure_rate_check", 0)

    if (now - last_check) < FAILURE_RATE_INTERVAL:
        return issues

    try:
        from kurultai_ledger import read_ledger
    except Exception as e:
        log(f"Cannot import kurultai_ledger for failure rate check: {e}", "ERROR")
        state["last_failure_rate_check"] = now
        return issues

    # Read only valid events (filter out events with validation errors)
    events = read_ledger(hours=FAILURE_RATE_LOOKBACK_H, valid_only=True)
    if not events:
        state["last_failure_rate_check"] = now
        return issues

    # Count completed and failed per agent
    agent_completed = {}
    agent_failed = {}
    for ev in events:
        agent = ev.get("agent")
        if not agent:
            continue
        event_type = ev.get("event", "")
        if event_type == "COMPLETED":
            agent_completed[agent] = agent_completed.get(agent, 0) + 1
        elif event_type == "FAILED":
            agent_failed[agent] = agent_failed.get(agent, 0) + 1

    # Build health flags
    flags = {}
    all_agents_with_tasks = set(list(agent_completed.keys()) + list(agent_failed.keys()))

    for agent in all_agents_with_tasks:
        completed = agent_completed.get(agent, 0)
        failed = agent_failed.get(agent, 0)
        total = completed + failed
        if total == 0:
            continue
        fail_rate = failed / total

        flag = {
            "completed_1h": completed,
            "failed_1h": failed,
            "total_1h": total,
            "fail_rate_1h": round(fail_rate, 3),
            "flagged": fail_rate >= FAILURE_RATE_THRESHOLD and total >= FAILURE_RATE_MIN_TASKS,
        }
        flags[agent] = flag

        if flag["flagged"]:
            log(f"HIGH FAILURE RATE: {agent} — {failed}/{total} ({fail_rate:.0%}) "
                f"failed in last {FAILURE_RATE_LOOKBACK_H}h", "WARN")
            issues.append(f"{agent} failure rate {fail_rate:.0%} ({failed}/{total} in 1h)")

    # Write health flags file for consumption by routing
    health_data = {
        "ts": datetime.now().isoformat(),
        "window_hours": FAILURE_RATE_LOOKBACK_H,
        "agents": flags,
    }

    try:
        AGENT_HEALTH_FLAGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(str(AGENT_HEALTH_FLAGS_FILE), "w") as f:
            json.dump(health_data, f, indent=2)
    except Exception as e:
        log(f"Failed to write agent health flags: {e}", "ERROR")

    state["last_failure_rate_check"] = now
    state["agent_failure_flags"] = {
        a: f["fail_rate_1h"] for a, f in flags.items() if f["flagged"]
    }

    return issues


# ============================================================
# Check 9b: Credential failure monitoring (CRITICAL)
# ============================================================
def check_credential_failures(state):
    """Detect AUTH/PROXY_AUTH failures that require human credential intervention.

    Reads ledger events for error_type="AUTH" or "PROXY_AUTH" from the last 30 minutes.
    Writes credential-alerts.json with per-agent credential failure counts and
    actionable remediation instructions.

    This is CRITICAL for DashScope incidents where agents have wrong credentials
    and 100% task failure rate. Faster detection = faster human intervention.
    """
    issues = []
    now = time.time()
    last_check = state.get("last_cred_failure_check", 0)

    if (now - last_check) < CRED_FAILURE_INTERVAL:
        return issues

    try:
        from kurultai_ledger import read_ledger
    except Exception as e:
        log(f"Cannot import kurultai_ledger for credential check: {e}", "ERROR")
        state["last_cred_failure_check"] = now
        return issues

    # Read only valid events (filter out events with validation errors)
    events = read_ledger(hours=CRED_FAILURE_LOOKBACK_M / 60.0, valid_only=True)
    if not events:
        state["last_cred_failure_check"] = now
        return issues

    # Count credential failures per agent
    agent_cred_failures = {}
    # Keywords that indicate credential/auth problems (match categorize_error logic)
    cred_keywords = [
        "unauthorized", "authentication", "invalid token", "invalid api key",
        "sk-sp-", "credential", "permission denied", "401", "403",
        "dashscope", "auth failed", "api key invalid"
    ]

    for ev in events:
        agent = ev.get("agent")
        if not agent:
            continue
        # Check both error_type field AND error message for credential issues
        error_type = ev.get("error_type", "")
        error_msg = (ev.get("error") or "").lower()

        is_cred_error = (
            error_type in ("AUTH", "PROXY_AUTH") or
            any(kw in error_msg for kw in cred_keywords)
        )
        if is_cred_error:
            agent_cred_failures[agent] = agent_cred_failures.get(agent, 0) + 1

    # Flag agents exceeding threshold
    alerts = {}
    for agent, count in agent_cred_failures.items():
        if count >= CRED_FAILURE_THRESHOLD:
            alerts[agent] = {
                "credential_failure_count": count,
                "lookback_minutes": CRED_FAILURE_LOOKBACK_M,
                "last_check": datetime.now().isoformat(),
                "remediation": f"Check ~/.openclaw/agents/{agent}/.claude/settings.json for ANTHROPIC_AUTH_TOKEN and ANTHROPIC_BASE_URL",
                "suspected_cause": "DashScope credentials (sk-sp-*) or wrong API endpoint",
                "action": "Get valid Anthropic API key (sk-ant-*) from https://console.anthropic.com/",
            }
            log(f"CREDENTIAL FAILURE ALERT: {agent} — {count} AUTH/PROXY_AUTH failures in last {CRED_FAILURE_LOOKBACK_M}m", "ERROR")
            issues.append(f"{agent} has {count} credential failures — requires API key update")

    # Write credential alerts file for human intervention
    if alerts:
        try:
            CRED_ALERT_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(str(CRED_ALERT_FILE), "w") as f:
                json.dump({"ts": datetime.now().isoformat(), "alerts": alerts}, f, indent=2)
            log(f"Wrote credential alerts to {CRED_ALERT_FILE.name}", "WARN")
        except Exception as e:
            log(f"Failed to write credential alerts: {e}", "ERROR")

        # O006: Auth Health Gap Response — Run auth_health_preflight.py when credential failures detected
        # This creates an ogedei task and logs auth failures for monitoring
        try:
            auth_script = Path(__file__).parent / "auth_health_preflight.py"
            if auth_script.exists():
                log("O006: Running auth_health_preflight.py --fix to assess and create task if needed", "WARN")
                result = subprocess.run(
                    [sys.executable, str(auth_script), "--fix"],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                if result.returncode != 0:
                    log(f"O006: auth_health_preflight.py detected issues (rc={result.returncode})", "WARN")
                # Log output for debugging (limited)
                if result.stdout:
                    log(f"O006: {result.stdout.strip()[:200]}", "WARN")
            else:
                log(f"O006: auth_health_preflight.py not found at {auth_script}", "ERROR")
        except subprocess.TimeoutExpired:
            log("O006: auth_health_preflight.py timed out", "ERROR")
        except Exception as e:
            log(f"O006: Failed to run auth_health_preflight.py: {e}", "ERROR")

    state["last_cred_failure_check"] = now
    return issues


# ============================================================
# Check 13: Auto queue balancing
# ============================================================
def check_queue_balance(state):
    """Check queue depths and auto-balance if imbalance detected.

    Redistributes tasks from overloaded agents to underloaded agents when:
    - Max queue depth > QUEUE_MAX_DEPTH (8 tasks)
    - Max-min difference > QUEUE_IMBALANCE_THRESHOLD (5 tasks)
    - At least one agent is underloaded (< QUEUE_MIN_DEPTH tasks)
    """
    issues = []
    now = time.time()
    last_check = state.get("last_queue_balance_check", 0)

    # Rate limiting: only check every QUEUE_BALANCE_INTERVAL
    if (now - last_check) < QUEUE_BALANCE_INTERVAL:
        return issues

    log("Checking queue balance")

    # Get current queue depths per agent
    depths = {}
    for agent in AGENTS:
        tasks_dir = AGENTS_DIR / agent / "tasks"
        if not tasks_dir.exists():
            depths[agent] = 0
            continue

        pending = 0
        # Count pending tasks by pattern
        for pattern in ["high-*.md", "normal-*.md", "low-*.md"]:
            pending += len(list(tasks_dir.glob(pattern)))

        # Subtract executing and done tasks (they may match the patterns above)
        for f in tasks_dir.glob("*"):
            if f.name.endswith(".executing.md") or f.name.endswith(".done.md") or f.name.endswith(".failed.md"):
                pending -= 1

        depths[agent] = max(0, pending)

    # Calculate imbalance metrics
    max_depth = max(depths.values()) if depths else 0
    min_depth = min(depths.values()) if depths else 0
    imbalance = max_depth - min_depth

    state["last_queue_balance_check"] = now
    state["queue_depths"] = depths

    # Check if action is needed
    if imbalance < QUEUE_IMBALANCE_THRESHOLD or max_depth < QUEUE_MAX_DEPTH:
        log(f"Queue balanced: max={max_depth}, min={min_depth}, imbalance={imbalance}")
        return issues

    # Identify overloaded and underloaded agents
    overloaded = [a for a, d in sorted(depths.items(), key=lambda x: -x[1]) if d > QUEUE_MAX_DEPTH]
    underloaded = [a for a, d in sorted(depths.items(), key=lambda x: x[1]) if d < QUEUE_MIN_DEPTH]

    if not overloaded:
        log(f"No overloaded agents (max={max_depth}, threshold={QUEUE_MAX_DEPTH})")
        return issues

    if not underloaded:
        log(f"No underloaded agents to receive tasks (min={min_depth}, threshold={QUEUE_MIN_DEPTH})")
        issues.append(f"queue_imbalance: {overloaded} overloaded but no underloaded agents")
        return issues

    log(f"QUEUE IMBALANCE: overloaded={[f'{a}={depths[a]}' for a in overloaded]}, "
        f"underloaded={[f'{a}={depths[a]}' for a in underloaded]}")

    # Redistribute tasks from overloaded to underloaded agents
    moved = 0
    import shutil

    for source in overloaded:
        if moved >= QUEUE_MAX_MOVE_PER_CYCLE:
            break

        tasks_dir = AGENTS_DIR / source / "tasks"
        source_tasks = []

        # Collect all pending task files
        for pattern in ["high-*.md", "normal-*.md", "low-*.md"]:
            source_tasks.extend(tasks_dir.glob(pattern))

        # Filter to actual pending tasks (exclude executing, done, failed)
        source_tasks = [
            t for t in source_tasks
            if not t.name.endswith(".executing.md") and not t.name.endswith(".done.md") and not t.name.endswith(".failed.md")
        ]

        # Sort by modification time (oldest first for fairness)
        source_tasks.sort(key=lambda f: f.stat().st_mtime)

        for i, task_path in enumerate(source_tasks):
            if moved >= QUEUE_MAX_MOVE_PER_CYCLE:
                break
            if not underloaded:
                break

            # Round-robin to underloaded agents
            target = underloaded[moved % len(underloaded)]

            try:
                target_dir = AGENTS_DIR / target / "tasks"
                target_dir.mkdir(parents=True, exist_ok=True)
                target_path = target_dir / task_path.name

                # Avoid name collisions (unlikely but possible)
                if target_path.exists():
                    # Add a small suffix to make unique
                    base_name = task_path.stem
                    ext = task_path.suffix
                    target_path = target_dir / f"{base_name}-moved{ext}"

                shutil.move(str(task_path), str(target_path))
                # Touch to update mtime (helps with priority ordering)
                target_path.touch()
                moved += 1
                log(f"AUTO-BALANCE: {task_path.name} {source} -> {target}")
            except Exception as e:
                log(f"Failed to move {task_path.name}: {e}", "ERROR")

    if moved > 0:
        log(f"Auto-balanced {moved} task(s)")
        state["queue_balance_moves"] = state.get("queue_balance_moves", 0) + moved
        issues.append(f"auto_balanced: {moved} tasks moved")
        record_queue_rebalance(moved, overloaded, underloaded)
    else:
        issues.append(f"queue_imbalance: detected but no tasks moved (check task file states)")

    return issues


# ============================================================
# Check 11: Cascade failure detection
# ============================================================
def check_cascade_risk(state):
    """Detect potential cascade failures across multiple agents.

    Analyzes recent failures for patterns like:
    - Multiple agents failing simultaneously
    - Single agent timeout spike
    - Failure rate accelerating over time
    - Gateway-wide failure spike
    """
    issues = []
    now = time.time()
    last_check = state.get("last_cascade_check", 0)

    # Only check every CASCADE_CHECK_INTERVAL
    if (now - last_check) < CASCADE_CHECK_INTERVAL:
        return issues

    log("Checking cascade failure risk")

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "cascade_detector", str(SCRIPTS_DIR / "cascade_detector.py")
        )
        cd = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cd)

        detector = cd.CascadeDetector(lookback_minutes=CASCADE_LOOKBACK_MINUTES)
        risk_report = detector.detect_cascade_risk()

        state["last_cascade_check"] = now
        state["cascade_risk"] = risk_report["risk_level"]
        state["cascade_metrics"] = risk_report["metrics"]

        if risk_report["risk_level"] in ["medium", "high"]:
            log(f"CASCADE RISK: {risk_report['risk_level'].upper()} — "
                f"{len(risk_report['patterns'])} pattern(s) detected", "WARN")
            issues.append(f"cascade_risk_{risk_report['risk_level']}")

            for pattern in risk_report["patterns"][:3]:
                log(f"  PATTERN: {pattern['description']}", "WARN")

            # Log recommendations
            for rec in risk_report["recommendations"][:2]:
                log(f"  RECOMMEND: {rec['description']}", "WARN")

            # Take preventive action for high risk
            if risk_report["risk_level"] == "high":
                for rec in risk_report["recommendations"]:
                    if rec.get("action") in ["reduce_load", "pause_new_tasks"]:
                        log(f"PREVENTIVE ACTION RECOMMENDED: {rec['description']}", "WARN")
                        # Would require additional infrastructure to actually pause tasks
                        # For now, just log the recommendation

        else:
            log(f"Cascade risk: {risk_report['risk_level']} ({risk_report['metrics']['events_analyzed']} events analyzed)")

    except Exception as e:
        log(f"Cascade check failed: {e}", "ERROR")
        issues.append(f"cascade_check_error: {e}")

    return issues


# ============================================================
# Check 12: Quality gate for recent completions
# ============================================================
def check_quality_gate(state):
    """Verify completion quality for recent .done.md files.

    Checks for:
    - Low content (< 500 chars)
    - Weak structure (< 3 headings)
    - Missing resolution section
    """
    issues = []
    now = time.time()
    last_check = state.get("last_quality_gate_check", 0)

    # Only check every QUALITY_GATE_INTERVAL
    if (now - last_check) < QUALITY_GATE_INTERVAL:
        return issues

    log("Running completion quality gate")

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "quality_gate", str(SCRIPTS_DIR / "quality_gate.py")
        )
        qg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(qg)

        gate = qg.CompletionQualityGate()
        checked_count = 0
        failed_count = 0
        retried_count = 0
        escalated_count = 0

        # Check recent .done.md files
        cutoff_time = now - (QUALITY_LOOKBACK_MINUTES * 60)

        for agent in AGENTS:
            tasks_dir = AGENTS_DIR / agent / "tasks"
            if not tasks_dir.exists():
                continue

            for f in tasks_dir.glob("*.done.md"):
                if not f.is_file():
                    continue

                # Skip tasks already in terminal states (verified, resolved, etc.)
                # These have already passed quality checks and should NOT be re-checked
                # This prevents false positive escalations of completed tasks
                # Use substring matching to handle suffixes like .revision-1.md
                if any(pattern in f.name for pattern in (
                    ".verified.done.",           # Already verified - Grade A, B, C, etc.
                    ".verified.completed.done.",  # Verified completion
                    ".verified.failed.done.",    # Verified failure
                    ".resolved.",                # Escalations that were resolved
                    ".orphan-resolved.",         # Orphan tasks that were resolved
                    ".failed.done.",             # Task crashed/failed — quality checks are irrelevant
                    ".no_output.done.",          # No output captured — nothing to grade
                )):
                    continue

                try:
                    mtime = f.stat().st_mtime
                except OSError:
                    continue

                if mtime < cutoff_time:
                    continue

                # Skip test tasks
                try:
                    content = f.read_text()
                    if "test" in content.lower() and len(content) < 500:
                        continue
                except OSError:
                    continue

                checked_count += 1
                result = gate.verify_completion(f)

                if not result.passed:
                    failed_count += 1
                    log(f"QUALITY FAIL: {agent}/{f.name} — {result.issues}", "WARN")

                    if result.action == "retry":
                        retried_count += 1
                        issues.append(f"{agent}/{f.name} quality: retry")
                        record_quality_retry(agent, f.name)
                    elif result.action == "escalate":
                        escalated_count += 1
                        issues.append(f"{agent}/{f.name} quality: escalate")
                        record_quality_escalation(agent, f.name)
                        # Create escalation task
                        gate.escalate_to_kublai(f, result.issues)

        state["last_quality_gate_check"] = now
        state["quality_gate_checked"] = checked_count
        state["quality_gate_failed"] = failed_count
        state["quality_gate_retried"] = retried_count
        state["quality_gate_escalated"] = escalated_count

        if checked_count > 0:
            log(f"Quality gate: {checked_count} checked, {failed_count} failed, "
                f"{retried_count} retried, {escalated_count} escalated")

    except Exception as e:
        log(f"Quality gate check failed: {e}", "ERROR")
        issues.append(f"quality_gate_error: {e}")

    return issues


# ============================================================
# Check 13: Self-healing score tracking
# ============================================================
def update_self_healing_score(state):
    """Calculate and report self-healing effectiveness score.

    Tracks percentage of issues auto-resolved vs. escalated.
    Saves snapshot for historical tracking.
    """
    issues = []
    now = time.time()
    last_check = state.get("last_self_healing_score_check", 0)

    # Only update every SELF_HEALING_SCORE_INTERVAL
    if (now - last_check) < SELF_HEALING_SCORE_INTERVAL:
        return issues

    log("Updating self-healing score")

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "self_healing_score", str(SCRIPTS_DIR / "self_healing_score.py")
        )
        shs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(shs)

        tracker = shs.SelfHealingScore()
        score_data = tracker.calculate_score(hours=SELF_HEALING_SCORE_HOURS)

        # Save snapshot
        tracker.save_score_snapshot(hours=SELF_HEALING_SCORE_HOURS)

        state["last_self_healing_score_check"] = now
        state["self_healing_score"] = score_data["score"]
        state["self_healing_metrics"] = {
            "auto_resolved": score_data["auto_resolved"],
            "escalated": score_data["escalated"],
            "manual": score_data["manual"],
            "total": score_data["total_issues"],
        }

        log(f"Self-healing score: {score_data['score']:.1f}% "
            f"({score_data['auto_resolved']}/{score_data['total_issues']} auto-resolved)")

        # Alert if score drops below threshold
        if score_data["score"] < 50 and score_data["total_issues"] > 5:
            log(f"LOW SELF-HEALING SCORE: {score_data['score']:.1f}% — system resilience degraded", "WARN")
            issues.append(f"low_self_healing_score: {score_data['score']:.1f}%")

    except Exception as e:
        log(f"Self-healing score update failed: {e}", "ERROR")
        issues.append(f"self_healing_score_error: {e}")

    return issues


# ============================================================
# Check 14: Circuit breaker health check
# ============================================================
def check_circuit_breaker_health(state):
    """Report circuit breaker state and validate recent data.

    Monitors:
    - OPEN circuits (quarantined agents)
    - HALF-OPEN circuits (agents on probation)
    - Recent redistributions
    - State file health
    """
    issues = []

    if _circuit_breaker is None:
        return issues

    try:
        report = _circuit_breaker.get_status_report()

        # Log any OPEN circuits
        for agent, status in report["agents"].items():
            if status["state"] == "OPEN":
                log(f"CIRCUIT OPEN: {agent} — {status['detail']}", "WARN")
                state["circuit_open_agents"] = state.get("circuit_open_agents", [])
                if agent not in state["circuit_open_agents"]:
                    state["circuit_open_agents"].append(agent)
                    issues.append(f"circuit_open: {agent}")

            elif status["state"] == "HALF_OPEN":
                log(f"CIRCUIT HALF-OPEN: {agent} — {status['detail']}", "INFO")
                state["circuit_half_open_agents"] = state.get("circuit_half_open_agents", [])
                if agent not in state["circuit_half_open_agents"]:
                    state["circuit_half_open_agents"].append(agent)

        # Store report in state
        state["circuit_report"] = report
        state["circuit_summary"] = report["summary"]

        # Check for excessive redistributions (potential thrashing)
        if "redistributions" in _circuit_breaker.state:
            recent_redistributions = [
                r for r in _circuit_breaker.state.get("redistributions", [])
                if datetime.fromisoformat(r["ts"]) > datetime.now() - timedelta(hours=1)
            ]
            state["recent_redistributions"] = len(recent_redistributions)

            if len(recent_redistributions) > 20:
                log(f"High redistribution count: {len(recent_redistributions)} in last hour (potential thrashing)", "WARN")
                issues.append(f"high_redistribution_count: {len(recent_redistributions)}/hour")

    except Exception as e:
        log(f"Circuit breaker check failed: {e}", "ERROR")
        issues.append(f"circuit_breaker_error: {e}")

    return issues


# ============================================================
# Check 15: Internal watchdog health check
# ============================================================
def check_watchdog_health(state):
    """Internal health check for the watchdog itself.

    Monitors:
    - Cycle execution time
    - Issue count trends
    - State file health
    """
    issues = []
    now = time.time()

    # Track cycle start time if not set
    if "cycle_start_time" not in state:
        state["cycle_start_time"] = now

    cycle_duration = now - state["cycle_start_time"]
    state["last_cycle_duration"] = cycle_duration

    # Warn if cycle is taking too long
    if cycle_duration > 30:  # 30 seconds
        log(f"Watchdog cycle slow: {cycle_duration:.1f}s", "WARN")
        state["slow_cycles"] = state.get("slow_cycles", 0) + 1

    # Check state file size
    try:
        state_size = STATE_FILE.stat().st_size if STATE_FILE.exists() else 0
        state["state_file_size"] = state_size

        if state_size > 100_000:  # 100KB
            log(f"State file large: {state_size / 1024:.1f}KB", "WARN")
    except Exception:
        pass

    return issues


# ============================================================
# Check 16: Git operation monitoring for autonomous agents
# ============================================================
def check_git_operations(state):
    """Monitor git operations by autonomous agents for anomalies.

    Checks for:
    - Commit spike detection (>5/hour per agent)
    - Large deletions (>100 files in single commit)
    - Critical file modifications (CLAUDE.md, config/)
    - Stale autonomous branches (>7 days old)
    - Unauthorized direct main merges

    Also collects metrics for dashboard display.
    """
    issues = []
    now = time.time()
    last_check = state.get("last_git_operation_check", 0)

    # Only check every GIT_OPERATION_INTERVAL
    if (now - last_check) < GIT_OPERATION_INTERVAL:
        return issues
        return issues

    log("Checking git operations")

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "git_operation_monitor", str(SCRIPTS_DIR / "git-operation-monitor.py")
        )
        gom = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gom)

        # Gather metrics
        metrics = gom.gather_metrics()

        state["last_git_operation_check"] = now
        state["git_metrics"] = {
            "autonomous_commits_24h": metrics["autonomous_commits_24h"],
            "autonomous_commits_1h": metrics["autonomous_commits_1h"],
            "autonomous_branches_active": metrics["autonomous_branches_active"],
            "autonomous_branches_stale": metrics["autonomous_branches_stale"],
            "autonomous_prs_open": metrics["autonomous_prs_open"],
            "anomaly_count": metrics["anomaly_count"],
            "blocked_operations_24h": metrics["blocked_operations_24h"],
        }

        # Check for anomalies
        if metrics["anomalies"]:
            for anomaly in metrics["anomalies"][:5]:
                severity = anomaly.get("severity", "unknown")
                msg = anomaly.get("message", "Unknown issue")
                log(f"GIT ANOMALY [{severity.upper()}]: {msg}", "WARN" if severity != "critical" else "ERROR")
                issues.append(f"git_anomaly: {anomaly.get('type', 'unknown')}")

            # Create alert task for critical/high anomalies
            critical_high = [a for a in metrics["anomalies"] if a.get("severity") in ["critical", "high"]]
            if critical_high:
                gom.create_alert_task(critical_high)

        # Check for stale branches
        if metrics["autonomous_branches_stale"] > 0:
            log(f"STALE AUTONOMOUS BRANCHES: {metrics['autonomous_branches_stale']} branches older than {GIT_STALE_BRANCH_DAYS} days", "WARN")
            issues.append(f"stale_branches: {metrics['autonomous_branches_stale']}")

        # Check for blocked operations
        if metrics["blocked_operations_24h"] > 0:
            log(f"BLOCKED OPERATIONS: {metrics['blocked_operations_24h']} unauthorized merges detected", "WARN")
            issues.append(f"blocked_operations: {metrics['blocked_operations_24h']}")

        # Store metrics in Neo4j for trend analysis
        if gom.store_metrics_neo4j(metrics):
            log("Git metrics stored in Neo4j")

        # Save metrics to file for dashboard
        gom.save_metrics(metrics)

    except FileNotFoundError:
        log("git-operation-monitor.py not found — skipping git check", "WARN")
    except Exception as e:
        log(f"Git operation check failed: {e}", "ERROR")
        issues.append(f"git_check_error: {e}")

    return issues


# ============================================================
# Check 17: Proactive health patrol (O003/O006 activation)
# ============================================================
def check_proactive_health_patrol(state):
    """Generate proactive 'fleet health patrol' task when ogedei is idle.

    Implements O003/O006 rules: When ogedei's queue is empty AND no cascade
    detections in 30 minutes, auto-create a fleet health patrol task to:
    - Check auth health (credential expiry, token validity)
    - Check cron gaps (tick/tock schedule drift)
    - Check session bloat (stale .jsonl files)

    This ensures the ops agent adds value during steady-state periods
    instead of being completely idle.
    """
    issues = []
    now = time.time()
    now_dt = datetime.now()

    # Check cooldown
    last_patrol = state.get("last_proactive_patrol", 0)
    if (now - last_patrol) < PROACTIVE_PATROL_INTERVAL:
        return issues

    # Check if ogedei's queue is empty
    ogedei_tasks_dir = AGENTS_DIR / "ogedei" / "tasks"
    pending_count = 0
    if ogedei_tasks_dir.exists():
        for f in ogedei_tasks_dir.iterdir():
            name = f.name
            if name.endswith(".md") and not any(
                tag in name for tag in [".done", ".failed", ".completed", ".verified", ".rerouted", ".absorbed", ".executing"]
            ):
                pending_count += 1

    # Only patrol if queue is empty (or very small)
    if pending_count > 2:
        log(f"Proactive patrol: skipping (ogedei has {pending_count} pending)")
        return issues

    # Check cascade activity - only patrol if quiet for 30+ minutes
    last_cascade = state.get("last_cascade_check", 0)
    cascade_quiet_minutes = (now - last_cascade) / 60
    if cascade_quiet_minutes < PROACTIVE_PATROL_IDLE_MINUTES:
        log(f"Proactive patrol: skipping (cascade check {cascade_quiet_minutes:.0f}min ago)")
        return issues

    # Also check if we recently had any cascade risk
    cascade_risk = state.get("cascade_risk", "low")
    if cascade_risk in ["medium", "high"]:
        log(f"Proactive patrol: skipping (cascade risk={cascade_risk})")
        return issues

    log("Proactive patrol: ogedei idle, cascade quiet — creating fleet health patrol task")

    # Create the patrol task
    try:
        from task_intake import create_task

        patrol_topics = [
            "1. Auth health: Check for credential failures in logs/credential-alerts.json",
            "2. Cron gaps: Verify tick/tock schedules are running on time",
            "3. Session bloat: Check sessions/ for stale .jsonl files >24h old",
            "4. Circuit breaker: Verify all agents are CLOSED (not OPEN/HALF_OPEN)",
            "5. Neo4j health: Check connection pool and recent query latency",
        ]

        task_body = f"""# Fleet Health Patrol

This is a proactive health patrol task generated by ogedei-watchdog during idle periods.

**Context:** Ogedei queue was empty ({pending_count} pending) and no cascade activity for {cascade_quiet_minutes:.0f} minutes.

**Checks to perform:**

{chr(10).join(patrol_topics)}

**Deliverables:**
- Summary of any issues found
- Recommended actions if issues detected
- Update self-healing score if auto-recovery actions taken

**Skills:** Use /kurultai-health for comprehensive system status.
"""

        task_id = create_task(
            title="Fleet Health Patrol — Proactive Ops Check",
            body=task_body,
            priority="low",
            source="ogedei_proactive_patrol",
            agent="ogedei",
            skill_hint="/kurultai-health"
        )

        state["last_proactive_patrol"] = now
        state["proactive_patrols"] = state.get("proactive_patrols", 0) + 1
        log(f"Created fleet health patrol task: {task_id}")
        issues.append("proactive_patrol_created")

        # Record this as a healing event (proactive monitoring)
        record_healing(
            issue_type="proactive_patrol",
            action="auto_created",
            outcome="success",
            agent="ogedei",
            details={"task_id": task_id, "pending_before": pending_count}
        )

    except Exception as e:
        log(f"Failed to create proactive patrol task: {e}", "ERROR")
        issues.append(f"proactive_patrol_error: {e}")

    return issues


# ============================================================
# Main cycle
# ============================================================
def run_cycle():
    """Run all checks. Returns list of issues found."""
    state = load_state()
    state["cycle_start_time"] = time.time()
    all_issues = []

    # Core health checks
    all_issues.extend(check_watcher_alive(state))
    all_issues.extend(check_stalled_tasks(state))
    all_issues.extend(verify_recent_completions(state))
    all_issues.extend(periodic_queue_audit(state))
    all_issues.extend(cleanup_malformed(state))
    all_issues.extend(check_reflection_pipeline(state))
    all_issues.extend(check_memory_health(state))
    all_issues.extend(check_routing_drift(state))
    all_issues.extend(check_agent_failure_rates(state))
    all_issues.extend(check_credential_failures(state))
    all_issues.extend(check_model_drift(state))
    all_issues.extend(check_queue_balance(state))

    # P2 enhancement checks
    all_issues.extend(check_cascade_risk(state))
    all_issues.extend(check_quality_gate(state))
    all_issues.extend(update_self_healing_score(state))
    all_issues.extend(check_circuit_breaker_health(state))
    all_issues.extend(check_watchdog_health(state))
    all_issues.extend(check_git_operations(state))

    # P3 proactive ops (O003/O006 activation)
    all_issues.extend(check_proactive_health_patrol(state))

    state["cycles"] = state.get("cycles", 0) + 1
    state["last_cycle"] = datetime.now().isoformat()
    state["last_cycle_epoch"] = time.time()
    state["last_issues"] = all_issues

    save_state(state)

    if all_issues:
        log(f"Cycle #{state['cycles']}: {len(all_issues)} issue(s)")
    return all_issues


def daemon_loop():
    """Main daemon loop — runs cycle every POLL_INTERVAL seconds.

    Self-reload: If this script file is modified, the daemon automatically restarts
    to pick up changes. This is critical for ops — bug fixes take effect immediately.
    """
    _script_path = Path(__file__).resolve()
    _last_mtime = _script_path.stat().st_mtime
    log(f"Ogedei Watchdog starting (poll interval: {POLL_INTERVAL}s)")
    log(f"State: {STATE_FILE}")
    log(f"Log: {LOG_FILE}")
    log(f"Script: {_script_path} (mtime: {_last_mtime})")

    while not stop_event.is_set():
        try:
            run_cycle()
        except Exception as e:
            log(f"Error in watchdog cycle: {e}", "ERROR")

        for _ in range(POLL_INTERVAL):
            if stop_event.is_set():
                break
            time.sleep(1)

        # Self-reload check: restart if script file has been modified
        # This ensures bug fixes (like credential guards) take effect immediately
        try:
            _current_mtime = _script_path.stat().st_mtime
            if _current_mtime > _last_mtime:
                log(f"SCRIPT MODIFIED: {_script_path}")
                log(f"  Old mtime: {_last_mtime}, New mtime: {_current_mtime}")
                log(f"  RESTARTING to pick up code changes...")
                # Exec ourself to replace the current process
                # This preserves PID but reloads all code
                os.execv(sys.executable, [sys.executable, str(_script_path), "--daemon"])
        except Exception as e:
            log(f"Self-reload check failed: {e}", "ERROR")

    log("Ogedei Watchdog stopped")


def signal_handler(sig, frame):
    log(f"Received signal {sig}, shutting down...")
    stop_event.set()


# ============================================================
# Healing event recording helpers
# ============================================================
def record_healing(
    issue_type: str,
    action: str,
    outcome: str = "success",
    agent: str = "",
    details: dict | None = None,
):
    """Record a healing event to the self-healing score tracker.

    Args:
        issue_type: Type of issue (e.g., "gateway_crash", "stale_task")
        action: Action taken ("auto_recovered", "escalated", "manual", "partial")
        outcome: Outcome ("success", "failed", "partial")
        agent: Agent affected (if applicable)
        details: Additional details about the event
    """
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "self_healing_score", str(SCRIPTS_DIR / "self_healing_score.py")
        )
        shs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(shs)

        tracker = shs.SelfHealingScore()
        tracker.record_issue(issue_type, action, outcome, agent, details)
    except Exception as e:
        log(f"Failed to record healing event: {e}", "ERROR")


def record_gateway_restart(success: bool, pid: int = 0):
    """Record a gateway restart event."""
    record_healing(
        issue_type="gateway_restart",
        action="auto_recovered" if success else "escalated",
        outcome="success" if success else "failed",
        details={"pid": pid} if pid else {},
    )


def record_fake_completion_requeued(agent: str, task_file: str):
    """Record a fake completion detection and requeue."""
    record_healing(
        issue_type="fake_completion",
        action="auto_recovered",
        outcome="success",
        agent=agent,
        details={"task_file": task_file},
    )


def record_stale_task_recovered(agent: str, task_file: str):
    """Record a stale task recovery."""
    record_healing(
        issue_type="stale_task_recovered",
        action="auto_recovered",
        outcome="success",
        agent=agent,
        details={"task_file": task_file},
    )


def record_memory_fix(fix_type: str, count: int):
    """Record a memory health fix."""
    record_healing(
        issue_type=f"memory_{fix_type}",
        action="auto_recovered",
        outcome="success",
        details={"fix_count": count},
    )


def record_queue_rebalance(moved_count: int, from_agents: list, to_agents: list):
    """Record a queue balancing action."""
    record_healing(
        issue_type="queue_rebalanced",
        action="auto_recovered",
        outcome="success",
        details={
            "moved_count": moved_count,
            "from_agents": from_agents,
            "to_agents": to_agents,
        },
    )


def record_quality_retry(agent: str, task_file: str):
    """Record a quality gate retry."""
    record_healing(
        issue_type="quality_retry",
        action="auto_recovered",
        outcome="success",
        agent=agent,
        details={"task_file": task_file},
    )


def record_quality_escalation(agent: str, task_file: str):
    """Record a quality gate escalation."""
    record_healing(
        issue_type="quality_failure",
        action="escalated",
        outcome="partial",
        agent=agent,
        details={"task_file": task_file},
    )


def main():
    parser = argparse.ArgumentParser(description="Ogedei Watchdog — quality assurance daemon")
    parser.add_argument("--once", action="store_true", help="Run single cycle and exit")
    parser.add_argument("--daemon", action="store_true", help="Run as persistent daemon")
    parser.add_argument("--status", action="store_true", help="Print current state and exit")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if args.status:
        state = load_state()
        print(json.dumps(state, indent=2))
        return

    if args.once:
        issues = run_cycle()
        if issues:
            print(f"Issues found: {len(issues)}")
            for i in issues:
                print(f"  - {i}")
        else:
            print("No issues found")
        return

    daemon_loop()


if __name__ == "__main__":
    main()
