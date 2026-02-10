#!/usr/bin/env python3
"""
Agent Collaboration Protocol - Kurultai v2.0

Multi-agent task orchestration with parallel sub-agent spawning,
result synthesis, and collaborative workflows.

Author: Kurultai v2.0
Date: 2026-02-10
"""

import os
import sys
import json
import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from kurultai.kurultai_types import TaskStatus, DeliverableType


class CollaborationMode(Enum):
    """Modes of agent collaboration."""
    SEQUENTIAL = "sequential"      # Agents work in sequence
    PARALLEL = "parallel"          # Agents work simultaneously
    CONSENSUS = "consensus"        # Agents vote/consensus on result
    COMPETITIVE = "competitive"    # Agents compete, best result wins
    SPECIALIST = "specialist"      # Each agent handles different aspect


class CollaborationPhase(Enum):
    """Phases of a collaboration workflow."""
    INITIALIZED = "initialized"
    SPAWNING = "spawning"
    EXECUTING = "executing"
    SYNTHESIZING = "synthesizing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentRole:
    """Defines an agent's role in a collaboration."""
    agent_type: str
    responsibility: str
    input_from: List[str] = field(default_factory=list)
    output_to: List[str] = field(default_factory=list)
    timeout_minutes: int = 30
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_type": self.agent_type,
            "responsibility": self.responsibility,
            "input_from": self.input_from,
            "output_to": self.output_to,
            "timeout_minutes": self.timeout_minutes
        }


@dataclass
class CollaborationResult:
    """Result of a collaborative task execution."""
    collaboration_id: str
    status: CollaborationPhase
    agent_results: Dict[str, Any] = field(default_factory=dict)
    synthesized_output: Optional[Any] = None
    consensus_reached: bool = False
    execution_time_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "collaboration_id": self.collaboration_id,
            "status": self.status.value,
            "agent_results": self.agent_results,
            "synthesized_output": self.synthesized_output,
            "consensus_reached": self.consensus_reached,
            "execution_time_seconds": self.execution_time_seconds,
            "errors": self.errors
        }


@dataclass
class CollaborationTask:
    """A task that requires multi-agent collaboration."""
    id: str
    title: str
    description: str
    mode: CollaborationMode
    roles: List[AgentRole]
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "mode": self.mode.value,
            "roles": [r.to_dict() for r in self.roles],
            "created_at": self.created_at.isoformat()
        }


class AgentCollaborationProtocol:
    """
    Multi-agent task orchestration and collaboration framework.
    
    Features:
    - Parallel sub-agent spawning
    - Sequential and parallel workflow execution
    - Result synthesis across multiple agents
    - Consensus building for critical decisions
    - Collaborative task distribution
    """
    
    # Predefined collaboration templates
    TEMPLATES = {
        "research_deep_dive": {
            "mode": CollaborationMode.SPECIALIST,
            "description": "Multi-agent research with synthesis",
            "roles": [
                AgentRole("researcher", "primary_research"),
                AgentRole("analyst", "analysis_and_validation", input_from=["researcher"]),
                AgentRole("writer", "documentation", input_from=["analyst"])
            ]
        },
        "security_audit": {
            "mode": CollaborationMode.CONSENSUS,
            "description": "Multi-perspective security analysis",
            "roles": [
                AgentRole("analyst", "vulnerability_analysis"),
                AgentRole("researcher", "threat_research"),
                AgentRole("developer", "code_review"),
            ]
        },
        "complex_implementation": {
            "mode": CollaborationMode.SEQUENTIAL,
            "description": "Complex feature development",
            "roles": [
                AgentRole("analyst", "design_and_planning"),
                AgentRole("developer", "implementation", input_from=["analyst"]),
                AgentRole("analyst", "testing", input_from=["developer"])
            ]
        },
        "rapid_analysis": {
            "mode": CollaborationMode.PARALLEL,
            "description": "Fast parallel analysis",
            "roles": [
                AgentRole("analyst", "quick_analysis"),
                AgentRole("researcher", "context_gathering"),
                AgentRole("writer", "summary"),
            ]
        },
        "competitive_review": {
            "mode": CollaborationMode.COMPETITIVE,
            "description": "Multiple solutions, best wins",
            "roles": [
                AgentRole("developer", "solution_a"),
                AgentRole("developer", "solution_b"),
                AgentRole("analyst", "evaluation"),
            ]
        }
    }
    
    def __init__(self, driver):
        self.driver = driver
        self.active_collaborations: Dict[str, CollaborationTask] = {}
        self.result_cache: Dict[str, CollaborationResult] = {}
        
    def generate_collaboration_id(self) -> str:
        """Generate unique collaboration ID."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        random_suffix = hashlib.md5(str(datetime.now()).encode()).hexdigest()[:6]
        return f"collab_{timestamp}_{random_suffix}"
    
    def create_collaboration(
        self,
        title: str,
        description: str,
        mode: CollaborationMode,
        roles: List[AgentRole],
        context: Optional[Dict] = None
    ) -> CollaborationTask:
        """Create a new collaboration task."""
        task = CollaborationTask(
            id=self.generate_collaboration_id(),
            title=title,
            description=description,
            mode=mode,
            roles=roles,
            context=context or {}
        )
        self.active_collaborations[task.id] = task
        return task
    
    def create_from_template(
        self,
        template_name: str,
        title: str,
        description: str,
        context: Optional[Dict] = None
    ) -> Optional[CollaborationTask]:
        """Create collaboration from predefined template."""
        template = self.TEMPLATES.get(template_name)
        if not template:
            return None
        
        return self.create_collaboration(
            title=title,
            description=description,
            mode=template["mode"],
            roles=template["roles"],
            context=context
        )
    
    async def spawn_agents_parallel(
        self,
        task: CollaborationTask
    ) -> Dict[str, Any]:
        """
        Spawn all required agents in parallel.
        
        Returns spawn results for each agent type.
        """
        spawn_tasks = []
        agent_types_needed = list({role.agent_type for role in task.roles})
        
        for agent_type in agent_types_needed:
            spawn_tasks.append(self._spawn_single_agent(agent_type, task))
        
        results = await asyncio.gather(*spawn_tasks, return_exceptions=True)
        
        spawn_results = {}
        for i, agent_type in enumerate(agent_types_needed):
            result = results[i]
            if isinstance(result, Exception):
                spawn_results[agent_type] = {"status": "error", "error": str(result)}
            else:
                spawn_results[agent_type] = result
        
        return spawn_results
    
    async def _spawn_single_agent(
        self,
        agent_type: str,
        task: CollaborationTask
    ) -> Dict[str, Any]:
        """Spawn a single agent for collaboration."""
        try:
            # Check if agent already active
            with self.driver.session() as session:
                result = session.run('''
                    MATCH (a:Agent {type: $type})
                    WHERE a.status = 'active'
                      AND a.last_heartbeat > datetime() - duration('PT5M')
                    RETURN a.id as id
                    LIMIT 1
                ''', type=agent_type)
                
                existing = result.single()
                if existing:
                    return {
                        "status": "already_active",
                        "agent_id": existing['id'],
                        "agent_type": agent_type
                    }
            
            # Spawn new agent
            from kurultai.agent_spawner_direct import spawn_agent
            agent_id = spawn_agent(agent_type, {
                "collaboration_id": task.id,
                "collaboration_role": next(
                    (r.responsibility for r in task.roles if r.agent_type == agent_type),
                    "collaborator"
                )
            })
            
            return {
                "status": "spawned",
                "agent_id": agent_id,
                "agent_type": agent_type
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "agent_type": agent_type
            }
    
    async def execute_collaboration(
        self,
        task: CollaborationTask
    ) -> CollaborationResult:
        """
        Execute full collaboration workflow.
        
        Handles different collaboration modes:
        - SEQUENTIAL: Execute roles in order
        - PARALLEL: Execute all roles simultaneously
        - CONSENSUS: Execute and build consensus
        - COMPETITIVE: Execute and select best
        - SPECIALIST: Each role handles different aspect
        """
        start_time = datetime.now()
        result = CollaborationResult(
            collaboration_id=task.id,
            status=CollaborationPhase.SPAWNING
        )
        
        try:
            # Step 1: Spawn agents
            spawn_results = await self.spawn_agents_parallel(task)
            result.agent_results["spawn"] = spawn_results
            
            # Check if all agents spawned successfully
            failed_spawns = [
                k for k, v in spawn_results.items() 
                if v.get("status") == "error"
            ]
            if failed_spawns:
                result.errors.append(f"Failed to spawn: {failed_spawns}")
                result.status = CollaborationPhase.FAILED
                return result
            
            # Step 2: Execute based on mode
            result.status = CollaborationPhase.EXECUTING
            
            if task.mode == CollaborationMode.PARALLEL:
                execution_results = await self._execute_parallel(task)
            elif task.mode == CollaborationMode.SEQUENTIAL:
                execution_results = await self._execute_sequential(task)
            elif task.mode == CollaborationMode.CONSENSUS:
                execution_results = await self._execute_consensus(task)
            elif task.mode == CollaborationMode.COMPETITIVE:
                execution_results = await self._execute_competitive(task)
            elif task.mode == CollaborationMode.SPECIALIST:
                execution_results = await self._execute_specialist(task)
            else:
                execution_results = await self._execute_parallel(task)
            
            result.agent_results["execution"] = execution_results
            
            # Step 3: Synthesize results
            result.status = CollaborationPhase.SYNTHESIZING
            synthesis = await self._synthesize_results(task, execution_results)
            result.synthesized_output = synthesis
            
            result.status = CollaborationPhase.COMPLETED
            
        except Exception as e:
            result.status = CollaborationPhase.FAILED
            result.errors.append(str(e))
        
        result.execution_time_seconds = (datetime.now() - start_time).total_seconds()
        self.result_cache[task.id] = result
        
        # Persist to Neo4j
        self._persist_collaboration_result(task, result)
        
        return result
    
    async def _execute_parallel(
        self,
        task: CollaborationTask
    ) -> Dict[str, Any]:
        """Execute all roles in parallel."""
        execution_tasks = []
        
        for role in task.roles:
            execution_tasks.append(self._execute_role(role, task.context))
        
        results = await asyncio.gather(*execution_tasks, return_exceptions=True)
        
        execution_results = {}
        for i, role in enumerate(task.roles):
            result = results[i]
            if isinstance(result, Exception):
                execution_results[role.agent_type] = {"status": "error", "error": str(result)}
            else:
                execution_results[role.agent_type] = result
        
        return execution_results
    
    async def _execute_sequential(
        self,
        task: CollaborationTask
    ) -> Dict[str, Any]:
        """Execute roles in sequence, passing outputs forward."""
        execution_results = {}
        accumulated_context = dict(task.context)
        
        for role in task.roles:
            # Add outputs from previous roles
            for input_from in role.input_from:
                if input_from in execution_results:
                    accumulated_context[f"input_from_{input_from}"] = execution_results[input_from]
            
            result = await self._execute_role(role, accumulated_context)
            execution_results[role.agent_type] = result
            
            # Pass output to next role
            accumulated_context[f"output_from_{role.agent_type}"] = result
        
        return execution_results
    
    async def _execute_consensus(
        self,
        task: CollaborationTask
    ) -> Dict[str, Any]:
        """Execute roles and build consensus on result."""
        # First execute in parallel
        execution_results = await self._execute_parallel(task)
        
        # Build consensus
        consensus = await self._build_consensus(task, execution_results)
        execution_results["consensus"] = consensus
        
        return execution_results
    
    async def _execute_competitive(
        self,
        task: CollaborationTask
    ) -> Dict[str, Any]:
        """Execute roles and select best result."""
        # Execute in parallel
        execution_results = await self._execute_parallel(task)
        
        # Evaluate and select best
        best_result = await self._select_best_result(task, execution_results)
        execution_results["selected_best"] = best_result
        
        return execution_results
    
    async def _execute_specialist(
        self,
        task: CollaborationTask
    ) -> Dict[str, Any]:
        """Execute roles with each handling different aspects."""
        execution_results = {}
        
        for role in task.roles:
            # Each role gets context specific to their responsibility
            role_context = {
                **task.context,
                "responsibility": role.responsibility,
                "aspect": role.responsibility.replace("_", " ")
            }
            
            result = await self._execute_role(role, role_context)
            execution_results[role.agent_type] = result
        
        return execution_results
    
    async def _execute_role(
        self,
        role: AgentRole,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a single role's task."""
        # Create sub-task for this role
        sub_task_id = f"{context.get('collaboration_id', 'unknown')}_{role.agent_type}"
        
        # Persist sub-task to Neo4j
        with self.driver.session() as session:
            session.run('''
                CREATE (t:SubTask {
                    id: $id,
                    agent_type: $agent_type,
                    responsibility: $responsibility,
                    context: $context,
                    status: 'assigned',
                    created_at: datetime()
                })
            ''',
                id=sub_task_id,
                agent_type=role.agent_type,
                responsibility=role.responsibility,
                context=json.dumps(context)
            )
        
        # In a real implementation, this would wait for agent completion
        # For now, return placeholder
        return {
            "sub_task_id": sub_task_id,
            "agent_type": role.agent_type,
            "responsibility": role.responsibility,
            "status": "assigned",
            "context_received": list(context.keys())
        }
    
    async def _synthesize_results(
        self,
        task: CollaborationTask,
        execution_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Synthesize results from multiple agents into coherent output.
        
        Uses different strategies based on collaboration mode.
        """
        synthesis = {
            "collaboration_id": task.id,
            "mode": task.mode.value,
            "agents_contributed": list(execution_results.keys()),
            "synthesis_method": "intelligent_merge",
            "output": {}
        }
        
        # Merge outputs based on mode
        if task.mode == CollaborationMode.SPECIALIST:
            # Each agent contributed different aspects
            synthesis["output"] = {
                role.responsibility: execution_results.get(role.agent_type, {})
                for role in task.roles
            }
        elif task.mode == CollaborationMode.CONSENSUS:
            # Use consensus output if available
            synthesis["output"] = execution_results.get("consensus", {})
            synthesis["consensus_reached"] = True
        elif task.mode == CollaborationMode.COMPETITIVE:
            # Use best result
            synthesis["output"] = execution_results.get("selected_best", {})
            synthesis["winner"] = execution_results.get("selected_best", {}).get("agent_type")
        else:
            # Merge all outputs
            merged = {}
            for agent_type, result in execution_results.items():
                if isinstance(result, dict):
                    merged[agent_type] = result
            synthesis["output"] = merged
        
        return synthesis
    
    async def _build_consensus(
        self,
        task: CollaborationTask,
        execution_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build consensus from multiple agent outputs."""
        # Simple consensus: majority agreement on key points
        # In practice, this would use more sophisticated NLP
        
        all_findings = []
        for agent_type, result in execution_results.items():
            if isinstance(result, dict) and "findings" in result:
                all_findings.extend(result["findings"])
        
        # Count occurrences
        finding_counts = {}
        for finding in all_findings:
            key = str(finding)
            finding_counts[key] = finding_counts.get(key, 0) + 1
        
        # Find consensus (agreed by > 50% of agents)
        consensus_findings = [
            finding for finding, count in finding_counts.items()
            if count > len(task.roles) / 2
        ]
        
        return {
            "consensus_findings": consensus_findings,
            "agreement_rate": len(consensus_findings) / len(all_findings) if all_findings else 0,
            "agents_participated": len(execution_results)
        }
    
    async def _select_best_result(
        self,
        task: CollaborationTask,
        execution_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Select best result from competitive execution."""
        # Simple selection: highest score or first success
        best = None
        best_score = -1
        
        for agent_type, result in execution_results.items():
            if isinstance(result, dict):
                score = result.get("score", result.get("confidence", 0))
                if score > best_score:
                    best_score = score
                    best = {
                        "agent_type": agent_type,
                        "result": result,
                        "score": score
                    }
        
        return best or {"agent_type": "none", "result": {}, "score": 0}
    
    def _persist_collaboration_result(
        self,
        task: CollaborationTask,
        result: CollaborationResult
    ) -> None:
        """Persist collaboration result to Neo4j."""
        try:
            with self.driver.session() as session:
                session.run('''
                    CREATE (c:Collaboration {
                        id: $id,
                        title: $title,
                        mode: $mode,
                        status: $status,
                        created_at: datetime($created_at),
                        completed_at: datetime(),
                        execution_time_seconds: $exec_time,
                        consensus_reached: $consensus,
                        synthesized_output: $output
                    })
                ''',
                    id=task.id,
                    title=task.title,
                    mode=task.mode.value,
                    status=result.status.value,
                    created_at=task.created_at.isoformat(),
                    exec_time=result.execution_time_seconds,
                    consensus=result.consensus_reached,
                    output=json.dumps(result.synthesized_output)[:1000]  # Limit size
                )
        except Exception as e:
            print(f"Error persisting collaboration: {e}")
    
    def get_collaboration_stats(self) -> Dict[str, Any]:
        """Get statistics about collaborations."""
        with self.driver.session() as session:
            result = session.run('''
                MATCH (c:Collaboration)
                RETURN count(c) as total,
                       count(CASE WHEN c.status = 'completed' THEN 1 END) as completed,
                       count(CASE WHEN c.status = 'failed' THEN 1 END) as failed,
                       avg(c.execution_time_seconds) as avg_time
            ''')
            stats = result.single()
        
        return {
            "total_collaborations": stats['total'],
            "completed": stats['completed'],
            "failed": stats['failed'],
            "avg_execution_time": round(stats['avg_time'], 2) if stats['avg_time'] else 0,
            "active_collaborations": len(self.active_collaborations)
        }
    
    def list_templates(self) -> Dict[str, Any]:
        """List available collaboration templates."""
        return {
            name: {
                "mode": template["mode"].value,
                "description": template["description"],
                "roles": [r.to_dict() for r in template["roles"]]
            }
            for name, template in self.TEMPLATES.items()
        }


# Global instance
_protocol: Optional[AgentCollaborationProtocol] = None


def get_collaboration_protocol(driver) -> AgentCollaborationProtocol:
    """Get or create global collaboration protocol instance."""
    global _protocol
    if _protocol is None:
        _protocol = AgentCollaborationProtocol(driver)
    return _protocol


def reset_collaboration_protocol():
    """Reset global instance (for testing)."""
    global _protocol
    _protocol = None


# Standalone execution
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Agent Collaboration Protocol")
    parser.add_argument("--templates", action="store_true", help="List available templates")
    parser.add_argument("--stats", action="store_true", help="Show collaboration statistics")
    
    args = parser.parse_args()
    
    if args.templates:
        # Create dummy protocol for listing
        protocol = AgentCollaborationProtocol(None)
        print(json.dumps(protocol.list_templates(), indent=2))
    elif args.stats:
        from neo4j import GraphDatabase
        
        uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
        password = os.environ.get('NEO4J_PASSWORD')
        
        if not password:
            print("NEO4J_PASSWORD not set")
            sys.exit(1)
        
        driver = GraphDatabase.driver(uri, auth=('neo4j', password))
        protocol = get_collaboration_protocol(driver)
        print(json.dumps(protocol.get_collaboration_stats(), indent=2))
        driver.close()
    else:
        parser.print_help()
