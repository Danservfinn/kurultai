#!/usr/bin/env python3
"""
Git Operation Monitor — Autonomous git operation tracking for the Kurultai.

Monitors:
1. Commits per hour (by agent)
2. Branches in `autonomous/*` namespace
3. PRs created by autonomous agents
4. Files modified per commit

Anomaly Detection:
- Sudden spike in commit rate (>5/hour)
- Large deletions (>100 files in single commit)
- Modifications to critical files (CLAUDE.md, config/)
- Commits during non-business hours (if unexpected)

Provides rollback automation when degradation detected.

Usage:
    python3 git-operation-monitor.py              # Full check
    python3 git-operation-monitor.py --metrics    # Output JSON metrics only
    python3 git-operation-monitor.py --rollback <commit_sha>  # Rollback specific commit
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Configuration
BASE_DIR = Path.home() / ".openclaw"
AGENTS_DIR = BASE_DIR / "agents"
LOGS_DIR = BASE_DIR / "logs"
METRICS_FILE = LOGS_DIR / "git-operation-metrics.json"

# Git configuration
REPO_ROOT = BASE_DIR

# Thresholds
COMMIT_SPIKE_THRESHOLD = 5          # commits per hour
LARGE_DELETION_THRESHOLD = 100      # files deleted in single commit
STALE_BRANCH_DAYS = 7               # days before branch is considered stale
CRITICAL_FILES = [
    "CLAUDE.md",
    "config/",
    ".claude/settings.json",
    "openclaw.json",
]

# Agent names that can make autonomous commits
AUTONOMOUS_AGENTS = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei"]


def log(msg: str, level: str = "INFO"):
    """Log message with timestamp."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOGS_DIR / "git-operation-monitor.log", "a") as f:
        f.write(line + "\n")


def run_git(args: list, cwd: Path = None) -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=cwd or REPO_ROOT
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -1, "", str(e)


def get_commits_by_hour(hours: int = 24) -> dict:
    """Get commit counts by author for the last N hours."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    rc, stdout, stderr = run_git([
        "log", "--all", f"--since={since}",
        "--format=%an", "--no-merges"
    ])

    if rc != 0:
        log(f"Failed to get commits: {stderr}", "ERROR")
        return {}

    authors = {}
    for line in stdout.strip().split("\n"):
        if not line:
            continue
        # Normalize agent names
        author = line.strip().lower()
        if author in AUTONOMOUS_AGENTS:
            authors[author] = authors.get(author, 0) + 1

    return authors


def get_autonomous_branches() -> list[dict]:
    """List all autonomous/* branches with age and status."""
    rc, stdout, stderr = run_git([
        "branch", "-a", "--format=%(refname:short)|%(committerdate:iso)|%(authorname)"
    ])

    if rc != 0:
        log(f"Failed to list branches: {stderr}", "ERROR")
        return []

    branches = []
    now = datetime.now(timezone.utc)
    stale_threshold = timedelta(days=STALE_BRANCH_DAYS)

    for line in stdout.strip().split("\n"):
        if not line or "autonomous" not in line.lower():
            continue

        parts = line.split("|")
        if len(parts) < 3:
            continue

        name = parts[0].strip()
        # Check if it's an autonomous branch
        if "autonomous" not in name.lower():
            continue

        try:
            commit_date = datetime.fromisoformat(parts[1].replace(" ", "T"))
            if commit_date.tzinfo is None:
                commit_date = commit_date.replace(tzinfo=timezone.utc)
        except (ValueError, IndexError):
            commit_date = now

        author = parts[2].strip() if len(parts) > 2 else "unknown"
        age_days = (now - commit_date).days
        is_stale = (now - commit_date) > stale_threshold

        branches.append({
            "name": name,
            "author": author,
            "last_commit": commit_date.isoformat(),
            "age_days": age_days,
            "stale": is_stale,
        })

    return branches


def get_autonomous_prs() -> list[dict]:
    """Get PRs created by autonomous agents (requires gh CLI)."""
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--state", "open", "--json", "number,title,author,createdAt,headRefName"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=REPO_ROOT
        )
        if result.returncode != 0:
            return []
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    try:
        prs = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    # Filter for autonomous branches/authors
    autonomous_prs = []
    for pr in prs:
        head_ref = pr.get("headRefName", "")
        author = pr.get("author", {})
        author_login = author.get("login", "").lower() if author else ""

        # Check if from autonomous branch or by autonomous agent
        is_autonomous = (
            "autonomous" in head_ref.lower() or
            any(agent in author_login for agent in AUTONOMOUS_AGENTS)
        )

        if is_autonomous:
            autonomous_prs.append({
                "number": pr.get("number"),
                "title": pr.get("title", "")[:80],
                "author": author_login,
                "created": pr.get("createdAt"),
                "branch": head_ref,
            })

    return autonomous_prs


def get_recent_commit_details(hours: int = 24) -> list[dict]:
    """Get details of recent commits including files modified."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    rc, stdout, stderr = run_git([
        "log", "--all", f"--since={since}",
        "--format=%H|%an|%ad|%s", "--date=iso", "--name-status"
    ])

    if rc != 0:
        return []

    commits = []
    current_commit = None

    for line in stdout.strip().split("\n"):
        if not line:
            continue

        if "|" in line and line.count("|") >= 3:
            # Commit header line
            if current_commit:
                commits.append(current_commit)

            parts = line.split("|")
            current_commit = {
                "sha": parts[0],
                "author": parts[1].lower(),
                "date": parts[2],
                "message": parts[3] if len(parts) > 3 else "",
                "files_added": 0,
                "files_modified": 0,
                "files_deleted": 0,
                "critical_files_touched": [],
            }
        elif current_commit and line.startswith(("A\t", "M\t", "D\t")):
            # File status line
            status, filepath = line.split("\t", 1)
            if status == "A":
                current_commit["files_added"] += 1
            elif status == "M":
                current_commit["files_modified"] += 1
            elif status == "D":
                current_commit["files_deleted"] += 1

            # Check for critical files
            for critical in CRITICAL_FILES:
                if filepath.startswith(critical) or filepath.endswith(critical):
                    current_commit["critical_files_touched"].append(filepath)

    if current_commit:
        commits.append(current_commit)

    return commits


def is_restorative_commit(commit: dict) -> bool:
    """Check if a commit is restorative (fixing previous issues) rather than destructive."""
    message_lower = commit.get("message", "").lower()

    # Keywords that indicate a restorative commit
    restorative_keywords = [
        "restore", "fix:", "revert", "recover", "rollback",
        "correct", "repair", "undo", "back to", "return to"
    ]

    # Check message for restorative keywords
    if any(keyword in message_lower for keyword in restorative_keywords):
        return True

    # Check if commit is restoring claude-opus-4-6 from alternative models
    if "claude-opus-4-6" in message_lower and any(x in message_lower for x in ["restore", "back", "return"]):
        return True

    return False


def is_destructive_model_change(commit: dict) -> bool:
    """Check if commit changes agents from claude models to non-anthropic models."""
    message_lower = commit.get("message", "").lower()

    # Signs of potentially destructive changes:
    # - Setting agents to glm-5, qwen, or other non-anthropic models
    # - WITHOUT restorative keywords
    if is_restorative_commit(commit):
        return False

    suspicious_patterns = [
        "set all agents to glm-5",
        "set all agents to qwen",
        "z.ai coding plan",
        "bailian",
    ]

    return any(pattern in message_lower for pattern in suspicious_patterns)


def was_issue_already_fixed(commit: dict, all_commits: list[dict]) -> bool:
    """Check if a problematic commit was already fixed by a later restorative commit.

    Args:
        commit: The potentially problematic commit to check
        all_commits: List of all commits in REVERSE chronological order (newest first)

    Returns:
        True if a later restorative commit addresses this issue
    """
    # Find the position of this commit in the list
    try:
        commit_idx = all_commits.index(commit)
    except ValueError:
        return False

    # Commits are in REVERSE chronological order (newest first).
    # So "later" restorative commits are BEFORE this commit in the list.
    # We only need to check commits with index < commit_idx.
    for later_commit in all_commits[:commit_idx]:
        if is_restorative_commit(later_commit):
            # Check if the restorative commit touches the same critical files
            # or if it's a general fix for model configuration
            message_lower = later_commit.get("message", "").lower()
            if ("restore" in message_lower and "claude-opus" in message_lower) or \
               ("fix" in message_lower and ("claude-opus" in message_lower or "misconfigured" in message_lower)):
                return True

    return False


def detect_anomalies(commits: list[dict], commit_counts: dict) -> list[dict]:
    """Detect anomalous patterns in git operations."""
    anomalies = []

    # Check for commit spikes
    for author, count in commit_counts.items():
        if count > COMMIT_SPIKE_THRESHOLD:
            anomalies.append({
                "type": "commit_spike",
                "severity": "high",
                "author": author,
                "count": count,
                "threshold": COMMIT_SPIKE_THRESHOLD,
                "message": f"{author} has {count} commits in last hour (threshold: {COMMIT_SPIKE_THRESHOLD})",
            })

    # Check for large deletions and critical file modifications
    for commit in commits:
        if commit["files_deleted"] > LARGE_DELETION_THRESHOLD:
            anomalies.append({
                "type": "large_deletion",
                "severity": "critical",
                "sha": commit["sha"],
                "author": commit["author"],
                "files_deleted": commit["files_deleted"],
                "threshold": LARGE_DELETION_THRESHOLD,
                "message": f"Commit {commit['sha'][:8]} deleted {commit['files_deleted']} files",
            })

        if commit["critical_files_touched"]:
            # Skip restorative commits - they're fixing problems, not causing them
            if is_restorative_commit(commit):
                continue

            # Skip if issue was already fixed by a later restorative commit
            if was_issue_already_fixed(commit, commits):
                continue

            # Flag potentially destructive model changes
            if is_destructive_model_change(commit):
                anomalies.append({
                    "type": "model_misconfiguration",
                    "severity": "high",
                    "sha": commit["sha"],
                    "author": commit["author"],
                    "files": commit["critical_files_touched"],
                    "message": f"Commit {commit['sha'][:8]} may have misconfigured agent models: {commit.get('message', '')[:60]}",
                })
            else:
                # Other critical file changes still get flagged
                anomalies.append({
                    "type": "critical_file_modification",
                    "severity": "high",
                    "sha": commit["sha"],
                    "author": commit["author"],
                    "files": commit["critical_files_touched"],
                    "message": f"Commit {commit['sha'][:8]} modified critical files: {', '.join(commit['critical_files_touched'][:3])}",
                })

    return anomalies


def check_direct_main_merges(hours: int = 24) -> list[dict]:
    """Check for unauthorized direct merges to main."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    rc, stdout, stderr = run_git([
        "log", "main", f"--since={since}",
        "--format=%H|%an|%s", "--merges"
    ])

    if rc != 0:
        return []

    unauthorized = []
    for line in stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|")
        if len(parts) >= 3:
            sha, author, message = parts[0], parts[1].lower(), parts[2]
            # Check if it's an autonomous agent
            if any(agent in author for agent in AUTONOMOUS_AGENTS):
                unauthorized.append({
                    "sha": sha,
                    "author": author,
                    "message": message[:80],
                    "type": "unauthorized_main_merge",
                })

    return unauthorized


def rollback_commit(commit_sha: str, dry_run: bool = False) -> tuple[bool, str]:
    """Rollback a specific commit using git revert."""
    if dry_run:
        log(f"DRY RUN: Would revert commit {commit_sha}")
        return True, f"Would revert {commit_sha}"

    # Create a revert commit
    rc, stdout, stderr = run_git(["revert", "--no-edit", commit_sha])

    if rc != 0:
        log(f"Failed to revert {commit_sha}: {stderr}", "ERROR")
        return False, f"Revert failed: {stderr}"

    log(f"Successfully reverted commit {commit_sha}")
    return True, f"Reverted {commit_sha}"


def auto_rollback_last_n(n: int = 1, author: str = None) -> list[dict]:
    """Auto-revert last N commits by an autonomous agent."""
    since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

    args = ["log", "--all", f"--since={since}", "--format=%H|%an", "--no-merges"]
    rc, stdout, stderr = run_git(args)

    if rc != 0:
        return []

    results = []
    reverted = 0

    for line in stdout.strip().split("\n"):
        if not line or reverted >= n:
            break

        parts = line.split("|")
        if len(parts) < 2:
            continue

        sha, commit_author = parts[0], parts[1].lower()

        # Filter by author if specified
        if author and author.lower() not in commit_author:
            continue

        # Only rollback autonomous agent commits
        if not any(a in commit_author for a in AUTONOMOUS_AGENTS):
            continue

        success, message = rollback_commit(sha)
        results.append({
            "sha": sha,
            "author": commit_author,
            "success": success,
            "message": message,
        })

        if success:
            reverted += 1

    return results


def store_metrics_neo4j(metrics: dict) -> bool:
    """Store metrics in Neo4j for trend analysis."""
    try:
        from neo4j_task_tracker import get_driver
        from datetime import datetime

        driver = get_driver()

        def parse_git_date(date_str: str) -> str:
            """Parse git date format to ISO format for Neo4j."""
            try:
                # Try parsing "2026-03-08 21:20:26 -0400" format
                dt = datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S")
                return dt.strftime("%Y-%m-%dT%H:%M:%S")
            except (ValueError, IndexError):
                # Fallback: return current time
                return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

        with driver.session() as session:
            # Create AutonomousCommit event nodes
            for commit in metrics.get("recent_commits", [])[:50]:
                iso_date = parse_git_date(commit.get("date", ""))
                session.run("""
                    MERGE (c:AutonomousCommit {sha: $sha})
                    SET c.author = $author,
                        c.date = datetime($date),
                        c.files_modified = $files_modified,
                        c.files_deleted = $files_deleted,
                        c.critical_files = $critical_files,
                        c.recorded_at = datetime()
                """, sha=commit["sha"], author=commit["author"],
                     date=iso_date, files_modified=commit["files_modified"],
                     files_deleted=commit["files_deleted"],
                     critical_files=commit["critical_files_touched"])

            # Create GitAnomaly event nodes
            for anomaly in metrics.get("anomalies", []):
                session.run("""
                    CREATE (a:GitAnomaly {
                        type: $type,
                        severity: $severity,
                        author: $author,
                        message: $message,
                        detected_at: datetime(),
                        sha: $sha
                    })
                """, type=anomaly.get("type", "unknown"),
                     severity=anomaly.get("severity", "unknown"),
                     author=anomaly.get("author", "unknown"),
                     message=anomaly.get("message", ""),
                     sha=anomaly.get("sha", ""))

        driver.close()
        return True
    except Exception as e:
        log(f"Failed to store metrics in Neo4j: {e}", "WARN")
        return False


def create_neo4j_schema() -> bool:
    """Create Neo4j indexes and constraints for git operation monitoring."""
    try:
        from neo4j_task_tracker import get_driver

        driver = get_driver()

        with driver.session() as session:
            # Create uniqueness constraint on sha first (replaces index if exists)
            # In Neo4j 5.x, constraints automatically create indexes
            try:
                session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (c:AutonomousCommit) REQUIRE c.sha IS UNIQUE")
            except Exception as constraint_err:
                # If constraint fails due to existing index, log and continue
                # The index already provides lookup capability
                if "IndexAlreadyExists" in str(constraint_err):
                    log("Index already exists for AutonomousCommit.sha, skipping constraint", "INFO")
                else:
                    log(f"Constraint creation note: {constraint_err}", "INFO")

            # Create indexes for AutonomousCommit nodes (non-unique properties)
            session.run("CREATE INDEX IF NOT EXISTS FOR (c:AutonomousCommit) ON (c.author)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (c:AutonomousCommit) ON (c.date)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (c:AutonomousCommit) ON (c.recorded_at)")

            # Create indexes for GitAnomaly nodes
            session.run("CREATE INDEX IF NOT EXISTS FOR (a:GitAnomaly) ON (a.type)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (a:GitAnomaly) ON (a.severity)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (a:GitAnomaly) ON (a.detected_at)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (a:GitAnomaly) ON (a.author)")

        driver.close()
        log("Neo4j schema created successfully")
        return True
    except Exception as e:
        log(f"Failed to create Neo4j schema: {e}", "ERROR")
        return False


def gather_metrics() -> dict:
    """Gather all git operation metrics."""
    now = datetime.now(timezone.utc)

    commits_24h = get_commits_by_hour(24)
    commits_1h = get_commits_by_hour(1)
    branches = get_autonomous_branches()
    prs = get_autonomous_prs()
    recent_commits = get_recent_commit_details(24)
    anomalies = detect_anomalies(recent_commits, commits_1h)
    unauthorized_merges = check_direct_main_merges(24)

    # Calculate aggregated metrics
    total_commits_24h = sum(commits_24h.values())
    total_commits_1h = sum(commits_1h.values())

    stale_branches = [b for b in branches if b["stale"]]

    metrics = {
        "timestamp": now.isoformat(),
        "autonomous_commits_24h": total_commits_24h,
        "autonomous_commits_1h": total_commits_1h,
        "commits_by_agent_24h": commits_24h,
        "commits_by_agent_1h": commits_1h,
        "autonomous_branches_active": len(branches),
        "autonomous_branches_stale": len(stale_branches),
        "branches": branches,
        "autonomous_prs_open": len(prs),
        "prs": prs,
        "recent_commits": recent_commits,
        "anomalies": anomalies,
        "anomaly_count": len(anomalies),
        "blocked_operations_24h": len(unauthorized_merges),
        "unauthorized_merges": unauthorized_merges,
        "failed_rollback_attempts_24h": 0,  # Tracked via state
    }

    return metrics


def save_metrics(metrics: dict):
    """Save metrics to JSON file."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(METRICS_FILE, "w") as f:
        json.dump(metrics, f, indent=2, default=str)


def create_alert_task(anomalies: list[dict]) -> bool:
    """Create a task for Kublai if there are critical anomalies."""
    if not anomalies:
        return False

    critical = [a for a in anomalies if a.get("severity") == "critical"]
    high = [a for a in anomalies if a.get("severity") == "high"]

    if not critical and not high:
        return False

    task_intake = AGENTS_DIR / "main" / "scripts" / "task_intake.py"
    if not task_intake.exists():
        return False

    severity = "critical" if critical else "high"
    body = f"""## Git Operation Anomaly Detected

**Severity:** {severity.upper()}

**Anomalies:**
"""
    for a in (critical + high)[:5]:
        body += f"- [{a.get('severity', 'unknown').upper()}] {a.get('message', 'Unknown issue')}\n"

    body += f"\n**Time:** {datetime.now(timezone.utc).isoformat()}\n"
    body += "\nReview and take corrective action if needed."

    try:
        result = subprocess.run(
            [sys.executable, str(task_intake),
             "--title", f"Git Anomaly Alert ({len(critical + high)} issue{'s' if len(critical + high) > 1 else ''})",
             "--body", body,
             "--agent", "kublai",
             "--priority", "critical" if critical else "high",
             "--source", "git-operation-monitor"],
            capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0 and "CREATED:" in result.stdout
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description="Git Operation Monitor")
    parser.add_argument("--metrics", action="store_true", help="Output JSON metrics only")
    parser.add_argument("--rollback", type=str, help="Rollback specific commit SHA")
    parser.add_argument("--auto-rollback", type=int, default=0, help="Auto-rollback last N commits")
    parser.add_argument("--author", type=str, help="Filter by author for rollback")
    parser.add_argument("--dry-run", action="store_true", help="Dry run for rollback")
    parser.add_argument("--check-stale", action="store_true", help="Check for stale branches")
    parser.add_argument("--create-schema", action="store_true", help="Create Neo4j schema for git monitoring")
    args = parser.parse_args()

    if args.create_schema:
        success = create_neo4j_schema()
        print(f"Schema creation: {'SUCCESS' if success else 'FAILED'}")
        return 0 if success else 1

    if args.rollback:
        success, message = rollback_commit(args.rollback, dry_run=args.dry_run)
        print(f"{'SUCCESS' if success else 'FAILED'}: {message}")
        return 0 if success else 1

    if args.auto_rollback > 0:
        results = auto_rollback_last_n(args.auto_rollback, args.author)
        for r in results:
            print(f"{'OK' if r['success'] else 'FAIL'}: {r['sha'][:8]} - {r['message']}")
        return 0 if all(r['success'] for r in results) else 1

    # Gather metrics
    metrics = gather_metrics()
    save_metrics(metrics)

    if args.metrics:
        print(json.dumps(metrics, indent=2, default=str))
        return 0

    # Regular output
    log(f"=== Git Operation Monitor ===")
    log(f"Commits 24h: {metrics['autonomous_commits_24h']} (1h: {metrics['autonomous_commits_1h']})")
    log(f"Autonomous branches: {metrics['autonomous_branches_active']} ({metrics['autonomous_branches_stale']} stale)")
    log(f"Open PRs: {metrics['autonomous_prs_open']}")
    log(f"Anomalies: {metrics['anomaly_count']}")

    if metrics['anomalies']:
        log(f"ANOMALIES DETECTED:", "WARN")
        for a in metrics['anomalies']:
            log(f"  [{a.get('severity', 'unknown').upper()}] {a.get('message', '')}", "WARN")
        create_alert_task(metrics['anomalies'])

    if args.check_stale and metrics['autonomous_branches_stale'] > 0:
        log(f"STALE BRANCHES:", "WARN")
        for b in metrics['branches']:
            if b['stale']:
                log(f"  {b['name']} - {b['age_days']} days old")

    # Store in Neo4j
    if store_metrics_neo4j(metrics):
        log("Metrics stored in Neo4j")

    return 0 if metrics['anomaly_count'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())