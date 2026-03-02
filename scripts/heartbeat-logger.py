#!/usr/bin/env python3
"""
Structured Heartbeat Logger
Logs agent heartbeat data to Neo4j for Kurultai analysis
"""

from neo4j import GraphDatabase
import os
from datetime import datetime

class HeartbeatLogger:
    def __init__(self):
        self.driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "neo4j"))
    
    def log_heartbeat(self, agent, completed_tasks, current_task, progress, 
                     blockers, next_action, self_directed=True, assigned_by=None):
        """Log a structured heartbeat to Neo4j"""
        
        with self.driver.session() as session:
            # Create Heartbeat node
            session.run("""
                CREATE (h:Heartbeat {
                    timestamp: datetime(),
                    agent: $agent,
                    completed_tasks: $completed,
                    current_task: $current,
                    current_task_progress: $progress,
                    blockers: $blockers,
                    next_action: $next,
                    self_directed: $self_directed,
                    assigned_by: $assigned_by,
                    blocker_count: size($blockers),
                    completed_count: size($completed)
                })
            """, 
            agent=agent,
            completed=completed_tasks or [],
            current=current_task or '',
            progress=progress or 0.0,
            blockers=blockers or [],
            next=next_action or '',
            self_directed=self_directed,
            assigned_by=assigned_by)
            
            print(f"✅ Logged heartbeat for {agent}")
    
    def get_agent_metrics(self, agent, hours=6):
        """Get metrics for an agent over the past N hours"""
        
        with self.driver.session() as session:
            result = session.run("""
                MATCH (h:Heartbeat)
                WHERE h.agent = $agent 
                AND h.timestamp > datetime() - duration('PT' + $hours + 'H')
                RETURN 
                    count(h) as heartbeat_count,
                    avg(h.completed_count) as avg_completed,
                    avg(h.blocker_count) as avg_blockers,
                    sum(CASE WHEN h.self_directed THEN 1 ELSE 0 END) * 100.0 / count(h) as autonomy_score,
                    collect(DISTINCT h.blockers) as all_blockers
                """,
                agent=agent, hours=str(hours))
            
            return result.single()
    
    def get_blocker_resolution_time(self, agent, hours=6):
        """Calculate average time between blocker appearance and resolution"""
        
        with self.driver.session() as session:
            # This is a simplified version - full implementation would track
            # when blockers appear and when they disappear
            result = session.run("""
                MATCH (h:Heartbeat)
                WHERE h.agent = $agent
                AND h.timestamp > datetime() - duration('PT' + $hours + 'H')
                AND size(h.blockers) > 0
                RETURN 
                    count(h) as heartbeats_with_blockers,
                    avg(h.blocker_count) as avg_blockers_per_heartbeat
                """,
                agent=agent, hours=str(hours))
            
            return result.single()
    
    def close(self):
        self.driver.close()


if __name__ == '__main__':
    # Example usage
    logger = HeartbeatLogger()
    
    # Log a sample heartbeat
    logger.log_heartbeat(
        agent='temujin',
        completed_tasks=['Fixed deployment script'],
        current_task='Deploying to Railway',
        progress=0.75,
        blockers=['Railway timeout'],
        next_action='Retry deployment',
        self_directed=True
    )
    
    # Get metrics
    metrics = logger.get_agent_metrics('temujin', hours=6)
    print(f"Metrics: {dict(metrics)}")
    
    logger.close()
