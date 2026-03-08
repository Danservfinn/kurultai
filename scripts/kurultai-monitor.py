#!/usr/bin/env python3
"""
Kurultai Website Uptime Monitor

Monitors https://the.kurult.ai for availability and correctness.
- HTTP GET → verify 200 status
- Check response contains expected HTML markers
- Verify API endpoints: /api/health, /api/tasks
- Optional: Validate JavaScript syntax

Run via cron every 5-10 minutes.
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests")
    sys.exit(1)

# Configuration
BASE_URL = "https://the.kurult.ai"
API_ENDPOINTS = ["/api/health", "/api/tasks"]
HTML_MARKERS = ['<div class="board">', "renderBoard", "<div id=\"app\">", "window.__INITIAL_STATE__"]
JS_MARKER = "<script"
LOG_DIR = Path.home() / ".openclaw" / "agents" / "main" / "logs"
LOG_FILE = LOG_DIR / "kurultai-monitor.log"
STATE_FILE = LOG_DIR / "kurultai-monitor-state.json"

# Thresholds
FAILURE_WARNING_THRESHOLD = 3  # After 3 consecutive failures → create task for Ogedei
FAILURE_CRITICAL_THRESHOLD = 10  # After 10 consecutive failures → escalate to Kublai

# Timeouts
HTTP_TIMEOUT = 10  # seconds
JS_VALIDATION_TIMEOUT = 5  # seconds


def log(message: str, level: str = "INFO"):
    """Log a message with timestamp."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] [{level}] {message}"
    print(log_line)

    # Append to log file
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(log_line + "\n")


def load_state() -> dict:
    """Load consecutive failure counter from state file."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"consecutive_failures": 0, "last_failure": None, "last_success": None}


def save_state(state: dict):
    """Save consecutive failure counter to state file."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def check_http_status(url: str) -> tuple[int, float, str]:
    """
    Check HTTP status of URL.
    Returns: (status_code, latency_ms, error_message)
    """
    try:
        start = datetime.now(timezone.utc)
        response = requests.get(url, timeout=HTTP_TIMEOUT, allow_redirects=True)
        latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        return response.status_code, latency_ms, ""
    except requests.Timeout:
        return 0, 0, f"Timeout after {HTTP_TIMEOUT}s"
    except requests.ConnectionError as e:
        return 0, 0, f"Connection error: {e}"
    except requests.RequestException as e:
        return 0, 0, f"Request error: {e}"


def validate_html_content(html: str) -> tuple[bool, list[str]]:
    """
    Validate HTML contains expected markers.
    Returns: (is_valid, list of missing markers found)
    """
    found_markers = []
    missing_markers = []

    for marker in HTML_MARKERS:
        if marker.lower() in html.lower():
            found_markers.append(marker)
        else:
            missing_markers.append(marker)

    # Consider valid if at least one marker is found
    is_valid = len(found_markers) > 0
    return is_valid, missing_markers


def extract_and_validate_js(html: str) -> tuple[bool, str]:
    """
    Extract inline JavaScript from HTML and validate syntax.
    Returns: (is_valid, error_message)
    """
    # Find inline scripts
    script_pattern = re.compile(r'<script[^>]*>(.*?)</script>', re.DOTALL | re.IGNORECASE)
    scripts = script_pattern.findall(html)

    if not scripts:
        return True, ""  # No inline scripts to validate

    for i, script in enumerate(scripts):
        script = script.strip()
        if not script or script.startswith('{'):  # Skip JSON data or empty
            continue

        # Write to temp file and validate with node --check
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
                f.write(script)
                temp_path = f.name

            result = subprocess.run(
                ['node', '--check', temp_path],
                capture_output=True,
                text=True,
                timeout=JS_VALIDATION_TIMEOUT
            )

            os.unlink(temp_path)

            if result.returncode != 0:
                return False, f"JS syntax error in script {i}: {result.stderr[:200]}"
        except subprocess.TimeoutExpired:
            return False, f"JS validation timeout for script {i}"
        except FileNotFoundError:
            return True, ""  # Node not available, skip JS validation
        except Exception as e:
            return True, f"JS validation skip: {e}"

    return True, ""


def check_api_endpoint(base_url: str, endpoint: str) -> tuple[bool, int, str]:
    """
    Check API endpoint.
    Returns: (success, status_code, error_message)
    """
    url = f"{base_url}{endpoint}"
    try:
        start = datetime.now(timezone.utc)
        response = requests.get(url, timeout=HTTP_TIMEOUT)
        latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000

        if response.status_code == 200:
            return True, response.status_code, f"OK ({latency_ms:.0f}ms)"
        else:
            return False, response.status_code, f"Unexpected status: {response.status_code}"
    except requests.Timeout:
        return False, 0, f"Timeout after {HTTP_TIMEOUT}s"
    except requests.RequestException as e:
        return False, 0, str(e)


def create_task(agent: str, priority: str, title: str, body: str):
    """Create a task for an agent using task_intake.py."""
    task_intake = Path.home() / ".openclaw" / "agents" / "main" / "scripts" / "task_intake.py"

    if not task_intake.exists():
        log(f"task_intake.py not found at {task_intake}", "ERROR")
        return False

    try:
        cmd = [
            sys.executable, str(task_intake),
            "--title", title,
            "--body", body,
            "--agent", agent,
            "--priority", priority,
            "--source", "kurultai-monitor"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            log(f"Task created for {agent}: {title}", "INFO")
            return True
        else:
            log(f"Failed to create task: {result.stderr}", "ERROR")
            return False
    except subprocess.TimeoutExpired:
        log("task_intake.py timed out", "ERROR")
        return False
    except Exception as e:
        log(f"Exception creating task: {e}", "ERROR")
        return False


def main():
    """Main monitoring function."""
    log("=== Kurultai Monitor Check Started ===")

    state = load_state()
    issues_found = []
    checks_passed = 0
    checks_failed = 0

    # ============================================
    # CHECK 1: Main website HTTP status
    # ============================================
    log("CHECK 1: Main website HTTP status")
    status_code, latency_ms, error = check_http_status(BASE_URL)

    if status_code == 200:
        log(f"✓ Main site: HTTP {status_code} ({latency_ms:.0f}ms)")
        checks_passed += 1
        main_site_ok = True

        # Get HTML content for further checks
        try:
            response = requests.get(BASE_URL, timeout=HTTP_TIMEOUT)
            html_content = response.text
        except Exception as e:
            html_content = ""
            log(f"Failed to fetch HTML content: {e}", "WARN")
    else:
        log(f"✗ Main site: HTTP {status_code} - {error}", "ERROR")
        checks_failed += 1
        main_site_ok = False
        html_content = ""

    # ============================================
    # CHECK 2: HTML content validation
    # ============================================
    if main_site_ok and html_content:
        log("CHECK 2: HTML content validation")
        is_valid, missing = validate_html_content(html_content)

        if is_valid:
            log(f"✓ HTML markers found")
            checks_passed += 1
            html_valid = True
        else:
            log(f"✗ HTML markers missing: {missing}", "ERROR")
            checks_failed += 1
            html_valid = False
            issues_found.append(f"HTML markers missing: {missing}")

        # ============================================
        # CHECK 3: JavaScript syntax validation (optional)
        # ============================================
        log("CHECK 3: JavaScript syntax validation")
        js_valid, js_error = extract_and_validate_js(html_content)

        if js_valid:
            log(f"✓ JavaScript syntax valid")
            checks_passed += 1
        else:
            log(f"✗ JavaScript syntax error: {js_error}", "ERROR")
            checks_failed += 1
            issues_found.append(f"JS syntax error: {js_error}")
    else:
        html_valid = False
        js_valid = True  # Skip if main site down

    # ============================================
    # CHECK 4: API endpoints
    # ============================================
    log("CHECK 4: API endpoints")
    for endpoint in API_ENDPOINTS:
        success, status, message = check_api_endpoint(BASE_URL, endpoint)

        if success:
            log(f"✓ {endpoint}: {message}")
            checks_passed += 1
        else:
            log(f"✗ {endpoint}: HTTP {status} - {message}", "ERROR")
            checks_failed += 1
            issues_found.append(f"{endpoint}: {message}")

    # ============================================
    # Determine overall status
    # ============================================
    all_checks_passed = checks_failed == 0

    if all_checks_passed:
        # Recovery detection
        if state["consecutive_failures"] > 0:
            log(f"✓ RECOVERY: Site back online after {state['consecutive_failures']} failures", "INFO")
            state["consecutive_failures"] = 0
            state["last_success"] = datetime.now(timezone.utc).isoformat()
            save_state(state)
        else:
            log("✓ All checks passed - site healthy")
    else:
        # Failure tracking
        state["consecutive_failures"] += 1
        state["last_failure"] = datetime.now(timezone.utc).isoformat()
        save_state(state)

        log(f"✗ Check failed (consecutive failures: {state['consecutive_failures']})", "ERROR")

        # Alerting logic
        if state["consecutive_failures"] >= FAILURE_CRITICAL_THRESHOLD:
            log(f"CRITICAL ALERT: {state['consecutive_failures']} consecutive failures - escalating to Kublai", "CRITICAL")
            create_task(
                agent="main",
                priority="critical",
                title="CRITICAL: the.kurult.ai down for 50+ minutes",
                body=f"## the.kurult.ai Critical Alert\n\n"
                     f"The website has failed {state['consecutive_failures']} consecutive health checks.\n\n"
                     f"Issues detected:\n" + "\n".join(f"- {issue}" for issue in issues_found) + "\n\n"
                     f"Last successful check: {state.get('last_success', 'unknown')}\n\n"
                     f"Immediate action required. Site may be down or broken."
            )
        elif state["consecutive_failures"] >= FAILURE_WARNING_THRESHOLD:
            log(f"WARNING ALERT: {state['consecutive_failures']} consecutive failures - notifying Ogedei", "WARN")
            create_task(
                agent="ogedei",
                priority="high",
                title=f"the.kurult.ai failing health checks ({state['consecutive_failures']}x)",
                body=f"## the.kurult.ai Health Check Failed\n\n"
                     f"The website has failed {state['consecutive_failures']} consecutive health checks.\n\n"
                     f"Issues detected:\n" + "\n".join(f"- {issue}" for issue in issues_found) + "\n\n"
                     f"Last successful check: {state.get('last_success', 'unknown')}\n\n"
                     f"Please investigate and remediate."
            )

    # ============================================
    # Summary
    # ============================================
    log(f"")
    log(f"=== SUMMARY ===")
    log(f"Checks Passed: {checks_passed}")
    log(f"Checks Failed: {checks_failed}")
    log(f"Consecutive Failures: {state['consecutive_failures']}")

    if checks_failed > 0:
        log(f"Issues: {issues_found}")

    log(f"=== Kurultai Monitor Check Complete ===")

    # Exit with error if any checks failed
    sys.exit(0 if checks_failed == 0 else 1)


if __name__ == "__main__":
    main()
