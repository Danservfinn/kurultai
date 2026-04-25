#!/usr/bin/env python3
"""
Daily Progress Report — Query Neo4j and filesystem for goal progress.

Generates a concise summary of active goals with:
- Task completion stats (total/completed/in_progress/blocked)
- % complete calculation
- Blockers (>48h no progress)
- Deadline tracking
- Revenue metrics for Parse goal (MRR, paying users, conversion rate)

Output format:
📊 Daily Progress [Date] 

## Goal Name
- Progress: X% complete, Y days remaining
- ✅ Wins: [list]
- ⚠️ Blockers: [list]
- 📍 Next: [milestone]
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Paths
MAIN_DIR = Path("/Users/kublai/.openclaw/agents/main")
AGENTS_DIR = Path("/Users/kublai/.openclaw/agents")
TOCK_LATEST = MAIN_DIR / "logs" / "tock" / "latest.json"
MEMORY_FILE = MAIN_DIR / "CONTEXT.md"

# Goals configuration
GOALS = {
    "Parse": {
        "keywords": ["parse", "parsethe", "parse media", "parsethe.media"],
        "deadline": "2026-06-09",  # Day 90 from start
        "target_mrr": 1500,
    },
    "LLM Survivor": {
        "keywords": ["llm survivor", "llmsurvivor", "tribal", "llmsurvivor.kurult"],
        "deadline": "2026-04-12",  # Day 30
    },
    "Heartbeat Master": {
        "keywords": ["heartbeat", "heartbeats", "master", "daemon", "watchdog"],
        "deadline": None,  # Ongoing
    },
}


def read_tock_data():
    """Read latest tock data for system state."""
    if not TOCK_LATEST.exists():
        return {}
    
    try:
        with open(TOCK_LATEST) as f:
            return json.load(f)
    except:
        return {}


def scan_agent_tasks():
    """Scan filesystem for task files across all agents."""
    agents = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei", "tolui"]
    tasks = []
    
    for agent in agents:
        task_dir = AGENTS_DIR / agent / "tasks"
        if not task_dir.exists():
            continue
        
        for fpath in task_dir.glob("*.md"):
            # Skip archived
            if ".archived" in str(fpath):
                continue
            
            fname = fpath.name
            
            # Determine status from filename
            if ".failed" in fname:
                status = "FAILED"
            elif ".completed" in fname or ".done" in fname or ".resolved" in fname:
                status = "COMPLETED"
            elif ".executing" in fname and not any(x in fname for x in [".done", ".completed", ".resolved"]):
                status = "EXECUTING"
            else:
                status = "PENDING"
            
            # Read task content
            try:
                content = fpath.read_text(errors="replace")
                # Extract title
                title_match = re.search(r'^# Task:\s*(.+)$', content, re.MULTILINE)
                title = title_match.group(1).strip() if title_match else fname
                
                # Get timestamps from frontmatter
                created_match = re.search(r'^created:\s*(.+)$', content, re.MULTILINE)
                created = created_match.group(1).strip() if created_match else None
                
                tasks.append({
                    "agent": agent,
                    "status": status,
                    "title": title,
                    "created": created,
                    "file": fname,
                })
            except:
                tasks.append({
                    "agent": agent,
                    "status": status,
                    "title": fname,
                    "created": None,
                    "file": fname,
                })
    
    return tasks


def get_task_stats_for_goal(keywords, all_tasks, days=30):
    """Filter tasks by keywords and calculate statistics."""
    cutoff = datetime.now() - timedelta(days=days)
    
    matching = []
    for task in all_tasks:
        text = f"{task['title']} {task['file']}".lower()
        if any(kw.lower() in text for kw in keywords):
            matching.append(task)
    
    total = len(matching)
    completed = sum(1 for t in matching if t["status"] == "COMPLETED")
    in_progress = sum(1 for t in matching if t["status"] in ["EXECUTING", "PENDING"])
    failed = sum(1 for t in matching if t["status"] == "FAILED")
    
    # Recent wins (completed in last 7 days)
    seven_days_ago = datetime.now() - timedelta(days=7)
    wins = []
    for t in matching:
        if t["status"] == "COMPLETED" and t["created"]:
            try:
                created_dt = datetime.fromisoformat(t["created"].replace("Z", ""))
                if created_dt > seven_days_ago:
                    wins.append(t["title"][:60])
            except:
                pass
    wins = wins[:5]
    
    # Find stale tasks (no progress in >48h) - for now just show failed as blockers
    seen_blockers = set()
    blockers = []
    for t in matching:
        if t["status"] == "FAILED":
            key = t["title"][:50]
            if key not in seen_blockers:
                seen_blockers.add(key)
                blockers.append(f"{key} (failed)")
        elif t["status"] == "PENDING":
            if t["created"]:
                try:
                    created_dt = datetime.fromisoformat(t["created"].replace("Z", ""))
                    if created_dt < datetime.now() - timedelta(hours=48):
                        key = t["title"][:50]
                        if key not in seen_blockers:
                            seen_blockers.add(key)
                            blockers.append(f"{key} (stale)")
                except:
                    pass
    blockers = blockers[:3]
    
    return {
        "total": total,
        "completed": completed,
        "in_progress": in_progress,
        "failed": failed,
        "wins": wins,
        "blockers": blockers,
    }


def get_parse_revenue_metrics(tock_data):
    """Get Parse revenue metrics from tock or state files."""
    # Try tock data first
    if "parse_metrics" in tock_data:
        m = tock_data["parse_metrics"]
        return {
            "mrr": m.get("mrr", 0),
            "paying_users": m.get("paying_users", 0),
            "conversion_rate": m.get("conversion_rate", 0),
        }
    
    # Check shared-context
    metrics_path = MAIN_DIR / "shared-context" / "parse_metrics.json"
    if metrics_path.exists():
        try:
            with open(metrics_path) as f:
                m = json.load(f)
            return {
                "mrr": m.get("mrr", 0),
                "paying_users": m.get("paying_users", 0),
                "conversion_rate": m.get("conversion_rate", 0),
            }
        except:
            pass
    
    # Default
    return {"mrr": 0, "paying_users": 0, "conversion_rate": 0}


def calculate_progress(stats):
    """Calculate progress percentage from task stats."""
    if stats["total"] == 0:
        return 0
    
    weighted = stats["completed"] * 1.0 + stats["in_progress"] * 0.3
    return min(100, round(weighted / stats["total"] * 100))


def days_remaining(deadline):
    """Calculate days remaining until deadline."""
    if not deadline:
        return None
    
    try:
        deadline_dt = datetime.strptime(deadline, "%Y-%m-%d")
        delta = deadline_dt - datetime.now()
        return max(0, delta.days)
    except:
        return None


def read_context_goals():
    """Read active projects from CONTEXT.md."""
    if not MEMORY_FILE.exists():
        return []
    
    try:
        content = MEMORY_FILE.read_text()
        # Extract Active Projects section
        match = re.search(r'## Active Projects\s*\n(.*?)(?=\n##|\Z)', content, re.DOTALL)
        if match:
            section = match.group(1).strip()
            projects = []
            for line in section.split('\n'):
                line = line.strip()
                if line.startswith('- **'):
                    # Extract project name
                    proj_match = re.search(r'\*\*(.+?):\*\*', line)
                    if proj_match:
                        projects.append(proj_match.group(1))
            return projects
    except:
        pass
    
    return []


def generate_report():
    """Generate the daily progress report."""
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [f"📊 Daily Progress {today}", ""]
    
    # Get data
    tock_data = read_tock_data()
    all_tasks = scan_agent_tasks()
    context_projects = read_context_goals()
    
    for goal_name, goal_config in GOALS.items():
        stats = get_task_stats_for_goal(goal_config["keywords"], all_tasks)
        progress = calculate_progress(stats)
        remaining = days_remaining(goal_config.get("deadline"))
        
        lines.append(f"## {goal_name}")
        
        if remaining is not None:
            lines.append(f"- Progress: {progress}% complete, {remaining} days remaining")
        else:
            lines.append(f"- Progress: {progress}% complete (ongoing)")
        
        # Add Parse revenue metrics
        if goal_name == "Parse":
            metrics = get_parse_revenue_metrics(tock_data)
            lines.append(f"- 💰 MRR: ${metrics['mrr']:,} | Users: {metrics['paying_users']} | Conv: {metrics['conversion_rate']:.1f}%")
        
        # Task stats
        lines.append(f"- 📋 Tasks: {stats['completed']}/{stats['total']} completed, {stats['in_progress']} in progress, {stats['failed']} failed")
        
        # Wins
        if stats["wins"]:
            lines.append(f"- ✅ Wins: {', '.join(stats['wins'])}")
        else:
            lines.append(f"- ✅ Wins: None this week")
        
        # Blockers
        if stats["blockers"]:
            lines.append(f"- ⚠️ Blockers: {', '.join(stats['blockers'])}")
        else:
            lines.append(f"- ⚠️ Blockers: None")
        
        # Next milestone
        if progress < 100 and remaining is not None:
            if remaining < 7:
                lines.append(f"- 📍 Next: CRITICAL - deadline in {remaining} days")
            elif remaining < 14:
                lines.append(f"- 📍 Next: URGENT - accelerate progress ({remaining} days)")
            elif remaining < 30:
                lines.append(f"- 📍 Next: On track - maintain momentum")
            else:
                lines.append(f"- 📍 Next: Steady progress toward goal")
        elif progress >= 100:
            lines.append(f"- 📍 Next: Goal complete!")
        else:
            lines.append(f"- 📍 Next: Ongoing maintenance and improvement")
        
        lines.append("")
    
    # System summary from tock
    lines.append("---")
    cron = tock_data.get("cron", {})
    if cron:
        lines.append(f"System: {cron.get('healthy', 0)}/{cron.get('total_jobs', 0)} cron jobs healthy")
    
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} EST")
    
    return "\n".join(lines)


if __name__ == "__main__":
    report = generate_report()
    print(report)
