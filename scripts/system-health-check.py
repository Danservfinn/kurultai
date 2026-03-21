#!/usr/bin/env python3
"""
System Health Check — Unified 5-minute health monitoring

HEALTH CHECK HIERARCHY:
======================
┌─────────────────────────────────────────────────────────────────┐
│ system-health-check.py (this file)                              │
│   - Unified 5-minute health monitoring                          │
│   - Gateway health: PID check + HTTP endpoint (localhost:18789) │
│   - Service health: Neo4j + Redis                               │
│   - Website health: HTTP checks for key properties              │
│   - Lock cleanup: Calls stale-lock-cleanup.py                   │
├─────────────────────────────────────────────────────────────────┤
│ Related health scripts:                                         │
│   - gateway-health-check.py (specialized for gateway incidents) │
│   - health_dashboard.py (dashboard interface)                   │
│   - ogedei-watchdog.py (quality assurance daemon, 5-min)        │
│   - task-watcher.py (task execution daemon, continuous)         │
│   - kurultai-monitor.py (deep browser checks, 1-min)            │
├─────────────────────────────────────────────────────────────────┤
│ Deprecated:                                                     │
│   - heartbeat-watchdog (superseded by watchdog-gather.sh)       │
└─────────────────────────────────────────────────────────────────┘

Merges three health checks into one:
1. Gateway health: PID check + HTTP endpoint (localhost:18789)
2. Service health: Neo4j + Redis
3. Website health: HTTP checks for key properties
4. Lock cleanup: Calls stale-lock-cleanup.py

Single notification per cycle if ANY check fails; silent if all OK.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Configuration
BASE_DIR = Path.home() / ".openclaw" / "agents" / "main"
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "system-health.log"

# Service endpoints
GATEWAY_ENDPOINT = "http://127.0.0.1:18789/health"

# Websites to check (simplified HTTP checks - kurultai-monitor.py does deep browser checks)
# Note: llmsurvivor.kurult.ai custom domain is broken (Cloudflare DNS issue)
# Workaround: Use direct Railway URL until domain is fixed
# IMPORTANT: Use GET, not HEAD - FastAPI health endpoints return 405 for HEAD
# PAUSED 2026-03-09: LLM Survivor monitoring disabled per user request
WEBSITES = [
    ("https://the.kurult.ai", "the.kurult.ai"),
    ("https://www.parsethe.media", "parsethe.media"),  # www required - non-www returns 405 for HEAD
    # ("https://llm-survivor-production.up.railway.app/health", "llmsurvivor.kurult.ai"),  # PAUSED
]

# Thresholds
HTTP_TIMEOUT = 10
NEO4J_TIMEOUT = 3


def log(message: str, level: str = "INFO"):
    """Log a message with timestamp."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    log_line = f"[{timestamp}] [{level}] {message}"
    print(log_line)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(log_line + "\n")


def check_gateway() -> tuple[bool, str, dict]:
    """
    Check gateway health: PID + HTTP endpoint.

    Returns: (is_healthy, reason, metrics)
    """
    try:
        # Check for openclaw-gateway process
        result = subprocess.run(
            ["pgrep", "-x", "openclaw-gateway"],
            capture_output=True,
            text=True,
            timeout=2
        )
        pids = [p.strip() for p in result.stdout.strip().split("\n") if p.strip()]
        pid_count = len(pids)

        # Check health endpoint
        try:
            import requests
            response = requests.get(GATEWAY_ENDPOINT, timeout=HTTP_TIMEOUT)
            http_status = response.status_code
            latency_ms = round(response.elapsed.total_seconds() * 1000)
        except Exception:
            http_status = 0
            latency_ms = None

        metrics = {
            "pid_count": pid_count,
            "http_status": http_status,
            "latency_ms": latency_ms,
        }

        # Health logic: HTTP is the authoritative check; pgrep can transiently fail
        if pid_count == 0 and http_status != 200:
            return False, "No gateway process running and HTTP unreachable", metrics
        if pid_count == 0 and http_status == 200:
            # pgrep transient failure — gateway is actually running
            log("Gateway pgrep returned 0 PIDs but HTTP is healthy (transient pgrep miss)", "WARN")
            return True, "OK (pgrep miss, HTTP healthy)", metrics
        if http_status != 200:
            return False, f"Gateway HTTP {http_status}", metrics
        if pid_count > 1:
            return False, f"Gateway running {pid_count} instances (should be 1)", metrics

        return True, "OK", metrics

    except Exception as e:
        return False, f"Gateway check failed: {e}", {}


def check_neo4j() -> tuple[bool, str, dict]:
    """
    Check Neo4j connectivity.

    Returns: (is_healthy, reason, metrics)
    """
    try:
        from neo4j_task_tracker import neo4j_session, get_pool_metrics

        with neo4j_session() as session:
            session.run("RETURN 1").consume()
        metrics = get_pool_metrics()
        return True, "OK", {"status": "up", **metrics}
    except Exception as e:
        return False, str(e)[:100], {"status": "down"}


def check_redis() -> tuple[bool, str, dict]:
    """
    Check Redis connectivity.

    Returns: (is_healthy, reason, metrics)
    """
    try:
        result = subprocess.run(
            ["redis-cli", "ping"],
            capture_output=True,
            text=True,
            timeout=2
        )
        is_up = "PONG" in result.stdout
        if is_up:
            return True, "OK", {"status": "up"}
        return False, "Redis did not return PONG", {"status": "down"}
    except FileNotFoundError:
        return False, "redis-cli not found", {"status": "unknown"}
    except Exception as e:
        return False, str(e)[:100], {"status": "down"}


def check_websites() -> list[dict]:
    """
    Check website availability via HTTP GET.

    Note: Using GET instead of HEAD because:
    - FastAPI health endpoints return 405 for HEAD requests
    - Some servers (e.g., parsethe.media) don't support HEAD on root

    Returns: List of results for each site
    """
    results = []
    try:
        import requests
    except ImportError:
        log("requests module not available - skipping website checks", "WARN")
        return results

    for url, name in WEBSITES:
        try:
            response = requests.get(url, timeout=HTTP_TIMEOUT, allow_redirects=True)
            results.append({
                "name": name,
                "url": url,
                "status": response.status_code,
                "healthy": response.status_code == 200,
            })
        except requests.Timeout:
            results.append({
                "name": name,
                "url": url,
                "status": 0,
                "healthy": False,
                "error": "timeout",
            })
        except Exception as e:
            results.append({
                "name": name,
                "url": url,
                "status": 0,
                "healthy": False,
                "error": str(e)[:100],
            })

    return results


def cleanup_stale_locks() -> tuple[bool, str]:
    """
    Call stale-lock-cleanup.py as final step.

    Returns: (success, output_summary)
    """
    cleanup_script = BASE_DIR / "scripts" / "stale-lock-cleanup.py"

    if not cleanup_script.exists():
        return False, "stale-lock-cleanup.py not found"

    try:
        result = subprocess.run(
            [sys.executable, str(cleanup_script), "--json"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            # Parse JSON to get summary
            try:
                data = json.loads(result.stdout)
                total = data.get("total", {})
                return True, f"scanned={total.get('scanned', 0)}, stale_removed={total.get('stale_removed', 0)}"
            except json.JSONDecodeError:
                return True, "completed"
        else:
            return False, f"exit code {result.returncode}"

    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as e:
        return False, str(e)[:100]


def check_git_operations() -> tuple[bool, str, dict]:
    """
    Check git operations by autonomous agents.

    Returns: (is_healthy, reason, metrics)
    """
    git_monitor_script = BASE_DIR / "scripts" / "git-operation-monitor.py"

    if not git_monitor_script.exists():
        return True, "git-operation-monitor.py not found (skipping)", {"status": "unavailable"}

    try:
        result = subprocess.run(
            [sys.executable, str(git_monitor_script), "--metrics"],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode != 0:
            return False, f"git monitor failed: {result.returncode}", {"status": "error"}

        try:
            metrics = json.loads(result.stdout)
        except json.JSONDecodeError:
            return False, "invalid JSON from git monitor", {"status": "parse_error"}

        # Check for anomalies
        anomaly_count = metrics.get("anomaly_count", 0)
        stale_branches = metrics.get("autonomous_branches_stale", 0)
        blocked_ops = metrics.get("blocked_operations_24h", 0)

        issues = []
        if anomaly_count > 0:
            issues.append(f"{anomaly_count} anomalies")
        if stale_branches > 0:
            issues.append(f"{stale_branches} stale branches")
        if blocked_ops > 0:
            issues.append(f"{blocked_ops} blocked ops")

        if issues:
            return False, ", ".join(issues), metrics

        return True, "OK", {
            "commits_24h": metrics.get("autonomous_commits_24h", 0),
            "branches_active": metrics.get("autonomous_branches_active", 0),
            "prs_open": metrics.get("autonomous_prs_open", 0),
            "status": "healthy",
        }

    except subprocess.TimeoutExpired:
        return False, "timeout", {"status": "timeout"}
    except Exception as e:
        return False, str(e)[:100], {"status": "error"}


def create_notification(issues: list[str], severity: str = "MEDIUM"):
    """
    Create a task for Ogedei if there are health issues.
    Uses task_intake.py if available.

    CIRCULAR CASCADE PREVENTION (2026-03-12): If ogedei is already failing,
    route to jochi instead to break the circular failure cascade.
    """
    task_intake = BASE_DIR / "scripts" / "task_intake.py"

    if not task_intake.exists():
        log("task_intake.py not found - skipping notification", "WARN")
        return False

    # CIRCULAR CASCADE PREVENTION: Check if ogedei is failing
    _OGEDEI_FAILURE_THRESHOLD = 0.5
    _target_agent = "ogedei"
    _watchdog_state = LOG_DIR / "ogedei-watchdog-state.json"

    try:
        if _watchdog_state.exists():
            with open(_watchdog_state) as f:
                state = json.load(f)
            flags = state.get("agent_failure_flags", {})
            ogedei_failure = flags.get("ogedei", 0.0)
            if ogedei_failure >= _OGEDEI_FAILURE_THRESHOLD:
                log(f"CIRCULAR CASCADE PREVENTION: ogedei failure flag={ogedei_failure:.2f} >= {_OGEDEI_FAILURE_THRESHOLD}", "WARN")
                log(f"  Routing health alert to jochi instead of ogedei to break cascade", "WARN")
                _target_agent = "jochi"
    except Exception:
        pass  # Default to ogedei if state read fails

    body = "## System Health Check Failed\n\n**Issues Detected:**\n" + "\n".join(f"- {issue}" for issue in issues)
    body += f"\n\n**Severity:** {severity}\n**Time:** {datetime.now(timezone.utc).isoformat()}"

    try:
        cmd = [
            sys.executable,
            str(task_intake),
            "--title", f"System Health Alert ({len(issues)} issue{'s' if len(issues) > 1 else ''})",
            "--body", body,
            "--agent", _target_agent,
            "--priority", "high" if severity == "HIGH" else "normal",
            "--source", "system-health-check"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        # task_intake.py outputs text, check for "CREATED:" in output
        if result.returncode == 0 and "CREATED:" in result.stdout:
            log(f"Task created for {_target_agent}: {len(issues)} health issue(s)", "INFO")
            return True
        else:
            log(f"Failed to create task: returncode={result.returncode}", "ERROR")
            if result.stdout:
                log(f"stdout: {result.stdout[:500]}", "ERROR")
            if result.stderr:
                log(f"stderr: {result.stderr[:500]}", "ERROR")
            return False
    except subprocess.TimeoutExpired:
        log("Task creation timed out", "ERROR")
        return False
    except Exception as e:
        log(f"Exception creating task: {e}", "ERROR")
        return False


def main():
    """Main health check function."""
    log("=== System Health Check Started ===")

    all_healthy = True
    issues = []
    metrics = {}

    # 1. Gateway health
    gateway_healthy, gateway_reason, gateway_metrics = check_gateway()
    metrics["gateway"] = gateway_metrics
    if not gateway_healthy:
        all_healthy = False
        issues.append(f"Gateway: {gateway_reason}")
    log(f"Gateway: {'OK' if gateway_healthy else 'FAIL'} - {gateway_reason}")

    # 2. Neo4j health
    neo4j_healthy, neo4j_reason, neo4j_metrics = check_neo4j()
    metrics["neo4j"] = neo4j_metrics
    if not neo4j_healthy:
        all_healthy = False
        issues.append(f"Neo4j: {neo4j_reason}")
    log(f"Neo4j: {'OK' if neo4j_healthy else 'FAIL'} - {neo4j_reason}")

    # 3. Redis health
    redis_healthy, redis_reason, redis_metrics = check_redis()
    metrics["redis"] = redis_metrics
    if not redis_healthy:
        all_healthy = False
        issues.append(f"Redis: {redis_reason}")
    log(f"Redis: {'OK' if redis_healthy else 'FAIL'} - {redis_reason}")

    # 4. Website health
    website_results = check_websites()
    metrics["websites"] = website_results
    for site in website_results:
        if not site["healthy"]:
            all_healthy = False
            err = site.get("error", f"HTTP {site['status']}")
            issues.append(f"Website {site['name']}: {err}")
        log(f"Website {site['name']}: {'OK' if site['healthy'] else 'FAIL'}")

    # 5. Lock cleanup (always run, even if other checks failed)
    cleanup_ok, cleanup_summary = cleanup_stale_locks()
    metrics["lock_cleanup"] = {"success": cleanup_ok, "summary": cleanup_summary}
    log(f"Lock cleanup: {'OK' if cleanup_ok else 'FAIL'} - {cleanup_summary}")

    # 6. Git operation health
    git_healthy, git_reason, git_metrics = check_git_operations()
    metrics["git_operations"] = git_metrics
    if not git_healthy:
        all_healthy = False
        issues.append(f"Git: {git_reason}")
    log(f"Git operations: {'OK' if git_healthy else 'FAIL'} - {git_reason}")

    # Summary
    log(f"=== Summary: {'HEALTHY' if all_healthy else 'ISSUES DETECTED'} ===")

    if all_healthy:
        # Silent if all OK - just log and exit cleanly
        return 0
    else:
        # Single notification for all issues
        severity = "HIGH" if len(issues) >= 3 or "Gateway" in str(issues) else "MEDIUM"
        create_notification(issues, severity)
        return 1


if __name__ == "__main__":
    sys.exit(main())
