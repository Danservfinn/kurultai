#!/usr/bin/env python3
"""
Persistent Issue Tracker for Kurultai Reflection

Tracks critical issues across hourly reflections and escalates when unresolved for 3+ reports.

Usage:
    python3 scripts/persistent-issues.py list
    python3 scripts/persistent-issues.py add "Issue description" --agent temujin
    python3 scripts/persistent-issues.py update <id> --status resolved
    python3 scripts/persistent-issues.py check-escalations
"""
from __future__ import annotations

import json
import sys
import os
from datetime import datetime
from pathlib import Path

# Configuration
SCRIPT_DIR = Path(__file__).parent
LOGS_DIR = SCRIPT_DIR.parent / "logs"
PERSISTENT_ISSUES_FILE = LOGS_DIR / "persistent-issues.json"

def load_issues():
    """Load persistent issues from JSON file."""
    if not PERSISTENT_ISSUES_FILE.exists():
        return {"issues": [], "last_updated": None}
    
    with open(PERSISTENT_ISSUES_FILE, 'r') as f:
        return json.load(f)

def save_issues(data):
    """Save persistent issues to JSON file."""
    data["last_updated"] = datetime.now().isoformat()
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    with open(PERSISTENT_ISSUES_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def add_issue(description, responsible_agent="unknown"):
    """Add a new issue to tracking."""
    data = load_issues()
    
    # Check if issue already exists (similar description)
    for issue in data["issues"]:
        if issue["description"].lower() in description.lower() or description.lower() in issue["description"].lower():
            # Increment existing issue
            issue["report_count"] += 1
            issue["last_reported"] = datetime.now().isoformat()
            issue["escalation_required"] = issue["report_count"] >= 3
            print(f"Updated existing issue #{issue['id']} (report #{issue['report_count']})")
            if issue["escalation_required"]:
                print(f"  ⚠️  ESCALATION REQUIRED - Issue unresolved for {issue['report_count']} reports")
            save_issues(data)
            return issue["id"]
    
    # Create new issue
    issue_id = f"issue-{datetime.now().strftime('%Y%m%d-%H%M')}"
    new_issue = {
        "id": issue_id,
        "description": description,
        "first_reported": datetime.now().isoformat(),
        "last_reported": datetime.now().isoformat(),
        "report_count": 1,
        "status": "open",
        "responsible_agent": responsible_agent,
        "escalation_required": False
    }
    
    data["issues"].append(new_issue)
    save_issues(data)
    print(f"Created new issue #{issue_id}")
    return issue_id

def list_issues():
    """List all tracked issues."""
    data = load_issues()
    
    if not data["issues"]:
        print("No persistent issues tracked.")
        return
    
    print(f"Persistent Issues (last updated: {data['last_updated']})\n")
    print("=" * 80)
    
    for issue in sorted(data["issues"], key=lambda x: x["report_count"], reverse=True):
        status_icon = "⚠️ " if issue["escalation_required"] else ""
        if issue["status"] == "resolved":
            status_icon = "✅ "
        
        print(f"{status_icon}#{issue['id']}")
        print(f"   Description: {issue['description']}")
        print(f"   Reports: {issue['report_count']} | Status: {issue['status']}")
        print(f"   Agent: {issue['responsible_agent']}")
        print(f"   First: {issue['first_reported'][:16]} | Last: {issue['last_reported'][:16]}")
        print()

def check_escalations():
    """Check for issues requiring escalation (3+ reports)."""
    data = load_issues()
    escalations = [i for i in data["issues"] if i["escalation_required"] and i["status"] == "open"]
    
    if not escalations:
        print("No escalations required.")
        return []
    
    print(f"ESCALATIONS REQUIRED ({len(escalations)} issues):\n")
    for issue in escalations:
        print(f"⚠️  #{issue['id']} - {issue['description']}")
        print(f"    Reports: {issue['report_count']} | Agent: {issue['responsible_agent']}")
        print(f"    Action: Create CRITICAL task and block reflection until acknowledged\n")
    
    return escalations

def update_issue(issue_id, status=None, resolution=None):
    """Update an existing issue."""
    data = load_issues()
    
    for issue in data["issues"]:
        if issue["id"] == issue_id:
            if status:
                issue["status"] = status
            if resolution:
                issue["resolution"] = resolution
            save_issues(data)
            print(f"Updated issue #{issue_id}")
            return
    
    print(f"Issue #{issue_id} not found.")

def get_escalation_tasks():
    """Get list of tasks to create for escalated issues."""
    data = load_issues()
    tasks = []
    
    for issue in data["issues"]:
        if issue["escalation_required"] and issue["status"] == "open":
            tasks.append({
                "agent": issue["responsible_agent"],
                "priority": "critical",
                "description": f"ESCALATION: {issue['description']} (unresolved for {issue['report_count']} reports)",
                "issue_id": issue["id"]
            })
    
    return tasks

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "list":
        list_issues()
    
    elif command == "add":
        if len(sys.argv) < 3:
            print("Usage: add 'Issue description' --agent <agent_name>")
            sys.exit(1)
        description = sys.argv[2]
        agent = "unknown"
        if "--agent" in sys.argv:
            agent = sys.argv[sys.argv.index("--agent") + 1]
        add_issue(description, agent)
    
    elif command == "update":
        if len(sys.argv) < 4:
            print("Usage: update <issue_id> --status <status> [--resolution <text>]")
            sys.exit(1)
        issue_id = sys.argv[2]
        status = None
        resolution = None
        if "--status" in sys.argv:
            status = sys.argv[sys.argv.index("--status") + 1]
        if "--resolution" in sys.argv:
            resolution = sys.argv[sys.argv.index("--resolution") + 1]
        update_issue(issue_id, status, resolution)
    
    elif command == "check-escalations":
        check_escalations()
    
    elif command == "get-tasks":
        tasks = get_escalation_tasks()
        print(json.dumps(tasks, indent=2))
    
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)

if __name__ == "__main__":
    main()
