#!/usr/bin/env python3
"""
Storage Monitor — Disk space tracking and alerting for OpenClaw Kurultai

Monitors disk usage, tracks OpenClaw growth, and alerts Danny when storage
thresholds are reached. Runs weekly via cron or manually.

Usage:
    python3 storage_monitor.py               # Full check with alerts
    python3 storage_monitor.py --quiet       # No output unless alert
    python3 storage_monitor.py --json        # JSON output for dashboard
    python3 storage_monitor.py --suggest     # Show cleanup suggestions only

Author: Ögedei (Operations Guardian)
Created: 2026-03-08
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional


# =============================================================================
# CONFIGURATION
# =============================================================================

OPENCLAW_ROOT = Path.home() / ".openclaw"
OPENCLAW_AGENTS = OPENCLAW_ROOT / "agents"
OPENCLAW_LOGS = OPENCLAW_ROOT / "logs"
OPENCLAW_BACKUPS = OPENCLAW_ROOT / "backups"
STORAGE_STATE_PATH = OPENCLAW_ROOT / "storage-state.json"

# Thresholds (disk usage percentage)
THRESHOLD_WARNING = 0.70     # 70% - notify Danny
THRESHOLD_CRITICAL = 0.85    # 85% - urgent alert
THRESHOLD_EMERGENCY = 0.95   # 95% - immediate action

# Age thresholds for cleanup suggestions (days)
OLD_LOG_DAYS = 90
OLD_BACKUP_DAYS = 30
OLD_CONVERSATION_DAYS = 365

# Signal configuration
SIGNAL_RECIPIENT = "+15165643945"  # Danny's number
SIGNAL_CLI = "/opt/signal-cli-0.13.24/bin/signal-cli"


# =============================================================================
# UTILITIES
# =============================================================================

def run_command(cmd: List[str]) -> str:
    """Run a shell command and return stdout."""
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def get_disk_usage(path: str = "/") -> Dict[str, int]:
    """Get disk usage in bytes for a path.

    Uses 'df' command for macOS compatibility (APFS snapshot handling).
    The shutil.disk_usage() includes APFS snapshots which inflates 'used' space.
    """
    try:
        # Use df -k for consistent output (kilobytes)
        result = subprocess.run(
            ["df", "-k", path],
            capture_output=True,
            text=True,
            check=True
        )
        # Parse df output: /dev/disk3s1s1   473949200 31028132 442579520    7%   /
        lines = result.stdout.strip().split('\n')
        if len(lines) >= 2:
            parts = lines[1].split()
            # df output: Filesystem 1024-blocks Used Available Capacity ...
            # parts[0] = filesystem, parts[1] = total, parts[2] = used, parts[3] = available
            if len(parts) >= 4:
                total_kb = int(parts[1])
                used_kb = int(parts[2])
                avail_kb = int(parts[3])

            total = total_kb * 1024
            used = used_kb * 1024
            free = avail_kb * 1024

            # Calculate percent based on used vs (used + avail) not total
            # This matches what df shows for "Capacity"
            percent = used / (used + free) if (used + free) > 0 else 0

            return {
                "total": total,
                "used": used,
                "free": free,
                "percent": percent
            }
    except (subprocess.CalledProcessError, ValueError, IndexError):
        pass

    # Fallback to shutil if df parsing fails
    usage = shutil.disk_usage(path)
    return {
        "total": usage.total,
        "used": usage.used,
        "free": usage.free,
        "percent": usage.used / usage.total
    }


def get_directory_size(path: Path) -> int:
    """Get directory size in bytes."""
    if not path.exists():
        return 0
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for filename in filenames:
            filepath = Path(dirpath) / filename
            try:
                total += filepath.stat().st_size
            except (OSError, FileNotFoundError):
                pass
    return total


def format_bytes(bytes_size: int) -> str:
    """Format bytes to human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f}{unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f}PB"


def format_percent(value: float) -> str:
    """Format ratio as percentage."""
    return f"{value * 100:.0f}%"


# =============================================================================
# STORAGE STATE PERSISTENCE
# =============================================================================

def load_storage_state() -> Dict:
    """Load previous storage state for growth tracking."""
    if STORAGE_STATE_PATH.exists():
        try:
            with open(STORAGE_STATE_PATH, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {
        "history": [],
        "last_check": None,
        "baseline_size": None,
        "baseline_date": None
    }


def save_storage_state(state: Dict) -> None:
    """Save storage state for future growth tracking."""
    state["last_check"] = datetime.now().isoformat()
    with open(STORAGE_STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def add_history_entry(state: Dict, entry: Dict) -> None:
    """Add a history entry and keep last 90 days."""
    state["history"].append(entry)
    # Keep only last 90 days of history (approx 13 weekly entries)
    cutoff = datetime.now() - timedelta(days=90)
    state["history"] = [
        h for h in state["history"]
        if datetime.fromisoformat(h["date"]) > cutoff
    ]


# =============================================================================
# GROWTH TRACKING
# =============================================================================

def calculate_growth_rate(history: List[Dict]) -> float:
    """Calculate weekly growth rate in GB based on historical data."""
    if len(history) < 2:
        return 0.0

    # Sort by date
    sorted_history = sorted(history, key=lambda x: x["date"])

    # Calculate growth between oldest and newest entries
    oldest = sorted_history[0]
    newest = sorted_history[-1]

    oldest_date = datetime.fromisoformat(oldest["date"])
    newest_date = datetime.fromisoformat(newest["date"])
    weeks_diff = max(1, (newest_date - oldest_date).days / 7)

    size_diff_gb = newest["openclaw_size_gb"] - oldest["openclaw_size_gb"]
    return size_diff_gb / weeks_diff


def project_threshold_date(
    current_gb: float,
    total_gb: float,
    growth_rate_gb_per_week: float,
    threshold_percent: float
) -> Optional[str]:
    """Project when we'll hit a threshold based on growth rate."""
    if growth_rate_gb_per_week <= 0:
        return None

    target_gb = total_gb * threshold_percent
    remaining_gb = target_gb - current_gb

    if remaining_gb <= 0:
        return "Already exceeded"

    weeks_until = remaining_gb / growth_rate_gb_per_week
    target_date = datetime.now() + timedelta(weeks=weeks_until)
    return target_date.strftime("%Y-%m-%d")


# =============================================================================
# CLEANUP SUGGESTIONS
# =============================================================================

def find_old_files(directory: Path, days: int, pattern: str = "*") -> List[Path]:
    """Find files older than specified days in a directory."""
    if not directory.exists():
        return []

    cutoff = datetime.now() - timedelta(days=days)
    old_files = []

    for filepath in directory.rglob(pattern):
        if filepath.is_file():
            try:
                mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
                if mtime < cutoff:
                    old_files.append(filepath)
            except (OSError, FileNotFoundError):
                pass

    return old_files


def suggest_cleanup_actions() -> List[Dict]:
    """Generate cleanup suggestions based on old files."""
    suggestions = []

    # Old logs
    old_logs = find_old_files(OPENCLAW_LOGS, OLD_LOG_DAYS, "*.log*")
    if old_logs:
        total_size = sum(f.stat().st_size for f in old_logs if f.exists())
        suggestions.append({
            "category": "Old Logs",
            "description": f"Archive {len(old_logs)} log files older than {OLD_LOG_DAYS} days",
            "size_bytes": total_size,
            "size_formatted": format_bytes(total_size),
            "action": "compress",
            "target": str(OPENCLAW_LOGS / "*.old")
        })

    # Old backups (check for .tar.gz, .zip files)
    old_backups = []
    for ext in ["*.tar.gz", "*.tgz", "*.zip", "*.backup"]:
        old_backups.extend(find_old_files(OPENCLAW_BACKUPS, OLD_BACKUP_DAYS, ext))
    if old_backups:
        total_size = sum(f.stat().st_size for f in old_backups if f.exists())
        suggestions.append({
            "category": "Old Backups",
            "description": f"Archive {len(old_backups)} backups older than {OLD_BACKUP_DAYS} days",
            "size_bytes": total_size,
            "size_formatted": format_bytes(total_size),
            "action": "compress",
            "target": str(OPENCLAW_BACKUPS / "*.old")
        })

    # Conversation archives (if they exist)
    conversation_paths = [
        OPENCLAW_ROOT / "conversations",
        OPENCLAW_ROOT / "agents" / "main" / "conversations",
    ]
    for conv_path in conversation_paths:
        if conv_path.exists():
            old_convs = find_old_files(conv_path, OLD_CONVERSATION_DAYS, "*.json")
            if old_convs:
                total_size = sum(f.stat().st_size for f in old_convs if f.exists())
                suggestions.append({
                    "category": "Old Conversations",
                    "description": f"Archive {len(old_convs)} conversations older than {OLD_CONVERSATION_DAYS} days",
                    "size_bytes": total_size,
                    "size_formatted": format_bytes(total_size),
                    "action": "archive",
                    "target": str(conv_path)
                })

    # Check for duplicate/mirror data
    suggestions.extend(check_duplicate_data())

    return suggestions


def check_duplicate_data() -> List[Dict]:
    """Check for duplicate data patterns that can be cleaned."""
    suggestions = []

    # Check for archived tasks (may have duplicates in ledger)
    ledger_path = OPENCLAW_ROOT / "agents" / "main" / "ledger"
    if ledger_path.exists():
        # Count small JSON files (likely task ledgers)
        task_files = list(ledger_path.rglob("*.md"))
        if len(task_files) > 1000:
            suggestions.append({
                "category": "Task Ledger Cleanup",
                "description": f"{len(task_files)} task ledger entries - consider archiving completed tasks older than 6 months",
                "size_bytes": sum(f.stat().st_size for f in task_files[:100] if f.exists()) * (len(task_files) / 100),
                "size_formatted": "~" + format_bytes(sum(f.stat().st_size for f in task_files[:100] if f.exists()) * (len(task_files) / 100)),
                "action": "review",
                "target": str(ledger_path)
            })

    return suggestions


# =============================================================================
# ALERTING
# =============================================================================

def send_signal_message(message: str, priority: str = "normal") -> bool:
    """Send a message via Signal CLI."""
    # Add emoji based on priority
    emoji = {
        "critical": "🚨",
        "emergency": "⚠️",
        "normal": "💾",
        "info": "ℹ️"
    }

    formatted_msg = f"{emoji.get(priority, '')} {message}" if priority in emoji else message

    try:
        # Try Signal CLI first
        result = subprocess.run(
            [SIGNAL_CLI, "-u", SIGNAL_RECIPIENT, "send", SIGNAL_RECIPIENT, formatted_msg],
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # Fallback: try gateway Signal API
        try:
            import urllib.request
            import urllib.parse
            import json

            api_url = "http://localhost:18789/signal/send"
            data = json.dumps({
                "recipient": SIGNAL_RECIPIENT,
                "message": formatted_msg
            }).encode()

            req = urllib.request.Request(
                api_url,
                data=data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status == 200
        except Exception:
            return False


def generate_alert_message(
    disk_status: Dict,
    openclaw_status: Dict,
    growth_rate: float,
    threshold_level: str
) -> str:
    """Generate an appropriate alert message based on threshold level."""

    usage_gb = disk_status["used"] / (1024**3)
    total_gb = disk_status["total"] / (1024**3)
    free_gb = disk_status["free"] / (1024**3)
    percent = format_percent(disk_status["percent"])

    openclaw_gb = openclaw_status["size_gb"]
    growth_str = f"~{growth_rate:.2f}GB/week" if growth_rate > 0 else "Unknown"

    if threshold_level == "warning":
        warning_date = project_threshold_date(
            openclaw_gb, total_gb, growth_rate, THRESHOLD_CRITICAL
        )
        warning_str = f"\nProjected critical (85%): ~{warning_date}" if warning_date else ""

        return f"""Storage Alert — 70% Full

Current usage: {format_bytes(disk_status['used'])} of {format_bytes(disk_status['total'])} ({percent})
Free space: {format_bytes(disk_status['free'])}
OpenClaw usage: {format_bytes(openclaw_status['size_bytes'])}

Growth rate: {growth_str}{warning_str}

Recommendation: Consider purchasing 1-2TB external SSD
Estimated cost: $100-150

No immediate action needed, but plan ahead!"""

    elif threshold_level == "critical":
        emergency_date = project_threshold_date(
            openclaw_gb, total_gb, growth_rate, THRESHOLD_EMERGENCY
        )
        emergency_str = f"\nProjected emergency (95%): ~{emergency_date}" if emergency_date else ""

        # Get cleanup suggestions
        suggestions = suggest_cleanup_actions()
        cleanup_potential = sum(s.get("size_bytes", 0) for s in suggestions)
        cleanup_str = f"\n\nI can free up ~{format_bytes(cleanup_potential)} with cleanup actions." if cleanup_potential > 0 else ""

        return f"""Storage Alert — 85% Full

Current usage: {format_bytes(disk_status['used'])} of {format_bytes(disk_status['total'])} ({percent})
Free space: {format_bytes(disk_status['free'])}
OpenClaw usage: {format_bytes(openclaw_status['size_bytes'])}

Growth rate: {growth_str}{emergency_str}{cleanup_str}

ACTION NEEDED: Purchase external storage within 2-3 weeks
Recommended: 2TB external SSD (~$150)

Should I suggest specific cleanup actions?"""

    else:  # emergency
        suggestions = suggest_cleanup_actions()
        cleanup_lines = []
        for s in suggestions[:5]:
            cleanup_lines.append(f"- {s['description']}: {s['size_formatted']}")

        cleanup_str = "\n".join(cleanup_lines) if cleanup_lines else "No immediate cleanup suggestions"

        return f"""URGENT: Storage 95% Full

Current usage: {format_bytes(disk_status['used'])} of {format_bytes(disk_status['total'])} ({percent})
Free space: {format_bytes(disk_status['free'])}

IMMEDIATE ACTION REQUIRED:
1. Purchase external storage TODAY
2. Free up space with emergency cleanup

Cleanup options:
{cleanup_str}

Should I proceed with emergency cleanup?"""


# =============================================================================
# MAIN MONITORING FUNCTION
# =============================================================================

def check_storage_thresholds(
    quiet: bool = False,
    send_alerts: bool = True
) -> Dict:
    """Main function to check storage against thresholds."""

    # Get current disk usage
    disk = get_disk_usage("/")

    # Get OpenClaw directory breakdown
    openclaw_total = get_directory_size(OPENCLAW_ROOT)
    agents_size = get_directory_size(OPENCLAW_AGENTS)
    logs_size = get_directory_size(OPENCLAW_LOGS)
    backups_size = get_directory_size(OPENCLAW_BACKUPS)

    openclaw_status = {
        "size_bytes": openclaw_total,
        "size_gb": openclaw_total / (1024**3),
        "agents_bytes": agents_size,
        "logs_bytes": logs_size,
        "backups_bytes": backups_size,
        "breakdown": {
            "agents": format_bytes(agents_size),
            "logs": format_bytes(logs_size),
            "backups": format_bytes(backups_size)
        }
    }

    # Load state and calculate growth
    state = load_storage_state()

    # Initialize baseline if first run
    if state.get("baseline_size") is None:
        state["baseline_size"] = openclaw_status["size_gb"]
        state["baseline_date"] = datetime.now().isoformat()

    # Add current entry to history
    entry = {
        "date": datetime.now().isoformat(),
        "disk_used_gb": disk["used"] / (1024**3),
        "disk_percent": disk["percent"],
        "openclaw_size_gb": openclaw_status["size_gb"],
        "openclaw_breakdown": openclaw_status["breakdown"]
    }
    add_history_entry(state, entry)

    # Calculate growth rate
    growth_rate = calculate_growth_rate(state.get("history", []))

    # Determine threshold level
    threshold_level = None
    priority = "normal"

    if disk["percent"] >= THRESHOLD_EMERGENCY:
        threshold_level = "emergency"
        priority = "emergency"
    elif disk["percent"] >= THRESHOLD_CRITICAL:
        threshold_level = "critical"
        priority = "critical"
    elif disk["percent"] >= THRESHOLD_WARNING:
        threshold_level = "warning"
        priority = "normal"

    # Generate result
    result = {
        "timestamp": datetime.now().isoformat(),
        "disk": {
            "total_bytes": disk["total"],
            "used_bytes": disk["used"],
            "free_bytes": disk["free"],
            "total_gb": disk["total"] / (1024**3),
            "used_gb": disk["used"] / (1024**3),
            "free_gb": disk["free"] / (1024**3),
            "percent": disk["percent"],
            "percent_formatted": format_percent(disk["percent"])
        },
        "openclaw": openclaw_status,
        "growth_rate_gb_per_week": growth_rate,
        "threshold_level": threshold_level,
        "projections": {
            "warning_date": project_threshold_date(
                openclaw_status["size_gb"],
                disk["total"] / (1024**3),
                growth_rate,
                THRESHOLD_WARNING
            ),
            "critical_date": project_threshold_date(
                openclaw_status["size_gb"],
                disk["total"] / (1024**3),
                growth_rate,
                THRESHOLD_CRITICAL
            ),
            "emergency_date": project_threshold_date(
                openclaw_status["size_gb"],
                disk["total"] / (1024**3),
                growth_rate,
                THRESHOLD_EMERGENCY
            )
        },
        "cleanup_suggestions": []
    }

    # Add cleanup suggestions if near threshold
    if threshold_level:
        result["cleanup_suggestions"] = suggest_cleanup_actions()

    # Save state
    save_storage_state(state)

    # Output and alerting
    if not quiet:
        print(json.dumps(result, indent=2))

    if threshold_level and send_alerts:
        message = generate_alert_message(
            result["disk"],
            result["openclaw"],
            growth_rate,
            threshold_level
        )
        send_signal_message(message, priority)
        if not quiet:
            print(f"\n📢 Alert sent: {threshold_level.upper()}", file=sys.stderr)

    return result


# =============================================================================
# CLI ENTRYPOINT
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Storage Monitor — Disk space tracking and alerting"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress output unless alert triggered"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON (default for piping)"
    )
    parser.add_argument(
        "--no-alert",
        action="store_true",
        help="Don't send Signal alerts"
    )
    parser.add_argument(
        "--suggest",
        action="store_true",
        help="Show cleanup suggestions only"
    )

    args = parser.parse_args()

    if args.suggest:
        # Show cleanup suggestions only
        suggestions = suggest_cleanup_actions()
        print(f"Cleanup Suggestions ({datetime.now().strftime('%Y-%m-%d')}):")
        print(f"{'=' * 60}")
        for s in suggestions:
            print(f"\n{s['category']}:")
            print(f"  {s['description']}")
            print(f"  Size: {s['size_formatted']}")
            print(f"  Action: {s['action']}")
        return 0

    # Run main check
    result = check_storage_thresholds(
        quiet=args.quiet,
        send_alerts=not args.no_alert
    )

    # Exit code based on threshold
    if result["threshold_level"] == "emergency":
        return 3
    elif result["threshold_level"] == "critical":
        return 2
    elif result["threshold_level"] == "warning":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
