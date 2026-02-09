"""
Autonomous Task Orchestrator
Ensures all tasks get assigned, delegated, and started without manual intervention
"""
import os
import json
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass
from neo4j import GraphDatabase

@dataclass
class TaskAssignment:
    """Task assignment decision"""
    task_id: str
    assignee: str
    reason: str
    priority: int

class AutonomousOrchestrator:
    """
    Kublai Autonomous Task Orchestrator
    
    Runs every heartbeat cycle to:
    1. Detect pending tasks without assignees
    2. Auto-assign based on capability matching
    3. Create AgentMessages for delegation
    4. Spawn agents if dormant
    5. Transition tasks to in_progress
    """
    
    # Agent capability mapping
    AGENT_CAPABILITIES = {
        'Kublai': ['orchestration', 'routing', 'synthesis', 'delegation'],
        'Möngke': ['research', 'web_search', 'api_analysis', 'knowledge_gap'],
        'Chagatai': ['writing', 'documentation', 'summarization', 'content'],
        'Temüjin': ['development', 'coding', 'testing', 'implementation'],
        'Jochi': ['analysis', 'security', 'testing', 'audit', 'review'],
        'Ögedei': ['operations', 'monitoring', 'health_check', 'failover']
    }
    
    # Task type to agent mapping
    TASK_TYPE_AGENTS = {
        'research': 'Möngke',
        'web_search': 'Möngke',
        'write': 'Chagatai',
        'document': 'Chagatai',
        'code': 'Temüjin',
        'develop': 'Temüjin',
        'implement': 'Temüjin',
        'test': 'Jochi',
        'analyze': 'Jochi',
        'audit': 'Jochi',
        'security': 'Jochi',
        'monitor': 'Ögedei',
        'ops': 'Ögedei',
        'health': 'Ögedei',
        'delegate': 'Kublai',
        'route': 'Kublai',
        'synthesize': 'Kublai'
    }
    
    def __init__(self, neo4j_driver):
        self.driver = neo4j_driver
        self.stats = {
            'tasks_assigned': 0,
            'tasks_started': 0,
            'agents_spawned': 0,
            'messages_created': 0
        }
    
    async def orchestrate_cycle(self) -> Dict:
        """
        Main orchestration cycle - runs every heartbeat
        Returns stats on actions taken
        """
        self.stats = {
            'tasks_assigned': 0,
            'tasks_started': 0,
            'agents_spawned': 0,
            'messages_created': 0,
            'errors': []
        }
        
        try:
            # Step 1: Assign unassigned tasks
            await self._assign_pending_tasks()
            
            # Step 2: Create AgentMessages for delegation
            await self._create_delegation_messages()
            
            # Step 3: Spawn dormant agents
            await self._spawn_needed_agents()
            
            # Step 4: Auto-start ready tasks
            await self._start_ready_tasks()
            
        except Exception as e:
            self.stats['errors'].append(str(e))
        
        return self.stats
    
    async def _assign_pending_tasks(self):
        """Find and assign unassigned pending tasks"""
        with self.driver.session() as session:
            # Find tasks without assignees
            result = session.run("""
                MATCH (t:Task {status: 'pending'})
                WHERE t.assigned_to IS NULL OR t.assigned_to = ''
                RETURN t.id as id, t.name as name, t.payload as payload
                LIMIT 10
            """)
            
            for record in result:
                task_id = record["id"]
                name = record["name"] or ""
                payload = record["payload"]
                
                # Determine best agent
                assignee = self._determine_assignee(name, payload)
                
                # Assign task
                session.run("""
                    MATCH (t:Task {id: $task_id})
                    SET t.assigned_to = $assignee,
                        t.auto_assigned = true,
                        t.assigned_at = datetime(),
                        t.assigned_by = 'Kublai_AutonomousOrchestrator'
                """, task_id=task_id, assignee=assignee)
                
                self.stats['tasks_assigned'] += 1
                
                # Log assignment
                session.run("""
                    CREATE (a:AutoAssignment {
                        id: randomUUID(),
                        task_id: $task_id,
                        assignee: $assignee,
                        reason: $reason,
                        created_at: datetime()
                    })
                """, task_id=task_id, assignee=assignee, 
                     reason=f"Matched to {assignee} based on task type")
    
    def _determine_assignee(self, name: str, payload: dict) -> str:
        """Determine best agent for task based on name/payload"""
        text = f"{name} {json.dumps(payload) if payload else ''}".lower()
        
        # Check for explicit agent assignment in payload
        if payload and isinstance(payload, dict):
            if 'assigned_to' in payload and payload['assigned_to']:
                return payload['assigned_to']
            if 'agent' in payload and payload['agent']:
                return payload['agent']
        
        # Match by keywords
        for keyword, agent in self.TASK_TYPE_AGENTS.items():
            if keyword in text:
                return agent
        
        # Default to Kublai for unknown tasks
        return 'Kublai'
    
    async def _create_delegation_messages(self):
        """Create AgentMessages for tasks that need delegation"""
        with self.driver.session() as session:
            # Find tasks with assignees but no AgentMessage
            result = session.run("""
                MATCH (t:Task {status: 'pending'})
                WHERE t.assigned_to IS NOT NULL
                  AND NOT EXISTS {
                      MATCH (m:AgentMessage)
                      WHERE m.payload CONTAINS t.id
                  }
                RETURN t.id as id, t.name as name, 
                       t.assigned_to as assignee, t.payload as payload
                LIMIT 10
            """)
            
            for record in result:
                task_id = record["id"]
                assignee = record["assignee"]
                name = record["name"]
                payload = record["payload"] or {}
                
                # Create AgentMessage
                msg_id = str(uuid.uuid4())
                msg_payload = json.dumps({
                    "task_id": task_id,
                    "task_name": name,
                    "auto_delegated": True,
                    **payload
                })
                
                session.run("""
                    CREATE (m:AgentMessage {
                        id: $msg_id,
                        type: 'task_assignment',
                        status: 'pending',
                        sender: 'Kublai',
                        recipient: $recipient,
                        payload: $payload,
                        created_at: datetime(),
                        priority: 1,
                        auto_created: true
                    })
                """, msg_id=msg_id, recipient=assignee, payload=msg_payload)
                
                self.stats['messages_created'] += 1
    
    async def _spawn_needed_agents(self):
        """Spawn agents that have pending tasks but are dormant"""
        with self.driver.session() as session:
            # Find agents with pending tasks but no recent heartbeat
            result = session.run("""
                MATCH (t:Task {status: 'pending'})
                MATCH (a:Agent {name: t.assigned_to})
                WHERE a.last_heartbeat IS NULL 
                   OR duration.between(a.last_heartbeat, datetime()).seconds > 300
                RETURN DISTINCT a.name as agent_name, count(t) as task_count
                ORDER BY task_count DESC
                LIMIT 5
            """)
            
            for record in result:
                agent_name = record["agent_name"]
                task_count = record["task_count"]
                
                # Spawn the agent
                await self._spawn_agent(agent_name)
                self.stats['agents_spawned'] += 1
    
    async def _spawn_agent(self, agent_name: str):
        """Spawn an agent via Signal or HTTP"""
        # Log spawn attempt
        with self.driver.session() as session:
            session.run("""
                CREATE (s:AgentSpawn {
                    id: randomUUID(),
                    agent: $agent,
                    triggered_by: 'AutonomousOrchestrator',
                    method: 'signal',
                    created_at: datetime(),
                    status: 'pending'
                })
            """, agent=agent_name)
        
        # In production, this would send Signal message or HTTP request
        # For now, we log it and rely on heartbeat wake-up
    
    async def _start_ready_tasks(self):
        """Auto-start tasks that are ready (have assignee and message)"""
        with self.driver.session() as session:
            # Find tasks with assignees and AgentMessages but still pending
            result = session.run("""
                MATCH (t:Task {status: 'pending'})
                WHERE t.assigned_to IS NOT NULL
                  AND EXISTS {
                      MATCH (m:AgentMessage)
                      WHERE m.payload CONTAINS t.id
                        AND m.status = 'pending'
                  }
                RETURN t.id as id, t.assigned_to as assignee
                LIMIT 10
            """)
            
            for record in result:
                task_id = record["id"]
                assignee = record["assignee"]
                
                # Update task to in_progress
                session.run("""
                    MATCH (t:Task {id: $task_id})
                    SET t.status = 'in_progress',
                        t.started_at = datetime(),
                        t.started_by = 'Kublai_AutonomousOrchestrator',
                        t.auto_started = true
                """, task_id=task_id)
                
                self.stats['tasks_started'] += 1
    
    def get_orchestration_summary(self) -> str:
        """Get human-readable summary of last orchestration"""
        lines = [
            "Autonomous Orchestration Results:",
            f"  Tasks Auto-Assigned: {self.stats['tasks_assigned']}",
            f"  Tasks Auto-Started: {self.stats['tasks_started']}",
            f"  AgentMessages Created: {self.stats['messages_created']}",
            f"  Agents Spawned: {self.stats['agents_spawned']}"
        ]
        
        if self.stats['errors']:
            lines.append(f"  Errors: {len(self.stats['errors'])}")
        
        return "\n".join(lines)

# Singleton instance
_orchestrator: Optional[AutonomousOrchestrator] = None

def get_orchestrator(neo4j_driver=None):
    """Get or create the autonomous orchestrator singleton"""
    global _orchestrator
    if _orchestrator is None:
        if neo4j_driver is None:
            raise ValueError("Neo4j driver required for initial setup")
        _orchestrator = AutonomousOrchestrator(neo4j_driver)
    return _orchestrator
