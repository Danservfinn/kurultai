"""
Task Queue Health Checker - Phase 5 of Jochi Health Check Enhancement Plan

Monitors task queue health:
- Queue depth
- Failed tasks
- Stuck tasks
- Queue trend
- Auto-retry
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from neo4j import GraphDatabase

from .base import BaseHealthChecker, HealthResult, HealthStatus

logger = logging.getLogger(__name__)

# Configuration
NEO4J_URI = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD')

# Default thresholds
DEFAULT_THRESHOLDS = {
    'max_pending_tasks': 100,
    'max_failed_per_hour': 10,
    'stuck_task_minutes': 30,
    'max_growth_rate': 0.20,  # 20% per hour
}


class TaskHealthChecker(BaseHealthChecker):
    """Health checker for task queue monitoring."""
    
    def __init__(self, timeout_seconds: float = 30.0, thresholds: Optional[Dict] = None):
        super().__init__("task", timeout_seconds)
        self.uri = NEO4J_URI
        self.password = NEO4J_PASSWORD
        self.thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    
    async def check(self) -> HealthResult:
        """Run all task health checks."""
        start_time = asyncio.get_event_loop().time()
        
        # Run synchronous Neo4j checks in a thread pool
        loop = asyncio.get_event_loop()
        
        checks = [
            loop.run_in_executor(None, self._check_queue_depth),
            loop.run_in_executor(None, self._check_failed_tasks),
            loop.run_in_executor(None, self._check_stuck_tasks),
            loop.run_in_executor(None, self._check_queue_trend),
        ]
        
        results = await asyncio.gather(*checks, return_exceptions=True)
        
        # Aggregate results
        errors = []
        warnings = []
        details = {}
        
        for result in results:
            if isinstance(result, Exception):
                errors.append(f"Check failed: {result}")
                continue
                
            check_name = result.get('check')
            status = result.get('status')
            details[check_name] = result
            
            if status == 'error':
                errors.append(f"{check_name}: {result.get('message')}")
            elif status == 'warning':
                warnings.append(f"{check_name}: {result.get('message')}")
        
        response_time = (asyncio.get_event_loop().time() - start_time) * 1000
        
        # Determine overall status
        if errors:
            status = HealthStatus.CRITICAL
            message = f"Task queue critical: {'; '.join(errors)}"
        elif warnings:
            status = HealthStatus.WARNING
            message = f"Task queue degraded: {'; '.join(warnings)}"
        else:
            status = HealthStatus.HEALTHY
            message = "Task queue healthy"
        
        return HealthResult(
            component='task_queue',
            status=status,
            message=message,
            details=details,
            error='; '.join(errors) if errors else None,
            response_time_ms=response_time
        )
    
    def _get_driver(self):
        """Get Neo4j driver instance."""
        if not self.password:
            raise ValueError("NEO4J_PASSWORD environment variable not set")
        return GraphDatabase.driver(self.uri, auth=('neo4j', self.password))
    
    def _check_queue_depth(self) -> Dict[str, Any]:
        """Check pending task queue depth."""
        try:
            driver = self._get_driver()
            with driver.session() as session:
                result = session.run('''
                    MATCH (t:Task)
                    WHERE t.status IN ['pending', 'ready', 'in_progress']
                    RETURN t.status as status, count(*) as count
                ''')
                
                counts = {r['status']: r['count'] for r in result}
                driver.close()
                
                pending = counts.get('pending', 0) + counts.get('ready', 0)
                in_progress = counts.get('in_progress', 0)
                total = pending + in_progress
                
                details = {
                    'pending': pending,
                    'in_progress': in_progress,
                    'total': total
                }
                
                if total > self.thresholds['max_pending_tasks']:
                    return {
                        'check': 'queue_depth',
                        'status': 'warning',
                        'message': f'Queue depth {total} exceeds threshold {self.thresholds["max_pending_tasks"]}',
                        **details
                    }
                
                return {
                    'check': 'queue_depth',
                    'status': 'ok',
                    'message': f'Queue depth healthy ({pending} pending, {in_progress} in progress)',
                    **details
                }
                    
        except Exception as e:
            return {
                'check': 'queue_depth',
                'status': 'error',
                'message': f'Queue depth check failed: {str(e)}'
            }
    
    def _check_failed_tasks(self) -> Dict[str, Any]:
        """Check for failed tasks in the last hour."""
        try:
            driver = self._get_driver()
            with driver.session() as session:
                one_hour_ago = datetime.now() - timedelta(hours=1)
                
                result = session.run('''
                    MATCH (t:Task)
                    WHERE t.status = 'failed' AND t.updated_at > $since
                    RETURN count(*) as failed_count
                ''', since=one_hour_ago)
                
                record = result.single()
                driver.close()
                
                failed_count = record['failed_count'] if record else 0
                
                details = {
                    'failed_last_hour': failed_count
                }
                
                if failed_count > self.thresholds['max_failed_per_hour']:
                    return {
                        'check': 'failed_tasks',
                        'status': 'warning',
                        'message': f'{failed_count} failed tasks in last hour (threshold: {self.thresholds["max_failed_per_hour"]})',
                        **details
                    }
                
                return {
                    'check': 'failed_tasks',
                    'status': 'ok',
                    'message': f'Failed tasks within bounds ({failed_count} in last hour)',
                    **details
                }
                    
        except Exception as e:
            return {
                'check': 'failed_tasks',
                'status': 'warning',
                'message': f'Failed tasks check failed: {str(e)}'
            }
    
    def _check_stuck_tasks(self) -> Dict[str, Any]:
        """Check for tasks stuck in progress."""
        try:
            driver = self._get_driver()
            with driver.session() as session:
                stuck_threshold = datetime.now() - timedelta(minutes=self.thresholds['stuck_task_minutes'])
                
                result = session.run('''
                    MATCH (t:Task)
                    WHERE t.status = 'in_progress' 
                      AND t.claimed_at < $threshold
                    RETURN t.id as task_id, 
                           t.claimed_by as claimed_by,
                           t.claimed_at as claimed_at,
                           t.description as description
                    LIMIT 20
                ''', threshold=stuck_threshold)
                
                stuck_tasks = list(result)
                driver.close()
                
                details = {
                    'stuck_count': len(stuck_tasks),
                    'stuck_tasks': [
                        {
                            'id': t['task_id'],
                            'claimed_by': t['claimed_by'],
                            'claimed_at': t['claimed_at'].isoformat() if t['claimed_at'] else None,
                            'description': t['description'][:100] if t['description'] else None
                        }
                        for t in stuck_tasks
                    ]
                }
                
                if stuck_tasks:
                    return {
                        'check': 'stuck_tasks',
                        'status': 'warning',
                        'message': f'{len(stuck_tasks)} tasks stuck >{self.thresholds["stuck_task_minutes"]} minutes',
                        **details
                    }
                
                return {
                    'check': 'stuck_tasks',
                    'status': 'ok',
                    'message': 'No stuck tasks detected',
                    **details
                }
                    
        except Exception as e:
            return {
                'check': 'stuck_tasks',
                'status': 'warning',
                'message': f'Stuck tasks check failed: {str(e)}'
            }
    
    def _check_queue_trend(self) -> Dict[str, Any]:
        """Check queue growth trend."""
        try:
            driver = self._get_driver()
            with driver.session() as session:
                # Compare queue depth now vs 1 hour ago
                one_hour_ago = datetime.now() - timedelta(hours=1)
                
                result = session.run('''
                    MATCH (t:Task)
                    WHERE t.status IN ['pending', 'ready']
                    WITH count(*) as current_count
                    MATCH (t:Task)
                    WHERE t.created_at < $since AND t.status IN ['pending', 'ready']
                    WITH current_count, count(*) as old_count
                    RETURN current_count, old_count
                ''', since=one_hour_ago)
                
                record = result.single()
                driver.close()
                
                if record:
                    current = record['current_count']
                    old = record['old_count']
                    
                    if old > 0:
                        growth_rate = (current - old) / old
                    else:
                        growth_rate = 0 if current == 0 else float('inf')
                    
                    details = {
                        'current_pending': current,
                        'pending_hour_ago': old,
                        'growth_rate': round(growth_rate, 2)
                    }
                    
                    if growth_rate > self.thresholds['max_growth_rate']:
                        return {
                            'check': 'queue_trend',
                            'status': 'warning',
                            'message': f'Queue growing at {growth_rate:.1%}/hour (threshold: {self.thresholds["max_growth_rate"]:.1%})',
                            **details
                        }
                    
                    return {
                        'check': 'queue_trend',
                        'status': 'ok',
                        'message': f'Queue trend stable ({growth_rate:+.1%}/hour)',
                        **details
                    }
                
                return {
                    'check': 'queue_trend',
                    'status': 'ok',
                    'message': 'Queue trend check skipped (insufficient data)'
                }
                    
        except Exception as e:
            return {
                'check': 'queue_trend',
                'status': 'warning',
                'message': f'Queue trend check failed: {str(e)}'
            }
    
    async def retry_failed_tasks(self, max_retries: int = 3) -> Dict[str, Any]:
        """Retry failed tasks (called separately from health check)."""
        try:
            driver = self._get_driver()
            with driver.session() as session:
                # Find failed tasks with retries left
                result = session.run('''
                    MATCH (t:Task)
                    WHERE t.status = 'failed'
                      AND (t.retry_count IS NULL OR t.retry_count < $max_retries)
                    RETURN t.id as task_id, t.retry_count as retry_count
                    LIMIT 10
                ''', max_retries=max_retries)
                
                tasks_to_retry = list(result)
                
                retried = []
                for task in tasks_to_retry:
                    # Reset task to pending
                    session.run('''
                        MATCH (t:Task {id: $task_id})
                        SET t.status = 'pending',
                            t.retry_count = coalesce(t.retry_count, 0) + 1,
                            t.error_message = NULL,
                            t.updated_at = datetime()
                    ''', task_id=task['task_id'])
                    
                    retried.append(task['task_id'])
                
                driver.close()
                
                return {
                    'retried_count': len(retried),
                    'retried_tasks': retried
                }
                    
        except Exception as e:
            return {
                'error': str(e),
                'retried_count': 0
            }
