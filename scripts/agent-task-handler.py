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
from kurultai_paths import AGENTS_DIR as _AGENTS_DIR, SPAWN_QUEUE as _SPAWN_QUEUE, TASK_LEDGER as _TASK_LEDGER, CLAUDE_AGENT as _CLAUDE_AGENT
from kurultai_ledger import append_ledger as _kp_append_ledger

AGENTS_DIR = str(_AGENTS_DIR)
SPAWN_QUEUE = str(_SPAWN_QUEUE)
CLAUDE_AGENT = str(_CLAUDE_AGENT)
CLAUDE_TIMEOUT = 7200  # 2 hours for Claude Code execution

# Fallback model configuration for rate limit recovery
# When the primary model (claude-opus-4-6) is rate limited, fallback to claude-sonnet-4-6
# Sonnet has higher rate limits and is suitable for most tasks
FALLBACK_MODEL = "claude-sonnet-4-6"  # Fallback when rate limited (higher limits than opus)
MAX_RATE_LIMIT_RETRIES = 1  # Only retry once with fallback model
TIMEOUT_BY_PRIORITY = {
    'high': 7200,   # 2 hours for complex high-priority tasks
    'normal': 7200, # 2 hours
    'low': 7200,    # 2 hours
}
# Skills that need extra time (design exploration, brainstorming)
SLOW_SKILLS = {
    '/horde-brainstorming': 7200,
    '/golden-horde': 7200,
    '/horde-implement': 7200,
    '/horde-review': 7200,
    '/horde-debug': 7200,
    '/horde-learn': 7200,
    '/horde-swarm': 7200,
    '/horde-test': 7200,
    # Medium-complexity skills: get slow stall thresholds (7min silence / 8min elapsed)
    # but don't override the priority-based execution timeout (value=0)
    '/senior-frontend': 0,
    '/senior-backend': 0,
    '/senior-fullstack': 0,
    '/senior-architect': 0,
    '/systematic-debugging': 0,
    '/content-research-writer': 0,
    '/horde-gate-testing': 0,
    '/horde-plan': 0,
}
MAX_TASK_DEPTH = 3
HAIKU_TIMEOUT = 120  # Max seconds for /task-complete haiku notification (increased from 60 due to cold start delays)

# Proxy health check configuration
PROXY_HEALTH_CHECK_TIMEOUT = 5  # seconds
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
        # Create SSL context that doesn't verify certificates (for proxy endpoints)
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

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
        Error type string: PROXY_AUTH, PROXY_ERROR, RATE_LIMIT, MODEL_FAILURE,
                          STALL_TIMEOUT, VERIFICATION_FAILED, or UNKNOWN
    """
    if not error_msg:
        return "UNKNOWN"

    combined = (error_msg or "") + " " + (output_content or "")
    combined_lower = combined.lower()

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
                    [CLAUDE_AGENT, "/task-complete"],
                    stdout=log_f, stderr=log_f,
                    close_fds=True,
                    env=env_haiku,
                )
            try:
                return_code = proc.wait(timeout=HAIKU_TIMEOUT)
                with open(log_file, 'a') as log_f:
                    log_f.write(f"[{datetime.now().isoformat()}] /task-complete for {agent_name} exited with {return_code}\n")
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
    """Load agent configuration"""
    config_path = f"{AGENTS_DIR}/{agent_name}/config.json"
    with open(config_path, 'r') as f:
        return json.load(f)

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
    """Get pending tasks from agent's queue"""
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
                
                # Determine priority
                priority = 'normal'
                if 'high-' in task_file:
                    priority = 'high'
                elif 'low-' in task_file:
                    priority = 'low'
                
                tasks.append({
                    'file': task_file,
                    'task': task_desc,
                    'priority': priority,
                    'created': datetime.fromtimestamp(os.path.getmtime(task_file)).isoformat()
                })
    
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


def _verify_task_completion(task_file):
    """Verify task file has substantial output before marking as complete.

    Checks:
    - Has content beyond frontmatter (at least 20 non-frontmatter lines)
    - Has completion markers (## Result, ## Output, ## Summary, ## Done)
    - Output has substance (not just headers)

    Returns tuple: (is_valid, reason)
    """
    try:
        with open(task_file, 'r') as f:
            content = f.read()

        # Split frontmatter from content
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                body = parts[2].strip()
            else:
                body = content
        else:
            body = content

        # Count non-frontmatter lines
        lines = body.split('\n')
        content_lines = [l for l in lines if l.strip() and not l.strip().startswith('#')]

        # Check for minimum content (20 lines)
        if len(content_lines) < 20:
            return False, f"Insufficient output ({len(content_lines)} lines, need 20+)"

        # Check for completion markers
        completion_markers = ['## Result', '## Output', '## Summary', '## Done', '## Completed']
        has_marker = any(marker in body for marker in completion_markers)

        if not has_marker:
            # For tasks without explicit markers, require more substantial content
            if len(content_lines) < 30:
                return False, f"No completion markers and insufficient output ({len(content_lines)} lines)"

        return True, "OK"
    except Exception as e:
        return False, f"Verification error: {e}"


def _append_output_to_executing(executing_file, content, model, duration_s, success=True):
    """Append execution output to .executing.md file before completion verification.

    This is CRITICAL for fake completion prevention. The verification function
    checks the .executing.md file for substantial output, so we must append
    the actual execution results BEFORE marking as done.

    Args:
        executing_file: Path to .executing.md file
        content: Execution output content (stdout result or error)
        model: Model used for execution
        duration_s: Execution duration in seconds
        success: True if successful execution, False if failed
    """
    if not os.path.exists(executing_file):
        return

    try:
        with open(executing_file, 'a') as f:
            f.write(f"\n\n## Execution Output\n\n")
            f.write(f"**Model:** {model}\n")
            f.write(f"**Duration:** {duration_s}s\n")
            f.write(f"**Status:** {'Completed' if success else 'Failed'}\n")
            f.write(f"\n---\n\n")
            f.write(content)
            f.write(f"\n")
    except Exception as e:
        print(f"  ⚠ Failed to append output to executing file: {e}")


def mark_task_executing(task_file):
    """Mark task as being executed and write PID sentinel."""
    executing_file = task_file.replace('.md', '.executing.md')
    os.rename(task_file, executing_file)
    _write_pid_file(executing_file)
    return executing_file


def mark_task_completed(task_file, status='completed', executing_file=None):
    """Mark task as completed.

    Handles the race where recover_stale_executions() renames the
    .executing.md file before this function runs. Falls back to searching
    for retry files created by recovery.

    Args:
        task_file: Original task file path (before .executing rename).
        status: 'completed', 'failed', or 'no_output'.
        executing_file: Actual .executing.md path if known (preferred).
    """
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

    completed_suffix = f'.{status}.done.md'

    # Normal path: .executing.md still exists
    if os.path.exists(executing_file):
        completed_file = executing_file.replace('.executing.md', completed_suffix)
        try:
            os.rename(executing_file, completed_file)
        except FileNotFoundError:
            # Race: recover_stale_executions() renamed it between exists() and rename()
            print(f"⚠ Race detected: {os.path.basename(executing_file)} moved during completion")
            # Fall through to fallback search below
        else:
            _cleanup_pid_file(executing_file)
            print(f"✓ Task {status}: {completed_file}")
            return True

    # .executing.md is gone — recovery renamed it
    print(f"⚠ Executing file missing: {os.path.basename(executing_file)}")

    task_dir = os.path.dirname(executing_file)
    stem = os.path.basename(executing_file).replace('.executing.md', '')

    # Search for retry files that recovery created (e.g., stem.retry-2.md)
    for candidate in sorted(glob.glob(os.path.join(task_dir, f"{stem}*.md"))):
        basename = os.path.basename(candidate)
        if '.done.md' in basename or '.executing' in basename:
            continue
        completed_file = os.path.join(task_dir, stem + completed_suffix)
        os.rename(candidate, completed_file)
        _cleanup_pid_file(executing_file)
        print(f"⚠ Task {status} (fallback): {basename} → {os.path.basename(completed_file)}")
        return True

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


def _extract_task_id(content):
    """Extract task_id from task frontmatter."""
    import re
    match = re.search(r'^task_id:\s*(\S+)', content, re.MULTILINE)
    return match.group(1) if match else None


def _extract_skill_hint(content):
    """Extract skill_hint from task frontmatter."""
    import re
    match = re.search(r'^skill_hint:\s*(\S+)', content, re.MULTILINE)
    return match.group(1) if match else None


def _append_ledger(entry):
    """Append an event to the unified task-ledger.jsonl (flock-safe via kurultai_paths)."""
    _kp_append_ledger(entry)


def _extract_skills_from_transcript(agent_name: str, start_time: float, task_id: str, skill_hint) -> list:
    """
    Post-execution: find the Claude Code session transcript for this task,
    extract all Skill tool invocations, append SKILL_INVOCATION events to ledger.

    Transcript location: ~/.claude/projects/{encoded_cwd}/{session_id}.jsonl
    """
    agent_root = f"{AGENTS_DIR}/{agent_name}"
    encoded = agent_root.replace('/', '-').replace('.', '-').lstrip('-')
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
        for block in msg.get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == "Skill":
                skill_name = block.get("input", {}).get("skill", "")
                if not skill_name:
                    continue
                skill_full = f"/{skill_name}" if not skill_name.startswith("/") else skill_name
                _append_ledger({
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


def spawn_subagent(agent_name, task, subagent_task, depth=0):
    """Spawn a subagent for parallel work. Rejects if depth >= MAX_TASK_DEPTH."""
    if depth >= MAX_TASK_DEPTH:
        print(f"REJECT: depth={depth} >= {MAX_TASK_DEPTH} — preventing runaway chain")
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

    # Load agent-specific environment from .claude/settings.json
    # This provides ANTHROPIC_MODEL (and optionally ANTHROPIC_BASE_URL, ANTHROPIC_AUTH_TOKEN)
    VALID_CLAUDE_MODELS = {'claude-opus-4-6', 'claude-sonnet-4-6', 'claude-haiku-4-5-20251001'}
    ALLOWED_PROXY_ENDPOINTS = ['dashscope.aliyuncs.com', 'openrouter.ai', 'api.z.ai']
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
        is_using_proxy = any(endpoint in base_url for endpoint in ALLOWED_PROXY_ENDPOINTS)
        debug_msg = f"DEBUG: agent={agent_name}, env_model={env_model}, base_url={base_url[:50] if base_url else 'NONE'}..., is_using_proxy={is_using_proxy}\n"
        with open('/tmp/agent_handler_debug.log', 'a') as f:
            f.write(debug_msg)
        print(f"  {debug_msg.strip()}")
        if env_model and env_model not in VALID_CLAUDE_MODELS and not is_using_proxy:
            print(f"  ⚠ REJECTED non-Claude ANTHROPIC_MODEL env '{env_model}' for {agent_name} — forcing claude-opus-4-6")
            env['ANTHROPIC_MODEL'] = 'claude-opus-4-6'
        else:
            print(f"  ✓ ACCEPTED model '{env_model}' for {agent_name} (proxy={is_using_proxy})")
    except (FileNotFoundError, json.JSONDecodeError):
        pass  # Use system environment if no agent settings

    # Validate ANTHROPIC_BASE_URL — allow Anthropic and approved proxy endpoints
    base_url = env.get('ANTHROPIC_BASE_URL', '')
    allowed_proxy_endpoints = ['dashscope.aliyuncs.com', 'openrouter.ai', 'api.z.ai']
    is_allowed_proxy = any(endpoint in base_url for endpoint in allowed_proxy_endpoints)
    if base_url and 'anthropic.com' not in base_url and not is_allowed_proxy:
        print(f"  !! BLOCKED non-Anthropic BASE_URL for {agent_name}: {base_url}")
        print(f"  !! Removing ANTHROPIC_BASE_URL — will use official Anthropic API")
        env.pop('ANTHROPIC_BASE_URL', None)

    # Validate ANTHROPIC_AUTH_TOKEN — allow Anthropic and approved proxy tokens
    auth_token = env.get('ANTHROPIC_AUTH_TOKEN', '')
    # Anthropic tokens start with sk-ant-, but proxy services may use different prefixes
    is_anthropic_token = auth_token.startswith('sk-ant-')
    is_proxy_token = (base_url and is_allowed_proxy and
                      (auth_token.startswith('sk-') or 'api.z.ai' in base_url))
    if auth_token and not is_anthropic_token and not is_proxy_token:
        print(f"  !! BLOCKED non-Anthropic AUTH_TOKEN for {agent_name} (prefix: {auth_token[:6]}...)")
        env.pop('ANTHROPIC_AUTH_TOKEN', None)

    effective_timeout = timeout or CLAUDE_TIMEOUT

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

        stdout_chunks = []
        last_output_time = time.time()
        start = time.time()

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

            # Stall detection (T14): check after STALL_MIN_ELAPSED
            # Use relaxed thresholds for slow skills or high priority tasks
            is_slow = (skill_hint in SLOW_SKILLS if skill_hint else False) or agent_name == "kublai" or priority == 'high'
            if is_slow:
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
                    project_slug = agent_root.replace('/', '-').lstrip('-')
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
                print(f"  STALL_DETECTED: no stdout for {silence:.0f}s after {elapsed:.0f}s elapsed — aborting (skill_hint={skill_hint}, is_slow={is_slow}, thresh={stall_elapsed_thresh}/{stall_silence_thresh})")
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


def execute_task_with_llm(agent_name, task_text, config, skill_hint=None, timeout=None, model=None, priority='normal', task_id=None):
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
    """
    # Build prompt with agent context
    agent_root = f"{AGENTS_DIR}/{agent_name}"
    memory = _load_agent_memory(agent_name)
    memory_section = f"\n\n## Recent Context\n{memory}" if memory else ""
    skill_section = f"\n\nIMPORTANT: Start this task by invoking {skill_hint} — it is the correct skill for this work." if skill_hint else ""

    # Inject active behavioral rules from rules.json
    rules_section = ""
    try:
        from rule_registry import get_active_rules
        active_rules = get_active_rules(agent_name)
        if active_rules:
            rules_lines = "\n".join(f"  {i}. {r}" for i, r in enumerate(active_rules, 1))
            rules_section = f"\n\n## Active Behavioral Rules\nYou MUST follow these rules. Output 'RULES LOADED' at the start of your response.\n{rules_lines}"
    except Exception:
        pass  # Don't block task execution if rule loading fails

    prompt = (
        f"{task_text}"
        f"{memory_section}"
        f"{rules_section}"
        f"{skill_section}\n\n"
        "Execute this task completely using your tools. "
        "Read files, write code, run commands, verify your work. "
        "For simple questions, a direct answer is fine."
    )

    # Load ACP fallback configuration
    acp_fallback = load_acp_fallback_config()

    # First attempt with requested model
    result = _call_claude_code(agent_name, prompt, config, skill_hint, timeout, model, priority)

    # Check if we should retry with fallback model
    if not result.get('success') and acp_fallback['enabled']:
        error_msg = result.get('error', '')
        output_content = result.get('content', '')

        # Check for stall timeout (also trigger fallback if configured)
        is_stall = 'STALL_TIMEOUT' in error_msg or 'STALL_DETECTED' in error_msg
        is_rate_limit = _is_rate_limit_error(error_msg, output_content)

        should_fallback = False
        fallback_reason = None

        if is_rate_limit and acp_fallback['trigger_on_rate_limit']:
            should_fallback = True
            fallback_reason = "rate_limit_detected"
        elif is_stall and acp_fallback['trigger_on_stall']:
            should_fallback = True
            fallback_reason = "stall_timeout_detected"

        if should_fallback:
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
                    "error_preview": error_msg[:200],
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
                if acp_fallback['log_events']:
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
                        "error": result.get('error', 'Unknown error')[:500],  # Increased from 200
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

    # Load agent config
    config = load_agent_config(agent_name)

    # Route to appropriate executor based on config
    executor = config.get('executor', 'claude-code')
    skill_hint = task.get('skill_hint')
    priority = task.get('priority', 'normal')
    priority_timeout = TIMEOUT_BY_PRIORITY.get(priority, CLAUDE_TIMEOUT)
    skill_timeout = SLOW_SKILLS.get(skill_hint, 0)
    timeout = max(priority_timeout, skill_timeout)

    if executor == 'ollama':
        # Direct Ollama API call (no tools, text-only)
        print(f"  🤖 Executing via Ollama (direct API)... (timeout: {timeout}s)")
        start_time = time.time()
        result = execute_task_with_ollama(agent_name, task_content, config, timeout=timeout)
        elapsed_s = round(time.time() - start_time, 1)
        executor_name = "ollama"
    else:
        # Claude Code with full tool access
        print(f"  🤖 Executing via Claude Code...{f' (skill: {skill_hint})' if skill_hint else ''} (timeout: {timeout}s)")
        start_time = time.time()
        VALID_MODELS = {
            # Only Claude models are valid for Claude Code executor
            'claude-opus-4-6', 'claude-sonnet-4-6', 'claude-haiku-4-5-20251001',
        }
        PROXY_ENDPOINTS = ['dashscope.aliyuncs.com', 'openrouter.ai', 'api.z.ai']
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
        # Validate model - allow proxy models when using proxy
        if model and model not in VALID_MODELS and not is_using_proxy:
            print(f"  ⚠ REJECTED non-Claude model '{model}' from config — using claude-opus-4-6")
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
        # If using proxy with a proxy model, don't pass --model (let env var handle it)
        if is_using_proxy and model and model not in VALID_MODELS:
            print(f"  ✓ Using proxy model '{model}' via ANTHROPIC_MODEL env var")
            model = None  # Don't pass --model, let env var handle it
        selected_model = model or env_model or 'claude-opus-4-6'
        debug_msg = f"MODEL_SELECT: model={model}, selected_model={selected_model}, is_using_proxy={is_using_proxy}\n"
        with open('/tmp/agent_handler_debug.log', 'a') as f:
            f.write(debug_msg)
        print(f"  🔧 Model selection: config={config.get('model', '(none)')}, resolved={selected_model}, proxy={is_using_proxy}")
        result = execute_task_with_llm(agent_name, task_content, config, skill_hint=skill_hint, timeout=timeout, priority=priority, model=selected_model, task_id=task_id)
        elapsed_s = round(time.time() - start_time, 1)
        executor_name = "claude-code"

    # Extract skill invocations from Claude Code session transcript (only for claude-code)
    if task_id and executor == 'claude-code':
        _extract_skills_from_transcript(agent_name, start_time, task_id, skill_hint)

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
        _append_output_to_executing(executing_file, output_content, result.get('model', executor_name), elapsed_s, success=True)

        mark_task_completed(task['file'], 'completed', executing_file=executing_file)
        print(f"  ✓ Task completed via {executor_name} ({elapsed_s}s)")

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

        # Log model usage for tracking
        try:
            from model_tracker import get_tracker as get_model_tracker
            model_used = result.get('model', selected_model if 'selected_model' in dir() else executor_name)
            # Strip "(fallback)" suffix if present
            if isinstance(model_used, str):
                model_used = model_used.replace(" (fallback)", "").strip()
            get_model_tracker().log_model_usage(
                task_id=task_id,
                agent=agent_name,
                model=model_used,
                success=True,
                duration_seconds=elapsed_s,
            )
        except Exception as e:
            # Don't block task completion on model tracking failure
            print(f"  WARNING: Model tracking failed: {e}")

        return True
    else:
        error_msg = result.get('error', 'Unknown error')
        output_content = result.get('content', '') or result.get('error', '')
        print(f"  ✗ {executor_name} failed: {error_msg[:200]}")

        # CRITICAL: Append error output to .executing.md so task file has execution trace
        # This ensures the task file reflects what actually happened during execution
        _append_output_to_executing(executing_file, output_content[:10000], result.get('model', executor_name), elapsed_s, success=False)

        mark_task_completed(task['file'], 'failed', executing_file=executing_file)

        if task_id:
            # Categorize error and save full content before truncation
            error_type = categorize_error(error_msg, output_content)
            error_file = save_error_content(
                agent_name, task_id, error_msg, output_content, error_type
            )
            _append_ledger({
                "task_id": task_id,
                "event": "EXECUTION_DETAIL",
                "ts": datetime.now().isoformat(),
                "agent": agent_name,
                "execution_time_s": elapsed_s,
                "error": error_msg[:500],
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
                payload={"task_id": task_id, "error": error_msg[:200], "error_type": error_type},
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

        # Log model usage for tracking (failure case)
        try:
            from model_tracker import get_tracker as get_model_tracker
            model_used = result.get('model', selected_model if 'selected_model' in dir() else executor_name)
            # Strip "(fallback)" suffix if present
            if isinstance(model_used, str):
                model_used = model_used.replace(" (fallback)", "").strip()
            get_model_tracker().log_model_usage(
                task_id=task_id,
                agent=agent_name,
                model=model_used,
                success=False,
                duration_seconds=elapsed_s,
                error_type=error_type,
            )
        except Exception as e:
            # Don't block task completion on model tracking failure
            print(f"  WARNING: Model tracking failed: {e}")

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
    task_id = _extract_task_id(content)
    skill_hint = _extract_skill_hint(content)

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
