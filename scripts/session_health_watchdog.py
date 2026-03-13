#!/usr/bin/env python3
"""
Session Health Watchdog — Proactively prevent session bloat causing SIGKILL.

PROBLEM (2026-03-12):
- Tasks failing with exit code -9 at exactly 14 seconds
- 226 accumulated session files in main/sessions (161MB)
- OS SIGKILL from memory pressure when Claude Code loads bloated sessions

SOLUTION:
- Archive old/unused sessions BEFORE they cause problems
- Pre-execution session size check
- Integration with hourly reflection

Usage:
    python3 session_health_watchdog.py [--agent AGENT] [--dry-run]
    python3 session_health_watchdog.py --check-agent AGENT

Run via cron or hourly_reflection.sh:
    Hourly: python3 ~/.openclaw/agents/main/scripts/session_health_watchdog.py
    Pre-task: python3 ... --check-agent temujin (returns exit 1 if unhealthy)
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta

AGENTS_DIR = Path.home() / ".openclaw" / "agents"
# Sessions older than this are archived (prevents context bloat)
SESSION_AGE_THRESHOLD_HOURS = 6
# Max session file size before forcing archive (prevents single-file bloat)
SESSION_SIZE_THRESHOLD_MB = 2
# Max total sessions before forcing cleanup (increased for drift-heavy agents)
MAX_SESSIONS_PER_AGENT = 50
# Max drift variants per base session before forcing archive (prevent drift accumulation)
MAX_DRIFT_VARIANTS = 10

def get_agent_sessions_dir(agent: str) -> Path:
    """Get the sessions directory for an agent."""
    return AGENTS_DIR / agent / "sessions"

def get_session_age_hours(session_file: Path) -> float:
    """Get session age in hours based on mtime."""
    try:
        mtime = session_file.stat().st_mtime
        now = datetime.now().timestamp()
        return (now - mtime) / 3600
    except OSError:
        return 999  # Very old if we can't read it

def get_session_size_mb(session_file: Path) -> float:
    """Get session size in MB."""
    try:
        return session_file.stat().st_size / (1024 * 1024)
    except OSError:
        return 0

def list_sessions(agent: str) -> list[Path]:
    """List all .jsonl* session files for an agent (including drift/stale/reset variants).

    Excludes already-archived files to prevent re-archiving loops that cause
    filename explosion ([Errno 63] File name too long).
    """
    sessions_dir = get_agent_sessions_dir(agent)
    if not sessions_dir.exists():
        return []
    # Match all .jsonl files including .jsonl.drift-*, .jsonl.stale-*, .jsonl.reset.*
    # but EXCLUDE already-archived files to prevent re-archiving loops
    return sorted(
        [f for f in sessions_dir.glob("*.jsonl*") if '.archived-' not in f.name],
        key=os.path.getmtime, reverse=True
    )

def archive_session(session_file: Path, reason: str, dry_run: bool = False) -> bool:
    """Archive a session file by renaming with timestamp and reason.

    Safety: strips any existing .archived-* suffixes to prevent filename explosion.
    """
    try:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        safe_reason = reason.replace(" ", "-")[:30]

        # Strip any existing .archived-* suffixes to prevent runaway filename growth
        import re
        base_name = re.sub(r'(\.archived-[^/]*)+$', '', session_file.name)
        archive_name = f"{base_name}.archived-{safe_reason}-{timestamp}"
        archive_path = session_file.parent / archive_name

        # Final safety check: filename must be under OS limit (255 bytes on macOS)
        if len(archive_name.encode('utf-8')) > 250:
            print(f"  SKIP archiving {session_file.name}: archive name would exceed OS limit", file=sys.stderr)
            return False

        if not dry_run:
            session_file.rename(archive_path)
        return True
    except OSError as e:
        print(f"  ERROR archiving {session_file}: {e}", file=sys.stderr)
        return False

def get_base_session_id(session_file: Path) -> str:
    """Extract base session ID from any .jsonl* filename.

    Examples:
        01234567-1234-1234-1234-0123456789ab.jsonl -> 01234567-1234-1234-1234-0123456789ab
        01234567-1234-1234-1234-0123456789ab.jsonl.drift-123 -> 01234567-1234-1234-1234-0123456789ab
        01234567-1234-1234-1234-0123456789ab.jsonl.stale-* -> 01234567-1234-1234-1234-0123456789ab
    """
    # Remove .jsonl suffix and any drift/stale/reset extensions
    name = session_file.name
    # Match UUID pattern at start of filename
    import re
    match = re.match(r'([0-9a-f-]{36})', name)
    return match.group(1) if match else name

def cleanup_drift_variants(sessions: list[Path], dry_run: bool = False) -> int:
    """Archive excessive drift/stale/reset variants for the same base session.

    Returns number of drift variants archived.
    """
    archived = 0
    # Group by base session ID (only for drift/stale files, skip already archived)
    from collections import defaultdict
    drift_groups = defaultdict(list)

    for session in sessions:
        # Skip already-archived files and files that no longer exist
        if '.archived-' in session.name or not session.exists():
            continue
        if any(suffix in session.name for suffix in ['.drift-', '.stale-', '.reset.']):
            base_id = get_base_session_id(session)
            drift_groups[base_id].append(session)

    # For each base session with too many variants, archive oldest ones
    for base_id, variants in drift_groups.items():
        if len(variants) > MAX_DRIFT_VARIANTS:
            # Sort by mtime (oldest first) - filter out files that may have been deleted
            existing_variants = [v for v in variants if v.exists()]
            if len(existing_variants) <= MAX_DRIFT_VARIANTS:
                continue
            sorted_variants = sorted(existing_variants, key=os.path.getmtime)
            # Keep newest MAX_DRIFT_VARIANTS, archive the rest
            to_archive = sorted_variants[:-MAX_DRIFT_VARIANTS]
            for variant in to_archive:
                if variant.exists() and archive_session(variant, f"excess-drifts-{len(variants)}", dry_run):
                    archived += 1

    return archived

def cleanup_agent_sessions(agent: str, dry_run: bool = False) -> dict:
    """Clean up old/large sessions for an agent.

    Returns summary dict with actions taken.
    """
    summary = {
        "agent": agent,
        "sessions_before": 0,
        "sessions_archived": 0,
        "space_freed_mb": 0,
        "reasons": [],
        "errors": []
    }

    sessions = list_sessions(agent)
    summary["sessions_before"] = len(sessions)

    if len(sessions) <= 1:
        # Always keep at least the current session
        return summary

    # Keep the most recent session (it's active)
    current_session = sessions[0] if sessions else None
    old_sessions = sessions[1:]

    for session_file in old_sessions:
        age_hours = get_session_age_hours(session_file)
        size_mb = get_session_size_mb(session_file)
        reason = None

        # Archive if too old
        if age_hours > SESSION_AGE_THRESHOLD_HOURS:
            reason = f"old-{age_hours:.0f}h"

        # Archive if too large (single session bloat)
        elif size_mb > SESSION_SIZE_THRESHOLD_MB:
            reason = f"large-{size_mb:.0f}MB"

        # Archive if too many sessions accumulated
        elif len(old_sessions) > MAX_SESSIONS_PER_AGENT:
            reason = f"count-{len(old_sessions)}"

        if reason:
            before_size = get_session_size_mb(session_file)
            if archive_session(session_file, reason, dry_run):
                summary["sessions_archived"] += 1
                summary["space_freed_mb"] += before_size
                summary["reasons"].append(f"{session_file.name}: {reason}")

    # Phase 2: Cleanup excessive drift variants (prevents drift accumulation)
    drift_archived = cleanup_drift_variants(sessions, dry_run)
    summary["sessions_archived"] += drift_archived

    return summary

def check_agent_health(agent: str) -> tuple[bool, str]:
    """Check if an agent's session directory is healthy.

    Returns (is_healthy, reason).
    Used as pre-flight check before task execution.

    Unhealthy conditions:
    - Current session > 5MB (context bloat imminent)
    - > 100 archived sessions (cleanup needed)
    """
    sessions = list_sessions(agent)
    if not sessions:
        return True, "no sessions"

    current = sessions[0]
    current_size_mb = get_session_size_mb(current)

    if current_size_mb > 5:
        return False, f"current session too large ({current_size_mb:.1f}MB)"

    # Count archived sessions (including .jsonl.archived-* patterns)
    archived_count = len(list(get_agent_sessions_dir(agent).glob("*.jsonl.archived-*")))
    if archived_count > 100:
        return False, f"too many archived sessions ({archived_count})"

    return True, "healthy"

def cleanup_all_agents(dry_run: bool = False) -> dict:
    """Clean up sessions for all agents."""
    agents = ["main", "temujin", "mongke", "chagatai", "jochi", "ogedei", "tolui", "kublai"]
    summary = {
        "timestamp": datetime.now().isoformat(),
        "dry_run": dry_run,
        "agents": {}
    }

    total_archived = 0
    total_freed_mb = 0

    for agent in agents:
        agent_summary = cleanup_agent_sessions(agent, dry_run)
        summary["agents"][agent] = agent_summary
        total_archived += agent_summary["sessions_archived"]
        total_freed_mb += agent_summary["space_freed_mb"]

    summary["total_sessions_archived"] = total_archived
    summary["total_space_freed_mb"] = round(total_freed_mb, 1)

    return summary

def main():
    parser = argparse.ArgumentParser(description="Session health watchdog")
    parser.add_argument("--agent", help="Specific agent to clean")
    parser.add_argument("--check-agent", help="Check agent health (exit code 1 if unhealthy)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    args = parser.parse_args()

    if args.check_agent:
        is_healthy, reason = check_agent_health(args.check_agent)
        print(f"{args.check_agent}: {reason}")
        sys.exit(0 if is_healthy else 1)

    if args.agent:
        summary = cleanup_agent_sessions(args.agent, args.dry_run)
        print(json.dumps(summary, indent=2))
    else:
        summary = cleanup_all_agents(args.dry_run)
        print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
