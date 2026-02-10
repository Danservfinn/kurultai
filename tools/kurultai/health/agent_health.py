"""
Agent Health Deep Dive Module

Phase 4: Agent Health Deep Dive
Monitors agent heartbeats, task completion rates, error rates, spawn success, and capabilities.

Tasks Implemented:
- H4-T1: Heartbeat freshness
- H4-T2: Task completion rate
- H4-T3: Error rate tracking
- H4-T4: Spawn success rate
- H4-T5: Capability drift
"""

import os
import time
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from neo4j import GraphDatabase, Driver

from .base import BaseHealthChecker, HealthResult, HealthStatus

logger = logging.getLogger(__name__)

# Configuration
NEO4J_URI = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.environ.get('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD', '')

# Thresholds
AGENT_THRESHOLDS = {
    'heartbeat_max_age_minutes': 2,
    'task_success_rate': 0.95,  # Alert if < 95%
    'error_rate': 0.05,  # Alert if > 5%
    'spawn_success_rate': 0.90,  # Alert if < 90%
}

# Expected agents
EXPECTED_AGENTS = ['main', 'researcher', 'writer', 'developer', 'analyst', 'ops']


class AgentHealthChecker(BaseHealthChecker):
    """Agent health deep dive monitoring.
    
    Monitors:
    - Heartbeat freshness for all agents
    - Task completion rates
    - Error rate tracking
    - Spawn success rates
    - Capability drift detection
    """
    
    def __init__(
        self,
        timeout_seconds: float = 30.0,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        thresholds: Optional[Dict[str, float]] = None,
        expected_agents: Optional[List[str]] = None
    ):
        super().__init__(name="agent", timeout_seconds=timeout_seconds)
        self.uri = uri or NEO4J_URI
        self.user = user or NEO4J_USER
        self.password = password or NEO4J_PASSWORD
        self.thresholds = {**AGENT_THRESHOLDS, **(thresholds or {})}
        self.expected_agents = expected_agents or EXPECTED_AGENTS
        self._driver: Optional[Driver] = None
    
    def _get_driver(self) -> Driver:
        """Get or create Neo4j driver."""
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password)
            )
        return self._driver
    
    async def check(self) -> HealthResult:
        """Run all agent health checks.
        
        Returns:
            HealthResult with aggregated status of all agent health metrics
        """
        start_time = time.time()
        
        try:
            # Run all checks
            checks = [
                await self.check_heartbeat_freshness(),
                await self.check_task_completion_rate(),
                await self.check_error_rate(),
                await self.check_spawn_success(),
                await self.check_capability_drift(),
            ]
            
            # Aggregate results
            critical_count = sum(1 for c in checks if c.status == HealthStatus.CRITICAL)
            warning_count = sum(1 for c in checks if c.status == HealthStatus.WARNING)
            
            if critical_count > 0:
                overall_status = HealthStatus.CRITICAL
                message = f"Agent health critical: {critical_count} critical issues"
            elif warning_count > 0:
                overall_status = HealthStatus.WARNING
                message = f"Agent health warning: {warning_count} warnings"
            else:
                overall_status = HealthStatus.HEALTHY
                message = "Agent health: all checks passed"
            
            details = {
                'checks': [c.to_dict() for c in checks],
                'healthy_checks': sum(1 for c in checks if c.status == HealthStatus.HEALTHY),
                'warning_checks': warning_count,
                'critical_checks': critical_count,
                'expected_agents': self.expected_agents,
            }
            
        except Exception as e:
            overall_status = HealthStatus.CRITICAL
            message = f"Agent health check failed: {e}"
            details = {'error': str(e)}
        
        response_time = (time.time() - start_time) * 1000
        
        return HealthResult(
            component='agent',
            status=overall_status,
            message=message,
            details=details,
            response_time_ms=response_time
        )
    
    async def check_heartbeat_freshness(self) -> HealthResult:
        """H4-T1: Check all agent heartbeats for staleness.
        
        Returns:
            HealthResult with heartbeat status
        """
        start_time = time.time()
        
        try:
            driver = self._get_driver()
            
            with driver.session() as session:
                # Check for stale heartbeats
                result = session.run('''
                    MATCH (a:Agent)
                    RETURN a.name as name,
                           a.infra_heartbeat as infra_heartbeat,
                           a.last_heartbeat as last_heartbeat,
                           a.status as status
                ''')
                
                agents = []
                stale_agents = []
                missing_agents = []
                
                found_names = set()
                
                for record in result:
                    name = record['name']
                    found_names.add(name)
                    
                    infra_hb = record['infra_heartbeat']
                    last_hb = record['last_heartbeat']
                    status = record['status']
                    
                    agent_info = {
                        'name': name,
                        'status': status,
                        'infra_heartbeat': infra_hb.isoformat() if infra_hb else None,
                        'last_heartbeat': last_hb.isoformat() if last_hb else None,
                    }
                    
                    # Check if heartbeats are stale
                    now = datetime.now()
                    max_age = timedelta(minutes=self.thresholds['heartbeat_max_age_minutes'])
                    
                    is_stale = False
                    if infra_hb and (now - infra_hb.replace(tzinfo=None)) > max_age:
                        is_stale = True
                        agent_info['stale_reason'] = 'infra_heartbeat'
                    elif last_hb and (now - last_hb.replace(tzinfo=None)) > max_age:
                        is_stale = True
                        agent_info['stale_reason'] = 'last_heartbeat'
                    
                    if is_stale:
                        stale_agents.append(agent_info)
                    
                    agents.append(agent_info)
                
                # Check for missing agents
                for expected in self.expected_agents:
                    if expected not in found_names:
                        missing_agents.append(expected)
                
                response_time = (time.time() - start_time) * 1000
                
                if missing_agents:
                    return HealthResult(
                        component='agent_heartbeats',
                        status=HealthStatus.CRITICAL,
                        message=f"Missing agents: {', '.join(missing_agents)}",
                        details={
                            'agents_found': len(agents),
                            'agents_expected': len(self.expected_agents),
                            'missing_agents': missing_agents,
                            'stale_agents': stale_agents
                        },
                        response_time_ms=response_time
                    )
                elif stale_agents:
                    return HealthResult(
                        component='agent_heartbeats',
                        status=HealthStatus.WARNING,
                        message=f"Stale heartbeats: {len(stale_agents)} agents",
                        details={
                            'agents': agents,
                            'stale_agents': stale_agents,
                            'threshold_minutes': self.thresholds['heartbeat_max_age_minutes']
                        },
                        response_time_ms=response_time
                    )
                else:
                    return HealthResult(
                        component='agent_heartbeats',
                        status=HealthStatus.HEALTHY,
                        message=f"All {len(agents)} agents have fresh heartbeats",
                        details={'agents': agents},
                        response_time_ms=response_time
                    )
                    
        except Exception as e:
            return HealthResult(
                component='agent_heartbeats',
                status=HealthStatus.UNKNOWN,
                message="Could not check agent heartbeats",
                error=str(e)
            )
    
    async def check_task_completion_rate(self) -> HealthResult:
        """H4-T2: Track task success/failure rates.
        
        Returns:
            HealthResult with task completion status
        """
        start_time = time.time()
        
        try:
            driver = self._get_driver()
            
            with driver.session() as session:
                # Get task stats for last hour
                result = session.run('''
                    MATCH (t:Task)
                    WHERE t.created_at > datetime() - duration('PT1H')
                    RETURN t.status as status, count(*) as count
                ''')
                
                status_counts = {}
                for record in result:
                    status_counts[record['status']] = record['count']
                
                total = sum(status_counts.values())
                completed = status_counts.get('completed', 0)
                failed = status_counts.get('failed', 0)
                
                # Calculate success rate
                finished = completed + failed
                success_rate = completed / finished if finished > 0 else 1.0
                
                response_time = (time.time() - start_time) * 1000
                
                details = {
                    'total_tasks_last_hour': total,
                    'completed': completed,
                    'failed': failed,
                    'success_rate': round(success_rate, 4),
                    'threshold': self.thresholds['task_success_rate'],
                    'status_breakdown': status_counts
                }
                
                if finished > 0 and success_rate < self.thresholds['task_success_rate']:
                    return HealthResult(
                        component='agent_task_completion',
                        status=HealthStatus.WARNING,
                        message=f"Task success rate low: {success_rate:.1%}",
                        details=details,
                        response_time_ms=response_time
                    )
                else:
                    return HealthResult(
                        component='agent_task_completion',
                        status=HealthStatus.HEALTHY,
                        message=f"Task success rate: {success_rate:.1%} ({completed}/{finished})",
                        details=details,
                        response_time_ms=response_time
                    )
                    
        except Exception as e:
            return HealthResult(
                component='agent_task_completion',
                status=HealthStatus.UNKNOWN,
                message="Could not check task completion rate",
                error=str(e)
            )
    
    async def check_error_rate(self) -> HealthResult:
        """H4-T3: Monitor agent error rates.
        
        Returns:
            HealthResult with error rate status
        """
        start_time = time.time()
        
        try:
            driver = self._get_driver()
            
            with driver.session() as session:
                # Get error counts by agent
                result = session.run('''
                    MATCH (t:Task)
                    WHERE t.created_at > datetime() - duration('PT1H')
                    OPTIONAL MATCH (t)-[:EXECUTED_BY]-(a:Agent)
                    RETURN a.name as agent, 
                           count(*) as total,
                           sum(CASE WHEN t.status = 'failed' THEN 1 ELSE 0 END) as errors
                ''')
                
                agent_errors = []
                total_tasks = 0
                total_errors = 0
                
                for record in result:
                    agent = record['agent'] or 'unknown'
                    total = record['total']
                    errors = record['errors']
                    error_rate = errors / total if total > 0 else 0
                    
                    agent_errors.append({
                        'agent': agent,
                        'total': total,
                        'errors': errors,
                        'error_rate': round(error_rate, 4)
                    })
                    
                    total_tasks += total
                    total_errors += errors
                
                overall_error_rate = total_errors / total_tasks if total_tasks > 0 else 0
                
                response_time = (time.time() - start_time) * 1000
                
                details = {
                    'total_tasks': total_tasks,
                    'total_errors': total_errors,
                    'overall_error_rate': round(overall_error_rate, 4),
                    'threshold': self.thresholds['error_rate'],
                    'by_agent': agent_errors
                }
                
                if overall_error_rate > self.thresholds['error_rate']:
                    return HealthResult(
                        component='agent_error_rate',
                        status=HealthStatus.WARNING,
                        message=f"Error rate high: {overall_error_rate:.1%}",
                        details=details,
                        response_time_ms=response_time
                    )
                else:
                    return HealthResult(
                        component='agent_error_rate',
                        status=HealthStatus.HEALTHY,
                        message=f"Error rate healthy: {overall_error_rate:.1%}",
                        details=details,
                        response_time_ms=response_time
                    )
                    
        except Exception as e:
            return HealthResult(
                component='agent_error_rate',
                status=HealthStatus.UNKNOWN,
                message="Could not check error rate",
                error=str(e)
            )
    
    async def check_spawn_success(self) -> HealthResult:
        """H4-T4: Track agent spawn success rates.
        
        Returns:
            HealthResult with spawn success status
        """
        start_time = time.time()
        
        try:
            driver = self._get_driver()
            
            with driver.session() as session:
                # Look for spawn-related tasks
                result = session.run('''
                    MATCH (t:Task)
                    WHERE t.type CONTAINS 'spawn' 
                       OR t.description CONTAINS 'spawn'
                       OR t.description CONTAINS 'delegate'
                    RETURN t.status as status, count(*) as count
                ''')
                
                spawn_counts = {}
                for record in result:
                    spawn_counts[record['status']] = record['count']
                
                total_spawns = sum(spawn_counts.values())
                successful = spawn_counts.get('completed', 0)
                failed = spawn_counts.get('failed', 0)
                
                spawn_success_rate = successful / (successful + failed) if (successful + failed) > 0 else 1.0
                
                response_time = (time.time() - start_time) * 1000
                
                details = {
                    'total_spawns': total_spawns,
                    'successful': successful,
                    'failed': failed,
                    'spawn_success_rate': round(spawn_success_rate, 4),
                    'threshold': self.thresholds['spawn_success_rate'],
                    'status_breakdown': spawn_counts
                }
                
                if spawn_success_rate < self.thresholds['spawn_success_rate'] and total_spawns > 0:
                    return HealthResult(
                        component='agent_spawn_success',
                        status=HealthStatus.WARNING,
                        message=f"Spawn success rate low: {spawn_success_rate:.1%}",
                        details=details,
                        response_time_ms=response_time
                    )
                else:
                    return HealthResult(
                        component='agent_spawn_success',
                        status=HealthStatus.HEALTHY,
                        message=f"Spawn success rate: {spawn_success_rate:.1%}",
                        details=details,
                        response_time_ms=response_time
                    )
                    
        except Exception as e:
            return HealthResult(
                component='agent_spawn_success',
                status=HealthStatus.UNKNOWN,
                message="Could not check spawn success rate",
                error=str(e)
            )
    
    async def check_capability_drift(self) -> HealthResult:
        """H4-T5: Check for capability gaps.
        
        Returns:
            HealthResult with capability drift status
        """
        start_time = time.time()
        
        try:
            driver = self._get_driver()
            
            with driver.session() as session:
                # Get expected capabilities per agent
                expected_capabilities = {
                    'main': ['task_management', 'orchestration', 'status_synthesis'],
                    'researcher': ['research', 'knowledge_gap_analysis', 'ecosystem_intelligence'],
                    'writer': ['content_creation', 'reflection_consolidation', 'documentation'],
                    'developer': ['code_generation', 'testing', 'smoke_tests', 'full_tests'],
                    'analyst': ['analysis', 'mvs_scoring', 'memory_curation', 'vector_dedup'],
                    'ops': ['operations', 'health_checks', 'file_consistency', 'notion_sync']
                }
                
                # Get actual capabilities from registry
                result = session.run('''
                    MATCH (a:Agent)
                    OPTIONAL MATCH (a)-[:HAS_CAPABILITY]->(c:Capability)
                    RETURN a.name as agent, collect(c.name) as capabilities
                ''')
                
                agent_capabilities = {}
                drift_detected = []
                
                for record in result:
                    agent = record['agent']
                    capabilities = record['capabilities'] or []
                    agent_capabilities[agent] = capabilities
                    
                    # Check for missing expected capabilities
                    expected = expected_capabilities.get(agent, [])
                    missing = [c for c in expected if c not in capabilities]
                    
                    if missing:
                        drift_detected.append({
                            'agent': agent,
                            'missing_capabilities': missing,
                            'expected': expected,
                            'actual': capabilities
                        })
                
                response_time = (time.time() - start_time) * 1000
                
                details = {
                    'agents_checked': len(agent_capabilities),
                    'agent_capabilities': agent_capabilities,
                    'drift_detected': drift_detected,
                    'drift_count': len(drift_detected)
                }
                
                if drift_detected:
                    return HealthResult(
                        component='agent_capability_drift',
                        status=HealthStatus.WARNING,
                        message=f"Capability drift detected in {len(drift_detected)} agents",
                        details=details,
                        response_time_ms=response_time
                    )
                else:
                    return HealthResult(
                        component='agent_capability_drift',
                        status=HealthStatus.HEALTHY,
                        message="All agents have expected capabilities",
                        details=details,
                        response_time_ms=response_time
                    )
                    
        except Exception as e:
            return HealthResult(
                component='agent_capability_drift',
                status=HealthStatus.UNKNOWN,
                message="Could not check capability drift",
                error=str(e)
            )
    
    def __del__(self):
        """Cleanup driver on destruction."""
        if self._driver:
            self._driver.close()
