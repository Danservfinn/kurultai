#!/usr/bin/env python3
"""
Neo4j Task Tracker - Persistent task history with queryable metrics

Schema:
- (:Task {label, agent, status, created, completed, ...})
- (:Agent {name})-[:EXECUTED]->(:Task)
- (:Task)-[:RETRIED]->(:Task)

Usage:
    from neo4j_task_tracker import TaskTracker
    tracker = TaskTracker()
    tracker.create_task("mongke-123", "mongke", "Research X")
    tracker.update_status("mongke-123", "completed")
"""

import os
import json
from datetime import datetime
from neo4j import GraphDatabase

class TaskTracker:
    def __init__(self):
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "myStrongPassword123")
        
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        
    def close(self):
        self.driver.close()
    
    def create_task(self, label, agent, task_desc, priority="normal", 
                    mode="run", continuous=False, source="chat"):
        """Create a task node"""
        with self.driver.session() as session:
            session.run("""
                MERGE (a:Agent {name: $agent})
                CREATE (t:Task {
                    label: $label,
                    agent: $agent,
                    task: $task,
                    priority: $priority,
                    mode: $mode,
                    continuous: $continuous,
                    source: $source,
                    status: 'ready',
                    created: datetime(),
                    retry_count: 0,
                    max_retries: 3
                })
                CREATE (a)-[:EXECUTED]->(t)
            """,
            label=label, agent=agent, task=task_desc,
            priority=priority, mode=mode, continuous=continuous, source=source)
    
    def update_status(self, label, status, error=None, session_key=None):
        """Update task status"""
        with self.driver.session() as session:
            session.run("""
                MATCH (t:Task {label: $label})
                SET t.status = $status,
                    t.updated = datetime()
                """,
                label=label, status=status)
            
            if status == 'running' and session_key:
                session.run("""
                    MATCH (t:Task {label: $label})
                    SET t.session_key = $session_key,
                        t.started = datetime()
                """, label=label, session_key=session_key)
            
            if status in ['completed', 'failed', 'killed']:
                session.run("""
                    MATCH (t:Task {label: $label})
                    SET t.completed = datetime()
                """, label=label)
            
            if error:
                session.run("""
                    MATCH (t:Task {label: $label})
                    SET t.error = $error
                """, label=label, error=error)
    
    def increment_retry(self, label):
        """Increment retry count"""
        with self.driver.session() as session:
            session.run("""
                MATCH (t:Task {label: $label})
                SET t.retry_count = t.retry_count + 1,
                    t.last_retry = datetime()
            """, label=label)
    
    def get_tasks_by_agent(self, agent, limit=10):
        """Get recent tasks for an agent"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (a:Agent {name: $agent})-[:EXECUTED]->(t:Task)
                RETURN t ORDER BY t.created DESC LIMIT $limit
            """, agent=agent, limit=limit)
            return [dict(r['t']) for r in result]
    
    def get_tasks_by_status(self, status, limit=50):
        """Get tasks by status"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task {status: $status})
                RETURN t ORDER BY t.created DESC LIMIT $limit
            """, status=status, limit=limit)
            return [dict(r['t']) for r in result]
    
    def get_hourly_summary(self, hours=1):
        """Get task summary for last N hours"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({hours: $hours})
                WITH t.agent AS agent, t
                RETURN 
                    agent,
                    count(t) AS total,
                    sum(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) AS completed,
                    sum(CASE WHEN t.status = 'failed' THEN 1 ELSE 0 END) AS failed,
                    sum(CASE WHEN t.status = 'running' THEN 1 ELSE 0 END) AS running,
                    sum(CASE WHEN t.status = 'ready' THEN 1 ELSE 0 END) AS ready
                GROUP BY agent
                ORDER BY total DESC
            """, hours=hours)
            return [dict(r) for r in result]
    
    def get_completion_rate(self, hours=24):
        """Get success/failure rates"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration('PT' + $hours + 'H')
                  AND t.status IN ['completed', 'failed']
                WITH 
                    count(t) AS total,
                    sum(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) AS success
                RETURN 
                    total,
                    success,
                    round(100.0 * success / total, 1) AS success_rate
            """, hours=hours)
            record = result.single()
            return dict(record) if record else {}
    
    def get_continuous_tasks(self):
        """Get all running continuous tasks"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task {continuous: true, status: 'running'})
                RETURN t ORDER BY t.created DESC
            """)
            return [dict(r['t']) for r in result]
    
    def get_reflection_data(self, agent=None, hours=1):
        """Get data for hourly reflection"""
        with self.driver.session() as session:
            if agent:
                result = session.run("""
                    MATCH (t:Task {agent: $agent})
                    WHERE t.created > datetime() - duration({hours: $hours})
                    RETURN 
                        count(t) AS total_tasks,
                        sum(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) AS completed,
                        sum(CASE WHEN t.status = 'failed' THEN 1 ELSE 0 END) AS failed,
                        coalesce(sum(t.retry_count), 0) AS total_retries
                    """, agent=agent, hours=hours)
            else:
                result = session.run("""
                    MATCH (t:Task)
                    WHERE t.created > datetime() - duration({hours: $hours})
                    RETURN 
                        count(t) AS total_tasks,
                        sum(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) AS completed,
                        sum(CASE WHEN t.status = 'failed' THEN 1 ELSE 0 END) AS failed,
                        coalesce(sum(t.retry_count), 0) AS total_retries
                    """, hours=hours)
            
            record = result.single()
            return dict(record) if record else {}
    
    def get_historical_trends(self, days=7):
        """Get daily task trends for last N days"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({days: $days})
                WITH 
                    date(t.created) AS day,
                    t.status AS status,
                    t
                RETURN 
                    day,
                    sum(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
                    sum(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
                    sum(CASE WHEN status = 'running' THEN 1 ELSE 0 END) AS running,
                    count(t) AS total
                GROUP BY day
                ORDER BY day DESC
                """, days=days)
            return [dict(r) for r in result]
    
    def get_agent_workload(self, days=7):
        """Get workload distribution by agent"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({days: $days})
                WITH t.agent AS agent, t
                RETURN 
                    agent,
                    count(t) AS total_tasks,
                    sum(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) AS completed,
                    round(100.0 * sum(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) / count(t), 1) AS success_rate
                GROUP BY agent
                ORDER BY total_tasks DESC
                """, days=days)
            return [dict(r) for r in result]
    
    def get_peak_hours(self, days=7):
        """Get busiest hours of day"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({days: $days})
                WITH 
                    t.created.hour AS hour,
                    count(t) AS count
                RETURN 
                    hour,
                    count
                ORDER BY count DESC
                LIMIT 5
                """, days=days)
            return [dict(r) for r in result]
    
    def get_bottlenecks(self, hours=24):
        """Find tasks with most retries (potential bottlenecks)"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({hours: $hours})
                  AND t.retry_count > 0
                RETURN 
                    t.agent AS agent,
                    t.label AS label,
                    t.retry_count AS retries,
                    t.status AS status
                ORDER BY retries DESC
                LIMIT 10
                """, hours=hours)
            return [dict(r) for r in result]


# Singleton instance
_tracker = None

def get_tracker():
    """Get or create tracker instance"""
    global _tracker
    if _tracker is None:
        _tracker = TaskTracker()
    return _tracker


if __name__ == "__main__":
    # Test
    tracker = get_tracker()
    print("Neo4j Task Tracker initialized")
    print("Hourly summary:", tracker.get_hourly_summary(1))
    tracker.close()
