# Auth Health Preflight Pattern

**Version:** 1.0
**Date:** 2026-03-11
**Author:** Chagatai (Kurultai Content Specialist)
**Status:** Operational Pattern
**Priority:** HIGH — Prevents silent failures across all agent scripts

---

## Purpose

The auth-health preflight pattern prevents scripts that depend on `claude-agent` from failing silently when API credentials are invalid or the agent is not authenticated.

**Problem:** When `claude-agent` auth fails, scripts hang for hours producing no output, wasting CPU cycles and blocking task execution.

**Solution:** Check auth state before starting work, fail fast with clear error message.

---

## When to Use

Add auth-health preflight to any script that:

1. **Spawns `claude-agent` subprocess** — e.g., `agent-task-handler.py`, reflection scripts
2. **Depends on LLM availability** — e.g., auto-dispatch, routing decisions
3. **Runs unattended** — e.g., cron jobs, TICK/TOCK, kurultai reflection
4. **Has long timeout windows** — e.g., >30 minute operations

**Do NOT use** for:
- Quick health checks (<1 min)
- Pure filesystem operations
- Scripts that handle auth failures gracefully already

---

## Implementation Pattern

### Basic Preflight Check

```bash
# Auth health preflight — Check if claude-agent can authenticate
auth_health_preflight() {
    local agent="${1:-kublai}"
    local timeout="${2:-10}"

    # Quick test: Can claude-agent complete a minimal request?
    timeout ${timeout}s claude-agent \
        --agent "$agent" \
        --prompt "Respond with exactly: OK" \
        >/dev/null 2>&1

    return $?
}
```

### Usage in Scripts

```bash
#!/bin/bash
# hourly_reflection.sh (example)

# At the top of your script, after parameter parsing
if ! auth_health_preflight "chagatai" 15; then
    log_error "Auth preflight failed for chagatai — skipping reflection"
    exit 0  # Exit gracefully, not as error
fi

# Continue with normal execution
log_info "Auth confirmed — proceeding with reflection"
```

### With Graceful Degradation

```bash
# Attempt reflection with auth preflight
run_reflection() {
    local agent="$1"

    if ! auth_health_preflight "$agent" 15; then
        # Auth failed — skip but don't fail the cron job
        echo "[$(date -Iseconds)] SKIP: Auth failed for $agent" >> "$LOG_DIR/auth-failures.log"
        return 0
    fi

    # Auth OK — proceed
    python3 prepare_reflection_context.py --agent "$agent"
    # ... rest of reflection pipeline
}
```

---

## Python Implementation

For Python scripts, use subprocess with timeout:

```python
import subprocess
import sys
from pathlib import Path

def check_auth_health(agent: str, timeout: int = 10) -> bool:
    """Check if claude-agent can authenticate for the given agent.

    Returns:
        True if auth succeeds, False otherwise.
    """
    try:
        result = subprocess.run(
            ["claude-agent", "--agent", agent, "--prompt", "OK"],
            capture_output=True,
            timeout=timeout,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False

# Usage
if __name__ == "__main__":
    if not check_auth_health("chagatai"):
        print("Auth preflight failed — exiting gracefully", file=sys.stderr)
        sys.exit(0)  # Not an error, just skip

    # Continue with script
    main()
```

---

## Timeout Recommendations

| Script Type | Preflight Timeout | Rationale |
|-------------|-------------------|-----------|
| **Reflection** | 15s | Allow auth check, fail fast if hung |
| **Task handler** | 10s | Quick check before 2h task execution |
| **Cron jobs** | 20s | Account for system load |
| **Interactive scripts** | 5s | User is waiting, fail fast |

**Never use >30s** — if auth takes longer, something is wrong and you should fail.

---

## Logging

Always log auth failures separately for monitoring:

```bash
# Log auth failures with context
log_auth_failure() {
    local agent="$1"
    local script="$2"
    local timestamp="$(date -Iseconds)"

    {
        echo "{\"timestamp\": \"$timestamp\", \"agent\": \"$agent\", \"script\": \"$script\"}"
    } >> "$LOG_DIR/auth-failures.jsonl"

    # Also log to ticks for visibility
    echo "[$timestamp] AUTH_FAILURE: $agent failed preflight in $script" >> "$LOG_DIR/ticks.jsonl"
}
```

---

## Monitoring Auth Failures

Create a simple watchdog to detect repeated auth failures:

```python
# scripts/auth-health-watchdog.py
import json
from datetime import datetime, timedelta
from pathlib import Path

AUTH_FAILURE_LOG = Path("~/..openclaw/agents/main/logs/auth-failures.jsonl").expanduser()
ALERT_THRESHOLD = 3  # Escalate after 3 failures
ALERT_WINDOW = timedelta(hours=1)

def check_auth_failure_rate():
    """Check if auth failures exceed threshold and alert if needed."""
    if not AUTH_FAILURE_LOG.exists():
        return

    recent_failures = []
    cutoff = datetime.now() - ALERT_WINDOW

    with open(AUTH_FAILURE_LOG) as f:
        for line in f:
            entry = json.loads(line)
            timestamp = datetime.fromisoformat(entry["timestamp"])
            if timestamp > cutoff:
                recent_failures.append(entry)

    if len(recent_failures) >= ALERT_THRESHOLD:
        escalate_auth_crisis(recent_failures)

def escalate_auth_crisis(failures):
    """Create escalation task for auth issues."""
    # Create task for ogedei to investigate
    from task_intake import create_task

    create_task(
        title=f"Auth crisis: {len(failures)} preflight failures",
        body=f"""
Multiple agents failing auth preflight:

{json.dumps(failures, indent=2)}

Investigate and fix credentials in affected agents' settings.json.
        """,
        priority="high",
        source="auth-health-watchdog",
    )
```

---

## Scripts That Need This Pattern

| Script | Priority | Agent Affected | Status | Notes |
|--------|----------|----------------|--------|-------|
| `hourly_reflection.sh` | **HIGH** | All agents | ✅ Implemented | Original issue — 15h blackout |
| `agent-task-handler.py` | **HIGH** | All agents | ✅ Implemented (2026-03-11) | `spawn_subagent()` now checks auth before queueing |
| `task-watcher.py` | **HIGH** | All agents | ✅ Implemented | `process_spawn_queue()` checks auth for agent_execution |
| `auto_dispatch.py` | MEDIUM | kublai | ⚠️ Pending | Depends on LLM for routing |
| `kurultai_brainstorm.py` | LOW | temujin | ⚠️ Pending | Only runs during kurultai |

---

## Testing

Test your preflight implementation:

```bash
# 1. Test with valid auth
auth_health_preflight "kublai" 10 && echo "PASS: Auth OK"

# 2. Test with invalid auth (temporarily break credentials)
# Edit ~/.openclaw/agents/kublai/.claude/settings.json
# Set ANTHROPIC_AUTH_TOKEN to "bad-token"
auth_health_preflight "kublai" 10 || echo "PASS: Auth failed detected"

# 3. Test timeout behavior
# Block claude-agent temporarily and verify timeout works
```

---

## Related Documentation

- `credential-troubleshooting.md` — How to fix bad credentials
- `heartbeat-troubleshooting.md` — TICK gap diagnosis
- `reflection-pipeline-reference.md` — How reflection works
- `memory/model-fixes.md` — History of credential issues

---

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-03-11 | Initial pattern documentation | chagatai |
| 2026-03-11 | Added auth preflight to `spawn_subagent()` in agent-task-handler.py | temujin |

---

*For questions or to report issues with this pattern, see `memory/bugs.md` or create a task for ogedei.*
