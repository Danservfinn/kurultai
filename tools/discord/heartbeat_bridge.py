#!/usr/bin/env python3
"""
Kurultai Heartbeat → Discord Bridge
Integrates the 5-minute heartbeat system with Discord deliberation channels.

This module:
- Polls Neo4j for agent heartbeat status
- Sends status summaries to #heartbeat-log
- Announces completed tasks to #council-chamber
- Sends critical alerts to #announcements
- Allows agents to react and respond to events
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from discord.deliberation_client import (
    KurultaiDiscordClient,
    AgentRole,
    AGENT_PERSONALITIES,
    create_discord_client,
    HeartbeatDiscordIntegration,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kurultai-heartbeat-bridge")


@dataclass
class AgentHeartbeat:
    """Agent heartbeat data structure."""
    agent: AgentRole
    status: str  # "healthy", "warning", "critical"
    last_seen: datetime
    tasks_active: int
    tasks_completed: int
    current_task: Optional[str] = None
    message: Optional[str] = None


@dataclass
class CompletedTask:
    """Completed task data."""
    agent: AgentRole
    task_name: str
    completed_at: datetime
    details: Optional[str] = None


@dataclass
class CriticalAlert:
    """Critical alert data."""
    title: str
    message: str
    severity: str  # "high", "medium", "low"
    timestamp: datetime


class Neo4jHeartbeatPoller:
    """Polls Neo4j for agent heartbeat data."""
    
    def __init__(self, neo4j_uri: Optional[str] = None, neo4j_auth: Optional[tuple] = None):
        self.neo4j_uri = neo4j_uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.neo4j_user = neo4j_auth[0] if neo4j_auth else os.getenv("NEO4J_USER", "neo4j")
        self.neo4j_password = neo4j_auth[1] if neo4j_auth else os.getenv("NEO4J_PASSWORD", "")
        self.driver = None
    
    def connect(self):
        """Connect to Neo4j."""
        try:
            from neo4j import GraphDatabase
            self.driver = GraphDatabase.driver(
                self.neo4j_uri,
                auth=(self.neo4j_user, self.neo4j_password)
            )
            logger.info("Connected to Neo4j")
        except ImportError:
            logger.warning("neo4j package not installed, using mock data")
            self.driver = None
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            self.driver = None
    
    def disconnect(self):
        """Disconnect from Neo4j."""
        if self.driver:
            self.driver.close()
            self.driver = None
    
    def get_agent_statuses(self) -> Dict[AgentRole, Dict[str, Any]]:
        """Fetch current status of all agents from Neo4j."""
        if not self.driver:
            # Return mock data for testing
            return self._get_mock_statuses()
        
        try:
            with self.driver.session() as session:
                result = session.run("""
                    MATCH (a:Agent)
                    RETURN a.name as name, a.status as status, 
                           a.last_heartbeat as last_heartbeat,
                           a.tasks_active as tasks_active,
                           a.tasks_completed as tasks_completed
                """)
                
                statuses = {}
                for record in result:
                    name = record["name"].lower()
                    try:
                        role = AgentRole(name)
                        statuses[role] = {
                            "status": record["status"] or "unknown",
                            "healthy": record["status"] == "healthy",
                            "last_heartbeat": record["last_heartbeat"],
                            "tasks_active": record["tasks_active"] or 0,
                            "tasks_completed": record["tasks_completed"] or 0,
                        }
                    except ValueError:
                        continue
                
                return statuses
        except Exception as e:
            logger.error(f"Error querying Neo4j: {e}")
            return self._get_mock_statuses()
    
    def get_completed_tasks(self, since: Optional[datetime] = None) -> List[CompletedTask]:
        """Get tasks completed since last check."""
        if not self.driver:
            return []
        
        since = since or (datetime.utcnow() - timedelta(minutes=5))
        
        try:
            with self.driver.session() as session:
                result = session.run("""
                    MATCH (t:Task)
                    WHERE t.status = 'completed'
                    AND t.completed_at > $since
                    RETURN t.name as name, t.agent as agent,
                           t.completed_at as completed_at, t.summary as summary
                """, since=since.isoformat())
                
                tasks = []
                for record in result:
                    try:
                        role = AgentRole(record["agent"].lower())
                        tasks.append(CompletedTask(
                            agent=role,
                            task_name=record["name"],
                            completed_at=datetime.fromisoformat(record["completed_at"]),
                            details=record["summary"]
                        ))
                    except (ValueError, TypeError):
                        continue
                
                return tasks
        except Exception as e:
            logger.error(f"Error querying completed tasks: {e}")
            return []
    
    def get_critical_alerts(self) -> List[CriticalAlert]:
        """Get any critical alerts from the system."""
        if not self.driver:
            return []
        
        try:
            with self.driver.session() as session:
                result = session.run("""
                    MATCH (a:Alert)
                    WHERE a.status = 'active'
                    AND a.severity IN ['high', 'critical']
                    RETURN a.title as title, a.message as message,
                           a.severity as severity, a.created_at as created_at
                """)
                
                alerts = []
                for record in result:
                    alerts.append(CriticalAlert(
                        title=record["title"],
                        message=record["message"],
                        severity=record["severity"],
                        timestamp=datetime.fromisoformat(record["created_at"])
                    ))
                
                return alerts
        except Exception as e:
            logger.error(f"Error querying alerts: {e}")
            return []
    
    def _get_mock_statuses(self) -> Dict[AgentRole, Dict[str, Any]]:
        """Generate mock agent statuses for testing."""
        return {
            AgentRole.KUBLAI: {
                "status": "healthy",
                "healthy": True,
                "last_heartbeat": datetime.utcnow().isoformat(),
                "tasks_active": 3,
                "tasks_completed": 47,
            },
            AgentRole.MONGKE: {
                "status": "healthy",
                "healthy": True,
                "last_heartbeat": datetime.utcnow().isoformat(),
                "tasks_active": 1,
                "tasks_completed": 23,
            },
            AgentRole.CHAGATAI: {
                "status": "healthy",
                "healthy": True,
                "last_heartbeat": datetime.utcnow().isoformat(),
                "tasks_active": 0,
                "tasks_completed": 31,
            },
            AgentRole.TEMUJIN: {
                "status": "healthy",
                "healthy": True,
                "last_heartbeat": datetime.utcnow().isoformat(),
                "tasks_active": 2,
                "tasks_completed": 56,
            },
            AgentRole.JOCHI: {
                "status": "healthy",
                "healthy": True,
                "last_heartbeat": datetime.utcnow().isoformat(),
                "tasks_active": 0,
                "tasks_completed": 19,
            },
            AgentRole.OGEDEI: {
                "status": "healthy",
                "healthy": True,
                "last_heartbeat": datetime.utcnow().isoformat(),
                "tasks_active": 1,
                "tasks_completed": 42,
            },
        }


class HeartbeatBridge:
    """
    Main bridge class that connects Neo4j heartbeats to Discord.
    
    Runs on the 5-minute heartbeat schedule and:
    1. Polls agent statuses from Neo4j
    2. Formats and sends to Discord channels
    3. Handles responses and reactions
    """
    
    def __init__(self):
        self.discord = create_discord_client()
        self.integration = HeartbeatDiscordIntegration(self.discord)
        self.poller = Neo4jHeartbeatPoller()
        self.last_check = datetime.utcnow() - timedelta(minutes=5)
        self.running = False
    
    async def initialize(self):
        """Initialize connections."""
        logger.info("Initializing Heartbeat Bridge...")
        self.poller.connect()
        logger.info("✅ Bridge initialized")
    
    async def shutdown(self):
        """Clean up connections."""
        logger.info("Shutting down Heartbeat Bridge...")
        self.poller.disconnect()
        logger.info("✅ Bridge shutdown complete")
    
    async def process_heartbeat(self) -> Dict[str, Any]:
        """
        Process a single heartbeat cycle.
        
        Returns:
            Summary of actions taken
        """
        logger.info("Processing heartbeat...")
        
        # Fetch data from Neo4j
        agent_statuses = self.poller.get_agent_statuses()
        completed_tasks = self.poller.get_completed_tasks(self.last_check)
        alerts = self.poller.get_critical_alerts()
        
        # Update last check time
        self.last_check = datetime.utcnow()
        
        # Send to Discord
        await self.integration.process_heartbeat(
            agent_statuses,
            completed_tasks,
            alerts
        )
        
        # Generate summary
        summary = {
            "timestamp": self.last_check.isoformat(),
            "agents_reporting": len(agent_statuses),
            "healthy_agents": sum(1 for s in agent_statuses.values() if s.get("healthy")),
            "completed_tasks": len(completed_tasks),
            "alerts": len(alerts),
        }
        
        logger.info(f"Heartbeat processed: {summary}")
        return summary
    
    async def run_single(self):
        """Run one heartbeat cycle."""
        await self.initialize()
        try:
            result = await self.process_heartbeat()
            return result
        finally:
            await self.shutdown()
    
    async def run_continuous(self, interval_minutes: int = 5):
        """
        Run continuous heartbeat processing.
        
        Args:
            interval_minutes: Minutes between heartbeats
        """
        await self.initialize()
        self.running = True
        
        logger.info(f"Starting continuous heartbeat (interval: {interval_minutes}m)")
        
        try:
            while self.running:
                await self.process_heartbeat()
                
                # Wait for next interval
                await asyncio.sleep(interval_minutes * 60)
        except asyncio.CancelledError:
            logger.info("Heartbeat loop cancelled")
        finally:
            await self.shutdown()
    
    def stop(self):
        """Stop continuous processing."""
        self.running = False


async def send_status_update(channel: str = "council-chamber"):
    """
    Send a one-off status update to Discord.
    
    Usage:
        python heartbeat_bridge.py --status
    """
    bridge = HeartbeatBridge()
    await bridge.initialize()
    
    try:
        # Get current status
        statuses = bridge.poller.get_agent_statuses()
        
        # Send as Kublai
        await bridge.discord.send_heartbeat_summary(statuses)
        
        logger.info(f"Status update sent to #{channel}")
    finally:
        await bridge.shutdown()


async def announce_task(agent_name: str, task_name: str, details: Optional[str] = None):
    """
    Announce a task completion manually.
    
    Usage:
        python heartbeat_bridge.py --announce temujin "Fixed bug #123"
    """
    bridge = HeartbeatBridge()
    
    try:
        agent = AgentRole(agent_name.lower())
        await bridge.discord.announce_task_completion(agent, task_name, details)
        logger.info(f"Announced {agent_name}'s task: {task_name}")
    except ValueError:
        logger.error(f"Unknown agent: {agent_name}")
        logger.info(f"Valid agents: {[r.value for r in AgentRole]}")


async def send_alert(title: str, message: str, severity: str = "high"):
    """
    Send a critical alert to Discord.
    
    Usage:
        python heartbeat_bridge.py --alert "System Down" "Neo4j connection lost"
    """
    bridge = HeartbeatBridge()
    await bridge.discord.send_critical_alert(title, message, severity)
    logger.info(f"Alert sent: {title}")


def main():
    """Main entry point with CLI args."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Kurultai Heartbeat → Discord Bridge"
    )
    parser.add_argument(
        "--continuous", "-c",
        action="store_true",
        help="Run continuous heartbeat (default: 5 min interval)"
    )
    parser.add_argument(
        "--interval", "-i",
        type=int,
        default=5,
        help="Heartbeat interval in minutes (default: 5)"
    )
    parser.add_argument(
        "--status", "-s",
        action="store_true",
        help="Send one-off status update"
    )
    parser.add_argument(
        "--announce", "-a",
        nargs=2,
        metavar=("AGENT", "TASK"),
        help="Announce task completion: --announce temujin 'Fixed bug'"
    )
    parser.add_argument(
        "--alert",
        nargs=2,
        metavar=("TITLE", "MESSAGE"),
        help="Send critical alert: --alert 'Title' 'Message'"
    )
    parser.add_argument(
        "--severity",
        default="high",
        choices=["high", "medium", "low"],
        help="Alert severity (default: high)"
    )
    
    args = parser.parse_args()
    
    if args.status:
        asyncio.run(send_status_update())
    elif args.announce:
        asyncio.run(announce_task(args.announce[0], args.announce[1]))
    elif args.alert:
        asyncio.run(send_alert(args.alert[0], args.alert[1], args.severity))
    elif args.continuous:
        bridge = HeartbeatBridge()
        try:
            asyncio.run(bridge.run_continuous(args.interval))
        except KeyboardInterrupt:
            logger.info("Received interrupt, shutting down...")
            bridge.stop()
    else:
        # Single heartbeat
        bridge = HeartbeatBridge()
        result = asyncio.run(bridge.run_single())
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
