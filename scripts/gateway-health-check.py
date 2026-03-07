#!/usr/bin/env python3
"""
Gateway Health Check Script - Ogedei
Runs every 5 minutes to proactively monitor gateway health.
Creates incidents and triggers remediation when issues detected.
"""

import os
import sys
import json
import socket
import subprocess
import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Configuration
LOG_DIR = Path("/Users/kublai/.openclaw/logs")
INCIDENT_DIR = Path("/Users/kublai/.openclaw/logs/incidents")
WORKSPACE_DIR = Path("/Users/kublai/.openclaw/agents/ogedei/workspace")

GATEWAYS = [
    {
        "name": "main",
        "label": "ai.openclaw.gateway",
        "port": 18789,
        "log_file": "gateway.log"
    },
    {
        "name": "tolui",
        "label": "ai.openclaw.gateway.tolui",
        "port": 18792,
        "log_file": "gateway-tolui.log"
    }
]

ALERT_LOG = LOG_DIR / "gateway-health-alerts.jsonl"


class GatewayHealthChecker:
    def __init__(self):
        self.timestamp = datetime.datetime.now().isoformat()
        self.results = []
        self.alert_level = "OK"  # OK, WARNING, HIGH, CRITICAL

    def check_launchd_status(self, label: str) -> Tuple[bool, Optional[int], Optional[int]]:
        """Check if a launchd service is running. Returns (running, pid, exit_code)."""
        try:
            result = subprocess.run(
                ["launchctl", "list"],
                capture_output=True,
                text=True,
                timeout=5
            )
            for line in result.stdout.split("\n"):
                parts = line.strip().split("\t")
                if len(parts) >= 3 and parts[2] == label:
                    pid = int(parts[0]) if parts[0] != "-" else None
                    exit_code = int(parts[1]) if parts[1] != "-" else None
                    running = pid is not None and pid > 0
                    return running, pid, exit_code
            return False, None, None
        except Exception as e:
            return False, None, None

    def check_port_connectivity(self, port: int, timeout: int = 3) -> Tuple[bool, Optional[str]]:
        """Check if a port is accepting connections."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                result = sock.connect_ex(("127.0.0.1", port))
                if result == 0:
                    return True, None
                else:
                    return False, f"Connection failed with code {result}"
        except Exception as e:
            return False, str(e)

    def check_log_errors(self, log_file: str, lookback_minutes: int = 10) -> List[Dict]:
        """Check recent log entries for error patterns."""
        errors = []
        log_path = LOG_DIR / log_file

        if not log_path.exists():
            return [{"type": "missing_log", "message": f"Log file not found: {log_file}"}]

        try:
            # Get file stats
            stat = log_path.stat()
            file_modified = datetime.datetime.fromtimestamp(stat.st_mtime)
            minutes_since_update = (datetime.datetime.now() - file_modified).total_seconds() / 60

            if minutes_since_update > lookback_minutes:
                errors.append({
                    "type": "stale_log",
                    "message": f"Log not updated in {minutes_since_update:.1f} minutes"
                })

            # Check recent log entries for errors
            with open(log_path, 'r', errors='ignore') as f:
                # Read last 100 lines
                lines = f.readlines()[-100:]

                for line in lines:
                    line_lower = line.lower()
                    if any(pattern in line_lower for pattern in [
                        "error", "fatal", "crash", "exception",
                        "connection refused", "econnrefused", "etimedout"
                    ]):
                        # Skip common non-error patterns
                        if any(skip in line_lower for skip in [
                            "signalaccount - config file is in use",
                            "waiting...",
                            "health-monitor: restarting"
                        ]):
                            continue
                        errors.append({
                            "type": "log_error",
                            "message": line.strip()[:200]
                        })

            # Deduplicate errors
            seen = set()
            unique_errors = []
            for err in errors:
                key = err.get("message", "")[:50]
                if key not in seen:
                    seen.add(key)
                    unique_errors.append(err)

            return unique_errors[:5]  # Limit to 5 errors

        except Exception as e:
            return [{"type": "read_error", "message": str(e)}]

    def restart_gateway(self, label: str) -> Tuple[bool, str]:
        """Restart a gateway service via launchctl."""
        try:
            # Stop and start
            subprocess.run(
                ["launchctl", "stop", label],
                capture_output=True,
                timeout=10
            )
            subprocess.run(
                ["launchctl", "start", label],
                capture_output=True,
                timeout=10
            )

            # Wait a moment and check status
            import time
            time.sleep(2)
            running, pid, _ = self.check_launchd_status(label)

            if running:
                return True, f"Restarted successfully (PID: {pid})"
            else:
                return False, "Restart failed - service not running after start"

        except Exception as e:
            return False, f"Restart error: {str(e)}"

    def create_incident(self, gateway_name: str, issues: List[str], action_taken: str):
        """Log an incident to the incidents directory."""
        INCIDENT_DIR.mkdir(parents=True, exist_ok=True)

        incident_id = f"{gateway_name}-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        incident_file = INCIDENT_DIR / f"{incident_id}.json"

        incident = {
            "id": incident_id,
            "timestamp": self.timestamp,
            "gateway": gateway_name,
            "issues": issues,
            "action_taken": action_taken,
            "alert_level": self.alert_level
        }

        with open(incident_file, 'w') as f:
            json.dump(incident, f, indent=2)

        # Also append to alerts log
        with open(ALERT_LOG, 'a') as f:
            f.write(json.dumps({
                "timestamp": self.timestamp,
                "incident_id": incident_id,
                "gateway": gateway_name,
                "alert_level": self.alert_level,
                "issues_count": len(issues)
            }) + "\n")

        return incident_id

    def create_self_task(self, gateway_name: str, issues: List[str]):
        """Create a self-task for Ogedei to investigate."""
        try:
            task_file = WORKSPACE_DIR / f"gateway-alert-{gateway_name}-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.md"

            content = f"""---
agent: ogedei
priority: high
created: {self.timestamp}
task_type: self_wake
source: gateway-health-check
---

# Gateway Alert: {gateway_name}

**Detected Issues:**
{chr(10).join(f"- {issue}" for issue in issues)}

**Action Required:**
1. Verify gateway is responding on expected port
2. Check logs for root cause
3. Restart if necessary
4. Update incident status

**Checklist:**
- [ ] Gateway process confirmed running
- [ ] Port connectivity verified
- [ ] No critical errors in logs
- [ ] Service responding to requests
"""
            with open(task_file, 'w') as f:
                f.write(content)

            return str(task_file)
        except Exception as e:
            return None

    def check_all_gateways(self) -> Dict:
        """Run health checks on all configured gateways."""
        overall_status = "healthy"
        critical_gateways = []

        for gateway in GATEWAYS:
            result = {
                "name": gateway["name"],
                "timestamp": self.timestamp,
                "checks": {}
            }

            issues = []
            alert_for_this = "OK"

            # Check 1: launchd status
            running, pid, exit_code = self.check_launchd_status(gateway["label"])
            result["checks"]["launchd"] = {
                "running": running,
                "pid": pid,
                "exit_code": exit_code
            }

            if not running:
                issues.append(f"Not running via launchctl (last exit: {exit_code})")
                alert_for_this = "CRITICAL"

            # Check 2: port connectivity
            port_ok, port_error = self.check_port_connectivity(gateway["port"])
            result["checks"]["port"] = {
                "open": port_ok,
                "port": gateway["port"],
                "error": port_error
            }

            if not port_ok:
                issues.append(f"Port {gateway['port']} not accessible: {port_error}")
                if alert_for_this == "OK":
                    alert_for_this = "HIGH"

            # Check 3: log errors
            log_errors = self.check_log_errors(gateway["log_file"])
            result["checks"]["logs"] = {
                "errors_found": len(log_errors),
                "error_samples": log_errors[:3]
            }

            if log_errors:
                for err in log_errors:
                    issues.append(f"Log issue: {err.get('type', 'unknown')}")
                if alert_for_this == "OK":
                    alert_for_this = "WARNING"

            # Determine overall status for this gateway
            result["status"] = "healthy" if not issues else "degraded" if alert_for_this in ["WARNING", "HIGH"] else "critical"
            result["alert_level"] = alert_for_this
            result["issues"] = issues

            # Update global alert level
            if alert_for_this == "CRITICAL":
                self.alert_level = "CRITICAL"
                critical_gateways.append(gateway["name"])
                overall_status = "critical"
            elif alert_for_this == "HIGH" and self.alert_level not in ["CRITICAL"]:
                self.alert_level = "HIGH"
                if overall_status != "critical":
                    overall_status = "degraded"
            elif alert_for_this == "WARNING" and self.alert_level == "OK":
                self.alert_level = "WARNING"

            # Take action if critical
            action_taken = "none"
            if alert_for_this in ["CRITICAL", "HIGH"]:
                restarted, restart_msg = self.restart_gateway(gateway["label"])
                action_taken = f"restart_attempt: {'success' if restarted else 'failed'} - {restart_msg}"

                # Create incident
                incident_id = self.create_incident(gateway["name"], issues, action_taken)
                result["incident_id"] = incident_id
                result["action_taken"] = action_taken

                # Create self-task for follow-up
                task_file = self.create_self_task(gateway["name"], issues)
                result["self_task"] = task_file

            self.results.append(result)

        return {
            "timestamp": self.timestamp,
            "overall_status": overall_status,
            "alert_level": self.alert_level,
            "gateways_checked": len(GATEWAYS),
            "critical_gateways": critical_gateways,
            "results": self.results
        }

    def run(self) -> Dict:
        """Execute full health check cycle."""
        # Ensure directories exist
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        INCIDENT_DIR.mkdir(parents=True, exist_ok=True)
        WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

        # Run checks
        report = self.check_all_gateways()

        # Write structured log
        with open(ALERT_LOG, 'a') as f:
            f.write(json.dumps({
                "timestamp": self.timestamp,
                "check_type": "gateway_health",
                "alert_level": report["alert_level"],
                "overall_status": report["overall_status"],
                "gateways": len(GATEWAYS)
            }) + "\n")

        # Print summary to stdout (for cron logging)
        print(f"[{self.timestamp}] Gateway Health Check: {report['overall_status'].upper()}")
        for result in self.results:
            status_icon = "✓" if result["status"] == "healthy" else "✗"
            print(f"  {status_icon} {result['name']}: {result['status']} ({result['alert_level']})")
            if result.get("issues"):
                for issue in result["issues"][:2]:
                    print(f"      - {issue[:60]}...")

        return report


if __name__ == "__main__":
    checker = GatewayHealthChecker()
    report = checker.run()

    # Exit with non-zero if critical
    if report["alert_level"] == "CRITICAL":
        sys.exit(1)
    sys.exit(0)
