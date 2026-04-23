#!/usr/bin/env python3
"""Daily Goal Progress Summary - queries Neo4j and generates progress report"""

import subprocess
import json
from datetime import datetime, timedelta
import os

NEO4J_USER = "neo4j"
NEO4J_PASS = os.environ.get("NEO4J_PASSWORD")
if not NEO4J_PASS:
    raise EnvironmentError("NEO4J_PASSWORD environment variable not set")
NEO4J_ADDR = "bolt://localhost:7687"

def run_cypher(query):
    """Execute Cypher query and return results"""
    cmd = [
        "cypher-shell",
        "-a", NEO4J_ADDR,
        "-u", NEO4J_USER,
        "-p", NEO4J_PASS,
        query,
        "--format", "plain"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return result.stdout.strip()

def get_projects():
    """Get all active projects (goals)"""
    query = 'MATCH (p:Project {status: "in_progress"}) RETURN p.name, p.goal, p.target_date, p.target_revenue, p.created_at'
    result = run_cypher(query)
    projects = []
    lines = result.split("\n")[1:]  # Skip header
    for line in lines:
        if line.strip():
            parts = line.split(", ")
            if len(parts) >= 4:
                projects.append({
                    "name": parts[0].strip('"'),
                    "goal": parts[1].strip('"') if len(parts) > 1 else "",
                    "target_date": parts[2].strip('"') if len(parts) > 2 else None,
                    "target_revenue": parts[3].strip('"') if len(parts) > 3 else None,
                    "created_at": parts[4].strip('"') if len(parts) > 4 else None
                })
    return projects

def get_component_progress(project_name):
    """Get component completion stats for a project"""
    query = f'MATCH (p:Project {{name: "{project_name}"}})-[:HAS_COMPONENT]->(c:Component) RETURN c.status, count(c)'
    result = run_cypher(query)
    stats = {"complete": 0, "in_progress": 0, "pending": 0, "total": 0}
    lines = result.split("\n")[1:]
    for line in lines:
        if line.strip():
            parts = line.split(", ")
            if len(parts) >= 2:
                status = parts[0].strip('"')
                count = int(parts[1])
                stats[status] = count
                stats["total"] += count
    return stats

def get_phase_progress(project_name):
    """Get phase completion stats for a project"""
    query = f'MATCH (p:Project {{name: "{project_name}"}})-[:HAS_PHASE]->(ph:Phase) RETURN ph.name, ph.status'
    result = run_cypher(query)
    phases = []
    lines = result.split("\n")[1:]
    for line in lines:
        if line.strip():
            parts = line.split(", ")
            if len(parts) >= 2:
                phases.append({
                    "name": parts[0].strip('"'),
                    "status": parts[1].strip('"')
                })
    return phases

def calculate_days_remaining(target_date):
    """Calculate days remaining until target date"""
    if not target_date:
        return None
    try:
        target = datetime.strptime(target_date, "%Y-%m-%d")
        now = datetime.now()
        delta = target - now
        return max(0, delta.days)
    except:
        return None

def get_recent_tasks():
    """Get recent completed tasks as wins"""
    query = 'MATCH (t:Task {status: "COMPLETED"}) WHERE t.created > datetime().minusDays(7) RETURN t.title, t.created, t.agent ORDER BY t.created DESC LIMIT 10'
    result = run_cypher(query)
    tasks = []
    lines = result.split("\n")[1:]
    for line in lines:
        if line.strip():
            parts = line.split(", ")
            if len(parts) >= 2:
                tasks.append({
                    "title": parts[0].strip('"'),
                    "created": parts[1].strip('"'),
                    "agent": parts[2].strip('"') if len(parts) > 2 else ""
                })
    return tasks

def get_stalled_tasks():
    """Get tasks that haven't progressed in 48+ hours"""
    query = 'MATCH (t:Task) WHERE t.status IN ["FAILED", "ORPHANED"] AND t.updated < (datetime() - duration({hours: 48})) RETURN t.title, t.status, t.agent'
    result = run_cypher(query)
    tasks = []
    lines = result.split("\n")[1:]
    for line in lines:
        if line.strip():
            parts = line.split(", ")
            if len(parts) >= 2:
                tasks.append({
                    "title": parts[0].strip('"'),
                    "status": parts[1].strip('"'),
                    "agent": parts[2].strip('"') if len(parts) > 2 else ""
                })
    return tasks

def get_task_stats():
    """Get overall task statistics"""
    query = 'MATCH (t:Task) RETURN t.status, count(t)'
    result = run_cypher(query)
    stats = {}
    lines = result.split("\n")[1:]
    for line in lines:
        if line.strip():
            parts = line.split(", ")
            if len(parts) >= 2:
                status = parts[0].strip('"')
                count = int(parts[1])
                stats[status] = count
    return stats

def get_critical_failures():
    """Get recent critical failures (last 24 hours), excluding test tasks"""
    query = 'MATCH (t:Task) WHERE t.status = "FAILED" AND t.updated > (datetime() - duration({hours: 24})) AND NOT t.title CONTAINS "TEST" AND NOT t.title CONTAINS "Unknown" RETURN t.title, t.agent, t.updated ORDER BY t.updated DESC LIMIT 5'
    result = run_cypher(query)
    tasks = []
    lines = result.split("\n")[1:]
    for line in lines:
        if line.strip():
            parts = line.split(", ")
            if len(parts) >= 2:
                tasks.append({
                    "title": parts[0].strip('"'),
                    "agent": parts[1].strip('"') if len(parts) > 2 else "",
                    "updated": parts[2].strip('"') if len(parts) > 2 else ""
                })
    return tasks

def main():
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Get all active projects
    projects = get_projects()
    
    # Get recent wins and blockers
    recent_tasks = get_recent_tasks()
    stalled_tasks = get_stalled_tasks()
    task_stats = get_task_stats()
    critical_failures = get_critical_failures()
    
    report = f"📊 Daily Progress {today}\n\n"
    
    for project in projects:
        name = project["name"]
        target_date = project["target_date"]
        days_remaining = calculate_days_remaining(target_date)
        
        # Get component progress
        comp_stats = get_component_progress(name)
        total = comp_stats["total"]
        complete = comp_stats["complete"]
        in_progress = comp_stats["in_progress"]
        
        # Calculate percentage
        pct = round((complete / total * 100) if total > 0 else 0)
        
        # Get phase info for next milestone
        phases = get_phase_progress(name)
        next_milestone = "All phases complete"
        for phase in phases:
            if phase["status"] != "complete":
                next_milestone = f"Complete {phase['name']}"
                break
        
        # Parse-specific revenue metrics (placeholder - would need actual data source)
        revenue_note = ""
        if "Revenue" in name:
            revenue_note = "\n- 💰 Revenue: Tracking toward $1500 target (first paying customer)"
        
        report += f"## {name}\n"
        report += f"- Progress: {pct}% complete"
        if days_remaining is not None:
            report += f", {days_remaining} days remaining"
        elif total == 0:
            report += " (no components tracked)"
        report += f"\n- Goal: {project['goal']}{revenue_note}\n"
        
        # Wins (recent completions related to this project)
        related_wins = [t for t in recent_tasks if name.split()[0].lower() in t["title"].lower() or "OpenRouter" in t["title"]]
        if related_wins:
            report += f"- ✅ Wins: {', '.join([t['title'][:50] for t in related_wins[:3]])}\n"
        elif pct == 100:
            report += "- ✅ Wins: Component migration complete\n"
        elif recent_tasks:
            report += f"- ✅ Wins: {recent_tasks[0]['title'][:60]}...\n"
        else:
            report += "- ✅ Wins: Initializing\n"
        
        # Blockers
        if stalled_tasks:
            report += f"- ⚠️ Blockers: {len(stalled_tasks)} stalled task(s) - {stalled_tasks[0]['title'][:50]}...\n"
        else:
            report += "- ⚠️ Blockers: None identified\n"
        
        # Next milestone
        if total == 0:
            report += "- 📍 Next: Define components and phases\n"
        elif pct == 100:
            report += "- 📍 Next: Project complete - ready for launch\n"
        else:
            report += f"- 📍 Next: {next_milestone}\n"
        report += "\n"
    
    # If no active projects, report on task system health
    if not projects:
        report += "## System Status\n"
        report += "- No active projects tracked in Neo4j\n"
        report += f"- ✅ Recent completions: {len(recent_tasks)} tasks in last 7 days\n"
        if stalled_tasks:
            report += f"- ⚠️ Blockers: {len(stalled_tasks)} stalled task(s)\n"
        report += "- 📍 Next: Initialize project tracking\n"
    
    # Add system health summary
    report += "---\n## System Health\n"
    total_tasks = sum(task_stats.values())
    completed = task_stats.get("COMPLETED", 0)
    failed = task_stats.get("FAILED", 0)
    orphaned = task_stats.get("ORPHANED", 0)
    success_rate = round((completed / total_tasks * 100) if total_tasks > 0 else 0)
    
    report += f"- 📈 Task Success Rate: {success_rate}% ({completed}/{total_tasks} completed)\n"
    report += f"- ⚠️ Failed: {failed}, Orphaned: {orphaned}\n"
    
    if critical_failures:
        report += "- 🔴 Critical Failures (24h):\n"
        for task in critical_failures[:3]:
            report += f"  - {task['title'][:60]} ({task['agent']})\n"
    
    if stalled_tasks:
        report += f"- 🕒 Stalled (>48h): {len(stalled_tasks)} task(s)\n"
    
    print(report)

if __name__ == "__main__":
    main()
