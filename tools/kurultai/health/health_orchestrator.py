"""
Health Orchestrator - Central coordinator for all health checks

Runs all health checkers, aggregates results, and handles scheduling.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from neo4j import GraphDatabase

from .base import HealthResult, HealthStatus, HealthSummary
from .signal_health import SignalHealthChecker
from .system_health import SystemHealthChecker
from .neo4j_health import Neo4jHealthChecker
from .agent_health import AgentHealthChecker
from .task_health import TaskHealthChecker
from .security_health import SecurityHealthChecker
from .external_health import ExternalHealthChecker

logger = logging.getLogger(__name__)


class HealthOrchestrator:
    """Orchestrates all health checks and aggregates results."""
    
    def __init__(
        self,
        neo4j_uri: str = 'bolt://localhost:7687',
        neo4j_password: Optional[str] = None,
        enable_signal: bool = True,
        enable_system: bool = True,
        enable_neo4j: bool = True,
        enable_agent: bool = True,
        enable_task: bool = True,
        enable_security: bool = True,
        enable_external: bool = True,
    ):
        self.neo4j_uri = neo4j_uri
        self.neo4j_password = neo4j_password
        
        # Initialize checkers based on configuration
        self.checkers = []
        
        if enable_signal:
            self.checkers.append(SignalHealthChecker())
        if enable_system:
            self.checkers.append(SystemHealthChecker())
        if enable_neo4j:
            self.checkers.append(Neo4jHealthChecker())
        if enable_agent:
            self.checkers.append(AgentHealthChecker())
        if enable_task:
            self.checkers.append(TaskHealthChecker())
        if enable_security:
            self.checkers.append(SecurityHealthChecker())
        if enable_external:
            self.checkers.append(ExternalHealthChecker())
    
    async def run_all_checks(self) -> HealthSummary:
        """Run all enabled health checks concurrently."""
        logger.info(f"Running {len(self.checkers)} health checks...")
        
        start_time = asyncio.get_event_loop().time()
        
        # Run all checks concurrently
        results = await asyncio.gather(
            *[checker.check() for checker in self.checkers],
            return_exceptions=True
        )
        
        total_time = asyncio.get_event_loop().time() - start_time
        logger.info(f"All health checks completed in {total_time:.2f}s")
        
        # Process results
        processed_results = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Health check failed with exception: {result}")
                processed_results.append(HealthResult(
                    component='unknown',
                    status=HealthStatus.UNKNOWN,
                    message=f'Check failed: {str(result)}',
                    error=str(result)
                ))
            else:
                processed_results.append(result)
        
        # Create summary
        healthy_count = sum(1 for r in processed_results if r.status == HealthStatus.HEALTHY)
        warning_count = sum(1 for r in processed_results if r.status == HealthStatus.WARNING)
        critical_count = sum(1 for r in processed_results if r.status == HealthStatus.CRITICAL)
        unknown_count = sum(1 for r in processed_results if r.status == HealthStatus.UNKNOWN)
        
        summary = HealthSummary(
            healthy_count=healthy_count,
            warning_count=warning_count,
            critical_count=critical_count,
            unknown_count=unknown_count,
            total_count=len(processed_results),
            results=processed_results
        )
        
        return summary
    
    def run_all_checks_sync(self) -> HealthSummary:
        """Synchronous version of run_all_checks."""
        return asyncio.run(self.run_all_checks())
    
    async def run_and_log(self, driver=None) -> HealthSummary:
        """Run checks and log results to Neo4j."""
        summary = await self.run_all_checks()
        
        # Log to Neo4j if driver provided
        if driver or self.neo4j_password:
            try:
                self._log_to_neo4j(summary, driver)
            except Exception as e:
                logger.error(f"Failed to log health results to Neo4j: {e}")
        
        return summary
    
    def _log_to_neo4j(self, summary: HealthSummary, driver=None):
        """Log health check results to Neo4j."""
        if driver is None:
            driver = GraphDatabase.driver(
                self.neo4j_uri,
                auth=('neo4j', self.neo4j_password)
            )
            close_driver = True
        else:
            close_driver = False
        
        try:
            with driver.session() as session:
                # Create summary node
                summary_result = session.run('''
                    CREATE (hs:HealthSummary {
                        id: randomUUID(),
                        timestamp: datetime(),
                        overall_status: $overall_status,
                        healthy_count: $healthy_count,
                        warning_count: $warning_count,
                        critical_count: $critical_count,
                        unknown_count: $unknown_count,
                        total_count: $total_count
                    })
                    RETURN hs.id as summary_id
                ''',
                    overall_status=summary.overall_status.value,
                    healthy_count=summary.healthy_count,
                    warning_count=summary.warning_count,
                    critical_count=summary.critical_count,
                    unknown_count=summary.unknown_count,
                    total_count=summary.total_count
                )
                
                summary_record = summary_result.single()
                summary_id = summary_record['summary_id']
                
                # Create individual check results
                for result in summary.results:
                    session.run('''
                        MATCH (hs:HealthSummary {id: $summary_id})
                        CREATE (hr:HealthResult {
                            component: $component,
                            status: $status,
                            message: $message,
                            error: $error,
                            response_time_ms: $response_time_ms,
                            timestamp: datetime()
                        })
                        CREATE (hs)-[:HAS_RESULT]->(hr)
                    ''',
                        summary_id=summary_id,
                        component=result.component,
                        status=result.status.value if isinstance(result.status, HealthStatus) else result.status,
                        message=result.message,
                        error=result.error,
                        response_time_ms=result.response_time_ms
                    )
                
                logger.info(f"Health results logged to Neo4j with summary ID: {summary_id}")
                
        finally:
            if close_driver:
                driver.close()
    
    def get_critical_issues(self, summary: HealthSummary) -> List[HealthResult]:
        """Get list of critical issues from summary."""
        return [r for r in summary.results if r.status == HealthStatus.CRITICAL]
    
    def get_warnings(self, summary: HealthSummary) -> List[HealthResult]:
        """Get list of warnings from summary."""
        return [r for r in summary.results if r.status == HealthStatus.WARNING]
    
    def format_report(self, summary: HealthSummary) -> str:
        """Format health summary as human-readable report."""
        lines = [
            "=" * 60,
            "HEALTH CHECK REPORT",
            f"Generated: {summary.timestamp.isoformat()}",
            f"Overall Status: {summary.overall_status.value.upper()}",
            "-" * 60,
            f"  Healthy:   {summary.healthy_count}/{summary.total_count}",
            f"  Warning:   {summary.warning_count}/{summary.total_count}",
            f"  Critical:  {summary.critical_count}/{summary.total_count}",
            f"  Unknown:   {summary.unknown_count}/{summary.total_count}",
            "-" * 60,
        ]
        
        # Add details for non-healthy results
        for result in summary.results:
            if result.status != HealthStatus.HEALTHY:
                lines.append(f"\n[{result.status.value.upper()}] {result.component}")
                lines.append(f"  Message: {result.message}")
                if result.error:
                    lines.append(f"  Error: {result.error}")
                if result.response_time_ms > 0:
                    lines.append(f"  Response Time: {result.response_time_ms:.1f}ms")
        
        lines.append("=" * 60)
        
        return "\n".join(lines)


# Convenience function for simple usage
async def run_health_checks(
    neo4j_uri: str = 'bolt://localhost:7687',
    neo4j_password: Optional[str] = None,
    **kwargs
) -> HealthSummary:
    """Run all health checks and return summary."""
    orchestrator = HealthOrchestrator(
        neo4j_uri=neo4j_uri,
        neo4j_password=neo4j_password,
        **kwargs
    )
    return await orchestrator.run_and_log()
