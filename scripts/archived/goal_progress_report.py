#!/usr/bin/env python3
"""
Daily Goal Progress Report Generator
Reports on active goals and task statistics by agent
"""

from neo4j import GraphDatabase
from datetime import datetime, timedelta
import os

# Neo4j connection
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

def get_active_goals(driver):
    """Get all active goals"""
    
    query = """
    MATCH (g:Goal {status: 'active'})
    RETURN g.title as title,
           g.priority as priority,
           g.deadline as deadline,
           g.domain as domain,
           g.blockers as blockers
    ORDER BY g.priority DESC, g.createdAt DESC
    LIMIT 10
    """
    
    with driver.session() as session:
        result = session.run(query)
        goals = []
        
        for record in result:
            goals.append({
                'title': record['title'],
                'priority': record['priority'],
                'deadline': record['deadline'],
                'domain': record['domain'],
                'blockers': record['blockers'] if record['blockers'] else []
            })
        
        return goals

def get_task_stats_by_agent(driver):
    """Get task statistics grouped by agent"""
    
    query = """
    MATCH (t:Task)
    WHERE t.created >= datetime() - duration('P7D')
    WITH t.assigned_to as agent,
         count(t) as total,
         sum(CASE WHEN t.status = 'COMPLETED' THEN 1 ELSE 0 END) as completed,
         sum(CASE WHEN t.status = 'FAILED' THEN 1 ELSE 0 END) as failed,
         sum(CASE WHEN t.status = 'PENDING' THEN 1 ELSE 0 END) as pending
    RETURN agent,
           total,
           completed,
           failed,
           pending,
           round(toFloat(completed) / total * 100, 1) as completion_rate
    ORDER BY total DESC
    """
    
    with driver.session() as session:
        result = session.run(query)
        stats = []
        
        for record in result:
            if record['agent']:  # Skip null agents
                stats.append({
                    'agent': record['agent'],
                    'total': record['total'],
                    'completed': record['completed'],
                    'failed': record['failed'],
                    'pending': record['pending'],
                    'completion_rate': record['completion_rate']
                })
        
        return stats

def get_recent_wins(driver, agent=None, limit=5):
    """Get recent completed tasks"""
    
    if agent:
        query = """
        MATCH (t:Task {assigned_to: $agent, status: 'COMPLETED'})
        WHERE t.completed_at >= datetime() - duration('P7D')
        RETURN t.title as title, t.completed_at as completed_at
        ORDER BY t.completed_at DESC
        LIMIT $limit
        """
        params = {'agent': agent, 'limit': limit}
    else:
        query = """
        MATCH (t:Task {status: 'COMPLETED'})
        WHERE t.completed_at >= datetime() - duration('P7D')
        RETURN t.title as title, t.completed_at as completed_at, t.assigned_to as agent
        ORDER BY t.completed_at DESC
        LIMIT $limit
        """
        params = {'limit': limit}
    
    with driver.session() as session:
        result = session.run(query, **params)
        wins = []
        
        for record in result:
            if agent:
                wins.append(record['title'])
            else:
                wins.append(f"{record['title']} ({record['agent']})")
        
        return wins

def get_blocked_tasks(driver):
    """Get tasks that have been pending too long (>24h)"""
    
    query = """
    MATCH (t:Task {status: 'PENDING'})
    WHERE t.created < datetime() - duration('P1D')
    RETURN t.title as title, t.assigned_to as agent, t.created as created
    ORDER BY t.created ASC
    LIMIT 10
    """
    
    with driver.session() as session:
        result = session.run(query)
        blocked = []
        
        for record in result:
            blocked.append(f"{record['title']} ({record['agent']})")
        
        return blocked

def get_failed_tasks(driver):
    """Get recently failed tasks"""
    
    query = """
    MATCH (t:Task {status: 'FAILED'})
    WHERE t.created >= datetime() - duration('P7D')
    RETURN t.title as title, t.assigned_to as agent, t.created as created
    ORDER BY t.created DESC
    LIMIT 5
    """
    
    with driver.session() as session:
        result = session.run(query)
        failed = []
        
        for record in result:
            failed.append(f"{record['title']} ({record['agent']})")
        
        return failed

def calculate_days_remaining(deadline):
    """Calculate days remaining until deadline"""
    if not deadline:
        return None
    
    try:
        # Handle ISO format
        deadline_dt = datetime.fromisoformat(deadline.replace('Z', '+00:00'))
        now = datetime.now(deadline_dt.tzinfo)
        days = (deadline_dt - now).days
        return max(0, days)
    except:
        return None

def generate_report():
    """Generate the daily progress report"""
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    try:
        goals = get_active_goals(driver)
        task_stats = get_task_stats_by_agent(driver)
        recent_wins = get_recent_wins(driver)
        blocked_tasks = get_blocked_tasks(driver)
        failed_tasks = get_failed_tasks(driver)
        
        report_lines = [
            f"📊 Daily Progress - {datetime.now().strftime('%B %d, %Y')}\n"
        ]
        
        # Active Goals Section
        if goals:
            report_lines.append("## 🎯 Active Goals")
            for goal in goals[:5]:  # Top 5 goals
                days_remaining = calculate_days_remaining(goal['deadline'])
                report_lines.append(f"\n**{goal['title']}**")
                report_lines.append(f"- Priority: {goal['priority']}")
                
                if days_remaining is not None:
                    report_lines.append(f"- Days Remaining: {days_remaining}")
                
                if goal['blockers']:
                    report_lines.append(f"- ⚠️ Blockers: {', '.join(goal['blockers'])}")
                
                report_lines.append(f"- Domain: {goal.get('domain', 'general')}")
        
        # Task Stats by Agent Section
        if task_stats:
            report_lines.append("\n## 📈 Agent Performance (7 days)")
            for stat in task_stats:
                report_lines.append(
                    f"\n**{stat['agent'].capitalize()}**: "
                    f"{stat['completion_rate']}% complete "
                    f"({stat['completed']}/{stat['total']} tasks) • "
                    f"{stat['failed']} failed, {stat['pending']} pending"
                )
        
        # Recent Wins Section
        if recent_wins:
            report_lines.append("\n## ✅ Recent Wins")
            for win in recent_wins[:5]:
                report_lines.append(f"- {win}")
        
        # Blockers Section
        if blocked_tasks:
            report_lines.append("\n## ⚠️ Stalled Tasks (>24h pending)")
            for task in blocked_tasks[:5]:
                report_lines.append(f"- {task}")
        
        # Failed Tasks Section
        if failed_tasks:
            report_lines.append("\n## ❌ Recent Failures")
            for task in failed_tasks:
                report_lines.append(f"- {task}")
        
        # Summary stats
        total_completed = sum(s['completed'] for s in task_stats)
        total_tasks = sum(s['total'] for s in task_stats)
        overall_rate = round(total_completed / total_tasks * 100, 1) if total_tasks > 0 else 0
        
        report_lines.append(f"\n---\n**Weekly Summary**: {total_completed}/{total_tasks} tasks completed ({overall_rate}%)")
        
        return '\n'.join(report_lines)
    
    finally:
        driver.close()

if __name__ == '__main__':
    report = generate_report()
    print(report)
