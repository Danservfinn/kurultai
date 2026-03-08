#!/usr/bin/env python3
"""
System Health Check — Unified 5-minute health monitoring

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
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "myStrongPassword123")

# Websites to check (simplified HTTP checks - kurultai-monitor.py does deep browser checks)
WEBSITES = [
    ("https://the.kurult.ai", "the.kurult.ai"),
    ("https://parsethe.media", "parsethe.media"),
    ("https://llmsurvivor.com", "llmsurvivor.com"),
]

# Thresholds
HTTP_TIMEOUT = 5
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

        # Health logic
        if pid_count == 0:
            return False, "No gateway process running", metrics
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
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
            connection_timeout=NEO4J_TIMEOUT,
            max_transaction_retry_time=NEO4J_TIMEOUT
        )
        driver.verify_connectivity()
        driver.close()
        return True, "OK", {"status": "up"}
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
    Check website availability via HTTP HEAD.

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
            response = requests.head(url, timeout=HTTP_TIMEOUT, allow_redirects=True)
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


def create_notification(issues: list[str], severity: str = "MEDIUM"):
    """
    Create a task for Ogedei if there are health issues.
    Uses task_intake.py if available.
    """
    task_intake = BASE_DIR / "scripts" / "task_intake.py"

    if not task_intake.exists():
        log("task_intake.py not found - skipping notification", "WARN")
        return False

    body = "## System Health Check Failed\n\n**Issues Detected:**\n" + "\n".join(f"- {issue}" for issue in issues)
    body += f"\n\n**Severity:** {severity}\n**Time:** {datetime.now(timezone.utc).isoformat()}"

    try:
        cmd = [
            sys.executable,
            str(task_intake),
            "--title", f"System Health Alert ({len(issues)} issue{'s' if len(issues) > 1 else ''})",
            "--body", body,
            "--agent", "ogedei",
            "--priority", "high" if severity == "HIGH" else "normal",
            "--source", "system-health-check"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        # task_intake.py outputs text, check for "CREATED:" in output
        if result.returncode == 0 and "CREATED:" in result.stdout:
            log(f"Task created for Ogedei: {len(issues)} health issue(s)", "INFO")
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
