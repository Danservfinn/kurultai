#!/usr/bin/env python3
"""
Agent Task Handler

Allows persistent agents to pick up and process tasks from their queue.
Can spawn subagents for parallel work.

Usage:
    python3 agent-task-handler.py --agent temujin
"""

import argparse
import glob
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from json_state import locked_json_update
from kurultai_paths import (
    AGENTS_DIR as _AGENTS_DIR, SPAWN_QUEUE as _SPAWN_QUEUE, TASK_LEDGER as _TASK_LEDGER,
    CLAUDE_AGENT as _CLAUDE_AGENT, CLAUDE_TIMEOUT as _KP_CLAUDE_TIMEOUT,
    TIMEOUT_BY_PRIORITY as _KP_TIMEOUT_BY_PRIORITY,
)
from kurultai_ledger import append_ledger as _kp_append_ledger

# LEDGER RELOAD FIX: Force reload of kurultai_ledger to pick up schema updates
# This prevents "invalid event type" errors when the ledger schema is updated
# but the Python process has cached the old module
import importlib
try:
    import kurultai_ledger as _ledger_module
    _kp_append_ledger = _ledger_module.append_ledger
except ImportError:
    _ledger_module = None

def _reload_ledger_module():
    """Reload kurultai_ledger module to pick up schema updates.

    Call this when the ledger schema has been updated but the running
    process has cached the old VALID_EVENTS set.
    """
    global _kp_append_ledger, _ledger_module
    if _ledger_module is None:
        try:
            import kurultai_ledger as _ledger_module
        except ImportError:
            return False
    try:
        importlib.reload(_ledger_module)
        _kp_append_ledger = _ledger_module.append_ledger
        print("[LEDGER] Module reloaded to pick up schema updates")
        return True
    except Exception as e:
        print(f"[LEDGER] Module reload failed: {e}")
        return False

# Prompt optimization integration
try:
    from prompt_optimizer import enhance_task_prompt, load_optimizer_config
    PROMPT_OPTIMIZER_AVAILABLE = True
except ImportError as e:
    print(f"[prompt_optimizer] Not available: {e}")
    PROMPT_OPTIMIZER_AVAILABLE = False

# Circuit breaker for agent health tracking
try:
    from circuit_breaker import AgentCircuitBreaker
    _circuit_breaker = AgentCircuitBreaker()
except Exception as e:
    print(f"[circuit_breaker] Init failed (non-fatal): {e}")
    _circuit_breaker = None

AGENTS_DIR = str(_AGENTS_DIR)
SPAWN_QUEUE = str(_SPAWN_QUEUE)
CLAUDE_AGENT = str(_CLAUDE_AGENT)
CLAUDE_TIMEOUT = _KP_CLAUDE_TIMEOUT  # imported from kurultai_paths (canonical source)

# Fallback model configuration for rate limit recovery
FALLBACK_MODEL = "glm-5"  # Primary model (Claude API unavailable)
MAX_RATE_LIMIT_RETRIES = 1  # Only retry once with fallback model
TIMEOUT_BY_PRIORITY = _KP_TIMEOUT_BY_PRIORITY  # imported from kurultai_paths (canonical source)
# Skills that need extra time (design exploration, brainstorming, debugging)
SLOW_SKILLS = {
    '/horde-brainstorming': 10800,
    '/golden-horde': 10800,
    '/horde-implement': 10800,
    '/horde-review': 10800,
    '/horde-debug': 10800,
    '/horde-learn': 10800,
    '/horde-swarm': 10800,
    '/horde-test': 10800,
    # Complex debugging and analysis skills need extended time
    '/systematic-debugging': 10800,
    '/kurultai-health': 10800,
    '/code-reviewer': 10800,
    # Medium-complexity skills: get slow stall thresholds (7min silence / 8min elapsed)
    # but don't override the priority-based execution timeout (value=0)
    '/senior-frontend': 0,
    '/senior-backend': 0,
    '/senior-fullstack': 0,
    '/senior-architect': 0,
    '/content-research-writer': 0,
    '/horde-gate-testing': 0,
    '/horde-plan': 0,
}


# =============================================================================
# Centralized Credential Vault
# =============================================================================

def load_vault_credentials() -> dict:
    """Load credentials from centralized vault as fallback."""
    vault_path = Path.home() / '.openclaw' / 'credentials' / 'provider.env'
    if not vault_path.exists():
        return {}

    creds = {}
    try:
        with open(vault_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    creds[key] = value.strip('"\'')
    except Exception as e:
        print(f"[vault] Error loading credentials: {e}")
    return creds


# =============================================================================
# Prompt Injection Protection (Security)
# =============================================================================

# Patterns that indicate potential prompt injection attempts
INJECTION_PATTERNS = [
    # Instruction override attempts
    (r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|rules?|directives?)", "[INSTRUCTION_OVERRIDE]"),
    (r"disregard\s+(all\s+)?(previous|above|prior)", "[INSTRUCTION_OVERRIDE]"),
    (r"forget\s+(all\s+)?(previous|above|your\s+instructions?)", "[INSTRUCTION_OVERRIDE]"),
    (r"you\s+are\s+now\s+", "[ROLE_CHANGE]"),
    (r"new\s+instructions?:", "[NEW_INSTRUCTION]"),
    # System token simulation
    (r"<\|.*?\|>", "[SPECIAL_TOKEN]"),
    (r"\[SYSTEM\]", "[SYSTEM_TOKEN]"),
    (r"\[/SYSTEM\]", "[SYSTEM_TOKEN]"),
    (r"<<.*?>>", "[DELIMITER_INJECTION]"),
    # Common jailbreak patterns
    (r"developer\s+mode", "[DEVELOPER_MODE]"),
    (r"debug\s+mode", "[DEBUG_MODE]"),
    (r"admin\s+mode", "[ADMIN_MODE]"),
    (r"override\s+safety", "[SAFETY_OVERRIDE]"),
]


def sanitize_task_content(content: str, verbose: bool = False) -> str:
    """Sanitize task content to prevent prompt injection attacks.

    Removes or neutralizes common prompt injection patterns that could
    manipulate the LLM's behavior.

    Args:
        content: The task content to sanitize
        verbose: If True, log what was filtered

    Returns:
        Sanitized content with injection patterns replaced
    """
    import re

    if not content:
        return content

    sanitized = content
    for pattern, replacement in INJECTION_PATTERNS:
        matches = re.findall(pattern, sanitized, re.IGNORECASE)
        if matches and verbose:
            print(f"  [SANITIZE] Filtered {len(matches)} instance(s) of {replacement}")
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

    return sanitized


def build_safe_prompt(system_context: str, task_content: str, skill_hint: str = None) -> str:
    """Build a prompt with clear section delimiters and sanitized content.

    Uses clear delimiters to separate system context from user content,
    preventing the model from confusing user input with instructions.

    Args:
        system_context: Agent identity and rules (trusted)
        task_content: User-provided task content (untrusted, will be sanitized)
        skill_hint: Optional skill hint for execution

    Returns:
        Formatted prompt with clear sections
    """
    # Sanitize user-provided content
    safe_task = sanitize_task_content(task_content)

    # Build prompt with clear delimiters
    sections = [
        "=" * 60,
        "SYSTEM CONTEXT (Agent Identity)",
        "=" * 60,
        system_context,
        "",
        "=" * 60,
        "USER TASK (Execute This)",
        "=" * 60,
        safe_task,
    ]

    if skill_hint:
        sections.extend([
            "",
            "=" * 60,
            f"MANDATORY SKILL INVOCATION (R008)",
            "=" * 60,
            f"CRITICAL: You MUST invoke the Skill tool with '{skill_hint}' before ANY other work.",
            f"This is NOT optional. Your task will be rejected if you do not invoke this skill.",
            f"Use: Skill: skill=\"{skill_hint}\"",
            "=" * 60,
        ])

    sections.extend([
        "",
        "=" * 60,
        "END OF TASK - Execute the above task using available tools",
        "=" * 60,
    ])

    return "\n".join(sections)


MAX_TASK_DEPTH = 3
HAIKU_TIMEOUT = 120  # Max seconds for /task-complete haiku notification (increased from 60 due to cold start delays)

# Proxy health check configuration
PROXY_HEALTH_CHECK_TIMEOUT = 5  # seconds
# Approved proxy endpoints for multi-tier fallback (Anthropic -> Z.AI -> Alibaba)
# All agents use this single source of truth - DO NOT add local duplicates
PROXY_ENDPOINTS = ['dashscope.aliyuncs.com', 'openrouter.ai', 'api.z.ai']


def check_proxy_health(proxy_url: str) -> bool:
    """Check if proxy endpoint is responding.

    Args:
        proxy_url: The proxy base URL to check

    Returns:
        True if proxy is reachable, False otherwise
    """
    import urllib.request
    import ssl

    if not proxy_url:
        return False

    try:
        # Use proper SSL verification - only skip for localhost/private networks
        # This is a security fix to prevent MITM attacks
        ssl_context = ssl.create_default_context()

        # Allow self-signed certs only for localhost/private endpoints
        if any(host in proxy_url for host in ['localhost', '127.0.0.1', '192.168.', '10.', '172.']):
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            # Log the security trade-off
            print(f"  [Security] SSL verification disabled for private endpoint: {proxy_url[:50]}...")
        else:
            # Full SSL verification for external endpoints
            ssl_context.check_hostname = True
            ssl_context.verify_mode = ssl.CERT_REQUIRED

        # Try a simple HEAD request to the proxy endpoint
        req = urllib.request.Request(proxy_url, method='HEAD')
        req.add_header('User-Agent', 'Kurultai-Agent/1.0')

        # Try with HTTPS first
        if proxy_url.startswith('https://'):
            urllib.request.urlopen(req, timeout=PROXY_HEALTH_CHECK_TIMEOUT, context=ssl_context)
        else:
            urllib.request.urlopen(req, timeout=PROXY_HEALTH_CHECK_TIMEOUT)
        return True
    except urllib.error.HTTPError as e:
        # HTTP error but endpoint is reachable (4xx/5xx means service is up)
        print(f"  Proxy health check: {proxy_url} responded with HTTP {e.code}")
        return True  # Service is reachable, even if returning errors
    except urllib.error.URLError as e:
        # Network-level error (DNS, connection refused, etc.)
        print(f"  Proxy health check FAILED: {proxy_url} - {e.reason}")
        return False
    except Exception as e:
        print(f"  Proxy health check FAILED: {proxy_url} - {str(e)}")
        return False


def log_proxy_status(agent_name: str, proxy_url: str, is_using_proxy: bool) -> dict:
    """Log proxy status at agent startup.

    Args:
        agent_name: Name of the agent
        proxy_url: The proxy URL being used
        is_using_proxy: Whether the agent is configured to use a proxy

    Returns:
        dict with health check results
    """
    result = {
        "agent": agent_name,
        "is_using_proxy": is_using_proxy,
        "proxy_url": proxy_url if is_using_proxy else None,
        "proxy_healthy": None,
        "proxy_error": None,
    }

    if not is_using_proxy:
        return result

    # Run health check
    is_healthy = check_proxy_health(proxy_url)
    result["proxy_healthy"] = is_healthy

    if not is_healthy:
        result["proxy_error"] = f"Proxy endpoint {proxy_url} is not reachable"
        print(f"  WARNING: Proxy health check failed for {agent_name}")
    else:
        print(f"  Proxy health check PASSED for {agent_name}")

    # Log to ledger for observability
    _append_ledger({
        "event": "PROXY_HEALTH_CHECK",
        "ts": datetime.now().isoformat(),
        "agent": agent_name,
        "proxy_url": proxy_url,
        "proxy_healthy": is_healthy,
        "proxy_error": result.get("proxy_error"),
    })

    return result


def categorize_error(error_msg: str, output_content: str = None) -> str:
    """Categorize error into structured error types.

    Args:
        error_msg: The error message
        output_content: Optional stdout content for additional context

    Returns:
        Error type string: SIGTERM_KILLED, PROXY_AUTH, PROXY_ERROR, RATE_LIMIT, MODEL_FAILURE,
                          STALL_TIMEOUT, VERIFICATION_FAILED, AUTH, or UNKNOWN
    """
    if not error_msg:
        return "UNKNOWN"

    combined = (error_msg or "") + " " + (output_content or "")
    combined_lower = combined.lower()

    # O002: SIGTERM / fast-failure detection (highest priority - prevents blind retries)
    # Signal patterns indicating process was killed before completion
    if any(pattern in combined_lower for pattern in [
        "signal 15", "signal -15", "sigterm", "terminated", "killed",
        "exit_code=-15", "exit_code=15", "returncode=-15", "returncode=15",
        "process was terminated", "received termination signal"
    ]):
        return "SIGTERM_KILLED"

    # Model fallback failures (check first - highest priority for this fix)
    if any(pattern in combined_lower for pattern in [
        "model_fallback_failed", "fallback to claude", "both models failed"
    ]):
        return "MODEL_FAILURE"

    # Stall timeout
    if any(pattern in combined_lower for pattern in [
        "stall_timeout", "stall_detected", "no stdout for"
    ]):
        return "STALL_TIMEOUT"

    # Verification failures (also check with spaces, not just underscores)
    if any(pattern in combined_lower for pattern in [
        "verification_failed", "verification failed", "test failed",
        "assertion failed", "test assertion"
    ]):
        return "VERIFICATION_FAILED"

    # Proxy/rate limit errors
    if any(pattern in combined_lower for pattern in [
        "rate limit", "too many requests", "quota exceeded", "429",
        "over capacity", "capacity exceeded"
    ]):
        return "RATE_LIMIT"

    # Proxy authentication errors (check after model failure)
    if any(pattern in combined_lower for pattern in [
        "unauthorized", "authentication", "invalid token", "api key",
        "sk-sp-", "credential", "permission denied"
    ]):
        if "proxy" in combined_lower or "dashscope" in combined_lower:
            return "PROXY_AUTH"
        return "AUTH"

    # Generic proxy errors
    if any(pattern in combined_lower for pattern in [
        "proxy", "dashscope", "connection refused", "connection error",
        "network error", "urlopen error"
    ]):
        return "PROXY_ERROR"

    return "UNKNOWN"


def save_error_content(agent_name: str, task_id: str, error_msg: str,
                       output_content: str, error_type: str) -> str:
    """Save full error content to a persistent file before any truncation.

    Args:
        agent_name: Name of the agent
        task_id: Task ID
        error_msg: The error message
        output_content: stdout content from execution
        error_type: Categorized error type

    Returns:
        Path to saved error file
    """
    from pathlib import Path

    error_dir = Path(f"{AGENTS_DIR}/{agent_name}/errors")
    error_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    error_file = error_dir / f"{task_id}-{timestamp}.error.md"

    content = f"""# Task Error Report

**Task ID:** {task_id}
**Agent:** {agent_name}
**Error Type:** {error_type}
**Timestamp:** {datetime.now().isoformat()}

## Error Message

```
{error_msg}
```

## Output Content

```
{output_content[:10000] if output_content else '(no output)'}
```
"""

    with open(error_file, 'w') as f:
        f.write(content)

    return str(error_file)


def _is_rate_limit_error(error_msg, stdout_content=None):
    """Detect rate limit / quota errors from Claude Code output.

    Returns True if the error indicates rate limiting, quota exceeded,
    or model unavailability that could be resolved by switching models.

    Args:
        error_msg: The stderr or error content
        stdout_content: Optional stdout content to also check (some errors appear in stdout)
    """
    if not error_msg and not stdout_content:
        return False

    # Combine error and stdout for checking
    combined = (error_msg or "") + " " + (stdout_content or "")
    combined_lower = combined.lower()

    # Rate limit patterns - expanded for comprehensive coverage
    rate_limit_patterns = [
        # Standard rate limiting
        "rate limit",
        "rate_limited",
        "rate-limit",
        "too many requests",
        "429",
        # Quota/capacity issues
        "quota exceeded",
        "quota limit",
        "capacity exceeded",
        "insufficient capacity",
        "over capacity",
        "temporarily unavailable",
        "try again later",
        "please retry",
        "retry after",
        # Anthropic-specific errors
        "model is not supported",  # Model config error - also triggers fallback
        "model not available",
        "invalid model",
        "model does not exist",
        "model not found",
        "unsupported model",
        "overloaded",
        "server error",
        "503",
        "529",  # Anthropic's overloaded error code
        # API key/billing issues that might resolve with different model
        "billing quota",
        "credit limit",
        "payment required",
        "402",
        # Authentication failures - trigger fallback to different provider
        "not logged in",
        "please run /login",
        "authentication failed",
        "auth failed",
        "invalid credentials",
        "unauthorized",
        "401",
        "token expired",
        "session expired",
        "sign in required",
        "login required",
        "claude login",
    ]

    return any(pattern in combined_lower for pattern in rate_limit_patterns)


# Stall detection (T14): abort tasks that produce no stdout for too long
# Base thresholds: 15 min (reduced from 10 min to reduce premature task kills)
STALL_SILENCE_THRESHOLD = 900  # seconds of no output before considering stall
STALL_MIN_ELAPSED = 900        # only check for stalls after this many seconds elapsed
# Slow skills get more generous stall thresholds (inference + subagent planning takes time)
SLOW_SKILL_STALL_SILENCE = 1200   # 20 min silence allowed for horde skills
SLOW_SKILL_STALL_ELAPSED = 1200   # don't check until 20 min for horde skills
# High priority tasks also get relaxed thresholds (complex tasks need more time)
HIGH_PRIORITY_STALL_SILENCE = 1200
HIGH_PRIORITY_STALL_ELAPSED = 1200
# Proxy endpoints (like z.ai) can have longer response times for complex reasoning
PROXY_STALL_SILENCE = 2400   # 40 min silence allowed when using proxy (z.ai, openrouter, etc.)
PROXY_STALL_ELAPSED = 1800   # don't check until 30 min when using proxy

# R008 skill hint pre-flight check — abort early if agent ignores required skill
R008_PREFLIGHT_ELAPSED = 60   # check for skill invocation after 60 seconds

# Per-skill R008 timeout overrides (ops/review skills need more startup time)
# FIX 2026-03-14: All SLOW_SKILLS now get extended R008 timeout (3 min) to allow skill invocation
# Previously only some skills were listed, causing false R008_VIOLATION for /horde-learn etc.
R008_PREFLIGHT_BY_SKILL = {
    '/kurultai-health': 180,
    '/code-reviewer': 180,
    '/kurultai-model-switcher': 120,
    # All horde skills need extended preflight time (research, brainstorming, implementation)
    '/horde-brainstorming': 180,
    '/golden-horde': 180,
    '/horde-implement': 180,
    '/horde-review': 180,
    '/horde-debug': 180,
    '/horde-learn': 180,
    '/horde-swarm': 180,
    '/horde-test': 180,
    '/horde-plan': 180,
    '/horde-gate-testing': 180,
    # Complex analysis skills
    '/systematic-debugging': 180,
}


def _spawn_haiku_completion(agent_name):
    """Spawn haiku /task-complete in a background thread with timeout.

    Writes a per-agent breadcrumb file so the skill reads the correct task
    (avoids ledger race when two agents complete near-simultaneously).
    Ensures the process is reaped and killed if it hangs.
    """
    def _run():
        log_file = Path.home() / '.openclaw' / 'agents' / 'main' / 'logs' / 'task-complete-debug.log'
        try:
            env_haiku = os.environ.copy()
            env_haiku.pop('CLAUDECODE', None)
            env_haiku['TASK_COMPLETE_AGENT'] = agent_name
            with open(log_file, 'a') as log_f:
                log_f.write(f"[{datetime.now().isoformat()}] Spawning /task-complete for {agent_name}\n")
                proc = subprocess.Popen(
                    [CLAUDE_AGENT, "--model", "glm-5", "/task-complete"],
                    stdout=log_f, stderr=log_f,
                    close_fds=True,
                    env=env_haiku,
                )
            try:
                return_code = proc.wait(timeout=HAIKU_TIMEOUT)
                with open(log_file, 'a') as log_f:
                    log_f.write(f"[{datetime.now().isoformat()}] /task-complete for {agent_name} exited with {return_code}\n")
            except subprocess.TimeoutExpired:
                # FIX 2026-03-12: Try SIGTERM first before SIGKILL
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                with open(log_file, 'a') as log_f:
                    log_f.write(f"[{datetime.now().isoformat()}] /task-complete for {agent_name} TIMED OUT after {HAIKU_TIMEOUT}s\n")
        except Exception as e:
            with open(log_file, 'a') as log_f:
                log_f.write(f"[{datetime.now().isoformat()}] /task-complete for {agent_name} FAILED: {e}\n")

    threading.Thread(target=_run, daemon=True).start()

def load_agent_config(agent_name):
    """Load agent configuration with fallback for missing config.json.

    Returns agent config dict, falling back to defaults if config.json
    doesn't exist. This prevents dispatch failures when agents don't
    have explicit config.json files.
    """
    config_path = f"{AGENTS_DIR}/{agent_name}/config.json"

    # Default configuration for agents without config.json
    default_config = {
        'task_queue_path': f"{AGENTS_DIR}/{agent_name}/tasks",
        'model': None,  # Will fall back to settings.json
    }

    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            # Merge with defaults (config values take precedence)
            return {**default_config, **config}
    except FileNotFoundError:
        # Config doesn't exist - use defaults
        return default_config
    except json.JSONDecodeError as e:
        print(f"[CONFIG] Invalid JSON in {config_path}: {e}, using defaults")
        return default_config

def load_acp_fallback_config():
    """Load ACP fallback configuration from openclaw.json.

    Returns dict with fallback configuration:
    - enabled: bool - whether fallback is enabled
    - fallback_model: str - model to use when rate limited
    - max_retries: int - max retries with fallback
    - log_events: bool - whether to log fallback events
    """
    try:
        openclaw_config_path = os.path.expanduser("~/.openclaw/openclaw.json")
        with open(openclaw_config_path, 'r') as f:
            config = json.load(f)

        acp_config = config.get('acp', {})
        fallback_config = acp_config.get('fallback', {})

        return {
            'enabled': fallback_config.get('enabled', True),
            'fallback_model': fallback_config.get('fallbackModel', FALLBACK_MODEL),
            'trigger_on_rate_limit': fallback_config.get('triggerOnRateLimit', True),
            'trigger_on_stall': fallback_config.get('triggerOnStallTimeout', True),
            'max_retries': fallback_config.get('maxRetries', MAX_RATE_LIMIT_RETRIES),
            'log_events': fallback_config.get('logEvents', True),
        }
    except Exception:
        # Return defaults if config cannot be loaded
        return {
            'enabled': True,
            'fallback_model': FALLBACK_MODEL,
            'trigger_on_rate_limit': True,
            'trigger_on_stall': True,
            'max_retries': MAX_RATE_LIMIT_RETRIES,
            'log_events': True,
        }

def get_pending_tasks(agent_name):
    """Get pending tasks from agent's queue.

    Parses task frontmatter for metadata including:
    - task_id, skill_hint, priority (existing)
    - audience, clarification_deadline (new communication fields)
    - context_history (previous agent work for cross-agent clarity)
    - output_format (expected deliverables)
    """
    config = load_agent_config(agent_name)
    task_queue_path = config.get('task_queue_path', f"{AGENTS_DIR}/{agent_name}/tasks")

    tasks = []
    for pattern in ['high-*.md', 'normal-*.md', 'low-*.md']:
        for task_file in glob.glob(f"{task_queue_path}/{pattern}"):
            if not task_file.endswith('.executing.md') and not task_file.endswith('.done.md'):
                # Read task content
                with open(task_file, 'r') as f:
                    content = f.read()

                # Extract task description
                task_desc = content
                for line in content.split('\n'):
                    if line.startswith('# Task:'):
                        task_desc = line.replace('# Task:', '').strip()
                        break

                # Determine priority from filename
                priority = 'normal'
                if 'high-' in task_file:
                    priority = 'high'
                elif 'low-' in task_file:
                    priority = 'low'

                # Extract frontmatter fields
                task_id = _extract_task_id(content, filepath=task_file)
                skill_hint = _extract_skill_hint(content)
                depth = _extract_depth(content)

                # Extract new communication/context fields
                audience = _extract_audience(content)
                clarification_deadline = _extract_clarification_deadline(content)
                context_history = _extract_context_history(content)
                output_format = _extract_output_format(content)

                task_dict = {
                    'file': task_file,
                    'task': task_desc,
                    'priority': priority,
                    'created': datetime.fromtimestamp(os.path.getmtime(task_file)).isoformat(),
                    'full_content': content,  # Pass full content for execution
                    'task_id': task_id,
                    'skill_hint': skill_hint,
                    'depth': depth,
                    'audience': audience,
                    'clarification_deadline': clarification_deadline,
                    'context_history': context_history,
                    'output_format': output_format,
                }

                tasks.append(task_dict)

    # Sort by priority
    priority_order = {'high': 0, 'normal': 1, 'low': 2}
    tasks.sort(key=lambda x: priority_order.get(x['priority'], 1))

    return tasks

def _write_pid_file(executing_file):
    """Write PID sentinel alongside .executing.md so recovery can check liveness.

    Format: PID\nSTART_TIMESTAMP (Unix timestamp as float)
    The timestamp allows recovery to calculate true process age regardless of file modifications.
    """
    pid_file = executing_file.replace('.executing.md', '.executing.pid')
    start_ts = time.time()
    with open(pid_file, 'w') as f:
        f.write(f"{os.getpid()}\n{start_ts}")


def _cleanup_pid_file(executing_file):
    """Remove PID sentinel file."""
    pid_file = executing_file.replace('.executing.md', '.executing.pid')
    try:
        os.unlink(pid_file)
    except OSError:
        pass


# O_EXCL constant for file locking (may not be available on all platforms)
O_OEXCL = os.O_EXCL if hasattr(os, 'O_EXCL') else 0x800


def _already_completed(source_path):
    """Check if a .done.md file (any terminal state) already exists for this task.

    Terminal states include: .completed.done.md, .failed.done.md, .no_output.done.md,
    .credential_failed.done.md (added 2026-03-09), .investigation_required.done.md (added 2026-03-11).

    This prevents the rename race condition where recover_stale_executions() tries to
    recover a task that mark_task_completed() already finished. Returns True if
    the task is already done and the .executing.md file should just be cleaned up.

    This matches the logic in task-watcher.py to ensure both sides of the race
    use the same completion detection.
    """
    import re
    from pathlib import Path

    source_path = Path(source_path)
    stem = source_path.name.replace('.executing.md', '').replace('.executing', '')
    # Strip retry suffixes to get the base stem
    stem_base = re.sub(r'\.retry-\d+', '', stem)
    parent = source_path.parent

    for done_file in parent.iterdir():
        if not done_file.name.endswith('.done.md'):
            continue
        # Check for all terminal states: .completed.done.md, .failed.done.md, .no_output.done.md,
        # .dup-orphan.done.md, .deadpid-orphan.done.md (duplicate recovery)
        # .no_output.done.md added 2026-03-09 to prevent false-positive escalations
        done_stem = None
        if '.completed.done.md' in done_file.name:
            done_stem = done_file.name.split('.completed.done.md')[0]
        elif '.failed.done.md' in done_file.name:
            done_stem = done_file.name.split('.failed.done.md')[0]
        elif '.no_output.done.md' in done_file.name:
            done_stem = done_file.name.split('.no_output.done.md')[0]
        elif '.dup-orphan.done.md' in done_file.name:
            done_stem = done_file.name.split('.dup-orphan.done.md')[0]
        elif '.deadpid-orphan.done.md' in done_file.name:
            done_stem = done_file.name.split('.deadpid-orphan.done.md')[0]

        if done_stem is None:
            continue
        done_stem_base = re.sub(r'\.retry-\d+', '', done_stem)
        if done_stem_base == stem_base:
            return True
    return False


def _safe_rename_with_lock(source_path, target_path, agent="unknown"):
    """Atomic rename with file lock to prevent race conditions.

    Prevents the race condition where:
    1. Handler checks if file exists -> True
    2. Recovery renames the file to .md
    3. Handler tries to rename to .completed.done.md -> FileNotFoundError

    Uses exclusive file lock per-task-stem to ensure only one process
    handles the rename at a time.

    CRITICAL FIX: Also checks _already_completed() to handle the case where
    the task was completed via a different retry file path. This prevents
    queue metric inflation from VERIFY FAIL on legitimately completed tasks.

    Returns (success: bool, action: str, error: str)
    """
    if not os.path.exists(source_path):
        return False, "skip", "source_not_found"

    # CRITICAL: Check if task is already completed via ANY path
    # This prevents the race where recovery moved the file to a retry path,
    # handler completed it there, but then recovery tries to "recover" the
    # original .executing.md without realizing it's already done.
    if _already_completed(source_path):
        print(f"[SAFE_RENAME] Task already completed: {os.path.basename(source_path)}")
        return False, "skip", "already_completed"

    # Extract task stem for lock file naming
    source_name = os.path.basename(source_path)
    stem = source_name.replace('.executing', '').replace('.md', '')
    import re
    stem_base = re.sub(r'\.retry-\d+', '', stem)
    lock_path = os.path.join(os.path.dirname(source_path), f".{stem_base}.rename-lock")

    lock_fd = None
    try:
        # Create exclusive lock - fails if another process has it
        lock_fd = os.open(lock_path, os.O_CREAT | O_OEXCL | os.O_WRONLY)
    except (FileExistsError, PermissionError):
        # Another process is handling this rename - log for monitoring
        print(f"[SAFE_RENAME] Race prevented: {agent} - lock held for {stem_base}")
        return False, "skip", "concurrent_operation"

    try:
        # CRITICAL: RECHECK completion after acquiring lock (TOCTOU guard)
        if _already_completed(source_path):
            print(f"[SAFE_RENAME] Task already completed (locked): {os.path.basename(source_path)}")
            return False, "skip", "already_completed_locked"

        # RECHECK: source still exists after acquiring lock
        if not os.path.exists(source_path):
            return False, "skip", "source_gone_during_lock_wait"

        # RECHECK: target doesn't already exist (avoid clobbering)
        if os.path.exists(target_path):
            return False, "skip", "target_already_exists"

        # Atomic rename
        os.rename(source_path, target_path)
        return True, "renamed", "ok"

    except FileNotFoundError:
        # File vanished during our operation (race won by another process)
        return False, "skip", "race_file_not_found"
    except OSError as e:
        return False, "error", str(e)
    finally:
        # Always release lock
        try:
            if lock_fd is not None:
                os.close(lock_fd)
            try:
                os.unlink(lock_path)
            except OSError:
                pass
        except (OSError, AttributeError):
            pass


def _verify_task_completion(task_file, max_retries=3):
    """Verify task file has actual execution output before marking as complete.

    CRITICAL FIX: This function now requires the presence of an "## Execution Output"
    section to distinguish actual execution results from the original task description.

    RACE CONDITION FIX (2026-03-08): Uses file locking to prevent false positives
    when the handler is still writing output. If verification fails, retries with
    exponential backoff to handle slow writes.

    RESOLUTION CHECK (2026-03-09): Substantive completions (>=100 chars) must include
    a resolution section ("## Resolution" or similar) matching /horde-review PRIORITY_FIX.

    R008 SKILL CHECK (2026-03-12 ENFORCED): Skill invocation is MANDATORY.
    The prompt includes explicit instruction to call Skill tool BEFORE any other work.
    Tasks with skill_hint that have no invocation evidence will FAIL verification.
    This is a blocking precondition - no work is valid without skill invocation.

    Checks:
    - Has "## Execution Output" section (added by _append_output_to_executing)
    - Content AFTER "## Execution Output" has substance (not just empty)
    - At least 4 non-empty lines of actual execution output
    - Resolution section present for substantive outputs (>=100 chars)
    - Skill invocation evidence when skill_hint is present (R008)

    Returns tuple: (is_valid, reason)
    """
    import fcntl
    import re as re_module

    # Extract skill_hint from frontmatter for R008 check
    skill_hint = None
    try:
        with open(task_file, 'r') as f:
            frontmatter = f.read(1000)
            match = re_module.search(r'^skill_hint:\s*(\S+)', frontmatter, re_module.MULTILINE)
            if match:
                skill_hint = match.group(1)
    except Exception:
        pass

    for attempt in range(max_retries):
        try:
            # Acquire shared lock to wait for any writer to finish
            fd = None
            try:
                fd = os.open(task_file, os.O_RDONLY)
                fcntl.flock(fd, fcntl.LOCK_SH)  # Wait for exclusive lock to release
            except (FileNotFoundError, OSError):
                if attempt < max_retries - 1:
                    time.sleep(0.1 * (2 ** attempt))  # Exponential backoff
                    continue
                else:
                    return False, f"Verification error: file unavailable after {max_retries} retries"

            try:
                with open(fd, 'r', closefd=False) as f:
                    content = f.read()
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)  # Release lock
                os.close(fd)

            # CRITICAL: Check for execution output section OR resolution section
            # The separator is added by _append_output_to_executing(), but agents
            # may also write directly with ## Resolution (e.g., jochi analysis tasks).
            # FIX 2026-03-12: Accept ## Resolution as alternative completion marker
            # to prevent false no_output markings when _append_output_to_executing fails.
            execution_marker = '## Execution Output'
            resolution_marker = '## Resolution'

            has_execution = execution_marker in content
            has_resolution = resolution_marker in content

            if not has_execution and not has_resolution:
                # If content looks incomplete (too short), retry before failing
                if len(content) < 1000 and attempt < max_retries - 1:
                    time.sleep(0.1 * (2 ** attempt))
                    continue
                return False, f"No execution output section found (missing '{execution_marker}' or '{resolution_marker}')"

            # Determine which marker to use for extraction (prefer execution, fallback to resolution)
            if has_execution:
                output_marker = execution_marker
            else:
                output_marker = resolution_marker

            # SECURITY: Use rsplit() to find the LAST occurrence of the marker,
            # which is always the system-controlled marker. This prevents injection
            # attacks where task descriptions contain the marker.
            parts = content.rsplit(output_marker, 1)
            if len(parts) < 2:
                return False, "Execution output section exists but has no content"

            execution_output = parts[1].strip()

            # If we're using resolution marker (fallback mode), check for status line
            # This is the pattern jochi uses: "**Status:** COMPLETE" or similar
            if output_marker == resolution_marker:
                # For resolution-mode, check if there's a status line (strong indicator of valid completion)
                output_upper = execution_output.upper()
                has_status = (
                    "**STATUS:" in output_upper
                    or "STATUS:" in output_upper
                    or "COMPLETED" in output_upper
                    or "COMPLETE" in output_upper
                )
                if not has_status and len(execution_output) < 200:
                    # Resolution without status line and short content = likely incomplete
                    return False, "Resolution section missing status line (add '**Status:**' or '## Status')"

            # Count actual execution output lines (non-empty, excluding known metadata patterns)
            # Only filter lines that are EXACTLY metadata format, not all bold text
            metadata_pattern = re_module.compile(r'^\*\*(Model|Duration|Status|Timestamp|Session|Agent|Task ID):\*\*')

            exec_lines = [l for l in execution_output.split('\n')
                          if l.strip()
                          and not metadata_pattern.match(l.strip())  # only filter known metadata
                          and not l.strip() == '---']

            # Require at least 4 lines of actual output (lowered to reduce fix-resolution churn)
            # 4 lines is enough to distinguish real completions from empty/bogus files
            # while accommodating brief fix-resolution tasks (5-7 lines is common)
            if len(exec_lines) < 4:
                # Might be incomplete write - retry if content looks truncated
                if not execution_output.endswith('```') and attempt < max_retries - 1:
                    time.sleep(0.1 * (2 ** attempt))
                    continue
                return False, f"Execution output too short ({len(exec_lines)} lines, need 4+)"

            # Also check for some substance (not just repeated markers)
            total_output_chars = sum(len(l) for l in exec_lines)
            if total_output_chars < 200:
                return False, f"Execution output too brief ({total_output_chars} chars, need 200+)"

            # RESOLUTION SECTION CHECK (2026-03-09): Match /horde-review PRIORITY_FIX
            # Substantive completions (>=100 chars) must include resolution documentation
            # This catches missing resolutions at verification time, not in later audit
            # FIXED: Case-insensitive check (2026-03-09) to fix false positives from agent output
            if total_output_chars >= 100:
                output_upper = execution_output.upper()
                has_resolution = (
                    "## RESOLUTION" in output_upper
                    or "**STATUS:** RESOLVED" in output_upper
                    or "**STATUS:** COMPLETED" in output_upper
                    or execution_output.count("##") >= 3  # Has multiple sections (likely includes resolution)
                )
                if not has_resolution:
                    return False, f"Missing resolution section (add '## Resolution' or '**Status:** RESOLVED/Completed')"

            # R008 SKILL INVOCATION CHECK (2026-03-12): Informational tracking only
            # Prompt includes mandatory skill instruction (Layer 6), but agent must call it.
            # This logs for compliance monitoring and identifying agents that need prompting.
            if skill_hint:
                skill_name = skill_hint.lstrip('/').replace('-', ' ')
                output_lower = execution_output.lower()

                # Evidence patterns for different skills
                skill_evidence = {
                    '/horde-learn': ['search', 'source', 'research', 'citation', 'finding', 'web'],
                    '/horde-brainstorming': ['proposal', 'brainstorm', 'option', 'approach', 'explore'],
                    '/horde-implement': ['implement', 'code', 'file', 'write', 'create'],
                    '/horde-review': ['review', 'analysis', 'strength', 'weakness', 'finding'],
                    '/horde-debug': ['debug', 'error', 'fix', 'issue', 'problem'],
                    '/systematic-debugging': ['debug', 'error', 'fix', 'issue', 'problem'],
                    '/content-research-writer': ['content', 'article', 'writing', 'draft'],
                    '/code-reviewer': ['review', 'code', 'security', 'vulnerability'],
                    '/scrapling-research': ['scrap', 'crawl', 'fetch', 'extract'],
                }

                # Check for evidence of skill usage
                has_evidence = False
                for keyword in skill_evidence.get(skill_hint, [skill_name]):
                    if keyword in output_lower:
                        has_evidence = True
                        break

                # Also check for explicit skill invocation patterns
                skill_patterns = [
                    f'{skill_hint.lower()}',
                    'skill invoked',
                    'using skill',
                    'skill response',
                ]
                if any(p in output_lower for p in skill_patterns):
                    has_evidence = True

                # R008 ENFORCEMENT (2026-03-12): Skill invocation is MANDATORY
                # Task FAILS if skill_hint present but no invocation evidence found
                if not has_evidence:
                    print(f"  ❌ R008 VIOLATION: Required skill '{skill_hint}' was NOT invoked")
                    print(f"     Task rejected per R008 mandatory skill invocation rule")
                    # Track for compliance monitoring
                    try:
                        _track_r008_violation("verify", skill_hint, skill_hint)
                    except Exception:
                        pass  # Tracking failure is non-critical
                    return False, f"R008 violation: Required skill '{skill_hint}' was not invoked"

            return True, "OK"

        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(0.1 * (2 ** attempt))
                continue
            return False, f"Verification error: {e}"

    return False, "Verification failed: max retries exceeded"


def _run_pre_submit_check(task_file):
    """Run pre-submit verification before marking task complete (K001 / R009).

    This enforces the K001 behavioral rule: "Pre-Submit Quality Check (R009)"
    which requires agents to run pre_submit_check.py before marking tasks complete.

    The check validates:
    - Content length (500+ chars)
    - Structure (3+ headings)
    - Resolution section presence

    Returns tuple: (passed, reason)
    - passed: True if check passed, False otherwise
    - reason: Error message if failed, empty string if passed
    """
    script_path = os.path.join(os.path.dirname(__file__), 'pre_submit_check.py')

    if not os.path.exists(script_path):
        print(f"[PRE_SUBMIT] ⚠ pre_submit_check.py not found at {script_path}")
        return True, ""  # Don't block if script is missing

    try:
        result = subprocess.run(
            ['python3', script_path, task_file],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            print(f"[PRE_SUBMIT] ✓ Quality check passed")
            return True, ""
        else:
            # Parse the output to get the failure reason
            reason = "Quality gate failed"
            if result.stdout:
                for line in result.stdout.split('\n'):
                    if 'Content length' in line or 'Structure' in line or 'Resolution' in line:
                        reason = line.strip()
                        break
            print(f"[PRE_SUBMIT] ✗ {reason}")
            return False, reason
    except subprocess.TimeoutExpired:
        print(f"[PRE_SUBMIT] ⚠ Check timed out (allowing completion)")
        return True, ""  # Don't block on timeout
    except Exception as e:
        print(f"[PRE_SUBMIT] ⚠ Check error (non-fatal): {e}")
        return True, ""  # Don't block on errors


def _append_output_to_executing(executing_file, content, model, duration_s, success=True):
    """Append execution output to .executing.md file before completion verification.

    This is CRITICAL for fake completion prevention. The verification function
    checks the .executing.md file for substantial output, so we must append
    the actual execution results BEFORE marking as done.

    RACE CONDITION FIX (2026-03-08): Uses exclusive file locking to ensure
    atomic write and prevent race conditions with verification reads.

    Args:
        executing_file: Path to .executing.md file
        content: Execution output content (stdout result or error)
        model: Model used for execution
        duration_s: Execution duration in seconds
        success: True if successful execution, False if failed
    """
    import fcntl

    if not os.path.exists(executing_file):
        print(f"  ⚠ Executing file missing during output append: {executing_file}")
        return False

    try:
        # Open for append with exclusive lock to ensure atomic write
        with open(executing_file, 'a') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # Exclusive lock
            try:
                f.write(f"\n\n## Execution Output\n\n")
                f.write(f"**Model:** {model}\n")
                f.write(f"**Duration:** {duration_s}s\n")
                f.write(f"**Status:** {'Completed' if success else 'Failed'}\n")
                f.write(f"\n---\n\n")
                f.write(content)
                f.write(f"\n")
                f.flush()  # Ensure data is written to disk
                os.fsync(f.fileno())  # Force sync to disk
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)  # Release lock
        return True
    except Exception as e:
        print(f"  ⚠ Failed to append output to executing file: {e}")
        return False


def mark_task_executing(task_file):
    """Mark task as being executed and write PID sentinel.

    CRITICAL: Write PID file BEFORE renaming to eliminate race condition.
    If subprocess_health_check runs between rename and PID write, it will
    incorrectly clear the task as "no PID file" (see ogedei reflection 2026-03-11).
    """
    executing_file = task_file.replace('.md', '.executing.md')
    # Write PID file FIRST while task_file still exists
    # This ensures subprocess_health_check always finds a PID for .executing.md files
    pid_file = executing_file.replace('.executing.md', '.executing.pid')
    start_ts = time.time()
    with open(pid_file, 'w') as f:
        f.write(f"{os.getpid()}\n{start_ts}")
    # Now rename - subprocess_health_check will see valid .executing.pid
    os.rename(task_file, executing_file)
    return executing_file


def mark_task_completed(task_file, status='completed', executing_file=None):
    """Mark task as completed.

    Handles the race where recover_stale_executions() renames the
    .executing.md file before this function runs. Falls back to searching
    for retry files created by recovery.

    Args:
        task_file: Original task file path (before .executing rename).
        status: 'completed', 'failed', 'no_output', 'credential_failed', or 'investigation_required'.
                'credential_failed' and 'investigation_required' are terminal states that bypass revision loops.
        executing_file: Actual .executing.md path if known (preferred).
    """
    # Extract agent name from task file path for circuit breaker + safe rename lock
    # Path format: /Users/kublai/.openclaw/agents/{agent}/tasks/{task}.md
    agent = "unknown"
    path_parts = Path(task_file).parts
    if 'agents' in path_parts:
        agent_idx = path_parts.index('agents')
        if agent_idx + 1 < len(path_parts):
            agent = path_parts[agent_idx + 1]

    # Record result for circuit breaker (non-blocking)
    if _circuit_breaker:
        try:
                    # Extract task_id from task file for logging
                    task_id = None
                    try:
                        with open(executing_file or task_file.replace('.md', '.executing.md'), 'r') as f:
                            content = f.read(2000)
                            import re
                            task_match = re.search(r'task_id:\s*(\S+)', content)
                            if task_match:
                                task_id = task_match.group(1)
                    except Exception:
                        pass

                    # Determine success (completed = True, failed/no_output = False)
                    success = status == 'completed'
                    _circuit_breaker.record_result(agent, success, task_id)
        except Exception as e:
            print(f"[circuit_breaker] Record result failed (non-fatal): {e}")

    if executing_file is None:
        if task_file.endswith('.executing.md'):
            executing_file = task_file
        else:
            executing_file = task_file.replace('.md', '.executing.md')

    # Verify completion before marking as done (prevent fake completions)
    if status == 'completed' and os.path.exists(executing_file):
        is_valid, reason = _verify_task_completion(executing_file)
        if not is_valid:
            print(f"⚠ COMPLETION VERIFICATION FAILED: {reason}")
            print(f"   Marking as no_output instead of completed")
            status = 'no_output'
            # Log to ledger for tracking
            try:
                _append_ledger({
                    "event": "COMPLETION_VERIFICATION_FAILED",
                    "ts": datetime.now().isoformat(),
                    "task_file": task_file,
                    "reason": reason,
                    "original_status": "completed",
                    "new_status": "no_output"
                })
            except Exception:
                pass  # Don't block on ledger failure

    # ==========================================================
    # COMPLETION GATE AUDIT (runs before final .done.md rename)
    # ==========================================================
    # Check if task should go through completion gate
    # Gate runs for:
    # - Tasks with completion_gate: true in frontmatter, OR
    # - High priority tasks (gradual rollout - Phase 1)
    #
    # Gate skips for:
    # - Tasks with completion_gate_optout: true
    # - Tasks with depth > 2 (follow-up follow-ups)
    # - Trivial tasks (< 100 lines of output)
    # - Failed/no_output status
    #
    # Design: ~/.openclaw/agents/mongke/workspace/completion-gate-design-2026-03-08.md

    gate_enabled = False
    gate_result = None

    if status == 'completed' and os.path.exists(executing_file):
        try:
            # Read frontmatter to check gate settings
            with open(executing_file, 'r') as f:
                content = f.read(5000)
                frontmatter_lower = content.lower()

            # VULN-2 FIX: Check for explicit opt-out with agent-source validation
            # Agents are NOT allowed to opt themselves out - only Kublai/humans can grant opt-out
            has_optout_flag = 'completion_gate_optout:true' in frontmatter_lower or \
                             'completion_gate_optout: true' in frontmatter_lower

            # Check who created this task (source field)
            # Agents cannot opt out their own tasks
            source_match = re.search(r'source:\s*(\S+)', content)
            task_source = source_match.group(1) if source_match else "unknown"

            # Agent sources that cannot grant opt-out
            agent_sources = ['mongke', 'chagatai', 'temujin', 'jochi', 'ogedei', 'tolui',
                           'kublai_router', 'task-redistribute', 'completion-gate']

            opt_out_denied = False
            if has_optout_flag:
                # Check if source is an agent (cannot self-opt-out)
                if any(agent_s in task_source.lower() for agent_s in agent_sources):
                    print(f"[COMPLETION_GATE] ❌ OPT-OUT DENIED - agent '{task_source}' cannot self-opt-out")
                    opt_out_denied = True

                    # Log to security if available
                    try:
                        from security_event_logger import log_security_event, EventType, Severity
                        task_id_match = re.search(r'task_id:\s*(\S+)', content)
                        task_id = task_id_match.group(1) if task_id_match else "unknown"
                        log_security_event(
                            event_type=EventType.OPT_OUT_DENIED,
                            severity=Severity.MEDIUM,
                            details={
                                "task_id": task_id,
                                "source": task_source,
                                "reason": "Agent attempted self-opt-out"
                            }
                        )
                    except ImportError:
                        pass  # Security logger not available

                # Check rate limit for opt-outs (prevent abuse)
                # Only 3 opt-outs per day per agent
                optout_log = Path.home() / ".openclaw" / "logs" / "optout-ratelimit.log"
                optout_log.parent.mkdir(parents=True, exist_ok=True)

                today = datetime.now().strftime('%Y-%m-%d')
                today_count = 0

                if optout_log.exists():
                    with open(optout_log, 'r') as f:
                        for line in f:
                            if line.strip().startswith(today):
                                today_count += 1

                if today_count >= 3:
                    print(f"[COMPLETION_GATE] ❌ OPT-OUT DENIED - daily limit exceeded (3/day)")
                    opt_out_denied = True
                else:
                    # Log this opt-out
                    with open(optout_log, 'a') as f:
                        f.write(f"{today} optout_granted\n")

            if has_optout_flag and not opt_out_denied:
                print("[COMPLETION_GATE] Opted out via frontmatter (authorized)")
            elif opt_out_denied:
                print("[COMPLETION_GATE] Opt-out flag ignored - proceeding with gate audit")
                has_optout_flag = False  # Force gate to run

            if not has_optout_flag:
                # Check if gate is explicitly enabled
                if 'completion_gate:true' in frontmatter_lower or \
                   'completion_gate: true' in frontmatter_lower:
                    gate_enabled = True
                    print("[COMPLETION_GATE] Enabled via frontmatter")
                # Phase 1 rollout: High priority tasks
                elif 'priority: high' in frontmatter_lower or 'priority:critical' in frontmatter_lower:
                    # Check depth - skip deep follow-up chains
                    depth_match = re.search(r'depth:\s*(\d+)', content)
                    depth = int(depth_match.group(1)) if depth_match else 0
                    if depth <= 2:
                        gate_enabled = True
                        print(f"[COMPLETION_GATE] Enabled for high-priority task (depth={depth})")

            if gate_enabled:
                print("[COMPLETION_GATE] Running audit...")

                # Import audit module (consolidated v2 in completion_gate_audit.py)
                try:
                    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                    from completion_gate_audit import completion_gate_audit_v2, save_audit_log_v2, create_followup_tasks_v2
                    use_v2 = True
                    print("[COMPLETION_GATE] Using v2 audit (three-tier fallback)")

                    # Extract agent from path
                    path_parts = Path(executing_file).parts
                    agent = path_parts[path_parts.index('agents') + 1] if 'agents' in path_parts else 'temujin'

                    # Run the audit
                    gate_result = completion_gate_audit_v2(Path(executing_file), agent)

                    print(f"[COMPLETION_GATE] Completion: {gate_result.completion_percentage}%")
                    print(f"[COMPLETION_GATE] Can complete: {gate_result.can_complete}")

                    # v2-specific logging
                    if hasattr(gate_result, 'audit_tier'):
                        print(f"[COMPLETION_GATE] Audit Tier: {gate_result.audit_tier}")
                        if hasattr(gate_result, 'retries_performed') and gate_result.retries_performed > 0:
                            print(f"[COMPLETION_GATE] Retries: {gate_result.retries_performed}")
                        if hasattr(gate_result, 'audit_fallback') and gate_result.audit_fallback:
                            print(f"[COMPLETION_GATE] ⚠️ WARNING: Permissive fallback used - manual review recommended")

                    # Save audit result
                    audit_path = save_audit_log_v2(gate_result, Path(executing_file))
                    print(f"[COMPLETION_GATE] Audit saved to: {audit_path}")

                    # Check gate result
                    if not gate_result.can_complete:
                        print(f"[COMPLETION_GATE] ❌ Gate FAILED - {len(gate_result.required_followups)} required follow-ups")

                        # Create follow-up tasks
                        task_metadata = extract_frontmatter(Path(executing_file))
                        if use_v2:
                            followup_paths = create_followup_tasks_v2(gate_result, task_metadata, executing_file)
                        else:
                            followup_paths = create_followup_tasks(gate_result, task_metadata)

                        print(f"[COMPLETION_GATE] Created {len(followup_paths)} follow-up tasks")

                        # Rename to .pending-gate.md instead of .done.md (with safe lock)
                        pending_gate_file = executing_file.replace('.executing.md', '.pending-gate.md')
                        success, action, detail = _safe_rename_with_lock(executing_file, pending_gate_file, agent)
                        if success:
                            print(f"[COMPLETION_GATE] Task renamed to: {os.path.basename(pending_gate_file)}")

                            # Update Neo4j gate status
                            try:
                                from neo4j_task_tracker import get_tracker
                                tracker = get_tracker()
                                tracker.update_gate_status(
                                    gate_result.original_task,
                                    "WAITING_FOLLOWUPS",
                                    completion_percentage=gate_result.completion_percentage,
                                    audit_ref=str(audit_path)
                                )
                            except Exception:
                                pass  # Neo4j not available

                            # Log to ledger
                            try:
                                _append_ledger({
                                    "event": "COMPLETION_GATE_BLOCKED",
                                    "ts": datetime.now().isoformat(),
                                    "task_file": task_file,
                                    "task_id": gate_result.original_task,
                                    "completion_percentage": gate_result.completion_percentage,
                                    "followups_created": len(followup_paths),
                                    "blockers": gate_result.blockers,
                                    "audit_ref": str(audit_path)
                                })
                            except Exception:
                                pass  # Don't block on ledger failure

                            # Clean up PID file and return (task not complete)
                            _cleanup_pid_file(executing_file)
                            return False
                        else:
                            print(f"[COMPLETION_GATE] Error renaming to pending-gate: {action} - {detail}")
                            # Fall through to normal completion on error
                    else:
                        print(f"[COMPLETION_GATE] ✓ Gate PASSED - task can complete")

                except ImportError as e:
                    print(f"[COMPLETION_GATE] Audit module not available: {e}")
                    print("[COMPLETION_GATE] Continuing without gate check")
                except Exception as e:
                    print(f"[COMPLETION_GATE] Audit failed: {e}")
                    print("[COMPLETION_GATE] Continuing without gate check (non-fatal)")

        except Exception as e:
            print(f"[COMPLETION_GATE] Gate check error (non-fatal): {e}")

    # ==========================================================
    # END COMPLETION GATE
    # ==========================================================

    # ==========================================================
    # K001 PRE-SUBMIT QUALITY CHECK (R009)
    # ==========================================================
    # Enforce behavioral rule: All completions must pass quality gate
    # This prevents tasks without resolution sections from completing
    # Implements: K001 "Pre-Submit Quality Check (R009)" from rules.json
    #
    # Runs for:
    # - All status='completed' tasks (no opt-out)
    #
    # Skips for:
    # - Failed/no_output status (already flagged as problematic)
    #
    # Design: ~/memory/when_then_rules.md (R009)

    if status == 'completed' and os.path.exists(executing_file):
        print("[PRE_SUBMIT] Running K001 quality check...")
        pre_submit_passed, pre_submit_reason = _run_pre_submit_check(executing_file)

        if not pre_submit_passed:
            print(f"[PRE_SUBMIT] ❌ Quality gate BLOCKED: {pre_submit_reason}")
            print(f"[PRE_SUBMIT] Marking as failed instead of completed")
            status = 'failed'
            completed_suffix = f'.{status}.done.md'

            # Log to ledger for tracking
            try:
                _append_ledger({
                    "event": "PRE_SUBMIT_GATE_BLOCKED",
                    "ts": datetime.now().isoformat(),
                    "task_file": task_file,
                    "reason": pre_submit_reason,
                    "original_status": "completed",
                    "new_status": "failed"
                })
            except Exception:
                pass  # Don't block on ledger failure
        else:
            print("[PRE_SUBMIT] ✓ Quality check passed - task can complete")

    # ==========================================================
    # END K001 PRE-SUBMIT CHECK
    # ==========================================================

    completed_suffix = f'.{status}.done.md'

    # Normal path: .executing.md still exists
    if os.path.exists(executing_file):
        completed_file = executing_file.replace('.executing.md', completed_suffix)
        # Use safe rename with file lock to prevent race conditions
        success, action, detail = _safe_rename_with_lock(executing_file, completed_file, agent)
        if success:
            _cleanup_pid_file(executing_file)
            
            # Clear Neo4j session_key to prevent stale claim accumulation
            try:
                from clear_neo4j_session_key import clear_session_key_for_task
                clear_session_key_for_task(executing_file)
            except Exception as e:
                print(f"[mark_task_completed] Failed to clear session_key (non-fatal): {e}")
            
            print(f"✓ Task {status}: {completed_file}")
            return True
        elif action == "skip" and detail in ("source_not_found", "source_gone_during_lock_wait", "target_already_exists"):
            # File was already handled by another process (race won by recovery)
            print(f"⚠ Race detected: {os.path.basename(executing_file)} already handled ({detail})")
            # Fall through to verification below
        else:
            # Unexpected error
            print(f"✗ Safe rename failed: {action} - {detail}")
            # Fall through to fallback path

    # .executing.md is gone — recovery renamed it
    print(f"⚠ Executing file missing: {os.path.basename(executing_file)}")

    task_dir = os.path.dirname(executing_file)
    stem = os.path.basename(executing_file).replace('.executing.md', '')

    # Search for retry files that recovery created (e.g., stem.retry-2.md)
    for candidate in sorted(glob.glob(os.path.join(task_dir, f"{stem}*.md"))):
        basename = os.path.basename(candidate)
        if '.done.md' in basename or '.executing' in basename:
            continue

        # CRITICAL: Verify completion before renaming in fallback path too
        # This prevents fake completions when recovery has moved the file
        if status == 'completed':
            # First check: Verify execution output exists (prevents fake completions)
            is_valid, reason = _verify_task_completion(candidate)
            if not is_valid:
                print(f"⚠ FAKE COMPLETION BLOCKED in fallback: {reason}")
                print(f"   Marking as no_output instead of completed")
                status = 'no_output'
                completed_suffix = f'.{status}.done.md'
                try:
                    _append_ledger({
                        "event": "COMPLETION_VERIFICATION_FAILED",
                        "ts": datetime.now().isoformat(),
                        "task_file": task_file,
                        "reason": reason,
                        "original_status": "completed",
                        "new_status": "no_output",
                        "fallback_path": True
                    })
                except Exception:
                    pass  # Don't block on ledger failure
            else:
                # Second check: K001 pre-submit quality gate (prevents missing resolutions)
                # FIX (2026-03-11): Fallback path was bypassing K001, causing 0% resolution compliance
                print("[PRE_SUBMIT] Running K001 quality check in fallback path...")
                pre_submit_passed, pre_submit_reason = _run_pre_submit_check(candidate)

                if not pre_submit_passed:
                    print(f"[PRE_SUBMIT] ❌ Quality gate BLOCKED in fallback: {pre_submit_reason}")
                    print(f"[PRE_SUBMIT] Marking as failed instead of completed")
                    status = 'failed'
                    completed_suffix = f'.{status}.done.md'
                    try:
                        _append_ledger({
                            "event": "PRE_SUBMIT_GATE_BLOCKED_FALLBACK",
                            "ts": datetime.now().isoformat(),
                            "task_file": task_file,
                            "reason": pre_submit_reason,
                            "original_status": "completed",
                            "new_status": "failed"
                        })
                    except Exception:
                        pass  # Don't block on ledger failure
                else:
                    print("[PRE_SUBMIT] ✓ Quality check passed in fallback path")

        completed_file = os.path.join(task_dir, stem + completed_suffix)
        # Use safe rename with file lock to prevent race conditions
        success, action, detail = _safe_rename_with_lock(candidate, completed_file, agent)
        if success:
            _cleanup_pid_file(executing_file)
            print(f"⚠ Task {status} (fallback): {basename} → {os.path.basename(completed_file)}")
            return True
        else:
            print(f"✗ Fallback rename failed: {action} - {detail}")
            # Continue to check if already done

    # Check if already marked done (idempotent)
    for done_candidate in glob.glob(os.path.join(task_dir, f"{stem}*.done.md")):
        print(f"⚠ Task already done: {os.path.basename(done_candidate)}")
        _cleanup_pid_file(executing_file)
        return True

    print(f"✗ No matching file to mark as {status} for: {stem}")
    _cleanup_pid_file(executing_file)
    return False

def _extract_depth(content):
    """Extract depth field from task frontmatter."""
    import re
    match = re.search(r'^depth:\s*(\d+)', content, re.MULTILINE)
    return int(match.group(1)) if match else 0


def _extract_task_id(content, filepath=None):
    """Extract task_id from task frontmatter or filename."""
    import re
    match = re.search(r'^task_id:\s*(\S+)', content, re.MULTILINE)
    if match:
        return match.group(1)
    # Fallback: extract canonical task_id from filename (priority-timestamp-uuid8)
    if filepath:
        fname = Path(filepath).name if not isinstance(filepath, Path) else filepath.name
        canonical = re.search(r'((?:critical|high|normal|low)-\d{10}-[a-f0-9]{8})', fname, re.I)
        if canonical:
            return canonical.group(1).lower()
    return None


def _extract_skill_hint(content):
    """Extract skill_hint from task frontmatter."""
    import re
    match = re.search(r'^skill_hint:\s*(\S+)', content, re.MULTILINE)
    return match.group(1) if match else None


def _extract_audience(content):
    """Extract audience field from task frontmatter.

    Returns: 'agent', 'human', 'both', or None if not specified.
    """
    import re
    match = re.search(r'^audience:\s*(agent|human|both)', content, re.MULTILINE | re.IGNORECASE)
    return match.group(1).lower() if match else None


def _extract_clarification_deadline(content):
    """Extract clarification_deadline from task frontmatter.

    Returns: ISO8601 datetime string or None if not specified.
    Validates the format is parseable.
    """
    import re
    from datetime import datetime
    match = re.search(r'^clarification_deadline:\s*(\S+)', content, re.MULTILINE)
    if not match:
        return None
    deadline_str = match.group(1)
    # Validate it's a valid ISO8601 format
    try:
        datetime.fromisoformat(deadline_str.replace('Z', '+00:00'))
        return deadline_str
    except ValueError:
        return None


def _extract_context_history(content):
    """Extract context_history list from task frontmatter.

    Parses YAML-style list entries for context history:
        context_history:
          - agent: temujin
            attempt: "Analyzed as implementation task"
            deliverable: "workspace/prelim-analysis.md"

    Returns: List of dicts with agent, attempt, and optional deliverable/findings.
    """
    import re
    history = []
    in_context_history = False
    current_entry = {}

    lines = content.split('\n')
    for i, line in enumerate(lines):
        stripped = line.strip()

        # Detect start of context_history block
        if stripped.startswith('context_history:'):
            in_context_history = True
            continue

        # Detect end of context_history block (another top-level key or end of frontmatter)
        if in_context_history:
            # Check if we've left the context_history block
            # Skip comment lines (start with #)
            if stripped.startswith('#'):
                continue
            # Check for new top-level key (non-indented, contains ':', not a list item)
            if line and not line[0].isspace() and ':' in stripped and not stripped.startswith('-'):
                # New top-level key, end of context_history
                if current_entry:
                    history.append(current_entry)
                break
            if stripped == '---':
                # End of frontmatter
                if current_entry:
                    history.append(current_entry)
                break

            # Parse list item start
            if stripped.startswith('- agent:'):
                # Save previous entry if exists
                if current_entry:
                    history.append(current_entry)
                current_entry = {'agent': stripped.split(':', 1)[1].strip()}
            elif stripped.startswith('attempt:') and current_entry:
                # Extract attempt value (may be quoted)
                val = stripped.split(':', 1)[1].strip().strip('"\'')
                current_entry['attempt'] = val
            elif stripped.startswith('deliverable:') and current_entry:
                val = stripped.split(':', 1)[1].strip().strip('"\'')
                current_entry['deliverable'] = val
            elif stripped.startswith('findings:') and current_entry:
                val = stripped.split(':', 1)[1].strip().strip('"\'')
                current_entry['findings'] = val

    # Don't forget the last entry (in case we didn't hit an end condition)
    if current_entry and current_entry not in history:
        history.append(current_entry)

    return history


def _extract_output_format(content):
    """Extract output_format settings from task frontmatter.

    Parses YAML-style block:
        output_format:
          human_summary: true
          agent_full: true
          deliverable: "workspace/final-report.md"

    Returns: Dict with output format settings.
    """
    import re
    output_format = {}
    in_output_format = False

    lines = content.split('\n')
    for i, line in enumerate(lines):
        stripped = line.strip()

        # Detect start of output_format block
        if stripped.startswith('output_format:'):
            in_output_format = True
            continue

        # Detect end of output_format block
        if in_output_format:
            if line and not line[0].isspace() and ':' in stripped and not stripped.startswith('human_') and not stripped.startswith('agent_') and not stripped.startswith('deliverable'):
                break
            if stripped == '---':
                break

            # Parse settings
            if stripped.startswith('human_summary:'):
                val = stripped.split(':', 1)[1].strip().lower()
                output_format['human_summary'] = val in ('true', 'yes', '1')
            elif stripped.startswith('agent_full:'):
                val = stripped.split(':', 1)[1].strip().lower()
                output_format['agent_full'] = val in ('true', 'yes', '1')
            elif stripped.startswith('deliverable:'):
                val = stripped.split(':', 1)[1].strip().strip('"\'')
                output_format['deliverable'] = val

    return output_format if output_format else None


def _format_context_history_for_prompt(context_history):
    """Format context_history for injection into Claude Code prompt.

    Returns: Formatted string describing previous agent work.
    """
    if not context_history:
        return ""

    lines = ["## Context History (Previous Agent Work)\n"]
    lines.append("This task has been worked on by other agents. Here's what they found:\n")

    for entry in context_history:
        agent = entry.get('agent', 'unknown')
        attempt = entry.get('attempt', 'No details provided')
        lines.append(f"\n### {agent.capitalize()}'s Work:")
        lines.append(f"- **What was tried:** {attempt}")
        if 'deliverable' in entry:
            lines.append(f"- **Deliverable:** `{entry['deliverable']}`")
        if 'findings' in entry:
            lines.append(f"- **Key findings:** {entry['findings']}")

    lines.append("\n---\n")
    return "\n".join(lines)


def _validate_session_model(agent_name: str, expected_model: str) -> tuple[bool, str, str]:
    """
    Validate that the agent's active session is using the expected model.

    Reads the most recent session file to detect model drift. If the session
    is using a different model than configured, rejects execution to prevent
    wasted tasks on a misconfigured agent.

    Returns:
        (is_valid, session_model, reason)
        - is_valid: True if session model matches expected, False otherwise
        - session_model: The model detected in the session (or 'unknown')
        - reason: Human-readable explanation of any mismatch
    """
    sessions_dir = Path(f"{AGENTS_DIR}/{agent_name}/sessions")
    if not sessions_dir.exists():
        # No session history = no drift detected
        return True, 'no-session', 'No session history to validate'

    # Find the most recent session file
    try:
        session_files = sorted(sessions_dir.glob('*.jsonl'), key=os.path.getmtime, reverse=True)
        if not session_files:
            return True, 'no-session', 'No session files found'

        latest_session = session_files[0]
        session_model = 'unknown'

        # Scan the last 50 lines of the session for model info
        with open(latest_session, 'r') as f:
            lines = f.readlines()[-50:]  # Last 50 lines most relevant
            for line in reversed(lines):  # Most recent first
                try:
                    entry = json.loads(line)
                    # Check for model_change event
                    if entry.get('type') == 'model_change':
                        provider = entry.get('provider', '')
                        model_id = entry.get('modelId', '')
                        if provider and model_id:
                            session_model = f"{provider}/{model_id}"
                            break
                    # Check for model-snapshot
                    if entry.get('customType') == 'model-snapshot':
                        data = entry.get('data', {})
                        provider = data.get('provider', '')
                        model_id = data.get('modelId', '')
                        if provider and model_id:
                            session_model = f"{provider}/{model_id}"
                            break
                    # Check direct model field (top-level)
                    if 'model' in entry and entry.get('model') != 'unknown':
                        session_model = entry.get('model', 'unknown')
                        break
                    # Check inside message object (common format for Claude Code sessions)
                    message = entry.get('message', {})
                    if isinstance(message, dict):
                        msg_model = message.get('model')
                        msg_provider = message.get('provider', '')
                        if msg_model and msg_model != 'unknown':
                            if msg_provider and msg_provider != 'anthropic':
                                session_model = f"{msg_provider}/{msg_model}"
                            else:
                                session_model = msg_model
                            break
                except (json.JSONDecodeError, KeyError):
                    continue

        # Normalize model names for comparison
        # expected_model is like "claude-opus-4-6"
        # session_model is like "anthropic/claude-opus-4-6" or "zai-coding/glm-5"
        norm_expected = expected_model.replace('anthropic/', '').lower()
        norm_session = session_model.replace('anthropic/', '').lower()

        # Check for mismatch
        if norm_expected not in norm_session and session_model != 'unknown':
            # Known non-Claude models that indicate drift
            known_drift_patterns = ['glm-5', 'kimi', 'qwen', 'bailian', 'dashscope', 'minimax', 'zai-coding']
            if any(pattern in norm_session for pattern in known_drift_patterns):
                # AUTO-CLEANUP: Archive stale session instead of rejecting
                # This allows fresh session to start with correct model
                try:
                    archive_path = str(latest_session) + f".drift-{int(time.time())}"
                    os.rename(str(latest_session), archive_path)
                    reason = f"Auto-archived stale session (was using '{session_model}', config expects '{expected_model}'). Fresh session will start."
                    print(f"  🧹 AUTO-CLEANUP: {reason}")
                    print(f"  📦 Archived to: {archive_path}")
                    # Log to ledger for observability
                    _append_ledger({
                        "event": "SESSION_AUTO_CLEANUP",
                        "ts": datetime.now().isoformat(),
                        "agent": agent_name,
                        "stale_model": session_model,
                        "expected_model": expected_model,
                        "archived_to": archive_path
                    })
                    return True, 'cleaned', reason
                except Exception as cleanup_err:
                    # If cleanup fails, still reject to prevent drift
                    reason = f"Session model drift (cleanup failed): session using '{session_model}' but config expects '{expected_model}'"
                    return False, session_model, reason

        # If session_model contains expected_model, we're good
        if norm_expected in norm_session or session_model == 'unknown':
            return True, session_model, 'Session model matches config'

    except Exception as e:
        # On error, allow execution but log the issue
        return True, 'error', f'Session validation failed: {e}'

    return True, session_model, 'Session model validated'


def _append_ledger(entry):
    """Append an event to the task ledger.

    kurultai_ledger.append_ledger is a no-op since Phase 5 cutover (2026-03-12).
    Delegate to _append_ledger_direct which dual-writes to JSONL + Neo4j.
    """
    _append_ledger_direct(entry)


def _append_ledger_direct(entry):
    """Write event to both JSONL and Neo4j for full telemetry visibility.

    Since Phase 5 cutover (2026-03-12), read_ledger() reads from Neo4j.
    Events written only to JSONL (SKILL_INVOCATION, SKILL_OUTCOME, etc.)
    are invisible to reflect cycles. This dual-writes to both stores.
    """
    import fcntl
    # 1. Write to JSONL (backward compat)
    ledger_path = Path.home() / '.openclaw' / 'tasks' / 'task-ledger.jsonl'
    try:
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with open(ledger_path, "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(json.dumps(entry) + "\n")
                f.flush()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except Exception as e:
        print(f"  WARNING: _append_ledger_direct JSONL write failed: {e}")

    # 2. Write to Neo4j as PipelineEvent (makes events visible to read_ledger)
    try:
        from neo4j_task_tracker import TaskTracker
        tracker = TaskTracker()
        tracker.emit_pipeline_event(
            event_type=entry.get("event", "UNKNOWN"),
            payload=entry,
            agent=entry.get("agent", ""),
        )
        tracker.close()
    except Exception as e:
        print(f"  WARNING: _append_ledger_direct Neo4j write failed (non-fatal): {e}")


def _extract_skills_from_transcript(agent_name: str, start_time: float, task_id: str, skill_hint) -> list:
    """
    Post-execution: find the Claude Code session transcript for this task,
    extract all Skill tool invocations, append SKILL_INVOCATION events to ledger.

    Transcript location: ~/.claude/projects/{encoded_cwd}/{session_id}.jsonl
    """
    agent_root = f"{AGENTS_DIR}/{agent_name}"
    # Claude Code encodes project paths by replacing / and . with -
    # The leading - from the absolute path's / must be preserved (not stripped)
    encoded = agent_root.replace('/', '-').replace('.', '-')
    project_dir = Path.home() / ".claude/projects" / encoded

    if not project_dir.exists():
        return []

    newest = None
    newest_mtime = 0.0
    for jf in project_dir.glob("*.jsonl"):
        try:
            mt = jf.stat().st_mtime
            if mt >= start_time and mt > newest_mtime:
                newest_mtime = mt
                newest = jf
        except OSError:
            continue

    if not newest:
        return []

    try:
        lines = newest.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []

    skills_found = []
    for line in lines:
        try:
            record = json.loads(line)
        except Exception:
            continue
        msg = record.get("message", {})
        content = msg.get("content", [])
        if isinstance(content, str):
            continue  # content is plain text, not a list of blocks
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("name") == "Skill":
                skill_name = block.get("input", {}).get("skill", "")
                if not skill_name:
                    continue
                skill_full = f"/{skill_name}" if not skill_name.startswith("/") else skill_name
                _append_ledger_direct({
                    "task_id": task_id,
                    "event": "SKILL_INVOCATION",
                    "ts": datetime.now().isoformat(),
                    "agent": agent_name,
                    "skill": skill_full,
                    "trigger": "skill_hint" if skill_hint and skill_name in skill_hint else "agent_choice",
                    "skill_hint_matched": bool(skill_hint and skill_name in skill_hint),
                    "session_id": str(newest.stem),
                    "skill_version": 1,
                    "executor": "claude-code",
                })
                skills_found.append(skill_name)

    return skills_found


def _check_skill_invocation_early(agent_name: str, start_time: float, skill_hint: str) -> bool:
    """
    Early R008 pre-flight check: detect if required skill was invoked within first N seconds.

    This enables fast-fail for agents ignoring skill_hint instead of waiting for full timeout.
    Called from monitoring loop after R008_PREFLIGHT_ELAPSED seconds.

    Returns True if skill_hint was found in session, False otherwise.
    """
    if not skill_hint:
        return True  # No skill hint required, pass check

    agent_root = f"{AGENTS_DIR}/{agent_name}"
    # Claude Code encodes project paths by replacing / and . with -
    # The leading - from the absolute path's / must be preserved (not stripped)
    encoded = agent_root.replace('/', '-').replace('.', '-')
    project_dir = Path.home() / ".claude/projects" / encoded

    if not project_dir.exists():
        return False

    # Find most recent session file since start_time
    newest = None
    newest_mtime = 0.0
    for jf in project_dir.glob("*.jsonl"):
        try:
            mt = jf.stat().st_mtime
            if mt >= start_time and mt > newest_mtime:
                newest_mtime = mt
                newest = jf
        except OSError:
            continue

    if not newest:
        return False

    try:
        lines = newest.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return False

    # Check for Skill tool invocation matching skill_hint
    hint_normalized = skill_hint.lstrip('/').lower()
    for line in lines:
        try:
            record = json.loads(line)
        except Exception:
            continue
        msg = record.get("message", {})
        content = msg.get("content", [])
        if isinstance(content, str):
            continue  # content is plain text, not a list of blocks
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("name") == "Skill":
                skill_name = block.get("input", {}).get("skill", "")
                if not skill_name:
                    continue
                # Normalize for matching (handle /prefix and variations)
                skill_normalized = skill_name.lstrip('/').lower()
                if hint_normalized in skill_normalized or skill_normalized in hint_normalized:
                    return True  # Skill was invoked

    # Emit R008_PREFLIGHT_CHECK event for tracking
    _append_ledger({
        "event": "R008_PREFLIGHT_CHECK",
        "ts": datetime.now().isoformat(),
        "agent": agent_name,
        "task_id": None,  # Will be added by caller if available
        "skill_hint": skill_hint,
        "skills_invoked": [],
        "preflight_elapsed": R008_PREFLIGHT_ELAPSED,
        "status": "FAIL"
    })
    return False  # Skill not found yet


# R008 LAYER 6: Compliance Tracking (INFORMATIONAL ONLY)
_R008_VIOLATION_TRACKER = {}  # agent_name -> {"count": int, "last_violation": str}

def _track_r008_violation(agent_name: str, task_id: str, skill_hint: str):
    """
    R008 LAYER 6: Track skill invocation for compliance monitoring.
    
    NOTE: This is INFORMATIONAL ONLY - tasks no longer fail for R008 violations.
    Skills are auto-invoked in the prompt, so tasks complete successfully.
    This tracking helps identify agents that may need additional prompting.
    
    Args:
        agent_name: Name of the agent
        task_id: Task ID
        skill_hint: The skill that was auto-invoked
    """
    global _R008_VIOLATION_TRACKER
    
    if agent_name not in _R008_VIOLATION_TRACKER:
        _R008_VIOLATION_TRACKER[agent_name] = {
            "count": 0,
            "last_violation": None,
            "escalated": False,
            "tasks": []
        }
    
    tracker = _R008_VIOLATION_TRACKER[agent_name]
    tracker["count"] += 1
    tracker["last_violation"] = datetime.now().isoformat()
    tracker["tasks"].append(task_id)
    
    count = tracker["count"]
    
    # Log compliance tracking (informational only)
    print(f"  ℹ️  R008 COMPLIANCE: {agent_name} skill auto-invoked #{count} (skill: {skill_hint})")
    
    # Log to ledger for monitoring
    try:
        _reload_ledger_module()
        _append_ledger({
            "event": "R008_SKILL_AUTO_INVOKED",
            "ts": datetime.now().isoformat(),
            "agent": agent_name,
            "task_id": task_id,
            "skill_hint": skill_hint,
            "auto_invoke_count": count,
        })
    except Exception as ledger_err:
        print(f"  [LEDGER] Failed to log R008 compliance tracking: {ledger_err}")


def _get_r008_violation_count(agent_name: str) -> int:
    """Get current R008 violation count for an agent."""
    if agent_name in _R008_VIOLATION_TRACKER:
        return _R008_VIOLATION_TRACKER[agent_name]["count"]
    return 0


def _requires_manual_approval(agent_name: str, skill_hint: str) -> bool:
    """
    Check if a task requires manual approval.
    
    NOTE: R008 no longer requires manual approval - skills are auto-invoked.
    This function always returns False for backward compatibility.
    """
    return False  # Skills are auto-invoked, no manual approval needed


def _track_skill_telemetry(task_id: str, agent_name: str, skill_hint: str, skills_invoked: list, r008_violation: bool):
    """
    Emit SKILL_OUTCOME event to task-ledger.jsonl after task execution.

    This closes the telemetry gap flagged by kurultai-reflect: without SKILL_OUTCOME
    events, reflect cycles cannot measure skill effectiveness or compliance rates.

    NOTE: Writes directly to JSONL file because kurultai_ledger.append_ledger is a
    no-op since Phase 5 cutover (2026-03-12). Same pattern as task_report_hook.py.
    """
    try:
        hint_normalized = skill_hint.lstrip('/')
        hint_matched = any(
            hint_normalized in skill.lstrip('/') or skill.lstrip('/') in hint_normalized
            for skill in skills_invoked
        )
        event = {
            "task_id": task_id,
            "event": "SKILL_OUTCOME",
            "ts": datetime.now().isoformat(),
            "agent": agent_name,
            "skill_hint": skill_hint,
            "skills_invoked": skills_invoked,
            "hint_matched": hint_matched,
            "r008_violation": r008_violation,
            "invocation_count": len(skills_invoked),
        }
        _append_ledger_direct(event)
    except Exception as e:
        print(f"  WARNING: SKILL_OUTCOME telemetry failed: {e}")


_TOOL_PATTERNS = {
    "file_ops": r'\b(Read|Write|Edit|Glob|NotebookEdit)\b',
    "bash":     r'\bBash\b',
    "search":   r'\b(Grep|WebSearch|WebFetch)\b',
    "browser":  r'\b(browser_|navigate|mcp__claude-in-chrome)\b',
    "agent_spawned": r'(spawn_subagent|Subagent spawned)',
}

_PHASE_KEYWORDS = {
    "read_context": ["reading", "checking context", "loading memory"],
    "plan":         ["planning", "let me plan", "approach:"],
    "implement":    ["implementing", "writing", "creating"],
    "verify":       ["verifying", "testing", "checking output", "confirmed"],
    "error_recovery": ["retry", "error occurred", "trying again", "fallback"],
    "summarize":    ["summary", "completed", "result:", "done:"],
}


def _analyze_tool_usage(stdout: str) -> dict:
    """Parse stdout for tool call patterns. Returns EXECUTION_TRACE payload."""
    import re
    tool_categories = {k: len(re.findall(p, stdout)) for k, p in _TOOL_PATTERNS.items()}
    phase_markers = []
    for phase, keywords in _PHASE_KEYWORDS.items():
        if any(kw in stdout.lower() for kw in keywords) and phase not in phase_markers:
            phase_markers.append(phase)
    error_lines = sum(1 for ln in stdout.splitlines()
                      if re.search(r'\b(error|failed|traceback)\b', ln, re.IGNORECASE))
    return {
        "tool_categories": tool_categories,
        "phase_markers": phase_markers,
        "intermediate_errors": error_lines,
        "output_tokens_est": len(stdout) // 4,
    }


def _analyze_code_changes(output_text: str, agent_name: str) -> dict:
    """Analyze code changes from task output.

    Parses Claude Code output for file operations and change metrics.

    Args:
        output_text: stdout content from task execution
        agent_name: Agent name for workspace lookup

    Returns:
        Dict with code change metrics
    """
    import re

    changes = {
        "lines_added": 0,
        "lines_removed": 0,
        "files_modified": [],
        "files_created": [],
        "files_deleted": [],
        "code_lines_added": 0,
        "doc_lines_added": 0,
        "test_lines_added": 0,
    }

    if not output_text:
        return None

    # Pattern for file creation
    created = re.findall(r'(?:Created|Wrote|Saved|Written)[:\s]+([~/][^\s\n]+)', output_text, re.IGNORECASE)
    changes["files_created"] = list(set(created))[:20]

    # Pattern for file modification
    modified = re.findall(r'(?:Modified|Updated|Edited)[:\s]+([~/][^\s\n]+)', output_text, re.IGNORECASE)
    changes["files_modified"] = list(set(modified))[:20]

    # Pattern for file deletion
    deleted = re.findall(r'(?:Deleted|Removed)[:\s]+([~/][^\s\n]+)', output_text, re.IGNORECASE)
    changes["files_deleted"] = list(set(deleted))[:10]

    # Count lines added/removed from diff-like output
    lines_added = len(re.findall(r'^\+[^+]', output_text, re.MULTILINE))
    lines_removed = len(re.findall(r'^-[^-]', output_text, re.MULTILINE))
    changes["lines_added"] = lines_added
    changes["lines_removed"] = lines_removed

    # Categorize by file type
    code_extensions = {'.py', '.js', '.ts', '.jsx', '.tsx', '.go', '.rs', '.java', '.cpp', '.c', '.h'}
    doc_extensions = {'.md', '.txt', '.rst', '.html'}
    test_patterns = {'test_', '_test.', '.test.', '.spec.'}

    for f in changes["files_created"]:
        lower_f = f.lower()
        ext = os.path.splitext(f)[1].lower()

        # Count lines (estimate from output)
        file_lines = 50  # Default estimate

        if ext in code_extensions:
            changes["code_lines_added"] += file_lines
            changes["lines_added"] += file_lines
        elif ext in doc_extensions:
            changes["doc_lines_added"] += file_lines
            changes["lines_added"] += file_lines

        # Check if test file
        if any(p in lower_f for p in test_patterns):
            changes["test_lines_added"] += file_lines

    # Only return if we found meaningful changes
    if not (changes["files_created"] or changes["files_modified"] or changes["lines_added"] > 100):
        return None

    return changes


def count_queue_depth(agent: str) -> int:
    """Count pending tasks in agent queue."""
    agents_dir = str(AGENTS_DIR)
    queue_dir = f"{agents_dir}/{agent}/tasks"
    if not os.path.isdir(queue_dir):
        return 0

    count = 0
    for pattern in ['*.md', '*.executing.md']:
        for f in glob.glob(f"{queue_dir}/{pattern}"):
            if not f.endswith('.done.md'):
                count += 1
    return count


def _check_architecture_update(agent_name: str, task_content: str, result_content: str, task_id: str):
    """
    Check if the completed task warrants an architecture.md update.
    Appends ARCH_UPDATE_CHECK event to ledger. Writes to architecture.md if needed.

    Triggers on: new scripts created, new patterns introduced, system design changes,
    infrastructure changes, or agent behavior changes.
    """
    import re
    arch_file = Path.home() / ".openclaw/agents/main/docs/architecture.md"
    if not arch_file.exists():
        return

    # Keywords that signal architectural significance
    arch_signals = [
        "new script", "created script", "new file", "created file",
        "new pattern", "new approach", "refactored", "restructured",
        "new agent", "new skill", "new hook", "new pipeline",
        "architecture", "system design", "infrastructure",
        "launchd", "plist", "cron", "daemon", "service",
        "database", "schema", "redis", "neo4j",
    ]

    combined = (task_content + " " + result_content).lower()
    if not any(signal in combined for signal in arch_signals):
        return

    # Check what changed: look for file paths created/modified in result
    created_files = re.findall(r'(?:created|wrote|saved|written to)[:\s]+([~/][^\s\n]+)', result_content, re.IGNORECASE)
    new_scripts = [f for f in created_files if f.endswith(('.py', '.sh', '.js', '.ts'))]

    if not created_files and not any(s in combined for s in ["architecture", "system design", "restructured"]):
        return

    _append_ledger({
        "task_id": task_id,
        "event": "ARCH_UPDATE_CHECK",
        "ts": datetime.now().isoformat(),
        "agent": agent_name,
        "triggered": True,
        "files_detected": created_files[:10],
        "new_scripts": new_scripts[:5],
        "note": "Review architecture.md for updates needed",
    })


def auth_health_preflight(agent: str, timeout: int = 30) -> bool:
    """Check if claude-agent can authenticate for the given agent.

    Prevents spawn crashes from invalid/expired auth tokens.
    Pattern from task-watcher.py and auth-health-preflight.md.

    FIX (2026-03-11): Increased default from 20s to 30s because claude-agent
    takes ~24 seconds to complete authentication and response.

    FIX (2026-03-12): Use cached auth-heartbeat.json to reduce concurrent checks.
    Multiple agents doing simultaneous auth checks cause resource contention
    and timeouts. Use 5-minute stale threshold to match auth_heartbeat.py.

    Args:
        agent: Agent name (temujin, mongke, etc.)
        timeout: Seconds to wait for auth check (default 30)

    Returns:
        True if auth succeeds, False otherwise
    """
    # First check cached auth status (5-minute stale threshold)
    heartbeat_file = Path(AGENTS_DIR) / "main" / "logs" / "auth-heartbeat.json"
    AUTH_STALE_SECONDS = 300  # 5 minutes - matches auth_heartbeat.py

    if heartbeat_file.exists():
        try:
            with open(heartbeat_file) as f:
                heartbeat = json.load(f)
            if agent in heartbeat:
                entry = heartbeat[agent]
                if entry.get("status") == "ok":
                    last_success = entry.get("last_success")
                    if last_success:
                        from datetime import datetime
                        last_success_time = datetime.fromisoformat(last_success)
                        age_seconds = (datetime.now() - last_success_time).total_seconds()
                        if age_seconds < AUTH_STALE_SECONDS:
                            # Cached result is fresh - skip auth check
                            return True
                        elif age_seconds < 900:  # 15 minutes — allow with warning
                            print(f"  AUTH PREFLIGHT: {agent} using recent auth ({age_seconds:.0f}s ago, soft-pass)")
                            return True
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            # Cache read failed - fall through to fresh check
            pass

    # Cache miss or stale - run fresh auth check
    agent_dir = Path(AGENTS_DIR) / agent
    if not agent_dir.is_dir():
        print(f"  AUTH PREFLIGHT: {agent} directory not found: {agent_dir}")
        return False

    # Lightweight check: claude auth status (10s timeout, no LLM invocation)
    try:
        status_result = subprocess.run(
            ["claude", "auth", "status"],
            capture_output=True, text=True, timeout=10
        )
        if status_result.returncode == 0 and "authenticated" in (status_result.stdout or "").lower():
            return True
    except (subprocess.TimeoutExpired, Exception):
        pass  # Fall through to full check

    test_prompt = "Respond with exactly: OK"

    # FIX (2026-03-11 21:35): Added 3 attempts with exponential backoff to match
    # task-watcher.py implementation. Previous single-attempt version was failing
    # on transient network issues, causing unnecessary auth failures.
    for attempt in range(3):
        try:
            result = subprocess.run(
                [CLAUDE_AGENT, test_prompt],
                cwd=str(agent_dir),
                capture_output=True,
                timeout=timeout,
                env={**os.environ, 'CLAUDECODE': '', 'CLAUDE_PROVIDER': 'zai'}
            )
            if result.returncode == 0:
                return True  # Auth success
        except subprocess.TimeoutExpired:
            # Retry with backoff
            pass
        except Exception as e:
            print(f"  AUTH PREFLIGHT: {agent} attempt {attempt + 1}: {e}")

        # Exponential backoff before retry (2s, 4s)
        if attempt < 2:
            backoff = 2 ** attempt
            time.sleep(backoff)

    print(f"  AUTH PREFLIGHT: {agent} failed after 3 attempts")
    return False


def spawn_subagent(agent_name, task, subagent_task, depth=0):
    """Spawn a subagent for parallel work. Rejects if depth >= MAX_TASK_DEPTH."""
    if depth >= MAX_TASK_DEPTH:
        print(f"REJECT: depth={depth} >= {MAX_TASK_DEPTH} — preventing runaway chain")
        return None

    # AUTH PREFLIGHT: Check credentials before spawning (R008_FIX 2026-03-11)
    # Prevents silent spawn failures when agent tokens are invalid/expired
    if not auth_health_preflight(agent_name, timeout=30):
        print(f"SPAWN SKIP: {agent_name} auth preflight failed — not spawning subagent")
        # Log auth failure for monitoring
        auth_failure_log = Path(AGENTS_DIR) / "main" / "logs" / "auth-failures.jsonl"
        try:
            auth_failure_log.parent.mkdir(parents=True, exist_ok=True)
            with open(auth_failure_log, "a") as af:
                af.write(f'{{"timestamp": "{datetime.now().isoformat()}", "agent": "{agent_name}", "label": "spawn_subagent", "script": "agent-task-handler.py", "reason": "preflight_failed"}}\n')
        except Exception:
            pass
        return None

    config = load_agent_config(agent_name)

    spawn_request = {
        "agent": agent_name,
        "model": config.get('model', 'claude-opus-4-6'),
        "task": subagent_task,
        "priority": "normal",
        "label": f"{agent_name}-sub-{int(time.time())}",
        "source": "agent_delegation",
        "parent_task": task,
        "depth": depth + 1,
    }
    
    # Add to spawn queue with file locking
    os.makedirs(os.path.dirname(SPAWN_QUEUE), exist_ok=True)
    with locked_json_update(SPAWN_QUEUE, default={'spawns': [], 'updated': 0}) as data:
        if 'spawns' not in data:
            data['spawns'] = []
        data['spawns'].append(spawn_request)
        data['updated'] = time.time()

    print(f"✓ Subagent spawned: {spawn_request['label']}")
    return spawn_request['label']

def _load_agent_memory(agent_name):
    """Load recent memory context for the agent."""
    memory_dir = f"{AGENTS_DIR}/{agent_name}/memory"
    context = ""

    # Load context.md if it exists
    context_file = f"{memory_dir}/context.md"
    if os.path.exists(context_file):
        try:
            with open(context_file, 'r') as f:
                context += f.read()[:2000] + "\n\n"
        except Exception:
            pass

    # Load today's memory file
    today = datetime.now().strftime("%Y-%m-%d")
    today_file = f"{memory_dir}/{today}.md"
    if os.path.exists(today_file):
        try:
            with open(today_file, 'r') as f:
                lines = f.readlines()
                context += "".join(lines[-50:])  # Last 50 lines
        except Exception:
            pass

    return context.strip()


def _gather_context_files(agent_name, task_text):
    """Pre-load relevant files for context injection (replaces tool-based file reading).

    Scans task text for file paths and loads them. Also loads recent workspace results.
    """
    import re
    context = ""
    max_context = 50000  # chars budget for file context

    # Extract file paths mentioned in task
    paths = re.findall(r'(/[^\s\n]+\.[a-zA-Z]+)', task_text)
    for path in paths[:5]:
        if os.path.exists(path) and os.path.isfile(path):
            try:
                with open(path, 'r') as f:
                    content = f.read()[:10000]
                context += f"\n### {path}\n```\n{content}\n```\n"
                if len(context) > max_context:
                    break
            except Exception:
                pass

    # Load recent workspace results for context
    workspace = f"{AGENTS_DIR}/{agent_name}/workspace"
    if os.path.isdir(workspace):
        recent_files = sorted(
            [f for f in os.listdir(workspace) if f.endswith('.md')],
            reverse=True
        )[:3]
        for fname in recent_files:
            fpath = os.path.join(workspace, fname)
            try:
                with open(fpath, 'r') as f:
                    content = f.read()[:5000]
                context += f"\n### workspace/{fname}\n```\n{content}\n```\n"
                if len(context) > max_context:
                    break
            except Exception:
                pass

    return context


def execute_task_with_ollama(agent_name, task_text, config, timeout=None):
    """Execute task via direct Ollama API call (no tools).

    Used for agents that run local models without tool-calling support.
    Context is pre-loaded into the prompt instead of using tools.
    """
    agent_root = f"{AGENTS_DIR}/{agent_name}"
    executor_config = config.get('executor_config', {})
    base_url = executor_config.get('base_url', 'http://localhost:11434')
    model_name = executor_config.get('model_name', 'hf.co/lukey03/Qwen3.5-9B-abliterated-GGUF')
    max_tokens = executor_config.get('max_tokens', 16384)
    temperature = executor_config.get('temperature', 0.7)

    # Load agent identity from CLAUDE.md
    claude_md = f"{agent_root}/CLAUDE.md"
    system_prompt = ""
    if os.path.exists(claude_md):
        with open(claude_md, 'r') as f:
            system_prompt = f.read()[:4000]

    # Load agent memory
    memory = _load_agent_memory(agent_name)
    memory_section = f"\n\n## Recent Context\n{memory}" if memory else ""

    # Pre-load relevant workspace files for context
    context_files = _gather_context_files(agent_name, task_text)
    context_section = "\n\n## Pre-loaded Files\n" + context_files if context_files else ""

    user_prompt = f"{task_text}{memory_section}{context_section}"

    # Call Ollama chat API directly
    payload = json.dumps({
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "stream": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": temperature,
        }
    }).encode('utf-8')

    effective_timeout = timeout or CLAUDE_TIMEOUT
    start_time = time.time()
    try:
        req = urllib.request.Request(
            f"{base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=effective_timeout) as resp:
            result = json.loads(resp.read().decode('utf-8'))

        content = result.get('message', {}).get('content', '')
        elapsed_ms = int((time.time() - start_time) * 1000)
        return {
            "success": bool(content.strip()),
            "content": content,
            "error": None if content.strip() else "Empty response from Ollama",
            "model": f"ollama/{model_name}",
            "latency_ms": elapsed_ms,
        }
    except urllib.error.URLError as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        return {
            "success": False,
            "error": f"Ollama connection failed: {e}",
            "model": f"ollama/{model_name}",
            "latency_ms": elapsed_ms,
        }
    except subprocess.TimeoutExpired:
        elapsed_ms = int((time.time() - start_time) * 1000)
        return {
            "success": False,
            "error": f"Ollama request timed out after {effective_timeout}s",
            "model": f"ollama/{model_name}",
            "latency_ms": elapsed_ms,
        }
    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        return {
            "success": False,
            "error": str(e),
            "model": f"ollama/{model_name}",
            "latency_ms": elapsed_ms,
        }


def _call_claude_code(agent_name, prompt, config, skill_hint=None, timeout=None, model=None, priority='normal'):
    """Execute a single Claude Code call with stall detection.

    Internal helper that performs the actual subprocess execution.
    Returns result dict with success, content, error, model fields.
    """
    # Use agent ROOT directory as workdir so CLAUDE.md is auto-discovered
    agent_root = f"{AGENTS_DIR}/{agent_name}"

    env = os.environ.copy()
    env.pop('CLAUDECODE', None)  # Allow nested Claude Code sessions
    env['PATH'] = (
        "/Users/kublai/.local/bin:/opt/homebrew/bin:"
        "/usr/local/bin:/usr/bin:/bin:" + env.get('PATH', '')
    )

    # Sanitize ALL inherited ANTHROPIC_* env vars to prevent stale/poisoned
    # values from the parent process (e.g. task-watcher launched with DashScope
    # credentials). We strip everything, then re-apply only validated values
    # from the agent's settings.json.
    _stripped_anthropic = []
    for key in list(env.keys()):
        if key.startswith('ANTHROPIC_'):
            _stripped_anthropic.append(key)
            del env[key]
    if _stripped_anthropic:
        print(f"  ENV_SANITIZE: stripped inherited {', '.join(_stripped_anthropic)} for {agent_name}")

    # Load credentials from centralized vault as base layer
    # This provides DEFAULT_MODEL and fallback provider credentials
    vault_creds = load_vault_credentials()
    for key, value in vault_creds.items():
        if key not in env or not env.get(key):  # Don't override if already set
            env[key] = value
    if vault_creds:
        print(f"  VAULT_LOADED: {len(vault_creds)} credentials from provider.env")

    # Load agent-specific environment from .claude/settings.json
    # This provides ANTHROPIC_MODEL (and optionally ANTHROPIC_BASE_URL, ANTHROPIC_AUTH_TOKEN)
    VALID_CLAUDE_MODELS = {'claude-opus-4-6', 'claude-sonnet-4-6', 'claude-haiku-4-5'}
    # NOTE: Uses module-level PROXY_ENDPOINTS for single source of truth (2026-03-09)
    try:
        settings_path = f"{agent_root}/.claude/settings.json"
        with open(settings_path, 'r') as _sf:
            settings = json.load(_sf)
        agent_env = settings.get('env', {})
        for key, value in agent_env.items():
            env[key] = value
        # Validate ANTHROPIC_MODEL env var — reject non-Claude models ONLY if using official Anthropic API
        # Allow proxy models (kimi-k2.5, etc.) when using approved proxy endpoints
        env_model = env.get('ANTHROPIC_MODEL')
        base_url = env.get('ANTHROPIC_BASE_URL', '')
        is_using_proxy = any(endpoint in base_url for endpoint in PROXY_ENDPOINTS)
        debug_msg = f"DEBUG: agent={agent_name}, env_model={env_model}, base_url={base_url[:50] if base_url else 'NONE'}..., is_using_proxy={is_using_proxy}\n"
        DEBUG_LOG_PATH = Path.home() / '.openclaw' / 'logs' / 'debug' / 'agent_handler.log'
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not DEBUG_LOG_PATH.exists():
            DEBUG_LOG_PATH.touch(mode=0o600)
        with open(DEBUG_LOG_PATH, 'a') as f:
            f.write(debug_msg)
        print(f"  {debug_msg.strip()}")
        # Validate ANTHROPIC_MODEL — only accept Claude models when using official Anthropic API
        # Proxy endpoints can use other models, but official API must use Claude models
        if env_model and env_model not in VALID_CLAUDE_MODELS and not is_using_proxy:
            print(f"  ⚠ Model '{env_model}' not in VALID_CLAUDE_MODELS — using claude-opus-4-6")
            env['ANTHROPIC_MODEL'] = 'claude-opus-4-6'
        else:
            print(f"  ✓ ACCEPTED model '{env_model}' for {agent_name} (proxy={is_using_proxy})")
    except (FileNotFoundError, json.JSONDecodeError):
        pass  # Use system environment if no agent settings

    # Validate ANTHROPIC_BASE_URL — allow Anthropic and approved proxy endpoints
    # Uses module-level PROXY_ENDPOINTS for single source of truth (2026-03-09)
    base_url = env.get('ANTHROPIC_BASE_URL', '')
    is_allowed_proxy = any(endpoint in base_url for endpoint in PROXY_ENDPOINTS)
    if base_url and 'anthropic.com' not in base_url and not is_allowed_proxy:
        print(f"  !! BLOCKED non-Anthropic BASE_URL for {agent_name}: {base_url}")
        print(f"  !! Removing ANTHROPIC_BASE_URL — will use official Anthropic API")
        env.pop('ANTHROPIC_BASE_URL', None)

    # Validate ANTHROPIC_AUTH_TOKEN — allow Anthropic and approved proxy tokens
    auth_token = env.get('ANTHROPIC_AUTH_TOKEN', '')
    # Anthropic tokens start with sk-ant-, but proxy services may use different prefixes
    is_anthropic_token = auth_token.startswith('sk-ant-')
    # DashScope tokens (sk-sp-*) NEVER work with Anthropic API - reject explicitly
    is_dashscope_token = auth_token.startswith('sk-sp-')
    # Z.AI proxy tokens use format like: d6ff69bb5ad74bb29b297d1681cc648c.KtP5x1d8kkFXgM21
    # (32-char hex prefix, dot, then suffix - but NOT starting with sk-)
    is_zai_token = (
        '.' in auth_token and
        len(auth_token.split('.')[0]) == 32 and
        not auth_token.startswith('sk-') and
        all(c in '0123456789abcdefABCDEF' for c in auth_token.split('.')[0])
    )

    # Track credential validation failures for immediate return
    credential_error = None

    if is_dashscope_token and not (base_url and is_allowed_proxy):
        # DashScope tokens (sk-sp-*) are allowed when using approved proxy endpoints
        # This enables Alibaba fallback tier in claude-agent wrapper (2026-03-09)
        print(f"  !! BLOCKED DashScope auth token for {agent_name} (prefix: {auth_token[:6]}...)")
        print(f"  !! DashScope tokens (sk-sp-*) require an approved proxy endpoint")
        print(f"  !! Get Anthropic API key from https://console.anthropic.com/")
        env.pop('ANTHROPIC_AUTH_TOKEN', None)
        credential_error = "DashScope token (sk-sp-*) is incompatible with Anthropic API. Get valid Anthropic API key from https://console.anthropic.com/"
    elif is_zai_token and not base_url:
        # Z.AI token without Z.AI base URL - will fail at Anthropic API
        print(f"  !! BLOCKED Z.AI proxy token for {agent_name} (format: {auth_token[:10]}...) - no BASE_URL set")
        print(f"  !! Z.AI tokens require ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic")
        print(f"  !! Removing token - will use system default or fail explicitly")
        env.pop('ANTHROPIC_AUTH_TOKEN', None)
        credential_error = "Z.AI proxy token without BASE_URL set. Either add ANTHROPIC_BASE_URL or use valid Anthropic API key (sk-ant-*)"
    elif auth_token and not is_anthropic_token and not is_zai_token and not (base_url and is_allowed_proxy and auth_token.startswith('sk-')):
        print(f"  !! BLOCKED non-Anthropic AUTH_TOKEN for {agent_name} (prefix: {auth_token[:6]}...)")
        env.pop('ANTHROPIC_AUTH_TOKEN', None)
        credential_error = f"Invalid credential format (prefix: {auth_token[:6]}...). Use valid Anthropic API key (sk-ant-*)"

    # CREDENTIAL_ERROR_LOG: Log credential issues but allow fallback chain execution.
    # The claude-agent wrapper has a multi-tier fallback system (Anthropic -> Z.AI -> Alibaba).
    # By sanitizing invalid credentials and continuing, we allow claude-agent to use its
    # own fallback chain instead of blocking execution here.
    # 2026-03-09: Removed short-circuit to enable fallback chain execution
    if credential_error:
        # Check if there's a valid token remaining after sanitization
        # Allow sk-sp-* tokens (Alibaba/DashScope) when using approved proxy endpoints
        remaining_token = env.get('ANTHROPIC_AUTH_TOKEN', '')
        is_valid_proxy_token = remaining_token.startswith('sk-sp-') and base_url and is_allowed_proxy
        has_valid_token = remaining_token and (remaining_token.startswith('sk-ant-') or is_valid_proxy_token)
        
        if not has_valid_token:
            print(f"  ⚠ CREDENTIAL_WARNING: No valid Anthropic API key after sanitization")
            print(f"  ⚠ Allowing claude-agent to use fallback chain: {credential_error}")
            _append_ledger({
                "event": "CREDENTIAL_WARNING_FALLBACK",
                "ts": datetime.now().isoformat(),
                "agent": agent_name,
                "warning": credential_error,
                "note": "Proceeding with claude-agent fallback chain",
            })
            # Continue to execution - claude-agent will handle fallback tiers

    effective_timeout = timeout or CLAUDE_TIMEOUT

    # R008 LAYER 3 removed (2026-03-11)
    # Skills are now auto-invoked immediately in execute_task_with_llm()
    # No need for session pre-flight injection here

    try:
        effort = config.get('effort', 'medium')
        if effort not in {'low', 'medium', 'high'}:
            effort = 'medium'

        # Build claude-agent command with optional model override
        cmd = [CLAUDE_AGENT, "--workdir", agent_root, "--effort", effort]
        if model:
            cmd.extend(["--model", model])
        cmd.extend(["--", prompt])

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )

        # R008 LAYER 4 removed (2026-03-11)
        # Skills are now auto-invoked immediately in execute_task_with_llm()
        # No need to monitor for skill invocation

        stdout_chunks = []
        last_output_time = time.time()
        start = time.time()
        r008_checked = False  # R008 fires at most once per task execution

        # Read stdout in a background thread so we can monitor for stalls
        import queue as _queue
        stdout_q = _queue.Queue()

        def _reader(pipe, q):
            for line in pipe:
                q.put(line)
            q.put(None)  # sentinel

        reader_thread = threading.Thread(target=_reader, args=(proc.stdout, stdout_q), daemon=True)
        reader_thread.start()

        while True:
            elapsed = time.time() - start

            # Hard timeout
            if elapsed >= effective_timeout:
                proc.kill()
                proc.wait()
                return {
                    "success": False,
                    "error": f"Claude Code timed out after {effective_timeout}s",
                    "content": "".join(stdout_chunks),
                    "model": model or "claude-code",
                    "latency_ms": 0,
                }

            # Drain available stdout
            got_output = False
            while True:
                try:
                    line = stdout_q.get_nowait()
                except _queue.Empty:
                    break
                if line is None:
                    # Process stdout closed — process is finishing
                    got_output = True
                    break
                stdout_chunks.append(line)
                got_output = True

            if got_output:
                last_output_time = time.time()

            # R008 LAYER 4: Preflight check for skill_hint invocation (2026-03-12 RE-ENABLED)
            # Previous "auto-invoke" was just text instructions — agents ignored it.
            # Now actively check if Skill tool was called early in execution.
            # FIX 2026-03-13: Per-skill timeouts + once-only guard (prevents repeated kills)
            r008_timeout = R008_PREFLIGHT_BY_SKILL.get(skill_hint, R008_PREFLIGHT_ELAPSED) if skill_hint else R008_PREFLIGHT_ELAPSED
            if skill_hint and elapsed >= r008_timeout and not r008_checked:
                r008_checked = True
                if not _check_skill_invocation_early(agent_name, start, skill_hint):
                    # Agent failed to invoke required skill within r008_timeout seconds
                    print(f"  ❌ R008_VIOLATION: Required skill '{skill_hint}' NOT invoked within {r008_timeout}s")
                    print(f"     Terminating task per R008 mandatory skill invocation rule")
                    # Determine if this is a slow skill for logging purposes
                    _is_slow_for_log = skill_hint in SLOW_SKILLS if skill_hint else False
                    _append_ledger({
                        "event": "R008_VIOLATION_TIMEOUT",
                        "ts": datetime.now().isoformat(),
                        "agent": agent_name,
                        "skill_hint": skill_hint,
                        "elapsed_s": int(elapsed),
                        "preflight_timeout": r008_timeout,
                        "is_slow_skill": _is_slow_for_log,
                    })
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                    return {
                        "success": False,
                        "error": f"R008_VIOLATION: Required skill '{skill_hint}' was not invoked within {r008_timeout}s",
                        "content": "".join(stdout_chunks),
                        "model": model or "claude-code",
                    }

            # Stall detection (T14): check after STALL_MIN_ELAPSED
            # Use relaxed thresholds for slow skills, high priority tasks, or proxy usage
            is_slow = (skill_hint in SLOW_SKILLS if skill_hint else False) or agent_name == "kublai" or priority == 'high'
            # Proxy endpoints (z.ai, openrouter, etc.) need longer timeouts for complex reasoning
            # Use is_allowed_proxy which was set earlier in this function
            is_proxy = is_allowed_proxy if 'is_allowed_proxy' in dir() else False

            if is_proxy:
                # Proxy gets most generous thresholds - complex reasoning can take time
                stall_elapsed_thresh = PROXY_STALL_ELAPSED
                stall_silence_thresh = PROXY_STALL_SILENCE
            elif is_slow:
                stall_elapsed_thresh = SLOW_SKILL_STALL_ELAPSED
                stall_silence_thresh = SLOW_SKILL_STALL_SILENCE
            elif priority == 'high':
                stall_elapsed_thresh = HIGH_PRIORITY_STALL_ELAPSED
                stall_silence_thresh = HIGH_PRIORITY_STALL_SILENCE
            else:
                stall_elapsed_thresh = STALL_MIN_ELAPSED
                stall_silence_thresh = STALL_SILENCE_THRESHOLD
            silence = time.time() - last_output_time
            if elapsed >= stall_elapsed_thresh and silence >= stall_silence_thresh:
                # Before killing, check if the claude session JSONL is still being written
                # (active tool calls produce no stdout but do write to the session file)
                session_active = False
                try:
                    project_slug = agent_root.replace('/', '-')
                    project_dir = os.path.expanduser(f"~/.claude/projects/{project_slug}")
                    if os.path.isdir(project_dir):
                        now = time.time()
                        for fname in os.listdir(project_dir):
                            if fname.endswith('.jsonl'):
                                fpath = os.path.join(project_dir, fname)
                                if now - os.path.getmtime(fpath) < 60:  # written in last 60s (increased from 30s)
                                    session_active = True
                                    break
                except Exception:
                    pass
                if session_active:
                    # Session is actively making tool calls — reset silence timer and continue
                    last_output_time = time.time() - (stall_silence_thresh - 60)  # allow 60s more
                    print(f"  SESSION_ACTIVE: JSONL modified recently, resetting stall timer (skill_hint={skill_hint}, elapsed={elapsed:.0f}s)")
                    time.sleep(0.5)
                    continue
                print(f"  STALL_DETECTED: no stdout for {silence:.0f}s after {elapsed:.0f}s elapsed — attempting graceful shutdown (skill_hint={skill_hint}, is_slow={is_slow}, thresh={stall_elapsed_thresh}/{stall_silence_thresh})")
                # FIX 2026-03-12: Use SIGTERM first for graceful shutdown, SIGKILL only if needed
                # This prevents exit code -9 and allows process cleanup
                _append_ledger({
                    "event": "STALL_SIGTERM",
                    "ts": datetime.now().isoformat(),
                    "skill_hint": skill_hint,
                    "elapsed_s": int(elapsed),
                    "silence_s": int(silence),
                })
                proc.terminate()  # SIGTERM (15) - allows graceful shutdown
                try:
                    proc.wait(timeout=10)  # Wait up to 10s for graceful exit
                except subprocess.TimeoutExpired:
                    # Process didn't respond to SIGTERM, force kill
                    print(f"  STALL_FORCEKILL: SIGTERM timed out, using SIGKILL")
                    proc.kill()
                    proc.wait()
                _append_ledger({
                    "event": "STALL_DETECTED",
                    "ts": datetime.now().isoformat(),
                    "agent": agent_name,
                    "elapsed_s": round(elapsed, 1),
                    "silence_s": round(silence, 1),
                    "timeout_s": effective_timeout,
                })
                return {
                    "success": False,
                    "error": f"STALL_TIMEOUT: no stdout for {silence:.0f}s after {elapsed:.0f}s (killed at {elapsed:.0f}s instead of waiting for {effective_timeout}s timeout)",
                    "content": "".join(stdout_chunks),
                    "model": model or "claude-code",
                    "latency_ms": 0,
                }

            # R008_PREFLIGHT_CHECK re-enabled (2026-03-12)
            # Active enforcement in monitoring loop above (line ~2775)

            # Check if process has exited
            retcode = proc.poll()
            if retcode is not None:
                break

            time.sleep(0.5)

        # Process has exited — collect remaining output
        reader_thread.join(timeout=5)
        while True:
            try:
                line = stdout_q.get_nowait()
            except _queue.Empty:
                break
            if line is not None:
                stdout_chunks.append(line)

        stderr_output = proc.stderr.read() if proc.stderr else ""
        proc.stderr.close() if proc.stderr else None

        output = "".join(stdout_chunks)
        error = stderr_output[-2000:] if stderr_output else ""

        success = proc.returncode == 0
        if success and not output.strip():
            success = False
            error = "Claude Code returned success but produced no output"

        if not success and not error.strip() and output.strip():
            error = f"exit_code={proc.returncode} stdout_tail: {output[-1000:]}"

        # R008 LAYER 5 removed (2026-03-11)
        # Skills are now auto-invoked immediately in execute_task_with_llm()
        # No fallback needed - invocation is guaranteed

        return {
            "success": success,
            "content": output,
            "error": error if not success else None,
            "model": model or "claude-code",
            "latency_ms": 0,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "model": model or "claude-code",
            "latency_ms": 0,
        }


def execute_task_with_llm(agent_name, task_text, config, skill_hint=None, timeout=None, model=None, priority='normal', task_id=None, context_history=None, audience=None):
    """Execute task via Claude Code using the claude-agent wrapper.

    Each agent runs as a sovereign Claude Code session with its own
    CLAUDE.md (auto-discovered from workdir), identity, and tools.

    Includes stall detection (T14): if no stdout is produced for
    STALL_SILENCE_THRESHOLD seconds after STALL_MIN_ELAPSED seconds
    have elapsed, the process is killed early instead of waiting for
    the full timeout.

    Includes rate limit fallback: if the primary model returns a rate limit
    error (429), automatically retries with FALLBACK_MODEL.

    Args:
        model: Optional model to use. If None, uses agent's default from settings.
        context_history: Optional list of dicts with previous agent work for cross-agent clarity.
        audience: Optional audience hint ('agent', 'human', 'both') for output formatting.
    """
    # Build prompt with agent context
    agent_root = f"{AGENTS_DIR}/{agent_name}"
    memory = _load_agent_memory(agent_name)
    memory_section = f"\n\n## Recent Context\n{memory}" if memory else ""
    skill_section = f"\n\nIMPORTANT: Start this task by invoking {skill_hint} — it is the correct skill for this work." if skill_hint else ""

    # Inject context history for cross-agent clarity
    context_history_section = ""
    if context_history:
        context_history_section = _format_context_history_for_prompt(context_history)

    # Inject audience instruction if specified
    audience_section = ""
    if audience:
        if audience == 'human':
            audience_section = "\n\n**Output Format:** This task's output is intended for human review. Prioritize clarity, include summaries, and use markdown formatting."
        elif audience == 'both':
            audience_section = "\n\n**Output Format:** This task's output is for both agent and human consumption. Include a clear summary section and detailed technical content."

    # Inject active behavioral rules from rules.json
    rules_section = ""
    active_rules = []  # Initialize for later use in rules_first_section
    try:
        from rule_registry import get_active_rules
        active_rules = get_active_rules(agent_name)
        if active_rules:
            rules_lines = "\n".join(f"  {i}. {r}" for i, r in enumerate(active_rules, 1))
            rules_section = f"\n\n## Active Behavioral Rules\nYou MUST follow these rules. Output 'RULES LOADED' at the start of your response.\n{rules_lines}"
    except Exception as e:
        print(f"  ⚠ Rule loading failed for {agent_name}: {e}")
        pass  # Don't block task execution if rule loading fails

    # Build prompt with rules FIRST (C16: rules must be at line 1 for agent compliance)
    # When rules exist, prepend mandatory first action to ensure they're loaded
    # R008 FIX: Also include skill_hint as MANDATORY if present
    rules_first_section = ""
    skill_hint_first_section = ""
    if active_rules:
        rules_first_section = "\n\n## MANDATORY FIRST ACTION\nBefore any other work, read ~/.openclaw/agents/{}/memory/rules.json and output 'RULES LOADED: [rule IDs]' at the start of your response.\n\n".format(agent_name)

    # R008 MANDATORY SKILL INSTRUCTION (2026-03-12 FIX)
    # Previous "auto-invoke" was fake — just added text that looked like a function call.
    # Now explicitly instruct agent to call Skill tool FIRST, before any other work.
    # This is mandatory — agent must invoke Skill tool before proceeding.
    if skill_hint:
        skill_name = skill_hint.lstrip('/')
        skill_hint_first_section = f"""

## ⚠️ MANDATORY: Skill Tool Required (R008)

**CRITICAL:** Before ANY other work, you MUST invoke the Skill tool:

```
Skill: {skill_hint}
```

Complete ALL skill phases before marking this task done. The skill will guide your approach.

Evidence of skill invocation is logged. Skipping the skill will result in R008_VIOLATION.

---

"""

    # Try to use prompt optimizer for enhanced prompts
    prompt = None
    optimization_metadata = None
    if PROMPT_OPTIMIZER_AVAILABLE:
        try:
            opt_config = load_optimizer_config()
            if opt_config.get("enabled", True):
                prompt, optimization_metadata = enhance_task_prompt(
                    task=task_text,
                    agent_name=agent_name,
                    memory=memory if memory else None,
                    skill_hint=skill_hint,
                    context_history=context_history_section if context_history_section else None,
                    audience=audience,
                    rules=rules_section if rules_section else None,
                )
                # Prepend rules first section if present (must be at line 1)
                # R008 FIX: Also prepend skill_hint as mandatory first action
                # C16 FIX: Include actual rules in mandatory_prefix, not just instruction to read them
                mandatory_prefix = rules_first_section + rules_section + skill_hint_first_section
                if mandatory_prefix:
                    prompt = mandatory_prefix + prompt
                # Log optimization result
                if optimization_metadata:
                    print(f"  PROMPT_OPTIMIZED: cached={optimization_metadata.get('cached', False)}, "
                          f"agent_type={optimization_metadata.get('agent_type', 'unknown')}")
        except Exception as e:
            print(f"  ⚠ Prompt optimization failed, using original: {e}")

    # Fallback to original prompt construction
    if prompt is None:
        # CRITICAL: Behavioral rules must be BEFORE task_text (C16 fix)
        # Agents need to see their constraints before starting work
        prompt = (
            f"{rules_first_section}"
            f"{rules_section}"  # MOVED: actual rules now before task, not after
            f"{skill_hint_first_section}"
            f"{context_history_section}"
            f"{task_text}"
            f"{memory_section}"
            f"{audience_section}"
            f"{skill_section}\n\n"
            "Execute this task completely using your tools. "
            "Read files, write code, run commands, verify your work. "
            "For simple questions, a direct answer is fine."
        )

    # Load ACP fallback configuration
    acp_fallback = load_acp_fallback_config()

    # AUTH PREFLIGHT: Check credentials before executing task (2026-03-11)
    # Prevents "Not logged in" failures that cause claude_code_crash pattern
    # Pattern from spawn_subagent - same check for main task execution path
    if not auth_health_preflight(agent_name, timeout=30):
        print(f"  AUTH PREFLIGHT FAIL: {agent_name} not authenticated — aborting task execution")
        # Log auth failure for monitoring
        auth_failure_log = Path(AGENTS_DIR) / "main" / "logs" / "auth-failures.jsonl"
        try:
            auth_failure_log.parent.mkdir(parents=True, exist_ok=True)
            with open(auth_failure_log, "a") as af:
                af.write(f'{{"timestamp": "{datetime.now().isoformat()}", "agent": "{agent_name}", "label": "execute_task_with_llm", "script": "agent-task-handler.py", "reason": "preflight_failed"}}\n')
        except Exception:
            pass
        _append_ledger({
            "event": "AUTH_PREFLIGHT_FAIL",
            "ts": datetime.now().isoformat(),
            "agent": agent_name,
            "task_id": task_id,
            "enforcer": "agent-task-handler.py",
        })
        return {
            "success": False,
            "error": "AUTH_PREFLIGHT_FAIL: Claude is not authenticated. Run /login to authenticate.",
            "content": "",
            "model": model or "claude-code",
            "latency_ms": 0,
        }

    # First attempt with requested model
    result = _call_claude_code(agent_name, prompt, config, skill_hint, timeout, model, priority)

    # Check if we should retry with fallback model
    if not result.get('success') and acp_fallback['enabled']:
        error_msg = result.get('error') or ''  # Handle explicit None values
        output_content = result.get('content', '')

        # Check for stall timeout (also trigger fallback if configured)
        is_stall = 'STALL_TIMEOUT' in error_msg or 'STALL_DETECTED' in error_msg
        is_rate_limit = _is_rate_limit_error(error_msg, output_content)
        
        # Check specifically for authentication failures (subset of rate limit patterns)
        is_auth_failure = any(pattern in (error_msg + ' ' + output_content).lower() for pattern in [
            "not logged in", "please run /login", "authentication failed", "auth failed",
            "invalid credentials", "unauthorized", "401", "token expired", "session expired",
            "sign in required", "login required", "claude login"
        ])

        should_fallback = False
        fallback_reason = None

        if is_auth_failure and acp_fallback['trigger_on_rate_limit']:
            should_fallback = True
            fallback_reason = "authentication_failed"
        elif is_rate_limit and acp_fallback['trigger_on_rate_limit']:
            should_fallback = True
            fallback_reason = "rate_limit_detected"
        elif is_stall and acp_fallback['trigger_on_stall']:
            should_fallback = True
            fallback_reason = "stall_timeout_detected"

        if should_fallback:
            # CONSTRAINT: Tolui must ONLY use the abliterated model - no fallbacks allowed
            if agent_name == 'tolui':
                print(f"  ⚠ Tolui constraint: skipping fallback (must use abliterated model only)")
                _append_ledger({
                    "event": "MODEL_FALLBACK_BLOCKED",
                    "ts": datetime.now().isoformat(),
                    "agent": agent_name,
                    "reason": "tolui_abliterated_constraint",
                    "original_error": (error_msg or 'Unknown error')[:200],  # Safe slicing
                })
                # Do not proceed with fallback - return the original failure
                should_fallback = False
            else:
                # Use fallback model for retry
                fallback_model = acp_fallback['fallback_model']
                print(f"  ⚠ {fallback_reason.replace('_', ' ').title()}, retrying with fallback model: {fallback_model}")

                if acp_fallback['log_events']:
                    _append_ledger({
                        "event": "MODEL_FALLBACK",
                        "ts": datetime.now().isoformat(),
                        "agent": agent_name,
                        "original_model": model or "claude-opus-4-6",
                        "fallback_model": fallback_model,
                        "reason": fallback_reason,
                        "error_preview": (error_msg or 'Unknown error')[:200],  # Safe slicing
                    })

                result = _call_claude_code(agent_name, prompt, config, skill_hint, timeout, fallback_model, priority)

                # Annotate result to indicate fallback was used
                if result.get('success'):
                    result['model'] = f"{fallback_model} (fallback)"
                    print(f"  ✓ Fallback successful: {fallback_model}")
                    if acp_fallback['log_events']:
                        _append_ledger({
                            "event": "MODEL_FALLBACK_SUCCESS",
                            "ts": datetime.now().isoformat(),
                            "agent": agent_name,
                            "fallback_model": fallback_model,
                        })
                else:
                    # Preserve original error but note fallback attempt
                    result['error'] = f"[Fallback to {fallback_model} also failed] {result.get('error', 'Unknown error')}"
                    result['output_content'] = output_content  # Preserve full output for error analysis
                    print(f"  ✗ Fallback also failed: {fallback_model}")
                    # Categorize error and save full content before truncation
                    error_type = categorize_error(result['error'], output_content)
                    error_file = None
                    if task_id:
                        error_file = save_error_content(
                            agent_name, task_id, result['error'],
                            output_content, error_type
                        )
                    _append_ledger({
                        "event": "MODEL_FALLBACK_FAILED",
                        "ts": datetime.now().isoformat(),
                        "agent": agent_name,
                        "fallback_model": fallback_model,
                        "error": (result.get('error') or 'Unknown error')[:500],  # Increased from 200
                        "error_type": error_type,  # NEW: structured error category
                        "error_file": error_file,  # NEW: path to full error content
                    })

    return result


def _pre_validate_research_sources(agent_name, task_content, task_id):
    """Pre-execution source validation for research tasks (mongke).

    Returns None if validation passes or is skipped.
    Returns an error dict if ALL sources are unreachable (fail fast).
    """
    if agent_name != 'mongke':
        return None
    try:
        from source_validator import validate_task_sources
        result = validate_task_sources(task_content)
        if result['urls_checked'] > 0:
            print(f"  🔍 Source validation: {result['urls_reachable']}/{result['urls_checked']} "
                  f"reachable ({result['elapsed_ms']}ms)")
        if result['block']:
            # Log to ledger for observability
            _append_ledger({
                "task_id": task_id or "unknown",
                "event": "SOURCE_VALIDATION_BLOCKED",
                "ts": datetime.now().isoformat(),
                "agent": agent_name,
                "urls_checked": result['urls_checked'],
                "urls_failed": result['urls_failed'],
                "reason": result['reason'][:300],
                "elapsed_ms": result['elapsed_ms'],
            })
            return {
                "success": False,
                "error": f"Pre-execution source validation failed: {result['reason'][:200]}",
                "model": "source_validator",
                "latency_ms": result['elapsed_ms'],
            }
    except Exception as e:
        # Validator import/crash should not block task execution
        print(f"  ⚠ Source validator error (non-blocking): {e}")
    return None


def _validate_domain_compliance(agent_name, task_content, task_id):
    """Pre-execution domain validation for ops agent (ogedei).

    Enforces O005 behavioral rule: reject tasks outside ops domain.
    Ops domain: monitoring, health checks, failover, alerts, reliability.
    Rejects: documentation, feature development, writing, content creation, non-ops research.

    Returns None if validation passes or is skipped.
    Returns an error dict if task is outside agent's domain (fail fast).
    """
    if agent_name != 'ogedei':
        return None

    # Domain keywords for ops (ogedei) - these are ALLOWED
    ops_keywords = {
        'monitor', 'health', 'check', 'failover', 'uptime', 'alert', 'reliability',
        'incident', 'escalation', 'circuit', 'breaker', 'timeout', 'queue', 'depth',
        'redis', 'neo4j', 'database', 'connection', 'pool', 'latency', 'throughput',
        'cron', 'launchd', 'scheduler', 'watchdog', 'heartbeat', 'ping', 'probe',
        'log', 'metric', 'telemetry', 'observability', 'dashboard', 'status',
        'reconcile', 'sync', 'backup', 'restore', 'cleanup', 'stale', 'orphan',
        'domain', 'compliance', 'validation', 'auth', 'credential', 'preflight',
        'deploy', 'rollback', 'capacity', 'scaling', 'performance', 'bottleneck',
    }

    # Keywords that indicate tasks OUTSIDE ops domain - trigger reroute
    # Using word-based detection for better flexibility
    writing_keywords = {
        'write article', 'write blog', 'write content', 'draft', 'edit', 'proofread',
        'documentation', 'doc update', 'readme', 'changelog', 'write up',
    }
    dev_keywords = {
        'implement', 'add feature', 'create feature', 'build component',
        'develop', 'code new', 'write code', 'program', 'application',
        'new function', 'create function', 'add function',
    }
    research_keywords = {
        'research and report', 'investigate and write', 'analyze and document',
        'study on', 'explore', 'survey of', 'literature review',
    }

    task_lower = task_content.lower()
    words = set(task_lower.split())

    # Check for explicit non-ops patterns (higher priority)
    # Check writing/documentation first
    for pattern in writing_keywords:
        if pattern in task_lower:
            correct_agent = 'chagatai'
            reason = f"writing/documentation task (detected: '{pattern}')"
            # Log and return
            _append_ledger({
                "task_id": task_id or "unknown",
                "event": "DOMAIN_COMPLIANCE_REJECT",
                "ts": datetime.now().isoformat(),
                "agent": agent_name,
                "correct_agent": correct_agent,
                "detected_pattern": pattern[:100],
                "reason": reason[:300],
            })
            return {
                "success": False,
                "error": f"Domain compliance: Task routed to wrong agent. This {reason} should go to {correct_agent}, not ogedei (ops).",
                "model": "domain_validator",
                "correct_agent": correct_agent,
                "latency_ms": 1,
            }

    # Check feature development
    for pattern in dev_keywords:
        if pattern in task_lower:
            correct_agent = 'temujin'
            reason = f"feature development task (detected: '{pattern}')"
            # Log and return
            _append_ledger({
                "task_id": task_id or "unknown",
                "event": "DOMAIN_COMPLIANCE_REJECT",
                "ts": datetime.now().isoformat(),
                "agent": agent_name,
                "correct_agent": correct_agent,
                "detected_pattern": pattern[:100],
                "reason": reason[:300],
            })
            return {
                "success": False,
                "error": f"Domain compliance: Task routed to wrong agent. This {reason} should go to {correct_agent}, not ogedei (ops).",
                "model": "domain_validator",
                "correct_agent": correct_agent,
                "latency_ms": 1,
            }

    # Check research
    for pattern in research_keywords:
        if pattern in task_lower:
            correct_agent = 'mongke'
            reason = f"research task (detected: '{pattern}')"
            # Log and return
            _append_ledger({
                "task_id": task_id or "unknown",
                "event": "DOMAIN_COMPLIANCE_REJECT",
                "ts": datetime.now().isoformat(),
                "agent": agent_name,
                "correct_agent": correct_agent,
                "detected_pattern": pattern[:100],
                "reason": reason[:300],
            })
            return {
                "success": False,
                "error": f"Domain compliance: Task routed to wrong agent. This {reason} should go to {correct_agent}, not ogedei (ops).",
                "model": "domain_validator",
                "correct_agent": correct_agent,
                "latency_ms": 1,
            }

    # Additional word-based check for cases not caught by phrase matching
    # Check if "write" appears with content/article/blog (writing task)
    if 'write' in words and any(w in words for w in {'article', 'blog', 'content', 'documentation', 'readme', 'changelog', 'guide', 'tutorial'}):
        correct_agent = 'chagatai'
        reason = "writing/documentation task (write + content keyword detected)"
        _append_ledger({
            "task_id": task_id or "unknown",
            "event": "DOMAIN_COMPLIANCE_REJECT",
            "ts": datetime.now().isoformat(),
            "agent": agent_name,
            "correct_agent": correct_agent,
            "reason": reason[:300],
        })
        return {
            "success": False,
            "error": f"Domain compliance: Task routed to wrong agent. This {reason} should go to {correct_agent}, not ogedei (ops).",
            "model": "domain_validator",
            "correct_agent": correct_agent,
            "latency_ms": 1,
        }

    # Check for development indicators
    if any(w in words for w in {'implement', 'develop', 'create', 'build'}) and any(w in words for w in {'feature', 'function', 'component', 'module', 'class'}):
        correct_agent = 'temujin'
        reason = "feature development task (dev + feature keyword detected)"
        _append_ledger({
            "task_id": task_id or "unknown",
            "event": "DOMAIN_COMPLIANCE_REJECT",
            "ts": datetime.now().isoformat(),
            "agent": agent_name,
            "correct_agent": correct_agent,
            "reason": reason[:300],
        })
        return {
            "success": False,
            "error": f"Domain compliance: Task routed to wrong agent. This {reason} should go to {correct_agent}, not ogedei (ops).",
            "model": "domain_validator",
            "correct_agent": correct_agent,
            "latency_ms": 1,
        }

    # Check for research + writing combination
    if 'research' in words and any(w in words for w in {'write', 'report', 'document', 'article'}):
        correct_agent = 'mongke'
        reason = "research task (research + write keyword detected)"
        _append_ledger({
            "task_id": task_id or "unknown",
            "event": "DOMAIN_COMPLIANCE_REJECT",
            "ts": datetime.now().isoformat(),
            "agent": agent_name,
            "correct_agent": correct_agent,
            "reason": reason[:300],
        })
        return {
            "success": False,
            "error": f"Domain compliance: Task routed to wrong agent. This {reason} should go to {correct_agent}, not ogedei (ops).",
            "model": "domain_validator",
            "correct_agent": correct_agent,
            "latency_ms": 1,
        }

    # Allow task to proceed - no domain violations detected
    return None


def process_task(agent_name, task):
    """Process a single task.

    Routes to Ollama executor for agents with executor='ollama' (text-only local models).
    Routes to Claude Code executor for all other agents (full tool access).
    """
    # Use full task content for execution, not just the summary line
    task_content = task.get('full_content', task['task'])
    task_id = task.get('task_id')
    print(f"\n📋 Processing: {task['task'][:80]}...")

    # Mark as executing
    executing_file = mark_task_executing(task['file'])
    print(f"  Status: executing")

    # Pre-execution snapshot for rollback capability
    if task_id:
        try:
            from task_snapshot import create_snapshot
            # Redirect snapshot logging to prevent stderr pollution affecting error detection
            import logging
            snapshot_logger = logging.getLogger('task_snapshot')
            original_level = snapshot_logger.level
            snapshot_logger.setLevel(logging.WARNING)  # Only log warnings/errors
            snap = create_snapshot(agent_name, task_id, os.path.basename(task['file']))
            snapshot_logger.setLevel(original_level)  # Restore original level
            print(f"  📸 Snapshot created: {snap['file_count']} files ({snap['archive_size_bytes']} bytes)")
        except Exception as e:
            print(f"  ⚠ Snapshot failed (non-blocking): {e}")

    # Pre-execution source validation (mongke research tasks)
    pre_fail = _pre_validate_research_sources(agent_name, task_content, task_id)
    if pre_fail:
        print(f"  ✗ Source validation BLOCKED: {pre_fail['error'][:120]}")
        # Append validation failure to task file for traceability
        _append_output_to_executing(executing_file, f"**Blocked:** {pre_fail['error']}", "source_validator", 0, success=False)
        mark_task_completed(task['file'], 'failed', executing_file=executing_file)
        if task_id:
            _append_ledger({
                "task_id": task_id,
                "event": "EXECUTION_DETAIL",
                "ts": datetime.now().isoformat(),
                "agent": agent_name,
                "execution_time_s": pre_fail.get('latency_ms', 0) / 1000,
                "error": pre_fail['error'][:500],
                "success": False,
                "executor": "source_validator",
            })
        return False

    # Pre-execution domain compliance validation (ogedei ops tasks)
    domain_fail = _validate_domain_compliance(agent_name, task_content, task_id)
    if domain_fail:
        print(f"  ✗ Domain compliance BLOCKED: {domain_fail['error'][:120]}")
        # Append validation failure to task file for traceability
        _append_output_to_executing(executing_file, f"**Blocked:** {domain_fail['error']}", "domain_validator", 0, success=False)
        mark_task_completed(task['file'], 'failed', executing_file=executing_file)
        if task_id:
            _append_ledger({
                "task_id": task_id,
                "event": "EXECUTION_DETAIL",
                "ts": datetime.now().isoformat(),
                "agent": agent_name,
                "correct_agent": domain_fail.get('correct_agent', 'kublai'),
                "execution_time_s": domain_fail.get('latency_ms', 0) / 1000,
                "error": domain_fail['error'][:500],
                "success": False,
                "executor": "domain_validator",
            })
        return False

    # Load agent config
    config = load_agent_config(agent_name)

    # Route to appropriate executor based on config
    executor = config.get('executor', 'claude-code')
    skill_hint = task.get('skill_hint')
    priority = task.get('priority', 'normal')
    priority_timeout = TIMEOUT_BY_PRIORITY.get(priority, CLAUDE_TIMEOUT)
    skill_timeout = SLOW_SKILLS.get(skill_hint, 0)
    timeout = max(priority_timeout, skill_timeout)

    # Extract cross-agent communication fields
    context_history = task.get('context_history')
    audience = task.get('audience')
    clarification_deadline = task.get('clarification_deadline')

    # Log context history presence for observability
    if context_history:
        print(f"  📎 Context history: {len(context_history)} previous agent(s) worked on this task")

    # FIX 2026-03-13: Initialize start_time BEFORE executor conditionals to ensure it's always defined
    # Prevents NameError when _extract_skills_from_transcript is called after model drift rejection
    start_time = time.time()

    if executor == 'ollama':
        # Direct Ollama API call (no tools, text-only)
        print(f"  🤖 Executing via Ollama (direct API)... (timeout: {timeout}s)")
        result = execute_task_with_ollama(agent_name, task_content, config, timeout=timeout)
        elapsed_s = round(time.time() - start_time, 1)
        executor_name = "ollama"
    else:
        # Claude Code with full tool access
        print(f"  🤖 Executing via Claude Code...{f' (skill: {skill_hint})' if skill_hint else ''} (timeout: {timeout}s)")
        VALID_CLAUDE_MODELS = {
            # Only Claude models are valid for Claude Code executor
            'claude-opus-4-6', 'claude-sonnet-4-6', 'claude-haiku-4-5',
        }
        # NOTE: Uses module-level PROXY_ENDPOINTS (includes Z.AI, Alibaba as of 2026-03-09)
        model = config.get('model')
        # Fallback: check .claude/settings.json if config.json has no model
        if not model:
            try:
                settings_path = f"{AGENTS_DIR}/{agent_name}/.claude/settings.json"
                with open(settings_path, 'r') as _sf:
                    settings = json.load(_sf)
                model = settings.get('model')
                debug_msg = f"SETTINGS_READ: settings_path={settings_path}, model={model}\n"
                with open('/tmp/agent_handler_debug.log', 'a') as f:
                    f.write(debug_msg)
            except Exception as e:
                debug_msg = f"SETTINGS_ERROR: {type(e).__name__}: {e}\n"
                with open('/tmp/agent_handler_debug.log', 'a') as f:
                    f.write(debug_msg)
                pass
        # Check if using a proxy endpoint
        proxy_url = None
        try:
            settings_path = f"{AGENTS_DIR}/{agent_name}/.claude/settings.json"
            with open(settings_path, 'r') as _sf:
                settings = json.load(_sf)
            proxy_url = settings.get('env', {}).get('ANTHROPIC_BASE_URL', '')
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        is_using_proxy = any(endpoint in proxy_url for endpoint in PROXY_ENDPOINTS) if proxy_url else False
        # Validate model - only Claude models allowed when not using proxy
        if model and model not in VALID_CLAUDE_MODELS and not is_using_proxy:
            print(f"  ⚠ Model '{model}' not available — using claude-opus-4-6")
            model = None
        # Capture env_model for fallback before potentially clearing model
        env_model = None
        if not env_model:
            try:
                settings_path = f"{AGENTS_DIR}/{agent_name}/.claude/settings.json"
                with open(settings_path, 'r') as _sf:
                    settings = json.load(_sf)
                env_model = settings.get('env', {}).get('ANTHROPIC_MODEL')
            except (FileNotFoundError, json.JSONDecodeError):
                pass
        # If using proxy with a non-Claude model, don't pass --model (let env var handle it)
        if is_using_proxy and model and model not in VALID_CLAUDE_MODELS:
            print(f"  ✓ Using proxy model '{model}' via ANTHROPIC_MODEL env var")
            model = None  # Don't pass --model, let env var handle it
        selected_model = model or env_model or 'claude-opus-4-6'
        debug_msg = f"MODEL_SELECT: model={model}, selected_model={selected_model}, is_using_proxy={is_using_proxy}\n"
        with open('/tmp/agent_handler_debug.log', 'a') as f:
            f.write(debug_msg)
        print(f"  🔧 Model selection: config={config.get('model', '(none)')}, resolved={selected_model}, proxy={is_using_proxy}")

        # CRITICAL: Validate session model matches config model
        # Prevents execution on agents with session drift (e.g., session using GLM-5 while config expects claude-opus-4-6)
        is_valid, session_model, reason = _validate_session_model(agent_name, selected_model)
        if not is_valid:
            # Session model drift detected - reject execution
            error_msg = f"🚨 SESSION MODEL DRIFT REJECTED: {reason}"
            print(f"  {error_msg}")
            print(f"  📋 Action required: Restart agent session or fix config in ~/.openclaw/agents/{agent_name}/.claude/settings.json")

            # Log to ledger for escalation
            if task_id:
                _append_ledger({
                    "task_id": task_id,
                    "event": "MODEL_DRIFT_REJECTED",
                    "ts": datetime.now().isoformat(),
                    "agent": agent_name,
                    "expected_model": selected_model,
                    "session_model": session_model,
                    "reason": reason,
                })

            # Return failure result to trigger retry logic
            result = {
                'success': False,
                'error': f"Session model drift: {reason}",
                'model': session_model,
            }
            elapsed_s = 0
            executor_name = "rejected-model-drift"
        else:
            result = execute_task_with_llm(
                agent_name, task_content, config,
                skill_hint=skill_hint, timeout=timeout, priority=priority,
                model=selected_model, task_id=task_id,
                context_history=context_history, audience=audience
            )
            elapsed_s = round(time.time() - start_time, 1)
            executor_name = "claude-code"

    # Extract skill invocations from Claude Code session transcript (only for claude-code)
    # Rule R008: Enforce skill_hint invocation — if skill_hint present, must be invoked
    skills_invoked = []
    r008_violation = False
    if task_id and executor == 'claude-code':
        skills_invoked = _extract_skills_from_transcript(agent_name, start_time, task_id, skill_hint)

        # Rule R008 Tracking (NON-BLOCKING): Check if required skill_hint was actually invoked
        # Skills are auto-invoked in the prompt, so task proceeds even if agent didn't explicitly invoke
        # This tracks compliance for monitoring without failing tasks
        if skill_hint:
            # Normalize hint for matching (remove leading slash if present)
            hint_normalized = skill_hint.lstrip('/')
            # Check if any invoked skill matches the hint
            hint_matched = any(
                hint_normalized in skill.lstrip('/') or skill.lstrip('/') in hint_normalized
                for skill in skills_invoked
            )
            if not hint_matched:
                r008_violation = True
                print(f"  ℹ️  R008_TRACKING: skill_hint='{skill_hint}' was not explicitly invoked (invoked: {skills_invoked})")
                print(f"  → Task proceeds (skill was auto-invoked in prompt)")

                # Log to ledger for tracking (informational only, does not fail task)
                try:
                    _append_ledger({
                        "task_id": task_id,
                        "event": "R008_SKILL_NOT_INVOKED",
                        "ts": datetime.now().isoformat(),
                        "agent": agent_name,
                        "skill_hint": skill_hint,
                        "skills_invoked": skills_invoked,
                        "auto_invoked": True,
                        "enforcer": "agent-task-handler.py"
                    })
                except Exception as ledger_err:
                    # Non-fatal: tracking continues even if ledger logging fails
                    if "invalid event type" in str(ledger_err).lower():
                        print(f"  [LEDGER] Schema update pending, R008_SKILL_NOT_INVOKED event skipped: {ledger_err}")
                    else:
                        print(f"  [LEDGER] Failed to log R008_SKILL_NOT_INVOKED: {ledger_err}")
                # TASK PROCEEDS NORMALLY - no failure, no content modification
                # result['success'] remains unchanged (task completes normally)

    # SKILL TELEMETRY: Track skill_hint → skill_invocation correlation
    # This enables analysis of how often agents follow skill recommendations
    if task_id and skill_hint:
        try:
            _track_skill_telemetry(task_id, agent_name, skill_hint, skills_invoked, r008_violation)
        except Exception as e:
            print(f"  WARNING: Skill telemetry emission failed: {e}")

    # R008 LAYER 6: FAILURE CONSEQUENCE AMPLIFICATION
    # Track R008 violations per agent and escalate after repeated failures
    if r008_violation and task_id:
        try:
            _track_r008_violation(agent_name, task_id, skill_hint)
        except Exception as e:
            print(f"  ⚠ R008 tracking failed: {e}")

    # Analyze tool usage from stdout and append EXECUTION_TRACE (only for claude-code)
    output_for_trace = result.get('content', '') or result.get('error', '') or ''
    if task_id and executor == 'claude-code' and output_for_trace:
        trace = _analyze_tool_usage(output_for_trace)
        _append_ledger({
            "task_id": task_id,
            "event": "EXECUTION_TRACE",
            "ts": datetime.now().isoformat(),
            "agent": agent_name,
            "executor": "claude-code",
            **trace,
            "skill_version": 1,
        })

    if result.get('success'):
        # Save result to workspace
        workspace_path = config.get('workspace_path', f"{AGENTS_DIR}/{agent_name}/workspace")
        result_file = f"{workspace_path}/task-{int(datetime.now().timestamp())}.md"

        os.makedirs(workspace_path, exist_ok=True)
        with open(result_file, 'w') as f:
            f.write(f"# Task Result\n\n")
            f.write(f"**Task:** {task['task']}\n\n")
            f.write(f"**Model:** {result.get('model', executor_name)}\n\n")
            f.write(f"---\n\n")
            f.write(f"{result.get('content', 'No content')}\n")

        print(f"  ✓ Result saved: {result_file}")

        # CRITICAL: Append execution output to .executing.md BEFORE completion verification
        # This prevents fake completions - verification checks the file has substantial output
        output_content = result.get('content', '')
        append_success = _append_output_to_executing(executing_file, output_content, result.get('model', executor_name), elapsed_s, success=True)

        # If output append failed, mark as no_output instead of completed
        completion_status = 'completed' if append_success else 'no_output'
        if not append_success:
            print(f"  ⚠ Output append failed, marking as no_output")

        mark_task_completed(task['file'], completion_status, executing_file=executing_file)
        print(f"  ✓ Task {completion_status} via {executor_name} ({elapsed_s}s)")

        # Emit execution metadata to ledger
        if task_id:
            output_content = result.get('content', '')
            _append_ledger({
                "task_id": task_id,
                "event": "EXECUTION_DETAIL",
                "ts": datetime.now().isoformat(),
                "agent": agent_name,
                "execution_time_s": elapsed_s,
                "output_lines": len(output_content.splitlines()),
                "result_file": result_file,
                "success": True,
                "executor": executor_name,
            })
            # Check if task warrants architecture.md update (only for claude-code)
            if executor == 'claude-code':
                _check_architecture_update(agent_name, task_content, output_content, task_id)

        # Persist research findings to Neo4j (mongke only, non-fatal)
        try:
            from persist_research import persist_task_research
            persist_task_research(agent_name, task.get('task', ''),
                                 result.get('content', ''), task_id)
        except Exception:
            pass

        # Update Neo4j
        update_agent_state(agent_name, 'idle', None, increment_completed=True)

        # Write per-agent breadcrumb for /task-complete (avoids ledger race)
        try:
            bc_path = os.path.join(str(_TASK_LEDGER.parent),
                                   f"last-completion-{agent_name}.json")
            with open(bc_path, "w") as f:
                json.dump({
                    "task_id": task_id,
                    "agent": agent_name,
                    "result_file": result_file,
                    "execution_time_s": elapsed_s,
                    "task_summary": task['task'][:200],
                    "ts": datetime.now().isoformat(),
                }, f)
        except Exception:
            pass

        # Spawn /task-complete skill (non-blocking with timeout/reaping)
        _spawn_haiku_completion(agent_name)

        # Record comprehensive task data for reflections
        try:
            from kublai_task_report import TaskReporter, estimate_token_cost
            reporter = TaskReporter()

            # Parse token usage from output if available
            output_text = output_content or ""
            input_tokens = None
            output_tokens = None
            total_tokens = None

            # Extract token info from Claude Code output
            import re
            token_match = re.search(r'(\d+)\s*input.*?(\d+)\s*output', output_text, re.IGNORECASE)
            if token_match:
                input_tokens = int(token_match.group(1))
                output_tokens = int(token_match.group(2))
                total_tokens = input_tokens + output_tokens

            # Record task execution metrics
            reporter.record_task_execution(task_id, agent_name, {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "token_cost_usd": estimate_token_cost(total_tokens or 0, result.get('model', '')),
                "model_effort": config.get('effort', 'medium'),
                "actual_duration_seconds": elapsed_s,
                "skills_invoked": _extract_skills_from_transcript(agent_name, start_time, task_id, skill_hint),
            })

            # Record agent state
            reporter.record_agent_state(agent_name, {
                "queue_depth_at_start": count_queue_depth(agent_name),
                "health_flags": ["normal"],
            }, task_id=task_id)

            # Analyze and record code changes from output
            code_changes = _analyze_code_changes(output_text, agent_name)
            if code_changes:
                reporter.record_code_changes(task_id, code_changes)

            # Record quality signals
            reporter.record_quality_signals(task_id, {
                "verification_checks_passed": 1 if result.get('success') else 0,
                "verification_checks_failed": 0 if result.get('success') else 1,
                "verification_score": 100.0 if result.get('success') else 0.0,
            })

            reporter.close()
        except Exception as e:
            print(f"  WARNING: Task data collection failed: {e}")

        # Emit pipeline event for observability
        try:
            from neo4j_task_tracker import get_tracker
            get_tracker().emit_pipeline_event(
                "TASK_COMPLETE_REPORT", agent=agent_name,
                payload={"task_id": task_id, "execution_time_s": elapsed_s},
            )
        except Exception:
            pass

        # Log model usage for tracking (DISABLED: model_tracker module not implemented)
        # try:
        #     from model_tracker import get_tracker as get_model_tracker
        #     model_used = result.get('model', selected_model if 'selected_model' in dir() else executor_name)
        #     # Strip "(fallback)" suffix if present
        #     if isinstance(model_used, str):
        #         model_used = model_used.replace(" (fallback)", "").strip()
        #     get_model_tracker().log_model_usage(
        #         task_id=task_id,
        #         agent=agent_name,
        #         model=model_used,
        #         success=True,
        #         duration_seconds=elapsed_s,
        #     )
        # except Exception as e:
        #     # Don't block task completion on model tracking failure
        #     print(f"  WARNING: Model tracking failed: {e}")
        pass  # Model tracking disabled until model_tracker module is implemented

        return True
    else:
        error_msg = result.get('error') or 'Unknown error'
        output_content = result.get('content', '') or result.get('error', '')
        # Safe string slicing with None check
        error_display = (error_msg or 'Unknown error')[:200] if error_msg else 'Unknown error'
        print(f"  ✗ {executor_name} failed: {error_display}")

        # O002: Categorize error FIRST to determine if investigation is required
        # This must happen before completion_status is set
        error_type = categorize_error(error_msg, output_content)

        # O002: SIGTERM/fast-failure detection - require investigation before retry
        # Tasks failing in <120s with SIGTERM signal indicate config/auth issues
        # that must be diagnosed (blind retry wastes cycles and violates behavioral rule)
        is_fast_sigterm = (
            error_type == "SIGTERM_KILLED" and elapsed_s < 120
        )

        # CREDENTIAL_ERROR handling: Use 'credential_failed' status to bypass revision loops
        # This prevents endless .revision-N.md creation when agents have invalid credentials
        is_credential_error = result.get('credential_error', False) or 'CREDENTIAL_ERROR' in error_msg

        # O002: Use 'investigation_required' status for fast SIGTERM failures
        # This is a terminal state (like credential_failed) that bypasses revision loops
        if is_fast_sigterm:
            completion_status = 'investigation_required'
        elif is_credential_error:
            completion_status = 'credential_failed'
        else:
            completion_status = 'failed'

        # CRITICAL: Append error output to .executing.md so task file has execution trace
        # This ensures the task file reflects what actually happened during execution
        append_success = _append_output_to_executing(executing_file, output_content[:10000], result.get('model', executor_name), elapsed_s, success=False)
        if not append_success:
            print(f"  ⚠ Failed to append error output to task file")

        if is_credential_error:
            print(f"  🔐 CREDENTIAL ERROR: Task permanently failed (no revision)")
            print(f"  🔐 ACTION REQUIRED: Update Anthropic API key in ~/.openclaw/agents/{agent_name}/.claude/settings.json")

        if is_fast_sigterm:
            print(f"  ⚠ O002: FAST SIGTERM FAILURE ({elapsed_s:.0f}s) - Investigation required before retry")
            print(f"  ⚠ ACTION: Read error output, verify config, check auth (do NOT blind retry)")
            # Log O002 violation for ops tracking
            _append_ledger({
                "event": "O002_FAST_FAILURE_REQUIRES_INVESTIGATION",
                "ts": datetime.now().isoformat(),
                "agent": agent_name,
                "task_id": task_id,
                "execution_time_s": elapsed_s,
                "error_type": error_type,
                "error_preview": (error_msg or 'Unknown error')[:200],
            })

        mark_task_completed(task['file'], completion_status, executing_file=executing_file)

        if task_id:
            # Save full error content for investigation
            error_file = save_error_content(
                agent_name, task_id, error_msg, output_content, error_type
            )
            _append_ledger({
                "task_id": task_id,
                "event": "EXECUTION_DETAIL",
                "ts": datetime.now().isoformat(),
                "agent": agent_name,
                "execution_time_s": elapsed_s,
                "error": (error_msg or 'Unknown error')[:500],  # Safe slicing
                "error_type": error_type,  # NEW: structured error category
                "error_file": error_file,  # NEW: path to full error content
                "success": False,
                "executor": executor_name,
            })

        # Emit pipeline event for observability
        try:
            from neo4j_task_tracker import get_tracker
            get_tracker().emit_pipeline_event(
                "FAILURE_ALERT", agent=agent_name,
                payload={"task_id": task_id, "error": (error_msg or 'Unknown error')[:200], "error_type": error_type},
            )
        except Exception:
            pass

        # Record comprehensive error data for failed tasks
        try:
            from kublai_task_report import TaskReporter
            reporter = TaskReporter()

            # Record error analysis
            reporter.record_error(task_id, {
                "error_category": error_type,
                "error_message": error_msg,
                "recovery_attempts": 1,  # Already tried once
                "fallback_models_tried": [result.get('model', '')] if "fallback" in str(result.get('model', '')).lower() else [],
                "recovery_success": False,
            })

            # Record agent state
            reporter.record_agent_state(agent_name, {
                "queue_depth_at_start": count_queue_depth(agent_name),
                "health_flags": ["stressed"] if error_type in ["STALL_TIMEOUT", "MODEL_FAILURE"] else ["normal"],
            }, task_id=task_id)

            # Record quality signals for failed task
            reporter.record_quality_signals(task_id, {
                "verification_checks_passed": 0,
                "verification_checks_failed": 1,
                "verification_score": 0.0,
                "rework_required": True,
                "rework_reason": f"Task failed: {error_type}",
            })

            reporter.close()
        except Exception as e:
            print(f"  WARNING: Error data collection failed: {e}")

        # Log model usage for tracking (DISABLED: model_tracker module not implemented)
        # try:
        #     from model_tracker import get_tracker as get_model_tracker
        #     model_used = result.get('model', selected_model if 'selected_model' in dir() else executor_name)
        #     # Strip "(fallback)" suffix if present
        #     if isinstance(model_used, str):
        #         model_used = model_used.replace(" (fallback)", "").strip()
        #     get_model_tracker().log_model_usage(
        #         task_id=task_id,
        #         agent=agent_name,
        #         model=model_used,
        #         success=False,
        #         duration_seconds=elapsed_s,
        #         error_type=error_type,
        #     )
        # except Exception as e:
        #     # Don't block task completion on model tracking failure
        #     print(f"  WARNING: Model tracking failed: {e}")
        pass  # Model tracking disabled until model_tracker module is implemented

        return False

def update_agent_state(agent_name, status='busy', task_label=None, increment_completed=False):
    """Update agent state in Neo4j"""
    try:
        from neo4j_task_tracker import get_driver

        driver = get_driver()
        
        with driver.session() as session:
            if increment_completed:
                session.run("""
                    MATCH (a:AgentState {name: $name})
                    SET a.status = $status,
                        a.current_task = $task,
                        a.last_heartbeat = datetime(),
                        a.tasks_completed = coalesce(a.tasks_completed, 0) + 1
                """, name=agent_name, status=status, task=task_label)
            elif task_label:
                session.run("""
                    MATCH (a:AgentState {name: $name})
                    SET a.status = $status,
                        a.current_task = $task,
                        a.last_heartbeat = datetime()
                """, name=agent_name, status=status, task=task_label)
            else:
                session.run("""
                    MATCH (a:AgentState {name: $name})
                    SET a.status = $status,
                        a.current_task = null,
                        a.last_heartbeat = datetime()
                """, name=agent_name, status=status)
        
        driver.close()
    except Exception as e:
        print(f"⚠ Neo4j update failed: {e}")

def execute_single_task(agent_name, task_file):
    """Execute a single task file via Claude Code."""
    with open(task_file, 'r') as f:
        content = f.read()

    # Extract short description for logging
    task_desc = content
    for line in content.split('\n'):
        if line.startswith('# Task:'):
            task_desc = line.replace('# Task:', '').strip()
            break

    depth = _extract_depth(content)
    task_id = _extract_task_id(content, filepath=task_file)
    skill_hint = _extract_skill_hint(content)

    # Extract new communication/context fields
    audience = _extract_audience(content)
    clarification_deadline = _extract_clarification_deadline(content)
    context_history = _extract_context_history(content)
    output_format = _extract_output_format(content)

    # Determine priority from filename prefix
    basename = os.path.basename(task_file).lower()
    if basename.startswith('high-'):
        priority = 'high'
    elif basename.startswith('low-'):
        priority = 'low'
    else:
        priority = 'normal'

    task = {
        'file': task_file,
        'task': task_desc,
        'task_id': task_id,
        'skill_hint': skill_hint,
        'full_content': content,  # Pass full content to Claude Code
        'priority': priority,
        'depth': depth,
        'audience': audience,
        'clarification_deadline': clarification_deadline,
        'context_history': context_history,
        'output_format': output_format,
    }

    return process_task(agent_name, task)

def main():
    parser = argparse.ArgumentParser(description='Agent task handler')
    parser.add_argument('--agent', required=True, help='Agent name')
    parser.add_argument('--poll', action='store_true', help='Continuously poll for tasks')
    parser.add_argument('--poll-interval', type=int, default=30, help='Poll interval in seconds')
    parser.add_argument('--task-file', help='Execute specific task file')
    
    args = parser.parse_args()
    
    # If task-file is specified, execute single task
    if args.task_file:
        print(f"Executing task: {args.task_file}")
        result = execute_single_task(args.agent, args.task_file)
        sys.exit(0 if result else 1)
    
    agent_name = args.agent
    print(f"=== Agent Task Handler: {agent_name.capitalize()} ===\n")

    # Load config
    try:
        config = load_agent_config(agent_name)
        print(f"Role: {config.get('agent_role')}")
        print(f"Model: {config.get('model')}")
        print(f"Workspace: {config.get('workspace_path')}")
        print()
    except Exception as e:
        print(f"✗ Failed to load config: {e}")
        sys.exit(1)

    # Check proxy health if configured
    try:
        settings_path = f"{AGENTS_DIR}/{agent_name}/.claude/settings.json"
        with open(settings_path, 'r') as _sf:
            settings = json.load(_sf)
        proxy_url = settings.get('env', {}).get('ANTHROPIC_BASE_URL', '')
        is_using_proxy = any(endpoint in proxy_url for endpoint in PROXY_ENDPOINTS) if proxy_url else False
        if is_using_proxy:
            log_proxy_status(agent_name, proxy_url, is_using_proxy)
    except (FileNotFoundError, json.JSONDecodeError):
        pass  # Skip proxy check if no settings

    # Update state to idle
    update_agent_state(agent_name, 'idle')
    
    if args.poll:
        print(f"Polling for tasks every {args.poll_interval}s... (Ctrl+C to stop)\n")
        try:
            while True:
                tasks = get_pending_tasks(agent_name)
                
                if tasks:
                    print(f"Found {len(tasks)} pending task(s)")
                    update_agent_state(agent_name, 'busy', tasks[0]['file'])
                    
                    for task in tasks:
                        process_task(agent_name, task)
                    
                    update_agent_state(agent_name, 'idle')
                else:
                    print(f"No pending tasks (polling...)")
                
                time.sleep(args.poll_interval)
        except KeyboardInterrupt:
            print("\n\nStopping poll...")
            update_agent_state(agent_name, 'idle')
    else:
        # Single poll
        tasks = get_pending_tasks(agent_name)
        
        if tasks:
            print(f"Found {len(tasks)} pending task(s)\n")
            update_agent_state(agent_name, 'busy', tasks[0]['file'])
            
            for task in tasks:
                process_task(agent_name, task)
            
            update_agent_state(agent_name, 'idle')
            print(f"\n✓ All tasks processed")
        else:
            print("No pending tasks")

if __name__ == "__main__":
    main()
