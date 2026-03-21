#!/usr/bin/env python3
"""
Daily Goal Progress Summary - Cron Job
Queries Neo4j for all active goals and generates progress report.

For each goal:
1) Get task completion stats (total/completed/in_progress/blocked)
2) Calculate % complete
3) Identify blockers (>48h no progress)
4) Check if on track for deadline

Report format:
📊 Daily Progress [Date]

## Goal Name
- Progress: X% complete, Y days remaining
- ✅ Wins: [list]
- ⚠️ Blockers: [list]
- 📍 Next: [milestone]
"""

import subprocess
import json
import re
from datetime import datetime, timedelta
import os

# Neo4j credentials
NEO4J_USER = "neo4j"
NEO4J_PASS = os.environ.get("NEO4J_PASSWORD", "myStrongPassword123")
NEO4J_ADDR = "bolt://localhost:7687"

def run_cypher(query):
    """Execute Cypher query and return results as list of dicts"""
    cmd = [
        "cypher-shell",
        "-a", NEO4J_ADDR,
        "-u", NEO4J_USER,
        "-p", NEO4J_PASS,
        query,
        "--format", "plain"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        return []
    
    lines = result.stdout.strip().split("\n")
    if len(lines) < 2:
        return []
    
    # Parse header
    header = [h.strip() for h in lines[0].split(", ")]
    
    # Parse data rows
    rows = []
    for line in lines[1:]:
        if not line.strip():
            continue
        # Simple CSV-like parsing (handles basic cases)
        values = []
        in_quotes = False
        current = ""
        for char in line:
            if char == '"' and (not current or current[-1] != '\\'):
                in_quotes = not in_quotes
            elif char == ',' and not in_quotes:
                values.append(current.strip().strip('"'))
                current = ""
            else:
                current += char
        values.append(current.strip().strip('"'))
        
        if len(values) == len(header):
            rows.append(dict(zip(header, values)))
    
    return rows

def get_active_projects():
    """Get all active projects (goals) from Neo4j"""
    query = 'MATCH (p:Project {status: "in_progress"}) RETURN p.name AS name, p.goal AS goal, p.target_date AS target_date, p.target_revenue AS target_revenue, p.created_at AS created_at, p.priority AS priority'
    return run_cypher(query)

def get_component_stats(project_name):
    """Get component completion stats for a project"""
    query = f'MATCH (p:Project {{name: "{project_name}"}})-[:HAS_COMPONENT]->(c:Component) RETURN c.status AS status, count(c) AS cnt'
    rows = run_cypher(query)
    
    stats = {"complete": 0, "in_progress": 0, "pending": 0, "total": 0}
    for row in rows:
        status = row.get("status", "pending")
        count = int(row.get("cnt", 0))
        if status in stats:
            stats[status] = count
        stats["total"] += count
    
    return stats

def get_phase_progress(project_name):
    """Get phase progress for a project"""
    query = f'MATCH (p:Project {{name: "{project_name}"}})-[:HAS_PHASE]->(ph:Phase) RETURN ph.name AS name, ph.status AS status ORDER BY ph.name'
    return run_cypher(query)

def get_task_stats_for_project(project_name):
    """Get task statistics related to a project"""
    # Escape quotes in project name
    safe_name = project_name.replace('"', '\\"')
    
    # Get tasks mentioning the project
    query = f'MATCH (t:Task) WHERE t.title CONTAINS "{safe_name}" OR t.title CONTAINS "{project_name.split()[0].lower()}" RETURN t.status AS status, count(t) AS cnt'
    rows = run_cypher(query)
    
    stats = {"COMPLETED": 0, "FAILED": 0, "BLOCKED": 0, "in_progress": 0, "total": 0}
    for row in rows:
        status = row.get("status", "unknown")
        count = int(row.get("cnt", 0))
        if status in stats:
            stats[status] = count
        stats["total"] += count
    
    return stats

def get_recent_wins(project_name, days=7):
    """Get recent completed tasks as wins"""
    safe_name = project_name.replace('"', '\\"')
    query = f'MATCH (t:Task {{status: "COMPLETED"}}) WHERE (t.title CONTAINS "{safe_name}" OR t.title CONTAINS "OpenRouter" OR t.title CONTAINS "Parse") AND t.created > (datetime() - duration({{days: {days}}})) RETURN t.title AS title, t.created AS created ORDER BY t.created DESC LIMIT 5'
    rows = run_cypher(query)
    return [row.get("title", "")[:60] for row in rows]

def get_stalled_tasks(project_name, hours=48):
    """Get tasks that haven't progressed in specified hours"""
    safe_name = project_name.replace('"', '\\"')
    query = f'MATCH (t:Task) WHERE (t.title CONTAINS "{safe_name}" OR t.title CONTAINS "Parse") AND t.status IN ["FAILED", "BLOCKED", "ORPHANED"] AND t.updated < (datetime() - duration({{hours: {hours}}})) RETURN t.title AS title, t.status AS status LIMIT 3'
    rows = run_cypher(query)
    return [f"{row.get('title', '')[:50]} ({row.get('status', 'unknown')})" for row in rows]

def get_next_milestone(phases):
    """Determine next milestone from phases"""
    for phase in phases:
        if phase.get("status") != "complete":
            return f"Complete {phase.get('name', 'next phase')}"
    return "All phases complete"

def calculate_days_remaining(target_date):
    """Calculate days remaining until target date"""
    if not target_date or target_date == "NULL":
        return None
    try:
        # Handle ISO date format
        if "T" in target_date:
            target_date = target_date.split("T")[0]
        target = datetime.strptime(target_date, "%Y-%m-%d")
        now = datetime.now()
        delta = target - now
        return max(0, delta.days)
    except Exception as e:
        return None

def calculate_progress(component_stats):
    """Calculate progress percentage from component stats"""
    total = component_stats.get("total", 0)
    if total == 0:
        return 0
    complete = component_stats.get("complete", 0)
    in_progress = component_stats.get("in_progress", 0)
    # Weighted: complete = 100%, in_progress = 50%
    weighted = complete * 1.0 + in_progress * 0.5
    return min(100, round(weighted / total * 100))

def get_parse_revenue_metrics():
    """Get Parse revenue metrics (from Neo4j or defaults)"""
    # Try to query Neo4j for any revenue/metric nodes
    query = 'MATCH (n) WHERE "ParseMetric" IN labels(n) OR "Revenue" IN labels(n) RETURN n LIMIT 1'
    rows = run_cypher(query)
    
    if rows:
        # Parse actual data
        return {"mrr": 0, "paying_users": 0, "conversion_rate": 0}
    
    # Default/placeholder based on project goal
    return {"mrr": 0, "paying_users": 0, "conversion_rate": 0}

def generate_report():
    """Generate the daily progress report"""
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [f"📊 Daily Progress {today}", ""]
    
    # Get all active projects
    projects = get_active_projects()
    
    if not projects:
        lines.append("## No Active Projects")
        lines.append("- No projects with status 'in_progress' found in Neo4j")
        lines.append("")
    else:
        for project in projects:
            name = project.get("name", "Unknown")
            goal = project.get("goal", "")
            target_date = project.get("target_date")
            target_revenue = project.get("target_revenue")
            
            # Get component stats
            comp_stats = get_component_stats(name)
            progress = calculate_progress(comp_stats)
            
            # Get days remaining
            days_left = calculate_days_remaining(target_date)
            
            # Get phases for next milestone
            phases = get_phase_progress(name)
            next_milestone = get_next_milestone(phases)
            
            # Get task stats
            task_stats = get_task_stats_for_project(name)
            
            # Get wins and blockers
            wins = get_recent_wins(name)
            blockers = get_stalled_tasks(name)
            
            # Build project section
            lines.append(f"## {name}")
            
            if days_left is not None:
                lines.append(f"- Progress: {progress}% complete, {days_left} days remaining")
            else:
                lines.append(f"- Progress: {progress}% complete (ongoing)")
            
            # Add goal description
            if goal:
                lines.append(f"- Goal: {goal}")
            
            # Add revenue metrics for Parse
            if "Parse" in name and target_revenue and target_revenue != "NULL":
                metrics = get_parse_revenue_metrics()
                lines.append(f"- 💰 Target MRR: ${target_revenue} (first paying customer)")
            
            # Add task stats
            if task_stats["total"] > 0:
                lines.append(f"- 📋 Tasks: {task_stats.get('COMPLETED', 0)} completed, {task_stats.get('in_progress', 0)} in progress, {task_stats.get('FAILED', 0)} failed")
            
            # Wins
            if wins:
                lines.append(f"- ✅ Wins: {', '.join(wins)}")
            elif progress == 100:
                lines.append("- ✅ Wins: All components complete")
            elif task_stats.get("COMPLETED", 0) > 0:
                lines.append(f"- ✅ Wins: {task_stats.get('COMPLETED', 0)} related task(s) completed")
            else:
                lines.append("- ✅ Wins: Initializing")
            
            # Blockers
            if blockers:
                lines.append(f"- ⚠️ Blockers: {', '.join(blockers)}")
            else:
                lines.append("- ⚠️ Blockers: None identified")
            
            # Next milestone
            if progress >= 100:
                lines.append("- 📍 Next: Project complete - ready for launch")
            elif comp_stats["total"] == 0:
                lines.append("- 📍 Next: Define components and phases for tracking")
            elif days_left is not None and days_left < 7:
                lines.append(f"- 📍 Next: CRITICAL - {next_milestone} (deadline in {days_left} days)")
            elif days_left is not None and days_left < 14:
                lines.append(f"- 📍 Next: URGENT - {next_milestone} ({days_left} days remaining)")
            else:
                lines.append(f"- 📍 Next: {next_milestone}")
            
            lines.append("")
    
    # Add system health summary
    lines.append("---")
    lines.append("## System Health")
    
    # Get overall task stats
    task_query = 'MATCH (t:Task) RETURN t.status AS status, count(t) AS cnt'
    task_rows = run_cypher(task_query)
    
    total_tasks = 0
    completed = 0
    failed = 0
    
    for row in task_rows:
        status = row.get("status", "")
        count = int(row.get("cnt", 0))
        total_tasks += count
        if status == "COMPLETED":
            completed = count
        elif status == "FAILED":
            failed = count
    
    success_rate = round((completed / total_tasks * 100) if total_tasks > 0 else 0)
    lines.append(f"- 📈 Success Rate: {success_rate}% ({completed}/{total_tasks})")
    lines.append(f"- ⚠️ Failed: {failed}")
    
    lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')} EST")
    
    return "\n".join(lines)

if __name__ == "__main__":
    report = generate_report()
    print(report)
