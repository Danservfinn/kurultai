#!/usr/bin/env python3
"""
Weekly Reflection Trigger - Ögedei Operations

Triggers proactive reflection on Sundays at midnight UTC.
Checks system idle status, generates ImprovementOpportunity nodes,
and logs the reflection cycle to Neo4j.

Usage:
    python -m tools.kurultai.reflection_trigger
    python tools/kurultai/reflection_trigger.py --dry-run
    python tools/kurultai/reflection_trigger.py --force

Author: Ögedei (Ops Agent)
Date: 2026-02-09
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("kurultai.reflection_trigger")


class ReflectionTrigger:
    """
    Triggers weekly reflection cycle.
    
    Responsibilities:
    1. Check system idle status
    2. Generate ImprovementOpportunity nodes
    3. Log reflection cycle to Neo4j
    4. Coordinate with Kublai's reflection tasks
    """
    
    # Thresholds for system idle determination
    IDLE_CPU_THRESHOLD = 50.0  # CPU usage below this is "idle"
    IDLE_MEMORY_THRESHOLD = 80.0  # Memory usage below this is "idle"
    PENDING_TASK_THRESHOLD = 5  # Fewer than this many pending tasks = idle
    
    def __init__(self, neo4j_driver=None):
        self.driver = neo4j_driver
        self.reflection_id = None
        
    def _get_driver(self):
        """Get or create Neo4j driver."""
        if self.driver is None:
            try:
                from neo4j import GraphDatabase
                uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
                user = os.environ.get("NEO4J_USER", "neo4j")
                password = os.environ.get("NEO4J_PASSWORD")
                
                if not password:
                    raise ValueError("NEO4J_PASSWORD environment variable not set")
                
                self.driver = GraphDatabase.driver(uri, auth=(user, password))
                logger.info(f"Connected to Neo4j at {uri}")
            except ImportError:
                logger.error("neo4j package not installed")
                raise
            except Exception as e:
                logger.error(f"Failed to connect to Neo4j: {e}")
                raise
        return self.driver
    
    def check_system_idle(self) -> Dict[str, Any]:
        """
        Check if system is idle enough for reflection.
        
        Returns:
            Dict with idle status and metrics
        """
        logger.info("Checking system idle status...")
        
        driver = self._get_driver()
        metrics = {
            "cpu_usage": None,
            "memory_usage": None,
            "pending_tasks": 0,
            "in_progress_tasks": 0,
            "high_priority_tasks": 0,
            "is_idle": False
        }
        
        try:
            with driver.session() as session:
                # Count pending and in-progress tasks
                result = session.run("""
                    MATCH (t:Task)
                    WHERE t.status IN ['pending', 'ready']
                    RETURN count(t) as pending
                """)
                metrics["pending_tasks"] = result.single()["pending"]
                
                result = session.run("""
                    MATCH (t:Task)
                    WHERE t.status = 'in_progress'
                    RETURN count(t) as in_progress
                """)
                metrics["in_progress_tasks"] = result.single()["in_progress"]
                
                # Count high priority tasks
                result = session.run("""
                    MATCH (t:Task)
                    WHERE t.status IN ['pending', 'in_progress', 'ready']
                      AND t.priority_weight >= 0.8
                    RETURN count(t) as high_priority
                """)
                metrics["high_priority_tasks"] = result.single()["high_priority"]
                
                # Check recent agent activity (heartbeat within last 10 minutes)
                result = session.run("""
                    MATCH (a:Agent)
                    WHERE a.last_heartbeat > datetime() - duration('PT10M')
                    RETURN count(a) as active_agents
                """)
                metrics["active_agents"] = result.single()["active_agents"]
                
        except Exception as e:
            logger.error(f"Error checking system status: {e}")
            metrics["error"] = str(e)
        
        # Determine if system is idle
        # System is idle if:
        # - Fewer than threshold pending tasks
        # - No high priority tasks
        # - Some agents are active (system is operational)
        metrics["is_idle"] = (
            metrics["pending_tasks"] < self.PENDING_TASK_THRESHOLD and
            metrics["high_priority_tasks"] == 0 and
            metrics.get("active_agents", 0) > 0
        )
        
        logger.info(f"System idle status: {metrics['is_idle']} "
                   f"(pending: {metrics['pending_tasks']}, "
                   f"high_priority: {metrics['high_priority_tasks']}, "
                   f"active_agents: {metrics.get('active_agents', 0)})")
        
        return metrics
    
    def identify_improvement_areas(self) -> List[Dict[str, Any]]:
        """
        Identify areas for improvement by analyzing system patterns.
        
        Returns:
            List of improvement opportunity dictionaries
        """
        logger.info("Identifying improvement areas...")
        
        driver = self._get_driver()
        opportunities = []
        
        try:
            with driver.session() as session:
                # Check for frequently failing tasks
                result = session.run("""
                    MATCH (t:Task)
                    WHERE t.status = 'failed'
                      AND t.updated_at > datetime() - duration('P7D')
                    WITH t.type as task_type, count(t) as fail_count
                    WHERE fail_count >= 3
                    RETURN task_type, fail_count
                    ORDER BY fail_count DESC
                    LIMIT 5
                """)
                
                for record in result:
                    opportunities.append({
                        "category": "reliability",
                        "title": f"High failure rate for task type: {record['task_type']}",
                        "description": f"{record['fail_count']} failures in the past week",
                        "severity": "high" if record["fail_count"] > 5 else "medium",
                        "source": "task_analysis"
                    })
                
                # Check for orphaned nodes
                result = session.run("""
                    MATCH (n)
                    WHERE NOT (n)--() AND NOT n:Agent
                    RETURN labels(n)[0] as node_type, count(n) as orphan_count
                    ORDER BY orphan_count DESC
                    LIMIT 5
                """)
                
                for record in result:
                    if record["orphan_count"] > 10:
                        opportunities.append({
                            "category": "data_quality",
                            "title": f"Orphaned {record['node_type']} nodes",
                            "description": f"{record['orphan_count']} orphaned nodes found",
                            "severity": "medium",
                            "source": "data_analysis"
                        })
                
                # Check for slow tasks (in_progress for more than 1 hour)
                result = session.run("""
                    MATCH (t:Task)
                    WHERE t.status = 'in_progress'
                      AND t.claimed_at < datetime() - duration('PT1H')
                    RETURN count(t) as slow_count
                """)
                
                slow_count = result.single()["slow_count"]
                if slow_count > 0:
                    opportunities.append({
                        "category": "performance",
                        "title": "Long-running tasks detected",
                        "description": f"{slow_count} tasks running for over 1 hour",
                        "severity": "medium",
                        "source": "performance_analysis"
                    })
                
                # Check for stale heartbeats
                result = session.run("""
                    MATCH (a:Agent)
                    WHERE a.last_heartbeat < datetime() - duration('PT1H')
                    RETURN a.name as agent_name, a.last_heartbeat as last_seen
                    LIMIT 5
                """)
                
                for record in result:
                    opportunities.append({
                        "category": "infrastructure",
                        "title": f"Stale heartbeat: {record['agent_name']}",
                        "description": f"Last seen: {record['last_seen']}",
                        "severity": "high",
                        "source": "health_check"
                    })
                
                # Check for backlog of unprocessed tasks
                result = session.run("""
                    MATCH (t:Task)
                    WHERE t.status = 'pending'
                      AND t.created_at < datetime() - duration('P1D')
                    RETURN count(t) as backlog_count
                """)
                
                backlog = result.single()["backlog_count"]
                if backlog > 10:
                    opportunities.append({
                        "category": "capacity",
                        "title": "Task backlog accumulating",
                        "description": f"{backlog} tasks pending for over 24 hours",
                        "severity": "high",
                        "source": "capacity_analysis"
                    })
                
        except Exception as e:
            logger.error(f"Error identifying improvement areas: {e}")
        
        logger.info(f"Identified {len(opportunities)} improvement opportunities")
        return opportunities
    
    def generate_improvement_opportunities(self, opportunities: List[Dict[str, Any]]) -> List[str]:
        """
        Create ImprovementOpportunity nodes in Neo4j.
        
        Args:
            opportunities: List of opportunity dictionaries
            
        Returns:
            List of created opportunity IDs
        """
        logger.info(f"Generating {len(opportunities)} ImprovementOpportunity nodes...")
        
        driver = self._get_driver()
        created_ids = []
        
        try:
            with driver.session() as session:
                for opp in opportunities:
                    result = session.run("""
                        CREATE (o:ImprovementOpportunity {
                            id: 'opp-' + randomUUID(),
                            title: $title,
                            description: $description,
                            category: $category,
                            severity: $severity,
                            source: $source,
                            status: 'identified',
                            created_at: datetime(),
                            reflection_id: $reflection_id
                        })
                        RETURN o.id as id
                    """, {
                        "title": opp["title"],
                        "description": opp["description"],
                        "category": opp["category"],
                        "severity": opp["severity"],
                        "source": opp["source"],
                        "reflection_id": self.reflection_id
                    })
                    
                    record = result.single()
                    if record:
                        created_ids.append(record["id"])
                        logger.info(f"Created opportunity: {record['id']} - {opp['title']}")
                
        except Exception as e:
            logger.error(f"Error creating opportunities: {e}")
        
        return created_ids
    
    def log_reflection_cycle(self, metrics: Dict[str, Any], 
                            opportunities: List[Dict[str, Any]],
                            created_ids: List[str]) -> str:
        """
        Log the reflection cycle to Neo4j.
        
        Args:
            metrics: System idle metrics
            opportunities: Identified opportunities
            created_ids: Created opportunity node IDs
            
        Returns:
            Reflection cycle ID
        """
        logger.info("Logging reflection cycle...")
        
        driver = self._get_driver()
        reflection_id = f"refl-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        
        try:
            with driver.session() as session:
                session.run("""
                    CREATE (r:Reflection {
                        id: $id,
                        type: 'weekly',
                        triggered_at: datetime(),
                        system_idle: $is_idle,
                        pending_tasks: $pending_tasks,
                        high_priority_tasks: $high_priority,
                        opportunities_identified: $opp_count,
                        opportunities_created: $created_count,
                        status: 'completed',
                        agent: 'ogedei'
                    })
                """, {
                    "id": reflection_id,
                    "is_idle": metrics.get("is_idle", False),
                    "pending_tasks": metrics.get("pending_tasks", 0),
                    "high_priority": metrics.get("high_priority_tasks", 0),
                    "opp_count": len(opportunities),
                    "created_count": len(created_ids)
                })
                
                logger.info(f"Logged reflection cycle: {reflection_id}")
                
        except Exception as e:
            logger.error(f"Error logging reflection cycle: {e}")
            reflection_id = f"error-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        
        return reflection_id
    
    def trigger_reflection(self, force: bool = False, dry_run: bool = False) -> Dict[str, Any]:
        """
        Main entry point: trigger the weekly reflection.
        
        Args:
            force: Run even if system is not idle
            dry_run: Don't write to Neo4j
            
        Returns:
            Reflection result dictionary
        """
        logger.info("=" * 60)
        logger.info("Weekly Reflection Trigger - Ögedei")
        logger.info("=" * 60)
        
        result = {
            "status": "started",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "dry_run": dry_run,
            "forced": force
        }
        
        # Step 1: Check system idle status
        metrics = self.check_system_idle()
        result["system_metrics"] = metrics
        
        if not metrics.get("is_idle") and not force:
            logger.warning("System not idle, skipping reflection (use --force to override)")
            result["status"] = "skipped"
            result["reason"] = "system_not_idle"
            return result
        
        # Step 2: Identify improvement areas
        opportunities = self.identify_improvement_areas()
        result["opportunities_identified"] = opportunities
        
        if dry_run:
            logger.info("Dry run mode - not writing to Neo4j")
            result["status"] = "dry_run_complete"
            return result
        
        # Set reflection ID for linking opportunities
        self.reflection_id = f"refl-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        
        # Step 3: Generate ImprovementOpportunity nodes
        created_ids = self.generate_improvement_opportunities(opportunities)
        result["opportunities_created"] = created_ids
        
        # Step 4: Log reflection cycle
        reflection_id = self.log_reflection_cycle(metrics, opportunities, created_ids)
        result["reflection_id"] = reflection_id
        result["status"] = "completed"
        
        logger.info("=" * 60)
        logger.info(f"Reflection complete: {len(created_ids)} opportunities created")
        logger.info("=" * 60)
        
        return result


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Weekly Reflection Trigger - Ögedei Operations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run reflection (checks idle status)
  python -m tools.kurultai.reflection_trigger

  # Force run even if not idle
  python -m tools.kurultai.reflection_trigger --force

  # Dry run (don't write to Neo4j)
  python -m tools.kurultai.reflection_trigger --dry-run

  # Output as JSON
  python -m tools.kurultai.reflection_trigger --json
        """
    )
    
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run even if system is not idle"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't write to Neo4j"
    )
    
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )
    
    parser.add_argument(
        "--neo4j-uri",
        type=str,
        default=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        help="Neo4j URI"
    )
    
    parser.add_argument(
        "--neo4j-user",
        type=str,
        default=os.getenv("NEO4J_USER", "neo4j"),
        help="Neo4j username"
    )
    
    parser.add_argument(
        "--neo4j-password",
        type=str,
        default=os.getenv("NEO4J_PASSWORD"),
        help="Neo4j password"
    )
    
    args = parser.parse_args()
    
    # Set environment for Neo4j connection
    if args.neo4j_uri:
        os.environ["NEO4J_URI"] = args.neo4j_uri
    if args.neo4j_user:
        os.environ["NEO4J_USER"] = args.neo4j_user
    if args.neo4j_password:
        os.environ["NEO4J_PASSWORD"] = args.neo4j_password
    
    # Validate password
    if not os.environ.get("NEO4J_PASSWORD") and not args.dry_run:
        logger.error("NEO4J_PASSWORD not set. Use --neo4j-password or set env var.")
        sys.exit(1)
    
    # Run reflection
    trigger = ReflectionTrigger()
    result = trigger.trigger_reflection(force=args.force, dry_run=args.dry_run)
    
    # Output results
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"\nReflection Status: {result['status']}")
        print(f"Timestamp: {result['timestamp']}")
        if 'system_metrics' in result:
            m = result['system_metrics']
            print(f"System Idle: {m.get('is_idle', False)}")
            print(f"Pending Tasks: {m.get('pending_tasks', 0)}")
            print(f"High Priority Tasks: {m.get('high_priority_tasks', 0)}")
        if 'opportunities_created' in result:
            print(f"Opportunities Created: {len(result['opportunities_created'])}")
        if 'reflection_id' in result:
            print(f"Reflection ID: {result['reflection_id']}")
    
    # Exit with error if reflection failed
    if result['status'] in ['error', 'failed']:
        sys.exit(1)


if __name__ == "__main__":
    main()
