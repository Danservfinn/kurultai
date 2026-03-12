#!/Users/kublai/.openclaw/agents/main/monitor-venv/bin/python3
"""
Kurultai Website Browser-Based Uptime Monitor

Monitors https://the.kurult.ai using REAL BROWSER to detect:
- JavaScript console errors
- Rendering failures (page stuck on "Loading...")
- Network failures
- HTTP errors

This is CRITICAL because HTTP 200 with valid HTML does NOT mean the page works.
JavaScript syntax errors cause the page to hang forever with HTTP 200.

Run via cron every 5 minutes.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import sleep

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
except ImportError:
    print("ERROR: playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)

# Configuration
BASE_URL = "https://the.kurult.ai"
LOG_DIR = Path.home() / ".openclaw" / "logs"
LOG_FILE = LOG_DIR / "kurultai-monitor.log"
STATE_FILE = LOG_DIR / "kurultai-monitor-state.json"

# Thresholds
FAILURE_WARNING_THRESHOLD = 1  # After 1 consecutive failure (5 min) → create task for Ogedei (reduced from 3 for faster detection)
FAILURE_CRITICAL_THRESHOLD = 10  # After 10 consecutive failures (50 min) → escalate to Kublai

# Timeouts (seconds)
PAGE_LOAD_TIMEOUT = 15
RENDER_TIMEOUT = 10


def log(message: str, level: str = "INFO"):
    """Log a message with timestamp."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
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
    return {
        "consecutive_failures": 0,
        "last_failure": None,
        "last_success": None,
        "downtime_start": None
    }


def save_state(state: dict):
    """Save consecutive failure counter to state file."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def check_kurultai() -> tuple[bool, list[str], dict]:
    """
    Check the.kurult.ai using a real browser.

    Returns:
        (is_healthy, issues, metrics)
    """
    issues = []
    metrics = {
        "console_errors": [],
        "console_warnings": [],
        "http_status": None,
        "load_time_ms": None,
        "render_time_ms": None,
        "board_found": False,
        "stuck_on_loading": False
    }

    with sync_playwright() as p:
        console_errors = []
        console_warnings = []

        def console_handler(msg):
            """Capture console messages."""
            text = msg.text
            if msg.type == "error":
                console_errors.append(text)
            elif msg.type == "warning":
                console_warnings.append(text)

        try:
            # Launch browser
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            )
            page = context.new_page()

            # Attach console handler
            page.on("console", console_handler)

            # Navigation and page load
            load_start = datetime.now(timezone.utc)
            response = page.goto(
                BASE_URL,
                wait_until="domcontentloaded",
                timeout=PAGE_LOAD_TIMEOUT * 1000
            )

            if response:
                metrics["http_status"] = response.status
                load_time = (datetime.now(timezone.utc) - load_start).total_seconds() * 1000
                metrics["load_time_ms"] = round(load_time, 0)

                if response.status != 200:
                    issues.append(f"HTTP {response.status} - expected 200")

            # Wait for network idle (all requests finished)
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except PlaywrightTimeout:
                # Network idle timeout is not critical - some polling connections stay open
                pass

            # CRITICAL CHECK: Wait for actual board rendering
            # The page should NOT be stuck on "Loading..."
            render_start = datetime.now(timezone.utc)

            try:
                # Check if we're stuck on "Loading..." text
                page_content = page.content()
                has_loading_text = "Loading" in page_content and "board" not in page_content.lower()

                # Wait for actual board element to appear
                page.wait_for_selector(".board, [data-testid='board'], #board, main", timeout=RENDER_TIMEOUT * 1000)
                metrics["board_found"] = True
                render_time = (datetime.now(timezone.utc) - render_start).total_seconds() * 1000
                metrics["render_time_ms"] = round(render_time, 0)

            except PlaywrightTimeout:
                # Board didn't render - page is stuck
                metrics["stuck_on_loading"] = True
                issues.append("Page stuck on 'Loading...' - board did not render within 10s")

                # Check if "Loading" text is visible
                try:
                    body_text = page.evaluate("() => document.body.innerText")
                    if "Loading" in body_text:
                        metrics["stuck_on_loading"] = True
                except:
                    pass

            # Collect console errors
            metrics["console_errors"] = console_errors
            metrics["console_warnings"] = console_warnings

            # Filter out common benign errors (not actual site breakage)
            benign_patterns = [
                "Non-Error promise rejection",
                "chrome-extension://",
                "extension",
                "cloudflareinsights.com",
                "Content Security Policy",
                "CSP directive",
                "beacon.min.js",
                "404",  # Missing resources (favicons, tracking pixels) are not critical
                "Failed to load resource",  # Often benign 404s
            ]
            critical_errors = [
                e for e in console_errors
                if not any(pattern.lower() in e.lower() for pattern in benign_patterns)
            ]

            if critical_errors:
                issues.append(f"JavaScript console errors: {len(critical_errors)}")
                for error in critical_errors[:3]:  # Log first 3
                    issues.append(f"  - {error[:200]}")

            # Additional check: page title
            try:
                title = page.title()
                if not title or title == "":
                    issues.append("Page has no title")
            except:
                pass

            # Final check: body not empty
            try:
                body_html = page.evaluate("() => document.body.innerHTML")
                if len(body_html) < 100:
                    issues.append("Page body suspiciously empty")
            except:
                pass

            browser.close()

        except PlaywrightTimeout:
            issues.append(f"Page load timeout after {PAGE_LOAD_TIMEOUT}s")
            return False, issues, metrics

        except Exception as e:
            issues.append(f"Browser check failed: {e}")
            return False, issues, metrics

    is_healthy = len(issues) == 0
    return is_healthy, issues, metrics


def restart_cloudflared() -> bool:
    """Attempt to restart the cloudflared tunnel service.

    Returns True if restart was attempted, False otherwise.
    """
    log("HTTP 530 detected - attempting cloudflared tunnel restart", "WARN")

    try:
        # Try launchd kickstart first (preferred method)
        result = subprocess.run(
            ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/com.cloudflare.cloudflared"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            log("cloudflared restart triggered via launchctl kickstart", "INFO")
            return True
    except Exception as e:
        log(f"launchctl kickstart failed: {e}", "ERROR")

    # Fallback: unload and reload
    try:
        subprocess.run(
            ["launchctl", "bootout", f"gui/{os.getuid()}/com.cloudflare.cloudflared"],
            capture_output=True,
            timeout=5
        )
        sleep(2)
        subprocess.run(
            ["launchctl", "bootstrap", f"gui/{os.getuid()}", str(Path.home() / "Library/LaunchAgents/com.cloudflare.cloudflared.plist")],
            capture_output=True,
            timeout=5
        )
        log("cloudflared restart triggered via bootout/bootstrap", "INFO")
        return True
    except Exception as e:
        log(f"bootout/bootstrap restart failed: {e}", "ERROR")

    return False


def create_task(agent: str, priority: str, title: str, body: str) -> bool:
    """Create a task for an agent using task_intake.py.

    Returns True if task was created successfully, False otherwise.
    Includes fallback notification path.
    """
    task_intake = Path.home() / ".openclaw" / "agents" / "main" / "scripts" / "task_intake.py"

    # Fallback alert log - always write regardless of task creation success
    alert_log = LOG_DIR / "alerts.log"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    alert_entry = f"[{timestamp}] ALERT | agent={agent} priority={priority} title={title}\n{body}\n"

    try:
        with open(alert_log, "a") as f:
            f.write(alert_entry + "\n")
    except Exception as e:
        log(f"Failed to write to alert log: {e}", "ERROR")

    if not task_intake.exists():
        log(f"task_intake.py not found at {task_intake} - alert written to {alert_log}", "ERROR")
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
            log(f"Failed to create task: {result.stderr} - alert written to {alert_log}", "ERROR")
            return False
    except subprocess.TimeoutExpired:
        log(f"task_intake.py timed out - alert written to {alert_log}", "ERROR")
        return False
    except Exception as e:
        log(f"Exception creating task: {e} - alert written to {alert_log}", "ERROR")
        return False


def format_downtime(start_iso: str | None) -> str:
    """Calculate and format downtime duration."""
    if not start_iso:
        return "unknown"

    try:
        start = datetime.fromisoformat(start_iso)
        now = datetime.now(timezone.utc)
        duration = now - start
        minutes = int(duration.total_seconds() / 60)
        return f"{minutes} minutes"
    except:
        return "unknown"


def main():
    """Main monitoring function."""
    log("=== Kurultai Browser-Based Monitor Check Started ===")

    state = load_state()
    is_healthy, issues, metrics = check_kurultai()

    # Log metrics
    log(f"HTTP Status: {metrics.get('http_status', 'N/A')}")
    log(f"Load Time: {metrics.get('load_time_ms', 'N/A')}ms")
    log(f"Render Time: {metrics.get('render_time_ms', 'N/A')}ms")
    log(f"Board Found: {metrics.get('board_found', False)}")
    log(f"Console Errors: {len(metrics.get('console_errors', []))}")
    log(f"Console Warnings: {len(metrics.get('console_warnings', []))}")

    if is_healthy:
        # Recovery detection
        if state["consecutive_failures"] > 0:
            downtime = format_downtime(state.get("downtime_start"))
            log(f"✓ RECOVERY: Site back online after {downtime} downtime ({state['consecutive_failures']} checks)", "INFO")

            # Create recovery task
            recovery_body = f"""## the.kurult.ai Recovery Detected

The website has recovered after being down.

**Downtime:** {downtime}
**Consecutive Failures:** {state['consecutive_failures']}
**Downtime Started:** {state.get('downtime_start', 'unknown')}
**Recovered At:** {datetime.now(timezone.utc).isoformat()}

**Current Metrics:**
- HTTP Status: {metrics.get('http_status', 'N/A')}
- Load Time: {metrics.get('load_time_ms', 'N/A')}ms
- Render Time: {metrics.get('render_time_ms', 'N/A')}ms

Site is now healthy. No action required.
"""
            create_task("ogedei", "normal", f"the.kurult.ai recovered after {downtime} downtime", recovery_body)

            # Reset state
            state["consecutive_failures"] = 0
            state["last_success"] = datetime.now(timezone.utc).isoformat()
            state["downtime_start"] = None
            save_state(state)
        else:
            log("✓ All checks passed - site healthy")
            state["last_success"] = datetime.now(timezone.utc).isoformat()
            save_state(state)
    else:
        # Failure tracking
        state["consecutive_failures"] += 1

        # First failure - record downtime start
        if state["consecutive_failures"] == 1:
            state["downtime_start"] = datetime.now(timezone.utc).isoformat()

        state["last_failure"] = datetime.now(timezone.utc).isoformat()
        save_state(state)

        # SPECIAL HANDLING: HTTP 530 indicates Cloudflare Tunnel failure
        # This is critical - attempt immediate cloudflared restart
        if metrics.get("http_status") == 530:
            log("HTTP 530 detected - Cloudflare cannot reach origin (tunnel down)", "CRITICAL")

            # Attempt auto-restart
            if restart_cloudflared():
                # Wait for tunnel to come up
                sleep(3)
                log("cloudflared restart attempted - will verify on next check", "INFO")

            # Create immediate critical alert for HTTP 530
            downtime = format_downtime(state.get("downtime_start"))
            critical_body = f"""## CRITICAL: HTTP 530 - Cloudflare Tunnel Down

**HTTP 530** indicates Cloudflare cannot reach the origin server.
This means the **cloudflared tunnel daemon has stopped**.

**Downtime:** {downtime}
**Auto-restart attempted:** {datetime.now(timezone.utc).isoformat()}

**Immediate Action Required:**
1. Check if cloudflared process is running: `pgrep -fa cloudflared`
2. If not running, restart manually: `launchctl kickstart -k gui/$(id -u)/com.cloudflare.cloudflared`
3. Verify site recovery: `curl -I https://the.kurult.ai`

**Metrics:**
- HTTP Status: {metrics.get('http_status', 'N/A')}
- Consecutive Failures: {state['consecutive_failures']}
- Downtime Started: {state.get('downtime_start')}
"""
            create_task("ogedei", "high", f"CRITICAL: HTTP 530 - cloudflared tunnel down", critical_body)
            return  # Exit early after 530 handling - alert already created

        log(f"✗ Check failed (consecutive failures: {state['consecutive_failures']})", "ERROR")

        for issue in issues:
            log(f"  - {issue}", "ERROR")

        # Alerting logic
        if state["consecutive_failures"] >= FAILURE_CRITICAL_THRESHOLD:
            downtime = format_downtime(state.get("downtime_start"))
            log(f"CRITICAL ALERT: {state['consecutive_failures']} consecutive failures ({downtime} downtime) - escalating to Kublai", "CRITICAL")

            critical_body = f"""## CRITICAL: the.kurult.ai Down

The website has been failing browser-based health checks.

**Downtime:** {downtime}
**Consecutive Failures:** {state['consecutive_failures']}
**Downtime Started:** {state.get('downtime_start')}

**Issues Detected:**
""" + "\n".join(f"- {issue}" for issue in issues) + f"""

**Metrics:**
- HTTP Status: {metrics.get('http_status', 'N/A')}
- Load Time: {metrics.get('load_time_ms', 'N/A')}ms
- Board Rendered: {metrics.get('board_found', False)}
- Stuck on Loading: {metrics.get('stuck_on_loading', False)}
- Console Errors: {len(metrics.get('console_errors', []))}

**Last Successful Check:** {state.get('last_success', 'Never')}

**IMMEDIATE ACTION REQUIRED** - The primary UI is down or broken.
"""
            create_task("main", "high", f"CRITICAL: the.kurult.ai down for {downtime}", critical_body)

        elif state["consecutive_failures"] >= FAILURE_WARNING_THRESHOLD:
            downtime = format_downtime(state.get("downtime_start"))
            log(f"WARNING ALERT: {state['consecutive_failures']} consecutive failures ({downtime} downtime) - notifying Ogedei", "WARN")

            warning_body = f"""## the.kurult.ai Health Check Failed

The website has failed consecutive health checks.

**Downtime:** {downtime}
**Consecutive Failures:** {state['consecutive_failures']}
**Downtime Started:** {state.get('downtime_start')}

**Issues Detected:**
""" + "\n".join(f"- {issue}" for issue in issues) + f"""

**Metrics:**
- HTTP Status: {metrics.get('http_status', 'N/A')}
- Board Rendered: {metrics.get('board_found', False)}
- Stuck on Loading: {metrics.get('stuck_on_loading', False)}
- Console Errors: {len(metrics.get('console_errors', []))}

**Last Successful Check:** {state.get('last_success', 'Unknown')}

Please investigate and remediate.
"""
            create_task("ogedei", "high", f"the.kurult.ai failing health checks ({state['consecutive_failures']}x, {downtime})", warning_body)

    # Summary
    log(f"")
    log(f"=== SUMMARY ===")
    log(f"Status: {'HEALTHY' if is_healthy else 'UNHEALTHY'}")
    log(f"Consecutive Failures: {state['consecutive_failures']}")
    if state.get("downtime_start") and state["consecutive_failures"] > 0:
        log(f"Current Downtime: {format_downtime(state['downtime_start'])}")
    log(f"=== Kurultai Monitor Check Complete ===")
    log(f"")

    # Exit with error if unhealthy
    sys.exit(0 if is_healthy else 1)


if __name__ == "__main__":
    main()
